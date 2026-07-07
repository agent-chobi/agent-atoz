"""
04. 최소 에이전트 루프 — stop_reason 을 보고 도구를 반복 실행.

무엇을 가르치나:
  - while 루프로 '생각 -> 행동 -> 관찰'을 반복하는 자율 에이전트
  - stop_reason == "end_turn" 이면 종료, "tool_use" 인 한 계속 반복
  - max_turns 상한으로 폭주 방지, 도구 오류는 is_error 로 되돌리기

이 예제는 로컬 파이썬 함수(도구)만으로 여러 단계를 연쇄한다.
  예) "부산 기온을 화씨로 바꿔줘" -> 날씨 조회 -> 계산 -> 답변

실행법:
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/04_agent_loop.py
"""

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감시 claude-haiku-4-5

TOOLS = [
    {
        "name": "get_temperature",
        "description": "도시의 현재 기온을 섭씨(숫자)로 반환한다.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "도시 이름"}},
            "required": ["city"],
        },
    },
    {
        "name": "celsius_to_fahrenheit",
        "description": "섭씨 기온을 화씨로 변환한다.",
        "input_schema": {
            "type": "object",
            "properties": {"celsius": {"type": "number", "description": "섭씨 온도"}},
            "required": ["celsius"],
        },
    },
]


def get_temperature(city: str) -> str:
    fake = {"서울": 24, "부산": 21}
    if city not in fake:
        raise ValueError(f"도시 '{city}'의 기온 정보 없음")
    return str(fake[city])


def celsius_to_fahrenheit(celsius: float) -> str:
    return str(celsius * 9 / 5 + 32)


TOOL_FUNCS = {
    "get_temperature": get_temperature,
    "celsius_to_fahrenheit": celsius_to_fahrenheit,
}


def run_agent(user_input: str, max_turns: int = 10) -> str:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_input}]

    for turn in range(max_turns):  # 폭주 방지 상한
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, tools=TOOLS, messages=messages,
        )

        # 종료 조건: 모델이 더는 도구가 필요 없다고 판단
        if resp.stop_reason == "end_turn":
            return next(b.text for b in resp.content if b.type == "text")

        if resp.stop_reason != "tool_use":
            return f"[예상 밖 stop_reason: {resp.stop_reason}]"

        # 어시스턴트 응답(도구 호출 포함) 누적
        messages.append({"role": "assistant", "content": resp.content})

        # 이번 턴의 모든 도구 실행 -> 결과 수집 (관찰)
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            print(f"[턴 {turn}] {block.name}({block.input})")
            try:
                output = TOOL_FUNCS[block.name](**block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
            except Exception as e:  # noqa: BLE001
                # 오류를 버리지 말고 되돌려주면 모델이 다른 방법을 시도한다
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"오류: {e}",
                    "is_error": True,
                })

        # 모든 결과를 하나의 user 메시지로 반환
        messages.append({"role": "user", "content": results})

    return "[최대 턴 수 초과]"


def main() -> None:
    answer = run_agent("부산의 현재 기온을 화씨로 바꿔서 알려줘.")
    print("\n=== 최종 답변 ===")
    print(answer)


if __name__ == "__main__":
    main()
