# 06. 단기 메모리 (체크포인터)

에이전트가 "방금 무슨 얘기를 했지?"를 기억하려면 **대화 한 세션(thread)의 상태를
어딘가에 저장**해야 합니다. LangGraph에서 이 역할을 하는 것이 **체크포인터(checkpointer)**
입니다. 그래프가 노드를 한 스텝 실행할 때마다 상태 스냅샷을 저장하고, 같은 `thread_id`로
다시 호출하면 그 상태를 이어받습니다. 이것이 **단기 메모리** — 하나의 스레드 안에서만
유지되는, 대화 맥락의 영속화입니다.

!!! note "단기 vs 장기 한 줄 정리"
    - **단기(이 챕터)** = *thread 단위* 체크포인터. "이 대화"의 메시지·상태를 잇는다.
    - **장기([07장](07-long-term-memory.md))** = *cross-thread* 스토어. "이 사용자"에 대한 사실을
      여러 대화에 걸쳐 기억한다.

## 1. 체크포인터란

체크포인터는 그래프의 각 **super-step**마다 상태를 **체크포인트(checkpoint)**로 저장합니다.
체크포인트에는 그 시점의 채널 값(예: `messages`), 다음 실행할 노드, 메타데이터가 담깁니다.
게임의 **세이브 파일**과 같은 개념입니다 — 매 장면(스텝)마다 자동 저장되고, 같은 슬롯
(`thread_id`)을 열면 마지막 지점부터 이어서 플레이하며, 과거 세이브로 되돌아갈 수도 있습니다.

```mermaid
flowchart LR
    subgraph T["thread_id = 'user-42'"]
        C0["ckpt-0<br/>(초기)"] --> C1["ckpt-1<br/>사용자: 내 이름은 밥"]
        C1 --> C2["ckpt-2<br/>AI: 반가워요 밥"]
        C2 --> C3["ckpt-3<br/>사용자: 내 이름 뭐였지?"]
        C3 --> C4["ckpt-4<br/>AI: 밥이에요"]
    end
    Store[("체크포인터<br/>InMemory / Sqlite")]
    C0 -.저장.-> Store
    C4 -.복원.-> Store
```

같은 `thread_id`로 그래프를 다시 호출하면 마지막 체크포인트에서 상태를 **복원**하므로,
이전 대화를 프롬프트에 수동으로 다시 넣지 않아도 됩니다.

## 2. 체크포인터 종류

| 클래스 | import | 저장 위치 | 용도 |
|--------|--------|-----------|------|
| `InMemorySaver` | `langgraph.checkpoint.memory` | RAM(프로세스 메모리) | 테스트·데모. 재시작하면 사라짐 |
| `SqliteSaver` | `langgraph.checkpoint.sqlite` | 로컬 `.sqlite` 파일 | 단일 노드 개발·소규모 영속화 |
| `AsyncSqliteSaver` | `langgraph.checkpoint.sqlite.aio` | 로컬 파일(async) | 비동기 앱 |
| `PostgresSaver` | `langgraph.checkpoint.postgres` | Postgres | 프로덕션·다중 인스턴스 |

!!! warning "설치 주의"
    `SqliteSaver`는 코어에 없습니다. 별도 패키지가 필요합니다:
    `pip install langgraph-checkpoint-sqlite`. 이 저장소의 `requirements.txt`에 포함돼 있습니다.

```python
# InMemory — 가장 간단
from langgraph.checkpoint.memory import InMemorySaver
checkpointer = InMemorySaver()

# Sqlite — 파일로 영속화 (컨텍스트 매니저)
from langgraph.checkpoint.sqlite import SqliteSaver
with SqliteSaver.from_conn_string("checkpoints.sqlite") as checkpointer:
    agent = create_react_agent(model, tools, checkpointer=checkpointer)
    ...
```

## 3. thread_id — 대화의 열쇠

체크포인터를 붙였다면, 호출할 때 **어떤 스레드인지**를 `config`로 알려줘야 합니다.

```python
config = {"configurable": {"thread_id": "user-42"}}
agent.invoke({"messages": [("user", "내 이름은 밥이야")]}, config)
agent.invoke({"messages": [("user", "내 이름 뭐였지?")]}, config)  # → "밥"
```

`thread_id`가 다르면 완전히 별개의 대화입니다. 한 사용자의 여러 세션을 구분하거나,
멀티 유저 서비스에서 사용자별 대화를 격리할 때 이 값을 키로 씁니다.

!!! tip "thread_id 설계"
    실무에선 `f"{user_id}:{session_id}"`처럼 조합해 씁니다. 값은 255자 미만으로 유지하세요.

## 4. 상태 조회 · 타임트래블 · 수정

체크포인터가 있으면 컴파일된 그래프에서 세 가지 강력한 API가 열립니다.

### get_state — 현재 스냅샷

```python
snap = agent.get_state(config)
snap.values      # 현재 채널 값 (예: {"messages": [...]})
snap.next        # 다음에 실행될 노드 (비어 있으면 완료)
snap.config      # 이 스냅샷의 checkpoint_id 포함
```

### get_state_history — 타임트래블

과거 모든 체크포인트를 **최신→과거 순**으로 순회합니다. 각 스냅샷은 자신의
`checkpoint_id`를 갖고 있어, 특정 시점으로 **되감기(replay)**할 수 있습니다.

```python
for snap in agent.get_state_history(config):
    print(snap.config["configurable"]["checkpoint_id"], snap.next)
```

### 되감기(replay)와 분기(fork)

과거 스냅샷의 `config`(= checkpoint_id 포함)를 그대로 `invoke`에 넘기면 그 시점부터
**다시 실행**합니다. 여기에 다른 입력을 주면 "만약 그때 다르게 답했다면?"의 분기가 생깁니다.

```mermaid
flowchart TB
    C2["ckpt-2"] --> C3["ckpt-3 (원래 경로)"]
    C2 -->|"과거 config로 재실행"| C3b["ckpt-3' (분기)"]
```

### update_state — 상태 직접 수정

사람이 개입(HITL)해 상태를 고쳐 넣을 때 씁니다. 리듀서가 있는 채널(`messages` 등)은
리듀서 규칙에 따라 병합됩니다.

```python
agent.update_state(config, {"messages": [("user", "정정: 내 이름은 로버트야")]})
```

## 5. resume — 중단된 실행 이어가기

`interrupt`([04장](04-langgraph-state-graph.md))로 그래프가 사람 승인을 기다리며 멈추면,
그 상태가 체크포인트에 저장됩니다. 나중에 같은 `thread_id`로 `Command(resume=...)`을 주면
**멈춘 지점부터** 이어서 실행합니다. 즉 단기 메모리는 HITL의 기술적 토대이기도 합니다.

## 따라하기

이 챕터의 예제는 [`examples/09_short_term_memory.py`](https://github.com/agent-chobi/agent-atoz/blob/main/examples/09_short_term_memory.py)
입니다 — `create_react_agent` + `SqliteSaver`로 같은 `thread_id`에서 멀티턴 기억을 유지하고,
`get_state_history`로 타임트래블을 출력합니다. (예제↔챕터 대응은
[매핑표](https://github.com/agent-chobi/agent-atoz/blob/main/examples/README.md) 참고)

**1) 사전 준비**

```bash
pip install -r requirements.txt   # langgraph-checkpoint-sqlite 포함
copy .env.example .env            # macOS/Linux는 cp — ANTHROPIC_API_KEY 채우기
```

**2) 실행**

```bash
python examples/09_short_term_memory.py
```

**3) 기대 출력 요지**

- 같은 thread에서 세 턴: 이름("밥")과 색("파랑")을 알려준 뒤 되물으면 에이전트가 **기억해서**
  답합니다.
- `get_state` 스냅샷: 누적 메시지 개수와 다음 실행 노드(완료면 빈 값)가 출력됩니다.
- 타임트래블: 과거 체크포인트가 최신→과거 순으로 나열되며, 스텝마다 메시지 수가 늘어난
  흔적이 보입니다.
- 다른 `thread_id`: 같은 질문에 "모른다"고 답합니다 — 스레드 격리의 증명.

**4) 흔한 에러**

| 증상 | 원인 → 해결 |
|------|-------------|
| `ANTHROPIC_API_KEY 가 설정되지 않았습니다` (SystemExit) | `.env` 미작성 → 키 입력 |
| `ModuleNotFoundError: langgraph.checkpoint.sqlite` | `SqliteSaver`는 코어에 없음 → `pip install langgraph-checkpoint-sqlite` (requirements.txt에 포함) |
| 재실행했더니 이전 실행의 대화가 이어짐 | 정상 동작 — `checkpoints.sqlite` 파일에 영속화됨. 초기화하려면 파일 삭제 |

## 설계 가이드 — 어떤 DB에 무엇이 저장되는가

체크포인터를 "붙이는" 것과 "운영하는" 것은 다른 문제입니다. 이 섹션은 백엔드 선택 기준,
DB에 실제로 저장되는 데이터의 구조, 그리고 보존·격리 같은 운영 설계를 다룹니다.

### 백엔드 선택: 4가지 선택지

2절 표(클래스·설치)와 아래 실무 트레이드오프 표(운영 특성)에 더해, **설계 관점**의
비교입니다. Redis 백엔드는 `langgraph-checkpoint-redis`(Redis 공식 유지보수)로 제공됩니다.

| 기준 | `InMemorySaver` | `SqliteSaver` | `PostgresSaver` | `RedisSaver` |
|------|-----------------|---------------|-----------------|--------------|
| 동시 쓰기 | 단일 프로세스 한정 | 파일 잠금 — 동시 쓰기 병목 | MVCC — 다중 워커 안전 | 고QPS·저지연 처리 |
| 수평 확장 | 불가 | 불가(파일 공유 곤란) | 커넥션 풀 + 리드 리플리카 | 클러스터 모드 |
| 백업·복구 | 없음 | 파일 복사 | `pg_dump`·PITR 등 성숙한 도구 | RDB/AOF 스냅숏 |
| 보존(TTL) | 프로세스 수명 | 수동 삭제 | 수동 삭제(내장 TTL 없음) | `ttl` 옵션 **내장** |
| 추천 | 테스트·데모 | 로컬·단일 프로세스 | **프로덕션 기본값** | 저지연·휘발성 세션 |

프로덕션 기본값이 Postgres인 이유: 체크포인트 저장은 스텝마다 여러 행을 함께 넣는
**트랜잭션 일관성**이 필요한 쓰기 부하이고, 대부분의 팀이 이미 Postgres 운영 경험
(백업·모니터링·마이그레이션)을 갖고 있기 때문입니다.

```python
# pip install langgraph-checkpoint-postgres "psycopg[binary,pool]"
from langgraph.checkpoint.postgres import PostgresSaver

DB_URI = "postgresql://user:pass@localhost:5432/agentdb"
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()          # 최초 1회 — 테이블 생성·마이그레이션
    graph = builder.compile(checkpointer=checkpointer)
    graph.invoke({"messages": [("user", "안녕")]},
                 {"configurable": {"thread_id": "user-42:conv-7"}})
```

!!! warning "setup() 주의 2가지"
    - `Connection`을 직접 만들어 넘길 때는 `autocommit=True`가 아니면 `setup()`의
      테이블 생성이 커밋되지 않을 수 있습니다.
    - 비동기 웹 서버(FastAPI 등)에서는 `AsyncPostgresSaver` + 커넥션 풀을 쓰세요.

### 실제로 무엇이 저장되는가

`setup()`은 Postgres에 4개 테이블을 만듭니다.

| 테이블 | 역할 |
|--------|------|
| `checkpoints` | 스텝마다 1행 — 스냅샷 본체(JSONB)와 메타데이터 |
| `checkpoint_blobs` | 대형 채널 값(`messages` 등)의 직렬화 바이너리(BYTEA) |
| `checkpoint_writes` | 스텝 도중 각 노드가 낸 쓰기(pending writes) — 부분 실패 복구용 |
| `checkpoint_migrations` | 라이브러리가 관리하는 스키마 버전 |

`checkpoints` 한 행을 논리적으로 펼치면 이런 모양입니다(개념 예시):

```json
{
  "thread_id": "user-42:conv-7",                 // 대화(스레드) 식별자
  "checkpoint_ns": "",                           // 서브그래프 구분 네임스페이스
  "checkpoint_id": "1f05d2b0-...-8004",          // 이 스냅샷의 ID(시간순 정렬 가능)
  "parent_checkpoint_id": "1f05d2b0-...-8003",   // 직전 스냅샷 → 타임트래블 체인
  "checkpoint": {
    "v": 1,
    "ts": "2026-07-08T04:32:11.220445+00:00",
    "channel_values": {"messages": "<checkpoint_blobs 참조>"},
    "channel_versions": {"messages": "00000005.0.52..."},
    "versions_seen": {"agent": {"messages": "00000004.0.13..."}}
  },
  "metadata": {"source": "loop", "step": 4, "writes": {"agent": "..."}, "parents": {}}
}
```

- **channel_values**가 상태의 본체입니다. `messages`처럼 크고 자주 바뀌는 채널 값은
  JSONB에 인라인되지 않고 `JsonPlusSerializer`(ormsgpack 기반 — msgpack, 실패 시 확장
  JSON 폴백)로 직렬화되어 **`checkpoint_blobs`에 채널·버전 단위로 분리 저장**되고,
  본체에는 버전 참조만 남습니다. 바뀌지 않은 채널이 스텝마다 중복 저장되지 않는 이유입니다.
- **metadata.source**는 이 체크포인트가 생긴 이유입니다 — `input`(사용자 입력),
  `loop`(그래프 스텝), `update`(`update_state`), `fork`(분기).
- 노드 실행 도중 프로세스가 죽으면 성공한 노드의 쓰기가 `checkpoint_writes`에 남아 있어,
  재개 시 그 노드들을 다시 실행하지 않습니다.

!!! danger "직렬화 보안"
    blob은 msgpack 바이너리라, DB 쓰기 권한을 가진 공격자가 악성 객체를 심으면 역직렬화
    시 코드 실행으로 이어질 수 있습니다(CVE-2025-64439 계열). 환경 변수
    `LANGGRAPH_STRICT_MSGPACK=true`로 역직렬화 허용 타입을 제한하세요 — 아래 트렌드
    섹션의 RCE 사례와 같은 맥락입니다.

### 운영 설계 3가지

**1) 증가율과 보존 정책.** 체크포인트는 **super-step마다 1개** 생깁니다. ReAct 한 턴이
3~5스텝이면 하루 1만 턴 서비스는 하루 3~5만 행 + 채널별 blob이 쌓입니다. OSS
`PostgresSaver`/`SqliteSaver`에는 **내장 TTL이 없으므로** 직접 정리합니다 —
`checkpointer.delete_thread(thread_id)`로 스레드 단위 삭제, 또는 비활성 스레드를 지우는
배치 SQL. 반면 Redis 백엔드는 `ttl={"default_ttl": 10080, "refresh_on_read": True}`
(분 단위, 읽을 때 연장)처럼 **자동 만료가 내장**돼 있고, 관리형(LangSmith Deployment)은
설정으로 TTL을 지정합니다.

**2) thread_id 설계와 멀티테넌시.** `f"{user_id}:{conversation_id}"` 합성이 관례입니다
(3절 팁의 확장 — 사용자별 대화 목록 조회와 사용자 단위 일괄 삭제가 쉬워집니다).
주의: 체크포인터에는 권한 개념이 없어서 **남의 thread_id를 알면 남의 대화를 읽습니다**.
클라이언트가 보낸 값을 그대로 쓰지 말고, 서버에서 인증된 user_id로 접두사를 강제하고
조회 전 소유권을 검증하세요. 테넌트 분리가 계약 요건이면 접두사 수준이 아니라
스키마/DB 분리까지 고려합니다.

**3) 스키마 마이그레이션.** 테이블 스키마는 라이브러리 소유입니다 —
`checkpoint_migrations`가 버전을 추적하고, 패키지 업그레이드 후 `setup()`을 재실행하면
필요한 마이그레이션이 적용됩니다. 테이블을 직접 ALTER 하지 마세요. 반면 **상태 스키마**
(State TypedDict)를 바꾸면 옛 체크포인트와 어긋날 수 있으니, 필드 추가는 기본값과 함께,
필드 제거·개명은 구버전 스레드가 만료된 뒤에 하는 것이 안전합니다.

### 결정 트리

```mermaid
flowchart TD
    A["체크포인터 선택"] --> B{"재시작 후에도<br/>대화가 남아야?"}
    B -->|아니오| M["InMemorySaver"]
    B -->|예| C{"단일 프로세스<br/>(CLI·데스크톱)?"}
    C -->|예| S["SqliteSaver"]
    C -->|아니오| D{"세션이 짧고<br/>자동 만료가 필요?"}
    D -->|"예 — 저지연·TTL"| R["RedisSaver"]
    D -->|"아니오 — 내구성 우선"| P["PostgresSaver ★ 기본값"]
```

## 실무 트레이드오프

세 저장소는 기능이 같고 **운영 특성**이 다릅니다. "어디에 저장되는가"가 곧
"어떤 서비스까지 감당하는가"를 결정합니다.

| 기준 | `InMemorySaver` | `SqliteSaver` | `PostgresSaver` |
|------|-----------------|---------------|-----------------|
| 영속성 | 프로세스 종료 시 소멸 | 로컬 파일로 유지 | DB 서버에 유지 |
| 동시성·다중 인스턴스 | 불가(단일 프로세스) | 단일 노드 위주 | 다중 워커·수평 확장 |
| 운영 부담 | 없음 | 거의 없음(파일 하나) | 백업·마이그레이션·모니터링 필요 |
| 설치 | 코어 포함 | `langgraph-checkpoint-sqlite` | `langgraph-checkpoint-postgres` + 최초 `.setup()` |
| 적합 | 단위 테스트·노트북 데모 | CLI 앱·소규모 영속화 | 프로덕션 웹 서비스 |

운영을 직접 감당하기 싫다면 관리형(LangSmith Deployment, 구 LangGraph Platform)이
체크포인터를 대신 운영해 줍니다.

!!! danger "단기 메모리의 한계"
    스레드가 길어지면 `messages`가 무한정 쌓여 컨텍스트 창을 넘고 비용이 폭증합니다.
    체크포인터는 "저장"만 할 뿐 "줄이기"는 하지 않습니다. 압축·요약은
    [08장 컨텍스트 엔지니어링](08-context-engineering.md)에서 다룹니다.

## 2026 실무 트렌드

- **"개발은 InMemory/Sqlite, 프로덕션은 Postgres"가 공식 권고로 정착** — 공식 레퍼런스
  문서가 `InMemorySaver`를 "디버깅·테스트 전용"으로 명시하고, 프로덕션에는
  `PostgresSaver`(또는 관리형 배포)를 권합니다.
- **체크포인터 백엔드 생태계 확장** — Redis가 `langgraph-checkpoint-redis`를 공식 지원하며
  저지연 읽기/쓰기·TTL 자동 만료를 내세우고, AWS도 `langgraph-checkpoint-aws`와 DynamoDB
  기반 내구성 에이전트 패턴을 내놓는 등 벤더 공식 구현이 경쟁 중입니다.
- **체크포인터가 보안 공격면으로 부상** — 2026년 Check Point Research가 SQLite/Redis
  체크포인터의 SQL 인젝션 + 역직렬화 체인으로 원격 코드 실행이 가능함을 공개했습니다
  (이후 패치됨). 체크포인터 라이브러리의 **버전 고정과 신속한 업그레이드**, 그리고
  `get_state_history` 필터에 사용자 입력을 그대로 넘기지 않기가 실무 수칙이 됐습니다.

## 실전 레퍼런스

- [Build smarter AI agents with LangGraph and Redis](https://redis.io/blog/langgraph-redis-build-smarter-ai-agents-with-memory-persistence/) —
  Redis 체크포인터(단기) + Redis Store(장기) 조합을 다룬 벤더 공식 가이드.
- [From SQLi to RCE: Exploiting LangGraph's Checkpointer](https://research.checkpoint.com/2026/from-sqli-to-rce-exploiting-langgraphs-checkpointer/) —
  체크포인터 취약점 체인을 분석한 Check Point Research 기술 블로그(패치 완료된 사례 연구).
- [Build durable AI agents with LangGraph and Amazon DynamoDB](https://aws.amazon.com/blogs/database/build-durable-ai-agents-with-langgraph-and-amazon-dynamodb/) —
  DynamoDB를 체크포인터 백엔드로 쓰는 AWS 공식 블로그.
- [LangGraph v0.2: 새 체크포인터 라이브러리](https://blog.langchain.com/langgraph-v0-2/) —
  체크포인터가 `checkpoint-sqlite`/`checkpoint-postgres` 별도 패키지로 분리된 배경(공식 블로그).

## 참고 자료

- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Checkpointers 레퍼런스](https://reference.langchain.com/python/langgraph/checkpoints)
- [langgraph-checkpoint-sqlite (PyPI)](https://pypi.org/project/langgraph-checkpoint-sqlite/)
- [Time Travel — LangGraph](https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/time-travel/)
