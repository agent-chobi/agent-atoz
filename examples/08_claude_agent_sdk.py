"""
08_claude_agent_sdk.py — Claude Agent SDK 최소 에이전트 (docs/05-claude-agent-sdk.md)

claude-agent-sdk 의 query() 로, 내장 도구(Read/Glob/Grep)를 사용해 이 저장소의
examples/ 폴더를 조사하는 최소 에이전트를 만든다. 도구를 직접 정의하지 않아도
Claude Code 런타임의 내장 도구를 그대로 상속받는 점이 이 SDK의 핵심이다.

전제 조건 (중요):
    - Python 3.10+
    - Node.js 18+ (내장 도구는 번들된 Claude Code CLI 위에서 동작)
    - 환경변수 ANTHROPIC_API_KEY
    - pip install claude-agent-sdk  (requirements.txt 에 포함)

주의:
    아래 API 이름(ClaudeAgentOptions, query, AssistantMessage, TextBlock, ResultMessage)은
    2026년 7월 기준 공식 문서로 확인한 것이다. SDK 마이너 버전에 따라 필드/동작이
    달라질 수 있으니 설치 버전과 대조가 필요하다.
      docs: https://docs.claude.com/en/api/agent-sdk/python
      repo: https://github.com/anthropics/claude-agent-sdk-python

실행:
    python examples/08_claude_agent_sdk.py
"""

import asyncio

from dotenv import load_dotenv

# claude-agent-sdk 미설치 환경에서도 파일을 열어볼 수 있도록 임포트를 보호한다.
try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "claude-agent-sdk 가 설치되지 않았습니다. 'pip install -r requirements.txt' 후 "
        "Node.js 18+ 가 설치돼 있는지 확인하세요.\n원본 오류: " + str(e)
    )

load_dotenv()  # ANTHROPIC_API_KEY 로드

# SDK 는 축약 모델 별칭을 받는다: "opus" / "sonnet" / "haiku".
# 비용을 아끼려면 "haiku" 로 바꾸세요.
MODEL = "opus"


async def main():
    # 옵션: 어떤 내장 도구를 허용할지 + 권한 모드를 정한다.
    options = ClaudeAgentOptions(
        model=MODEL,
        system_prompt="너는 코드베이스 조사 도우미다. 한국어로 간결하게 답한다.",
        allowed_tools=["Read", "Glob", "Grep"],  # 읽기 계열만 허용 (쓰기/실행 없음)
        permission_mode="acceptEdits",           # 읽기 작업 자동 승인
        # cwd=".",  # 필요하면 작업 디렉터리 지정 가능
    )

    prompt = "examples/ 폴더에 어떤 파이썬 파일들이 있는지 나열하고, 각 파일이 무슨 주제인지 한 줄로 요약해줘."

    print("=== Claude Agent SDK: 내장 도구로 코드베이스 조사 ===\n")

    # query() 는 비동기 제너레이터: 메시지 스트림을 순회한다.
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            # 어시스턴트 메시지는 여러 콘텐츠 블록으로 구성된다 (텍스트/도구 호출 등)
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text, end="", flush=True)
        elif isinstance(message, ResultMessage):
            # 실행 종료 요약 (subtype: "success" / "error")
            print(f"\n\n[완료] status={message.subtype}")


if __name__ == "__main__":
    asyncio.run(main())
