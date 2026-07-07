"""
15_mcp_server.py — MCP 서버 (FastMCP, stdio 전송)

MCP(Model Context Protocol) 는 에이전트와 도구를 잇는 표준입니다.
FastMCP 로 "타입 힌트 + docstring" 만으로 도구를 노출하면, JSON 스키마·프로토콜 처리는
프레임워크가 자동으로 해줍니다.

여기서는 도구 2개(add, get_weather)를 stdio 전송으로 노출합니다.
stdio 서버는 보통 클라이언트가 서브프로세스로 띄우므로, 직접 실행할 일은 드뭅니다.

실행(직접 확인용, 보통은 16_mcp_client.py 가 자동으로 띄웁니다):
    pip install -U mcp
    python examples/15_mcp_server.py       # stdin/stdout 으로 대기 (Ctrl+C 로 종료)

참고: mcp>=1.x 의 안정 API 기준입니다. mcp v2 (pre-release) 는 임포트 경로가 다릅니다.
      설치 버전 대조 필요.

[기대 출력 예시]
    (직접 실행 시) 화면에 아무것도 출력되지 않고 stdin 대기 상태로 멈춘 것처럼 보인다.
    이는 정상 — stdio 서버는 stdin 으로 JSON-RPC 메시지가 들어오길 기다린다.
    Ctrl+C 로 종료. 실제 동작 확인은 16_mcp_client.py 를 실행하면 되고,
    그때 이 서버가 서브프로세스로 떠서 add / get_weather 호출에 응답한다.

[흔한 에러]
    - ImportError: No module named 'mcp' → pip install -r requirements.txt 재실행
    - ImportError: cannot import name 'FastMCP' (mcp v2 pre-release 설치됨)
      → pip install "mcp>=1,<2" 로 1.x 안정 버전 설치
    - 직접 실행했는데 "멈춘 것 같다" → 오류 아님(stdin 대기). 클라이언트로 테스트할 것
"""

from mcp.server.fastmcp import FastMCP

# 서버 인스턴스 (이름은 클라이언트가 식별용으로 봅니다)
mcp = FastMCP("demo-tools")


@mcp.tool()
def add(a: int, b: int) -> int:
    """두 정수를 더한다.

    Args:
        a: 첫 번째 정수
        b: 두 번째 정수
    """
    return a + b


@mcp.tool()
def get_weather(city: str) -> str:
    """도시의 날씨를 반환한다(데모용 고정 응답).

    Args:
        city: 도시 이름
    """
    table = {
        "seoul": "맑음, 26도",
        "busan": "흐림, 24도",
        "tokyo": "비, 22도",
    }
    return table.get(city.lower(), f"{city} 의 날씨 데이터가 없습니다.")


if __name__ == "__main__":
    # stdio 전송으로 실행 (클라이언트가 stdin/stdout 파이프로 통신).
    # HTTP 로 노출하려면 transport="streamable-http" 로 바꾸고 host/port 를 설정하세요.
    mcp.run(transport="stdio")
