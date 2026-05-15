# order-watcher 스킬

## 역할
`/input` 폴더를 watchdog으로 감시하여 스마트스토어 주문 xlsx 파일 드롭 시 전체 파이프라인을 자동 트리거한다.

## 파일 구성

| 파일 | 역할 |
|------|------|
| `watcher.py` | watchdog 데몬 — `/input` 폴더 상시 감시 |
| `run_pipeline.py` | STEP 1~9 전체 파이프라인 실행 (수동·watchdog 공용) |

## watchdog 시작 방법

```powershell
$env:PYTHONUTF8 = "1"
Start-Process -NoNewWindow `
  "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\watcher.py"
```

## 수동 파이프라인 실행

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  "C:\Users\user\비서\input\스마트스토어_주문조회_20260430.xlsx" `
  --month 2026-04
```

## 과거 임포트 (STEP 0)

여러 파일을 날짜순 일괄 처리:

```powershell
$env:PYTHONUTF8 = "1"
$files = Get-ChildItem "C:\Users\user\비서\input" -Filter "스마트스토어_주문조회_*.xlsx" | Sort-Object Name
foreach ($f in $files) {
    $month = $f.Name -replace "스마트스토어_주문조회_(\d{4})(\d{2})\d+.*", '$1-$2'
    & "C:\Users\user\비서\.venv\Scripts\python.exe" `
      "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
      $f.FullName --month $month
}
```

## 감지 기준
파일명이 `스마트스토어_주문조회_*.xlsx` 패턴인 파일이 `/input`에 생성되거나 이동될 때 트리거.
