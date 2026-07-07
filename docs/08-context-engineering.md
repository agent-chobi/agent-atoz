# 08. 컨텍스트 엔지니어링

2026년 에이전트 품질을 가르는 것은 더 큰 모델이 아니라 **컨텍스트 창에 무엇을, 얼마나,
어떤 형태로 넣는가**입니다. 메모리([06](06-short-term-memory.md)·[07장](07-long-term-memory.md))가
"무엇을 저장할까"였다면, 컨텍스트 엔지니어링은 "저장한 것 중 **무엇을 지금 이 호출에
넣을까**"입니다. 이것이 프롬프트 엔지니어링을 넘어선, MAS의 핵심 규율입니다.

## 1. 왜 더 넣는 게 답이 아닌가

컨텍스트 창이 길다고 다 채우면 안 됩니다. 관련 컨텍스트가 대략 **50K 토큰을 넘어서면
성능이 눈에 띄게 저하**됩니다(정확도·지연·비용 모두). 대표적 실패 양상:

- **컨텍스트 오염(poisoning)**: 잘못된 정보가 한 번 들어가 계속 참조됨.
- **주의 분산(distraction)**: 관련 없는 내용이 신호를 묻어버림.
- **혼동(confusion)**: 서로 모순되는 정보로 판단이 흔들림.
- **Lost in the middle**: 긴 컨텍스트의 중간부는 실제로 잘 안 읽힘.

!!! danger "핵심 원칙"
    컨텍스트는 **예산(budget)**이다. 토큰은 유한한 자원이며, 넣을 후보가 아니라
    **꼭 필요한 것만** 넣는 것이 기본값이다.

## 2. 세 가지 전략: 선택 · 압축 · 격리

```mermaid
flowchart TB
    subgraph All["가용 정보 (메모리·도구결과·히스토리·문서)"]
        direction LR
        A1["대화 50턴"]
        A2["장기 기억 200건"]
        A3["도구 출력 10K줄"]
    end
    All --> SEL["① 선택(Selection)<br/>관련 top-k만 검색·주입"]
    SEL --> COMP["② 압축(Compression)<br/>요약·트림으로 토큰↓"]
    COMP --> ISO["③ 격리(Isolation)<br/>역할별 컨텍스트 분리"]
    ISO --> LLM["LLM 호출<br/>(≤ 예산)"]
```

### ① 선택(Selection) — 관련된 것만

전부가 아니라 **지금 작업에 관련된 것**만 고릅니다.

- 장기 기억은 벡터 검색으로 **top-k**만 회상(07장).
- 도구는 필요한 것만 노출 — 도구 100개를 다 주면 선택 정확도가 떨어집니다.
- RAG 문서도 재랭킹 후 상위 몇 개만.

### ② 압축(Compression) — 같은 뜻을 더 적은 토큰으로

대화가 길어지면 오래된 부분을 **잘라내거나(trim)** **요약(summarize)**합니다.

**trim_messages** — 최근 N 토큰만 남기기:

```python
from langchain_core.messages import trim_messages

trimmed = trim_messages(
    messages,
    strategy="last",          # 최근 메시지 우선 보존
    max_tokens=4000,
    token_counter=model,      # 모델의 토큰 카운터 사용
    start_on="human",         # 대화가 HumanMessage로 시작하도록
    include_system=True,      # 시스템 프롬프트는 유지
)
```

**요약 노드(summarization)** — 오래된 대화를 한 문단으로 접기:

```mermaid
flowchart LR
    H["긴 히스토리<br/>(40턴)"] --> N{"토큰 > 임계?"}
    N -->|"예"| SUM["요약 노드<br/>오래된 30턴 → 요약 1건"]
    N -->|"아니오"| PASS["그대로"]
    SUM --> NEW["요약 + 최근 10턴"]
```

오래된 메시지를 LLM으로 요약해 하나의 `SystemMessage`로 대체하고, 최근 몇 턴은 원문 유지.
LangGraph에는 이를 자동화하는 `SummarizationNode`/`langmem` 요약 유틸도 있습니다.

### ③ 격리(Isolation) — 컨텍스트를 나눠 담기

하나의 거대한 컨텍스트 대신 **역할별로 분리**합니다. 서브에이전트가 각자 자기 컨텍스트에서
일하고, 메인은 결과만 받습니다(→ [10장](10-subagents-deep-agents-skills.md)).

- 서브에이전트 격리: 리서치 워커의 10K줄 원자료는 워커 안에 두고, 메인엔 요약만.
- 상태 스키마 분리: 그래프 내부 상태와 LLM에 보이는 메시지를 구분.
- 샌드박스/파일: 큰 산출물은 컨텍스트가 아니라 파일·가상 FS에 두고 경로만 전달.

## 3. 공유 컨텍스트 계층과 라우팅

멀티에이전트에서는 "누가 무엇을 보는가"를 계층으로 설계합니다.

| 계층 | 내용 | 누가 봄 |
|------|------|---------|
| **전역(global)** | 목표·제약·공용 사실 | 모든 에이전트 |
| **역할(role)** | 그 역할에 필요한 정보만 | 해당 에이전트 |
| **로컬(local)** | 진행 중 스크래치·도구 원출력 | 자기 자신 |

**컨텍스트 라우팅** = 에이전트의 역할에 맞는 정보만 골라 전달하는 것. 코더에겐 코드·에러
로그를, 기획자에겐 요구사항·결정 로그를 준다 — 서로의 잡음을 나눠 갖지 않게 합니다.

!!! note "왜 격리가 압축보다 먼저인가"
    무작정 요약부터 하면 정작 필요한 디테일이 뭉개집니다. 먼저 **누가 무엇을 봐야 하는지**를
    계층으로 정리하면 각 에이전트의 컨텍스트가 자연히 작아져, 애초에 압축할 양이 줄어듭니다.
    즉 격리(설계)가 압축(사후 처리)보다 근본적인 해법입니다.

## 4. 핸드오프는 "전체"가 아니라 "요약"

swarm/supervisor에서 제어권을 넘길 때([00장](00-landscape.md) 패턴), 초심자는 전체 대화를
그대로 넘깁니다. 정석은 **요약된 핸드오프**입니다.

```mermaid
flowchart LR
    A["에이전트 A<br/>(30턴 대화)"] -->|"❌ 전체 히스토리"| Bad["B: 컨텍스트 폭발"]
    A -->|"✅ 요약 + 결정사항 + 다음할일"| Good["B: 깔끔한 시작"]
```

핸드오프 페이로드에 담을 것: **목표, 지금까지의 결론, 미해결 항목, 다음 액션**. 원본이
필요하면 스토어/파일 참조 경로만 함께 넘깁니다.

!!! tip "요약 핸드오프 체크리스트"
    - 결정된 사실(decisions)과 열린 질문(open questions)을 분리해 명시.
    - 숫자·ID·경로 등 **정확성이 중요한 값은 원문 그대로** 유지(요약이 뭉개지 않게).
    - "왜"보다 "무엇을 다음에"에 무게.

## 5. 정리: 컨텍스트 엔지니어의 루프

1. **관측**: 현재 컨텍스트 토큰을 계측(임계 50K 근처를 경보선으로).
2. **선택**: 관련 top-k만.
3. **압축**: 넘치면 trim/요약.
4. **격리**: 큰 작업은 서브에이전트/파일로 분리.
5. **핸드오프**: 넘길 땐 요약으로.

## 실습 코드

`examples/11_context_engineering.py` — 긴 대화 히스토리를 `trim_messages`로 자르고, 넘칠 때
LLM 요약으로 압축해 컨텍스트를 관리하는 예제.
([매핑표](../examples/README.md) 참고)

```bash
python examples/11_context_engineering.py
```

## 참고 자료

- [Effective context engineering for AI agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Context Engineering for Agents (LangChain)](https://blog.langchain.com/context-engineering-for-agents/)
- [How to trim messages (LangChain)](https://python.langchain.com/docs/how_to/trim_messages/)
- [How Long Contexts Fail (Drew Breunig)](https://www.dbreunig.com/2025/06/22/how-contexts-fail-and-how-to-fix-them.html)
