"""
12_supervisor.py — Supervisor 패턴 (중앙 라우팅)

한 명의 supervisor(코디네이터)가 여러 전문 워커에게 작업을 라우팅합니다.
여기서는 워커 2개(리서처 / 작가)를 두고, supervisor가 사용자 요청을 보고
"먼저 리서처 → 그다음 작가" 순으로 제어를 넘깁니다.

- 제어권은 항상 supervisor를 거칩니다(hub-and-spoke). 워커끼리 직접 대화하지 않습니다.
- 라이브러리: langgraph-supervisor 의 create_supervisor()
- 각 워커는 langgraph.prebuilt.create_react_agent 로 만든 독립 에이전트입니다.

실행:
    pip install -U langgraph langgraph-supervisor langchain-anthropic
    python examples/12_supervisor.py

참고: LangChain 1.0 계열에서는 create_react_agent 대신
      `from langchain.agents import create_agent` 를 쓰기도 합니다. 설치 버전 대조 필요.
"""

import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor

load_dotenv()

# 비용을 아끼려면 "claude-haiku-4-5" 로 교체하세요.
MODEL = "claude-opus-4-8"
# MODEL = "claude-haiku-4-5"


# --- 워커가 사용할 도구 (데모용 가짜 구현) -----------------------------------
def web_search(query: str) -> str:
    """웹에서 정보를 검색한다(데모용 고정 응답)."""
    return (
        "검색 결과 요약:\n"
        "- LangGraph 는 2026년 프로덕션 멀티에이전트의 사실상 표준 그래프 런타임이다.\n"
        "- supervisor 패턴이 전체 오케스트레이션의 약 70%를 차지한다.\n"
        "- 중앙집중형은 토큰 오버헤드가 크지만 제어·관측이 명확하다."
    )


# --- 전문 워커 2개 -----------------------------------------------------------
model = ChatAnthropic(model=MODEL, temperature=0)

research_agent = create_react_agent(
    model=model,
    tools=[web_search],
    name="research_expert",  # supervisor 가 이 이름으로 라우팅한다
    prompt="너는 리서처다. web_search 도구로 사실을 모아 간결한 불릿으로 정리하라.",
)

writer_agent = create_react_agent(
    model=model,
    tools=[],  # 작가는 도구 없이 글쓰기에 집중
    name="writing_expert",
    prompt="너는 기술 작가다. 주어진 리서치 노트를 3문장 한국어 단락으로 매끄럽게 다듬어라.",
)

# --- Supervisor: 워커들을 라우팅하는 중앙 코디네이터 -------------------------
workflow = create_supervisor(
    [research_agent, writer_agent],
    model=model,
    prompt=(
        "너는 팀 supervisor다. 리서처(research_expert)와 작가(writing_expert)를 관리한다.\n"
        "규칙: 사실 조사가 필요하면 먼저 research_expert 에게 위임하고,\n"
        "글 정리가 필요하면 writing_expert 에게 위임하라. 직접 답을 쓰지 말고 워커를 활용하라."
    ),
)

# create_supervisor 는 StateGraph 를 돌려주므로 compile 해야 실행 가능하다.
app = workflow.compile()


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    result = app.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "2026년 멀티에이전트에서 supervisor 패턴이 왜 기본값인지 조사해서 한 단락으로 써줘.",
                }
            ]
        }
    )

    # 최종 메시지만 출력 (전체 라우팅 로그를 보려면 result["messages"] 전체를 순회하세요)
    print("\n=== 최종 답변 ===")
    print(result["messages"][-1].content)

    print("\n=== 라우팅 추적 (누가 언제 말했나) ===")
    for m in result["messages"]:
        who = getattr(m, "name", None) or m.type
        preview = (m.content or "").replace("\n", " ")[:80]
        print(f"[{who}] {preview}")


if __name__ == "__main__":
    main()
