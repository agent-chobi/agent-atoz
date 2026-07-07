"""
step1_agent.py — [캡스톤 Step 1] 단일 리서치 에이전트 (docs/22-capstone-project.md)

미니 리서치 팀의 출발점: 도구(web_search)를 쥔 리서치 에이전트 하나.
create_react_agent 가 '생각 → 도구 호출 → 관찰'의 에이전트 루프(02장)를 대신 돌린다.

- 이 파일의 web_search / build_research_agent 는 Step 2~5 가 그대로 import 해 재사용한다.
- web_search 는 데모용 가짜 구현(고정 응답)이다. 실전에서는 Tavily·MCP 검색 서버 등으로 교체.

[실행법]
  pip install -r requirements.txt
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/project/step1_agent.py

[기대 출력 예시]
  === Step 1: 단일 리서치 에이전트 ===
  [도구 호출] web_search(query='멀티에이전트 시스템 토큰 오버헤드')
  [최종 답변]
  멀티에이전트 시스템은 단일 에이전트 대비 토큰 오버헤드가 큽니다.
  중앙집중형은 약 +285%, 독립형은 약 +58% 수준이며 ...

[흔한 에러]
  - SystemExit "ANTHROPIC_API_KEY 가 없습니다" → .env 확인
  - ImportError: langgraph → pip install -r requirements.txt
  - 도구를 안 부르고 바로 답함 → 프롬프트에 "반드시 web_search 로 확인" 문구가 있는지 확인
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 출력이 깨지지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

# 기본은 가장 강력한 Opus. 비용을 아끼려면 아래 한 줄로 교체:
# MODEL = "claude-haiku-4-5"   # 빠르고 저렴
MODEL = "claude-opus-4-8"


# ── 리서치 도구 (데모용 가짜 검색 — Step 2~5 에서도 재사용) ────────────────
def web_search(query: str) -> str:
    """웹에서 정보를 검색한다. (데모용 고정 지식 베이스)"""
    print(f"[도구 호출] web_search(query={query!r})")
    return (
        "검색 결과 요약:\n"
        "- 멀티에이전트는 단일 에이전트 대비 토큰 오버헤드가 크다 "
        "(중앙집중형 약 +285%, 독립형 약 +58%).\n"
        "- 그럼에도 전문화·병렬성·비평(critique)이 필요할 때는 품질 이득이 비용을 이긴다.\n"
        "- 2026년 프로덕션 오케스트레이션의 다수(~70%)는 supervisor 패턴이다.\n"
        "- Anthropic 의 멀티에이전트 리서치 시스템은 orchestrator-worker 구조로 "
        "단일 Opus 대비 내부 평가에서 90.2% 우세했지만 토큰을 약 15배 썼다."
    )


def build_research_agent(model):
    """도구를 쥔 리서치 에이전트를 만든다. (Step 2 supervisor 의 워커로도 쓰인다)"""
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        model=model,
        tools=[web_search],
        name="research_expert",  # supervisor(Step 2)가 이 이름으로 라우팅한다
        prompt=(
            "너는 리서처다. 사실 관계는 반드시 web_search 도구로 확인한 뒤, "
            "출처가 있는 간결한 불릿으로 정리하라. 지어내지 마라."
        ),
    )


def main() -> None:
    # API 키 가드: 모델(클라이언트) 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(model=MODEL)
    agent = build_research_agent(model)

    print("=== Step 1: 단일 리서치 에이전트 ===")
    result = agent.invoke(
        {"messages": [("user", "멀티에이전트 시스템의 토큰 오버헤드가 얼마나 되는지 조사해줘.")]}
    )
    print("[최종 답변]")
    print(result["messages"][-1].content)


if __name__ == "__main__":
    main()
