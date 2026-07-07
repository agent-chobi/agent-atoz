# Agent A to Z 🤖

멀티에이전트 시스템(MAS)을 **개념부터 실습까지** 단계별로 구축하며 배우는 저장소입니다.
LangChain · LangGraph · Claude Agent SDK · MCP · A2A · OpenClaw/Hermes · 하네스 엔지니어링까지,
에이전트 생태계를 직접 만드는 데 필요한 지식 전체를 다룹니다.

📖 **문서 사이트**: https://agent-chobi.github.io/agent-atoz/
각 챕터는 `docs/`의 학습 문서와 `examples/`의 실행 가능한 Python 코드가 짝을 이룹니다.

## 학습 로드맵

| Phase | 챕터 | 핵심 |
|-------|------|------|
| **A. 기반** | 00 지형도+SDK비교 · 01 LLM API · 02 Tool Use·에이전트 루프 | 에이전트의 기본기 |
| **B. 프레임워크** | 03 LangChain · 04 LangGraph · 05 Claude Agent SDK | 에이전트 개발 |
| **C. 메모리·컨텍스트** | 06 단기 메모리 · 07 장기 메모리 · 08 컨텍스트 엔지니어링 | 상태와 기억 |
| **D. 오케스트레이션** | 09 멀티에이전트 패턴 · 10 서브에이전트·Deep Agents · 11 MCP · 12 A2A | 협업·상호운용 |
| **E. 프로덕션** | 13 관측 · 14 권한·보안·HITL · 15 평가·비용 · 16 OpenClaw·Hermes · 17 하네스 엔지니어링 | 신뢰성 |
| **F. 심화·실전** | 18 구조화된 출력 · 19 워크플로우 패턴 · 20 LangGraph 심화 · 21 RAG · 22 통합 프로젝트 | 실무 적용 |

전체 목차와 상세는 [문서 사이트](https://agent-chobi.github.io/agent-atoz/) 또는 [`docs/index.md`](docs/index.md) 참고.

## 빠른 시작

```bash
# 1) 가상환경 (Windows)
python -m venv .venv
.venv\Scripts\activate

# 2) 실습 의존성
pip install -r requirements.txt
#    (08번 Claude Agent SDK 예제는 Node.js 18+ 도 필요)

# 3) API 키
copy .env.example .env   # 그리고 ANTHROPIC_API_KEY 채우기

# 4) 첫 예제
python examples/01_basic_message.py
```

## 문서 사이트 로컬 미리보기

```bash
pip install -r requirements-docs.txt
mkdocs serve             # http://127.0.0.1:8000
```

`main` 브랜치에 푸시하면 GitHub Actions가 자동으로 GitHub Pages에 배포합니다
([`.github/workflows/deploy-docs.yml`](.github/workflows/deploy-docs.yml)).

## 저장소 구조

```
agent-atoz/
├── docs/                 # 학습 문서 (MkDocs Material)
├── examples/             # 실행 가능한 실습 코드
├── mkdocs.yml            # 문서 사이트 설정
├── requirements.txt      # 실습 코드 런타임 의존성
├── requirements-docs.txt # 문서 빌드 의존성
└── .github/workflows/    # Pages 자동 배포
```

## 사용 모델

예제 기본값은 `claude-opus-4-8`. 비용을 아끼려면 각 예제 상단 `MODEL` 상수를
`claude-haiku-4-5`(가장 저렴) 또는 `claude-sonnet-5`로 변경.

## 참고 자료

- [Building Effective Agents (Anthropic)](https://www.anthropic.com/research/building-effective-agents)
- [Effective harnesses for long-running agents (Anthropic)](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Model Context Protocol](https://modelcontextprotocol.io/) · [A2A Protocol](https://a2a-protocol.org/)
- [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)
