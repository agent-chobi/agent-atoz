"""
22_harness.py — 캡스톤: 계획→생성→평가 3-에이전트 미니 하네스 (17장)

하네스 엔지니어링의 핵심을 최소 코드로 시연한다.
  1) 계획(Planner)  — 무엇을, 어떤 기준으로 만들지 계획한다.
  2) 생성(Builder)  — 계획을 보고 결과물을 만든다(또는 피드백을 받아 고친다).
  3) 평가(Evaluator)— 결과물을 '별도 프롬프트'로 채점한다(생성≠평가 분리).

세 역할은 **서로 다른 프롬프트/역할**을 갖는다. 특히 평가자는 생성자와
분리되어야 자기채점 편향(후한 점수)을 피할 수 있다.

또한 **핸드오프 파일**(examples/_scratch_progress.md — 환경변수 HARNESS_PROGRESS 로
변경 가능)에 각 반복의 진행 상황을 기록한다. 실전에서는 긴 작업 시 컨텍스트를
완전히 리셋하고 이 압축 파일만 읽혀 새 세션을 시작한다(compaction만으로는 부족).
여기서는 그 패턴의 축소판으로, 매 반복마다 진행 파일을 갱신한다.

루프: 평가가 통과(threshold 이상)하거나 최대 반복 횟수에 도달하면 종료.

실행법
------
  pip install anthropic python-dotenv
  # .env 에 ANTHROPIC_API_KEY=sk-ant-...
  python examples/22_harness.py

[기대 출력 예시] (결과물·점수는 실행마다 다르며, 보통 반복 1~2회 안에 통과)
  ======================================================================
  계획 단계
  ======================================================================
  1. 캐싱의 핵심 원리를 한 문장으로 정의 ... (판정 기준 포함 계획)

  ======================================================================
  반복 1: 생성 → 평가
  ======================================================================
  [결과물]
  프롬프트 캐싱은 자주 쓰는 서두를 미리 계산해 두는 것으로, 카페의 ...
  [평가] 점수 4/5 — 비유와 무효화 조건을 모두 충족했다.

  통과 ✅ (임계값 4점) — 반복 1에서 종료
  진행/핸드오프 파일: <프로젝트 경로>/examples/_scratch_progress.md

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 파일 확인
  - ModuleNotFoundError: No module named 'anthropic' → pip install anthropic python-dotenv
  - PermissionError(_scratch_progress.md 쓰기 실패): 폴더 쓰기 권한 없음
    → 환경변수 HARNESS_PROGRESS 로 쓰기 가능한 경로 지정
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
import anthropic

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경

client = anthropic.Anthropic()

# 진행/핸드오프 파일 경로 (기본: 이 파일 옆 examples/_scratch_progress.md, HARNESS_PROGRESS 로 변경 가능)
PROGRESS_PATH = Path(
    os.environ.get("HARNESS_PROGRESS", Path(__file__).parent / "_scratch_progress.md")
)

MAX_ITERS = 3          # 최대 반복 횟수
PASS_THRESHOLD = 4     # 평가 통과 점수(1~5)


# ---------------------------------------------------------------------------
# 핸드오프(진행) 파일 유틸
# ---------------------------------------------------------------------------
def write_progress(task: str, plan: str, history: list[dict]) -> None:
    """진행 상황을 마크다운 파일로 기록한다. (컨텍스트 리셋 시 이 파일만 읽힘)"""
    lines = [
        "# 하네스 진행 상황 (핸드오프 파일)",
        "",
        f"## 과제\n{task}",
        "",
        f"## 계획\n{plan}",
        "",
        "## 반복 이력",
    ]
    for i, h in enumerate(history, 1):
        lines.append(f"### 반복 {i}")
        lines.append(f"- 점수: {h['score']}/5")
        lines.append(f"- 평가 근거: {h['reasoning']}")
        lines.append(f"- 결과물(발췌): {h['draft'][:200]}...")
        lines.append("")
    PROGRESS_PATH.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1) 계획(Planner)
# ---------------------------------------------------------------------------
def plan(task: str) -> str:
    """무엇을 만들지, 어떤 기준으로 좋다고 볼지 계획을 세운다."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=(
            "너는 계획가(planner)다. 주어진 과제를 어떻게 해결할지 "
            "3~5개의 짧은 단계와, '좋은 결과물'의 판정 기준을 제시하라. "
            "직접 결과물을 쓰지는 말고 계획만 세워라."
        ),
        messages=[{"role": "user", "content": f"과제: {task}"}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# 2) 생성(Builder)
# ---------------------------------------------------------------------------
def build(task: str, plan_text: str, feedback: str | None) -> str:
    """계획(과 이전 평가 피드백)을 보고 결과물을 만든다."""
    user = f"과제: {task}\n\n계획:\n{plan_text}"
    if feedback:
        # 이전 반복의 평가 피드백을 반영해 개선한다.
        user += f"\n\n이전 결과물에 대한 평가 피드백(반드시 반영):\n{feedback}"

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=(
            "너는 생성가(builder)다. 계획과 피드백을 충실히 반영해 "
            "실제 결과물을 작성하라. 결과물만 출력하라(메타 설명 금지)."
        ),
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# 3) 평가(Evaluator) — 생성과 분리된 별도 프롬프트
# ---------------------------------------------------------------------------
EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "reasoning": {"type": "string", "description": "점수 근거(한국어)"},
        "feedback": {
            "type": "string",
            "description": "다음 반복에서 고칠 점(통과 시 빈 문자열 가능)",
        },
    },
    "required": ["score", "reasoning", "feedback"],
    "additionalProperties": False,
}


def evaluate(task: str, plan_text: str, draft: str) -> dict:
    """결과물을 별도 채점자로 평가한다. (자기채점 편향 회피)"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=(
            "너는 엄격한 평가자(evaluator)다. 결과물을 새로 쓰지 않는다. "
            "과제와 계획의 판정 기준에 비추어 [결과물]을 1~5점으로 채점하고, "
            "부족하면 구체적 개선 피드백을 남겨라. 후하게 주지 마라."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"[과제]\n{task}\n\n[계획]\n{plan_text}\n\n[결과물]\n{draft}\n\n"
                    "채점 결과를 JSON으로 반환하라."
                ),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": EVAL_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------------------
# 하네스 루프
# ---------------------------------------------------------------------------
def run_harness(task: str) -> None:
    print("=" * 70)
    print("계획 단계")
    print("=" * 70)
    plan_text = plan(task)
    print(plan_text)

    history: list[dict] = []
    feedback: str | None = None
    draft = ""

    for it in range(1, MAX_ITERS + 1):
        print("\n" + "=" * 70)
        print(f"반복 {it}: 생성 → 평가")
        print("=" * 70)

        # 생성
        draft = build(task, plan_text, feedback)
        print("[결과물]\n" + draft[:500] + ("..." if len(draft) > 500 else ""))

        # 평가 (생성과 분리된 별도 채점자)
        verdict = evaluate(task, plan_text, draft)
        print(f"\n[평가] 점수 {verdict['score']}/5 — {verdict['reasoning']}")

        history.append(
            {
                "score": verdict["score"],
                "reasoning": verdict["reasoning"],
                "draft": draft,
            }
        )
        # 매 반복마다 핸드오프 파일 갱신 (컨텍스트 리셋 대비)
        write_progress(task, plan_text, history)

        if verdict["score"] >= PASS_THRESHOLD:
            print(f"\n통과 ✅ (임계값 {PASS_THRESHOLD}점) — 반복 {it}에서 종료")
            break

        # 통과 못하면 피드백을 다음 생성에 반영
        feedback = verdict["feedback"]
        print(f"[피드백→다음 반복] {feedback}")
    else:
        print(f"\n최대 반복({MAX_ITERS}) 도달 — 마지막 결과물로 종료")

    print(f"\n진행/핸드오프 파일: {PROGRESS_PATH}")


def main() -> None:
    task = (
        "초급 개발자에게 '프롬프트 캐싱'을 설명하는 4~6문장짜리 문단을 써라. "
        "비유 하나를 포함하고, 언제 캐싱이 무효화되는지도 한 문장으로 언급할 것."
    )
    run_harness(task)


if __name__ == "__main__":
    main()
