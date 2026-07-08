"""
28_serve_fastapi.py — FastAPI + SSE(StreamingResponse)로 에이전트 응답 스트리밍 서빙

[문서] docs/24-deployment-operations.md

에이전트 응답은 수십 초씩 걸리므로, 토큰을 생기는 즉시 클라이언트로 흘리는
스트리밍 서빙이 프로덕션 기본값입니다. 서버→클라이언트 단방향 스트림에는
WebSocket 대신 **SSE(Server-Sent Events)** 가 표준 — 일반 HTTP라 프록시를 그대로
통과하고, 브라우저 EventSource 가 재연결을 내장합니다.

이 예제는 추가 라이브러리(sse-starlette) 없이 **표준 StreamingResponse 만으로**
  - GET /health       : 헬스체크 (배포·로드밸런서용)
  - GET /chat/stream  : 에이전트 응답을 SSE 프레임(data: {json}\\n\\n)으로 스트리밍
을 제공합니다. lifespan 에서 클라이언트를 만들고 종료 시 정리하는 구조는
그레이스풀 셧다운의 축소판입니다.

────────────────────────────────────────────────────────────────────
[실행법]
  pip install fastapi uvicorn anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/28_serve_fastapi.py        # 127.0.0.1:8000 에서 uvicorn 기동

  # ── 다른 터미널에서 테스트 ──
  curl http://127.0.0.1:8000/health
  curl -N --get --data-urlencode "q=SSE가 뭐야? 두 문장으로" http://127.0.0.1:8000/chat/stream
  #    ^ -N (--no-buffer) 이 없으면 curl 이 출력을 모아서 보여줘 스트리밍처럼 안 보임
────────────────────────────────────────────────────────────────────

[기대 출력 예시] (curl -N 쪽 터미널 — 토큰이 실시간으로 흘러나오면 성공)
  data: {"type": "start", "model": "claude-haiku-4-5"}

  data: {"type": "token", "text": "SSE"}

  data: {"type": "token", "text": "(Server-Sent Events)는 서버가"}
  ...
  data: {"type": "done", "input_tokens": 32, "output_tokens": 118}

[흔한 에러]
  - RuntimeError: ANTHROPIC_API_KEY ... : .env 미설정 → 키 가드가 기동 자체를 막음(의도된 동작)
  - ModuleNotFoundError: No module named 'fastapi' → pip install fastapi uvicorn
  - [Errno 10048/98] Address already in use : 8000 포트 점유 → 하단 uvicorn.run 의 port 변경
  - curl 출력이 끝나고 한 번에 나옴 : -N 플래그 누락 (프록시 뒤라면 X-Accel-Buffering 확인)
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

# Windows 한글 콘솔(cp949)에서도 로그가 깨지지 않도록 UTF-8 출력 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
except Exception:
    pass

load_dotenv()

MODEL = "claude-haiku-4-5"  # 고성능 필요 시: "claude-opus-4-8" 로 변경

SYSTEM_PROMPT = "너는 간결하게 답하는 도우미다. 질문에 2~4문장으로 답하라."


# ── 0. API 키 가드 — 클라이언트 생성보다 먼저 ───────────────────────
def require_api_key() -> None:
    """키가 없으면 서버를 띄우지 않는다 — 첫 요청에서야 실패하는 것보다 낫다."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY 가 없습니다. .env 에 설정하세요. "
            "(예: ANTHROPIC_API_KEY=sk-ant-...)"
        )


# ── 1. lifespan — 기동 시 클라이언트 생성, 종료 시 정리 ─────────────
# 프로덕션 그레이스풀 셧다운의 축소판: SIGTERM → uvicorn 이 새 요청을 끊고
# 진행 중 응답을 마무리 → lifespan 의 yield 이후 코드로 리소스 정리.
@asynccontextmanager
async def lifespan(app: FastAPI):
    require_api_key()  # 키 확인이 먼저 —
    app.state.client = anthropic.AsyncAnthropic()  # — 클라이언트는 그 다음 (모듈 레벨 생성 금지)
    print(f"[startup] 준비 완료 — model={MODEL}")
    yield
    await app.state.client.close()  # 커넥션 정리
    print("[shutdown] 클라이언트 정리 완료")


app = FastAPI(title="agent-atoz SSE 서빙 예제", lifespan=lifespan)


# ── 2. 헬스체크 ──────────────────────────────────────────────────────
# liveness 용 — 프로세스 생존 확인. LLM 을 호출하지 않는다(헬스체크가 청구서가 된다).
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL}


# ── 3. SSE 스트리밍 엔드포인트 ───────────────────────────────────────
def sse(data: dict) -> str:
    """dict 하나를 SSE 프레임 한 개로 직렬화한다. (형식: 'data: {json}\\n\\n')"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/chat/stream")
async def chat_stream(q: str):
    """에이전트 응답을 SSE 로 스트리밍한다.

    LangGraph 라면 graph.astream(stream_mode=...) 청크를 같은 방식으로
    SSE 프레임에 담으면 된다(docs/24 §4). 여기서는 최소 골격을 위해
    anthropic SDK 의 스트리밍을 직접 쓴다.
    """
    client: anthropic.AsyncAnthropic = app.state.client

    async def event_gen():
        yield sse({"type": "start", "model": MODEL})
        try:
            async with client.messages.stream(
                model=MODEL,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": q}],
            ) as stream:
                async for text in stream.text_stream:  # 토큰 델타를 생기는 즉시 방류
                    yield sse({"type": "token", "text": text})
                final = await stream.get_final_message()
            # usage 를 함께 내려 주면 클라이언트/게이트웨이에서 비용 집계 가능 (docs/24 §6)
            yield sse({
                "type": "done",
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            })
        except Exception as e:  # 스트림 도중 에러도 SSE 이벤트로 알린다 (연결만 뚝 끊지 않기)
            yield sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",     # 중간 캐시가 스트림을 저장하지 않도록
            "X-Accel-Buffering": "no",       # Nginx 류 프록시의 응답 버퍼링 해제
        },
    )


# ── 4. 기동 ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    # 개발용 단일 프로세스. 프로덕션은 "1컨테이너 1워커 × 레플리카"가 정석 (docs/24 설계 가이드)
    uvicorn.run(app, host="127.0.0.1", port=8000)
