"""
19_tracing.py — 에이전트 실행 트레이싱 (LangSmith / Langfuse / 자체 폴백)

[문서] docs/13-debugging-observability.md

에이전트 관측의 핵심은 "왜 저 도구를 골랐는가"(의도 가시성)입니다.
이 예제는 간단한 도구 사용 에이전트 루프를 만들고, 각 단계(프롬프트/도구선택/도구입출력)를
트레이스 span으로 남깁니다.

세 가지 방식을 방어적으로 시도합니다.
  1) LangSmith  — 환경변수만 설정되어 있으면 `@traceable`로 자동 기록.
  2) Langfuse   — 설치+설정 시 span 기록(선택).
  3) 자체 폴백  — 관측 SDK가 없어도 콘솔에 span 트리를 출력하여 에이전트는 항상 동작.

────────────────────────────────────────────────────────────────────
[실행법]
  pip install anthropic python-dotenv
  # (선택) 트레이싱: pip install langsmith
  #   .env 또는 셸에 아래를 설정하면 LangSmith로 전송됩니다.
  #     LANGSMITH_TRACING=true
  #     LANGSMITH_API_KEY=ls-...
  #     LANGSMITH_PROJECT=agent-atoz          # 선택
  #     # EU 리전: LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
  python examples/19_tracing.py

  트레이싱을 설정하지 않아도 콘솔에 자체 span 트리가 출력됩니다.
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import sys
import time

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 이모지/트리 문자가 깨지지 않도록 UTF-8 출력 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
except Exception:
    pass

load_dotenv()  # .env 에서 API 키 / 트레이싱 환경변수 로드

# 기본 모델 (비용 절감: "claude-haiku-4-5" 로 교체)
MODEL = "claude-opus-4-8"

# ── 관측 SDK 방어적 로딩 ────────────────────────────────────────────
# LangSmith: 환경변수 LANGSMITH_TRACING=true 이고 패키지가 설치돼 있을 때만 활성화.
_LS_ON = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
try:
    from langsmith import traceable  # type: ignore

    _HAS_LANGSMITH = True
except Exception:  # 미설치 시에도 예제는 동작해야 함
    _HAS_LANGSMITH = False

    def traceable(*d_args, **d_kwargs):  # no-op 데코레이터 폴백
        def _wrap(fn):
            return fn

        # @traceable 와 @traceable(...) 두 형태 모두 지원
        if len(d_args) == 1 and callable(d_args[0]) and not d_kwargs:
            return d_args[0]
        return _wrap


def _tracing_status() -> str:
    if _HAS_LANGSMITH and _LS_ON:
        return "LangSmith ON (환경변수 감지)"
    if _HAS_LANGSMITH and not _LS_ON:
        return "LangSmith 설치됨 / LANGSMITH_TRACING 미설정 → 자체 폴백"
    return "LangSmith 미설치 → 자체 폴백"


# ── 자체 폴백 span 트레이서 (콘솔 트리) ─────────────────────────────
# 관측 백엔드가 없어도 "무엇을 로깅해야 하는가"를 눈으로 보여주기 위한 최소 구현.
class ConsoleTracer:
    def __init__(self) -> None:
        self._depth = 0

    def span(self, name: str, **fields):
        tracer = self

        class _Span:
            def __enter__(self_inner):
                indent = "  " * tracer._depth
                print(f"{indent}▶ {name}")
                for k, v in fields.items():
                    print(f"{indent}    {k}: {_short(v)}")
                tracer._depth += 1
                self_inner._t0 = time.time()
                return self_inner

            def __exit__(self_inner, *exc):
                tracer._depth -= 1
                dt = (time.time() - self_inner._t0) * 1000
                indent = "  " * tracer._depth
                mark = "OK" if exc[0] is None else "ERR"
                print(f"{indent}  └ {mark} {name} ({dt:.0f}ms)")
                return False

        return _Span()


def _short(v, n: int = 120) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


TRACER = ConsoleTracer()

# ── 도구 정의 (계산기) ──────────────────────────────────────────────
TOOLS = [
    {
        "name": "calculator",
        "description": "간단한 사칙연산을 계산한다. 예: '12 * (3 + 4)'",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    }
]


@traceable(run_type="tool", name="calculator")  # LangSmith span (있으면)
def run_calculator(expression: str) -> str:
    """안전한 계산기: 숫자/연산자만 허용."""
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return "error: 허용되지 않은 문자"
    try:
        # 로깅해야 할 것: 도구 입력·출력·에러 (13장 §2)
        return str(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 (샌드박스된 입력)
    except Exception as e:  # 도구 에러도 트레이스로 남긴다
        return f"error: {e}"


@traceable(run_type="chain", name="agent_loop")  # 루트 span (있으면)
def agent_loop(question: str) -> str:
    """생각→행동→관찰 루프. 각 단계를 span으로 기록한다."""
    from anthropic import Anthropic

    client = Anthropic()  # ANTHROPIC_API_KEY 사용
    messages = [{"role": "user", "content": question}]

    with TRACER.span("agent_loop", question=question):
        for turn in range(5):  # 무한루프 방지
            with TRACER.span(f"llm_call (turn {turn})", model=MODEL):
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    tools=TOOLS,
                    messages=messages,
                )
            # 결정 분기 로깅: stop_reason 이 곧 에이전트의 의도 신호
            print(f"      stop_reason = {resp.stop_reason}")

            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return text.strip()

            # 도구 호출 처리
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                with TRACER.span(
                    f"tool: {block.name}", input=block.input
                ):
                    if block.name == "calculator":
                        out = run_calculator(block.input["expression"])
                    else:
                        out = f"error: 알 수 없는 도구 {block.name}"
                    print(f"        output = {out}")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": out,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        return "중단: 최대 턴 수 초과"


def main() -> None:
    print("=" * 64)
    print("19_tracing.py — 에이전트 트레이싱")
    print(f"트레이싱 상태: {_tracing_status()}")
    print("=" * 64)

    question = "12 곱하기 (3 더하기 4)는 얼마야? 계산기를 써서 알려줘."
    answer = agent_loop(question)

    print("-" * 64)
    print(f"질문: {question}")
    print(f"답변: {answer}")
    if _HAS_LANGSMITH and _LS_ON:
        print("\n→ https://smith.langchain.com 프로젝트에서 트레이스 트리를 확인하세요.")
    else:
        print("\n(위 콘솔 트리가 곧 트레이스입니다. LangSmith 설정 시 웹 UI로도 볼 수 있습니다.)")


if __name__ == "__main__":
    main()
