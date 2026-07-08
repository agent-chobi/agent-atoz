"""
21_llm_judge.py — LLM-as-judge: 생성과 평가의 분리 시연 (15장)

핵심 아이디어
-------------
에이전트의 출력 품질을 자동으로 채점할 때, **생성한 그 모델/프롬프트로
스스로 채점하게 하면 점수가 후하게 나온다(self-scoring bias)**.
따라서 "생성 프롬프트"와 "평가(judge) 프롬프트"를 **완전히 분리**한다.

이 예제는 두 단계를 보여준다.
  1) 생성(generation): 사용자 질문에 대한 답변을 만든다.
  2) 평가(judge): 그 답변만 따로 떼어, 별도의 judge 프롬프트로
     1~5점 점수 + 근거를 구조화된 JSON으로 받는다.

judge는 원래 질문·정답 기준(rubric)을 받되, "생성자가 아니라 채점자"라는
역할을 명확히 부여받는다.

실행법
------
  # 1) 의존성
  pip install anthropic python-dotenv
  # 2) .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  # 3) 실행
  python examples/21_llm_judge.py

[기대 출력 예시] (답변·점수는 실행마다 다르며 대략 이런 형태)
  ======================================================================
  1) 생성 단계
  ======================================================================
  프롬프트 캐싱은 반복되는 프리픽스(시스템 프롬프트 등)를 서버에 저장해 ...

  ======================================================================
  2) 평가 단계 (별도 judge 프롬프트)
  ======================================================================
  점수: 5 / 5
  근거: 캐시 재사용으로 입력 토큰 비용이 줄어드는 원리를 정확히 설명했다. ...
  세부: {'accuracy': True, 'relevance': True, 'conciseness': True}

  판정: PASS ✅ (임계값 4점)

[흔한 에러]
  - authentication_error (401): ANTHROPIC_API_KEY 미설정 → .env 파일 확인
  - ModuleNotFoundError: No module named 'anthropic' → pip install anthropic python-dotenv
  - json.JSONDecodeError: output_config 미지원 구형 SDK → pip install -U anthropic
"""

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
import anthropic

# .env 에서 ANTHROPIC_API_KEY 로드
load_dotenv()

MODEL = "claude-haiku-4-5"  # 고성능 필요 시: "claude-opus-4-8" 로 변경

client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# 1) 생성(generation) — 답변을 만드는 에이전트
# ---------------------------------------------------------------------------
def generate_answer(question: str) -> str:
    """사용자 질문에 대한 답변을 생성한다. (평가와 무관한, 순수 생성 단계)"""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=(
            "너는 사용자의 질문에 정확하고 간결하게 답하는 도우미다. "
            "핵심만 3~5문장으로 답하라."
        ),
        messages=[{"role": "user", "content": question}],
    )
    # 텍스트 블록만 뽑아 문자열로 합친다.
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# 2) 평가(judge) — 답변을 채점하는 "별도" 프롬프트
# ---------------------------------------------------------------------------
# judge 응답을 구조화하기 위한 JSON 스키마.
# output_config.format 로 강제하면 항상 파싱 가능한 JSON이 돌아온다.
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            # enum 으로 1~5 정수만 허용
            "enum": [1, 2, 3, 4, 5],
            "description": "1(매우 나쁨)~5(매우 좋음) 점수",
        },
        "reasoning": {
            "type": "string",
            "description": "점수를 준 근거 (한국어, 2~3문장)",
        },
        "criteria": {
            "type": "object",
            "properties": {
                "accuracy": {"type": "boolean", "description": "사실적으로 정확한가"},
                "relevance": {"type": "boolean", "description": "질문에 직접 답했는가"},
                "conciseness": {"type": "boolean", "description": "불필요한 군더더기가 없는가"},
            },
            "required": ["accuracy", "relevance", "conciseness"],
            "additionalProperties": False,
        },
    },
    "required": ["score", "reasoning", "criteria"],
    "additionalProperties": False,
}


def judge_answer(question: str, answer: str, rubric: str) -> dict:
    """생성된 답변을 '별도의 judge 프롬프트'로 채점한다.

    핵심: 생성 단계와 프롬프트/역할을 분리한다. judge는 "채점자"이며,
    자기가 만든 답이 아니라 '주어진 답'을 냉정하게 평가한다.
    """
    judge_system = (
        "너는 엄격한 채점자(evaluator)다. 너는 답을 새로 쓰지 않는다. "
        "아래에 주어진 [질문]과 [평가 기준]에 비추어 [답변]을 채점한다. "
        "후하게 주지 말고, 기준을 충족하지 못하면 과감히 낮은 점수를 매겨라."
    )
    judge_user = (
        f"[질문]\n{question}\n\n"
        f"[평가 기준]\n{rubric}\n\n"
        f"[답변]\n{answer}\n\n"
        "위 답변을 1~5점으로 채점하고, 근거와 세부 기준 충족 여부를 JSON으로 반환하라."
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=judge_system,
        messages=[{"role": "user", "content": judge_user}],
        # 구조화된 출력 강제 → 항상 파싱 가능한 JSON
        output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


# ---------------------------------------------------------------------------
# 데모
# ---------------------------------------------------------------------------
def main() -> None:
    question = "프롬프트 캐싱은 왜 비용을 줄여 주나? 한 문단으로 설명해줘."
    rubric = (
        "- accuracy: 캐시된 프리픽스를 재처리하지 않아 입력 토큰 비용이 대폭 준다는 점을 언급\n"
        "- relevance: 질문(비용 절감 이유)에 직접 답할 것\n"
        "- conciseness: 한 문단, 군더더기 없이"
    )

    print("=" * 70)
    print("1) 생성 단계")
    print("=" * 70)
    answer = generate_answer(question)
    print(answer)

    print("\n" + "=" * 70)
    print("2) 평가 단계 (별도 judge 프롬프트)")
    print("=" * 70)
    verdict = judge_answer(question, answer, rubric)
    print(f"점수: {verdict['score']} / 5")
    print(f"근거: {verdict['reasoning']}")
    print(f"세부: {verdict['criteria']}")

    # 통과 기준 예시: 4점 이상이면 합격으로 취급
    passed = verdict["score"] >= 4
    print(f"\n판정: {'PASS ✅' if passed else 'FAIL ❌'} (임계값 4점)")


if __name__ == "__main__":
    main()
