"""
16_mcp_client.py — MCP 클라이언트 (두 가지 방식)

15_mcp_server.py 를 서브프로세스(stdio)로 띄워 그 도구를 호출합니다.
서버를 미리 별도 터미널에서 실행할 필요는 없습니다 — 클라이언트가 자동으로 띄웁니다.

두 가지 사용법을 보여줍니다:
  (A) 순수 MCP SDK: ClientSession 으로 직접 list_tools / call_tool
  (B) langchain-mcp-adapters: MultiServerMCPClient.get_tools() 로 MCP 도구를
      LangGraph 에이전트에 그대로 연결 (에이전트가 알아서 도구를 호출)

실행:
    pip install -U mcp langchain-mcp-adapters langgraph langchain-anthropic
    python examples/16_mcp_client.py

참고: 방식 (B) 는 ANTHROPIC_API_KEY 가 필요합니다(에이전트가 LLM 을 호출).
      키가 없으면 (A) 만 실행됩니다.

[기대 출력 예시] ((A)는 결정적, (B)의 문구는 실행마다 다름)
    === (A) 서버가 노출한 도구 ===
    - add: 두 정수를 더한다. ...
    - get_weather: 도시의 날씨를 반환한다(데모용 고정 응답). ...

    add(3, 5) => 8
    get_weather('Seoul') => 맑음, 26도

    === (B) LangGraph 에이전트가 MCP 도구를 자율 호출 ===
    서울은 맑고 26도입니다. 그리고 3 더하기 5는 8입니다.

[흔한 에러]
    - FileNotFoundError / 서버 기동 실패: 15_mcp_server.py 경로 문제 → 이 파일과 같은
      examples/ 폴더에 15_mcp_server.py 가 있어야 한다 (SERVER_SCRIPT 가 자동 계산)
    - ImportError: No module named 'langchain_mcp_adapters' → pip install -r requirements.txt
    - "[건너뜀] ANTHROPIC_API_KEY 가 없어..." 출력: (B) 생략 — 키를 .env 에 설정하면 실행됨
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-8"  # 비용 절감: "claude-haiku-4-5" 로 변경

# 이 클라이언트가 띄울 서버 스크립트 (같은 폴더의 15_mcp_server.py)
SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "15_mcp_server.py")


# --- (A) 순수 MCP SDK 로 직접 호출 -------------------------------------------
async def run_raw_client() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # 서버를 서브프로세스로 띄우는 파라미터 (현재 파이썬으로 서버 스크립트 실행)
    server_params = StdioServerParameters(command=sys.executable, args=[SERVER_SCRIPT])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()  # 핸드셰이크

            tools = await session.list_tools()
            print("=== (A) 서버가 노출한 도구 ===")
            for t in tools.tools:
                print(f"- {t.name}: {t.description}")

            add_result = await session.call_tool("add", {"a": 3, "b": 5})
            print("\nadd(3, 5) =>", add_result.content[0].text)

            weather = await session.call_tool("get_weather", {"city": "Seoul"})
            print("get_weather('Seoul') =>", weather.content[0].text)


# --- (B) langchain-mcp-adapters 로 LangGraph 에이전트에 연결 ------------------
async def run_langgraph_agent() -> None:
    from langchain_anthropic import ChatAnthropic
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langgraph.prebuilt import create_react_agent

    client = MultiServerMCPClient(
        {
            "demo": {
                "command": sys.executable,
                "args": [SERVER_SCRIPT],
                "transport": "stdio",
            }
        }
    )

    # MCP 도구를 LangChain 도구 객체로 변환 (비동기)
    tools = await client.get_tools()

    # 최신 Opus는 temperature 미지원(400) — 결정성이 필요하면 프롬프트로 제어
    agent = create_react_agent(ChatAnthropic(model=MODEL), tools)

    print("\n=== (B) LangGraph 에이전트가 MCP 도구를 자율 호출 ===")
    response = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "서울 날씨 알려주고, 3 더하기 5도 계산해줘."}]}
    )
    print(response["messages"][-1].content)


async def main() -> None:
    await run_raw_client()

    if os.getenv("ANTHROPIC_API_KEY"):
        await run_langgraph_agent()
    else:
        print("\n[건너뜀] ANTHROPIC_API_KEY 가 없어 (B) LangGraph 연동은 생략합니다.")


if __name__ == "__main__":
    asyncio.run(main())
