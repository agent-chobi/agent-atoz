# examples/ — 실습 코드

각 파일은 문서의 챕터와 번호로 대응됩니다. 실행 전 환경 설정을 확인하세요.

## 실행 준비

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS/Linux

pip install -r requirements.txt

copy .env.example .env            # Windows (cp on *nix), 그리고 키 채우기
#   ANTHROPIC_API_KEY=sk-ant-...
```

대부분의 예제는 `python-dotenv`로 `.env`를 자동 로드합니다.
비용을 아끼려면 각 파일 상단의 `MODEL` 상수를 `claude-haiku-4-5`로 바꾸세요.

> **모델 변경 예외 2건**: `08_claude_agent_sdk.py`는 별칭(`"opus"` → `"haiku"`),
> `14_subagents.py`는 provider 접두사 포함(`"anthropic:claude-haiku-4-5"`) 형식을 사용합니다.

**추가 사전 준비가 필요한 예제:**

| 예제 | 추가 요구사항 |
|------|---------------|
| `08_claude_agent_sdk.py` | **Node.js 18+** 설치 (Claude Agent SDK 런타임 전제조건) |
| `10_long_term_memory.py` (의미검색 부분) | `.env`에 `OPENAI_API_KEY` (임베딩용, 없으면 해당 부분 건너뜀) |
| `12`~`14` | `langgraph-supervisor`/`langgraph-swarm`/`deepagents` — requirements.txt에 포함됨 |
| `15`+`16`, `17`+`18` | 서버/클라이언트 쌍 — **서버를 먼저** 별도 터미널에서 실행 |
| `19_tracing.py` | `LANGSMITH_*` 환경변수 설정 시 LangSmith 트레이싱, 미설정 시 콘솔 폴백 |

> 16장(셀프호스팅 런타임)은 개념 챕터로 대응 예제가 없습니다.

## 파일 ↔ 챕터 매핑

| 파일 | 챕터 |
|------|------|
| `01_basic_message.py`, `02_streaming.py` | 01. LLM API 기초 |
| `03_tool_use.py`, `04_agent_loop.py` | 02. Tool Use & 에이전트 루프 |
| `05_langchain_lcel.py` | 03. LangChain 기초 |
| `06_langgraph_basics.py`, `07_langgraph_hitl.py` | 04. LangGraph 상태 그래프 |
| `08_claude_agent_sdk.py` | 05. Claude Agent SDK |
| `09_short_term_memory.py` | 06. 단기 메모리 |
| `10_long_term_memory.py` | 07. 장기 메모리 |
| `11_context_engineering.py` | 08. 컨텍스트 엔지니어링 |
| `12_supervisor.py`, `13_swarm.py` | 09. 멀티에이전트 패턴 |
| `14_subagents.py` | 10. 서브에이전트·Deep Agents |
| `15_mcp_server.py`, `16_mcp_client.py` | 11. MCP 연계 |
| `17_a2a_server.py`, `18_a2a_client.py` | 12. A2A 프로토콜 |
| `19_tracing.py` | 13. 디버깅 & 관측 |
| `20_permissions_hitl.py` | 14. 권한 & 보안 & HITL |
| `21_llm_judge.py` | 15. 평가 & 비용 |
| `22_harness.py` | 17. 하네스 엔지니어링 (캡스톤) |
| `23_structured_output.py` | 18. 구조화된 출력 |
| `24_workflow_patterns.py` | 19. 워크플로우 패턴 |
| `25_langgraph_advanced.py` | 20. LangGraph 심화 |
| `26_agentic_rag.py` | 21. RAG & Agentic RAG |
| `project/` (step1~step5) | 22. 통합 프로젝트 — 단계별 캡스톤 |

> 일부 예제(MCP·A2A 서버)는 별도 터미널 두 개(서버/클라이언트)로 실행합니다. 각 파일 상단 주석을 참고하세요.
