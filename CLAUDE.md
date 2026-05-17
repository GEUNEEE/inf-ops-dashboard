# 인플루언서 대시보드 오케스트레이터

## 역할 및 목적
1. **브리핑 자동화** — 인플루언서 관리 엑셀과 구글 캘린더를 읽어 일일 브리핑 문서 생성
2. **주문 파이프라인** — 스마트스토어 주문 파일을 받아 정산서 생성 + 대시보드 JSON 갱신 + 카카오톡 알림

---

# ① 브리핑 시스템

## 실행 트리거
사용자가 다음 중 하나를 입력하면 즉시 아래 워크플로우를 시작한다:
- `브리핑`
- `브리핑 실행해줘`
- `브리핑 생성`

## 워크플로우 (STEP 순서 반드시 준수)

### STEP 1. 엑셀 파싱 — PowerShell 직접 실행

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" "C:\Users\user\비서\.claude\skills\excel-parser\scripts\extract.py"
```

- 성공 기준: `C:\Users\user\비서\output\YYYY-MM-DD_parsed.json` 파일 생성 및 `influencers` 배열 포함
- 실패 시: 에러 메시지를 사용자에게 알리고 중단
- 성공 후: JSON 파일을 읽어 STEP 2로 진행

### STEP 2. 구글 캘린더 조회 — Google Calendar MCP

모든 캘린더(개인·업무 구분 없음)에서 다음 두 범위를 조회한다:

| 구분 | 범위 | 용도 |
|------|------|------|
| 오늘 일정 | 오늘 00:00 ~ 23:59 (전체) | 브리핑 섹션 4 |
| 주간 일정 | 내일 00:00 ~ 오늘+7일 23:59 | 브리핑 섹션 3 |

> 오늘 일정은 주간 범위에서 제외 (중복 방지)

MCP 실패 시: 1회 재시도 → 실패 시 해당 섹션에 `(캘린더 조회 실패)` 표기 후 계속 진행

### STEP 3. 브리핑 MD 생성 및 저장

STEP 1 JSON + STEP 2 캘린더 데이터를 통합하여 아래 규칙대로 브리핑 문서를 생성한다.

저장 경로: `C:\Users\user\비서\브리핑결과\YYYY-MM-DD_브리핑.md`

## 브리핑 생성 규칙

### 섹션 순서 (고정)

```
1. 👥 인플루언서 일정    (전체, 엑셀 기반 — 기타 상태 제외)
2. ⚠️ 조치 필요 항목    (overdue 항목, 없으면 섹션 전체 생략)
3. 🗓️ 주간 캘린더       (내일~오늘+7일, 구글 캘린더)
4. 📅 오늘 일정          (당일 전체, 구글 캘린더)
```

### 섹션 1 — 인플루언서 일정
- `upcoming`이 비어있는 인플루언서는 표시하지 않음
- 각 인플루언서는 가장 먼 미래 일정 하나만 표시 (`upcoming[0]`)
- 정렬: `upcoming[0].date` 기준 오름차순
- D-day: `days_until` 값 사용 → `D-2` 형태
- `note` 있으면 LLM이 1-2줄 요약하여 `📝 비고:` 줄에 삽입
- 섹션 말미에 `✅ 일정 있는 인플루언서: N명` 표시

### 섹션 2 — 조치 필요 항목
- `missing_ad` 배열 항목 있는 인플루언서만 표시
- 표: `| 인플루언서 | 상태 | 조치 항목 |`
- 모두 비어있으면 섹션 생략

### 섹션 3 — 주간 캘린더
- 내일~오늘+7일, 날짜·요일·시각·이벤트명 순
- 없으면 `(이번 주 예정 일정 없음)`

### 섹션 4 — 오늘 일정
- 오늘 전체, 시각·이벤트명 순
- 없으면 `(오늘 예정 일정 없음)`

---

# ② 주문 파이프라인 시스템

## 실행 트리거

| 트리거 | 설명 |
|--------|------|
| 주문 파일 처리 요청 | 사용자가 스마트스토어 xlsx 파일 경로를 제시 |
| `과거 임포트 실행` | STEP 0 — 보유 주문 파일 일괄 처리 |
| `대시보드 갱신` | STEP 1~2만 실행 (주문 없이 KPI만 갱신) |

## 워크플로우 진입점

```
주문 파일 존재?
  YES → STEP 1~2 (마스터DB 파싱) → order-processor 서브에이전트 위임 (STEP 3~6) → STEP 7~9
  NO  → STEP 1~2만 실행 + STEP 9 (대시보드 JSON + git push)
```

## STEP 1 — 메일발송현황 파싱

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" "C:\Users\user\비서\.claude\skills\excel-parser\scripts\parse_mail.py"
```

출력: 퍼널 KPI JSON (총발송·응답률·미팅전환율·광고수락률)

## STEP 2 — 인플루언서관리 파싱 → managed_set 추출

```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" "C:\Users\user\비서\.claude\skills\excel-parser\scripts\parse_inf.py"
```

출력: `managed_set` (등재 인플루언서 이름 배열), 상태 집계

## STEP 3~6 — order-processor 서브에이전트 위임

`.claude/agents/order-processor/AGENT.md` 참조.
managed_set을 JSON 문자열로 인라인 전달.
전체 파이프라인 일괄 실행:

```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  "<xlsx_경로>" --month "YYYY-MM"
```

## STEP 7 — 월별 스냅샷 (run_pipeline.py 내부 자동 실행)

`site/data/history/YYYY-MM.json` + `output/history/YYYY-MM.json` 저장

## STEP 8 — 카카오톡 알림

notify.py로 메시지 생성 → `KakaotalkChat-MemoChat` MCP로 전송

**트리거:**
- 주문 처리 완료 후 (4섹션 메시지)
- 관리탭 미등재 인플루언서 발견 즉시 (별도 선발송)

## STEP 9 — git push

```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\site-publisher\scripts\publish.py" "YYYY-MM"
```

1회 재시도 → 실패 시 로컬만 저장, 다음 처리 시 재시도.

---

## 정산 대상 판별 원칙

| 버킷 | 조건 | Raw_Data | 정산서 | 카카오 알림 |
|------|------|----------|--------|------------|
| settlement | managed_set 등재 | O | O | — |
| general | 유튜버명 패턴 없음 | O | 기타일반 시트 | — |
| excluded | 미등재 | O | X (로그) | 즉시 발송 |
| skipped | 취소 or 완전제외 | X | X | — |

- `우리의 서술집` → exclude 목록, Raw_Data 반영 자체 차단
- 유튜버명 추출 정규식: `\[([^\]]+?)\s*구독자`
- name_map 정규화: `ytber_config.json` 참조

## 구간 단가 적용 원칙
- 누적 수량 기준: Raw_Data 전체 (월 리셋 없음)
- 경계 도달 시점부터 새 단가 적용 (단위 수량별 분할 — 경계 전 수량은 이전 단가, 경계 이후 수량은 새 단가)
- 기준: 1~29개 ₩20,000 / 30~99개 ₩22,000 / 100개+ ₩25,000

## 에러 처리 원칙
| 오류 | 처리 |
|------|------|
| 비밀번호 오류 (복호화 실패) | 에스컬레이션 — 파이프라인 중단 |
| 시트 구조 미매칭 | 에스컬레이션 |
| 개별 인플루언서 정산 오류 | 해당 시트 스킵 + 로그 + 계속 |
| git push 실패 | 1회 재시도 → 로컬 저장 후 계속 |
| 카카오톡 MCP 실패 | 1회 재시도 → 로그 후 계속 |

---

## 파일 경로 규칙

| 항목 | 경로 |
|------|------|
| 마스터 DB | `C:\Users\user\비서\스케줄\0. 유튜브 인플루언서 관리_*.xlsx` |
| 주문 드롭 폴더 | `C:\Users\user\비서\input\` |
| 정산DB | `C:\Users\user\비서\스케줄\정산DB_업데이트.xlsx` |
| 정산 제외 로그 | `C:\Users\user\비서\output\settlement_skipped.log` |
| 사이트 데이터 | `C:\Users\user\비서\site\data\` |
| 월별 스냅샷 | `C:\Users\user\비서\site\data\history\YYYY-MM.json` |
| 환경변수 | `C:\Users\user\비서\.env` (SMARTSTORE_XLSX_PASSWORD) |
| 유튜버 설정 | `C:\Users\user\비서\.claude\skills\settlement-generator\scripts\ytber_config.json` |
| 임시 JSON | `C:\Users\user\비서\output\tmp\` |

## 스킬 목록

| 스킬 | 역할 |
|------|------|
| `excel-parser` | 마스터 DB 파싱 (parse_mail, parse_inf, parse_order, extract) |
| `settlement-generator` | 정산 시트 생성 (구간 단가·VAT) |
| `dashboard-builder` | KPI 집계·매출수익·스냅샷 → JSON |
| `order-watcher` | /input 감시 + 파이프라인 실행 |
| `kakao-notifier` | 카카오톡 메시지 생성 + MCP 호출 |
| `site-publisher` | git add/commit/push |
