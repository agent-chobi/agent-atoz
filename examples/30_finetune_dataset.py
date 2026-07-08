"""
30_finetune_dataset.py — 에이전트 트레이스 → 도구 호출 파인튜닝 데이터셋 (docs/26-finetuning-agents.md)

무엇을 보여주나
---------------
프로덕션 에이전트의 실행 트레이스(JSON)를 도구 호출(tool-use) 파인튜닝용
학습 데이터셋(JSONL, messages 포맷)으로 변환한다. 26장 3절의 파이프라인 그대로:

  트레이스 → [품질 필터 3겹] → [messages+tools 포맷 변환] → JSONL 저장
              ① 성공 트레이스만
              ② 중복 제거(요청+도구 시퀀스 해시)
              ③ 길이 필터(너무 짧거나 긴 것 제외)

이 예제는 **외부 API가 필요 없다** — 샘플 트레이스 6건이 파일에 내장되어
있고, LLM 호출 없이 순수 파이썬으로 동작한다. 실제 학습 실행은 파일 하단의
주석(개념 스케치)을 참고.

실행법
------
  pip install python-dotenv     # API 키 불필요
  python examples/30_finetune_dataset.py

[기대 출력 예시]
  === 1) 품질 필터 ===
  입력 트레이스: 6건
  [필터 ①] 성공 트레이스만  : 6 → 4건 (에러/미완료 2건 제외)
  [필터 ②] 중복 제거        : 4 → 3건 (동일 요청·도구 시퀀스 1건 제외)
  [필터 ③] 길이 필터        : 3 → 2건 (도구 호출 0회 no-op 1건 제외)

  === 2) JSONL 변환 ===
  finetune_dataset.jsonl 저장: 2 레코드
  [첫 레코드 구조]
  - tools: 1개 (search_docs)
  - messages: 5턴 (system → user → assistant(tool_calls) → tool → assistant)

  === 3) 다음 단계 (개념) ===
  ... (학습 실행 스케치 안내)

[흔한 에러]
  - PermissionError: 실행 디렉터리에 쓰기 권한 없음 → 쓰기 가능한 위치에서 실행
  - 한글 깨짐: 구형 Windows 터미널 → chcp 65001 후 재실행
  - 자기 데이터로 바꿨더니 필터 후 0건: status 라벨("success") 누락 —
    트레이스 수집 시 성공/실패 라벨부터 붙일 것 (13장 트레이싱)
"""

from __future__ import annotations

import hashlib
import json
import sys

from dotenv import load_dotenv

# Windows 한글 콘솔(cp949)에서도 출력이 깨지지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()  # 이 예제는 API 키가 필요 없지만, 예제 공통 관례로 유지

OUTPUT_PATH = "finetune_dataset.jsonl"

# 이 에이전트가 쓰는 도구 정의 — 학습 레코드마다 함께 기록해야
# 모델이 "이 스키마를 보고 이렇게 호출했다"를 배운다 (26장 3절).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "사내 규정 문서에서 관련 내용을 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "짧은 키워드 검색어"},
                },
                "required": ["query"],
            },
        },
    }
]

SYSTEM_PROMPT = "너는 사내 규정 안내 도우미다. 규정 근거가 필요하면 search_docs 로 검색하라."


# ---------------------------------------------------------------------------
# 샘플 트레이스 — 실전에서는 13장 트레이싱(LangSmith 등)에서 내보낸 JSON
# ---------------------------------------------------------------------------
# 트레이스 구조: {trace_id, status, steps[]}
#   step: {role, content} | {role, tool_call:{name, arguments}} | {role:"tool", ...}
SAMPLE_TRACES: list[dict] = [
    {   # ① 정상 성공 — 검색 1회 후 답변 (학습 데이터로 적합)
        "trace_id": "tr-001",
        "status": "success",
        "steps": [
            {"role": "user", "content": "재택근무는 주 며칠까지 가능해?"},
            {"role": "assistant", "tool_call": {"name": "search_docs",
                                                "arguments": {"query": "재택근무 주당 가능 일수"}}},
            {"role": "tool", "content": "[근무 규정] 재택근무는 주 3일까지 가능하다. 팀장 사전 승인 필요."},
            {"role": "assistant", "content": "재택근무는 주 3일까지 가능하며, 팀장의 사전 승인이 필요합니다."},
        ],
    },
    {   # ② 도구 실행 에러로 끝난 트레이스 — 필터 ①에서 제외
        "trace_id": "tr-002",
        "status": "error",
        "steps": [
            {"role": "user", "content": "노트북 반출 규정 알려줘"},
            {"role": "assistant", "tool_call": {"name": "search_docs",
                                                "arguments": {"query": "노트북 반출"}}},
            {"role": "tool", "content": "ERROR: search backend timeout"},
        ],
    },
    {   # ③ 정상 성공 — 검색 없이 인사에 바로 답변 ("도구를 안 쓰는 판단"도 귀중한 예제)
        "trace_id": "tr-003",
        "status": "success",
        "steps": [
            {"role": "user", "content": "고마워!"},
            {"role": "assistant", "content": "천만에요! 더 궁금한 규정이 있으면 언제든 물어보세요."},
        ],
    },
    {   # ④ tr-001 과 사실상 동일한 요청·도구 시퀀스 — 필터 ②에서 제외
        "trace_id": "tr-004",
        "status": "success",
        "steps": [
            {"role": "user", "content": "재택근무는 주 며칠까지 가능해?"},
            {"role": "assistant", "tool_call": {"name": "search_docs",
                                                "arguments": {"query": "재택근무 주당 가능 일수"}}},
            {"role": "tool", "content": "[근무 규정] 재택근무는 주 3일까지 가능하다. 팀장 사전 승인 필요."},
            {"role": "assistant", "content": "주 3일까지 가능합니다. 팀장 승인을 먼저 받으세요."},
        ],
    },
    {   # ⑤ 사용자가 이탈해 미완료 — 필터 ①에서 제외
        "trace_id": "tr-005",
        "status": "abandoned",
        "steps": [
            {"role": "user", "content": "연차"},
        ],
    },
    {   # ⑥ 성공이지만 사실상 no-op(어시스턴트 턴 없음) — 필터 ③에서 제외
        "trace_id": "tr-006",
        "status": "success",
        "steps": [
            {"role": "user", "content": "ㅎㅇ"},
        ],
    },
]


# ---------------------------------------------------------------------------
# 1) 품질 필터 3겹 — 쓰레기를 학습시키면 쓰레기 습관이 가중치에 굽힌다
# ---------------------------------------------------------------------------
def filter_success(traces: list[dict]) -> list[dict]:
    """필터 ①: 과제를 실제로 달성한(success) 트레이스만 남긴다.
    실패 트레이스는 버리지 말고 DPO 의 '나쁜 답' 후보로 따로 모아 두면 좋다."""
    return [t for t in traces if t["status"] == "success"]


def trace_fingerprint(trace: dict) -> str:
    """중복 판정용 지문: (사용자 요청, 도구 호출 시퀀스)를 정규화해 해시.
    같은 질문에 같은 도구를 같은 인자로 부른 트레이스는 하나만 남긴다."""
    user_texts = [s["content"].strip() for s in trace["steps"] if s["role"] == "user" and "content" in s]
    tool_seq = [
        (s["tool_call"]["name"], json.dumps(s["tool_call"]["arguments"], sort_keys=True, ensure_ascii=False))
        for s in trace["steps"] if s["role"] == "assistant" and "tool_call" in s
    ]
    payload = json.dumps({"users": user_texts, "tools": tool_seq}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def filter_dedup(traces: list[dict]) -> list[dict]:
    """필터 ②: 요청+도구 시퀀스가 같은 트레이스는 첫 건만 남긴다(분포 왜곡 방지)."""
    seen: set[str] = set()
    out = []
    for t in traces:
        fp = trace_fingerprint(t)
        if fp not in seen:
            seen.add(fp)
            out.append(t)
    return out


def filter_length(traces: list[dict], min_assistant_turns: int = 1, max_chars: int = 8000) -> list[dict]:
    """필터 ③: 어시스턴트 턴이 없는 no-op 과 비정상적으로 긴 트레이스 제외.
    (실전에서는 문자 수 대신 토크나이저 기준 토큰 수로 재는 것이 정확하다)"""
    out = []
    for t in traces:
        n_assistant = sum(1 for s in t["steps"] if s["role"] == "assistant")
        total_chars = sum(len(json.dumps(s, ensure_ascii=False)) for s in t["steps"])
        if n_assistant >= min_assistant_turns and total_chars <= max_chars:
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# 2) messages 포맷 변환 — 파인튜닝 API 가 요구하는 JSONL 레코드로
# ---------------------------------------------------------------------------
def trace_to_record(trace: dict) -> dict:
    """트레이스 1건 → 학습 레코드 1건.

    레코드 구조(도구 호출 SFT 의 사실상 표준인 messages 포맷):
      {"messages": [system, user, assistant(tool_calls), tool, assistant, ...],
       "tools": [...도구 정의...]}
    assistant 의 도구 호출은 tool_calls 배열로, 도구 결과는 role="tool" 로 기록한다.
    """
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    call_counter = 0

    for step in trace["steps"]:
        if step["role"] == "user":
            messages.append({"role": "user", "content": step["content"]})
        elif step["role"] == "assistant" and "tool_call" in step:
            call_counter += 1
            call_id = f"call_{trace['trace_id']}_{call_counter}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": step["tool_call"]["name"],
                        # arguments 는 JSON "문자열"이어야 한다 (흔한 포맷 실수)
                        "arguments": json.dumps(step["tool_call"]["arguments"], ensure_ascii=False),
                    },
                }],
            })
        elif step["role"] == "tool":
            call_id = f"call_{trace['trace_id']}_{call_counter}"
            messages.append({"role": "tool", "tool_call_id": call_id, "content": step["content"]})
        elif step["role"] == "assistant":
            messages.append({"role": "assistant", "content": step["content"]})

    return {"messages": messages, "tools": TOOLS}


# ---------------------------------------------------------------------------
# 데모
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== 1) 품질 필터 ===")
    traces = SAMPLE_TRACES
    print(f"입력 트레이스: {len(traces)}건")

    step1 = filter_success(traces)
    print(f"[필터 ①] 성공 트레이스만  : {len(traces)} → {len(step1)}건 "
          f"(에러/미완료 {len(traces) - len(step1)}건 제외)")

    step2 = filter_dedup(step1)
    print(f"[필터 ②] 중복 제거        : {len(step1)} → {len(step2)}건 "
          f"(동일 요청·도구 시퀀스 {len(step1) - len(step2)}건 제외)")

    step3 = filter_length(step2)
    print(f"[필터 ③] 길이 필터        : {len(step2)} → {len(step3)}건 "
          f"(no-op/초장문 {len(step2) - len(step3)}건 제외)")

    print("\n=== 2) JSONL 변환 ===")
    records = [trace_to_record(t) for t in step3]
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"{OUTPUT_PATH} 저장: {len(records)} 레코드")

    first = records[0]
    tool_names = [t["function"]["name"] for t in first["tools"]]
    print("[첫 레코드 구조]")
    print(f"- tools: {len(first['tools'])}개 ({', '.join(tool_names)})")
    print(f"- messages: {len(first['messages'])}턴 "
          f"({' → '.join(m['role'] + ('(tool_calls)' if m.get('tool_calls') else '') for m in first['messages'])})")

    print("\n=== 3) 다음 단계 (개념) ===")
    print("아래 주석의 학습 실행 스케치를 참고하세요. 핵심은 26장의 원칙:")
    print("- 학습 전후를 '같은 평가셋'(15장)으로 비교할 것")
    print("- 대상 작업 점수와 '일반 능력 퇴행' 점수를 둘 다 추적할 것")

    # ── 학습 실행 개념 스케치 (실행되지 않는 참고 주석) ──────────────────
    #
    # [경로 A] 관리형 (예: Azure AI Foundry 의 OpenAI 모델 SFT)
    #   1. finetune_dataset.jsonl 을 학습 파일로 업로드
    #   2. 파인튜닝 잡 생성: base model + training_file (+ validation_file)
    #   3. 잡 완료 후 발급된 모델 ID 로 기존 호출의 model 파라미터만 교체
    #
    # [경로 B] AWS Bedrock 에서 Claude 3 Haiku SFT (us-west-2)
    #   - Bedrock 이 요구하는 포맷으로 레코드를 변환해 S3 에 업로드하고
    #     커스터마이즈 잡을 생성. 사용 시 Provisioned Throughput 필요.
    #
    # [경로 C] 오픈 모델 + QLoRA (Unsloth)
    #   from unsloth import FastLanguageModel          # 개념 스케치
    #   model, tokenizer = FastLanguageModel.from_pretrained("...-Instruct", load_in_4bit=True)
    #   model = FastLanguageModel.get_peft_model(model, r=16)   # LoRA 어댑터 부착
    #   # messages 레코드를 채팅 템플릿으로 직렬화해 SFTTrainer 로 학습
    #   # → 어댑터만 저장/배포 (수십 MB), 베이스 모델 업데이트 시 재학습 필요
    #
    # 공통: 학습이 끝나면 반드시 15장의 오프라인 eval 로 전후를 비교하고,
    #       회귀가 보이면 데이터 필터(위 1단계)로 되돌아간다.


if __name__ == "__main__":
    main()
