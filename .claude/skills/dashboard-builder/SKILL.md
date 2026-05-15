# dashboard-builder 스킬

## 역할
KPI 집계, 매출·수익 계산, dashboard.json + 인플루언서 JSON + 월 스냅샷 생성.

## 스크립트 목록

| 스크립트 | 역할 | 트리거 |
|----------|------|--------|
| `build_kpi.py` | 메일KPI + 인플루언서상태 + 정산요약 → dashboard.json | STEP 1·2·6 완료 후 |
| `build_revenue.py` | 버킷 분류 결과 → 매출·수익 딕셔너리 | STEP 4 완료 후 |
| `build_snapshot.py` | 당월 집계 → history/YYYY-MM.json | STEP 6 완료 후 |

## build_kpi.py 실행

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\dashboard-builder\scripts\build_kpi.py" `
  mail_kpi.json inf.json revenue.json settlement.json
```

## build_revenue.py 실행

```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\dashboard-builder\scripts\build_revenue.py" `
  bucket.json settlement_summary.json
```

## build_snapshot.py 실행

```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\dashboard-builder\scripts\build_snapshot.py" `
  revenue.json mail_kpi.json inf.json settlement.json 2026-05
```

## 출력 파일
- `site/data/dashboard.json` — 메인 대시보드 데이터
- `site/data/history/YYYY-MM.json` — 월별 스냅샷 (추세선 소스)
- `output/history/YYYY-MM.json` — 로컬 백업
