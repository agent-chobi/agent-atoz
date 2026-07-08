"""
25. LangGraph 심화 — 서브그래프 2방식 + 스트리밍 모드(updates/custom/messages).

무엇을 가르치나:
  - 서브그래프 방식 A(상태 공유): 부모와 키를 공유하면 컴파일된 그래프를
    그대로 부모의 노드로 추가할 수 있다
  - 서브그래프 방식 B(상태 변환): 스키마가 다르면 노드 함수 안에서
    변환 → invoke → 역변환 한다
  - 스트리밍: 한 번의 실행에서 updates(노드별 갱신) + custom(진행 상황)
    + messages(LLM 토큰) 세 모드를 동시에 받고, subgraphs=True 로
    서브그래프 내부 이벤트까지 네임스페이스와 함께 관찰한다

실행법:
  pip install langgraph langchain-anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/25_langgraph_advanced.py

[기대 출력 예시]
  === 서브그래프 + 멀티모드 스트리밍 ===
  [custom  |research_team] 'LangGraph 서브그래프' 자료 수집 중...
  [updates |research_team] gather → ['notes']
  [updates |research_team] summarize → ['research']
  [updates |(root)] research_team → ['research']
  [messages|write_report] LangGraph의 서브그래프는 ... (토큰 단위 출력)
  [updates |(root)] write_report → ['report']
  [updates |(root)] polish → ['report']

  === 최종 상태 ===
  research: [요약] LangGraph 서브그래프 관련 메모 3건 → 핵심 2가지 정리
  report  : (다듬어진 보고서 텍스트)

[흔한 에러]
  - AuthenticationError: .env 의 ANTHROPIC_API_KEY 누락/오타
  - 서브그래프 내부 이벤트가 안 보임 → stream() 에 subgraphs=True 를 빠뜨림
  - custom 청크가 안 나옴 → stream_mode 에 "custom" 을 포함했는지 확인
    (get_stream_writer 는 custom 모드로 스트리밍할 때만 소비자에게 전달됨)
  - InvalidUpdateError: 부모/서브그래프가 공유하는 키에 리듀서 없이
    같은 스텝에서 동시 기록하면 발생 — 키 소유권을 명확히 나눌 것
"""

import os
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

# Windows 콘솔에서 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

MODEL = "claude-haiku-4-5"  # 고성능 필요 시: "claude-opus-4-8" 로 변경


# ---------------------------------------------------------------------------
# 부모 그래프 상태
# ---------------------------------------------------------------------------
class ParentState(TypedDict):
    topic: str      # 입력 주제
    research: str   # 서브그래프 A 와 '공유'하는 키
    report: str     # LLM 이 쓰는 보고서


# ---------------------------------------------------------------------------
# 서브그래프 A — 상태 공유 방식: topic/research 를 부모와 공유
# ---------------------------------------------------------------------------
class ResearchState(TypedDict):
    topic: str      # 부모와 공유
    research: str   # 부모와 공유 — 이 키의 갱신만 부모에 반영된다
    notes: str      # 서브그래프 내부 전용 키 (부모에게는 보이지 않음)


def gather(state: ResearchState) -> dict:
    # custom 스트리밍: 임의의 진행 상황을 소비자에게 흘려보낸다
    writer = get_stream_writer()
    writer(f"'{state['topic']}' 자료 수집 중...")
    return {"notes": f"{state['topic']} 관련 메모 3건"}


def summarize(state: ResearchState) -> dict:
    return {"research": f"[요약] {state['notes']} → 핵심 2가지 정리"}


research_builder = StateGraph(ResearchState)
research_builder.add_node("gather", gather)
research_builder.add_node("summarize", summarize)
research_builder.add_edge(START, "gather")
research_builder.add_edge("gather", "summarize")
research_builder.add_edge("summarize", END)
research_graph = research_builder.compile()


# ---------------------------------------------------------------------------
# 서브그래프 B — 상태 변환 방식: 부모와 스키마가 완전히 다름
# ---------------------------------------------------------------------------
class PolishState(TypedDict):
    text: str
    polished: str


def do_polish(state: PolishState) -> dict:
    # 실무라면 LLM 호출 — 여기서는 규칙 기반으로 단순화
    return {"polished": state["text"].strip().replace("  ", " ")}


polish_builder = StateGraph(PolishState)
polish_builder.add_node("do_polish", do_polish)
polish_builder.add_edge(START, "do_polish")
polish_builder.add_edge("do_polish", END)
polish_graph = polish_builder.compile()


def call_polish(state: ParentState) -> dict:
    # 방식 B 의 핵심: 부모 상태 → 서브그래프 입력 변환, 결과 → 부모 키로 역변환
    result = polish_graph.invoke({"text": state["report"]})
    return {"report": result["polished"]}


# ---------------------------------------------------------------------------
# LLM 노드 — messages 모드 스트리밍의 토큰 공급원
# ---------------------------------------------------------------------------
def write_report(state: ParentState) -> dict:
    from langchain_anthropic import ChatAnthropic  # API 키 가드 이후에만 임포트 사용

    llm = ChatAnthropic(model=MODEL, max_tokens=512)
    msg = llm.invoke(
        f"다음 조사 요약을 바탕으로 두 문장짜리 보고서를 써라:\n{state['research']}"
    )
    return {"report": _text_of(msg)}


def _text_of(msg) -> str:
    """AIMessage(Chunk) 의 content 가 문자열/블록 리스트 어느 쪽이든 텍스트만 추출."""
    content = msg.content
    if isinstance(content, str):
        return content
    return "".join(
        p.get("text", "") for p in content
        if isinstance(p, dict) and p.get("type") == "text"
    )


# ---------------------------------------------------------------------------
# 부모 그래프 조립
# ---------------------------------------------------------------------------
builder = StateGraph(ParentState)
builder.add_node("research_team", research_graph)  # 방식 A: 컴파일된 그래프를 그대로 노드로
builder.add_node("write_report", write_report)
builder.add_node("polish", call_polish)            # 방식 B: 변환 래퍼 노드
builder.add_edge(START, "research_team")
builder.add_edge("research_team", "write_report")
builder.add_edge("write_report", "polish")
builder.add_edge("polish", END)
graph = builder.compile()


def main() -> None:
    # API 키 가드는 클라이언트(LLM) 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("오류: ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")

    print("=== 서브그래프 + 멀티모드 스트리밍 ===")
    final_report = ""

    # 멀티모드 + subgraphs=True → 청크는 (네임스페이스, 모드, 데이터) 3-튜플
    for namespace, mode, chunk in graph.stream(
        {"topic": "LangGraph 서브그래프", "research": "", "report": ""},
        stream_mode=["updates", "custom", "messages"],
        subgraphs=True,
    ):
        ns = namespace[0].split(":")[0] if namespace else "(root)"

        if mode == "updates":
            # 노드별 상태 '갱신분'만 — {노드이름: 갱신 dict}
            for node, update in chunk.items():
                keys = list(update.keys()) if isinstance(update, dict) else update
                print(f"[updates |{ns}] {node} → {keys}")
                if isinstance(update, dict) and "report" in update:
                    final_report = update["report"]
        elif mode == "custom":
            # 노드 안에서 get_stream_writer() 로 흘려보낸 임의 데이터
            print(f"[custom  |{ns}] {chunk}")
        elif mode == "messages":
            # (LLM 토큰 청크, 메타데이터) — UI 라면 여기서 실시간 렌더링
            token, meta = chunk
            text = _text_of(token)
            if text:
                print(text, end="", flush=True)
    print()

    print("\n=== 최종 상태 ===")
    print(f"report  : {final_report}")


if __name__ == "__main__":
    main()
