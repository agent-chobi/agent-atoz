# 03. LangChain 기초 (LCEL)

앞선 [02장](02-tool-use-agent-loop.md)에서는 Anthropic SDK로 **에이전트 루프를 직접**
짜 봤습니다. 매번 `messages` 리스트를 관리하고, `stop_reason`을 분기하고, 도구 결과를
되돌려 넣는 보일러플레이트가 반복됐죠. LangChain은 이 반복을 **재사용 가능한 부품**으로
바꿉니다. 이 챕터의 핵심은 두 가지입니다. (1) **LCEL**로 프롬프트·모델·파서를 파이프처럼
잇는 법, (2) 그리고 **언제 이 추상화가 값을 하고 언제 과한가**를 판단하는 눈입니다.

## 1. LangChain은 무엇을 추상화하나

LangChain의 존재 이유는 **"프로바이더 교체 가능성"과 "조합 가능성"** 입니다. 아래 세 조각이
표준 인터페이스(`Runnable`)로 통일되어 있어서, 서로 자유롭게 연결·교체됩니다.

| 조각 | 역할 | 대표 클래스 |
|------|------|-------------|
| **Prompt** | 변수를 받아 메시지로 렌더링 | `ChatPromptTemplate` |
| **Model** | 메시지 → 응답 | `ChatAnthropic`, `ChatOpenAI` |
| **Parser** | 응답 → 원하는 타입 | `StrOutputParser`, `PydanticOutputParser` |

`ChatAnthropic`은 `langchain-anthropic` 패키지가 제공하며, 내부적으로 우리가 [01장](01-llm-api-basics.md)에서
본 `client.messages.create(...)`를 감쌉니다. 즉 **없던 기능이 생기는 게 아니라, 같은 API가
표준 인터페이스로 포장**되는 것입니다.

## 2. LCEL — 파이프로 잇는 체인

LCEL(LangChain Expression Language)은 파이썬 `|` 연산자로 `Runnable`을 잇는 문법입니다.
왼쪽의 출력이 오른쪽의 입력으로 흐릅니다 — 유닉스 파이프와 같은 감각입니다.

```python
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_messages([
    ("system", "너는 {topic} 전문가다. 세 문장으로 답하라."),
    ("human", "{question}"),
])
model = ChatAnthropic(model="claude-opus-4-8", max_tokens=1024)
parser = StrOutputParser()

chain = prompt | model | parser          # ← LCEL 파이프
answer = chain.invoke({"topic": "분산 시스템", "question": "왜 합의가 어려운가?"})
print(answer)                            # 이미 str (파서가 .content 추출)
```

```mermaid
flowchart LR
    IN["입력 dict<br/>{topic, question}"] --> P["ChatPromptTemplate<br/>→ 메시지 목록"]
    P --> M["ChatAnthropic<br/>→ AIMessage"]
    M --> O["StrOutputParser<br/>→ str"]
    O --> OUT["최종 문자열"]
```

파이프로 조립된 `chain` 역시 하나의 `Runnable`입니다. 그래서 **모든 조각이 같은 메서드**를
공유합니다 — 이게 LCEL이 주는 진짜 가치입니다.

| 메서드 | 용도 |
|--------|------|
| `.invoke(x)` | 단건 동기 실행 |
| `.batch([x1, x2])` | 여러 입력 병렬 처리 |
| `.stream(x)` | 토큰 스트리밍(제너레이터) |
| `.ainvoke` / `.astream` | 비동기 버전 |

!!! tip "스트리밍이 공짜"
    `chain.stream({...})`를 호출하면 파이프 전체가 자동으로 스트리밍 모드가 됩니다.
    SDK에서 직접 `stream=True`를 다루던 것과 달리, 체인을 바꾸지 않고 호출만 바꾸면 됩니다.

`.batch`도 같은 원리입니다. 입력 리스트를 넘기면 내부적으로 병렬 실행됩니다 — 여러 문서를
한 번에 요약·분류할 때 유용합니다.

```python
inputs = [
    {"topic": "OS", "question": "컨텍스트 스위칭이란?"},
    {"topic": "DB", "question": "인덱스는 왜 빠른가?"},
]
answers = chain.batch(inputs)     # [str, str] — 순서 보존, 병렬 처리
```

### 파서 교체 — 구조화된 출력

`StrOutputParser` 대신 다른 파서를 끼우면 출력 타입이 바뀝니다. 파이프의 앞 두 조각은
그대로 두고 **마지막 조각만 교체**하면 되는 게 LCEL의 조합성입니다. 예를 들어 Pydantic
모델로 구조화하려면 `.with_structured_output`을 쓰는 게 2026년 권장 경로입니다.

```python
from pydantic import BaseModel, Field

class Verdict(BaseModel):
    sentiment: str = Field(description="positive | negative | neutral")
    score: float = Field(description="0.0~1.0 확신도")

structured = ChatAnthropic(model="claude-opus-4-8").with_structured_output(Verdict)
v = structured.invoke("이 리뷰 감성 분석: '배송은 느렸지만 제품은 훌륭했다'")
print(v.sentiment, v.score)      # 이미 Verdict 인스턴스 (검증 완료)
```

## 3. 도구 바인딩 — `.bind_tools`

에이전트를 만들려면 모델이 도구를 호출할 수 있어야 합니다. LangChain은 파이썬 함수에
`@tool` 데코레이터만 붙이면 **스키마를 자동 추론**합니다(01·02장에서 손으로 짠 JSON Schema를
대신 만들어 줍니다).

```python
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """주어진 도시의 현재 날씨를 반환한다."""   # ← docstring이 도구 설명이 됨
    return f"{city}: 맑음, 24도"

model_with_tools = ChatAnthropic(model="claude-opus-4-8", max_tokens=1024).bind_tools([get_weather])
ai = model_with_tools.invoke("서울 날씨 알려줘")

# 모델이 도구를 부르기로 하면 tool_calls에 구조화되어 담긴다
for call in ai.tool_calls:
    print(call["name"], call["args"])     # get_weather {'city': '서울'}
```

`.bind_tools`는 도구 목록을 모델에 "묶어" 새 `Runnable`을 돌려줍니다. 응답의
`ai.tool_calls`는 프로바이더별 포맷 차이를 흡수한 **표준 형태**입니다 — Anthropic이든
OpenAI든 같은 코드로 읽습니다. 실제 도구 실행·결과 반환 루프는 [04장](04-langgraph-state-graph.md)의
LangGraph가 담당하게 됩니다.

## 4. 언제 LangChain이 유용하고, 언제 과한가

추상화는 공짜가 아닙니다. **디버깅할 층이 하나 더 생기고**, 버전 간 API 변화에 노출되며,
문제가 생기면 "내 코드인지 프레임워크인지"를 먼저 가려야 합니다. 아래 기준으로 판단하세요.

| 상황 | 권장 |
|------|------|
| 프로바이더를 바꿀 가능성이 있다 | ✅ LangChain (인터페이스 통일) |
| 프롬프트·파서·도구를 여러 조합으로 재사용 | ✅ LCEL |
| 배치/스트리밍/비동기를 무료로 얻고 싶다 | ✅ LCEL |
| LangGraph·LangSmith 생태계를 함께 쓴다 | ✅ (도구가 `Runnable`이면 바로 물림) |
| 단발성 스크립트, Claude 한 곳만 호출 | ❌ 그냥 `anthropic` SDK |
| 프롬프트 하나 + 단순 파싱 | ❌ 추상화 비용이 이득보다 큼 |
| 저수준 동작을 완전히 통제해야 함 | ❌ SDK 직접 |

!!! warning "추상화 비용은 실재한다"
    "LCEL이 있으니 무조건 LangChain" 은 안티패턴입니다. **[00장](00-landscape.md)의 제1원칙 —
    가장 단순한 것부터** 는 여기서도 유효합니다. Claude 하나에 프롬프트 하나면
    `anthropic` SDK 직접 호출이 더 읽기 쉽고 디버깅도 쉽습니다. LangChain은
    **조합·교체·생태계**가 필요할 때 값을 합니다.

!!! note "LangChain vs LangGraph"
    LangChain(LCEL)은 **선형 파이프라인**에 강합니다. 하지만 조건 분기, 반복 루프,
    상태 누적, 중단·재개(HITL) 같은 **제어 흐름**이 필요하면 그래프 기반의 LangGraph가
    정답입니다. 실제로 에이전트 루프는 다음 챕터에서 LangGraph로 구현합니다.

## 5. 실습 코드

- [`examples/05_langchain_lcel.py`](../examples/05_langchain_lcel.py) — `ChatAnthropic` +
  `ChatPromptTemplate` + `StrOutputParser`를 LCEL로 잇고, `.invoke`·`.stream`·`.bind_tools`까지
  한 파일에서 시연합니다.

실행:

```bash
pip install -r requirements.txt
python examples/05_langchain_lcel.py
```

## 참고 자료

- [LangChain (OSS Python) 개요](https://docs.langchain.com/oss/python/langchain/overview)
- [LCEL / Runnable 인터페이스](https://python.langchain.com/docs/concepts/lcel/)
- [langchain-anthropic ChatAnthropic 레퍼런스](https://python.langchain.com/docs/integrations/chat/anthropic/)
- [도구 호출(tool calling) 가이드](https://docs.langchain.com/oss/python/langchain/tools)
