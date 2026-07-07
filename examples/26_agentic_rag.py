"""
26_agentic_rag.py — Agentic RAG: retriever 를 도구로 쥔 에이전트 (docs/21-rag-agentic-rag.md)

무엇을 보여주나
---------------
1) 인덱싱: 가상의 사내 규정 문서 4개를 임베딩해 Chroma(인메모리)에 저장
2) retriever 를 @tool 로 감싸 LangGraph ReAct 에이전트에게 제공
3) 에이전트가 스스로 결정:
   - 검색이 필요한 질문 → 쿼리를 재작성해 (필요하면 여러 번) search_docs 호출
   - 검색이 불필요한 질문 → 도구 호출 없이 바로 답변
   이것이 "항상 1회 검색"하는 단순 RAG 와의 차이다.

주의: 생성은 Claude, 임베딩은 OpenAI — Anthropic 은 임베딩 API 를 제공하지 않는다
(공식 권장은 Voyage AI, 이 예제는 진입장벽이 낮은 OpenAI 임베딩 사용).

[실행법]
  pip install -r requirements.txt   # chromadb, langchain-chroma, langchain-openai 포함
  # .env 에 두 키 모두 설정:
  #   ANTHROPIC_API_KEY=sk-ant-...   (생성용)
  #   OPENAI_API_KEY=sk-...          (임베딩용)
  python examples/26_agentic_rag.py

[기대 출력 예시]
  === 1) 인덱싱: 문서 4개 → Chroma ===
  색인 완료: 4개 청크

  === 2) 질문: 재택근무는 주 며칠까지 가능하고, 노트북 반출 규정은? ===
    [도구 호출] search_docs(query='재택근무 주당 가능 일수')
    [도구 호출] search_docs(query='노트북 사외 반출 보안 규정')
  [에이전트 답변]
  재택근무는 주 3일까지 가능하며 팀장 사전 승인이 필요합니다. ...

  === 3) 질문: 고마워! (검색 불필요) ===
    (도구 호출 없음)
  [에이전트 답변]
  천만에요! ...

[흔한 에러]
  - "OPENAI_API_KEY 가 없습니다" 안내 후 종료 → 임베딩용 키 미설정 (의도된 정상 종료)
  - AuthenticationError 401 → 키 오타/만료. 두 키 모두 확인
  - chromadb 의 sqlite3 버전 에러 → Python 3.11+ 사용 (sqlite3 >= 3.35 필요)
  - 검색 결과가 엉뚱함 → 인덱싱/검색의 임베딩 모델이 다르면 안 됨 (같은 모델 유지)
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

# 기본은 가장 강력한 Opus. 비용을 아끼려면 아래 한 줄로 교체:
# MODEL = "claude-haiku-4-5"   # 빠르고 저렴
MODEL = "claude-opus-4-8"

EMBED_MODEL = "text-embedding-3-small"  # 인덱싱과 검색에 반드시 같은 모델 사용


# ── 1. 지식 코퍼스 (실전에서는 DocumentLoader 로 PDF/위키에서 로드) ─────────
DOCS = [
    "[근무 규정] 재택근무는 주 3일까지 가능하다. 재택근무를 하려면 전주 금요일까지 "
    "팀장의 사전 승인을 받아야 하며, 코어타임(10시~16시)에는 메신저 응답이 가능해야 한다.",
    "[보안 규정] 회사 노트북을 사외로 반출할 때는 디스크 암호화(BitLocker/FileVault)가 "
    "활성화되어 있어야 하고, 반출 신청서를 보안팀에 제출해 승인받아야 한다. "
    "공용 와이파이 사용 시 사내 VPN 접속이 의무다.",
    "[휴가 규정] 연차는 입사일 기준으로 매년 15일이 부여되며, 3년 근속마다 1일씩 "
    "가산된다(최대 25일). 반차는 0.5일로 차감하고, 당일 연차는 오전 9시 이전에 "
    "팀장에게 통보해야 한다.",
    "[장비 규정] 개발 장비는 3년 주기로 교체 신청할 수 있다. 모니터는 1인당 최대 2대까지 "
    "지원하며, 추가 장비는 부서 예산으로 구매 후 자산 등록해야 한다.",
]


def build_retriever_tool():
    """문서를 Chroma 에 인덱싱하고, retriever 를 감싼 도구를 만들어 반환한다."""
    # 무거운 의존성은 함수 안에서 import (키 가드 이후에만 로드되도록)
    from langchain_chroma import Chroma
    from langchain_core.tools import tool
    from langchain_openai import OpenAIEmbeddings

    print("=== 1) 인덱싱: 문서 4개 → Chroma ===")
    vectorstore = Chroma.from_texts(
        texts=DOCS,
        embedding=OpenAIEmbeddings(model=EMBED_MODEL),
        collection_name="company-policies",
        # persist_directory 를 주지 않으면 인메모리 → 스크립트 종료와 함께 소멸
    )
    print(f"색인 완료: {len(DOCS)}개 청크\n")

    retriever = vectorstore.as_retriever(search_kwargs={"k": 2})  # top-2 검색

    @tool
    def search_docs(query: str) -> str:
        """사내 규정 문서에서 관련 내용을 검색한다. 검색어는 짧은 키워드 문장으로 쓸 것."""
        print(f"  [도구 호출] search_docs(query={query!r})")
        docs = retriever.invoke(query)
        return "\n\n".join(d.page_content for d in docs)

    return search_docs


def ask(agent, question: str) -> None:
    """질문 하나를 에이전트에 보내고, 도구 사용 여부와 최종 답변을 출력한다."""
    result = agent.invoke({"messages": [("user", question)]})

    # 도구를 한 번도 안 불렀다면 명시적으로 표시 (Agentic RAG 의 핵심 관찰 포인트)
    tool_used = any(getattr(m, "tool_calls", None) for m in result["messages"])
    if not tool_used:
        print("  (도구 호출 없음)")

    print("[에이전트 답변]")
    print(result["messages"][-1].content)


def main() -> None:
    # ── API 키 가드: 클라이언트/임베딩 생성보다 먼저 ──────────────────────
    if not os.getenv("OPENAI_API_KEY"):
        # 임베딩 키가 없으면 에러가 아니라 안내 후 "정상 종료"
        print("OPENAI_API_KEY 가 없습니다 — 이 예제는 임베딩에 OpenAI 를 씁니다.")
        print("(Anthropic 은 임베딩 API 미제공. 공식 권장은 Voyage AI, 학습용으로 OpenAI 사용)")
        print(".env 에 OPENAI_API_KEY=sk-... 를 추가한 뒤 다시 실행하세요.")
        return
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 를 확인하세요.")

    from langchain_anthropic import ChatAnthropic
    from langgraph.prebuilt import create_react_agent

    search_docs = build_retriever_tool()

    model = ChatAnthropic(model=MODEL)
    agent = create_react_agent(
        model,
        tools=[search_docs],
        prompt=(
            "너는 사내 규정 안내 도우미다.\n"
            "- 규정 근거가 필요한 질문이면 search_docs 로 검색하라. 질문을 그대로 넣지 말고 "
            "검색에 맞는 키워드로 재작성하고, 서로 다른 주제는 나눠서 여러 번 검색하라.\n"
            "- 검색 결과가 부족하면 검색어를 바꿔 다시 검색하라 (self-correction).\n"
            "- 검색된 문서에 없는 내용은 지어내지 말고 '규정에 없음'이라고 답하라.\n"
            "- 인사말 등 규정과 무관한 말에는 검색 없이 바로 답하라."
        ),
    )

    # 검색이 "필요한" 질문 — 두 규정에 걸쳐 있어 여러 번 검색해야 한다
    q1 = "재택근무는 주 며칠까지 가능하고, 노트북 반출 규정은?"
    print(f"=== 2) 질문: {q1} ===")
    ask(agent, q1)

    # 검색이 "불필요한" 질문 — 단순 RAG 라면 여기서도 검색을 돌렸을 것
    q2 = "고마워!"
    print(f"\n=== 3) 질문: {q2} (검색 불필요) ===")
    ask(agent, q2)


if __name__ == "__main__":
    main()
