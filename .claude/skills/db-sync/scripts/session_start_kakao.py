# -*- coding: utf-8 -*-
"""
미발송 DB동기화 카톡 자동배달 훅. 두 이벤트에서 호출:
  - SessionStart    : Claude 켤 때 그동안 쌓인 알림 배달
  - UserPromptSubmit : 세션이 이미 열린 상태에서 동기화가 돌아도, 다음 메시지에서 즉시 배달
미발송 파일이 있으면 내용을 additionalContext로 주입 → Claude가 KakaotalkChat-MemoChat MCP로 전송.
(카톡 MCP는 세션 안에서만 동작 → 세션 활동을 배달 트리거로 사용)
파일 I/O만 하므로 즉시 종료 — 입력 지연 없음. 인자: argv[1]=이벤트명(기본 SessionStart).
"""
import os, sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PEND = r"C:\Users\user\비서\output\tmp\sync_kakao_pending.txt"

def main():
    event = sys.argv[1] if len(sys.argv) > 1 else "SessionStart"
    if not os.path.exists(PEND):
        return
    with open(PEND, encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return
    msg = (
        "[자동 알림 — DB동기화 미발송 카톡 배달]\n"
        "아래 내용을 KakaotalkChat-MemoChat MCP의 message 파라미터로 전송한 뒤 "
        "'%s' 파일을 삭제하세요. 여러 건이 '— — —' 구분선으로 나뉘어 있으면 건별로 나눠 보내세요.\n\n%s"
        % (PEND, content)
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": msg,
        }
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
