"""
31_context_budget.py — 섹션별 컨텍스트 예산을 정의하고 초과분을 트리밍/요약

무엇을 보여주나
---------------
- 컨텍스트 창을 하나의 덩어리가 아니라 **섹션별 예산**으로 관리한다:
  시스템 프롬프트 / 도구 정의 / 대화 히스토리 / RAG 결과.
- 각 섹션의 사용량을 측정한다:
  (a) ANTHROPIC_API_KEY 가 있으면 client.messages.count_tokens (정확)
  (b) 키가 없으면 로컬 근사치 len(text) / 3.5 (폴백 — 대략적 감만 잡는 용도)
- 예산을 초과한 섹션을 정책대로 줄인다:
  - 히스토리: 오래된 턴부터 삭제(트리밍) — 로컬 연산, 키 불필요
  - RAG 결과: 키가 있으면 LLM 요약, 없으면 단순 절삭(truncate)
- 결과를 예산표(섹션 | 예산 | 사용 | 상태)로 출력한다.
- 대응 문서: docs/08-context-engineering.md 의 "실무 패턴 — 컨텍스트 예산 배분"

실행법
------
  pip install anthropic python-dotenv
  copy .env.example .env      # (선택) 키 없이도 폴백 모드로 동작한다
  python examples/31_context_budget.py

[기대 출력 예시] (토큰 수치는 카운터·실행 환경에 따라 다름)
  토큰 카운터: 로컬 근사 (len/3.5)   ← 키가 있으면 "count_tokens API"
  === 예산 집행 전 ===
  섹션         |   예산 |   사용 | 상태
  system      |    300 |     18 | OK
  tools       |    400 |     95 | OK
  history     |    600 |    931 | 초과!
  rag         |    500 |    914 | 초과!
  ------------------------------------
  합계         |   1800 |   1958 |

  [history] 931 → 558 토큰 (오래된 8턴 삭제)
  [rag] 914 → 501 토큰 (단순 절삭)      ← 키가 있으면 "LLM 요약"

  === 예산 집행 후 ===
  ... (모든 섹션 OK, 합계가 총예산 이내)

[흔한 에러]
  - ImportError: No module named 'anthropic' → pip install anthropic python-dotenv
  - authentication_error (401): ANTHROPIC_API_KEY 값이 잘못됨 → .env 확인
    (키를 아예 지우면 폴백 모드로 동작하므로 데모 자체는 실행 가능)
  - 집행 후에도 '초과!' 표시: 예산이 지나치게 작으면 최근 1턴/최소 보존분만으로도
    초과할 수 있음 → BUDGET 값을 키워 관찰
"""

import json
import os
import sys

from dotenv import load_dotenv

# Windows 콘솔에서 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경

# ---------------------------------------------------------------------------
# 1) 섹션별 토큰 예산 — 총 컨텍스트를 용도별로 나눠서 상한을 건다.
#    비율은 docs/08 "실무 패턴"의 예산표를 축소한 데모용 수치.
# ---------------------------------------------------------------------------
BUDGET = {
    "system": 300,   # 시스템 프롬프트 (불변 — 초과하면 설계부터 재검토)
    "history": 600,  # 대화 히스토리 (초과 시 오래된 턴 삭제)
    "rag": 500,      # RAG 검색 결과 (초과 시 요약/절삭)
    "tools": 400,    # 도구 정의 (불변 — 초과하면 도구 수를 줄일 신호)
}

# API 키 유무에 따라 정확 카운트 / 로컬 근사를 자동 선택
_client = None
if os.getenv("ANTHROPIC_API_KEY"):
    try:
        import anthropic

        _client = anthropic.Anthropic()
    except ImportError:
        pass  # anthropic 미설치 → 폴백 모드


def count_tokens(text: str) -> int:
    """토큰 수 측정. 키가 있으면 count_tokens API, 없으면 문자수/3.5 근사."""
    if _client is not None:
        resp = _client.messages.count_tokens(
            model=MODEL,
            messages=[{"role": "user", "content": text}],
        )
        return resp.input_tokens
    # 로컬 근사: 한국어/영어 혼합 텍스트에서 대략 1토큰 ≈ 3.5자
    # (정밀하지 않다 — 예산 '경보' 용도로만 쓰고, 과금 추정에는 쓰지 말 것)
    return max(1, int(len(text) / 3.5))


# ---------------------------------------------------------------------------
# 2) 데모용 가짜 컨텍스트 — 실제로는 에이전트 루프가 채우는 값들
# ---------------------------------------------------------------------------
def build_fake_context() -> dict:
    """섹션별 텍스트를 만든다. history/rag 는 일부러 예산을 초과시킨다."""
    system = (
        "너는 사내 문서 검색 도우미다. 항상 한국어로 답하고, "
        "출처 문서 ID를 함께 제시한다. 모르면 모른다고 말한다."
    )

    tools = json.dumps(
        [
            {
                "name": "search_docs",
                "description": "사내 위키에서 키워드로 문서를 검색한다.",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "read_doc",
                "description": "문서 ID로 본문 전체를 읽는다.",
                "input_schema": {
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                    "required": ["doc_id"],
                },
            },
        ],
        ensure_ascii=False,
        sort_keys=True,  # 캐시 친화: 직렬화를 결정적으로 (docs/08 실무 패턴)
    )

    # 20턴짜리 긴 히스토리 — history 예산을 초과하도록 각 턴을 길게
    history = []
    for i in range(20):
        history.append(
            {
                "role": "user",
                "content": f"질문 {i + 1}: 휴가 규정 문서에서 이월 조건을 다시 설명해줘. "
                "작년에 바뀐 부분과 올해 기준을 비교해서 알려주면 좋겠어.",
            }
        )
        history.append(
            {
                "role": "assistant",
                "content": f"답변 {i + 1}: 연차 이월은 최대 5일까지 가능하며, "
                "미사용분은 다음 해 3월까지 소진해야 합니다. 자세한 근거는 HR-042 문서를 참고하세요.",
            }
        )

    # rag 예산을 초과하는 긴 RAG 결과
    rag = "\n".join(
        f"[문서 HR-{i:03d}] 휴가 규정 제{i}조: 연차는 입사일 기준으로 산정하며, "
        "회계연도 전환 시 잔여 일수는 인사 시스템에서 자동 정산된다. "
        "부서장 승인 없이 5일 이상 연속 사용은 불가하다."
        for i in range(1, 31)
    )

    return {"system": system, "tools": tools, "history": history, "rag": rag}


def history_to_text(history: list) -> str:
    """히스토리(메시지 목록)를 토큰 측정용 단일 텍스트로 직렬화."""
    return "\n".join(f"{m['role']}: {m['content']}" for m in history)


def measure(ctx: dict) -> dict:
    """섹션별 사용 토큰을 측정해 dict 로 반환."""
    return {
        "system": count_tokens(ctx["system"]),
        "tools": count_tokens(ctx["tools"]),
        "history": count_tokens(history_to_text(ctx["history"])),
        "rag": count_tokens(ctx["rag"]),
    }


def print_table(usage: dict, title: str) -> None:
    """예산표를 표 형태로 출력."""
    print(f"\n=== {title} ===")
    print(f"{'섹션':<10} | {'예산':>6} | {'사용':>6} | 상태")
    print("-" * 40)
    for name in ("system", "tools", "history", "rag"):
        status = "OK" if usage[name] <= BUDGET[name] else "초과!"
        print(f"{name:<10} | {BUDGET[name]:>6} | {usage[name]:>6} | {status}")
    print("-" * 40)
    print(f"{'합계':<10} | {sum(BUDGET.values()):>6} | {sum(usage.values()):>6} |")


# ---------------------------------------------------------------------------
# 3) 예산 집행(enforcement) — 섹션 성격에 맞는 축소 정책을 적용
# ---------------------------------------------------------------------------
def trim_history(history: list, budget: int) -> list:
    """오래된 턴부터 잘라 예산 안으로 — 최근 대화가 더 중요하다는 가정."""
    trimmed = list(history)
    # user/assistant 짝을 유지하기 위해 2개(1턴)씩 삭제, 최소 1턴은 보존
    while len(trimmed) > 2 and count_tokens(history_to_text(trimmed)) > budget:
        trimmed = trimmed[2:]
    return trimmed


def shrink_rag(rag: str, budget: int) -> tuple:
    """RAG 결과 축소: 키가 있으면 LLM 요약, 없으면 단순 절삭. (결과, 방법) 반환."""
    if _client is not None:
        # LLM 요약 — 숫자·문서 ID 같은 정확성이 중요한 값은 원문 유지 지시
        # 최신 Opus 는 temperature 미지원(400) — 결정성이 필요하면 프롬프트로 제어
        resp = _client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system="검색 결과를 요약해라. 문서 ID와 숫자는 원문 그대로 보존하고, "
            "중복되는 조항은 하나로 합쳐라.",
            messages=[{"role": "user", "content": rag}],
        )
        summary = "".join(b.text for b in resp.content if b.type == "text")
        return f"[요약된 검색 결과] {summary}", "LLM 요약"

    # 폴백: 앞부분만 남기는 단순 절삭 — 정보 손실이 크지만 키 없이 동작
    suffix = "\n...(예산 초과분 절삭됨)"
    # 근사 카운터(len/3.5)의 역산 — 접미사 길이와 오차 여유분을 미리 빼 둔다
    keep_chars = max(0, int(budget * 3.5) - len(suffix) - 40)
    return rag[:keep_chars] + suffix, "단순 절삭"


def enforce_budget(ctx: dict, usage: dict) -> dict:
    """초과 섹션에 축소 정책을 적용하고 로그를 남긴다."""
    print()
    if usage["history"] > BUDGET["history"]:
        before_len, before_tok = len(ctx["history"]), usage["history"]
        ctx["history"] = trim_history(ctx["history"], BUDGET["history"])
        after_tok = count_tokens(history_to_text(ctx["history"]))
        removed = (before_len - len(ctx["history"])) // 2
        print(f"[history] {before_tok} → {after_tok} 토큰 (오래된 {removed}턴 삭제)")

    if usage["rag"] > BUDGET["rag"]:
        before_tok = usage["rag"]
        ctx["rag"], how = shrink_rag(ctx["rag"], BUDGET["rag"])
        after_tok = count_tokens(ctx["rag"])
        print(f"[rag] {before_tok} → {after_tok} 토큰 ({how})")

    # system / tools 는 '불변 프리픽스'라 런타임에 줄이지 않는다 (캐시 보호).
    # 이 섹션이 초과라면 코드를 고칠 일이지, 실행 중 자를 일이 아니다.
    for name in ("system", "tools"):
        if usage[name] > BUDGET[name]:
            print(f"[{name}] 예산 초과 — 런타임 축소 대신 프롬프트/도구 수 재설계 필요")

    return ctx


def main() -> None:
    counter = "count_tokens API" if _client is not None else "로컬 근사 (len/3.5)"
    print(f"토큰 카운터: {counter}")

    ctx = build_fake_context()

    usage = measure(ctx)
    print_table(usage, "예산 집행 전")

    ctx = enforce_budget(ctx, usage)

    usage_after = measure(ctx)
    print_table(usage_after, "예산 집행 후")

    print("\n요점: 컨텍스트는 한 덩어리가 아니라 섹션별 예산이다.")
    print("      섹션마다 성격이 다르므로 축소 정책도 다르다 —")
    print("      히스토리는 트리밍, RAG는 요약/절삭, 시스템·도구는 불변(캐시 보호).")


if __name__ == "__main__":
    main()
