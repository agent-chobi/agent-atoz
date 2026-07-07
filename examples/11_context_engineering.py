"""
11_context_engineering.py — 긴 대화 컨텍스트를 트림/요약으로 압축

무엇을 보여주나
---------------
- 대화가 길어지면 컨텍스트 창이 넘치고 비용이 폭증한다.
- (A) trim_messages: 최근 N 토큰만 남겨 오래된 메시지를 잘라낸다.
- (B) 요약(summarization): 오래된 메시지를 LLM 으로 한 문단 요약해
      SystemMessage 로 접고, 최근 몇 턴만 원문으로 유지한다.
- 두 기법 모두 "무엇을 컨텍스트에 넣을까"를 관리하는 컨텍스트 엔지니어링의 기본기.

대응 문서: docs/08-context-engineering.md

실행법
------
  pip install -r requirements.txt          # langchain-core, langchain-anthropic
  copy .env.example .env                    # (요약 데모에만 ANTHROPIC_API_KEY 필요)
  python examples/11_context_engineering.py
"""

import os

from dotenv import load_dotenv
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    trim_messages,
)

load_dotenv()

# 비용 절감:  MODEL = "claude-haiku-4-5"
MODEL = "claude-opus-4-8"


def build_long_history() -> list:
    """40턴짜리 가짜 긴 대화를 만든다."""
    history: list = [SystemMessage(content="너는 친절한 여행 도우미다.")]
    topics = ["파리", "로마", "도쿄", "서울", "뉴욕"]
    for i in range(20):
        city = topics[i % len(topics)]
        history.append(HumanMessage(content=f"{city} 여행 팁 하나만 알려줘 (질문 {i + 1})"))
        history.append(AIMessage(content=f"{city}에서는 대중교통 패스를 사세요. (답변 {i + 1})"))
    return history


def demo_trim(history: list) -> None:
    """(A) trim_messages: 최근 토큰만 남기기."""
    print("=== (A) trim_messages — 최근 토큰만 보존 ===")
    print(f"원본 메시지 수: {len(history)}")

    # token_counter=len 은 '메시지 개수'로 근사 카운트(데모용).
    # 실제로는 token_counter=model 로 모델 토크나이저를 쓰는 게 정확하다.
    trimmed = trim_messages(
        history,
        strategy="last",        # 최근 것 우선 보존
        max_tokens=8,           # len 카운터 기준 = 최근 8개 메시지 근처
        token_counter=len,
        start_on="human",       # 대화가 HumanMessage 로 시작하도록 정리
        include_system=True,    # 시스템 프롬프트는 항상 유지
    )
    print(f"트림 후 메시지 수: {len(trimmed)}")
    print("남은 메시지 미리보기:")
    for m in trimmed:
        print(f"  - {type(m).__name__}: {m.content[:40]}")


def demo_summarize(history: list) -> None:
    """(B) 요약: 오래된 대화를 한 문단으로 접기 (LLM 필요)."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        print("\n=== (B) 요약 데모 건너뜀 (langchain-anthropic 미설치) ===")
        return
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n=== (B) 요약 데모 건너뜀 (ANTHROPIC_API_KEY 없음) ===")
        return

    print("\n=== (B) 요약 — 오래된 대화를 SystemMessage 로 압축 ===")
    model = ChatAnthropic(model=MODEL, temperature=0)

    keep_recent = 4                      # 최근 4개 메시지는 원문 유지
    old, recent = history[1:-keep_recent], history[-keep_recent:]

    # 오래된 대화를 요약
    to_summarize = "\n".join(f"{type(m).__name__}: {m.content}" for m in old)
    summary = model.invoke(
        [
            SystemMessage(content="다음 대화를 3문장 이내로 요약해라. 핵심 사실만."),
            HumanMessage(content=to_summarize),
        ]
    ).content

    # 새 컨텍스트 = 원래 시스템 + 요약 + 최근 원문
    compressed = [
        history[0],
        SystemMessage(content=f"[이전 대화 요약] {summary}"),
        *recent,
    ]
    print(f"원본 {len(history)}개 → 압축 후 {len(compressed)}개")
    print(f"요약 내용: {summary[:120]}...")


def main() -> None:
    history = build_long_history()
    demo_trim(history)
    demo_summarize(history)

    print("\n요점: 컨텍스트는 예산이다. 넘치면 (A)트림 또는 (B)요약으로 줄여라.")
    print("      멀티에이전트 핸드오프도 '전체'가 아니라 '요약'을 넘기는 게 정석 (docs/08).")


if __name__ == "__main__":
    main()
