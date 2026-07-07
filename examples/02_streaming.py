"""
02. 스트리밍 — 응답을 토큰 단위로 받아 즉시 출력.

무엇을 가르치나:
  - client.messages.stream() 헬퍼로 텍스트 스트리밍
  - stream.text_stream 으로 델타를 순회하며 실시간 출력(flush)
  - stream.get_final_message() 로 스트림 종료 후 전체 메시지·usage 획득

왜 스트리밍인가:
  - 긴 출력/큰 max_tokens 에서 HTTP 타임아웃을 피하고 체감 지연을 줄인다.

실행법:
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/02_streaming.py

[기대 출력 예시] (이야기 내용은 실행마다 다르며 대략 이런 형태)
  === 스트리밍 출력 ===
  탐사선 아리랑호는 목성의 위성 유로파에 착륙했다. ... (토큰 단위로 실시간 출력)

  === 최종 usage ===
  stop_reason: end_turn
  입력 토큰: 35
  출력 토큰: 180

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 파일 확인
  - ModuleNotFoundError: No module named 'anthropic' → pip install anthropic python-dotenv
  - APIConnectionError: 네트워크 끊김(스트림 중단) → 재시도. 부분 출력은 버릴 것
"""

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경


def main() -> None:
    client = anthropic.Anthropic()

    print("=== 스트리밍 출력 ===")
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,  # max_tokens는 상한일 뿐 과금은 실제 생성분만 — 스트리밍에선 크게 줘도 무해함을 시연
        messages=[
            {"role": "user", "content": "우주 탐사를 소재로 한 짧은 이야기를 5문장으로 써줘."},
        ],
    ) as stream:
        # text_stream: 텍스트 델타만 순회한다. flush=True 로 즉시 화면에 흘린다.
        for text in stream.text_stream:
            print(text, end="", flush=True)

        # 스트림이 끝난 뒤 전체 메시지를 한 번에 얻는다 (usage 포함).
        final = stream.get_final_message()

    print("\n\n=== 최종 usage ===")
    print("stop_reason:", final.stop_reason)
    print("입력 토큰:", final.usage.input_tokens)
    print("출력 토큰:", final.usage.output_tokens)


if __name__ == "__main__":
    main()
