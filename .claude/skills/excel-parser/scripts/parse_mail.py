#!/usr/bin/env python3
# parse_mail.py — STEP 1: 메일발송현황 시트 파싱 → 퍼널 KPI 반환
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
SHEET_NAME = "메일발송현황"

# 0-based 열 인덱스 (Excel 열 번호 - 1)
COL_SEND_DATE   = 24  # 열 25 = 발송일
COL_REPLY_DATE  = 26  # 열 27 = 회신일
COL_STATUS      = 27  # 열 28 = 진행상태
COL_ACCEPT_DATE = 29  # 열 30 = 협찬수락일
DATA_START_ROW  = 7   # 1-based

ETC_KEYWORDS = {"검토", "진행불가", "우리측거절", "기타"}
MEETING_KEYWORDS = {"미팅대기", "미팅진행", "미팅예정"}
AD_KEYWORDS = {"광고예정", "광고완료", "광고진행"}


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


def cell_val(ws, row_1based, col_0based):
    try:
        return ws.cell(row=row_1based, column=col_0based + 1).value
    except Exception:
        return None


def is_date(val) -> bool:
    if val is None:
        return False
    if isinstance(val, (datetime, date)):
        return True
    if isinstance(val, str) and val.strip():
        return True
    return False


def normalize_status(raw) -> str:
    if raw is None:
        return ""
    return re.sub(r"\s+", "", str(raw).strip())


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
        print(f"[ERROR] 시트 '{SHEET_NAME}' 없음. 시트 목록: {wb.sheetnames}", file=sys.stderr)
        sys.exit(1)

    ws = wb[SHEET_NAME]
    max_row = ws.max_row or 0

    total_sent = 0
    etc_count  = 0
    replied    = 0
    meeting    = 0
    exp_total  = 0  # 인플루언서관리 시트에서 채움 — 여기선 협찬수락일로 근사
    ad_total   = 0

    for row in range(DATA_START_ROW, max_row + 1):
        send_date   = cell_val(ws, row, COL_SEND_DATE)
        reply_date  = cell_val(ws, row, COL_REPLY_DATE)
        status_raw  = cell_val(ws, row, COL_STATUS)
        accept_date = cell_val(ws, row, COL_ACCEPT_DATE)

        if not is_date(send_date):
            continue

        status = normalize_status(status_raw)

        # 기타 상태 → 분모·분자 모두 제외
        if any(k in status for k in ETC_KEYWORDS) or status == "기타":
            etc_count += 1
            continue

        total_sent += 1

        # 응답: 회신일 있음 OR 진행상태 기재 OR 협찬수락일 있음
        if is_date(reply_date) or status or is_date(accept_date):
            replied += 1

        # 미팅: 미팅대기/미팅진행/미팅예정
        if any(k in status for k in MEETING_KEYWORDS):
            meeting += 1

        # 협찬수락일로 체험전환 근사 (정확값은 인플루언서관리 시트에서)
        if is_date(accept_date):
            exp_total += 1

        # 광고단계
        if any(k in status for k in AD_KEYWORDS):
            ad_total += 1

    wb.close()

    result = {
        "total_sent":    total_sent,
        "etc_excluded":  etc_count,
        "replied":       replied,
        "reply_rate":    round(replied / total_sent, 4) if total_sent else 0,
        "meeting_total": meeting,
        "meeting_rate":  round(meeting / total_sent, 4) if total_sent else 0,
        "exp_total_approx": exp_total,
        "ad_total":      ad_total,
        "ad_rate":       round(ad_total / total_sent, 4) if total_sent else 0,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[INFO] 메일발송현황 파싱 완료 — 총발송 {total_sent}건, 기타제외 {etc_count}건", file=sys.stderr)


if __name__ == "__main__":
    main()
