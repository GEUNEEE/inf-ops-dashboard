# order-processor 서브에이전트

## 역할
스마트스토어 주문 파일 처리 전담 (STEP 3~9).
메인 오케스트레이터가 `run_pipeline.py`를 통해 일괄 실행한다.

## 실행 방법

```powershell
# 파일 직접 지정
$env:PYTHONUTF8 = "1"; $env:SMARTSTORE_XLSX_PASSWORD = "1234"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  "<xlsx_경로>" --month "YYYY-MM"

# 스케줄/input 폴더에서 최신 파일 자동 선택
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  --latest --month "YYYY-MM"
```

## 파이프라인 단계

### STEP 3-4 — 복호화 + 버킷 분류 + Raw_Data 반영
`parse_order.py` 실행. `.env`에서 `SMARTSTORE_XLSX_PASSWORD` 자동 로드.

**버킷 분류 기준:**
| 버킷 | 조건 | Raw_Data | 정산서 |
|------|------|----------|--------|
| settlement | managed_set 등재 | O | O |
| general | 유튜버명 패턴 없음 | O | 기타일반 시트 |
| excluded | 미등재 | O (로그) | X |
| skipped | 취소 or 완전제외 | X | X |

신규 0건이어도 파이프라인 계속 진행 (Raw_Data 기반 재빌드).

### STEP 5 — 정산서 생성 (settlement-generator 스킬)
- `generate_sheets.py` 실행
- **Raw_Data 해당 월 전체** 기준으로 시트 생성 (bucket 신규분만 아님)
- name_map 정규화 + history 파일로 누적 수량 보완

### STEP 6 — 매출·수익 집계
- `build_revenue.py` 실행
- 수량은 **settlement.json 누계 기준** (bucket 신규분 아님)

### STEP 7 — 월별 스냅샷
`build_snapshot.py` → `site/data/history/YYYY-MM.json`

### STEP 8 — dashboard.json 빌드
`build_kpi.py` → `site/data/dashboard.json`

### STEP 9 — git push
`publish.py` → GitHub Pages 배포

### STEP 10 — 데이터 검증
`verify_data.py` 6개 항목 자동 검증:
1. settlement 수량·금액 수기 검증
2. 미등재 인플루언서 확인
3. 인플루언서별 누적 수량 및 단가 구간
4. history 파일 gross_revenue 역산
5. dashboard trends vs history 정합성
6. dashboard.revenue vs 현재월 snapshot

## 에스컬레이션 조건
- 비밀번호 오류 (복호화 실패)
- 주문 시트 구조 미매칭 (`주문조회` 시트 없음)

## 이름 정규화 설정
`ytber_config.json`으로 관리:
- `name_map`: 유튜버명 정규화 매핑
- `additional_managed`: 인플루언서관리 탭 외 추가 정산 대상
- `exclude`: 완전 차단 (Raw_Data 기록 자체 제외)
