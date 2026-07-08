"""
32_a2a_langgraph.py — LangGraph 에이전트를 A2A 서버로 노출 + 클라이언트 호출 (docs/12-a2a-protocol.md 7.1절)

17·18번이 a2a-sdk 의 최소 골격(LLM 없음)이었다면, 이 예제는 **진짜 에이전트**를 감싼다:
  - LangGraph create_react_agent(도구 1개: 환율 조회) 를 만들고,
  - AgentExecutor 어댑터 안에서 graph.ainvoke() 를 호출한 뒤,
  - 결과를 TaskUpdater 로 A2A task 상태(working → completed) + artifact 로 변환한다.
    (공식 a2a-samples 의 LangGraph 환율 에이전트와 같은 패턴)
같은 파일의 --client 모드는 A2ACardResolver 로 카드를 발견하고 message/send 를 보낸다.

핵심 개념:
  - "프레임워크는 그대로, AgentExecutor 어댑터만 갈아끼운다" — 서버 골격은 17번과 동일
  - TaskUpdater: task 를 만들고(update_status) 산출물을 붙이고(add_artifact) 종결(complete)
  - 17·18의 응답이 "kind": "message" 였다면, 이 예제는 "kind": "task" 응답을 돌려준다

실행(터미널 2개 — 반드시 서버 먼저):
    pip install -r requirements.txt          # a2a-sdk, uvicorn, httpx, langgraph, langchain-anthropic
    copy .env.example .env                   # ANTHROPIC_API_KEY 채우기 (서버 모드가 LLM 호출)

    # 터미널 1: A2A 서버 모드 (기본, 포트 9998)
    python examples/32_a2a_langgraph.py
    # → Agent Card: http://localhost:9998/.well-known/agent-card.json

    # 터미널 2: 클라이언트 모드
    python examples/32_a2a_langgraph.py --client

주의: a2a-sdk 는 2026년 시그니처가 자주 바뀝니다(0.3 → 1.0 에서 AgentCard 필드·클라이언트
      생성 방식이 변경됨). 아래는 17·18번과 같은 0.2.x/0.3.x 정석 패턴입니다. 설치 버전 대조 필요.

[기대 출력 예시] (클라이언트 쪽 — 문구는 실행마다 다르며 대략 이런 형태)
    === 발견한 Agent Card ===
    이름: LangGraph Exchange Agent
    스킬: ['환율 조회']

    === 서버 응답 (kind=task) ===
    상태: completed
    [artifact] result:
      1달러는 약 1,350원입니다. (데모 고정 환율 기준)

[흔한 에러]
    - httpx.ConnectError: Connection refused → 서버 모드를 먼저 별도 터미널에서 실행
    - SystemExit: ANTHROPIC_API_KEY 미설정 → .env 확인 (서버 모드만 키 필요)
    - ImportError: No module named 'a2a' → pip install -r requirements.txt (패키지명은 a2a-sdk)
    - pydantic ValidationError / ImportError(TaskUpdater 등): a2a-sdk 버전 불일치 → 설치 버전 대조
    - OSError: [WinError 10048] / address already in use: 9998 포트 사용 중 → 기존 프로세스 종료
"""

import argparse
import asyncio
import os
import sys
from uuid import uuid4

from dotenv import load_dotenv

# Windows 콘솔에서 한글 깨짐 방지
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경
HOST, PORT = "localhost", 9998  # 17번(9999)과 충돌하지 않게 별도 포트
BASE_URL = f"http://{HOST}:{PORT}"


# ==========================================================================
# 서버 쪽 ① — LangGraph 에이전트 (04장의 create_react_agent 그대로)
# ==========================================================================
def build_langgraph_agent():
    """도구 1개(환율 조회)를 가진 최소 ReAct 에이전트를 만든다."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent

    @tool
    def get_exchange_rate(base: str, target: str) -> str:
        """base 통화 → target 통화의 현재 환율을 반환한다. (예: base='USD', target='KRW')"""
        # 데모용 고정값 — 실전이라면 환율 API 호출 (공식 a2a-samples 는 Frankfurter API 사용)
        return f"1 {base.upper()} = 1,350 {target.upper()} (데모 고정값)"

    model = ChatAnthropic(model=MODEL, max_tokens=1024)
    return create_react_agent(model=model, tools=[get_exchange_rate])


# ==========================================================================
# 서버 쪽 ② — AgentExecutor 어댑터: LangGraph 결과 → A2A task/artifact
#   (docs/12 7.1절 = 공식 a2a-samples LangGraph 예제의 단순화판)
# ==========================================================================
def build_executor_class():
    """a2a-sdk import 를 함수 안에 두어, --client 모드에서는 서버 의존성을 건드리지 않는다."""
    from a2a.server.agent_execution import AgentExecutor, RequestContext
    from a2a.server.events import EventQueue
    from a2a.server.tasks import TaskUpdater
    from a2a.types import Part, TaskState, TextPart
    from a2a.utils import new_agent_text_message, new_task

    class LangGraphAgentExecutor(AgentExecutor):
        """LangGraph 그래프를 A2A 프로토콜에 연결하는 어댑터."""

        def __init__(self):
            self.graph = build_langgraph_agent()

        async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
            query = context.get_user_input()

            # 첫 호출이면 task 를 만들어 발행 (멀티턴이면 current_task 로 이어받는다)
            task = context.current_task
            if not task:
                task = new_task(context.message)
                await event_queue.enqueue_event(task)
            updater = TaskUpdater(event_queue, task.id, task.context_id)

            # 진행 상황 → status-update 이벤트 (스트리밍 클라이언트에는 SSE 로 발송)
            await updater.update_status(
                TaskState.working,
                new_agent_text_message("LangGraph 그래프 실행 중...", task.context_id, task.id),
            )

            # LangGraph 실행 — 마지막 AIMessage 가 최종 답
            result = await self.graph.ainvoke({"messages": [("user", query)]})
            answer = result["messages"][-1].content
            if isinstance(answer, list):  # content 가 블록 리스트인 경우 텍스트만 이어붙임
                answer = "".join(
                    b.get("text", "") for b in answer if isinstance(b, dict) and b.get("type") == "text"
                )

            # 최종 결과를 artifact 로 승격하고 task 종결 (AIMessage.content → TextPart)
            await updater.add_artifact([Part(root=TextPart(text=str(answer)))], name="result")
            await updater.complete()

        async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
            raise Exception("취소는 지원하지 않습니다.")

    return LangGraphAgentExecutor


# ==========================================================================
# 서버 모드 — Agent Card + 서버 골격 (17번과 동일한 조립, executor 만 교체)
# ==========================================================================
def run_server():
    # 키 가드 먼저: 서버 모드는 실제 LLM 을 호출한다
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY 가 없습니다. .env 파일을 확인하세요. (서버 모드는 LLM 호출)")

    import uvicorn
    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import AgentCapabilities, AgentCard, AgentSkill

    skill = AgentSkill(
        id="exchange-rate",
        name="환율 조회",
        description="통화쌍(예: USD→KRW)의 환율을 조회해 답한다.",
        tags=["currency", "langgraph", "demo"],
        examples=["1달러는 몇 원이야?", "USD to KRW"],
    )
    agent_card = AgentCard(
        name="LangGraph Exchange Agent",
        description="LangGraph ReAct 에이전트를 A2A 로 노출한 데모",
        url=f"{BASE_URL}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    executor_cls = build_executor_class()
    handler = DefaultRequestHandler(agent_executor=executor_cls(), task_store=InMemoryTaskStore())
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()

    print(f"A2A 서버 시작: {BASE_URL}")
    print(f"Agent Card: {BASE_URL}/.well-known/agent-card.json")
    print("다른 터미널에서:  python examples/32_a2a_langgraph.py --client")
    uvicorn.run(app, host="0.0.0.0", port=PORT)


# ==========================================================================
# 클라이언트 모드 — 발견(A2ACardResolver) → message/send → task 응답 해석
# ==========================================================================
async def run_client():
    import httpx
    from a2a.client import A2ACardResolver, A2AClient
    from a2a.types import MessageSendParams, SendMessageRequest

    async with httpx.AsyncClient(timeout=60) as httpx_client:  # LLM 호출이 있어 넉넉한 타임아웃
        # 1) Agent Card 발견
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=BASE_URL)
        card = await resolver.get_agent_card()
        print("=== 발견한 Agent Card ===")
        print("이름:", card.name)
        print("스킬:", [s.name for s in card.skills])

        # 2) 클라이언트 생성 후 message/send
        client = A2AClient(httpx_client=httpx_client, agent_card=card)
        payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "1달러는 몇 원이야?"}],
                "message_id": uuid4().hex,
            }
        }
        request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
        response = await client.send_message(request)

        # 3) 응답 해석 — 이번엔 "kind": "task" (17·18의 "kind": "message" 와 비교해 볼 것)
        data = response.model_dump(mode="json", exclude_none=True)
        result = data.get("result", {})
        print(f"\n=== 서버 응답 (kind={result.get('kind', '?')}) ===")
        print("상태:", (result.get("status") or {}).get("state"))
        # artifacts[] 안의 TextPart 를 꺼낸다 (버전에 따라 구조가 다를 수 있어 방어적으로)
        for art in result.get("artifacts") or []:
            texts = [p.get("text", "") for p in art.get("parts", []) if p.get("kind") == "text"]
            print(f"[artifact] {art.get('name', '?')}:")
            for t in texts:
                print(" ", t)
        if not result.get("artifacts"):
            print("(artifact 없음 — 응답 전체 덤프)")
            print(data)


def main():
    parser = argparse.ArgumentParser(description="LangGraph + A2A 통합 데모 (서버/클라이언트 한 파일)")
    parser.add_argument("--client", action="store_true", help="클라이언트 모드로 실행 (기본: 서버 모드)")
    args = parser.parse_args()

    if args.client:
        asyncio.run(run_client())
    else:
        run_server()


if __name__ == "__main__":
    main()
