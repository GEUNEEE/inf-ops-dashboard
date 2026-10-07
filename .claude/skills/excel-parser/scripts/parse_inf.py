#!/usr/bin/env python3
# parse_inf.py — STEP 2: 인플루언서관리 시트 → managed_set + 상태 집계 반환
# 출력: stdout JSON
#
# 2026-10: 소스를 `인플루언서 종합 관리시트.xlsx`로 변경하고 행 번호 고정 → A열 라벨 탐색으로 변경.
#          build_yk.py에서 import 해 name_filter(영끌러님 ㅇ 명단)로 재사용한다.
#          `영끌러님 관리` 행의 ㅇ 표시 → yk_marked, `제품` 행 → product_by_name 을 항상 함께 반환.
import sys
import json
import re
from pathlib import Path
from datetime import date, datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import openpyxl

EXCEL_DIR        = Path(r"G:\.shortcut-targets-by-id\1aExMnOUaz0KyUTRAhiSvAjCebgHx7Wa1\스카이님 공유용 스프레드 개설")
MASTER_XLSX_NAME = "인플루언서 종합 관리시트.xlsx"
SHEET_NAME       = "인플루언서관리"
CONFIG_PATH      = Path(r"C:\Users\user\비서\.claude\skills\settlement-generator\scripts\ytber_config.json")

# A열 라벨 (공백 제거 후 완전 일치). 전치형: 행=항목, 열=인플루언서
LABEL_STATUS  = "현재상태"
LABEL_NAME    = "유튜버명"
LABEL_YK      = "영끌러님관리"
LABEL_PRODUCT = "제품"            # "제품 발송일"과 다름 — 완전 일치만 인정
LABEL_EXP_ACCEPT = "체험수락일"   # 1차 체험 수락일 (월별 체험 인원 집계)
EXP_LABELS = ["체험수락일", "2차체험", "3차체험", "4차체험"]
AD_LABELS  = ["1차광고", "2차광고", "3차광고", "4차광고"]

SPONSOR_COST_PER_EXP = 40000
OWNER_MARKS = {"ㅇ", "o", "O", "○"}

STATUS_CATEGORIES = {
    "미팅대기": "미팅_대기",
    "미팅진행": "미팅_진행",
    "1차체험진행": "체험진행_1차",
    "2차체험진행": "체험진행_2차",
    "3차체험진행": "체험진행_3차",
    "1차광고예정": "광고예정_1차",
    "2차광고예정": "광고예정_2차",
    "1차광고완료": "광고완료_1차",
    "기타": "기타",
}

PRODUCT_ALIASES = [
    # (포함 키워드, 정규 제품명) — 앞에서부터 첫 매칭
    ("수면", "수면영양제"),
    ("슬립", "수면영양제"),
    ("스팟멜트", "화장품"),
    ("화장품", "화장품"),
    ("흑염소", "흑염소"),
    ("올리브", "올리브오일캡슐"),
]


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _norm(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", "", str(v))


def is_owner_mark(val) -> bool:
    return _norm(val) in OWNER_MARKS


def normalize_product(raw) -> str:
    """제품 셀 값 → 정규 제품명. 빈값이면 ''. 알 수 없는 값은 공백 제거한 원문."""
    s = _norm(raw)
    if not s:
        return ""
    for kw, canon in PRODUCT_ALIASES:
        if kw in s:
            return canon
    return s


def find_master_xlsx(shared_dir: Path = EXCEL_DIR) -> Path:
    """종합 관리시트 우선, 없으면 유튜브 공유 파일 최신본으로 폴백."""
    master = Path(shared_dir) / MASTER_XLSX_NAME
    if master.exists():
        return master
    print(f"[WARN] {MASTER_XLSX_NAME} 없음 → 유튜브 공유 파일로 폴백", file=sys.stderr)
    return find_latest_excel(shared_dir)


def find_latest_excel(excel_dir: Path) -> Path:
    pattern = re.compile(r"유튜브 인플루언서 관리_공유_(\d{6})")
    candidates = []
    for f in Path(excel_dir).glob("*.xlsx"):
        if f.name.startswith("~$") or "백업" in f.name or "backup" in f.name.lower():
            continue
        m = pattern.search(f.name)
        if m:
            candidates.append((int(m.group(1)), f.name, f))
    if not candidates:
        raise FileNotFoundError(f"'{excel_dir}'에서 마스터 DB xlsx를 찾을 수 없습니다.")
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def safe_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def is_date(val) -> bool:
    if val is None:
        return False
    if isinstance(val, (datetime, date)):
        return True
    if isinstance(val, str) and val.strip():
        return True
    return False


def _to_ym(val):
    try:
        if isinstance(val, (date, datetime)):
            dt = val
        else:
            dt = datetime.strptime(str(val).strip(), "%Y-%m-%d")
        return dt.strftime("%Y-%m")
    except Exception:
        return None


def build_row_index(rows) -> dict:
    """A열 라벨(공백 제거) → 0-based 행 인덱스. 같은 라벨이 여러 번 나오면 첫 등장만."""
    idx: dict = {}
    for i, row in enumerate(rows):
        if not row:
            continue
        key = _norm(row[0])
        if key and key not in idx:
            idx[key] = i
    return idx


def _cell(rows, r, c):
    if r is None or r >= len(rows):
        return None
    row = rows[r]
    return row[c] if c < len(row) else None


def parse_rows(rows, config: dict, name_filter=None, source_file: str = "") -> dict:
    """시트 전체 행(values) → 집계 dict.
    name_filter: name_map 정규화된 이름을 받아 True/False (None이면 전원)."""
    rows = list(rows)
    ridx = build_row_index(rows)
    if LABEL_NAME not in ridx:
        raise ValueError(f"'{LABEL_NAME}' 라벨 행을 찾을 수 없습니다 (A열 라벨: {list(ridx)[:15]}…)")

    r_name    = ridx[LABEL_NAME]
    r_status  = ridx.get(LABEL_STATUS)
    r_yk      = ridx.get(LABEL_YK)
    r_product = ridx.get(LABEL_PRODUCT)
    r_exp_acc = ridx.get(LABEL_EXP_ACCEPT)
    exp_rows  = [ridx[l] for l in EXP_LABELS if l in ridx]
    ad_rows   = [ridx[l] for l in AD_LABELS if l in ridx]
    if r_yk is None:
        print(f"[WARN] '{LABEL_YK}' 행 없음 → 영끌러님 표시 0명", file=sys.stderr)
    if r_product is None:
        print(f"[WARN] '{LABEL_PRODUCT}' 행 없음 → 제품은 Raw_Data 추정/미지정", file=sys.stderr)

    name_row = rows[r_name]
    start_col = 1
    while start_col < len(name_row) and not safe_str(name_row[start_col]):
        start_col += 1

    name_map      = config.get("name_map", {})
    sponsor_extra = config.get("sponsor_extra", {})

    managed_set, yk_marked, product_by_name = [], [], {}
    status_counter = {v: 0 for v in STATUS_CATEGORIES.values()}
    status_counter["기타"] = 0
    ad_total = 0
    ad_by_month: dict = {}
    exp_by_month: dict = {}
    per_influencer: dict = {}

    for col_idx in range(start_col, len(name_row)):
        name = safe_str(name_row[col_idx])
        if not name:
            break
        normalized_name = name_map.get(name, name)

        # ㅇ 표시·제품은 필터와 무관하게 항상 수집 (build_yk가 명단을 만들 때 사용)
        if r_yk is not None and is_owner_mark(_cell(rows, r_yk, col_idx)):
            yk_marked.append(normalized_name)
        if r_product is not None:
            prod = normalize_product(_cell(rows, r_product, col_idx))
            if prod:
                product_by_name[normalized_name] = prod

        if name_filter is not None and not name_filter(normalized_name):
            continue

        managed_set.append(name)

        status_raw = safe_str(_cell(rows, r_status, col_idx)) if r_status is not None else ""
        category = STATUS_CATEGORIES.get(_norm(status_raw), "기타")
        status_counter[category] = status_counter.get(category, 0) + 1

        exp_cnt = 0
        exp_months = []
        for er in exp_rows:
            val = _cell(rows, er, col_idx)
            if is_date(val):
                exp_cnt += 1
                exp_months.append(_to_ym(val))
        exp_cnt = max(1, exp_cnt)   # 등록 = 최소 1회 체험 기준

        extra_months = sponsor_extra.get(normalized_name) or sponsor_extra.get(name) or []
        if isinstance(extra_months, list) and extra_months:
            exp_months.extend(extra_months)
            exp_cnt += len(extra_months)

        per_influencer[normalized_name] = {
            "status": category,
            "exp_count": exp_cnt,
            "sponsor_cost": exp_cnt * SPONSOR_COST_PER_EXP,
            "exp_months": exp_months,
        }

        if r_exp_acc is not None:
            val = _cell(rows, r_exp_acc, col_idx)
            if val is not None:
                ym = _to_ym(val)
                if ym:
                    exp_by_month[ym] = exp_by_month.get(ym, 0) + 1

        for ar in ad_rows:
            val = _cell(rows, ar, col_idx)
            if not is_date(val):
                continue
            ad_total += 1
            ym = _to_ym(val)
            if ym:
                ad_by_month[ym] = ad_by_month.get(ym, 0) + 1

    exp_total = sum(exp_by_month.values())
    meeting_total = status_counter.get("미팅_대기", 0) + status_counter.get("미팅_진행", 0)

    return {
        "managed_set": managed_set,
        "managed_count": len(managed_set),
        "inf_status": status_counter,
        "meeting_total": meeting_total,
        "exp_total": exp_total,
        "exp_by_month": dict(sorted(exp_by_month.items())),
        "ad_total": ad_total,
        "ad_by_month": dict(sorted(ad_by_month.items())),
        "per_influencer": per_influencer,
        "yk_marked": yk_marked,
        "product_by_name": product_by_name,
        "source_file": source_file,
    }


def parse_master(excel_path, config: dict, name_filter=None) -> dict:
    wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
    try:
        if SHEET_NAME not in wb.sheetnames:
            raise ValueError(f"시트 '{SHEET_NAME}' 없음. 목록: {wb.sheetnames}")
        rows = list(wb[SHEET_NAME].iter_rows(values_only=True))
    finally:
        wb.close()
    return parse_rows(rows, config, name_filter=name_filter, source_file=Path(excel_path).name)


def main():
    try:
        excel_path = find_master_xlsx(EXCEL_DIR)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 마스터DB: {excel_path.name}", file=sys.stderr)
    try:
        result = parse_master(excel_path, load_config())
    except Exception as e:
        print(f"[ERROR] 인플루언서관리 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[INFO] 인플루언서관리 파싱 완료 — {result['managed_count']}명 (영끌러님 ㅇ {len(result['yk_marked'])}명)",
          file=sys.stderr)


if __name__ == "__main__":
    main()
