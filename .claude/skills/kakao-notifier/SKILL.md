# kakao-notifier 스킬

## 역할
카카오톡 메모챗 MCP(`KakaotalkChat-MemoChat`)를 호출하여 주문 처리 결과를 알린다.

## 트리거
- (A) 주문 파이프라인 완료 시
- (B) 관리탭 미등재 인플루언서 발견 즉시 (별도 선발송)

## 메시지 구성 (4 섹션)
1. 주문 처리 요약 (신규 N건, 정산 M명, 기타 K건)
2. 관리탭 미등재 목록 (있을 때만)
3. 이번달 매출·수익
4. 대시보드 URL

## 사용 방법

```powershell
# Step 1: 메시지 텍스트 생성
$env:PYTHONUTF8 = "1"
$msg = & "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\kakao-notifier\scripts\notify.py" `
  revenue.json bucket.json settlement.json

# Step 2: Claude Code 에이전트가 MCP 호출
# mcp__claude_ai_PlayMCP__KakaotalkChat-MemoChat 도구로 $msg 전송
```

## 실패 처리
1회 재시도 → 실패 시 로컬 `output/watcher.log`에 기록 후 계속 진행

## 주의사항
- `notify.py`의 `SITE_URL` 변수를 실제 GitHub Pages URL로 교체해야 한다.
- MCP 메시지 최대 길이 초과 시 요약 압축 필요 (설계서 미결항목 #11).
