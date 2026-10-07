#!/usr/bin/env python3
# yk_excel_setup.py — 영끌러님 대시보드용 엑셀 1회성 변경 (Excel COM, 재실행 안전)
#
#   1) 뷰티·유튜브 공유 파일의 `메일발송현황*` 시트 6행 헤더 맨 앞에 `구분` 열 삽입 (A6:A<마지막행> 셀 삽입, 오른쪽 이동)
#      - 이미 A6가 `구분`이면 건너뜀.  기존 A열(분류) 값은 B열로 밀려 보존된다.
#      - 1~5행 미니 대시보드는 건드리지 않는다.
#   2) 뷰티 파일을 복사해 `1. 슬립이지 인플루언서 관리_공유_YYMMDD.xlsx` 생성
#      - 시트명 접미사 제거, 7행 이하 데이터 비움(헤더·수식·구분 열 유지). 이미 있으면 건너뜀.
#   실행 전 각 파일을 `<이름>_백업_YYMMDD.xlsx`로 복사한다 (있으면 건너뜀).
#
# 사용법: PYTHONUTF8=1 python yk_excel_setup.py [--dry-run]
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_mail import _SHARED_DIR, SHEET_PREFIX, OWNER_HEADER, HEADER_ROW, DATA_START_ROW, _norm, find_shared_xlsx  # noqa: E402

XL_TO_RIGHT = -4161
XL_FORMAT_FROM_RIGHT_OR_BELOW = 1
XL_OPENXML_WORKBOOK = 51

SLEEP_KIND = "슬립이지"
SLEEP_SHEET_NAMES = ["메일 변환", "메일발송현황", "인플루언서관리", "메일 답장 메뉴얼"]
TODAY_YYMMDD = datetime.now().strftime("%y%m%d")


def log(msg):
    print(msg, file=sys.stderr)


def backup(path: Path) -> Path:
    dst = path.with_name(f"{path.stem}_백업_{TODAY_YYMMDD}{path.suffix}")
    if dst.exists():
        log(f"[SKIP] 백업 이미 있음: {dst.name}")
    else:
        shutil.copy2(path, dst)
        log(f"[OK] 백업: {dst.name}")
    return dst


def get_excel():
    import win32com.client
    try:
        app = win32com.client.GetActiveObject("Excel.Application")
        return app, False
    except Exception:
        app = win32com.client.DispatchEx("Excel.Application")
        app.Visible = False
        return app, True


def open_workbook(app, path: Path):
    """이미 열려 있으면 그 워크북, 아니면 열기. 읽기 전용이면 RuntimeError."""
    target = str(path).lower()
    for wb in app.Workbooks:
        if str(wb.FullName).lower() == target:
            log(f"[INFO] 열린 워크북 재사용: {wb.Name}")
            if wb.ReadOnly:
                raise RuntimeError(f"읽기 전용으로 열려 있음: {wb.Name} — 편집 가능 상태로 다시 연 뒤 재실행")
            return wb, False
    wb = app.Workbooks.Open(str(path), UpdateLinks=0, ReadOnly=False)
    if wb.ReadOnly:
        wb.Close(SaveChanges=False)
        raise RuntimeError(f"읽기 전용으로만 열림(다른 곳에서 사용 중?): {path.name}")
    return wb, True


def find_mail_ws(wb):
    for ws in wb.Worksheets:
        if str(ws.Name).startswith(SHEET_PREFIX):
            return ws
    return None


def last_used_row(ws) -> int:
    ur = ws.UsedRange
    return max(int(ur.Row + ur.Rows.Count - 1), DATA_START_ROW)


def insert_owner_column(ws, dry_run=False) -> bool:
    """A6가 `구분`이 아니면 A6:A<last>에 셀 삽입 후 A6=`구분`. 변경했으면 True."""
    a6 = ws.Cells(HEADER_ROW, 1).Value
    if _norm(a6) == OWNER_HEADER:
        log(f"[SKIP] '{ws.Name}' A{HEADER_ROW}는 이미 '{OWNER_HEADER}'")
        return False
    last = last_used_row(ws)
    log(f"[INFO] '{ws.Name}' A{HEADER_ROW}='{a6}' → A{HEADER_ROW}:A{last} 셀 삽입(오른쪽 이동)")
    if dry_run:
        return False
    # 표(ListObject)가 걸려 있으면 셀 삽입이 거부되므로 표 열 추가로 처리
    if ws.ListObjects.Count > 0:
        for lo in ws.ListObjects:
            if lo.Range.Row <= HEADER_ROW <= lo.Range.Row + lo.Range.Rows.Count - 1:
                col = lo.ListColumns.Add(1)
                col.Name = OWNER_HEADER
                log(f"[OK] 표 '{lo.Name}' 첫 열에 '{OWNER_HEADER}' 추가")
                return True
    ws.Range(f"A{HEADER_ROW}:A{last}").Insert(Shift=XL_TO_RIGHT, CopyOrigin=XL_FORMAT_FROM_RIGHT_OR_BELOW)
    ws.Cells(HEADER_ROW, 1).Value = OWNER_HEADER
    try:
        ws.Columns(1).ColumnWidth = 6
    except Exception:
        pass
    log(f"[OK] '{ws.Name}' '{OWNER_HEADER}' 열 삽입 완료")
    return True


def process_shared_file(app, kind: str, dry_run=False) -> Path | None:
    path = find_shared_xlsx(kind)
    if path is None:
        log(f"[WARN] {kind} 공유 파일 없음 → 건너뜀")
        return None
    log(f"==== {kind}: {path.name}")
    backup(path)
    wb, opened_here = open_workbook(app, path)
    try:
        ws = find_mail_ws(wb)
        if ws is None:
            raise RuntimeError(f"'{SHEET_PREFIX}*' 시트 없음: {[w.Name for w in wb.Worksheets]}")
        changed = insert_owner_column(ws, dry_run=dry_run)
        if changed:
            wb.Save()
            log(f"[OK] 저장: {path.name}")
    finally:
        if opened_here:
            wb.Close(SaveChanges=False)
    return path


def create_sleep_file(app, beauty_path: Path, dry_run=False):
    existing = find_shared_xlsx(SLEEP_KIND)
    if existing is not None:
        log(f"[SKIP] 슬립이지 파일 이미 있음: {existing.name}")
        return existing
    dst = beauty_path.with_name(f"1. {SLEEP_KIND} 인플루언서 관리_공유_{TODAY_YYMMDD}.xlsx")
    log(f"==== 슬립이지 파일 생성: {dst.name} (뷰티 복사)")
    if dry_run:
        return None
    shutil.copy2(beauty_path, dst)
    wb = app.Workbooks.Open(str(dst), UpdateLinks=0, ReadOnly=False)
    try:
        # 시트명 접미사 제거
        for ws in wb.Worksheets:
            for base in SLEEP_SHEET_NAMES:
                if str(ws.Name).startswith(base) and ws.Name != base:
                    ws.Name = base
                    break
        names = [w.Name for w in wb.Worksheets]
        log(f"[OK] 시트명: {names}")

        # 메일발송현황: 7행 이하 데이터 비움 (헤더·구분 열·서식 유지)
        ws = wb.Worksheets("메일발송현황")
        last = last_used_row(ws)
        lastcol = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1
        if last >= DATA_START_ROW:
            rng = ws.Range(ws.Cells(DATA_START_ROW, 1), ws.Cells(last, lastcol))
            rng.Hyperlinks.Delete()
            rng.ClearContents()
        ws.Cells(HEADER_ROW, 1).Value = OWNER_HEADER
        log(f"[OK] 메일발송현황 {DATA_START_ROW}~{last}행 비움")

        # 메일 변환: B7:E<last> 비움 (F/G 수식 유지)
        ws = wb.Worksheets("메일 변환")
        last = last_used_row(ws)
        if last >= 7:
            rng = ws.Range(f"B7:E{last}")
            rng.Hyperlinks.Delete()
            rng.ClearContents()
        log(f"[OK] 메일 변환 B7:E{last} 비움")

        # 인플루언서관리: 10행 이하, B열 이후 비움 (A열 라벨 유지)
        ws = wb.Worksheets("인플루언서관리")
        last = last_used_row(ws)
        lastcol = max(ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1, 2)
        if last >= 10:
            rng = ws.Range(ws.Cells(10, 2), ws.Cells(last, lastcol))
            rng.Hyperlinks.Delete()
            rng.ClearContents()
        log(f"[OK] 인플루언서관리 10~{last}행 B열 이후 비움")

        wb.Worksheets("메일발송현황").Activate()
        wb.Save()
        log(f"[OK] 저장: {dst.name}")
    finally:
        wb.Close(SaveChanges=False)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import pythoncom
    pythoncom.CoInitialize()
    app, started_here = get_excel()
    prev_alerts = app.DisplayAlerts
    app.DisplayAlerts = False
    try:
        beauty = process_shared_file(app, "뷰티", dry_run=args.dry_run)
        process_shared_file(app, "유튜브", dry_run=args.dry_run)
        if beauty is not None:
            create_sleep_file(app, beauty, dry_run=args.dry_run)
        else:
            log("[WARN] 뷰티 파일이 없어 슬립이지 파일을 만들지 않음")
    finally:
        app.DisplayAlerts = prev_alerts
        if started_here:
            app.Quit()
    log("[DONE] yk_excel_setup 완료")


if __name__ == "__main__":
    main()
