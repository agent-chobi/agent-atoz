# 부록 A · SDK / 프레임워크 비교 매트릭스

멀티에이전트 시스템을 구축할 때 선택지가 되는 주요 SDK·런타임을 한 표로 비교합니다.
수치와 평가는 2026년 기준이며, 빠르게 변하므로 **의사결정 시점에 재확인**하세요.

## 종합 매트릭스

| | 제어도 | 학습곡선 | 멀티에이전트 | 메모리/체크포인트 | MCP | 모델 락인 | 토큰 효율 |
|---|---|---|---|---|---|---|---|
| **LangGraph** | ★★★★★ | 중 | 그래프+supervisor/swarm | 내장(체크포인터+time-travel) | 어댑터 | 없음(멀티) | 높음 |
| **LangChain** | ★★★☆☆ | 낮 | 제한적(체인 위주) | 통합 | 어댑터 | 없음 | 중 |
| **CrewAI** | ★★☆☆☆ | 매우 낮 | 역할 기반 팀 | 기본 제공 | 지원 | 없음 | 낮음(최대 3×) |
| **AutoGen / AG2** | ★★★☆☆ | 중 | 대화형 그룹챗 | 확장 | 지원 | 없음 | 중 |
| **Claude Agent SDK** | ★★★★☆ | 낮 | 서브에이전트 | 파일 기반+세션 | **최심 통합** | Claude 전용 | 높음 |
| **OpenAI Agents SDK** | ★★★★☆ | 낮 | handoff 모델 | 세션 | 지원 | OpenAI 전용 | 높음 |
| **Google ADK** | ★★★★☆ | 중 | 계층형+A2A | 확장 | 지원 | Gemini 우선 | 중 |
| **Strands** | ★★★☆☆ | 낮 | 모델-드리븐 | 확장 | 지원 | 멀티 | 높음 |
| **OpenClaw** (런타임) | ★★★☆☆ | 중 | Gateway 오케스트레이션 | 영속 | 지원 | 멀티 | — |
| **Hermes** (런타임) | ★★★☆☆ | 중 | 자율+Skills 자동생성 | 영속 학습 루프 | 지원 | 멀티 | — |

## 언제 무엇을 선택하나

=== "제어·프로덕션 중시"
    **LangGraph.** 명시적 상태 그래프·조건 분기·체크포인트(time-travel)·HITL이 필요할 때.
    Klarna가 8,500만 사용자 규모로 운영. CrewAI 대비 약 47% 낮은 토큰 비용(명시적 엣지 전이 덕).
    비용: 보일러플레이트와 그래프 개념 학습.

=== "빠른 프로토타입"
    **CrewAI.** 역할(Researcher/Writer/Reviewer) 기반으로 20~25줄이면 동작하는 팀 구성.
    단, 모든 Agent가 role/goal/backstory를 매 호출에 실어 컨텍스트가 부풀어 토큰이 최대 3×.
    스케일에서 라우팅 제어가 부족 → 흔히 LangGraph로 재구현.

=== "코딩 에이전트"
    **Claude Agent SDK.** 파일 read/write·bash·코드 편집·웹검색·grep이 **내장**(Claude Code 런타임 상속).
    MCP 통합이 가장 깊음. 대신 Claude 모델 전용.

=== "OpenAI 스택"
    **OpenAI Agents SDK.** 실험적 Swarm을 대체한 프로덕션용 정식 SDK. 깔끔한 handoff 추상.
    OpenAI 모델 전용.

=== "셀프호스팅 런타임"
    **OpenClaw / Hermes.** SDK로 조립하는 대신, 여러 LLM·메시징 채널에 붙는 완성형 런타임이
    필요할 때. Hermes는 반복 작업을 감지해 Skills를 스스로 생성(→ 16장).

## 프로토콜은 SDK와 직교한다

MCP·A2A는 SDK 선택과 **독립적**입니다. 어떤 프레임워크를 쓰든:

- **MCP** = 에이전트 ↔ 도구/리소스 표준 (→ 11장)
- **A2A** = 에이전트 ↔ 에이전트 표준 (→ 12장)

즉 "LangGraph + MCP 도구 + A2A로 외부 에이전트 호출" 같은 조합이 자연스럽습니다.

## 참고 자료

- [2026 AI Agent Framework Showdown](https://qubittool.com/blog/ai-agent-framework-comparison-2026)
- [Best AI Agent SDKs Compared (2026)](https://www.requesty.ai/blog/best-ai-agent-sdks-compared-2026-langchain-crewai-openai-anthropic-google)
- [Claude Agent SDK vs LangGraph vs CrewAI Benchmark](https://pasqualepillitteri.it/en/news/3095/claude-agent-sdk-vs-langgraph-vs-crewai-benchmark-2026-en)
