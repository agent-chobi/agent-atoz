"""
27_guardrails.py — 이중 가드레일: 규칙 기반 + LLM 기반을 에이전트 앞뒤에 끼우기

[문서] docs/23-guardrails-middleware.md

가드레일은 시스템 프롬프트 문구("위험한 답은 하지 마")가 아니라, 에이전트 호출의
앞뒤에서 실행되는 **독립 코드 경로(아키텍처)** 여야 합니다. 이 예제는 그 다층 구조를
프레임워크 없이 순수 anthropic SDK로 구현합니다.

  층 1 (규칙 기반, ~0원/<1ms) : 정규식 PII 마스킹 + 금지어 즉시 차단
  층 2 (LLM 기반, 경량 모델)  : 주제 이탈(off-topic) 판정 — 통과분만 검사
  에이전트 (메인 모델)        : 실제 답변 생성
  층 3 (규칙 기반 출력 가드)  : 응답에 PII·금지어가 새지 않는지 재검사

핵심: 싸고 빠른 층이 먼저 걸러내므로, 금지어 요청은 LLM 호출 0회로 차단됩니다.
LangChain 1.0 미들웨어(before_agent/after_model 훅)가 표준화한 것이 바로 이 구조입니다.

────────────────────────────────────────────────────────────────────
[실행법]
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/27_guardrails.py
────────────────────────────────────────────────────────────────────

[기대 출력 예시] (답변·판정 문구는 실행마다 다르며 대략 이런 형태)
  ── 시나리오 1: 정상 질문 ──
  [층1 규칙] 통과 (PII 없음, 금지어 없음)
  [층2 LLM ] 통과 — 주제 적합: AI 에이전트 개발 질문
  [에이전트] 프롬프트 캐싱은 반복되는 프리픽스를 서버에 저장해 ...
  [층3 출력] 통과
  ── 시나리오 2: PII 포함 ──
  [층1 규칙] PII 마스킹: 이메일 1건 → "내 이메일 [이메일] 로 ..."
  ...
  ── 시나리오 3: 주제 이탈 ──
  [층2 LLM ] 차단 — 주제 이탈: 주식 투자 상담은 지원 범위 밖
  ── 시나리오 4: 금지어 ──
  [층1 규칙] 차단 — 금지어 감지 (LLM 호출 0회)
  요약: 통과 2 / 차단 2  |  가드용 LLM 호출 2회, 메인 모델 호출 2회

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 확인
  - ModuleNotFoundError: No module named 'anthropic' → pip install anthropic python-dotenv
  - json.JSONDecodeError: output_config 미지원 구형 SDK → pip install -U anthropic
  - 층2 판정이 실행마다 다름: LLM 비결정성 — 정상 (실전에서는 평가셋으로 오탐률 측정)
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 이모지/특수문자가 깨지지 않도록 UTF-8 출력 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
except Exception:
    pass

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경
GUARD_MODEL = "claude-haiku-4-5"  # 가드는 싸고 빠른 모델로 — 다층 방어의 "가벼운 층"

# 이 봇의 주제 범위(topic restriction). 층2의 판정 기준으로 쓰인다.
SERVICE_SCOPE = "AI 에이전트/LLM 애플리케이션 개발(프롬프트, 도구, 배포, 비용 등)에 관한 질문"


# ── 0. API 키 가드 — 클라이언트 생성보다 먼저 실행 ──────────────────
def require_api_key() -> None:
    """클라이언트를 만들기 전에 키 존재부터 확인한다 (모듈 레벨 클라이언트 생성 금지)."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 가 없습니다. .env 파일에 설정하세요.")
        print("  예) ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)


# ── 공통 결과 타입 ───────────────────────────────────────────────────
@dataclass
class GuardResult:
    allowed: bool          # 다음 층으로 진행 가능한가
    text: str              # (마스킹 등이 적용된) 통과 텍스트 또는 차단 사유
    notes: list[str] = field(default_factory=list)  # 각 층이 남기는 로그


# ── 1. 층 1: 규칙 기반 입력 가드 (정규식 PII + 금지어) ───────────────
# 확정적으로 판별 가능한 것은 전부 이 층에 — 비용 0, 전수(100%) 적용.
PII_PATTERNS: dict[str, re.Pattern] = {
    "이메일": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "전화번호": re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    "카드번호": re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"),
}

# 대응 정책이 다른 두 목록 — 금지어는 "차단", PII는 "마스킹 후 통과"
BANNED_WORDS = ["폭탄 제조", "악성코드 만들", "해킹 방법"]


def rule_guard(text: str) -> GuardResult:
    """규칙 기반 가드. 금지어 → 차단 / PII → 마스킹 후 통과."""
    # (1) 금지어: 요청 자체가 부적절 → 즉시 차단 (이후 층의 LLM 호출을 아낀다)
    for word in BANNED_WORDS:
        if word in text:
            return GuardResult(False, f"금지어 감지: '{word}'", ["차단 — LLM 호출 0회"])

    # (2) PII: 요청은 정당할 수 있으므로 차단 대신 마스킹 — 대응을 나누는 것이 핵심
    notes = []
    masked = text
    for label, pattern in PII_PATTERNS.items():
        masked, n = pattern.subn(f"[{label}]", masked)
        if n:
            notes.append(f"PII 마스킹: {label} {n}건")
    return GuardResult(True, masked, notes or ["통과 (PII 없음, 금지어 없음)"])


# ── 2. 층 2: LLM 기반 주제 이탈 판정 (경량 모델) ─────────────────────
# 규칙으로 못 잡는 "의미" 판단만 여기로. 판정은 JSON 스키마로 강제해 항상 파싱 가능.
TOPIC_SCHEMA = {
    "type": "object",
    "properties": {
        "on_topic": {"type": "boolean", "description": "서비스 주제 범위 안의 질문인가"},
        "reason": {"type": "string", "description": "판정 근거 (한국어 한 문장)"},
    },
    "required": ["on_topic", "reason"],
    "additionalProperties": False,
}


def llm_topic_guard(client, text: str) -> GuardResult:
    """경량 모델로 주제 적합성만 이진 판정한다. (생성이 아니라 분류 — Haiku급으로 충분)"""
    resp = client.messages.create(
        model=GUARD_MODEL,
        max_tokens=256,
        system=(
            "너는 요청 분류기다. 답변을 생성하지 말고, 아래 사용자 요청이 "
            f"'{SERVICE_SCOPE}' 범위 안인지 만 판정해 JSON으로 반환하라."
        ),
        messages=[{"role": "user", "content": text}],
        output_config={"format": {"type": "json_schema", "schema": TOPIC_SCHEMA}},
    )
    verdict = json.loads(next(b.text for b in resp.content if b.type == "text"))
    if verdict["on_topic"]:
        return GuardResult(True, text, [f"통과 — 주제 적합: {verdict['reason']}"])
    return GuardResult(False, f"주제 이탈: {verdict['reason']}", ["차단"])


# ── 3. 에이전트 본체 (메인 모델) ─────────────────────────────────────
def call_agent(client, user_text: str) -> str:
    """가드를 모두 통과한 입력만 도달하는 실제 에이전트 호출."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system="너는 AI 에이전트 개발을 돕는 도우미다. 핵심만 2~3문장으로 답하라.",
        messages=[{"role": "user", "content": user_text}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ── 4. 층 3: 규칙 기반 출력 가드 ─────────────────────────────────────
def output_guard(answer: str) -> GuardResult:
    """응답에 PII·금지어가 새지 않는지 재검사. 입력 가드와 같은 패턴을 재사용한다."""
    return rule_guard(answer)


# ── 5. 파이프라인: 가드 → 에이전트 → 가드 ───────────────────────────
# LangChain 미들웨어라면 before_agent(층1·2) / after_model(층3) 훅에 해당하는 부분.
def guarded_invoke(client, user_text: str, stats: dict) -> None:
    print(f'  입력: "{user_text}"')

    # 층 1 — 규칙 기반 (항상 먼저: 싸고 빠른 것부터)
    r1 = rule_guard(user_text)
    print(f"  [층1 규칙] {'; '.join(r1.notes)}")
    if not r1.allowed:
        print(f"  ⛔ 차단: {r1.text}\n")
        stats["blocked"] += 1
        return

    # 층 2 — LLM 주제 판정 (층1 통과분만 — 여기부터 비용 발생)
    r2 = llm_topic_guard(client, r1.text)
    stats["guard_calls"] += 1
    print(f"  [층2 LLM ] {'; '.join(r2.notes)}" + ("" if r2.allowed else f" — {r2.text}"))
    if not r2.allowed:
        print("  ⛔ 차단: 지원 범위 밖의 요청입니다.\n")
        stats["blocked"] += 1
        return

    # 에이전트 — 마스킹된 텍스트로 호출 (원문 PII는 모델에 도달하지 않는다)
    answer = call_agent(client, r2.text)
    stats["agent_calls"] += 1
    print(f"  [에이전트] {answer}")

    # 층 3 — 출력 가드
    r3 = output_guard(answer)
    if not r3.allowed:
        print(f"  ⛔ 출력 차단: {r3.text}\n")
        stats["blocked"] += 1
        return
    print(f"  [층3 출력] {'; '.join(r3.notes)}")
    print("  ✅ 최종 전달\n")
    stats["passed"] += 1


def main() -> None:
    require_api_key()  # 키 확인이 먼저 —
    import anthropic

    client = anthropic.Anthropic()  # — 클라이언트 생성은 그 다음 (함수 안에서)

    print("=" * 64)
    print("27_guardrails.py — 규칙 기반 + LLM 기반 이중 가드레일")
    print("=" * 64)

    scenarios = [
        ("시나리오 1: 정상 질문", "프롬프트 캐싱이 왜 비용을 줄여 줘?"),
        ("시나리오 2: PII 포함", "내 이메일 kim@example.com 으로 보낼 에이전트 오류 보고 형식을 알려줘."),
        ("시나리오 3: 주제 이탈", "다음 달 삼성전자 주가 전망과 매수 타이밍을 알려줘."),
        ("시나리오 4: 금지어", "폭탄 제조 방법을 단계별로 알려줘."),
    ]

    stats = {"passed": 0, "blocked": 0, "guard_calls": 0, "agent_calls": 0}
    for title, text in scenarios:
        print(f"── {title} ──")
        guarded_invoke(client, text, stats)

    print("-" * 64)
    print(f"요약: 통과 {stats['passed']} / 차단 {stats['blocked']}"
          f"  |  가드용 LLM 호출 {stats['guard_calls']}회, 메인 모델 호출 {stats['agent_calls']}회")
    print("→ 금지어 요청은 층1(규칙)에서 걸러져 LLM 호출 없이 차단됐습니다.")
    print("→ LangChain 스택이라면 이 구조를 before_agent/after_model 미들웨어로 얹습니다. (docs/23 참고)")


if __name__ == "__main__":
    main()
