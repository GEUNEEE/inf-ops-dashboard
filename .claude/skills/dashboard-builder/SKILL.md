# dashboard-builder 스킬

## 역할
KPI 집계, 매출·수익 계산, dashboard.json + 인플루언서 JSON + 월 스냅샷 생성.

## 스크립트 목록

| 스크립트 | 역할 | 트리거 |
|----------|------|--------|
| `build_kpi.py` | 메일KPI + 인플루언서상태 + 정산요약 → dashboard.json | STEP 1·2·6 완료 후 |
| `build_revenue.py` | 버킷 분류 결과 → 매출·수익 딕셔너리 | STEP 4 완료 후 |
| `build_snapshot.py` | 당월 집계 → history/YYYY-MM.json | STEP 6 완료 후 |
| `build_ads.py` | Meta 광고 원본(MCP) → ads/YYYY-MM.json + index.json | `퍼포먼스 갱신` |
| `build_yk.py` | 영끌러님(ㅇ) 필터 → site/yk/data/{dashboard.json, history/, influencer/} | STEP 8 완료 후 (run_pipeline STEP 8.5, 실패해도 종합은 계속) |

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
  bucket.json settlement_summary.json inf.json 2026-09
```

- 수익 = 매출 − 정산비 − 협찬원가 − 원가(전체 수량 × 40,000) − 수기판매 수수료
- **눈길 인건비(개당 10,000)는 초방리농장(A) 흑염소 판매수량에만 적용** (2026-10-07 사용자 지시). 수기 판매(지인판매)는 기본 제외, 항목에 `"labor": true`를 넣은 건만 포함.
  슬립케어랩(B) 판매분은 눈길 인건비 별도 책정 없음. 기준 수량은 `labor_base_qty()`가 Raw_Data 스토어별 집계(`build_snapshot.aggregate_by_product_store`)에서 가져오며,
  스토어 분리 이전 월(2026-06 이하)은 전체 수량 기준 그대로. 출력에 `labor_qty`·`labor_basis`(`store_A`/`all`)가 함께 실리고 snapshot → history → dashboard.json(`profit_analysis.monthly`)까지 전달된다.
  app.js 기여수익 표 하단 인건비 줄도 이 값을 쓴다. 설정: `ytber_config.json` `labor_cost_store`.
- **2026-10부터 눈길 인건비 안 받음**: `ytber_config.json` `labor_cost_until: "2026-09"` 이후 월은 인건비 0, `labor_basis: "none"`, 영업이익 = 수익.
- 2026-07~09 history는 2026-10-07에 이 기준으로 소급 재계산함 (영업이익 07: 2,014,000 / 08: 2,320,000 / 09: 1,300,000).

## build_snapshot.py 실행

```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\dashboard-builder\scripts\build_snapshot.py" `
  revenue.json mail_kpi.json inf.json settlement.json 2026-05
```

## build_ads.py 실행 (퍼포먼스 대시보드)

입력: `output/tmp/meta_YYYY-MM.json` — Meta Ads MCP 응답을 그대로 담은 파일
(`campaigns[]` 캠페인 레벨 월 합계 + `daily[]` `time_increment:"1"` 일별). 값은 `"538112"`,
`"₩575,607 KRW"`, `{"value":"538112","unit":"KRW"}`, `"2.20%"`, `null` 모두 허용.

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\dashboard-builder\scripts\build_ads.py" 2026-09
# 인자 없으면 output/tmp/meta_*.json 전부 재생성
```

자사몰 주문/매출은 `site/data/history/YYYY-MM.json`의 `cosmetics_breakdown.by_channel.자사몰`에서 자동 병합.

## build_yk.py 실행 (영끌러님 대시보드)

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\dashboard-builder\scripts\build_yk.py"
# 정합 검증용: ㅇ 무시 + 시작월 해제 → 종합 history 2026-08·09 와 by_product/매출 일치, 유튜브 발송 4013
& "...\build_yk.py" --no-filter --start none --out "C:\Users\user\AppData\Local\Temp\yk_all"
```

- 입력: 종합 관리시트 `영끌러님 관리` 행 ㅇ(= ㅇ/o/O/○) 명단 + `제품` 행, 공유 메일 파일 3종(유튜브=흑염소·뷰티=화장품·슬립이지=수면영양제)의 `구분`=ㅇ 행, Raw_Data(ㅇ 명단 필터), 종합 `output/tmp/settlement.json`(정산금·누적수량·단가는 재계산 없이 필터)
- 종합 `site/data`·`output/tmp`는 읽기만 한다 (종합 숫자 불변). 인건비 0·지인판매 제외.
- **시작월 2026-10** (`YK_START_MONTH`, `--start YYYY-MM`): 영끌러님 대시보드는 2026-10부터 운영. 그 이전 월은 메일 퍼널·체험·광고·매출·history 모두 제외하고, 정산월이 시작월보다 빠르면 정산 데이터도 비우고 기준월을 시작월로 둔다. `--start none` 이면 제한 없음(정합 검증용).
- 출력 키 = 종합 dashboard.json 키 + `mail_funnel_by_product{제품:{…,by_month,source_file}}` + `ops_summary{managed_count,total_sent,…,by_product,influencer_products,unassigned}`
- 제품 미지정(`제품` 행 비어 있고 Raw_Data 주문도 없음)은 `alerts.product_unassigned`에 나열 → 사장님이 `제품` 행 입력
- 단위 테스트: `PYTHONUTF8=1 .venv\Scripts\python.exe -m unittest tests.test_build_yk` (24개)

## 출력 파일
- `site/yk/data/dashboard.json`, `site/yk/data/history/YYYY-MM.json`, `site/yk/data/influencer/<이름>.json` — 영끌러님 대시보드(`site/yk/`) 데이터
- `site/data/ads/YYYY-MM.json` + `site/data/ads/index.json` — 퍼포먼스 대시보드(`site/performance.html`) 데이터
- `site/data/dashboard.json` — 메인 대시보드 데이터
- `site/data/history/YYYY-MM.json` — 월별 스냅샷 (추세선 소스)
- `output/history/YYYY-MM.json` — 로컬 백업
