"""
05_langchain_lcel.py — LangChain LCEL 기초 (docs/03-langchain-basics.md)

LCEL(LangChain Expression Language)로 프롬프트·모델·파서를 파이프(|)로 잇고,
.invoke / .stream / .bind_tools 세 가지 사용법을 한 파일에서 시연한다.

핵심:
    chain = prompt | model | parser   ← 세 Runnable을 파이프로 연결
    - .invoke : 단건 실행
    - .stream : 토큰 스트리밍 (체인은 그대로, 호출만 변경)
    - .bind_tools : 모델에 도구를 묶어 tool_calls를 얻음

사전 준비:
    pip install -r requirements.txt
    copy .env.example .env   # 그리고 ANTHROPIC_API_KEY 채우기

실행:
    python examples/05_langchain_lcel.py

[기대 출력 예시] (모델 출력은 실행마다 다르며 대략 이런 형태)
    === 1) .invoke — 단건 실행 ===
    합의는 노드 장애·메시지 지연이 겹치면 ... (세 문장 이내 답변)

    === 2) .stream — 토큰 스트리밍 ===
    TCP 3-way handshake는 SYN → SYN-ACK → ACK ... (토큰 단위 출력)

    === 3) .bind_tools — 도구 바인딩 ===
    모델이 호출한 도구: get_weather({'city': '서울'})
    도구 실행 결과: 서울: 맑음, 24도

[흔한 에러]
    - ImportError: No module named 'langchain_anthropic' → pip install -r requirements.txt 재실행
    - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 파일 확인
    - 3)에서 "도구 호출 없이 응답": 모델이 도구가 불필요하다고 판단한 경우 — 오류 아님
"""

from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

load_dotenv()  # .env 에서 ANTHROPIC_API_KEY 로드

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경


def build_chain():
    """prompt | model | parser 로 이어지는 기본 LCEL 체인을 만든다."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "너는 {topic} 전문가다. 한국어로 세 문장 이내로 답하라."),
            ("human", "{question}"),
        ]
    )
    model = ChatAnthropic(model=MODEL, max_tokens=1024)
    parser = StrOutputParser()  # AIMessage → 순수 문자열(.content) 추출

    # LCEL 파이프: 왼쪽 출력이 오른쪽 입력으로 흐른다
    return prompt | model | parser


def demo_invoke(chain):
    """단건 동기 실행."""
    print("\n=== 1) .invoke — 단건 실행 ===")
    answer = chain.invoke({"topic": "분산 시스템", "question": "왜 합의(consensus)가 어려운가?"})
    print(answer)  # parser 덕분에 이미 str


def demo_stream(chain):
    """같은 체인을 호출만 바꿔 토큰 스트리밍한다."""
    print("\n=== 2) .stream — 토큰 스트리밍 ===")
    for chunk in chain.stream({"topic": "네트워킹", "question": "TCP 3-way handshake를 설명해줘."}):
        print(chunk, end="", flush=True)  # chunk 는 str 조각
    print()


@tool
def get_weather(city: str) -> str:
    """주어진 도시의 현재 날씨를 반환한다."""
    # 실제로는 외부 API 호출. 여기서는 데모용 고정값.
    return f"{city}: 맑음, 24도"


def demo_bind_tools():
    """.bind_tools 로 도구를 묶고, 모델이 만든 tool_calls(표준 형태)를 읽는다."""
    print("\n=== 3) .bind_tools — 도구 바인딩 ===")
    model_with_tools = ChatAnthropic(model=MODEL, max_tokens=1024).bind_tools([get_weather])
    ai = model_with_tools.invoke("서울 날씨 알려줘")

    if ai.tool_calls:
        for call in ai.tool_calls:
            print(f"모델이 호출한 도구: {call['name']}({call['args']})")
            # 실제 실행 후 결과를 되돌려 넣는 '루프'는 06_langgraph_basics.py 참고
            result = get_weather.invoke(call["args"])
            print(f"도구 실행 결과: {result}")
    else:
        # 모델이 도구 없이 바로 답한 경우
        print(f"도구 호출 없이 응답: {ai.content}")


def main():
    chain = build_chain()
    demo_invoke(chain)
    demo_stream(chain)
    demo_bind_tools()


if __name__ == "__main__":
    main()
