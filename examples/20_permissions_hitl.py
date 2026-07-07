"""
20_permissions_hitl.py — 위험 도구 실행 전 사람 승인(HITL) 게이트

[문서] docs/14-permissions-security-hitl.md

에이전트가 파일을 지우거나(delete_file) 돈을 보내는(send_money) 등
"부수효과가 크고 비가역적인" 도구를 부를 때는, 실행 **직전에** 정책으로 분류하고
필요하면 사람의 승인을 받아야 합니다.

핵심 개념
  - 최소권한(least privilege): 도구별 위험도를 정책으로 선언(allow / deny / ask).
  - HITL 승인 게이트: 위험(ask) 도구는 사람이 approve/reject 할 때까지 실행 보류.
  - 이 예제의 `policy_gate()` 는 LangGraph `interrupt()` 승인 패턴의 순수 파이썬 축약형입니다.
    (LangGraph 버전은 docs/14 및 04장 참고: interrupt() → Command(resume=...))

────────────────────────────────────────────────────────────────────
[실행법]
  pip install python-dotenv        # (LLM 호출은 없어 anthropic 불필요)
  python examples/20_permissions_hitl.py

  기본은 데모용 자동 응답 시나리오로 approve/reject 분기를 모두 보여줍니다.
  실제 콘솔 입력으로 승인받으려면:  python examples/20_permissions_hitl.py --interactive
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 이모지/em-dash가 깨지지 않도록 UTF-8 출력 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
except Exception:
    pass

load_dotenv()

MODEL = "claude-opus-4-8"  # 이 데모는 LLM을 호출하지 않지만 규칙상 명시 (haiku: "claude-haiku-4-5")


# ── 1. 도구 정책 (최소권한 선언) ────────────────────────────────────
class Decision(str, Enum):
    ALLOW = "allow"   # 즉시 실행
    ASK = "ask"       # 사람 승인 필요(HITL)
    DENY = "deny"     # 무조건 거부


# 도구 이름 → 위험도 정책.
# 기본은 "명시되지 않은 도구는 거부"(deny-by-default) 로 운용한다.
TOOL_POLICY: dict[str, Decision] = {
    "read_file": Decision.ALLOW,     # 읽기 전용 → 허용
    "list_dir": Decision.ALLOW,
    "delete_file": Decision.ASK,     # 비가역 → 승인 필요
    "send_money": Decision.ASK,      # 금전 이동 → 승인 필요
    "deploy_prod": Decision.ASK,     # 프로덕션 영향 → 승인 필요
    "exec_shell": Decision.DENY,     # 임의 코드 실행 → 차단
}


def classify(tool_name: str) -> Decision:
    """정책 조회. 미등록 도구는 기본 거부."""
    return TOOL_POLICY.get(tool_name, Decision.DENY)


# ── 2. 승인자(approver) 인터페이스 ─────────────────────────────────
# 데모 자동 응답 / 실제 콘솔 입력을 바꿔 낄 수 있도록 함수로 주입.
Approver = Callable[[str, dict], bool]  # (tool_name, args) -> approved?


def console_approver(tool_name: str, args: dict) -> bool:
    """실제 사람이 콘솔에서 y/n 으로 승인."""
    print(f"  ⚠️  승인 요청: {tool_name}({args})")
    ans = input("      실행을 승인하시겠습니까? [y/N] ").strip().lower()
    return ans in ("y", "yes")


def make_scripted_approver(answers: dict[str, bool]) -> Approver:
    """데모용: 도구 이름별로 미리 정한 승인 여부를 반환."""

    def _approver(tool_name: str, args: dict) -> bool:
        decision = answers.get(tool_name, False)
        mark = "승인" if decision else "거부"
        print(f"  ⚠️  승인 요청: {tool_name}({args})  → [사람: {mark}]")
        return decision

    return _approver


# ── 3. 도구 구현 (실제로는 부수효과가 나는 코드) ────────────────────
def tool_read_file(path: str) -> str:
    return f"(demo) '{path}' 내용을 읽었습니다."


def tool_delete_file(path: str) -> str:
    return f"(demo) '{path}' 를 삭제했습니다. ← 비가역!"


def tool_send_money(to: str, amount: int) -> str:
    return f"(demo) {to} 에게 {amount}원을 송금했습니다. ← 금전 이동!"


TOOL_IMPL: dict[str, Callable[..., str]] = {
    "read_file": lambda args: tool_read_file(**args),
    "delete_file": lambda args: tool_delete_file(**args),
    "send_money": lambda args: tool_send_money(**args),
}


# ── 4. 게이트: 정책 분류 → (필요 시) 승인 → 실행 ───────────────────
@dataclass
class GateResult:
    executed: bool
    output: str


def policy_gate(tool_name: str, args: dict, approver: Approver) -> GateResult:
    """
    도구 실행 전 게이트.
      allow → 즉시 실행
      ask   → 사람 승인(approver) 통과 시에만 실행 (LangGraph interrupt 승인 지점에 대응)
      deny  → 실행 거부
    """
    decision = classify(tool_name)
    print(f"→ 도구 요청: {tool_name}  |  정책: {decision.value}")

    if decision is Decision.DENY:
        return GateResult(False, f"거부됨(정책): {tool_name} 은 금지된 도구입니다.")

    if decision is Decision.ASK:
        # ── HITL 승인 게이트 ─────────────────────────────
        approved = approver(tool_name, args)
        if not approved:
            return GateResult(False, f"거부됨(사람): {tool_name} 실행이 취소되었습니다.")

    # allow 또는 승인된 ask → 실행
    impl = TOOL_IMPL.get(tool_name)
    if impl is None:
        return GateResult(False, f"거부됨: {tool_name} 구현이 없습니다.")
    return GateResult(True, impl(args))


# ── 5. 시연 ─────────────────────────────────────────────────────────
def run_demo(approver: Approver) -> None:
    # 에이전트가 순차적으로 제안한 도구 호출이라고 가정
    proposed_calls = [
        ("read_file", {"path": "notes.txt"}),                 # allow
        ("delete_file", {"path": "prod.db"}),                 # ask
        ("send_money", {"to": "vendor-42", "amount": 100000}),  # ask
        ("exec_shell", {"cmd": "rm -rf /"}),                  # deny
    ]

    for name, args in proposed_calls:
        result = policy_gate(name, args, approver)
        status = "✅ 실행" if result.executed else "⛔ 차단"
        print(f"   {status}: {result.output}\n")


def main() -> None:
    print("=" * 64)
    print("20_permissions_hitl.py — 위험 도구 HITL 승인 게이트")
    print("=" * 64)

    if "--interactive" in sys.argv:
        print("[모드] 대화형 — 콘솔에서 직접 승인하세요.\n")
        run_demo(console_approver)
        return

    # 데모: delete_file 은 거부, send_money 는 승인하는 시나리오
    print("[모드] 스크립트 데모 — delete_file 거부 / send_money 승인\n")
    scripted = make_scripted_approver(
        {"delete_file": False, "send_money": True}
    )
    run_demo(scripted)

    print("-" * 64)
    print("요약:")
    print("  read_file  → 정책 allow  → 즉시 실행")
    print("  delete_file→ 정책 ask    → 사람이 거부 → 차단")
    print("  send_money → 정책 ask    → 사람이 승인 → 실행")
    print("  exec_shell → 정책 deny   → 무조건 차단")
    print("\n프로덕션에서는 approver 를 LangGraph interrupt()/Command(resume=...) 나")
    print("MCP elicitation 으로 연결해 진짜 사람 승인을 받습니다. (docs/14 참고)")


if __name__ == "__main__":
    main()
