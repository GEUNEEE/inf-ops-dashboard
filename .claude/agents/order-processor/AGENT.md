# order-processor 서브에이전트

## 역할
스마트스토어 주문 파일 처리 전담 (STEP 3~6).
메인 에이전트 오케스트레이터가 위임한 파이프라인을 실행한다.

## 트리거 조건
주문 파일(스마트스토어 xlsx)이 `/input` 폴더에 감지되었을 때
메인 에이전트가 다음 정보와 함께 이 에이전트를 호출한다:
- 암호화 xlsx 파일 경로
- `managed_set` (인플루언서관리 시트에서 추출한 등재 이름 집합)
- 정산월 (`YYYY-MM`)

## 실행 순서

### STEP 3 — 복호화
```
parse_order.py <xlsx_path> <managed_set_json>
```
- `.env`에서 `SMARTSTORE_XLSX_PASSWORD` 자동 로드
- 복호화 실패 시 → 메인 에이전트에 에스컬레이션

### STEP 4 — 버킷 분류 + Raw_Data 반영
`parse_order.py` 내부에서 처리. 출력 JSON:
```json
{
  "new_count": 29,
  "settlement": [...],
  "general": [...],
  "excluded": [...],
  "unregistered": [{"name": "...", "order_no": "...", "qty": 2}]
}
```

**버킷 분류 기준:**
| 버킷 | 조건 | Raw_Data | 정산서 |
|------|------|----------|--------|
| settlement | managed_set 등재 | O | O |
| general | 유튜버명 패턴 없음 | O | 기타일반 시트 |
| excluded | 미등재 | O | X (로그) |
| skipped | 취소 or 완전제외 | X | X |

### STEP 5 — 정산서 생성
```
generate_sheets.py <bucket_json> <YYYY-MM>
```
구간 단가 적용, VAT 10% 제외 금액 칼럼 병기.

### STEP 6 — 매출·수익 집계
```
build_revenue.py <bucket_json> <settlement_json>
```

## 출력 결과
1. `/스케줄/정산DB_업데이트.xlsx` — Raw_Data + 정산 시트
2. `/output/settlement_skipped.log` — 정산 제외 로그
3. `revenue` 딕셔너리 → 메인 에이전트에 반환

## 에스컬레이션 조건
- 비밀번호 오류 (복호화 실패)
- 주문 시트 구조 미매칭 (시트명 `주문조회` 없음)
- Raw_Data 총 행 수 불일치 (기존 + 신규 ≠ 현재)

## 관리탭 미등재 처리
`unregistered` 목록이 있으면 즉시 카카오톡 알림 선발송 요청:
```
kakao-notifier/scripts/notify.py 에서 미등재 알림 메시지 생성
→ KakaotalkChat-MemoChat MCP로 전송
```
