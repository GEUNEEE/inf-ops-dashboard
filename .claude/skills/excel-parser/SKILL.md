# excel-parser 스킬

## 역할
인플루언서 관리 엑셀 파일을 파싱하여 브리핑용 JSON을 생성한다.

## 호출 조건
브리핑 워크플로우 STEP 1에서 항상 호출

## 실행 방법

다음 PowerShell 명령을 실행한다:

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" "C:\Users\user\비서\.claude\skills\excel-parser\scripts\extract.py"
```

## 성공 기준

- 종료 코드 0
- `C:\Users\user\비서\output\YYYY-MM-DD_parsed.json` 파일이 생성됨
- JSON에 `influencers` 배열과 `date_range` 필드가 포함됨
- `influencers` 배열에 1명 이상 포함됨

## 실패 처리

| 상황 | 처리 |
|------|------|
| 엑셀 파일 없음 | 에러 메시지 출력 후 중단, 사용자에게 알림 |
| 시트명 불일치 | 에러 메시지 출력 후 중단 |
| 특정 인플루언서 파싱 오류 | 해당 인플루언서 스킵 후 계속 진행 |

## 출력 JSON 스키마

```json
{
  "generated_at": "YYYY-MM-DD HH:MM",
  "date_range": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
  "influencers": [
    {
      "name": "유튜버명",
      "status": "진행상태 원문",
      "status_emoji": "🔵",
      "note": "비고 원문 (빈 문자열 가능)",
      "upcoming": [
        { "item": "항목명", "date": "YYYY-MM-DD", "days_until": 2 }
      ],
      "overdue": [
        { "item": "항목명", "date": "YYYY-MM-DD", "days_overdue": 3 }
      ]
    }
  ]
}
```
