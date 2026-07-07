"""
03. Tool Use — 단일 왕복(tool_use -> tool_result) 수동 처리.

무엇을 가르치나:
  - 도구 2개(get_weather, calculator)를 JSON Schema 로 정의
  - tools 를 넘겨 stop_reason == "tool_use" 로 도구 호출을 받는다
  - 도구를 실행하고 결과를 tool_result 로 되돌려 최종 답을 얻는다

핵심 규칙:
  - tool_result.tool_use_id 는 대응하는 tool_use.id 와 정확히 일치해야 한다
  - 어시스턴트 응답(content 전체)을 히스토리에 다시 넣어야 한다

실행법:
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/03_tool_use.py

[기대 출력 예시] (출력은 실행마다 다르며 대략 이런 형태)
  stop_reason: tool_use
    -> 도구 호출: get_weather({'city': '서울'})
    -> 도구 호출: calculator({'expression': '(3+5)*2'})

  === 최종 답변 ===
  서울은 현재 맑고 24도입니다. (3+5)*2 = 16 입니다.

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 파일 확인
  - invalid_request_error (400): tool_result 의 tool_use_id 불일치 → block.id 를 그대로 사용
  - KeyError: 모델이 정의에 없는 도구를 호출(드묾) → TOOL_FUNCS 매핑과 도구 이름 확인
"""

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경

# --- 도구 정의 (JSON Schema) -------------------------------------------------
TOOLS = [
    {
        "name": "get_weather",
        "description": "특정 도시의 현재 날씨를 조회한다. 날씨/기온 질문이면 호출.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "도시 이름, 예: 서울"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "calculator",
        "description": "산술식을 계산한다. 수식 계산이 필요하면 호출.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "예: (3+5)*2"},
            },
            "required": ["expression"],
        },
    },
]


# --- 실제 도구 구현 (로컬 함수) ----------------------------------------------
def get_weather(city: str) -> str:
    fake = {"서울": "맑음, 24도", "부산": "흐림, 21도"}
    return fake.get(city, "정보 없음")


def calculator(expression: str) -> str:
    try:
        # 데모용. 실제 서비스에서는 안전한 파서를 쓸 것.
        return str(eval(expression, {"__builtins__": {}}))
    except Exception as e:  # noqa: BLE001
        return f"계산 오류: {e}"


TOOL_FUNCS = {"get_weather": get_weather, "calculator": calculator}


def main() -> None:
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": "서울 날씨 알려주고, (3+5)*2 도 계산해줘."}]

    # 1) 첫 호출 — 모델이 도구 호출을 요청한다
    resp = client.messages.create(
        model=MODEL, max_tokens=1024, tools=TOOLS, messages=messages,
    )
    print("stop_reason:", resp.stop_reason)  # 'tool_use'

    # 2) 어시스턴트 응답(도구 호출 포함) 전체를 히스토리에 추가
    messages.append({"role": "assistant", "content": resp.content})

    # 3) 이번 턴의 모든 tool_use 블록을 실행 (병렬 호출 대비)
    tool_results = []
    for block in resp.content:
        if block.type == "tool_use":
            print(f"  -> 도구 호출: {block.name}({block.input})")
            output = TOOL_FUNCS[block.name](**block.input)  # 이미 파싱된 dict
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,  # 반드시 tool_use.id 와 일치
                "content": output,
            })

    # 4) 모든 결과를 하나의 user 메시지로 반환
    messages.append({"role": "user", "content": tool_results})

    # 5) 결과를 반영한 최종 답변
    final = client.messages.create(
        model=MODEL, max_tokens=1024, tools=TOOLS, messages=messages,
    )
    print("\n=== 최종 답변 ===")
    print(next(b.text for b in final.content if b.type == "text"))


if __name__ == "__main__":
    main()
