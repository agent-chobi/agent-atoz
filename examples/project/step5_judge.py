"""
step5_judge.py — [캡스톤 Step 5] LLM judge 평가 + 재작성 루프 (docs/22-capstone-project.md)

Step 2 의 리서치 팀이 만든 보고서를, 팀과 "완전히 분리된" judge 프롬프트(15장)로
1~5점 채점한다. 점수가 임계값(4점) 미만이면 judge 의 피드백을 팀에 돌려보내
1회 재작성시킨다 — 생성과 평가의 분리(critique 패턴, 09장) + 반복 상한.

- judge 는 anthropic SDK 를 직접 쓰고 output_config(JSON 스키마)로 구조화 출력을 강제한다.
- 자기채점(self-scoring)은 후하게 나오므로, judge 에게 "채점자" 역할을 명시한다.

[실행법]
  pip install -r requirements.txt
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/project/step5_judge.py

[기대 출력 예시]
  === Step 5: LLM judge 평가 ===
  --- 1) 팀이 보고서 생성 ---
  [도구 호출] web_search(query='...')
  [보고서] 2026년 프로덕션 멀티에이전트의 다수는 supervisor 패턴을 ...

  --- 2) 별도 judge 가 채점 ---
  점수: 5 / 5
  근거: 토큰 오버헤드 수치와 채택률을 정확히 인용했고 ...
  판정: PASS ✅ (임계값 4점)

[흔한 에러]
  - json.JSONDecodeError → output_config 를 지원하는 최신 anthropic SDK 인지 확인 (pip install -U anthropic)
  - 점수가 매번 5점 → judge 프롬프트에 "후하게 주지 마라"와 구체적 rubric 이 있는지 확인
  - 재작성이 무한 반복 → MAX_REVISIONS 상한이 있는지 확인 (이 예제는 1회)
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 출력이 깨지지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

# Step 2 의 팀 빌더를 그대로 재사용 (누적 확장)
from step2_supervisor import build_team  # noqa: E402

# 기본은 가장 강력한 Opus. 비용을 아끼려면 아래 한 줄로 교체:
# MODEL = "claude-haiku-4-5"   # 빠르고 저렴 (반복 채점용 judge 에 특히 적합)
MODEL = "claude-opus-4-8"

PASS_SCORE = 4      # 이 점수 이상이면 합격
MAX_REVISIONS = 1   # 재작성 상한 — 없으면 무한 왕복·비용 폭증 (09장 안티패턴)

# judge 출력을 항상 파싱 가능한 JSON 으로 강제하는 스키마 (15장, 21번 예제와 동일 기법)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "enum": [1, 2, 3, 4, 5],
            "description": "1(매우 나쁨)~5(매우 좋음) 점수",
        },
        "reasoning": {"type": "string", "description": "점수 근거 (한국어 2~3문장)"},
        "feedback": {"type": "string", "description": "점수를 올리기 위한 구체적 수정 지시 1가지"},
    },
    "required": ["score", "reasoning", "feedback"],
    "additionalProperties": False,
}

RUBRIC = (
    "- accuracy: 토큰 오버헤드(+285%/+58%)나 채택률(~70%) 같은 구체 수치를 근거로 인용할 것\n"
    "- relevance: 'supervisor 가 왜 기본값인가'라는 질문에 직접 답할 것\n"
    "- conciseness: 한 단락, 군더더기 없이"
)


def judge_report(client, report: str) -> dict:
    """팀과 분리된 judge 프롬프트로 보고서를 채점한다. (생성/평가 분리)"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=(
            "너는 엄격한 채점자(evaluator)다. 답을 새로 쓰지 않는다. "
            "주어진 [평가 기준]에 비추어 [보고서]를 채점하고, 후하게 주지 마라."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"[평가 기준]\n{RUBRIC}\n\n[보고서]\n{report}\n\n"
                    "1~5점 점수, 근거, 수정 지시를 JSON 으로 반환하라."
                ),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def main() -> None:
    # API 키 가드: 클라이언트 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    import anthropic
    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(model=MODEL)
    team = build_team(model)                # 생성자: Step 2 리서치 팀
    judge_client = anthropic.Anthropic()    # 평가자: 별도 클라이언트·별도 프롬프트

    task = "supervisor 패턴이 2026년 기본값인 이유를 구체 수치를 들어 한 단락 보고서로 써줘."

    print("=== Step 5: LLM judge 평가 ===")
    print("\n--- 1) 팀이 보고서 생성 ---")
    result = team.invoke({"messages": [("user", task)]})
    report = result["messages"][-1].content
    print(f"[보고서] {report}")

    # 채점 → (미달이면) 피드백 반영 재작성 → 재채점. 상한 MAX_REVISIONS 회.
    for attempt in range(MAX_REVISIONS + 1):
        print(f"\n--- 2) 별도 judge 가 채점 (시도 {attempt + 1}) ---")
        verdict = judge_report(judge_client, report)
        print(f"점수: {verdict['score']} / 5")
        print(f"근거: {verdict['reasoning']}")

        if verdict["score"] >= PASS_SCORE:
            print(f"판정: PASS ✅ (임계값 {PASS_SCORE}점)")
            break

        if attempt >= MAX_REVISIONS:
            print(f"판정: FAIL ❌ — 재작성 상한({MAX_REVISIONS}회) 도달, 사람 검토로 에스컬레이션")
            break

        # judge 피드백을 팀에 돌려보내 재작성 (critique 루프)
        print(f"판정: 미달 — 피드백으로 재작성 요청: {verdict['feedback']}")
        result = team.invoke(
            {
                "messages": [
                    ("user", f"{task}\n\n[검수 피드백 — 반드시 반영]\n{verdict['feedback']}")
                ]
            }
        )
        report = result["messages"][-1].content
        print(f"[재작성 보고서] {report}")


if __name__ == "__main__":
    main()
