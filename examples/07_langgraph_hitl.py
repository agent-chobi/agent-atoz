"""
07_langgraph_hitl.py — LangGraph HITL: interrupt / Command(resume) (docs/04-langgraph-state-graph.md)

위험한 행동(예: 송금) 앞에 '사람 승인 게이트'를 두는 Human-in-the-Loop 패턴.
    - 노드 안에서 interrupt(payload) -> 실행이 그 자리에서 멈추고 상태가 저장됨
    - 나중에 graph.invoke(Command(resume=값), config) 로 같은 지점부터 재개
    - ⚠️ interrupt 는 체크포인터가 있어야 동작하고, 재개 시 같은 thread_id 필요

이 예제는 사용자 입력 없이 자동 진행되도록, 승인 값을 코드에서 두 경우(yes/no)로 넣어
두 번 실행한다. 실제 앱에서는 resume 값을 사람의 UI 입력으로 받는다.

사전 준비:
    pip install -r requirements.txt

실행:
    python examples/07_langgraph_hitl.py

[기대 출력 예시] (LLM 미호출이라 아래와 거의 동일하게 출력되면 성공)
    === HITL 승인 게이트 데모 ===
    [tx-approve] 일시정지, 승인 요청: {'question': '이 송금을 승인하시겠습니까?', 'amount': 10000}
    [tx-approve] resume='yes' -> 10000원 송금 완료 ✅
    [tx-reject] 일시정지, 승인 요청: {'question': '이 송금을 승인하시겠습니까?', 'amount': 10000}
    [tx-reject] resume='no' -> 송금이 거부되었습니다 ❌
    ※ 승인(yes) 케이스는 ✅, 거부(no) 케이스는 ❌ 가 나와야 정상.

[흔한 에러]
    - ImportError: No module named 'langgraph' → pip install -r requirements.txt 재실행
    - KeyError: '__interrupt__': 체크포인터 없이 compile 함 → compile(checkpointer=...) 필수
    - 재개가 처음부터 다시 실행됨: resume 시 thread_id 가 다름 → 같은 config 로 invoke
"""

from typing import TypedDict

from dotenv import load_dotenv

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경 — 규칙상 명시(이 예제는 LLM 미호출, 20번과 동일 패턴)


class State(TypedDict):
    amount: int
    approved: bool
    result: str


def approval_node(state: State) -> dict:
    """승인 게이트: interrupt 로 실행을 멈추고 사람의 판단을 기다린다."""
    # interrupt 에 넘긴 payload 는 result["__interrupt__"] 로 호출자에게 노출된다.
    # 재개 시 Command(resume=값) 의 '값'이 여기 decision 으로 들어온다.
    decision = interrupt({"question": "이 송금을 승인하시겠습니까?", "amount": state["amount"]})
    return {"approved": decision == "yes"}


def execute_node(state: State) -> dict:
    """승인 여부에 따라 실제 행동을 수행(하는 척)한다."""
    if state["approved"]:
        return {"result": f"{state['amount']}원 송금 완료 ✅"}
    return {"result": "송금이 거부되었습니다 ❌"}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("approval", approval_node)
    builder.add_node("execute", execute_node)
    builder.add_edge(START, "approval")
    builder.add_edge("approval", "execute")
    builder.add_edge("execute", END)
    # ⚠️ interrupt 재개를 위해 체크포인터 필수 (상태를 저장해 둬야 복원 가능)
    return builder.compile(checkpointer=InMemorySaver())


def run_once(graph, thread_id: str, decision: str):
    """한 트랜잭션을 처음부터 실행하고, interrupt 에서 멈춘 뒤 decision 으로 재개한다."""
    config = {"configurable": {"thread_id": thread_id}}  # 스레드 단위 상태 격리

    # 1) 실행 -> approval 노드의 interrupt 에서 멈춘다
    state = graph.invoke({"amount": 10000, "approved": False, "result": ""}, config=config)
    print(f"[{thread_id}] 일시정지, 승인 요청: {state['__interrupt__'][0].value}")

    # 2) 사람 판단을 받아 재개 (같은 thread_id 로!)
    final = graph.invoke(Command(resume=decision), config=config)
    print(f"[{thread_id}] resume='{decision}' -> {final['result']}")


def main():
    graph = build_graph()
    print("=== HITL 승인 게이트 데모 ===")
    run_once(graph, thread_id="tx-approve", decision="yes")  # 승인 케이스
    run_once(graph, thread_id="tx-reject", decision="no")    # 거부 케이스


if __name__ == "__main__":
    main()
