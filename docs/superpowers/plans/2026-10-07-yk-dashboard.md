# 영끌러님 대시보드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종합 대시보드를 그대로 복제해 `site/yk/`에 영끌러님(ㅇ 표시) 몫만 보여주는 두 번째 대시보드를 만들고, 파이프라인·엑셀 원본·문서를 그에 맞게 연결한다.

**Architecture:** 원본 파서(`parse_mail.py`, `parse_inf.py`)를 헤더/라벨 기반 탐색 + 필터 파라미터를 받는 함수형으로 리팩터링하고(출력 수치 불변), `build_snapshot.py` 집계 함수에 `name_filter`를 추가한 뒤, 이를 모두 import 하는 `build_yk.py`가 `site/yk/data/`를 생성한다. 화면은 `site/` 복제본에 최소 조정(탭 키, 제품별 퍼널, 운영 현황 카드).

**Tech Stack:** Python 3 (openpyxl, win32com 1회성), stdlib `unittest`, vanilla JS + Chart.js 4, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-07-yk-dashboard-design.md`

## Global Constraints

- 종합 대시보드(`site/index.html`, `site/assets/app.js`, `site/data/**`)는 **변경 금지**. `site/data/dashboard.json`의 `mail_funnel.total_sent`는 4013 유지.
- 종합 관리시트(`인플루언서 종합 관리시트.xlsx`)는 **읽기만** — `제품` 행은 사장님이 추가.
- 메일발송현황 시트의 `구분` 열은 **삽입**(기존 A열 값 덮어쓰기 금지), 6행 헤더 `구분`, 7행부터 데이터.
- ㅇ 판정: 공백 제거 후 `ㅇ`/`o`/`O`/`○`.
- 제품 정규화: `수면`·`슬립이지`→`수면영양제`, `스팟멜트`→`화장품`, 빈값→Raw_Data 추정→`미지정`.
- 파일 패턴 `<종류> 인플루언서 관리_공유_(\d{6})`, `~$`·`백업`·`backup` 제외, 최신 1개. 시트명은 `메일발송현황`으로 시작.
- 열·행 번호 고정 금지(헤더/라벨 기반).
- 탭 순서 localStorage 키 `dashTabOrder_yk`. 공개 주소 `https://geuneee.github.io/inf-ops-dashboard/yk/`.
- 테스트: `PYTHONUTF8=1 .venv\Scripts\python.exe -m unittest tests.test_build_yk -v`.
- 커밋은 작업 파일만 `git add` (작업 트리에 무관한 변경 다수). 커밋 메시지 말미 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

### Task 1: parse_mail.py 헤더 기반 리팩터링 + 테스트

**Files:**
- Modify: `.claude/skills/excel-parser/scripts/parse_mail.py` (전면 재작성, stdout JSON 동일)
- Test: `tests/test_build_yk.py` (신규, `TestParseMail`)

**Interfaces (Produces):**
- `find_shared_xlsx(kind="유튜브", shared_dir=_SHARED_DIR) -> Path | None`
- `SHEET_PREFIX, HEADER_ROW=6, DATA_START_ROW=7, OWNER_HEADER="구분", OWNER_MARKS`
- `is_owner_mark(val) -> bool`, `_norm(v) -> str`
- `find_mail_sheet(wb) -> Worksheet | None`
- `header_columns(header_row) -> dict[str,int]` (필수 헤더 없으면 ValueError)
- `parse_mail_sheet(ws, owner_filter=None) -> dict` (키: total_sent, etc_excluded, replied, reply_rate, meeting_total, meeting_rate, exp_total_approx, ad_total, by_month)
- `parse_mail_workbook(path, owner_filter=None) -> dict`
- `merge_mail_results(results: list[dict]) -> dict`
- `empty_result() -> dict`

- [ ] Step 1: 테스트 작성 — ㅇ 4종, 헤더 기반(구분 삽입 전/후 동일 total), owner_filter(ㅇ 행만·구분 없으면 0), 시트 접미사, merge, find_shared_xlsx 제외 규칙
- [ ] Step 2: 실패 확인 (`ImportError`)
- [ ] Step 3: 구현 (import-time 파일 탐색 제거, 모듈 레벨 상수 유지)
- [ ] Step 4: 테스트 통과 + `parse_mail.py` 실제 실행 → `total_sent == 4013` 확인
- [ ] Step 5: Commit `refactor(parse_mail): 헤더 기반 열 탐색 + owner 필터`

### Task 2: parse_inf.py 라벨 기반 리팩터링 + 테스트

**Files:**
- Modify: `.claude/skills/excel-parser/scripts/parse_inf.py`
- Test: `tests/test_build_yk.py` (`TestParseInf`)

**Interfaces (Produces):**
- `MASTER_XLSX_NAME`, `LABEL_*`, `EXP_LABELS`, `AD_LABELS`
- `build_row_index(rows) -> dict[str,int]` (A열 라벨 정규화→첫 등장 행 인덱스, 완전 일치)
- `normalize_product(raw) -> str` ("" if empty)
- `find_master_xlsx(shared_dir=EXCEL_DIR) -> Path`
- `parse_rows(rows, config, name_filter=None, source_file="") -> dict` (기존 키 + `yk_marked`, `product_by_name`, `source_file`)
- `parse_master(excel_path, config, name_filter=None) -> dict`

- [ ] Step 1: 테스트 — 라벨 탐색(행 삽입 후 동일), `제품` vs `제품 발송일`, yk_marked/product_by_name, normalize_product, name_filter
- [ ] Step 2: 실패 확인
- [ ] Step 3: 구현 (소스 = 종합 관리시트, 없으면 유튜브 파일 폴백)
- [ ] Step 4: 테스트 통과 + 실제 실행 → 이전 출력과 managed_count/exp_total/ad_total 비교 기록
- [ ] Step 5: Commit

### Task 3: build_snapshot.py `name_filter`

**Files:** Modify `.claude/skills/dashboard-builder/scripts/build_snapshot.py:128,239,307`
**Interfaces:** `aggregate_by_product_store(target_month, config, name_filter=None)`, `aggregate_cosmetics_breakdown(target_month, name_filter=None)`, `aggregate_product_trials(target_month, name_filter=None)`; `name_filter(ytber_raw) -> bool`, None이면 전체(기존 동작).
- [ ] 테스트(RAWDATA_PATH 몽키패치 픽스처) → 구현 → 통과 → Commit

### Task 4: yk_excel_setup.py (1회성 엑셀 변경, win32com)

**Files:** Create `.claude/skills/excel-parser/scripts/yk_excel_setup.py`
- 백업 `<stem>_백업_YYMMDD.xlsx` (있으면 skip), 실행 중 Excel 재사용(`GetActiveObject`), 열린 워크북 재사용, `ReadOnly`면 중단.
- 뷰티·유튜브 `메일발송현황*` 시트: A6가 `구분`이면 skip, 아니면 A열 삽입 + `A6="구분"`.
- 슬립이지 파일 생성: 뷰티 복사 → 시트명 정리 → 데이터 비우기(헤더·수식 유지).
- [ ] 작성 → 실행 → `parse_mail.py` 재실행 total_sent 4013 확인 → Commit

### Task 5: build_yk.py

**Files:** Create `.claude/skills/dashboard-builder/scripts/build_yk.py`
**Interfaces:** `mail_cum_through(by_month, month) -> dict`, `filter_settlement(settlement, names) -> dict`, `resolve_products(names, product_by_name, raw_products) -> dict`, `raw_product_majority(name_filter) -> dict`, `main(argv)`; CLI `--no-filter`, `--out`, `--month`.
- 출력 `site/yk/data/dashboard.json` (종합 키 + `mail_funnel_by_product`, `ops_summary`, `influencer_products`, `manual_sales=[]`), `history/YYYY-MM.json`, `influencer/<name>.json`.
- [ ] 헬퍼 테스트 → 구현 → `--no-filter` 정합(제품×월 매출·수량 = 종합 history, total_sent 4013) → Commit

### Task 6: site/yk/ 복제 + 화면 조정

**Files:** Create `site/yk/index.html`, `site/yk/influencer.html`, `site/yk/assets/app.js`
- 제목 "영끌러님 대시보드", performance 링크 제거, 운영 현황 카드, 지인판매 카드 제거, 제품 탭 퍼널/카드, 흑염소 탭은 `mail_funnel_by_product.흑염소`.
- [ ] `node --check` → 로컬 렌더(http.server + 브라우저 스크린샷 또는 DOM 검사) → Commit

### Task 7: 파이프라인·알림·sync_core·문서

**Files:** Modify `run_pipeline.py`(STEP 8.5), `notify.py:89`, `sync_core.py:68-77`, `CLAUDE.md`, `.claude/skills/dashboard-builder/SKILL.md`
- [ ] 수정 → `python -m py_compile` → Commit

### Task 8: 회귀·배포

- [ ] `git diff --stat site/data/` 비어 있음, `site/data/dashboard.json` total_sent 4013
- [ ] `publish.py` 배포 → 두 URL 확인 → 인수인계 항목 보고

## Self-review
- 스펙 §2(판정·정규화·파일/시트/열/행 탐색) → Task 1·2. §3(엑셀 1회성·파급) → Task 4·7. §4·5(화면) → Task 6. §6(build_yk) → Task 3·5. §7(파이프라인) → Task 7. §8(검증) → Task 1·2·5·8 + 수동 대조는 사장님 ㅇ 표시 후.
