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

모든 캘린더(개인·업무 구분 없음)에서 다음 두 범위를 조회한다.
**반드시 아래 캘린더 ID를 전부 개별 조회한다 (기본 캘린더만 조회하면 일정 누락됨):**
- `calix9k@gmail.com` (내일정)
- `fd02c7454fbae4abc03c49b20874211cc64bc96533bf7f007a476643546f6cbc@group.calendar.google.com` (1. 인플루언서 관리)
- `1788d98de90c51523d4b25aa64d8dcaaa6bf723631bc3bd5726a298156eba2f5@group.calendar.google.com` (2. 업무)
- `022bb8b8fc2192bb4cb0a607bd855140a311935967b65b344248a43bc1d43ee5@group.calendar.google.com` (공유캘린더)

| 구분 | 범위 | 용도 |
|------|------|------|
| 오늘 일정 | 오늘 00:00 ~ 23:59 (전체) | 브리핑 섹션 2 |
| 주간 일정 | 내일 00:00 ~ 오늘+7일 23:59 | 브리핑 섹션 3 |

> 오늘 일정은 주간 범위에서 제외 (중복 방지)

MCP 실패 시: 1회 재시도 → 실패 시 해당 섹션에 `(캘린더 조회 실패)` 표기 후 계속 진행

### STEP 3. 브리핑 MD 생성 및 저장

STEP 1 JSON + STEP 2 캘린더 데이터를 통합하여 아래 규칙대로 브리핑 문서를 생성한다.

저장 경로: `C:\Users\user\비서\브리핑결과\YYYY-MM-DD_브리핑.md`

## 브리핑 생성 규칙

### 섹션 순서 (고정)

```
1. ⚡️ 오늘 마감 / D-7 이내 예정  (D-DAY + D-7 이내 통합, 날짜 오름차순)
2. 📅 오늘 일정                   (당일 전체, 구글 캘린더)
3. 🗓️ 주간 캘린더                 (내일~오늘+7일, 구글 캘린더)
4. 👥 인플루언서 일정              (전체, 엑셀 기반 — 기타 상태 제외)
5. ⚠️ 조치 필요 항목              (overdue 항목, 없으면 섹션 전체 생략)
```

### 섹션 1 — 오늘 마감 / D-7 이내 예정
- JSON의 `upcoming` 일정 중 `days_until`이 **0 이하(D-DAY 포함 지남)** 또는 **1~7** 인 항목을 **모두 하나의 섹션**에 합쳐서 표시
- 정렬: 날짜 오름차순 (가장 급한 것부터)
- 형식: `• D-N 인플루언서명 — 일정내용 (MM/DD)`
  - D-DAY: `• D-DAY 인플루언서명 — 일정내용 (MM/DD)`
  - 지난 경우: `• D+N 인플루언서명 — 일정내용 (MM/DD)` (연체 느낌)
- 해당 항목 없으면 섹션 전체 생략

### 섹션 2 — 오늘 일정
- 오늘 전체, 캘린더별 그룹(1. 인플루언서 관리 / 2. 업무)으로 나눠 표시
- 형식: 캘린더명을 **굵게** 소제목으로, 각 일정은 `• 시각 — 이벤트명`
- 없으면 `(오늘 예정 일정 없음)`

### 섹션 3 — 주간 캘린더
- 내일~오늘+7일, 날짜·요일별로 묶어 표시
- 형식: `날짜 (요일)` 헤더 아래 `• 시각 — 이벤트명` 나열
- 없으면 `(이번 주 예정 일정 없음)`

### 섹션 4 — 인플루언서 일정
- `upcoming`이 비어있는 인플루언서는 표시하지 않음
- 표: `| 인플루언서 | 상태 | 다음 일정 | D-day |`
- 상태 이모지: 🟡 광고예정, 🟠 2차 광고예정, 🔵 체험진행, ✅ 광고완료 등
- 정렬: `upcoming[0].date` 기준 오름차순
- D-day: `days_until` 값 사용 → `D-4` 형태
- `note` 있으면 조치 항목 셀에 `📝 비고:` 형태로 삽입
- 섹션 말미에 `✅ 일정 있는 인플루언서: N명` 표시

### 섹션 5 — 조치 필요 항목
- `missing_ad` 배열 항목 있는 인플루언서만 표시
- 표: `| 인플루언서 | 상태 | 조치 항목 |`
- 상태 이모지 동일 적용
- `note` 있으면 조치 항목 셀 끝에 `📝 비고:` 추가
- 모두 비어있으면 섹션 생략

---

# ② 주문 파이프라인 시스템

## 실행 트리거

| 트리거 | 설명 |
|--------|------|
| 주문 파일 처리 요청 | 사용자가 파일 경로를 제시하거나 "최신 파일 반영" 등 언급 |
| `과거 임포트 실행` | STEP 0 — 보유 주문 파일 일괄 처리 |
| `대시보드 갱신` | STEP 1~2만 실행 (주문 없이 KPI만 갱신). 종합(`site/data`) 갱신 후 `build_yk.py`로 영끌러님 대시보드(`site/yk/data`)도 같이 갱신 (run_pipeline STEP 8.5 자동) |
| `정산서까지 돌려줘` / `정산서 뽑아줘` | 신규 주문 파일 유무와 무관하게 Raw_Data 기준으로 정산서 재생성 + PNG 이미지까지 생성. `run_pipeline.py --all --rebuild --images --month YYYY-MM` (월말 전용 — 평소 주문 처리 때는 `--rebuild --images` 붙이지 않음). `--images` 시 STEP 5.7에서 `output/N월 정산/` 에 정산비용(계좌 열 포함)·원천세 엑셀도 자동 생성 |
| `퍼포먼스 갱신` | Meta 광고 → `site/performance.html` 데이터 갱신. ① Meta Ads MCP `ads_get_ad_entities`(계정 `706112365442772`, 캠페인 레벨 + `time_increment:"1"` 일별)로 당월 수집 → `output/tmp/meta_YYYY-MM.json` 저장 (원본 값 형식 그대로) ② `build_ads.py YYYY-MM` → `site/data/ads/YYYY-MM.json` + `index.json` ③ `publish.py`. 자사몰 주문은 `history/YYYY-MM.json`에서 자동 병합되므로 주문 파이프라인 먼저 돌린 뒤 실행 |

## 주문 파일 탐색 순서

1. 사용자가 경로를 직접 제시한 경우 → 해당 파일 사용
2. 그 외(기본값 `--all`) → **스케줄 → input → Downloads** 3개 폴더에서 `스마트스토어_주문조회_*.xlsx` · `스마트스토어_*발주발송관리_*.xlsx` · `스마트스토어_*주문배송현황_*.xlsx` · `스마트스토어_*취소관리_*.xlsx`(취소 건) · `calix9k_*.zip`(자사몰) 패턴 파일을 **모두 수집**해 일괄 처리 (내용이 동일한 중복 사본은 우선순위 높은 폴더 것 1개만 남기고 제외)
3. `--latest` 지정 시 → 위 3개 폴더 중 mtime이 가장 최신인 파일 **1개**만 처리

### 자사몰(spoteasy) 주문 zip
- `calix9k_YYYYMMDD_*.zip` — 비밀번호 걸린 CSV 1개 포함 (비밀번호: `.env`의 `JASAMALL_ZIP_PASSWORD`)
- `parse_mall_order.py`가 처리: 제품=`화장품`·채널=`자사몰` 고정, 품목별 주문번호 기준 중복 스킵
- 정산예정금액 컬럼 없음 → 빈값 기록, 수익은 **총 주문금액 기준 네이버와 동일 공식** (주문금액×0.9 − 원가5,000 − 배송2,800)

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
# 파일 경로를 직접 지정하는 경우
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  "<xlsx_경로>" --month "YYYY-MM"

# 스케줄/input/Downloads 폴더의 주문 파일을 전부 자동 수집하는 경우 (기본값, 내용 중복 자동 제외)
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\order-watcher\scripts\run_pipeline.py" `
  --all --month "YYYY-MM"
```

> 파일 인자 없이 실행하면 스케줄→input→Downloads 3개 폴더의 주문 파일을 **모두** 수집한다.
> 내용이 동일한 중복 사본은 우선순위 높은 폴더 것 1개만 처리하고 나머지는 제외한다.
> 주문번호(상품주문번호) 단위 중복은 Raw_Data 대조로 자동 스킵되어 이중 집계되지 않는다.
> 최신 1개만 처리하려면 `--all` 대신 `--latest`를 쓴다.

`run_pipeline.py` 내부에서 STEP 3~4 직후 **STEP 4.5 — 고객DB 누적**이 자동 실행된다.
이번 배치 파일 중 연락처 보유 형식(발주발송관리·주문배송현황·자사몰 zip)만 골라
`스케줄\build_customer_db.py`로 넘겨 `스케줄\고객DB.xlsx`(연락처·주소·구매이력 누적, Git 미포함)를 갱신한다.
별도 호출 불필요 — 매번 파이프라인 실행 시 자동으로 같이 쌓인다.

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
| cancelled | 취소 (아래 규칙) | O (취소 상태 그대로 기록) | 취소 목록 | 건수 표기 `(취소 N건)` |
| skipped | 완전제외 | X | X | — |

- **취소 판정 규칙 (parse_order·build_snapshot·generate_sheets·build_payout_tax 공통)**: 주문상태에 `취소`(취소/미결제취소) **또는** 클레임상태·`취소 처리상태`가 `취소요청`/`취소처리중`/`취소완료`. `취소철회`는 정상 주문. 취소 건은 Raw_Data에 기록되지만 매출·수량·정산 집계에서 모두 제외
- **취소관리 파일** (`스마트스토어_*취소관리_*.xlsx`, 시트 `취소관리`, `취소 처리상태` 열): 발주발송관리 목록에 빠진 취소 건을 Raw_Data에 취소로 기록. 이미 기록된 주문이 이 파일(또는 다른 주문 파일)에서 상태가 바뀌면 `주문상태`·`클레임상태`를 제자리 갱신 (사후 취소 → 집계 제외, 취소철회 → 집계 복귀). 취소 건이 있는 날은 **발주발송관리 + 취소관리 두 파일을 모두** 다운로드해야 함
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
| 마스터 DB (2026-08 이전 레거시, 더 이상 파싱에 사용 안 함) | `C:\Users\user\비서\스케줄\0. 유튜브 인플루언서 관리_*.xlsx` |
| 메일발송현황 소스 (2026-08~, 퍼널 KPI) | `G:\.shortcut-targets-by-id\1aExMnOUaz0KyUTRAhiSvAjCebgHx7Wa1\스카이님 공유용 스프레드 개설\1. <종류> 인플루언서 관리_공유_YYMMDD.xlsx` — `parse_mail.py`가 종류별 최신 날짜 파일 자동 선택 (종합 = 유튜브, `~$`·백업 제외). 시트 `메일발송현황*` 6행 헤더: A열 `구분`(담당자 ㅇ, 2026-10-07 삽입) → 분류 → … |
| 인플루언서관리 소스 (상태값·체험·광고, 영끌러님 ㅇ 명단·제품) | 같은 폴더 `인플루언서 종합 관리시트.xlsx` 시트 `인플루언서관리` (전치형: A열 라벨, 열=인플루언서) — `parse_inf.py`. `영끌러님 관리` 행 ㅇ = 영끌러님 담당, `제품` 행 = 담당 제품 (사장님이 직접 입력, 자동 생성 금지) |
| 영끌러님 대시보드 | `C:\Users\user\비서\site\yk\` (`index.html`·`assets/app.js` 자체 사본, `data/`는 `build_yk.py` 산출) → `https://geuneee.github.io/inf-ops-dashboard/yk/`. **2026-10부터 집계** (`build_yk.py` `YK_START_MONTH`, 이전 월 데이터 제외). 종합 대시보드 요약·흑염소·제품 탭 상단 KPI 아래 "영끌러님 매출·수익" 미니 블럭이 `yk/data/dashboard.json`(trends)을 읽어 표시 (선택 월 연동) |
| 주문 드롭 폴더 | `C:\Users\user\비서\스케줄\` (우선) / `C:\Users\user\비서\input\` (보조) |
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
