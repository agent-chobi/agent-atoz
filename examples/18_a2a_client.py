"""
18_a2a_client.py — A2A 클라이언트 (Agent Card 발견 → task 전송)

17_a2a_server.py 가 노출한 Agent Card 를 발견한 뒤, 그 에이전트에게 메시지(task)를
보내고 응답을 받습니다.

흐름:
  1) A2ACardResolver 로 서버의 .well-known Agent Card 를 가져온다(발견).
  2) A2AClient 를 Agent Card 로 생성한다.
  3) SendMessageRequest 로 텍스트 task 를 보낸다.

실행(반드시 서버를 먼저 띄우세요):
    # 터미널 1
    python examples/17_a2a_server.py
    # 터미널 2
    pip install -U a2a-sdk httpx
    python examples/18_a2a_client.py

주의: a2a-sdk 클라이언트 API 는 버전에 민감합니다. 아래는 널리 쓰이는 0.2.x/0.3.x 패턴이며,
      1.0 계열에서는 create_client(ClientConfig(...)) 방식으로 바뀔 수 있습니다. 설치 버전 대조 필요.

[기대 출력 예시] (응답 JSON 구조는 버전마다 조금 다르며 대략 이런 형태)
    === 발견한 Agent Card ===
    이름: Greeter Agent
    설명: A2A 데모용 인사 에이전트
    스킬: ['인사하기']

    === 서버 응답 ===
    {'id': '...', 'jsonrpc': '2.0', 'result': {'kind': 'message', 'parts':
     [{'kind': 'text', 'text': "안녕하세요! A2A 에이전트가 받았습니다: '안녕, A2A 서버!'"}], ...}}

[흔한 에러]
    - httpx.ConnectError: Connection refused → 17_a2a_server.py 를 먼저 별도 터미널에서 실행
    - ImportError: No module named 'a2a' → pip install -r requirements.txt (a2a-sdk, httpx)
    - 404 (agent-card.json): 서버가 다른 포트/경로에 떠 있음 → BASE_URL 과 서버 포트 일치 확인
"""

import asyncio
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

BASE_URL = "http://localhost:9999"


async def main() -> None:
    async with httpx.AsyncClient() as httpx_client:
        # 1) Agent Card 발견 (기본 .well-known 경로에서 가져옴)
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=BASE_URL)
        agent_card = await resolver.get_agent_card()
        print("=== 발견한 Agent Card ===")
        print("이름:", agent_card.name)
        print("설명:", agent_card.description)
        print("스킬:", [s.name for s in agent_card.skills])

        # 2) 카드로 클라이언트 생성
        client = A2AClient(httpx_client=httpx_client, agent_card=agent_card)

        # 3) task(메시지) 전송
        payload = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "안녕, A2A 서버!"}],
                "message_id": uuid4().hex,
            }
        }
        request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
        response = await client.send_message(request)

        print("\n=== 서버 응답 ===")
        # 응답 구조는 버전마다 다를 수 있어 통째로 덤프
        print(response.model_dump(mode="json", exclude_none=True))


if __name__ == "__main__":
    asyncio.run(main())
