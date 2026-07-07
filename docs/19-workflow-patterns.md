# 19. 워크플로우 패턴

[02장](02-tool-use-agent-loop.md)에서 만든 에이전트 루프는 **모델이 흐름을 결정**했습니다
— 도구를 부를지, 몇 번 돌지 모두 모델 판단이었죠. 하지만 실무 작업의 상당수는 경로가
미리 정해져 있습니다: "요약하고 → 검증하고 → 번역한다". 이럴 때는 모델에게 흐름까지
맡길 이유가 없습니다. 이 챕터는 Anthropic 의 *Building Effective Agents* 가 정리한
**5가지 워크플로우 패턴**과, 가장 중요한 판단인 **Workflow vs Agent 선택 기준**,
그리고 [09장 멀티에이전트 패턴](09-multi-agent-patterns.md)과의 관계를 다룹니다.

## 1. Workflow vs Agent — 용어부터

Anthropic 은 "agentic system"을 두 부류로 나눕니다:

| | **Workflow** | **Agent** |
|--|--------------|-----------|
| 흐름 결정 | **코드**가 미리 정의한 경로 | **모델**이 매 스텝 동적으로 결정 |
| 예측 가능성 | 높음 (같은 입력 → 같은 경로) | 낮음 (경로가 실행마다 다름) |
| 토큰/지연 | 호출 수가 상수로 고정 | 루프 길이만큼 가변 |
| 디버깅 | 단계별 격리 용이 | 트레이싱 필수([13장](13-debugging-observability.md)) |
| 언제 | 하위 작업을 **미리 열거 가능**할 때 | 필요한 스텝 수를 **예측 불가**할 때 |

!!! tip "제1원칙: 워크플로우로 충분하면 에이전트를 만들지 마라"
    [00장](00-landscape.md)의 "가장 단순한 것부터"의 연장입니다. 단일 호출 → 워크플로우
    → 에이전트 순으로 올라가되, **각 단계는 아래 단계로 풀리지 않을 때만** 선택합니다.
    2026년 프로덕션의 지배적 구조도 "결정적 백본(워크플로우) + 필요한 지점에만 에이전트
    삽입"입니다.

## 2. Prompt Chaining — 직렬 분해 + 게이트

작업을 고정된 단계로 쪼개고, 각 호출의 출력을 다음 호출의 입력으로 넘깁니다. 핵심은
단계 사이의 **게이트(gate)** — LLM 이 아니라 *코드*가 중간 결과를 검증하는 지점입니다.

```mermaid
flowchart LR
    IN["입력"] --> L1["LLM 1<br/>초안"] --> G{"게이트<br/>(코드 검증)"}
    G -->|통과| L2["LLM 2<br/>다듬기"] --> OUT["출력"]
    G -->|실패| FIX["수정 단계"] --> L2
```

정확도를 위해 지연을 지불하는 패턴입니다 — 한 번에 다 시키는 것보다 각 호출이 쉬워져
품질이 오릅니다. 마케팅 카피 생성 → 길이/톤 검증 → 번역 같은 흐름이 전형입니다.

## 3. Routing — 분류 후 전문 핸들러로

입력을 먼저 **분류**하고, 카테고리별 전문 프롬프트/모델/도구로 보냅니다. 관심사가
분리되어 각 핸들러를 독립적으로 최적화할 수 있습니다.

```mermaid
flowchart LR
    IN["입력"] --> R["분류기 LLM"]
    R -->|billing| H1["결제 핸들러"]
    R -->|technical| H2["기술 핸들러"]
    R -->|general| H3["일반 핸들러"]
    H1 & H2 & H3 --> OUT["출력"]
```

!!! tip "분류는 구조화 출력으로"
    분류 결과를 자유 텍스트로 받으면 라우팅 코드가 깨집니다. [18장](18-structured-output.md)의
    `enum` 스키마로 라벨 자체를 강제하세요. 분류기는 저렴한 모델(haiku)로 내리는 것이
    비용 정석입니다.

## 4. Parallelization — 동시 실행 후 취합

독립적인 하위 작업을 **동시에** 던지고 결과를 합칩니다. 두 변형이 있습니다:

- **Sectioning** — 작업을 서로 다른 관점/구역으로 쪼개 병렬 처리 (보안·비용·성능 리뷰)
- **Voting** — 같은 작업을 여러 번 돌려 다수결/합의로 신뢰도를 올림 (판정, 취약점 탐지)

```mermaid
flowchart LR
    IN["입력"] --> P1["LLM A<br/>(관점 1)"] & P2["LLM B<br/>(관점 2)"] & P3["LLM C<br/>(관점 3)"]
    P1 & P2 & P3 --> AGG["취합(reduce)"] --> OUT["출력"]
```

지연은 "가장 느린 호출 1개" 수준으로 줄지만 비용은 호출 수만큼 늘어납니다.
Python 에서는 `AsyncAnthropic` + `asyncio.gather` 가 전부입니다 — 프레임워크 불필요.

## 5. Orchestrator-Worker — 동적 분해

오케스트레이터 LLM 이 작업을 **런타임에** 하위 작업으로 쪼개고, 워커들에게 위임한 뒤
결과를 합성합니다. Parallelization 과의 차이: 하위 작업의 **개수·내용을 미리 알 수 없어
모델이 정합니다**. 워크플로우에서 에이전트로 넘어가는 경계선상의 패턴입니다.

```mermaid
flowchart TB
    IN["입력"] --> O["🧠 Orchestrator<br/>작업 분해(동적)"]
    O --> W1["워커 1"] & W2["워커 2"] & W3["워커 …N"]
    W1 & W2 & W3 --> SYN["합성"] --> OUT["출력"]
```

[09장 5절](09-multi-agent-patterns.md)에서 본 orchestrator-worker 와 같은 개념입니다 —
09장은 이를 LangGraph `Send` API 로 멀티에이전트화하는 구현을 다룹니다.

## 6. Evaluator-Optimizer — 생성·평가 루프

한 LLM 이 생성하고 다른 LLM 이 **명시적 기준으로 평가·피드백**해 반복 개선합니다.
평가 기준이 명확하고, 반복이 실제로 품질을 올리는 작업(번역 뉘앙스, 코드 리뷰 반영)에
적합합니다.

```mermaid
flowchart LR
    IN["입력"] --> GEN["✍️ Generator"] --> EV["🧐 Evaluator"]
    EV -->|"기준 통과"| OUT["출력"]
    EV -->|"피드백"| GEN
```

!!! warning "반복 상한은 필수"
    [09장 6절](09-multi-agent-patterns.md)의 critique 패턴과 동일한 주의사항 — 상한 없는
    생성↔평가 루프는 무한 왕복과 비용 폭증으로 이어집니다. 최대 N회 + 탈출 조건을 코드로
    못 박으세요. 평가 기준이 모호하면 이 패턴 자체가 값을 못 합니다.

## 7. 09장(멀티에이전트)과의 관계

다섯 패턴은 **한 프로세스 안의 LLM 호출 배치**이고, 09장의 패턴은 이를 **독립 에이전트
(각자 도구·프롬프트·컨텍스트 소유)로 승격**한 것입니다. 대응 관계:

| 워크플로우 패턴 (19장) | 멀티에이전트 대응 (09장) | 승격 기준 |
|------------------------|--------------------------|-----------|
| Prompt Chaining | Sequential pipeline | 단계별로 도구/권한 분리가 필요할 때 |
| Routing | Supervisor | 핸들러가 다단계 대화를 소유해야 할 때 |
| Parallelization | Orchestrator-Worker (Send) | 워커가 도구를 쥐고 자율 판단해야 할 때 |
| Orchestrator-Worker | Orchestrator-Worker / Hierarchical | 그대로 확장 |
| Evaluator-Optimizer | Critique (생성·평가 분리) | 평가자에게 별도 컨텍스트가 필요할 때 |

같은 형태라도 멀티에이전트로 승격하면 토큰 오버헤드(+58~285%, [09장 1절](09-multi-agent-patterns.md))가
붙습니다. **워크플로우 버전으로 시작해, 전문화·병렬성·비평의 이득이 증명될 때만 승격**하세요.

## 따라하기

**사전 준비**:

```bash
pip install -r requirements.txt          # anthropic, python-dotenv 포함
# .env 에 ANTHROPIC_API_KEY=sk-ant-... 설정
```

**실행 명령**:

```bash
python examples/24_workflow_patterns.py
```

**기대 출력 예시**:

```text
=== 1) Prompt Chaining ===
[1단계] 한 줄 카피 초안: 회의록은 AI가, 결정은 당신이.
[게이트] 30자 이내 검증 통과
[2단계] 최종 카피: 회의록은 AI가 쓰고, 결정은 당신이 합니다.

=== 2) Routing ===
[분류] '환불 언제 되나요?' → billing
[billing 전문 응답] 환불은 결제 취소 후 영업일 기준 3~5일 내 처리됩니다. ...

=== 3) Parallelization ===
[병렬] 3개 관점 동시 분석
- 보안: 사내 문서 접근 권한 모델을 먼저 정의해야 ...
- 비용: 임베딩 배치 처리로 초기 인덱싱 비용을 ...
- 성능: 검색 지연이 사용자 경험을 좌우하므로 ...
[취합] 종합 권고: 권한 모델을 선결한 뒤 ...
```

**흔한 에러와 해결**:

| 에러 | 원인 | 해결 |
|------|------|------|
| `AuthenticationError` | API 키 누락/오타 | `.env` 의 `ANTHROPIC_API_KEY` 확인 |
| `RuntimeError: asyncio.run() cannot be called...` | Jupyter 등 이미 이벤트 루프가 도는 환경 | `await demo_parallel(...)` 로 직접 호출 |
| `RateLimitError` (429) | 병렬 호출이 조직 한도 초과 | gather 대상 수 축소 또는 지수 백오프 재시도 |
| 라우팅 분기 오동작 | 분류 결과가 자유 텍스트 | 예제처럼 `enum` 스키마로 강제([18장](18-structured-output.md)) |

## 실무 트레이드오프

| 패턴 | 지연 | 비용(호출 수) | 예측 가능성 | 주 리스크 |
|------|------|---------------|-------------|-----------|
| Prompt Chaining | 단계 수에 비례 ↑ | 단계 수 ×1 | 매우 높음 | 단계 과다 분해로 지연 낭비 |
| Routing | +분류 1회 | +1 | 높음 | 오분류가 전체 품질 좌우 |
| Parallelization | 최장 호출 1개 수준 ↓ | 병렬 폭 × | 높음 | 비용 배수, 취합 품질 |
| Orchestrator-Worker | 분해+합성 오버헤드 | 가변 | 중간 | 분해 품질에 전체가 종속 |
| Evaluator-Optimizer | 반복 횟수 × | 반복 × 2 | 중간 | 무한 루프, 모호한 평가 기준 |

## 설계 가이드 — 워크플로우 vs 에이전트 결정 프레임

§1의 구분을 실제 설계 결정으로 옮기려면 두 질문을 던집니다 — **절차가 확정적인가**
(하위 단계를 미리 열거할 수 있나), **입력이 다양한가**(들어오는 요청의 종류가 몇 가지인가).

### 2축 매트릭스

| | **입력 다양성 낮음**(요청 종류 한정) | **입력 다양성 높음**(요청이 제각각) |
|--|--------------------------------------|--------------------------------------|
| **절차 확정** | 단일 호출 또는 Prompt Chaining — 에이전트 불필요 | **Routing** 으로 분류 후, 카테고리별 확정 체인 |
| **절차 미확정** | **Orchestrator-Worker** — 분해만 동적, 실행은 통제 | **Agent** — 여기가 에이전트의 정당한 자리 |

대부분의 실무 요구는 좌상단~우상단에 있습니다. 우하단(진짜 에이전트)이라고 판단했다면
"절차를 정말 열거할 수 없는가"를 한 번 더 의심하세요 — 열거가 귀찮은 것과 불가능한
것은 다릅니다.

### 패턴 조합 — 패턴은 중첩된다

다섯 패턴은 배타적 선택지가 아니라 **합성 가능한 부품**입니다. 전형적 조합:

- **Routing → 카테고리별 Chaining** — 분류 후 각 핸들러가 자체 다단계 체인을 소유.
  고객지원 자동화의 표준 골격입니다.
- **Chaining 의 한 단계가 Parallelization** — "초안 → [보안·비용·성능 병렬 리뷰] →
  취합 → 수정"처럼 체인 중간에 팬아웃을 끼움.
- **Evaluator-Optimizer 를 마지막 게이트로** — 어떤 조합이든 출구 직전에 생성·평가
  루프 1개를 두면 품질 하한이 생김([17장](17-harness-engineering.md) 평가 게이트).
- **Orchestrator-Worker 의 워커가 확정 체인** — 분해는 모델이, 각 하위 작업 실행은
  결정적 워크플로우가. "결정적 백본 + 지점 에이전트"의 역방향 구도입니다.

조합할 때의 규칙 하나 — **단계 사이 계약은 반드시 구조화 출력으로 고정**하세요
([18장](18-structured-output.md)). 자유 텍스트로 잇는 순간 조합 지점이 최약점이 됩니다.

### 패턴별 실패 모드와 복구 지점

| 패턴 | 대표 실패 모드 | 복구 지점 설계 |
|------|----------------|----------------|
| Prompt Chaining | 중간 단계 품질 미달이 하류로 전파 | 각 게이트에서 실패 시 **해당 단계만 재시도** — 전체 재실행 금지 |
| Routing | 오분류 → 엉뚱한 핸들러 | 분류 confidence 낮으면 폴백 핸들러/사람에게, 오분류 로그를 평가셋으로([15장](15-evaluation-cost.md)) |
| Parallelization | 일부 브랜치 실패·지연 | 브랜치별 타임아웃 + 부분 결과로 취합 진행(전부 기다리지 않기) |
| Orchestrator-Worker | 분해 자체가 잘못됨(누락·중복) | 분해 결과를 스키마 검증 + 워커 수 상한, 실행 전 분해안 검토 게이트 |
| Evaluator-Optimizer | 수렴 실패로 무한 왕복 | 반복 상한 + "개선 없으면 조기 종료" + 최종 미달 시 인간 폴백 |

공통 원칙: 복구 지점은 **실패가 감지되는 곳이 아니라 상태를 되돌릴 수 있는 곳**에
둡니다. 게이트를 코드로 두는 이유(§2)가 바로 이것입니다 — 코드 게이트는 결정적이라
"실패 감지 자체가 실패하는" 일이 없습니다.

## 2026 실무 트렌드

- **"결정적 백본 + 지점 에이전트"가 승자 구조** — 2026년 프로덕션 컨센서스는 워크플로우가
  전체 흐름을 쥐고, 모호성 해소가 필요한 스텝에만 에이전트를 호출한 뒤 제어권을 백본으로
  회수하는 하이브리드입니다. 순수 자율 에이전트는 토큰·지연·비결정성 비용 때문에 소수파.
- **실패 원인은 인프라가 아니라 명세** — 멀티에이전트 실패의 약 79%가 명세·조정 문제라는
  연구가 인용되면서, "패턴을 늘리기 전에 각 스텝의 계약(입출력 스키마)을 고정하라"는
  실천이 확산 — [18장](18-structured-output.md)의 구조화 출력이 그 계약 도구입니다.
- **결정적 계산은 코드로 회수** — 산술·상태 조회·규칙 분기처럼 정답이 결정적인 스텝을
  LLM 에서 일반 코드로 되돌리는 리팩터링이 비용 최적화의 첫 항목으로 자리잡았습니다.

## 실전 레퍼런스

- [Building Effective Agents (Anthropic 공식)](https://www.anthropic.com/research/building-effective-agents) — 이 챕터의 원전. 5패턴 + workflow/agent 구분의 출처.
- [How We Build Effective Agents — Barry Zhang, Anthropic (AI Engineer Summit, YouTube)](https://www.youtube.com/watch?v=D7_ipDqhtwk) — 원저자가 직접 설명하는 컨퍼런스 발표.
- [AI Agents and Deterministic Workflows: A Spectrum (deepset 기술블로그)](https://www.deepset.ai/blog/ai-agents-and-deterministic-workflows-a-spectrum) — 워크플로우↔에이전트를 이분법이 아닌 스펙트럼으로 보는 실무 관점.
- [The 2026 Guide to AI Agent Workflows (Vellum)](https://www.vellum.ai/blog/agentic-workflows-emerging-architectures-and-design-patterns) — 패턴별 프로덕션 아키텍처 사례 모음.

## 참고 자료

- [Building Effective Agents — Anthropic](https://www.anthropic.com/research/building-effective-agents)
- [09장 멀티에이전트 패턴](09-multi-agent-patterns.md) — 패턴의 멀티에이전트 승격판
- [18장 구조화된 출력](18-structured-output.md) — 스텝 간 계약 고정
- 실습 코드: [`examples/24_workflow_patterns.py`](https://github.com/agent-chobi/agent-atoz/blob/main/examples/24_workflow_patterns.py)
