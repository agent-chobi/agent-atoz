"""
23. 구조화된 출력 — Pydantic 파싱, strict tool use, 검증 실패 재시도.

무엇을 가르치나:
  - client.messages.parse() + Pydantic 모델로 영수증 텍스트를 타입 안전하게 파싱
  - 도구 정의에 strict: True 를 붙여 도구 입력을 스키마 수준에서 보장
  - 스키마는 통과했지만 '비즈니스 규칙'이 깨진 경우 오류를 되돌려 재시도

실행법:
  pip install anthropic pydantic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/23_structured_output.py

[기대 출력 예시]
  === 1) Pydantic 영수증 파싱 (messages.parse) ===
  가게: 한빛분식 / 날짜: 2026-07-01
  - 김치찌개 x2 @ 9000원
  - 공기밥 x2 @ 1000원
  합계: 20000원 (검증 통과: True)

  === 2) strict tool use — 회의 예약 ===
  도구 호출: book_meeting
  입력(스키마 보장): {'title': '주간 회고', 'date': '2026-07-10', 'attendees': 4}

  === 3) 검증 실패 재시도 ===
  [시도 1] 검증 통과 → {'name': '김개발', 'email': 'kim@example.com', ...}

[흔한 에러]
  - AuthenticationError: .env 의 ANTHROPIC_API_KEY 누락/오타
  - additionalProperties 관련 400: strict/json_schema 는
    "additionalProperties": False 와 required 전체 나열이 필수
  - ValidationError: 스키마 밖 제약(합계 검증 등)은 모델 응답이 어겨도
    API 가 막지 못함 → 이 예제의 3번처럼 재시도 루프로 처리
"""

import json
import os
import sys

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, model_validator

# Windows 콘솔에서 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

MODEL = "claude-haiku-4-5"  # 고성능 필요 시: "claude-opus-4-8" 로 변경


# ---------------------------------------------------------------------------
# 1) Pydantic 모델 → 스키마 자동 변환 (messages.parse)
# ---------------------------------------------------------------------------
class LineItem(BaseModel):
    """영수증의 품목 한 줄."""

    name: str = Field(description="품목 이름")
    quantity: int = Field(description="수량")
    unit_price: int = Field(description="단가(원)")


class Receipt(BaseModel):
    """영수증 전체. 합계가 품목 합과 일치해야 검증을 통과한다."""

    store: str = Field(description="가게 이름")
    date: str = Field(description="구매 날짜, YYYY-MM-DD")
    items: list[LineItem] = Field(description="품목 목록")
    total: int = Field(description="합계 금액(원)")

    @model_validator(mode="after")
    def check_total(self) -> "Receipt":
        # 스키마(타입)는 API 가 보장하지만, '합계 = 품목 합' 같은
        # 비즈니스 규칙은 여기서 직접 검증해야 한다.
        expected = sum(i.quantity * i.unit_price for i in self.items)
        if expected != self.total:
            raise ValueError(f"합계 불일치: 품목 합 {expected} != total {self.total}")
        return self


RECEIPT_TEXT = """
[한빛분식] 2026-07-01
김치찌개 2개 x 9,000원
공기밥 2개 x 1,000원
합계 20,000원
"""


def demo_parse_receipt(client: anthropic.Anthropic) -> None:
    print("=== 1) Pydantic 영수증 파싱 (messages.parse) ===")
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": f"다음 영수증을 파싱하라:\n{RECEIPT_TEXT}"}],
        output_format=Receipt,  # Pydantic 모델이 곧 JSON Schema 가 된다
    )
    receipt = resp.parsed_output  # 이미 검증된 Receipt 인스턴스
    print(f"가게: {receipt.store} / 날짜: {receipt.date}")
    for item in receipt.items:
        print(f"- {item.name} x{item.quantity} @ {item.unit_price}원")
    print(f"합계: {receipt.total}원 (검증 통과: True)\n")


# ---------------------------------------------------------------------------
# 2) strict tool use — 도구 입력을 스키마 수준에서 보장
# ---------------------------------------------------------------------------
BOOK_MEETING_TOOL = {
    "name": "book_meeting",
    "description": "회의를 예약한다. 사용자가 회의/미팅 일정을 잡아 달라고 하면 호출.",
    "strict": True,  # tool_choice 가 아니라 '도구 정의'에 붙인다
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "회의 제목"},
            "date": {"type": "string", "format": "date", "description": "YYYY-MM-DD"},
            "attendees": {"type": "integer", "enum": [2, 3, 4, 5, 6]},
        },
        "required": ["title", "date", "attendees"],  # strict 는 전 필드 나열 필수
        "additionalProperties": False,               # strict 필수 조건
    },
}


def demo_strict_tool(client: anthropic.Anthropic) -> None:
    print("=== 2) strict tool use — 회의 예약 ===")
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[BOOK_MEETING_TOOL],
        messages=[{
            "role": "user",
            "content": "7월 10일에 4명이 참석하는 '주간 회고' 회의를 잡아줘.",
        }],
    )
    for block in resp.content:
        if block.type == "tool_use":
            print(f"도구 호출: {block.name}")
            print(f"입력(스키마 보장): {block.input}\n")  # 파싱된 dict, 스키마 100% 준수


# ---------------------------------------------------------------------------
# 3) 검증 실패 재시도 — output_config.format + Pydantic 수동 검증
# ---------------------------------------------------------------------------
class Candidate(BaseModel):
    """이력서 요약. 경력 연차는 0 이상이어야 한다."""

    name: str
    email: str
    skills: list[str]
    years_of_experience: int

    @model_validator(mode="after")
    def check_experience(self) -> "Candidate":
        if self.years_of_experience < 0:
            raise ValueError("경력 연차는 0 이상이어야 함")
        return self


RESUME_TEXT = "김개발 (kim@example.com) — Python/LangGraph 5년차, MCP 서버 구축 경험."


def demo_retry(client: anthropic.Anthropic, max_retries: int = 3) -> None:
    print("=== 3) 검증 실패 재시도 ===")
    schema = Candidate.model_json_schema()
    schema["additionalProperties"] = False  # output_config.format 필수 조건

    messages = [{"role": "user", "content": f"다음 이력서를 파싱하라:\n{RESUME_TEXT}"}]
    for attempt in range(1, max_retries + 1):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next(b.text for b in resp.content if b.type == "text")
        try:
            candidate = Candidate.model_validate(json.loads(text))
            print(f"[시도 {attempt}] 검증 통과 → {candidate.model_dump()}\n")
            return
        except (ValidationError, json.JSONDecodeError) as e:
            # 오류를 버리지 않고 대화에 되돌려 주면 모델이 고쳐서 다시 낸다
            print(f"[시도 {attempt}] 검증 실패: {e}")
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": f"검증 오류가 발생했다. 수정해서 다시 출력하라:\n{e}",
            })
    print("[재시도 한도 초과]\n")


def main() -> None:
    # API 키 가드는 클라이언트 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("오류: ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    client = anthropic.Anthropic()

    demo_parse_receipt(client)
    demo_strict_tool(client)
    demo_retry(client)


if __name__ == "__main__":
    main()
