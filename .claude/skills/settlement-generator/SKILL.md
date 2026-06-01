# settlement-generator 스킬

## 역할
Raw_Data 해당 월 전체 주문을 기반으로 인플루언서별 정산 시트를 생성한다.
구간 단가(누적 수량 기반)와 VAT 10% 제외 금액 칼럼을 포함한다.

## 호출 조건
- 신규 주문이 있을 때 (run_pipeline.py STEP 5에서 자동 호출)
- 신규 0건이어도 Raw_Data 기반 재생성이 필요할 때 (파이프라인 재빌드 시)

## 실행 방법

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\settlement-generator\scripts\generate_sheets.py" `
  "C:\Users\user\비서\output\tmp\bucket.json" "2026-05"
```

## 입력
- 위치 인수 1: bucket_json 파일 경로 (또는 `-` → stdin)
- 위치 인수 2: 정산월 `YYYY-MM`

## 출력
- `C:\Users\user\비서\스케줄\유튜버별 월정산시트 작성 YYYY-MM_송부용.xlsx` — 정산 시트
- stdout JSON: 정산 요약 (인플루언서별 건수·수량·금액·누적수량·단가)

## 핵심 동작 원칙

### 정산 대상 결정
- bucket.json의 settlement 목록이 아닌 **Raw_Data 해당 월 전체** 기준으로 시트 생성
- name_map 정규화 적용 (예: "코 앞의 경제" → "코앞의경제")
- 기타/일반 제외한 모든 비취소 ytber에 시트 생성

### 누적 수량 계산
- Raw_Data에 있는 이전 월 분은 Raw_Data에서 집계
- Raw_Data에 없는 이전 월 분은 `site/data/history/*.json`에서 자동 보완
- 두 값을 합산하여 정확한 누적 수량 산출 → 구간 단가 결정

### 구간 단가 정책
| 누적 수량 | 단가 |
|-----------|------|
| 1~29개   | ₩20,000 |
| 30~99개  | ₩22,000 |
| 100개+   | ₩25,000 |

경계 도달 시점부터 새 단가 적용. `ytber_config.json`의 `tier_pricing`으로 관리.

## 버킷별 처리
| 버킷 | 시트 생성 | 금액 |
|------|-----------|------|
| settlement | `{유튜버명} {월}월` | 구간 단가 × 수량 |
| general    | `기타일반 {월}월`   | null (-) |
| excluded   | 없음 + 로그        | — |

## 이름 정규화 설정
`ytber_config.json`의 `name_map`과 `additional_managed`로 관리:
- `name_map`: 주문 파일 유튜버명 → 정규화된 이름 매핑
- `additional_managed`: 인플루언서관리 탭에 없지만 정산 대상인 유튜버 목록
