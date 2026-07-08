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

!!! warning "필수 전제 — Node.js 18+ 없이는 동작하지 않는다"
    이 SDK는 파이썬 패키지지만, 내장 도구는 **Claude Code CLI(Node.js 앱)** 위에서 돕니다.
    즉 `pip install claude-agent-sdk` **만으로는 부족**하고, 다음 세 가지가 모두 준비돼야
    합니다(하나라도 빠지면 이 챕터 코드는 실행되지 않습니다):

    1. **Node.js 18+** — CLI 바이너리는 패키지에 번들되지만 Node 런타임 자체는 별도 설치
    2. **Python 3.10+**
    3. **`ANTHROPIC_API_KEY`** 환경변수

    *(설치 버전에 따라 세부 사항이 다를 수 있어 대조 필요.)*

## 2. 두 가지 진입점 — `query()` 와 `ClaudeSDKClient`

SDK는 비동기(`async`)가 기본입니다. 사용 방식은 두 가지입니다.

!!! info "처음 보는 async/await — 왜 에이전트 SDK는 비동기인가"
    에이전트는 실행 시간 대부분을 **기다리며** 보냅니다 — 모델 응답, 도구 실행, 네트워크
    왕복. 비동기는 이 대기 시간에 프로그램이 다른 일을 할 수 있게 하는 파이썬 문법입니다.
    주문을 넣고 음식이 나올 때까지 다른 테이블을 받는 웨이터를 떠올리면 됩니다. 게다가
    에이전트의 응답은 한 덩어리가 아니라 **메시지 스트림**으로 도착하므로, 도착하는 대로
    하나씩 받는 비동기 반복이 자연스러운 인터페이스입니다. 최소 문법 세 가지만 알면
    이 챕터의 코드를 전부 읽을 수 있습니다.

    - `async def main(): ...` — "기다릴 수 있는 함수"(코루틴) 정의
    - `await 표현식` / `async for x in 스트림:` — 결과(또는 다음 항목)가 올 때까지
      이 함수만 잠들고, 프로그램 전체는 멈추지 않음
    - `asyncio.run(main())` — 일반 코드(최상위)에서 코루틴을 실행하는 진입점

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

## 따라하기

이 챕터의 예제는 [`examples/08_claude_agent_sdk.py`](https://github.com/agent-chobi/agent-atoz/blob/main/examples/08_claude_agent_sdk.py)
입니다 — `query()`로 내장 도구(`Read`/`Glob`/`Grep`)를 사용해 저장소의 `examples/` 폴더를
조사하는 최소 에이전트. 웹으로 확인한 실제 API를 따르며, 버전에 민감한 부분은 주석으로
표시했습니다.

**1) 사전 준비** — 이 예제만의 추가 전제가 있습니다.

```bash
node --version                    # v18 이상인지 먼저 확인! (없으면 nodejs.org에서 설치)
pip install -r requirements.txt   # claude-agent-sdk 포함
copy .env.example .env            # macOS/Linux는 cp — ANTHROPIC_API_KEY 채우기
```

**2) 실행**

```bash
python examples/08_claude_agent_sdk.py
```

**3) 기대 출력 요지**

- 에이전트가 `Glob`/`Read`/`Grep`으로 `examples/` 폴더를 훑은 뒤, 조사 결과(파일 구성 요약
  등)를 텍스트로 **스트리밍** 출력합니다.
- 마지막에 `ResultMessage`(비용·소요 턴 수 요약)가 출력됩니다 — 우리가 도구를 하나도 정의하지
  않았는데 파일 작업이 일어났다는 점이 이 SDK의 핵심입니다.

**4) 흔한 에러**

| 증상 | 원인 → 해결 |
|------|-------------|
| CLI를 찾을 수 없다는 예외(`CLINotFoundError` 류) 또는 즉시 종료 | **Node.js 미설치** — 이 예제의 압도적 1위 에러. `node --version`으로 확인 후 Node 18+ 설치 |
| `claude-agent-sdk 가 설치되지 않았습니다` (SystemExit) | `pip install -r requirements.txt` 미실행 |
| 인증 오류 | `.env`에 `ANTHROPIC_API_KEY` 미설정 |
| 모델 이름 오류 | 이 SDK는 축약 별칭(`"opus"`/`"sonnet"`/`"haiku"`)을 사용 — 다른 예제의 전체 모델명과 형식이 다름 |

## 실무 트레이드오프

이 SDK를 채택할지는 결국 "내장 런타임의 힘"과 "종속성"의 교환입니다.

| 기준 | Claude Agent SDK | LangGraph (비교 기준) |
|------|------------------|----------------------|
| 내장 도구 | 파일·셸·검색·웹 등 프로덕션급 도구 즉시 사용 | 전부 직접 정의(`@tool`) |
| 프로바이더 | **Claude 전용** — 교체 불가 | 모델 클래스 교체로 벤더 중립 |
| 제어 흐름 | 에이전트 루프가 블랙박스에 가까움 | 상태 그래프로 노드 단위 제어 |
| 권한/안전 | `permission_mode` 등 권한 체계 내장 | 직접 설계 |
| 런타임 의존 | Python + **Node.js 18+** 이중 의존 | Python만 |
| 프로그래밍 모델 | 비동기 전용(async) | 동기·비동기 모두 |
| MCP·서브에이전트 | 1급 시민으로 최심 통합 | 별도 통합 작업 |

!!! tip "선택 기준"
    **코드베이스에서 파일·셸을 다루는 에이전트**(코딩·자동화·DevOps)라면 Claude Agent SDK가
    가장 빠르고 강력합니다. 반대로 **프로바이더 중립성**이나 **세밀한 상태 그래프 제어**가
    핵심이면 [LangGraph](04-langgraph-state-graph.md)가 낫습니다. 셋을 비교한 표는
    [부록 A](appendix-sdk-matrix.md)에 있습니다.

## 2026 실무 트렌드

- **"코딩 에이전트"를 넘어 범용 에이전트 SDK로** — Anthropic은 SDK의 설계 철학을 "에이전트에게
  컴퓨터를 주라"로 정리하고, 금융 분석·개인 비서·고객 지원 등 비(非)코딩 유스케이스를 공식
  예시로 밀고 있습니다. 리브랜딩(Code SDK → Agent SDK)이 단순 개명이 아니라 방향 전환이라는 뜻.
- **로컬 SDK ↔ 매니지드 인프라 이원화** — 2026년 "Claude Managed Agents"(호스티드 API +
  세션별 매니지드 샌드박스)가 출시되면서, "Agent SDK로 로컬 프로토타이핑 → Managed Agents로
  프로덕션 전환"이 공식 안내 경로가 됐습니다.
- **장기 실행 에이전트 하네스·Agent Skills의 표준화** — 컨텍스트 관리, 파일시스템 기반
  스킬(`SKILL.md`) 등 실무 패턴이 Anthropic 엔지니어링 블로그를 통해 잇달아 정리되며
  사실상의 교과서가 되고 있습니다(이 책 10·17장과 연결).

## 실전 레퍼런스

- [Building agents with the Claude Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk) —
  SDK를 만든 이유와 "에이전트에게 컴퓨터를" 철학, 비코딩 에이전트 사례를 담은 Anthropic 공식 글.
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) —
  장시간 실행 에이전트의 하네스 설계(컨텍스트·상태 관리) 공식 가이드.
- [anthropics/claude-agent-sdk-demos](https://github.com/anthropics/claude-agent-sdk-demos) —
  이메일 어시스턴트·리서치 에이전트 등 SDK로 만든 실동작 예제 모음(공식 저장소).
- [Claude Agent SDK Full Workshop (YouTube)](https://www.youtube.com/watch?v=TqC1qOfiVcQ) —
  Anthropic 소속 발표자가 진행한 실습 중심 SDK 워크숍 영상(2026-01).

### 함께 보면 좋은 한국어 자료

- [Claude Agent SDK로 나만의 AI 에이전트 만들기 — MadPlay](https://madplay.github.io/post/claude-agent-sdk-tutorial) — `query()`·세션 유지·커스텀 도구·훅·권한 관리까지 이 챕터의 흐름을 그대로 한국어로 따라가고, PR 자동 리뷰 에이전트 예제로 마무리하는 튜토리얼.
- [Claude Agent SDK 완전 가이드 — BLUEBUG'S BLOG](https://k82022603.github.io/posts/claude-agent-sdk-%EC%99%84%EC%A0%84-%EA%B0%80%EC%9D%B4%EB%93%9C/) — 설치부터 MCP 서버 통합·서브에이전트 병렬 처리, "멀티 에이전트 개인 비서" 구축까지 14단계로 풀어낸 종합 가이드.
- [코딩 에이전트 핵심 개념 완전 가이드 — yceffort](https://yceffort.kr/2026/01/coding-agent-core-concepts) — SDK가 상속하는 Claude Code 런타임의 개념들(Rules·Hooks·Skills·서브에이전트·MCP)을 한국어로 한 번에 정리.

## 참고 자료

- [Claude Agent SDK 개요](https://docs.claude.com/en/api/agent-sdk/overview)
- [Python SDK 레퍼런스](https://docs.claude.com/en/api/agent-sdk/python)
- [권한 & 도구](https://docs.claude.com/en/api/agent-sdk/permissions)
- [GitHub: anthropics/claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python)
