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

## 월말 정산서 전체 실행 (`--rebuild --images`)

기본 실행은 신규 주문 파일이 하나도 없으면 에러로 중단된다. 사용자가 "정산서까지 돌려줘" 등으로
**신규 주문 파일 없이도 Raw_Data 기준으로 정산서(+이미지)까지 뽑아달라고** 명시적으로 요청한 경우에만
아래처럼 `--rebuild --images`를 추가한다 (평소 주문 처리에는 절대 기본으로 붙이지 않음 — 월말 전용):

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  --all --rebuild --images --month "2026-08"
```

- `--rebuild`: 스케줄/input/Downloads에 주문 파일이 0개여도 에러 없이 Raw_Data 기준으로 정산·대시보드 재빌드 진행
- `--images`: STEP 5(정산서 생성) 직후 `settlement-generator/scripts/export_images.py`를 자동 호출해
  `output/N월 정산/*.png`까지 생성 (기존엔 수동으로만 실행되던 단계)
- 신규 주문 파일이 있는 평소 실행(`--all --month ...`)에는 두 플래그를 붙이지 않는다 — 이미지 변환은 Excel COM을 띄우는 무거운 작업이라 매번 돌릴 필요 없음
