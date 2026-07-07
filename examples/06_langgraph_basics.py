"""
06_langgraph_basics.py — LangGraph 상태 그래프 기초 (docs/04-langgraph-state-graph.md)

도구 1개를 가진 최소 ReAct 에이전트를 두 가지 방식으로 만든다.
    (A) create_react_agent 프리빌트 — 한 줄
    (B) StateGraph 로 직접 조립 — 노드/엣지/조건분기/리듀서를 눈으로 확인

핵심 개념:
    - State: TypedDict + Annotated[list, add_messages] (메시지 누적 리듀서)
    - Node: 상태를 받아 '바뀐 키만' dict 로 반환
    - Edge: add_edge(고정) / add_conditional_edges(분기)
    - tools -> agent 순환 = 에이전트 루프

사전 준비:
    pip install -r requirements.txt
    copy .env.example .env   # ANTHROPIC_API_KEY 채우기

실행:
    python examples/06_langgraph_basics.py
"""

from typing import Annotated, TypedDict

from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

load_dotenv()

# 비용 절감: "claude-haiku-4-5" 로 교체 가능 ("claude-sonnet-5" 도 가능)
MODEL = "claude-opus-4-8"


# --- 도구 정의 --------------------------------------------------------------
@tool
def get_weather(city: str) -> str:
    """주어진 도시의 현재 날씨를 반환한다."""
    return f"{city}: 맑음, 24도"


TOOLS = [get_weather]


# ==========================================================================
# (A) 프리빌트: create_react_agent — 위 루프를 한 줄로
# ==========================================================================
def demo_prebuilt():
    print("\n=== (A) create_react_agent 프리빌트 ===")
    model = ChatAnthropic(model=MODEL, max_tokens=1024)
    agent = create_react_agent(model=model, tools=TOOLS)

    result = agent.invoke({"messages": [("user", "서울 날씨 알려줘")]})
    print(result["messages"][-1].content)


# ==========================================================================
# (B) 직접 조립: StateGraph — 노드/엣지/조건분기를 손으로
# ==========================================================================
class State(TypedDict):
    # add_messages 리듀서: 반환된 메시지를 덮어쓰지 않고 이어붙인다(append)
    messages: Annotated[list, add_messages]


# 도구 이름 -> 함수 매핑 (도구 실행 노드에서 사용)
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
_model_with_tools = None


def call_model(state: State) -> dict:
    """agent 노드: 현재까지의 메시지로 모델을 호출한다."""
    global _model_with_tools
    if _model_with_tools is None:
        _model_with_tools = ChatAnthropic(model=MODEL, max_tokens=1024).bind_tools(TOOLS)
    ai = _model_with_tools.invoke(state["messages"])
    return {"messages": [ai]}  # 바뀐 키만 반환 → add_messages 가 누적 병합


def run_tools(state: State) -> dict:
    """tools 노드: 마지막 AI 메시지의 tool_calls 를 실제로 실행한다."""
    last = state["messages"][-1]
    results = []
    for call in last.tool_calls:
        output = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
        # 도구 결과는 ToolMessage 로 되돌려 넣는다 (tool_call_id 로 짝을 맞춤)
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
    return {"messages": results}


def should_continue(state: State) -> str:
    """라우팅: 마지막 AI 가 도구를 불렀으면 tools, 아니면 종료."""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def build_graph():
    builder = StateGraph(State)
    builder.add_node("agent", call_model)
    builder.add_node("tools", run_tools)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, ["tools", END])
    builder.add_edge("tools", "agent")  # 도구 결과를 다시 모델로 (순환 = 루프)
    return builder.compile()


def demo_manual():
    print("\n=== (B) StateGraph 직접 조립 ===")
    graph = build_graph()
    result = graph.invoke({"messages": [("user", "부산 날씨 알려줘")]})
    print(result["messages"][-1].content)


def main():
    demo_prebuilt()
    demo_manual()


if __name__ == "__main__":
    main()
