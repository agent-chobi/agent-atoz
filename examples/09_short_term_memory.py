"""
09_short_term_memory.py — 단기 메모리(체크포인터)로 멀티턴 기억 유지

무엇을 보여주나
---------------
- LangGraph `create_react_agent` + `SqliteSaver`(체크포인터)를 붙이면
  같은 thread_id 안에서 이전 대화를 자동으로 기억한다.
- get_state()로 현재 스냅샷을, get_state_history()로 과거 체크포인트를(타임트래블) 조회한다.
- thread_id를 바꾸면 완전히 다른 대화가 되어 아무것도 기억하지 못한다.

대응 문서: docs/06-short-term-memory.md

실행법
------
  pip install -r requirements.txt          # langgraph, langgraph-checkpoint-sqlite, langchain-anthropic
  copy .env.example .env                    # ANTHROPIC_API_KEY 채우기
  python examples/09_short_term_memory.py

  # 실행 후 생성되는 checkpoints.sqlite 를 지우면 기억이 초기화된다.

[기대 출력 예시] (모델 문구는 실행마다 다르며 대략 이런 형태)
  === 같은 thread 에서 멀티턴 ===
  [사용자] 내 이름이 뭐라고 했지?
  [에이전트] 밥이라고 하셨어요.
  [사용자] 내가 좋아하는 색은?
  [에이전트] 파랑을 좋아하신다고 하셨죠.

  === 다른 thread (기억 없음) ===
  [에이전트] 죄송하지만 이전 대화 기록이 없어 이름을 알 수 없어요.

[흔한 에러]
  - ImportError: No module named 'langgraph.checkpoint.sqlite' → pip install -r requirements.txt
    (langgraph-checkpoint-sqlite 패키지 필요)
  - SystemExit "ANTHROPIC_API_KEY 가 설정되지 않았습니다" → .env 파일 확인
  - 이전 실행의 기억이 섞임: checkpoints.sqlite 가 남아 있음 → 파일 삭제 후 재실행
"""

import os

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent

load_dotenv()

MODEL = "claude-haiku-4-5"  # 고성능 필요 시: "claude-opus-4-8" 로 변경


@tool
def get_time() -> str:
    """현재 시각을 문자열로 반환한다(데모용 간단 도구)."""
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")


def last_ai_text(result: dict) -> str:
    """에이전트 응답에서 마지막 AI 메시지 텍스트를 뽑는다."""
    return result["messages"][-1].content


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 를 확인하세요.")

    # 최신 Opus는 temperature 미지원(400) — 결정성이 필요하면 프롬프트로 제어
    model = ChatAnthropic(model=MODEL)

    # SqliteSaver 는 컨텍스트 매니저로 열어 파일 커넥션을 관리한다.
    # ":memory:" 를 주면 프로세스 메모리에만(InMemorySaver 유사) 저장된다.
    with SqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
        agent = create_react_agent(model, tools=[get_time], checkpointer=checkpointer)

        # thread_id 가 "이 대화"의 열쇠. 같은 값이면 상태가 이어진다.
        config = {"configurable": {"thread_id": "demo-user-1"}}

        print("=== 같은 thread 에서 멀티턴 ===")
        turns = [
            "안녕! 내 이름은 밥이고, 좋아하는 색은 파랑이야.",
            "내 이름이 뭐라고 했지?",
            "내가 좋아하는 색은?",
        ]
        for user_msg in turns:
            result = agent.invoke({"messages": [("user", user_msg)]}, config)
            print(f"\n[사용자] {user_msg}")
            print(f"[에이전트] {last_ai_text(result)}")

        # --- 현재 상태 스냅샷 ---
        print("\n=== get_state (현재 스냅샷) ===")
        snap = agent.get_state(config)
        print(f"메시지 개수: {len(snap.values['messages'])}")
        print(f"다음 실행 노드(비었으면 완료): {snap.next}")

        # --- 타임트래블: 과거 체크포인트 순회(최신 → 과거) ---
        print("\n=== get_state_history (타임트래블) ===")
        for i, past in enumerate(agent.get_state_history(config)):
            ckpt_id = past.config["configurable"]["checkpoint_id"]
            n_msgs = len(past.values.get("messages", []))
            print(f"  #{i:02d} checkpoint={ckpt_id[:12]}... msgs={n_msgs} next={past.next}")

        # --- 다른 thread_id 는 기억이 전혀 없다 ---
        print("\n=== 다른 thread (기억 없음) ===")
        other = {"configurable": {"thread_id": "demo-user-2"}}
        result = agent.invoke({"messages": [("user", "내 이름이 뭐였지?")]}, other)
        print(f"[에이전트] {last_ai_text(result)}")


if __name__ == "__main__":
    main()
