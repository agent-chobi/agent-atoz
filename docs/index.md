# Agent A to Z 🤖

멀티에이전트 시스템(MAS)을 **개념부터 실습까지** 단계별로 익히는 저장소입니다.
각 챕터는 **학습 문서**와 **실행 가능한 Python 코드**(`examples/`)가 짝을 이룹니다.

!!! tip "이 자료의 목표"
    단순히 "에이전트를 호출하는 법"이 아니라, **에이전트 생태계를 직접 구축**하는 데
    필요한 지식 전체를 다룹니다 — 에이전트 개발 → 서브에이전트·MCP → 오케스트레이션
    → 디버깅·관측 → 권한·보안 → 하네스 엔지니어링까지.

## 무엇을 다루나

- **프레임워크**: LangChain · LangGraph · Claude Agent SDK
- **프로토콜**: MCP(Model Context Protocol) · A2A(Agent2Agent)
- **런타임**: OpenClaw · Hermes (셀프호스팅 오케스트레이션)
- **규율(discipline)**: 컨텍스트 엔지니어링 · 관측(observability) · 권한 관리 · 하네스 엔지니어링

## 학습 로드맵

| # | 문서 | 핵심 주제 |
|---|------|-----------|
| **A** | **기반** | |
| 00 | [오케스트레이션 지형도 + SDK 비교](00-landscape.md) | MAS 언제 쓰나, 프레임워크/프로토콜 지도, 패턴·토큰 트레이드오프 |
| 01 | [LLM API 기초](01-llm-api-basics.md) | Messages API, 스트리밍, tool use 최소단위 |
| 02 | [Tool Use & 에이전트 루프](02-tool-use-agent-loop.md) | 생각→행동→관찰, `stop_reason` 분기 |
| **B** | **프레임워크로 에이전트 개발** | |
| 03 | [LangChain 기초 (LCEL)](03-langchain-basics.md) | 추상화 계층, 언제 유용/과함 |
| 04 | [LangGraph 상태 그래프](04-langgraph-state-graph.md) | 노드/엣지/조건분기 + HITL |
| 05 | [Claude Agent SDK](05-claude-agent-sdk.md) | 내장 도구·서브에이전트·MCP 네이티브 |
| **C** | **메모리 & 컨텍스트** | |
| 06 | [단기 메모리 (체크포인터)](06-short-term-memory.md) | thread 영속화, replay/time-travel |
| 07 | [장기 메모리 (스토어)](07-long-term-memory.md) | langmem vs mem0, 의미/에피소드/절차 |
| 08 | [컨텍스트 엔지니어링](08-context-engineering.md) | 선택·압축·격리, 핸드오프 요약 |
| **D** | **멀티에이전트 오케스트레이션** | |
| 09 | [멀티에이전트 패턴](09-multi-agent-patterns.md) | supervisor/swarm/hierarchical + 트레이드오프 |
| 10 | [서브에이전트 · Deep Agents · Skills](10-subagents-deep-agents-skills.md) | planning, 가상 FS, 핸드오프 아티팩트 |
| 11 | [MCP 연계](11-mcp-integration.md) | 서버/클라이언트/어댑터, agent+subagent+mcp |
| 12 | [A2A 프로토콜](12-a2a-protocol.md) | Agent Card, task 교환, 상호운용 |
| **E** | **프로덕션: 관측·권한·안전** | |
| 13 | [디버깅 & 관측](13-debugging-observability.md) | LangSmith/OTel/Langfuse, 멀티에이전트 트레이싱 |
| 14 | [권한 & 보안 & HITL](14-permissions-security-hitl.md) | MCP 인가·최소권한·승인·자격증명 게이트웨이 |
| 15 | [평가 & 비용](15-evaluation-cost.md) | LLM-as-judge, 에이전트 평가, 토큰 관리 |
| 16 | [셀프호스팅 런타임 (OpenClaw & Hermes)](16-self-hosted-runtimes.md) | Gateway 오케스트레이션, Skills 자동생성 |
| 17 | [하네스 엔지니어링 (캡스톤)](17-harness-engineering.md) | 계획/생성/평가 분리, 컨텍스트 리셋·핸드오프 |
| — | [부록 A · SDK 비교 매트릭스](appendix-sdk-matrix.md) | 프레임워크 장단점 한눈에 |

## 빠른 시작

```bash
# 1) 가상환경 (Windows)
python -m venv .venv
.venv\Scripts\activate

# 2) 실습 의존성 설치
pip install -r requirements.txt

# 3) API 키 (.env.example 복사 후 채우기)
#    ANTHROPIC_API_KEY=sk-ant-...

# 4) 첫 예제 실행
python examples/01_basic_message.py
```

문서 사이트를 로컬에서 미리 보려면:

```bash
pip install -r requirements-docs.txt
mkdocs serve   # http://127.0.0.1:8000
```

## 사용 모델

예제는 기본적으로 `claude-opus-4-8`을 사용합니다. 학습/실험 비용을 아끼려면 각 예제 상단의
`MODEL` 상수를 `claude-haiku-4-5`(가장 저렴)나 `claude-sonnet-5`로 바꾸세요.

| 모델 | ID | 입력/출력 ($/1M) | 용도 |
|------|----|------------------|------|
| Claude Opus 4.8 | `claude-opus-4-8` | $5 / $25 | 기본값, 가장 강력 |
| Claude Sonnet 5 | `claude-sonnet-5` | $3 / $15 | 속도·지능 균형 |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | 빠르고 저렴 |

## 참고 자료

- [Building Effective Agents (Anthropic)](https://www.anthropic.com/research/building-effective-agents)
- [Effective harnesses for long-running agents (Anthropic)](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [A2A Protocol](https://a2a-protocol.org/)
- [LangGraph Docs](https://docs.langchain.com/oss/python/langgraph/overview)
