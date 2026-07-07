# 05. Claude Agent SDK

앞의 두 챕터([03](03-langchain-basics.md)·[04](04-langgraph-state-graph.md))는 프로바이더 중립적인
프레임워크였습니다. 이번 챕터의 **Claude Agent SDK**는 결이 다릅니다. 이것은 **Claude Code를
움직이는 바로 그 런타임**을 파이썬/타입스크립트에서 그대로 쓰는 SDK입니다. 즉 파일 읽기·쓰기,
bash 실행, 코드 편집, 검색, 웹 검색 같은 **프로덕션급 내장 도구를 처음부터 상속**받습니다.
직접 도구를 짜지 않아도 "코드베이스에서 일하는 에이전트"가 즉시 만들어집니다.

!!! note "이름 정리 — Agent SDK vs Code"
    2024년의 "Claude Code SDK"가 2025년 리브랜딩되어 **Claude Agent SDK**가 되었습니다.
    옵션 클래스도 `ClaudeCodeOptions` → **`ClaudeAgentOptions`** 로 바뀌었습니다.
    오래된 예제에서 옛 이름을 보면 이 대응으로 읽으세요.

## 1. 무엇이 다른가 — 런타임 상속

LangGraph에서는 `@tool`로 도구를 **직접** 정의했습니다. Claude Agent SDK에서는 Claude Code가
쓰는 도구들이 **이미 존재**하며, 에이전트에 이름으로 허용만 하면 됩니다.

| 내장 도구 | 하는 일 |
|-----------|---------|
| `Read` / `Write` / `Edit` | 파일 읽기·생성·정밀 편집 |
| `Bash` | 셸 명령 실행 |
| `Glob` / `Grep` | 파일 패턴·정규식 검색 |
| `WebSearch` / `WebFetch` | 웹 검색·페이지 가져오기 |
| `Agent` | 서브에이전트 호출 |

이 도구들은 **파일시스템 경계·권한 모드**로 통제됩니다. 즉 "무엇을 할 수 있는가"가 옵션
한 줄로 제어됩니다 — 이것이 이 SDK의 핵심 가치입니다.

!!! warning "전제 조건 — Node.js가 필요하다"
    Claude Agent SDK의 내장 도구는 Claude Code CLI(Node.js 앱) 위에서 돕니다. 그래서
    **Node.js 18+ 가 설치돼 있어야** 합니다(CLI 바이너리는 패키지에 번들됨). 또한
    `ANTHROPIC_API_KEY` 환경변수가 필요합니다. `pip install claude-agent-sdk` 만으로는
    파이썬 3.10+ 와 Node 런타임 둘 다 준비돼야 정상 동작합니다. *(설치 버전에 따라 세부
    사항이 다를 수 있어 대조 필요.)*

## 2. 두 가지 진입점 — `query()` 와 `ClaudeSDKClient`

SDK는 비동기(`async`)가 기본입니다. 사용 방식은 두 가지입니다.

| 진입점 | 특성 | 언제 |
|--------|------|------|
| `query()` | 한 번의 요청 → 메시지 스트림. 상태 없음(one-shot) | 단발 작업 |
| `ClaudeSDKClient` | 컨텍스트 매니저. 멀티턴 대화, 동적 권한 변경 | 지속 세션·대화형 |

### query() — 단발 실행

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

async def main():
    async for message in query(
        prompt="이 폴더에서 가장 큰 파일을 찾아 이름을 알려줘",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Glob", "Grep", "Bash"],  # 허용 도구만 나열
            permission_mode="acceptEdits",                    # 파일 작업 자동 승인
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)

asyncio.run(main())
```

### ClaudeSDKClient — 멀티턴 세션

```python
from claude_agent_sdk import ClaudeSDKClient

async with ClaudeSDKClient(options=ClaudeAgentOptions(...)) as client:
    await client.query("이 디렉터리에 뭐가 있어?")
    async for msg in client.receive_response():
        ...                                  # 첫 응답 스트림
    await client.query("그중 가장 최근 파일은?")  # 컨텍스트가 유지된 채 이어짐
    async for msg in client.receive_response():
        ...
```

## 3. 권한 모드 — 안전의 핵심

내장 도구는 강력한 만큼 통제가 중요합니다. `permission_mode`가 도구 실행 정책을 정합니다.

| 모드 | 동작 | 용도 |
|------|------|------|
| `"default"` | `can_use_tool` 콜백으로 매번 확인 | 대화형 승인 |
| `"acceptEdits"` | 파일 편집류 자동 승인 | 반자동 작업 |
| `"plan"` | 읽기 전용, 편집은 항상 확인 | 계획 수립 단계 |
| `"bypassPermissions"` | 전부 승인 | 격리된 자동화(주의) |

!!! danger "bypassPermissions는 격리 환경에서만"
    `bypassPermissions`는 확인 없이 파일 쓰기·bash 실행을 허용합니다. 반드시 컨테이너·샌드박스
    같은 격리 환경에서만 쓰세요. 프로덕션 권한 설계는 [14장](14-permissions-security-hitl.md)에서
    다룹니다.

## 4. MCP 네이티브 통합

Claude Agent SDK는 [MCP](11-mcp-integration.md)를 **1급 시민**으로 다룹니다. 외부 MCP 서버를
`mcp_servers`로 붙이거나, 서브프로세스 없이 **인프로세스 SDK MCP 서버**를 만들 수 있습니다.

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions

@tool("add", "두 수를 더한다", {"a": float, "b": float})
async def add(args):
    return {"content": [{"type": "text", "text": str(args["a"] + args["b"])}]}

calc = create_sdk_mcp_server(name="calc", version="1.0.0", tools=[add])

options = ClaudeAgentOptions(
    mcp_servers={"calc": calc},
    allowed_tools=["mcp__calc__add"],   # MCP 도구 이름: mcp__<서버>__<도구>
)
```

## 5. 서브에이전트 — `AgentDefinition`

`agents` 옵션으로 **역할별 서브에이전트**를 정의하면, 메인 에이전트가 `Agent` 도구로
필요할 때 위임합니다. 각 서브에이전트는 자기만의 프롬프트·도구·모델을 가질 수 있습니다
(오케스트레이션 패턴은 [09](09-multi-agent-patterns.md)·[10장](10-subagents-deep-agents-skills.md)).

```python
from claude_agent_sdk import AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Agent"],   # Agent 도구를 켜야 위임 가능
    agents={
        "reviewer": AgentDefinition(
            description="보안·품질 관점의 코드 리뷰어",
            prompt="코드를 리뷰하고 보안 이슈와 스타일 문제를 지적하라.",
            tools=["Read", "Glob", "Grep"],
            model="opus",     # 서브에이전트별 모델 지정 가능
        ),
    },
)
```

## 6. 장단점 — 언제 이 SDK인가

| 강점 | 약점 |
|------|------|
| 프로덕션급 내장 도구 즉시 사용 | **Claude 전용** (프로바이더 교체 불가) |
| MCP·서브에이전트 최심 통합 | Node.js 런타임 의존 |
| Claude Code와 동일 런타임의 검증된 동작 | 비동기 전용, 세밀한 그래프 제어는 약함 |

!!! tip "선택 기준"
    **코드베이스에서 파일·셸을 다루는 에이전트**(코딩·자동화·DevOps)라면 Claude Agent SDK가
    가장 빠르고 강력합니다. 반대로 **프로바이더 중립성**이나 **세밀한 상태 그래프 제어**가
    핵심이면 [LangGraph](04-langgraph-state-graph.md)가 낫습니다. 셋을 비교한 표는
    [부록 A](appendix-sdk-matrix.md)에 있습니다.

## 7. 실습 코드

- [`examples/08_claude_agent_sdk.py`](../examples/08_claude_agent_sdk.py) — `query()`로
  내장 도구(`Read`/`Glob`/`Grep`)를 사용해 폴더를 조사하는 최소 에이전트. 웹으로 확인한
  실제 API를 따르며, 버전에 민감한 부분은 주석으로 표시했습니다.

실행:

```bash
pip install -r requirements.txt   # claude-agent-sdk 포함 + Node.js 18+ 필요
python examples/08_claude_agent_sdk.py
```

## 참고 자료

- [Claude Agent SDK 개요](https://docs.claude.com/en/api/agent-sdk/overview)
- [Python SDK 레퍼런스](https://docs.claude.com/en/api/agent-sdk/python)
- [권한 & 도구](https://docs.claude.com/en/api/agent-sdk/permissions)
- [GitHub: anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
