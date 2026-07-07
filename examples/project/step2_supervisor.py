"""
step2_supervisor.py — [캡스톤 Step 2] supervisor + 워커 2개 (docs/22-capstone-project.md)

Step 1 의 리서치 에이전트를 그대로 워커로 재사용하고, 작가 워커를 추가한 뒤
langgraph-supervisor 의 create_supervisor() 로 팀을 만든다 (09장, 12번 예제와 동일 방식).

- supervisor 가 요청을 보고 research_expert → writing_expert 순으로 위임한다(hub-and-spoke).
- 이 파일의 build_team() 은 Step 3~5 가 그대로 import 해 재사용한다.
  checkpointer 인자를 받아 두어 Step 3(중단/재개)에서 그대로 확장된다.

[실행법]
  pip install -r requirements.txt   # langgraph-supervisor 포함
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/project/step2_supervisor.py

[기대 출력 예시]
  === Step 2: supervisor + 리서처/작가 워커 ===
  [도구 호출] web_search(query='supervisor 패턴 채택률')
  [최종 답변]
  2026년 프로덕션 멀티에이전트의 다수는 supervisor 패턴을 씁니다. ...

  === 라우팅 추적 (누가 언제 말했나) ===
  [human] supervisor 패턴이 왜 기본값인지 ...
  [supervisor] ...
  [research_expert] ...
  [writing_expert] ...

[흔한 에러]
  - ImportError: langgraph_supervisor → pip install langgraph-supervisor
  - 워커 이름 불일치 → create_react_agent(name=...) 과 supervisor 프롬프트의 이름이 같아야 라우팅됨
  - supervisor 가 직접 답해버림 → 프롬프트에 "직접 답하지 말고 워커에게 위임" 명시
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

# Step 1 에서 만든 리서치 에이전트를 그대로 재사용 (누적 확장)
from step1_agent import build_research_agent  # noqa: E402

# 기본은 가장 강력한 Opus. 비용을 아끼려면 아래 한 줄로 교체:
# MODEL = "claude-haiku-4-5"   # 빠르고 저렴
MODEL = "claude-opus-4-8"


def build_writer_agent(model):
    """리서치 노트를 읽기 좋은 보고서로 다듬는 작가 워커."""
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        model=model,
        tools=[],  # 작가는 도구 없이 글쓰기에 집중 (최소권한, 14장)
        name="writing_expert",
        prompt=(
            "너는 기술 작가다. 주어진 리서치 노트를 3~4문장의 한국어 보고서 단락으로 "
            "매끄럽게 다듬어라. 새로운 사실을 추가하지 마라."
        ),
    )


def build_team(model, checkpointer=None):
    """supervisor + 워커 2개로 구성된 리서치 팀 그래프를 컴파일해 반환한다.

    checkpointer 를 넘기면 thread 단위 상태 영속화가 켜진다 (Step 3에서 사용).
    """
    from langgraph_supervisor import create_supervisor

    workflow = create_supervisor(
        [build_research_agent(model), build_writer_agent(model)],
        model=model,
        prompt=(
            "너는 리서치 팀의 supervisor 다. 리서처(research_expert)와 "
            "작가(writing_expert)를 관리한다.\n"
            "규칙: 사실 조사가 필요하면 먼저 research_expert 에게 위임하고, "
            "조사 결과를 글로 다듬을 때는 writing_expert 에게 위임하라. "
            "직접 답을 쓰지 말고 워커를 활용하라."
        ),
    )
    return workflow.compile(checkpointer=checkpointer)


def print_routing_trace(messages) -> None:
    """누가 언제 말했는지(라우팅 순서)를 한 줄씩 출력한다."""
    print("\n=== 라우팅 추적 (누가 언제 말했나) ===")
    for m in messages:
        who = getattr(m, "name", None) or m.type
        content = m.content if isinstance(m.content, str) else str(m.content)
        preview = content.replace("\n", " ")[:80]
        print(f"[{who}] {preview}")


def main() -> None:
    # API 키 가드: 모델(클라이언트) 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(model=MODEL)
    team = build_team(model)

    print("=== Step 2: supervisor + 리서처/작가 워커 ===")
    result = team.invoke(
        {
            "messages": [
                (
                    "user",
                    "2026년 멀티에이전트에서 supervisor 패턴이 왜 기본값인지 "
                    "조사해서 한 단락 보고서로 써줘.",
                )
            ]
        }
    )

    print("[최종 답변]")
    print(result["messages"][-1].content)
    print_routing_trace(result["messages"])


if __name__ == "__main__":
    main()
