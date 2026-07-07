"""
17_a2a_server.py — A2A 서버 (Agent Card 노출 + task 처리)

A2A(Agent2Agent) 는 에이전트끼리 통신하는 표준입니다(Google → Linux Foundation).
서버는 .well-known 경로로 **Agent Card**(에이전트의 명함: 이름·설명·스킬·엔드포인트)를
노출하고, 클라이언트는 이를 발견(discovery)한 뒤 task 를 보냅니다.

구성 요소:
  - AgentCard / AgentSkill / AgentCapabilities : 자기소개(발견용 메타데이터)
  - AgentExecutor.execute()                    : 실제 일 처리 (여기서 응답 생성)
  - DefaultRequestHandler + InMemoryTaskStore  : task 수명주기 관리
  - A2AStarletteApplication                    : ASGI 앱으로 빌드 → uvicorn 실행

실행(먼저 이 서버를 별도 터미널에서 띄우세요):
    pip install -U a2a-sdk uvicorn
    python examples/17_a2a_server.py
    # → http://localhost:9999 에서 대기.
    #   Agent Card: http://localhost:9999/.well-known/agent-card.json
    # 그다음 다른 터미널에서:  python examples/18_a2a_client.py

주의: a2a-sdk 는 2026년 시그니처가 자주 바뀝니다(0.3 → 1.0 에서 AgentCard 필드·클라이언트
      생성 방식이 변경됨). 아래는 널리 쓰이는 0.2.x/0.3.x 안정 패턴입니다. 설치 버전 대조 필요.

[기대 출력 예시] (서버가 뜬 뒤 종료되지 않고 대기하면 성공)
    A2A 서버 시작: http://localhost:9999
    Agent Card: http://localhost:9999/.well-known/agent-card.json
    INFO:     Started server process [12345]
    INFO:     Uvicorn running on http://0.0.0.0:9999 (Press CTRL+C to quit)
    (이후 18_a2a_client.py 가 붙으면 200 OK 액세스 로그가 찍힌다)

[흔한 에러]
    - ImportError: No module named 'a2a' → pip install -r requirements.txt (a2a-sdk, uvicorn)
    - OSError: [WinError 10048] / address already in use: 9999 포트 사용 중
      → 기존 서버 종료 또는 포트 변경(클라이언트 BASE_URL 도 함께 변경)
    - pydantic ValidationError(AgentCard 필드): a2a-sdk 버전 불일치 → 설치 버전 문서 대조
"""

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message


# --- 에이전트의 핵심 로직: task 를 받아 응답을 이벤트 큐에 넣는다 -------------
class GreeterAgentExecutor(AgentExecutor):
    """받은 텍스트에 인사로 응답하는 최소 에이전트."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # 들어온 사용자 메시지 텍스트 추출
        user_text = context.get_user_input() if hasattr(context, "get_user_input") else ""
        reply = f"안녕하세요! A2A 에이전트가 받았습니다: '{user_text}'"
        # 에이전트 발화를 클라이언트로 전송
        await event_queue.enqueue_event(new_agent_text_message(reply))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("취소는 지원하지 않습니다.")


# --- Agent Card: 발견용 명함 -------------------------------------------------
skill = AgentSkill(
    id="greet",
    name="인사하기",
    description="받은 메시지에 한국어로 인사하며 응답한다.",
    tags=["greeting", "demo"],
    examples=["안녕", "hello"],
)

agent_card = AgentCard(
    name="Greeter Agent",
    description="A2A 데모용 인사 에이전트",
    url="http://localhost:9999/",
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[skill],
)


def build_app():
    request_handler = DefaultRequestHandler(
        agent_executor=GreeterAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(agent_card=agent_card, http_handler=request_handler)
    return server.build()  # Starlette ASGI 앱


if __name__ == "__main__":
    print("A2A 서버 시작: http://localhost:9999")
    print("Agent Card: http://localhost:9999/.well-known/agent-card.json")
    uvicorn.run(build_app(), host="0.0.0.0", port=9999)
