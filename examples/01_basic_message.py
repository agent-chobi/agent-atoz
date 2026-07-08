"""
01. 기본 메시지 호출 — Messages API의 최소 단위.

무엇을 가르치나:
  - client.messages.create() 로 1회 호출
  - response.content 가 '블록 리스트'임을 이해하고 타입별로 순회 출력
  - stop_reason, usage(토큰 사용량) 확인

실행법:
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/01_basic_message.py

[기대 출력 예시] (모델 출력은 실행마다 다르며 대략 이런 형태)
  === 응답 블록 순회 ===
  리스트 컴프리헨션은 반복문과 조건을 한 줄로 압축해 새 리스트를 만드는 문법입니다.

  === 메타 ===
  stop_reason: end_turn
  입력 토큰: 58
  출력 토큰: 47

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정/오타 → .env 파일 확인
  - ModuleNotFoundError: No module named 'anthropic' → pip install anthropic python-dotenv
  - rate_limit_error (429): 요청 과다 → 잠시 후 재시도 (SDK가 기본 2회 자동 재시도)
"""

import anthropic
from dotenv import load_dotenv

load_dotenv()  # .env 의 ANTHROPIC_API_KEY 를 환경변수로 로드

MODEL = "claude-haiku-4-5"  # 고성능 필요 시: "claude-opus-4-8" 로 변경


def main() -> None:
    client = anthropic.Anthropic()  # 키는 환경변수에서 자동 로드

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,  # '출력' 토큰 상한 (입력이 아님)
        system="너는 간결하고 정확한 한국어 기술 도우미다.",
        messages=[
            {"role": "user", "content": "파이썬 리스트 컴프리헨션을 한 문장으로 설명해줘."},
        ],
    )

    # 핵심: response.content 는 문자열이 아니라 '블록'의 리스트다.
    # 각 블록은 type(text/thinking/tool_use...)을 가지므로 확인 후 접근한다.
    print("=== 응답 블록 순회 ===")
    for block in response.content:
        if block.type == "text":
            print(block.text)
        else:
            print(f"[{block.type} 블록]")

    # 메타데이터: 왜 멈췄는지 + 토큰 사용량
    print("\n=== 메타 ===")
    print("stop_reason:", response.stop_reason)  # 보통 'end_turn'
    print("입력 토큰:", response.usage.input_tokens)
    print("출력 토큰:", response.usage.output_tokens)


if __name__ == "__main__":
    main()
