"""
13_swarm.py — Swarm 패턴 (peer-to-peer handoff)

supervisor 같은 중개자 없이, 피어 에이전트들이 서로에게 제어권을 직접 넘깁니다(handoff).
handoff 도구를 호출하면 내부적으로 Command(goto=대상에이전트) 로 그래프 제어가 이동하고,
swarm 은 "마지막으로 활성화된 에이전트"를 상태에 기억합니다(멀티턴 재개용).

- 라이브러리: langgraph-swarm 의 create_swarm(), create_handoff_tool()
- Alice(수학 담당) ↔ Bob(해적 말투 담당) 이 서로에게 넘깁니다.
- 멀티턴을 기억하려면 반드시 checkpointer 와 함께 compile 해야 합니다.

실행:
    pip install -U langgraph langgraph-swarm langchain-anthropic
    python examples/13_swarm.py

참고: 최신 langgraph-swarm 예제는 워커 생성에 langchain.agents.create_agent 를 쓰기도 합니다.
      여기서는 프로젝트 전반과 일관되게 langgraph.prebuilt.create_react_agent 를 사용합니다.
      시그니처가 다르면 설치 버전에 맞춰 교체하세요.
"""

import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm

load_dotenv()

MODEL = "claude-opus-4-8"
# MODEL = "claude-haiku-4-5"


def add(a: int, b: int) -> int:
    """두 정수를 더한다."""
    return a + b


model = ChatAnthropic(model=MODEL, temperature=0)

# --- 피어 에이전트 2개, 각자 상대에게 넘길 handoff 도구를 소지 -----------------
alice = create_react_agent(
    model=model,
    tools=[
        add,
        # 말투/캐릭터가 필요한 요청이면 Bob 에게 제어권을 직접 넘긴다.
        create_handoff_tool(agent_name="Bob", description="해적 말투가 필요하면 Bob 에게 넘겨라"),
    ],
    name="Alice",
    prompt="너는 Alice, 덧셈 전문가다. 계산은 네가 하고, 말투 연기가 필요하면 Bob 에게 넘겨라.",
)

bob = create_react_agent(
    model=model,
    tools=[
        create_handoff_tool(agent_name="Alice", description="수학 계산이 필요하면 Alice 에게 넘겨라"),
    ],
    name="Bob",
    prompt="너는 Bob, 해적처럼 말한다. 수학이 필요하면 Alice 에게 넘겨라.",
)

# --- Swarm 조립: default_active_agent 로 첫 진입점 지정 ------------------------
checkpointer = InMemorySaver()
workflow = create_swarm([alice, bob], default_active_agent="Alice")
app = workflow.compile(checkpointer=checkpointer)


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    # thread_id 로 대화 상태(마지막 활성 에이전트 포함)를 이어간다.
    config = {"configurable": {"thread_id": "swarm-demo-1"}}

    print("=== 턴 1: Bob 을 불러 해적 말투로 인사시키기 ===")
    turn1 = app.invoke(
        {"messages": [{"role": "user", "content": "Bob 이랑 얘기하고 싶어. 해적처럼 인사해줘."}]},
        config,
    )
    print(turn1["messages"][-1].content)

    print("\n=== 턴 2: 이제 5 + 7 을 물어보면 Alice 로 handoff 된다 ===")
    turn2 = app.invoke(
        {"messages": [{"role": "user", "content": "좋아, 그런데 5 더하기 7은?"}]},
        config,
    )
    print(turn2["messages"][-1].content)


if __name__ == "__main__":
    main()
