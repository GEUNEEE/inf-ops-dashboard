#!/usr/bin/env python3
# parse_mail.py — STEP 1: 메일발송현황 시트 파싱 → 퍼널 KPI 반환
# 출력: stdout JSON
#
# 2026-10: 열 번호 고정 → 6행 헤더 글자 기반 탐색으로 변경 (구분 열 삽입 대응).
#          build_yk.py에서 import 해 owner_filter(구분=ㅇ)로 재사용한다.
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

# 2026-08부터: 메일발송현황·인플루언서관리 둘 다 스카이님 공유 스프레드시트가 소스
_SHARED_DIR = Path(r"G:\.shortcut-targets-by-id\1aExMnOUaz0KyUTRAhiSvAjCebgHx7Wa1\스카이님 공유용 스프레드 개설")

SHEET_PREFIX   = "메일발송현황"   # 시트명은 이 글자로 시작 (뷰티 파일은 접미사 있음)
HEADER_ROW     = 6                # 1-based 헤더 행
DATA_START_ROW = 7                # 1-based 데이터 시작 행
OWNER_HEADER   = "구분"           # 담당자 표시 열 헤더 (영끌러님 = ㅇ)
OWNER_MARKS    = {"ㅇ", "o", "O", "○"}

H_SEND, H_REPLY, H_STATUS, H_MTG, H_ACCEPT, H_AD = (
    "발송일", "회신일", "진행상태", "미팅일", "협찬수락일", "광고수락일")
REQUIRED_HEADERS = (H_SEND, H_REPLY, H_STATUS, H_MTG, H_ACCEPT, H_AD)

ETC_KEYWORDS = {"검토", "진행불가", "우리측거절", "기타"}


def _norm(v) -> str:
    """셀 값 → 공백 전부 제거한 문자열 (헤더/라벨/표시값 비교용)."""
    if v is None:
        return ""
    return re.sub(r"\s+", "", str(v))


def is_owner_mark(val) -> bool:
    return _norm(val) in OWNER_MARKS


def find_shared_xlsx(kind: str = "유튜브", shared_dir: Path = _SHARED_DIR):
    """`<kind> 인플루언서 관리_공유_YYMMDD.xlsx` 중 날짜 최신 1개. 없으면 None.
    `~$` 잠금 파일, 백업/backup 사본은 제외."""
    pattern = re.compile(rf"{re.escape(kind)} 인플루언서 관리_공유_(\d{{6}})")
    candidates = []
    try:
        files = list(Path(shared_dir).glob("*.xlsx"))
    except OSError:
        return None
    for f in files:
        low = f.name.lower()
        if f.name.startswith("~$") or "백업" in f.name or "backup" in low:
            continue
        m = pattern.search(f.name)
        if m:
            candidates.append((int(m.group(1)), f.name, f))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


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


def find_mail_sheet(wb):
    """이름이 SHEET_PREFIX로 시작하는 첫 시트. 없으면 None."""
    for name in wb.sheetnames:
        if name.startswith(SHEET_PREFIX):
            return wb[name]
    return None


def header_columns(header_row) -> dict:
    """헤더 행(iterable) → {정규화 헤더: 0-based 열 인덱스}. 필수 헤더 누락 시 ValueError."""
    cols: dict = {}
    for idx, v in enumerate(header_row):
        key = _norm(v)
        if key and key not in cols:
            cols[key] = idx
    missing = [h for h in REQUIRED_HEADERS if h not in cols]
    if missing:
        raise ValueError(f"메일발송현황 헤더 누락: {missing} (헤더 행 {HEADER_ROW})")
    return cols


def _ym(val):
    """날짜값 → 'YYYY-MM' 문자열, 파싱 불가 시 None"""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m")
    # 동기화로 "2026-07-01  12:00:00 AM"처럼 시간/AM-PM이 붙은 텍스트가 들어와도
    # 앞의 YYYY-MM-DD만 추출해 월 귀속시킨다 (뒷부분 시간 표기는 무시).
    m = re.match(r"(\d{4})-(\d{2})-\d{2}", str(val).strip())
    return f"{m.group(1)}-{m.group(2)}" if m else None


def empty_result() -> dict:
    return {
        "total_sent": 0, "etc_excluded": 0, "replied": 0, "reply_rate": 0,
        "meeting_total": 0, "meeting_rate": 0, "exp_total_approx": 0, "ad_total": 0,
        "by_month": {},
    }


def _finalize(total_sent, etc_count, replied, meeting, exp_total, ad_total, by_month) -> dict:
    by_month_rates = {}
    for ym, d in sorted(by_month.items()):
        s = d["sent"] or 1
        by_month_rates[ym] = {
            "sent":         d["sent"],
            "replied":      d["replied"],
            "meeting":      d["meeting"],
            "exp":          d["exp"],
            "ad":           d["ad"],
            "reply_rate":   round(d["replied"] / s, 4),
            "meeting_rate": round(d["meeting"] / s, 4),
            "exp_rate":     round(d["exp"] / s, 4),
            "ad_rate":      round(d["ad"] / s, 4),
        }
    return {
        "total_sent":       total_sent,
        "etc_excluded":     etc_count,
        "replied":          replied,
        "reply_rate":       round(replied / total_sent, 4) if total_sent else 0,
        "meeting_total":    meeting,
        "meeting_rate":     round(meeting / total_sent, 4) if total_sent else 0,
        "exp_total_approx": exp_total,
        "ad_total":         ad_total,
        "by_month":         by_month_rates,
    }


def parse_mail_sheet(ws, owner_filter=None) -> dict:
    """메일발송현황 시트 1개 집계.
    owner_filter: None이면 전체 행, 아니면 `구분` 열 값에 적용할 함수(예: is_owner_mark).
    owner_filter가 있는데 `구분` 열이 없으면 경고 후 빈 결과."""
    rows_iter = ws.iter_rows(min_row=HEADER_ROW, values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return empty_result()
    cols = header_columns(header)

    owner_col = cols.get(OWNER_HEADER)
    if owner_filter is not None and owner_col is None:
        print(f"[WARN] '{ws.title}' 시트에 '{OWNER_HEADER}' 열이 없어 담당자 필터를 적용할 수 없습니다 → 0건 처리",
              file=sys.stderr)
        return empty_result()

    c_send, c_reply, c_status = cols[H_SEND], cols[H_REPLY], cols[H_STATUS]
    c_mtg, c_accept, c_ad = cols[H_MTG], cols[H_ACCEPT], cols[H_AD]

    total_sent = etc_count = replied = meeting = exp_total = ad_total = 0
    empty_streak = 0
    by_month: dict = {}   # "YYYY-MM" → {sent, replied, meeting, exp, ad}

    def _bm(ym_key):
        if ym_key not in by_month:
            by_month[ym_key] = {"sent": 0, "replied": 0, "meeting": 0, "exp": 0, "ad": 0}
        return by_month[ym_key]

    for row_vals in rows_iter:
        if all(v is None for v in row_vals):
            empty_streak += 1
            if empty_streak >= 10:
                break
            continue
        empty_streak = 0

        def _get(col):
            return row_vals[col] if col < len(row_vals) else None

        if owner_filter is not None and not owner_filter(_get(owner_col)):
            continue

        send_date   = _get(c_send)
        reply_date  = _get(c_reply)
        status_raw  = _get(c_status)
        mtg_date    = _get(c_mtg)
        accept_date = _get(c_accept)
        ad_date     = _get(c_ad)

        # 월별 집계는 '각 이벤트가 일어난 날짜'의 월로 귀속 (달력 기준).
        #   발송→발송일 / 응답→회신일 / 미팅→미팅일 / 체험→협찬수락일 / 광고→광고수락일

        # 응답: 발송 여부와 무관하게 회신일 있으면 카운트, 월 귀속은 회신일(없으면 발송일)
        if is_date(reply_date):
            replied += 1
            ym_r = _ym(reply_date) or _ym(send_date)
            if ym_r:
                _bm(ym_r)["replied"] += 1

        # 이하 지표는 발송일 있는 행만
        if not is_date(send_date):
            continue

        total_sent += 1
        status = normalize_status(status_raw)
        ym_s = _ym(send_date)
        if ym_s:
            _bm(ym_s)["sent"] += 1

        if is_date(mtg_date):
            meeting += 1
            ym_m = _ym(mtg_date)
            if ym_m:
                _bm(ym_m)["meeting"] += 1

        # 기타(검토/진행불가/우리측거절)는 체험·광고 지표에서만 제외
        if any(k in status for k in ETC_KEYWORDS) or status == "기타":
            etc_count += 1
            continue

        if is_date(accept_date):
            exp_total += 1
            ym_a = _ym(accept_date)
            if ym_a:
                _bm(ym_a)["exp"] += 1

        if is_date(ad_date):
            ad_total += 1
            ym_d = _ym(ad_date)
            if ym_d:
                _bm(ym_d)["ad"] += 1

    return _finalize(total_sent, etc_count, replied, meeting, exp_total, ad_total, by_month)


def parse_mail_workbook(path, owner_filter=None) -> dict:
    """파일 1개 → parse_mail_sheet 결과. 시트 없으면 ValueError."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = find_mail_sheet(wb)
        if ws is None:
            raise ValueError(f"'{SHEET_PREFIX}*' 시트 없음. 시트 목록: {wb.sheetnames}")
        return parse_mail_sheet(ws, owner_filter=owner_filter)
    finally:
        wb.close()


def merge_mail_results(results) -> dict:
    """여러 파일 결과 합산 (비율 재계산)."""
    total_sent = etc = replied = meeting = exp = ad = 0
    by_month: dict = {}
    for r in results:
        total_sent += r.get("total_sent", 0)
        etc        += r.get("etc_excluded", 0)
        replied    += r.get("replied", 0)
        meeting    += r.get("meeting_total", 0)
        exp        += r.get("exp_total_approx", 0)
        ad         += r.get("ad_total", 0)
        for ym, d in r.get("by_month", {}).items():
            b = by_month.setdefault(ym, {"sent": 0, "replied": 0, "meeting": 0, "exp": 0, "ad": 0})
            for k in b:
                b[k] += d.get(k, 0)
    return _finalize(total_sent, etc, replied, meeting, exp, ad, by_month)


def main():
    excel_path = find_shared_xlsx("유튜브")
    if excel_path is None:
        print(f"[ERROR] 공유 스프레드시트를 찾을 수 없습니다: {_SHARED_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] 메일발송현황 소스(공유 스프레드시트): {excel_path.name}", file=sys.stderr)

    try:
        result = parse_mail_workbook(excel_path)
    except Exception as e:
        print(f"[ERROR] 메일발송현황 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[INFO] 메일발송현황 파싱 완료 — 총발송 {result['total_sent']}건(기타포함), 기타 {result['etc_excluded']}건",
          file=sys.stderr)


if __name__ == "__main__":
    main()
