# settlement-generator 스킬

## 역할
주문 버킷 분류 결과를 받아 인플루언서별 정산 시트를 생성한다.
구간 단가(누적 수량 기반)와 VAT 10% 제외 금액 칼럼을 포함한다.

## 호출 조건
STEP 4 완료 후, 신규 주문 1건 이상일 때

## 실행 방법

```powershell
$env:PYTHONUTF8 = "1"
# bucket_data = parse_order.py stdout JSON 을 파일로 저장 후
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\settlement-generator\scripts\generate_sheets.py" `
  "bucket_data.json" "2026-05"
```

## 입력
- 위치 인수 1: bucket_json 파일 경로 (또는 `-` → stdin)
- 위치 인수 2: 정산월 `YYYY-MM`

## 출력
- `C:\Users\user\비서\스케줄\정산DB_업데이트.xlsx` — 정산 시트 추가
- stdout JSON: 정산 요약 (인플루언서별 건수·수량·금액·누적수량·단가)

## 구간 단가 정책
| 누적 수량 | 단가 |
|-----------|------|
| 1~29개   | ₩20,000 |
| 30~99개  | ₩22,000 |
| 100개+   | ₩25,000 |

경계 주문부터 새 단가 적용 (부분 분할 없음). `ytber_config.json`의 `tier_pricing`으로 관리.

## 버킷별 처리
| 버킷 | 시트 생성 | 금액 |
|------|-----------|------|
| settlement | `{유튜버명} {월}월` | 구간 단가 × 수량 |
| general    | `기타일반 {월}월`   | null (-) |
| excluded   | 없음 + 로그        | — |
