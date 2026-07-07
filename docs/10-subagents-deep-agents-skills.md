# 10. 서브에이전트 · Deep Agents · Skills

[09장](09-multi-agent-patterns.md)의 패턴들은 모두 하나의 빌딩블록 위에 서 있습니다 —
**서브에이전트**. 이 챕터는 서브에이전트가 왜 컨텍스트 관점에서 결정적인지, 이를
배터리처럼 포장한 **LangChain Deep Agents**, 그리고 장기실행 에이전트를 지탱하는
**하네스 패턴**과 **Skills** 개념을 다룹니다.

## 1. 서브에이전트 위임 — 핵심은 컨텍스트 격리

서브에이전트의 진짜 값은 "일을 나눠 한다"가 아니라 **컨텍스트 격리(context
quarantine)** 입니다. 메인 에이전트가 무거운 작업(웹검색 수십 회, 긴 파일 읽기,
대용량 DB 조회)을 서브에이전트에게 위임하면, 그 수십 번의 중간 도구 호출은
서브에이전트 안에 갇히고 메인 에이전트는 **최종 결과만** 돌려받습니다.

```mermaid
flowchart TB
    M["🧠 메인 에이전트<br/>(깨끗한 컨텍스트 유지)"]
    M -->|"task('research-agent', 질문)"| SA["🔬 서브에이전트"]
    SA -->|"도구 호출 ×수십 (격리됨)"| T["🔎🔎🔎 도구들"]
    T --> SA
    SA -->|"최종 요약만 반환"| M
```

!!! note "왜 격리가 중요한가"
    도구 출력이 큰 작업일수록 컨텍스트 창이 중간 결과로 빠르게 오염됩니다. 서브에이전트는
    이 상세 작업을 격리해, 메인은 결론만 보고 판단을 이어갑니다. 이것이 [08장](08-context-engineering.md)
    의 "격리(isolation)" 를 실전에서 구현하는 방법입니다.

## 2. LangChain Deep Agents

`deepagents` 는 `create_agent` 위에 **planning · 가상 파일시스템 · 서브에이전트 ·
skills** 를 기본 탑재한 "배터리 포함(batteries-included)" 하네스입니다. Claude Code가
쓰는 패턴(계획 세우기 → 파일에 작업 상태 기록 → 서브에이전트 위임)을 라이브러리로
일반화한 것입니다.

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-opus-4-8",
    tools=[internet_search],
    system_prompt="너는 리서치 오케스트레이터다. 먼저 write_todos 로 계획을 세워라.",
    subagents=[research_subagent],   # 커스텀 서브에이전트 (아래 표 형식)
)
result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
```

→ 전체 실행 예제: [`examples/14_subagents.py`](https://github.com/agent-chobi/agent-atoz/blob/main/examples/14_subagents.py)

### 2-1. 네 가지 기본 탑재 기능

| 기능 | 역할 |
|------|------|
| **planning (`write_todos`)** | 작업을 todo 리스트로 쪼개 계획을 명시. 긴 작업에서 방향 유지 |
| **가상 파일시스템** | `read`/`write`/`edit`/`search` 로 중간 산출물을 파일에 저장(컨텍스트 밖 메모리) |
| **서브에이전트** | `task()` 도구로 위임. `general-purpose` 서브에이전트가 자동 포함 |
| **skills** | 재사용 가능한 절차(아래 4절)를 시스템 프롬프트에 로드 |

### 2-2. 서브에이전트 딕셔너리 형식

```python
research_subagent = {
    "name": "research-agent",          # 메인이 task() 로 부를 식별자
    "description": "심층 조사에 사용",   # 구체적·행동 지향적으로
    "system_prompt": "너는 뛰어난 리서처다. 결론만 요약해 반환하라.",
    "tools": [internet_search],        # 선택
    "model": "anthropic:claude-haiku-4-5",  # 선택 — 메인 모델 오버라이드
}
```

!!! warning "버전 민감성"
    `deepagents` 는 2026년 빠르게 진화 중입니다. 서브에이전트 키가 `system_prompt` 인지
    `prompt` 인지, skills 상속 규칙 등이 바뀔 수 있습니다. 커스텀 서브에이전트는 기본적으로
    skills를 **상속하지 않으므로** 필요하면 `skills` 파라미터로 따로 줘야 합니다. 설치
    버전 대조가 필요합니다.

## 3. 장기실행 하네스 패턴 (Anthropic)

에이전트가 수십 분~수 시간 도는 장기 작업에서는, 컨텍스트 창 하나에 모든 것을 담을 수
없습니다. Anthropic이 권장하는 **하네스 엔지니어링** 패턴은 상태를 컨텍스트 밖으로
빼내 관리합니다.

```mermaid
flowchart LR
    P["📝 진행상황 파일<br/>(progress.md)"] --> A["🤖 에이전트 루프"]
    A -->|작업 후 업데이트| P
    A --> G["🌿 git 상태관리<br/>(커밋 = 체크포인트)"]
    A -->|컨텍스트 리셋 시| H["📦 구조화된 핸드오프<br/>아티팩트"]
    H --> A
```

- **진행상황 파일** — 무엇을 했고 다음에 뭘 할지 파일에 기록. 컨텍스트가 리셋돼도 여기서
  이어감(가상 FS의 `write_todos`/`progress.md`가 이 역할).
- **git 상태관리** — 커밋을 체크포인트로 삼아 되돌리기·비교 가능. 에이전트가 자기
  변경을 git으로 추적.
- **구조화된 핸드오프 아티팩트** — 컨텍스트를 비우기 전에, 다음 인스턴스가 읽을 수 있는
  **요약 문서**를 남김. "대화 통째로 넘기기"가 아니라 "정제된 상태만 넘기기".

!!! tip "컨텍스트 리셋은 실패가 아니라 설계다"
    긴 작업에서 컨텍스트를 주기적으로 비우고 핸드오프 아티팩트로 재시작하는 것은
    정상적인 운영입니다. 이 규율은 [17장 하네스 엔지니어링](17-harness-engineering.md)에서
    캡스톤으로 깊게 다룹니다.

## 4. Skills 개념

**Skill** 은 에이전트가 재사용하는 **절차적 지식의 패키지**입니다. 도구가 사무실의
장비(누르면 동작하는 기계)라면, skill은 신입에게 건네는 **업무 매뉴얼**에 가깝습니다.
보통 `SKILL.md`(무엇을·언제·어떻게) + 스크립트/리소스로 구성되며, 에이전트는 필요할 때
해당 skill을 컨텍스트로 로드해 "매번 처음부터 추론" 대신 검증된 절차를 따릅니다.

```markdown
<!-- 예: skills/pdf-report/SKILL.md -->
---
name: pdf-report
description: 데이터 요약을 PDF 보고서로 변환할 때 사용
---
1. 데이터를 `report.md` 로 정리한다.
2. `scripts/render.py` 로 PDF 로 변환한다.
3. 표지·목차·페이지 번호를 포함한다.
```

| 구분 | 도구(tool) | 스킬(skill) |
|------|-----------|-------------|
| 단위 | 함수 하나 | 절차·지침·리소스 묶음 |
| 형태 | 코드 시그니처 | `SKILL.md` + 자산 |
| 로드 | 항상 노출 | 필요 시 선택적 로드 |

Deep Agents는 skills를 미들웨어로 시스템 프롬프트에 주입합니다(**progressive
disclosure** — 이름·설명만 먼저 보이고, 실제 호출 시 본문을 로드해 컨텍스트를 아낌).
자기개선형 런타임에서는 에이전트가 **skill을 스스로 만들어** 축적하기도 합니다
(→ [16장 Hermes](16-self-hosted-runtimes.md)).

!!! tip "언제 도구 대신 skill로 만드나"
    - 단일 함수 호출이면 **도구**.
    - "여러 단계를 정해진 순서로, 매번 같은 방식으로" 반복한다면 **skill**.
    - 절차가 자주 바뀌거나 사람이 관리해야 한다면 코드가 아니라 `SKILL.md` 로 두는 편이
      수정이 쉽습니다.

## 5. 정리

- 서브에이전트의 값은 분업이 아니라 **컨텍스트 격리**다.
- **Deep Agents** = create_agent + planning + 가상 FS + 서브에이전트 + skills.
- 장기실행은 **진행상황 파일 · git · 핸드오프 아티팩트**로 상태를 컨텍스트 밖에 둔다.
- **Skill** 은 재사용 절차의 패키지 — 도구보다 큰 단위, 선택적 로드.

다음은 에이전트를 외부 도구 생태계와 표준으로 잇는 [MCP 연계](11-mcp-integration.md)입니다.

## 따라하기

서브에이전트 위임과 컨텍스트 격리를
[`examples/14_subagents.py`](https://github.com/agent-chobi/agent-atoz/blob/main/examples/14_subagents.py)
로 직접 확인합니다.

**① 사전 준비**

```bash
pip install -U deepagents langchain-anthropic python-dotenv
```

`.env` 에 `ANTHROPIC_API_KEY` 필요. 이 예제의 모델 문자열은 **provider 접두사 포함**
형식입니다 — 비용을 아끼려면 `MODEL` 을 `"anthropic:claude-haiku-4-5"` 로 바꾸세요
(다른 예제들과 형식이 다른 점에 주의).

**② 실행**

```bash
python examples/14_subagents.py
```

**③ 기대 출력 요지**

- `=== 최종 답변 ===` 아래에 "왜 서브에이전트로 컨텍스트를 격리하는가"에 대한
  한국어 요약 단락이 출력됩니다. 그 과정에서 메인 에이전트는 `write_todos` 로 계획을
  세우고 `task()` 도구로 `research-agent` 서브에이전트에게 조사를 위임합니다 —
  서브에이전트의 중간 검색 호출은 메인 대화에 나타나지 않습니다(격리의 증거).
- 에이전트가 가상 파일시스템에 뭔가 남겼다면 `=== 가상 파일시스템 ===` 아래에
  계획/산출물 파일 내용이 함께 출력됩니다.

**④ 흔한 에러**

| 증상 | 원인 · 해결 |
|------|-------------|
| `ModuleNotFoundError: deepagents` | 패키지 미설치 — `pip install -U deepagents` |
| `TypeError: unexpected keyword 'system_prompt'` 류 | deepagents 버전에 따라 서브에이전트 키가 `prompt` 일 수 있음 — 설치 버전 문서 대조 |
| 모델 로드 실패 | `MODEL` 에 `anthropic:` 접두사 누락 — deepagents는 `"provider:model"` 문자열을 받음 |
| `ANTHROPIC_API_KEY 가 없습니다` | `.env` 누락 또는 키 미기입 |

## 실무 트레이드오프

서브에이전트 격리는 공짜가 아닙니다 — **깨끗한 컨텍스트를 얻는 대신 정보와 시간을
지불**합니다. 언제 격리하고 언제 한 에이전트 안에서 컨텍스트를 공유할지 기준을 세우세요.

| 기준 | 서브에이전트 격리 | 단일 에이전트(컨텍스트 공유) |
|------|------------------|---------------------------|
| 메인 컨텍스트 | 중간 도구 출력이 격리되어 깨끗함 | 도구 출력이 쌓여 오염·비대화 |
| 토큰 비용 | 시스템 프롬프트·지시 중복으로 총량 증가 | 중복 없음 — 총량은 적음 |
| 지연 | 위임 왕복(LLM 호출 추가)만큼 느려짐 | 왕복 없음 |
| 정보 보존 | 요약 반환 과정에서 세부가 유실될 수 있음 | 모든 중간 결과에 접근 가능 |
| 디버깅 | 실패가 서브에이전트 안에 숨을 수 있음 — 트레이싱 필요([13장](13-debugging-observability.md)) | 단일 트레이스로 추적 쉬움 |
| 적합 상황 | 도구 출력이 크고(검색 수십 회, 긴 파일) 결론만 필요할 때 | 작업이 짧고 중간 결과를 계속 참조해야 할 때 |

## 2026 실무 트렌드

- **하네스의 기성품화** — LangChain이 deepagents를 "배터리 포함 에이전트 하네스"로
  밀면서, planning·가상 FS·서브에이전트·장기 메모리를 직접 조립하지 않고 하네스에서
  받아 쓰는 흐름이 표준화되고 있습니다.
- **Agent Skills(`SKILL.md`)의 프레임워크 횡단 확산** — Anthropic이 제안한 skills
  개념을 deepagents 등 다른 프레임워크가 그대로 채택했습니다. 폴더+`SKILL.md` 라는
  단순한 형식과 progressive disclosure(필요할 때만 본문 로드)가 사실상의 관례가 되는 중입니다.
- **장기실행 규율의 보편화** — "진행상황 파일 + 컨텍스트 리셋 + 구조화된 핸드오프"라는
  Anthropic식 장기실행 하네스 패턴이 특정 제품(Claude Code)의 트릭이 아니라 업계 공통
  운영 규율로 자리잡고 있습니다.

## 실전 레퍼런스

- [Deep Agents overview — LangChain 공식 문서](https://docs.langchain.com/oss/python/deepagents/overview) — deepagents의 구성요소(planning·FS·서브에이전트·메모리) 공식 레퍼런스
- [Using skills with Deep Agents — LangChain Blog](https://www.langchain.com/blog/using-skills-with-deep-agents) — deepagents에서 `SKILL.md` 를 로드하는 방법과 설계 배경
- [How we built our multi-agent research system — Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system) — 리드+서브에이전트 위임을 프로덕션에서 굴린 기록
- [State of Agent Engineering — LangChain](https://www.langchain.com/state-of-agent-engineering) — 에이전트 프로덕션 채택률과 하네스·스킬 도입 흐름을 보여주는 조사 보고서
- [Harrison Chase on Deep Agents — NVIDIA AI Podcast (YouTube)](https://www.youtube.com/watch?v=c-fsL0gsmo0) — deepagents 설계 철학을 창시자가 직접 설명

## 참고 자료

- [deepagents (GitHub)](https://github.com/langchain-ai/deepagents)
- [Deep Agents — Subagents 문서](https://docs.langchain.com/oss/python/deepagents/subagents)
- [Effective harnesses for long-running agents — Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Agent Skills — Anthropic](https://www.anthropic.com/news/skills)
- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)
