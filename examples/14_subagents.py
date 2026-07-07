"""
14_subagents.py — 서브에이전트 위임 (LangChain Deep Agents)

Deep Agents(deepagents) 는 create_agent 위에 planning(write_todos), 가상 파일시스템,
서브에이전트, skills 를 기본 탑재한 "배터리 포함" 하네스입니다.

핵심 아이디어 — **컨텍스트 격리(context quarantine)**:
메인 에이전트가 무거운 작업(웹검색·긴 파일 읽기)을 서브에이전트에게 위임하면,
서브에이전트의 수십 번의 중간 도구 호출은 격리되고 메인 에이전트는 **최종 결과만** 돌려받습니다.
덕분에 메인 컨텍스트가 깨끗하게 유지됩니다.

서브에이전트 딕셔너리 형식:
    {
        "name": "고유 이름 (메인이 task() 도구로 호출할 때 쓰는 식별자)",
        "description": "무슨 일을 하는지 (구체적·행동 지향적으로)",
        "system_prompt": "이 서브에이전트의 지침",
        "tools": [...],        # 선택
        "model": "...",        # 선택 — 메인 모델을 오버라이드
    }

실행:
    pip install -U deepagents langchain-anthropic
    python examples/14_subagents.py

참고: deepagents 는 2026년 빠르게 진화 중입니다. subagent 키가 system_prompt 인지
      prompt 인지 등 시그니처가 바뀔 수 있으니 설치 버전 대조가 필요합니다.

[기대 출력 예시] (출력은 실행마다 다르며 대략 이런 형태 — 위임 흐름이 성공 판단 기준)
    === 최종 답변 ===
    Deep Agents 는 무거운 조사 작업을 서브에이전트에 위임해 컨텍스트를 격리한다. ...

    === 가상 파일시스템 ===
    --- todos.md ---            (write_todos 로 남긴 계획이 있으면 함께 출력)
    1. research-agent 에 조사 위임
    2. 반환 노트로 요약 작성
    ※ 내부적으로 메인 에이전트가 write_todos → task(research-agent) → 요약 순으로
      진행하고, 서브에이전트의 중간 도구 호출은 최종 답변에 노출되지 않으면 성공.

[흔한 에러]
    - ImportError: No module named 'deepagents' → pip install -r requirements.txt 재실행
    - SystemExit "ANTHROPIC_API_KEY 가 없습니다" → .env 파일 확인
    - TypeError(system_prompt/prompt 키 등): deepagents 버전 시그니처 변경 → 설치 버전 문서 대조
"""

import os

from dotenv import load_dotenv
from deepagents import create_deep_agent

load_dotenv()

# 예외: deepagents 는 "provider:model" 형식 문자열을 받는다 —
# 다른 예제의 "claude-haiku-4-5" 대신 "anthropic:claude-haiku-4-5" 형식.
MODEL = "anthropic:claude-opus-4-8"  # 비용 절감: "anthropic:claude-haiku-4-5" 로 변경


# --- 서브에이전트가 사용할 도구 (데모용 가짜 검색) ----------------------------
def internet_search(query: str) -> str:
    """인터넷을 검색한다(데모용 고정 응답)."""
    return (
        "검색 결과:\n"
        "- Deep Agents 는 planning(write_todos), 가상 FS, 서브에이전트, skills 를 기본 제공한다.\n"
        "- 서브에이전트는 긴 중간 결과를 격리해 메인 컨텍스트 오염을 막는다.\n"
        "- Anthropic 은 장기실행 에이전트에 '진행상황 파일 + 구조화된 핸드오프'를 권장한다."
    )


# --- 커스텀 리서치 서브에이전트 정의 -----------------------------------------
research_subagent = {
    "name": "research-agent",
    "description": "심층 조사가 필요한 질문에 사용한다. 사실을 모아 요약해 돌려준다.",
    "system_prompt": (
        "너는 뛰어난 리서처다. internet_search 로 근거를 모으고,\n"
        "핵심만 불릿으로 정리해 반환하라. 중간 과정은 남기지 말고 결론만 넘겨라."
    ),
    "tools": [internet_search],
}


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    # 에이전트 생성은 API 키 가드 '뒤'에서 수행한다.
    # --- 메인(오케스트레이터) Deep Agent -------------------------------------
    # subagents 를 넘기지 않아도 general-purpose 서브에이전트가 자동 추가됩니다.
    agent = create_deep_agent(
        model=MODEL,
        tools=[internet_search],
        system_prompt=(
            "너는 리서치 오케스트레이터다.\n"
            "1) 먼저 write_todos 로 작업 계획을 세워라.\n"
            "2) 조사가 필요하면 research-agent 서브에이전트에게 위임하라(task 도구).\n"
            "3) 반환된 노트를 바탕으로 한국어 요약 단락을 작성하라."
        ),
        subagents=[research_subagent],
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Deep Agents 가 왜 서브에이전트로 컨텍스트를 격리하는지 조사해서 한 단락으로 정리해줘.",
                }
            ]
        }
    )

    print("\n=== 최종 답변 ===")
    print(result["messages"][-1].content)

    # 가상 파일시스템에 남은 계획/산출물이 있으면 함께 출력
    files = result.get("files")
    if files:
        print("\n=== 가상 파일시스템 ===")
        for path, content in files.items():
            print(f"--- {path} ---")
            print(content[:300])


if __name__ == "__main__":
    main()
