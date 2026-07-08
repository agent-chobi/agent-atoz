"""
29_reliability_validation.py — 재시도·폴백 + 3단 검증 게이트 (docs/25-reliability-validation.md)

무엇을 보여주나
---------------
(A) 재시도 + 폴백 데코레이터
    - 일시적 실패(429/5xx 등)를 지수 백오프로 재시도하고,
    - 재시도를 소진하면 폴백 모델 체인(Opus 실패 → Sonnet)으로 갈아탄다.
    - 동작을 눈으로 확인할 수 있게, 먼저 "2번 실패 후 성공하는 가짜 함수"로 시연한다.

(B) 3단 검증 게이트 파이프라인 (스키마 → 규칙 → LLM judge)
    - 생성 단계가 만든 산출물(상품 소개 JSON)을
      ① 스키마 게이트(파싱·필수 필드) → ② 규칙 게이트(길이·금칙어)
      → ③ judge 게이트(별도 프롬프트, 4점 이상) 순으로 검사한다.
    - 어느 게이트든 실패하면 실패 사유를 피드백으로 붙여 재생성한다(상한 2회).
    - 재생성 경로가 항상 시연되도록, 1차 시도 산출물은 "고의로 오염"시킨다
      (규칙 게이트가 잡아내는 것을 보여주기 위한 실습 장치).

실행법
------
  # 1) 의존성
  pip install anthropic python-dotenv
  # 2) .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  # 3) 실행
  python examples/29_reliability_validation.py

[기대 출력 예시] (문구·점수는 실행마다 다르며 대략 이런 형태)
  ======================================================================
  A) 재시도 + 폴백 데코레이터
  ======================================================================
  [시도 1/3] flaky_service ... 실패(가짜 과부하) → 0.5초 대기
  [시도 2/3] flaky_service ... 실패(가짜 과부하) → 1.0초 대기
  [시도 3/3] flaky_service ... 성공
  결과: 3번째 시도에 성공했습니다

  ======================================================================
  B) 3단 검증 게이트 파이프라인
  ======================================================================
  --- 시도 1 (산출물 고의 오염: 금칙어 삽입) ---
  [게이트 1] 스키마 검증 ... PASS
  [게이트 2] 규칙 검증   ... FAIL — 금칙어 '세계 최고' 포함
  → 실패 사유를 피드백으로 붙여 재생성

  --- 시도 2 ---
  [게이트 1] 스키마 검증 ... PASS
  [게이트 2] 규칙 검증   ... PASS
  [게이트 3] LLM judge   ... PASS (5/5)
  [최종 통과] name='...' summary='...'

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 확인
  - ModuleNotFoundError: No module named 'anthropic' → pip install anthropic python-dotenv
  - judge 게이트에서 계속 FAIL: LLM 채점의 비결정성 — 상한 도달 시
    "인간 폴백 큐" 메시지가 나오는 것이 정상 동작(불량을 하류로 안 보냈다는 뜻)
"""

from __future__ import annotations

import functools
import json
import os
import random
import sys
import time
from typing import Callable

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 출력이 깨지지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경
FALLBACK_MODEL = "claude-sonnet-5"  # 주 모델 실패 시 갈아탈 모델


# ---------------------------------------------------------------------------
# A) 재시도 + 폴백 데코레이터
# ---------------------------------------------------------------------------
def with_retry(max_attempts: int = 3, base_delay: float = 0.5):
    """일시적 실패를 지수 백오프(+지터)로 재시도하는 데코레이터.

    - 재시도 대상: TransientError (실전에서는 anthropic.RateLimitError,
      APIStatusError 중 5xx, APIConnectionError 등을 여기에 매핑)
    - 결정적 오류(ValueError 등)는 재시도하지 않고 그대로 올린다(§1 분류).
    """

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"[시도 {attempt}/{max_attempts}] {fn.__name__} ...", end=" ")
                    result = fn(*args, **kwargs)
                    print("성공")
                    return result
                except TransientError as e:
                    last_exc = e
                    if attempt == max_attempts:
                        print(f"실패({e}) → 재시도 소진")
                        break
                    # 지수 백오프 + 지터: 0.5 → 1.0 → 2.0초 ... (+ 무작위)
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.1)
                    print(f"실패({e}) → {delay:.1f}초 대기")
                    time.sleep(delay)
            raise last_exc  # 재시도 소진 — 호출자가 폴백을 결정한다

        return wrapper

    return decorator


class TransientError(Exception):
    """일시적 실패(레이트리밋·과부하·네트워크)를 나타내는 예제용 예외."""


def demo_retry_and_fallback() -> None:
    """가짜 불안정 서비스로 재시도·폴백 동작을 API 비용 없이 시연한다."""
    calls = {"n": 0}

    @with_retry(max_attempts=3, base_delay=0.5)
    def flaky_service() -> str:
        """처음 2번은 실패하고 3번째에 성공하는 가짜 서비스."""
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("가짜 과부하")
        return f"{calls['n']}번째 시도에 성공했습니다"

    print("결과:", flaky_service())

    # 폴백 체인의 뼈대: 주 모델의 재시도가 소진되면 다음 모델로 넘어간다.
    # (실전에서는 각 call_llm 이 실제 API 호출이 된다)
    def call_with_fallback_chain(models: list[str]) -> str:
        for i, model in enumerate(models):
            try:

                @with_retry(max_attempts=2, base_delay=0.3)
                def call_llm() -> str:
                    if i == 0:  # 첫 모델은 계속 실패한다고 가정 (시연용)
                        raise TransientError(f"{model} 지속 장애")
                    return f"{model} 가 응답했습니다"

                return call_llm()
            except TransientError:
                print(f"→ 폴백: {model} 포기, 다음 모델로 전환")
        return "모든 모델 실패 — 캐시 응답/인간 폴백으로"

    print("\n[폴백 체인 시연]")
    print("결과:", call_with_fallback_chain([MODEL, FALLBACK_MODEL]))


# ---------------------------------------------------------------------------
# B) 3단 검증 게이트 파이프라인
# ---------------------------------------------------------------------------
# 생성 단계가 지켜야 할 산출물 스키마 (18장: output_config.format 으로 형식 강제)
PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "상품명"},
        "summary": {"type": "string", "description": "한 문단 소개 (과장 없이)"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "태그 2~4개"},
    },
    "required": ["name", "summary", "tags"],
    "additionalProperties": False,
}

# judge 채점 결과 스키마 (15장: enum 으로 1~5 정수만 허용)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "reasoning": {"type": "string", "description": "점수 근거 (한국어 1~2문장)"},
    },
    "required": ["score", "reasoning"],
    "additionalProperties": False,
}

BANNED_WORDS = ["세계 최고", "100% 보장", "완벽한"]  # 규칙 게이트의 금칙어


def generate_product_json(client, feedback: str | None) -> str:
    """상품 소개 JSON 을 생성한다. 재생성 시에는 이전 실패 사유를 피드백으로 붙인다."""
    user = (
        "상품: '텀블러 오션' — 재활용 스테인리스 보온 텀블러.\n"
        "이 상품의 소개 JSON을 만들어라. summary는 사실 위주로 120자 이내."
    )
    if feedback:
        user += f"\n\n[이전 산출물이 검증에서 탈락했다. 실패 사유를 반드시 고쳐라]\n{feedback}"

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system="너는 이커머스 카피라이터다. 과장·최상급 표현 없이 사실만 쓴다.",
        messages=[{"role": "user", "content": user}],
        # 형식은 생성 시점에 강제 → 스키마 게이트는 사실상 항상 통과 (18장)
        output_config={"format": {"type": "json_schema", "schema": PRODUCT_SCHEMA}},
    )
    return next(b.text for b in resp.content if b.type == "text")


def gate1_schema(raw: str) -> tuple[dict | None, str]:
    """게이트 ①: 파싱 + 필수 필드. 결정적이고 무료 → 전수 적용."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"JSON 파싱 실패: {e}"
    missing = [k for k in ("name", "summary", "tags") if k not in data]
    if missing:
        return None, f"필수 필드 누락: {missing}"
    return data, ""


def gate2_rules(data: dict) -> str:
    """게이트 ②-규칙: 길이·금칙어 같은 결정적 비즈니스 규칙."""
    if len(data["summary"]) > 200:
        return f"summary 가 200자 초과({len(data['summary'])}자)"
    for word in BANNED_WORDS:
        if word in data["summary"] or word in data["name"]:
            return f"금칙어 '{word}' 포함"
    if not (2 <= len(data["tags"]) <= 4):
        return f"태그 수 위반({len(data['tags'])}개, 2~4개 필요)"
    return ""


def gate3_judge(client, data: dict) -> tuple[int, str]:
    """게이트 ②-judge: 별도 프롬프트의 채점자가 품질을 1~5점으로 판정 (15장)."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=(
            "너는 엄격한 카피 심사자다. 답을 새로 쓰지 말고 주어진 산출물만 채점하라. "
            "기준: 사실 위주인가, 과장이 없는가, 자연스러운 한국어인가."
        ),
        messages=[{
            "role": "user",
            "content": f"다음 상품 소개를 채점하라:\n{json.dumps(data, ensure_ascii=False)}",
        }],
        output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
    )
    verdict = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return verdict["score"], verdict["reasoning"]


def demo_validation_pipeline(client) -> None:
    """스키마→규칙→judge 게이트를 통과할 때까지 재생성하는 파이프라인 (상한 2회)."""
    MAX_ATTEMPTS = 2
    feedback: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        tainted = attempt == 1
        label = " (산출물 고의 오염: 금칙어 삽입)" if tainted else ""
        print(f"\n--- 시도 {attempt}{label} ---")

        raw = generate_product_json(client, feedback)
        # ⚠️ 실습 장치: 1차 시도 산출물에 금칙어를 주입해 규칙 게이트가
        #    불량을 잡아 재생성시키는 경로를 항상 시연한다. 실전에서는 제거할 것.
        if tainted:
            data_tmp = json.loads(raw)
            data_tmp["summary"] = "세계 최고의 보온력! " + data_tmp["summary"]
            raw = json.dumps(data_tmp, ensure_ascii=False)

        # 게이트 ① 스키마
        data, err = gate1_schema(raw)
        print(f"[게이트 1] 스키마 검증 ... {'PASS' if data else 'FAIL — ' + err}")
        if data is None:
            feedback = f"스키마 위반: {err}"
            continue

        # 게이트 ② 규칙
        err = gate2_rules(data)
        print(f"[게이트 2] 규칙 검증   ... {'PASS' if not err else 'FAIL — ' + err}")
        if err:
            feedback = f"규칙 위반: {err}"
            print("→ 실패 사유를 피드백으로 붙여 재생성")
            continue

        # 게이트 ③ LLM judge (통과분에만 — 비용이 드는 게이트는 마지막에)
        score, reasoning = gate3_judge(client, data)
        ok = score >= 4
        print(f"[게이트 3] LLM judge   ... {'PASS' if ok else 'FAIL'} ({score}/5) — {reasoning}")
        if not ok:
            feedback = f"품질 미달({score}/5): {reasoning}"
            print("→ judge 근거를 피드백으로 붙여 재생성")
            continue

        print(f"[최종 통과] name={data['name']!r} summary={data['summary']!r}")
        return

    # 재생성 상한 도달 — 불량을 하류로 보내지 않고 인간에게 넘긴다 (25장 설계 가이드)
    print(f"\n[상한 도달] {MAX_ATTEMPTS}회 재생성에도 게이트 미통과 → 인간 폴백 큐로 이관")


# ---------------------------------------------------------------------------
# 데모
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 70)
    print("A) 재시도 + 폴백 데코레이터")
    print("=" * 70)
    demo_retry_and_fallback()  # API 키 불필요 (가짜 서비스로 시연)

    # ── API 키 가드: 클라이언트 생성보다 먼저 ────────────────────────────
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\nANTHROPIC_API_KEY 가 없습니다 — (B) 검증 게이트 데모는 건너뜁니다.")
        print(".env 에 ANTHROPIC_API_KEY=sk-ant-... 를 설정한 뒤 다시 실행하세요.")
        return

    import anthropic

    client = anthropic.Anthropic()

    print("\n" + "=" * 70)
    print("B) 3단 검증 게이트 파이프라인")
    print("=" * 70)
    demo_validation_pipeline(client)


if __name__ == "__main__":
    main()
