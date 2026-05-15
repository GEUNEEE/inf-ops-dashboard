#!/usr/bin/env python3
# parse_inf.py — STEP 2: 인플루언서관리 시트 → managed_set + 상태 집계 반환
# 출력: stdout JSON
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

EXCEL_DIR  = Path(r"C:\Users\user\비서\스케줄")
SHEET_NAME = "인플루언서관리"

# 0-based 행 인덱스 (전치형: 행=항목, 열=인플루언서)
ROW_STATUS = 9   # Excel Row 10: 현재상태
ROW_NAME   = 10  # Excel Row 11: 유튜버명

STATUS_CATEGORIES = {
    "1차체험진행": "체험진행_1차",
    "2차체험진행": "체험진행_2차",
    "3차체험진행": "체험진행_3차",
    "1차광고예정": "광고예정_1차",
    "2차광고예정": "광고예정_2차",
    "1차광고완료": "광고완료_1차",
    "기타": "기타",
}


def find_latest_excel(excel_dir: Path) -> Path:
    pattern = re.compile(r"인플루언서 관리_(\d{6})")
    candidates = []
    for f in excel_dir.glob("*.xlsx"):
        if f.name.startswith("~$") or "백업" in f.name:
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


def main():
    try:
        excel_path = find_latest_excel(EXCEL_DIR)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 마스터DB: {excel_path.name}", file=sys.stderr)

    try:
        wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=True)
    except Exception as e:
        print(f"[ERROR] 엑셀 읽기 실패: {e}", file=sys.stderr)
        sys.exit(1)

    if SHEET_NAME not in wb.sheetnames:
        print(f"[ERROR] 시트 '{SHEET_NAME}' 없음. 목록: {wb.sheetnames}", file=sys.stderr)
        sys.exit(1)

    ws = wb[SHEET_NAME]
    rows = list(ws.iter_rows(values_only=True))
    n_rows = len(rows)

    if ROW_NAME >= n_rows:
        print(f"[ERROR] 시트 행 수({n_rows}) < ROW_NAME({ROW_NAME})", file=sys.stderr)
        sys.exit(1)

    # 인플루언서 컬럼 탐색 (Row 11 비어있지 않은 첫 열부터)
    name_row = rows[ROW_NAME]
    start_col = 1
    while start_col < len(name_row) and not safe_str(name_row[start_col]):
        start_col += 1

    managed_set = []
    status_counter = {v: 0 for v in STATUS_CATEGORIES.values()}
    status_counter["기타"] = 0

    ad_counts = {"광고예정_1차": 0, "광고예정_2차": 0, "광고완료_1차": 0}

    for col_idx in range(start_col, len(name_row)):
        name = safe_str(name_row[col_idx])
        if not name:
            break

        status_raw = ""
        if ROW_STATUS < n_rows and col_idx < len(rows[ROW_STATUS]):
            status_raw = safe_str(rows[ROW_STATUS][col_idx])

        normalized = re.sub(r"\s+", "", status_raw)
        managed_set.append(name)

        category = STATUS_CATEGORIES.get(normalized, "기타")
        status_counter[category] = status_counter.get(category, 0) + 1

    wb.close()

    # 광고수락률용 광고 단계 합산
    ad_total = (
        status_counter.get("광고예정_1차", 0)
        + status_counter.get("광고예정_2차", 0)
        + status_counter.get("광고완료_1차", 0)
    )
    exp_total = (
        status_counter.get("체험진행_1차", 0)
        + status_counter.get("체험진행_2차", 0)
        + status_counter.get("체험진행_3차", 0)
        + ad_total
    )

    result = {
        "managed_set": managed_set,
        "managed_count": len(managed_set),
        "inf_status": status_counter,
        "exp_total": exp_total,
        "ad_total": ad_total,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[INFO] 인플루언서관리 파싱 완료 — {len(managed_set)}명", file=sys.stderr)


if __name__ == "__main__":
    main()
