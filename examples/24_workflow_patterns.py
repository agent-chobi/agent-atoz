"""
24. 워크플로우 패턴 — Prompt Chaining · Routing · Parallelization 을 순수 SDK 로.

무엇을 가르치나:
  - Prompt Chaining: 초안 → 게이트(코드 검증) → 다듬기, 단계 사이를 코드가 제어
  - Routing: 분류 호출(구조화 출력)로 입력을 전문 프롬프트에 분기
  - Parallelization: AsyncAnthropic + asyncio.gather 로 독립 관점을 동시 실행

  프레임워크 없이 anthropic SDK 만으로 구현한다 — 워크플로우의 본질은
  'LLM 호출을 코드가 미리 정한 경로로 엮는 것'임을 보여주기 위해서다.

실행법:
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/24_workflow_patterns.py

[기대 출력 예시]
  === 1) Prompt Chaining ===
  [1단계] 한 줄 카피 초안: "회의록은 AI 가, 결정은 당신이."
  [게이트] 30자 이내 검증 통과
  [2단계] 최종 카피: 회의록은 AI가, 결정은 당신이

  === 2) Routing ===
  [분류] '환불 언제 되나요?' → billing
  [billing 전문 응답] 환불은 영업일 기준 3~5일 내에 ...

  === 3) Parallelization ===
  [병렬] 3개 관점 동시 분석 (약 N초)
  - 보안: ...
  - 비용: ...
  - 성능: ...
  [취합] 종합 권고: ...

[흔한 에러]
  - AuthenticationError: .env 의 ANTHROPIC_API_KEY 누락/오타
  - RuntimeError: asyncio.run() 중복 호출 — Jupyter 에서는 await main_async() 사용
  - RateLimitError: 병렬 호출 수가 조직 한도를 넘으면 429 —
    gather 대상 수를 줄이거나 재시도 백오프를 두면 된다
"""

import asyncio
import json
import os
import sys

import anthropic
from dotenv import load_dotenv

# Windows 콘솔에서 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경


def ask(client: anthropic.Anthropic, prompt: str, max_tokens: int = 512) -> str:
    """단일 호출 헬퍼 — 텍스트 블록만 뽑아 반환."""
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in resp.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# 1) Prompt Chaining — 단계 사이에 '코드 게이트'를 끼운 직렬 체인
# ---------------------------------------------------------------------------
def demo_chaining(client: anthropic.Anthropic) -> None:
    print("=== 1) Prompt Chaining ===")
    draft = ask(client, "회의록 자동 요약 SaaS 의 한 줄 광고 카피를 1개만, 따옴표 없이 출력하라.")
    print(f"[1단계] 한 줄 카피 초안: {draft}")

    # 게이트: LLM 이 아니라 '코드'가 중간 결과를 검증한다 — 워크플로우의 핵심
    if len(draft) > 30:
        print(f"[게이트] {len(draft)}자 — 30자 초과, 축약 단계 추가")
        draft = ask(client, f"다음 카피를 30자 이내로 축약하라. 결과만 출력:\n{draft}")
    else:
        print("[게이트] 30자 이내 검증 통과")

    final = ask(client, f"다음 카피를 더 자연스러운 한국어로 다듬어라. 결과만 출력:\n{draft}")
    print(f"[2단계] 최종 카피: {final}\n")


# ---------------------------------------------------------------------------
# 2) Routing — 분류 호출로 전문 핸들러에 분기 (분류는 구조화 출력으로 강제)
# ---------------------------------------------------------------------------
HANDLER_PROMPTS = {
    "billing": "너는 결제/환불 전문 상담원이다. 정중하고 정확하게 2문장 이내로 답하라.",
    "technical": "너는 기술지원 엔지니어다. 단계별 해결책을 3줄 이내로 제시하라.",
    "general": "너는 일반 안내 상담원이다. 친절하게 2문장 이내로 답하라.",
}

ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["billing", "technical", "general"]},
    },
    "required": ["category"],
    "additionalProperties": False,
}


def demo_routing(client: anthropic.Anthropic, question: str) -> None:
    print("=== 2) Routing ===")
    # 1단계: 저렴한 분류 호출 — enum 스키마로 잘못된 라벨 자체를 차단 (18장 참고)
    resp = client.messages.create(
        model=MODEL, max_tokens=64,
        messages=[{"role": "user", "content": f"다음 문의의 카테고리를 분류하라: {question}"}],
        output_config={"format": {"type": "json_schema", "schema": ROUTE_SCHEMA}},
    )
    category = json.loads(next(b.text for b in resp.content if b.type == "text"))["category"]
    print(f"[분류] '{question}' → {category}")

    # 2단계: 카테고리 전용 시스템 프롬프트로 본 응답
    answer = client.messages.create(
        model=MODEL, max_tokens=512,
        system=HANDLER_PROMPTS[category],
        messages=[{"role": "user", "content": question}],
    )
    text = next(b.text for b in answer.content if b.type == "text").strip()
    print(f"[{category} 전문 응답] {text}\n")


# ---------------------------------------------------------------------------
# 3) Parallelization — 독립 하위작업을 asyncio 로 동시 실행 (sectioning)
# ---------------------------------------------------------------------------
ASPECTS = ["보안", "비용", "성능"]


async def analyze_aspect(client: anthropic.AsyncAnthropic, plan: str, aspect: str) -> str:
    """하나의 관점에서 계획을 분석 — 서로 독립이므로 병렬화 가능."""
    resp = await client.messages.create(
        model=MODEL, max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"다음 계획을 '{aspect}' 관점에서만 한 문장으로 평가하라:\n{plan}",
        }],
    )
    return next(b.text for b in resp.content if b.type == "text").strip()


async def demo_parallel(plan: str) -> None:
    print("=== 3) Parallelization ===")
    aclient = anthropic.AsyncAnthropic()

    # 세 관점을 동시에 — 지연은 '가장 느린 호출 1개' 수준으로 줄어든다
    print(f"[병렬] {len(ASPECTS)}개 관점 동시 분석")
    results = await asyncio.gather(
        *(analyze_aspect(aclient, plan, a) for a in ASPECTS)
    )
    for aspect, result in zip(ASPECTS, results):
        print(f"- {aspect}: {result}")

    # 취합(reduce): 병렬 결과를 하나로 합치는 마지막 직렬 단계
    merged = "\n".join(f"{a}: {r}" for a, r in zip(ASPECTS, results))
    final = await aclient.messages.create(
        model=MODEL, max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"다음 세 관점의 평가를 종합해 한 문장의 권고로 요약하라:\n{merged}",
        }],
    )
    print(f"[취합] 종합 권고: {next(b.text for b in final.content if b.type == 'text').strip()}\n")


def main() -> None:
    # API 키 가드는 클라이언트 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("오류: ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일을 확인하세요.")
    client = anthropic.Anthropic()

    demo_chaining(client)
    demo_routing(client, "환불 언제 되나요?")
    asyncio.run(demo_parallel("사내 문서 검색용 RAG 챗봇을 2주 안에 출시한다."))


if __name__ == "__main__":
    main()
