"""
step4_hitl.py — [캡스톤 Step 4] HITL 승인 게이트 (docs/22-capstone-project.md)

Step 2 의 리서치 팀을 상위 StateGraph 의 한 노드로 감싸고, 팀이 만든 보고서를
"게시(publish)"하기 전에 사람 승인을 받는 HITL 게이트(14장)를 끼운다.

  research_team(팀 실행) → approval(interrupt 로 정지) → publish(승인 시에만 게시)

- interrupt() 는 그래프를 그 자리에서 멈추고 상태를 체크포인터에 저장한다.
- 사람의 결정은 Command(resume="yes"/"no") 로 같은 thread_id 에 넣어 재개한다.
- 데모는 자동으로 "yes" 를 넣는다. 거부 분기를 보려면 --reject, 직접 입력은 --interactive.

[실행법]
  pip install -r requirements.txt
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/project/step4_hitl.py               # 자동 승인 데모
  python examples/project/step4_hitl.py --reject      # 자동 거부 데모
  python examples/project/step4_hitl.py --interactive # 콘솔에서 직접 y/n 입력

[기대 출력 예시]
  === Step 4: HITL 승인 게이트 ===
  --- 1) 팀 실행 → 승인 게이트에서 정지 ---
  [도구 호출] web_search(query='...')
  [승인 요청] 이 보고서를 게시할까요?
  [보고서 초안] 2026년 프로덕션 멀티에이전트의 다수는 supervisor 패턴 ...

  --- 2) 사람 결정 'yes' 로 재개 ---
  [결과] 보고서 게시 완료 ✅

[흔한 에러]
  - interrupt 관련 에러 → 체크포인터 없이 compile 하면 동작하지 않음 (필수)
  - 재개해도 멈춘 지점으로 안 돌아감 → 최초 invoke 와 resume 의 thread_id 가 같아야 함
  - '__interrupt__' KeyError → interrupt 에 도달하기 전에 그래프가 끝난 것. 엣지 연결 확인
"""

from __future__ import annotations

import os
import sys
from typing import TypedDict

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
# MODEL = "claude-haiku-4-5"   # 빠르고 저렴
MODEL = "claude-opus-4-8"


class ReviewState(TypedDict):
    """상위 그래프의 상태: 주제 → 초안 → 승인 여부 → 최종 결과."""

    topic: str
    draft: str
    approved: bool
    result: str


def build_reviewed_pipeline(model):
    """리서치 팀 → 사람 승인 → 게시, 3단계 상위 그래프를 컴파일해 반환한다."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import interrupt

    team = build_team(model)  # Step 2 의 supervisor 팀이 통째로 한 노드가 된다

    def research_team_node(state: ReviewState) -> dict:
        """리서치 팀을 돌려 보고서 초안을 만든다."""
        result = team.invoke(
            {"messages": [("user", f"{state['topic']} 에 대해 한 단락 보고서를 써줘.")]}
        )
        return {"draft": result["messages"][-1].content}

    def approval_node(state: ReviewState) -> dict:
        """승인 게이트: interrupt 로 정지하고 사람의 판단을 기다린다 (14장)."""
        decision = interrupt(
            {"question": "이 보고서를 게시할까요?", "draft": state["draft"]}
        )
        return {"approved": decision == "yes"}

    def publish_node(state: ReviewState) -> dict:
        """승인됐을 때만 게시한다. 거부되면 초안을 버린다."""
        if state["approved"]:
            return {"result": "보고서 게시 완료 ✅"}
        return {"result": "게시 반려 — 초안을 폐기했습니다 ❌"}

    builder = StateGraph(ReviewState)
    builder.add_node("research_team", research_team_node)
    builder.add_node("approval", approval_node)
    builder.add_node("publish", publish_node)
    builder.add_edge(START, "research_team")
    builder.add_edge("research_team", "approval")
    builder.add_edge("approval", "publish")
    builder.add_edge("publish", END)

    # ⚠️ interrupt 는 정지 상태를 저장할 체크포인터가 반드시 필요하다 (Step 3 개념 재사용)
    return builder.compile(checkpointer=InMemorySaver())


def main() -> None:
    # API 키 가드: 모델(클라이언트) 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    from langchain_anthropic import ChatAnthropic
    from langgraph.types import Command

    model = ChatAnthropic(model=MODEL)
    pipeline = build_reviewed_pipeline(model)
    config = {"configurable": {"thread_id": "capstone-review-1"}}

    print("=== Step 4: HITL 승인 게이트 ===")
    print("\n--- 1) 팀 실행 → 승인 게이트에서 정지 ---")
    state = pipeline.invoke(
        {
            "topic": "supervisor 패턴이 2026년 기본값인 이유",
            "draft": "",
            "approved": False,
            "result": "",
        },
        config=config,
    )

    # interrupt 에 넘긴 payload 가 '__interrupt__' 로 노출된다
    payload = state["__interrupt__"][0].value
    print(f"\n[승인 요청] {payload['question']}")
    print(f"[보고서 초안] {payload['draft'][:200]}...")

    # 사람의 결정: 자동 데모(yes/no) 또는 콘솔 입력
    if "--interactive" in sys.argv:
        ans = input("\n게시를 승인하시겠습니까? [y/N] ").strip().lower()
        decision = "yes" if ans in ("y", "yes") else "no"
    else:
        decision = "no" if "--reject" in sys.argv else "yes"

    print(f"\n--- 2) 사람 결정 {decision!r} 로 재개 ---")
    # 같은 thread_id 로 Command(resume=...) → 멈춘 approval 노드부터 이어서 실행
    final = pipeline.invoke(Command(resume=decision), config=config)
    print(f"[결과] {final['result']}")


if __name__ == "__main__":
    main()
