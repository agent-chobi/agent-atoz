"""
step3_checkpoint.py — [캡스톤 Step 3] 체크포인터로 중단/재개 (docs/22-capstone-project.md)

Step 2 의 리서치 팀에 SqliteSaver 체크포인터(06장)를 붙인다.
- 같은 thread_id 로 다시 invoke 하면 팀이 이전 대화(보고서)를 기억한다.
- 상태가 파일(research_team.sqlite)에 저장되므로, 스크립트를 껐다 켜도
  같은 thread 에서 대화가 "재개"된다 — 이것이 중단/재개의 본질이다.

build_team(model, checkpointer=...) 한 줄만 바뀐다. Step 2 코드는 그대로 재사용.

[실행법]
  pip install -r requirements.txt   # langgraph-checkpoint-sqlite 포함
  # .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
  python examples/project/step3_checkpoint.py
  # 다시 실행하면 같은 thread 가 이어진다. 기억을 지우려면 research_team.sqlite 삭제.

[기대 출력 예시]
  === Step 3: 체크포인터로 중단/재개 ===
  --- 턴 1: 보고서 작성 ---
  [도구 호출] web_search(query='...')
  [답변] 2026년 프로덕션 멀티에이전트의 다수는 supervisor 패턴을 ...

  --- 턴 2: 같은 thread 에서 후속 질문 (이전 보고서를 기억) ---
  [답변] 방금 보고서의 핵심은 두 가지입니다. 첫째, ...

  --- 현재 스냅샷 ---
  thread='capstone-team' 저장된 메시지 수: 14, 다음 노드: ()

[흔한 에러]
  - ImportError: langgraph.checkpoint.sqlite → pip install langgraph-checkpoint-sqlite
  - 턴 2가 보고서를 기억 못함 → 두 invoke 의 thread_id 가 같은지 확인
  - 재실행마다 답이 길어짐 → 같은 thread 에 히스토리가 누적되는 정상 동작.
    초기화하려면 research_team.sqlite 를 지우거나 thread_id 를 바꿀 것
"""

from __future__ import annotations

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
# MODEL = "claude-haiku-4-5"   # 빠르고 저렴
MODEL = "claude-opus-4-8"

DB_PATH = "research_team.sqlite"  # 체크포인트 저장 파일 (지우면 기억 초기화)
THREAD_ID = "capstone-team"       # "이 대화"의 열쇠 — 같으면 상태가 이어진다


def main() -> None:
    # API 키 가드: 모델(클라이언트) 생성보다 먼저
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY 가 없습니다. .env 를 확인하세요.")

    from langchain_anthropic import ChatAnthropic
    from langgraph.checkpoint.sqlite import SqliteSaver

    model = ChatAnthropic(model=MODEL)

    # SqliteSaver 는 컨텍스트 매니저로 열어 파일 커넥션을 관리한다.
    with SqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        # Step 2 와의 차이는 이 한 줄: checkpointer 를 붙여 컴파일
        team = build_team(model, checkpointer=checkpointer)
        config = {"configurable": {"thread_id": THREAD_ID}}

        print("=== Step 3: 체크포인터로 중단/재개 ===")

        print("\n--- 턴 1: 보고서 작성 ---")
        r1 = team.invoke(
            {"messages": [("user", "supervisor 패턴이 왜 기본값인지 한 단락 보고서로 써줘.")]},
            config,
        )
        print("[답변]")
        print(r1["messages"][-1].content)

        # 여기서 프로세스가 죽어도(=중단) 상태는 sqlite 에 남아 있다.
        # 같은 thread_id 로 다시 invoke 하는 것이 곧 "재개"다.
        print("\n--- 턴 2: 같은 thread 에서 후속 질문 (이전 보고서를 기억) ---")
        r2 = team.invoke(
            {"messages": [("user", "방금 그 보고서의 핵심만 두 문장으로 요약해줘.")]},
            config,
        )
        print("[답변]")
        print(r2["messages"][-1].content)

        # 현재 스냅샷 확인: 무엇이 저장되어 있나 (06장 get_state)
        snap = team.get_state(config)
        print("\n--- 현재 스냅샷 ---")
        print(
            f"thread={THREAD_ID!r} 저장된 메시지 수: {len(snap.values['messages'])}, "
            f"다음 노드: {snap.next}"
        )
        print(f"(스크립트를 다시 실행하면 이 지점에서 이어집니다. 초기화: {DB_PATH} 삭제)")


if __name__ == "__main__":
    main()
