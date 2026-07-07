"""
10_long_term_memory.py — 장기 메모리(스토어)로 cross-thread 회상

무엇을 보여주나
---------------
- LangGraph `InMemoryStore` 는 thread 를 가로지르는(cross-thread) key-value 저장소다.
- namespace=(user_id, "memories") 로 사용자 선호를 put() 하고,
  전혀 다른 thread 에서 get()/search() 로 회상한다.
- (선택) langmem 이 설치돼 있으면, 에이전트가 스스로 저장/검색 도구를 호출하는
  방식도 함께 보여준다.

핵심: 단기 메모리(체크포인터, 예제 09)는 "이 대화"만 기억하지만,
장기 메모리(스토어)는 "이 사용자"를 여러 대화에 걸쳐 기억한다.

대응 문서: docs/07-long-term-memory.md

실행법
------
  pip install -r requirements.txt          # langgraph (langmem 은 선택)
  copy .env.example .env                    # (langmem 데모에만 ANTHROPIC_API_KEY 필요)
  python examples/10_long_term_memory.py

[기대 출력 예시] (1)은 결정적, (2)의 문구는 실행마다 다름)
  === 1) 순수 스토어: put → 다른 thread 에서 get/search ===
  저장 완료: 식성, 언어 선호

  get('diet') → 채식주의자, 견과류 알레르기

  search(namespace) 전체 기억:
    - [diet] 채식주의자, 견과류 알레르기
    - [lang] 한국어로 존댓말 선호

  === 2) langmem: 에이전트가 스스로 기억 저장/검색 ===
  [에이전트] 파이썬을 좋아하고 자바는 싫어한다고 하셨어요.

[흔한 에러]
  - ImportError: No module named 'langgraph' → pip install -r requirements.txt 재실행
  - "(2) langmem 데모 건너뜀" 출력: langmem 미설치 또는 키 없음 — 오류 아님(선택 데모)
  - authentication_error (401): ANTHROPIC_API_KEY 값이 잘못됨 → .env 파일 확인
"""

import os

from dotenv import load_dotenv
from langgraph.store.memory import InMemoryStore

load_dotenv()

# langmem 데모(선택)에서만 사용.
MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경

USER_ID = "alex"


def demo_pure_store() -> None:
    """순수 InMemoryStore 만으로 cross-thread 회상 시연 (LLM/외부 의존성 불필요)."""
    print("=== 1) 순수 스토어: put → 다른 thread 에서 get/search ===")

    store = InMemoryStore()
    namespace = (USER_ID, "memories")  # (사용자, 카테고리) 튜플

    # [thread-1 상황] 사용자가 선호를 알려줌 → 장기 스토어에 저장
    store.put(namespace, "diet", {"fact": "채식주의자, 견과류 알레르기"})
    store.put(namespace, "lang", {"fact": "한국어로 존댓말 선호"})
    print("저장 완료: 식성, 언어 선호")

    # [thread-2 상황: 완전히 다른 대화] 그래도 회상 가능
    item = store.get(namespace, "diet")
    print(f"\nget('diet') → {item.value['fact']}")

    # search: 네임스페이스 안에서 검색(임베딩 인덱스를 붙이면 의미검색, 여기선 전체 나열)
    print("\nsearch(namespace) 전체 기억:")
    for hit in store.search(namespace):
        print(f"  - [{hit.key}] {hit.value['fact']}")


def demo_langmem_agent() -> None:
    """langmem 이 있으면: 에이전트가 스스로 기억을 저장/검색하는 도구를 호출."""
    try:
        from langchain_anthropic import ChatAnthropic
        from langgraph.prebuilt import create_react_agent
        from langmem import create_manage_memory_tool, create_search_memory_tool
    except ImportError:
        print("\n=== 2) langmem 데모 건너뜀 (langmem/langchain-anthropic 미설치) ===")
        return
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n=== 2) langmem 데모 건너뜀 (ANTHROPIC_API_KEY 없음) ===")
        return

    print("\n=== 2) langmem: 에이전트가 스스로 기억 저장/검색 ===")
    store = InMemoryStore()
    # 최신 Opus는 temperature 미지원(400) — 결정성이 필요하면 프롬프트로 제어
    model = ChatAnthropic(model=MODEL)

    tools = [
        # {user_id} 동적 네임스페이스 → 사용자별로 기억이 격리된다
        create_manage_memory_tool(namespace=("memories", "{user_id}")),
        create_search_memory_tool(namespace=("memories", "{user_id}")),
    ]
    agent = create_react_agent(model, tools=tools, store=store)

    cfg = {"configurable": {"user_id": USER_ID}}

    # thread-1: 선호를 학습시킴
    agent.invoke(
        {"messages": [("user", "기억해줘: 나는 파이썬을 좋아하고 자바는 싫어해.")]},
        {"configurable": {"thread_id": "t1", "user_id": USER_ID}},
    )
    # thread-2: 다른 대화지만 같은 user_id → 회상
    result = agent.invoke(
        {"messages": [("user", "내가 어떤 프로그래밍 언어를 좋아한다고 했지?")]},
        {"configurable": {"thread_id": "t2", "user_id": USER_ID}},
    )
    print(f"[에이전트] {result['messages'][-1].content}")


def main() -> None:
    demo_pure_store()
    demo_langmem_agent()

    print("\n참고: mem0 를 쓴다면 대략 아래 형태 (docs/07 참고)")
    print("  from mem0 import Memory")
    print("  m = Memory(); m.add(messages, user_id='alex')")
    print("  m.search('식성이 어떻게 되지?', user_id='alex')")


if __name__ == "__main__":
    main()
