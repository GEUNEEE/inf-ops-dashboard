#!/usr/bin/env python3
# extract.py - 인플루언서 관리 엑셀 파싱 스크립트
# 출력: output/YYYY-MM-DD_parsed.json
import sys
import json
import re
from pathlib import Path
from datetime import date, datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd

EXCEL_DIR  = Path(r"C:\Users\user\비서\스케줄")
OUTPUT_DIR = Path(r"C:\Users\user\비서\output")
SHEET_NAME = "인플루언서관리"

ROW_STATUS = 9   # Excel Row 10: 진행상태
ROW_NAME   = 10  # Excel Row 11: 유튜버명
ROW_NOTE   = 19  # Excel Row 20: 비고

# A열 날짜 행 동적 탐색 시작 행 (Excel Row 28 = index 27)
DATE_SCAN_START = 27
# 이 문자열이 A열에 나타나면 날짜 행 탐색 종료
STOP_MARKERS = ["광고여부확인일", "광고 여부 확인일"]

# 체험 완료 후 광고 날짜 미입력 여부 체크 쌍 (trigger → expected_ad)
AD_PAIRS = [
    ("체험 종료",  "1차 광고"),
    ("2차 체험",   "2차 광고"),
    ("3차 체험",   "3차 광고"),
    ("4차 체험",   "4차 광고"),
]

STATUS_EMOJI = {
    "1차체험진행": "🔵",
    "1차광고예정": "🟡",
    "1차광고완료": "✅",
    "2차체험진행": "🟣",
    "2차광고예정": "🟠",
    "2차광고완료": "✅✅",
    "기타":       "❌",
}


def find_latest_excel(excel_dir: Path) -> Path:
    pattern = re.compile(r"인플루언서 관리_(\d{6})")
    candidates = []
    for f in excel_dir.glob("*.xlsx"):
        if f.name.startswith("~$"):
            continue
        m = pattern.search(f.name)
        if m:
            candidates.append((int(m.group(1)), f.name, f))
    if not candidates:
        raise FileNotFoundError(
            f"'{excel_dir}'에서 '인플루언서 관리_YYMMDD' 패턴 xlsx 파일을 찾을 수 없습니다."
        )
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def get_status_emoji(raw: str) -> str:
    normalized = re.sub(r"\s+", "", raw.strip())
    return STATUS_EMOJI.get(normalized, "❓")


def parse_date_cell(val) -> "date | None":
    if val is None:
        return None
    if isinstance(val, float) and (val != val):
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y.%m.%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
    return None


def safe_str(val) -> str:
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    return str(val).strip()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()

    try:
        excel_path = find_latest_excel(EXCEL_DIR)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 파싱 대상: {excel_path.name}", file=sys.stderr)

    try:
        df = pd.read_excel(
            excel_path,
            sheet_name=SHEET_NAME,
            header=None,
            dtype=object,
        )
    except Exception as e:
        print(f"[ERROR] 엑셀 읽기 실패: {e}", file=sys.stderr)
        sys.exit(1)

    n_rows, n_cols = df.shape

    # A열에서 날짜 행 동적 탐색 (DATE_SCAN_START ~ 광고여부확인일 직전)
    date_rows = {}
    for row_idx in range(DATE_SCAN_START, n_rows):
        label = safe_str(df.iloc[row_idx, 0])
        if not label:
            continue
        if any(m in label for m in STOP_MARKERS):
            break
        date_rows[label] = row_idx

    print(f"[INFO] 날짜 행 {len(date_rows)}개 감지: {list(date_rows.keys())}", file=sys.stderr)

    # 인플루언서 컬럼 스캔 (Row 11이 비어있지 않은 첫 번째 열부터)
    influencers = []
    start_col = 1
    while start_col < n_cols and safe_str(df.iloc[ROW_NAME, start_col]) == "":
        start_col += 1

    for col_idx in range(start_col, n_cols):
        if ROW_NAME >= n_rows:
            break
        name = safe_str(df.iloc[ROW_NAME, col_idx])
        if not name:
            break

        status_raw = safe_str(df.iloc[ROW_STATUS, col_idx]) if ROW_STATUS < n_rows else ""
        normalized_status = re.sub(r"\s+", "", status_raw.strip())

        # 기타 상태 제외
        if normalized_status == "기타":
            continue

        status_emoji = get_status_emoji(status_raw)
        note = safe_str(df.iloc[ROW_NOTE, col_idx]) if ROW_NOTE < n_rows else ""

        # 각 인플루언서의 마지막(가장 먼 미래) 일정 하나만 upcoming으로 선택
        last_future: "dict | None" = None

        for item_name, row_idx in date_rows.items():
            if row_idx >= n_rows:
                continue
            item_date = parse_date_cell(df.iloc[row_idx, col_idx])
            if item_date is None:
                continue
            delta = (item_date - today).days
            if delta >= 0:
                if last_future is None or item_date > datetime.strptime(last_future["date"], "%Y-%m-%d").date():
                    last_future = {
                        "item":       item_name,
                        "date":       item_date.strftime("%Y-%m-%d"),
                        "days_until": delta,
                    }

        upcoming = [last_future] if last_future else []

        # 광고 날짜 미입력 체크: n차 체험 날짜는 있는데 n차 광고 날짜가 없는 경우
        missing_ad = []
        for trigger_item, ad_item in AD_PAIRS:
            if trigger_item not in date_rows or ad_item not in date_rows:
                continue
            trigger_date = parse_date_cell(df.iloc[date_rows[trigger_item], col_idx])
            ad_date = parse_date_cell(df.iloc[date_rows[ad_item], col_idx])
            if trigger_date is not None and ad_date is None:
                missing_ad.append({
                    "trigger": trigger_item,
                    "missing": ad_item,
                })

        influencers.append({
            "name":         name,
            "status":       status_raw,
            "status_emoji": status_emoji,
            "note":         note,
            "upcoming":     upcoming,
            "missing_ad":   missing_ad,
        })

    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date_range": {
            "start": today.strftime("%Y-%m-%d"),
        },
        "influencers": influencers,
    }

    out_path = OUTPUT_DIR / f"{today.strftime('%Y-%m-%d')}_parsed.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[INFO] JSON 저장 완료: {out_path}", file=sys.stderr)
    print(f"[INFO] 인플루언서 {len(influencers)}명 파싱 완료 (기타 제외)", file=sys.stderr)


if __name__ == "__main__":
    main()
