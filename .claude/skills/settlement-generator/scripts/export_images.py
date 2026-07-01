#!/usr/bin/env python3
# export_images.py — 정산서 Excel 시트 → PNG 이미지 변환
# 사용법: python export_images.py <excel_path> [output_dir]
import sys
import os
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import fitz  # PyMuPDF
import win32com.client
import pythoncom


def export_sheets_to_images(excel_path: Path, output_dir: Path, month_filter: str = None):
    output_dir.mkdir(parents=True, exist_ok=True)
    pythoncom.CoInitialize()

    excel = win32com.client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False

    try:
        wb = excel.Workbooks.Open(str(excel_path.resolve()))

        results = []
        for ws in wb.Worksheets:
            sheet_name = ws.Name
            # Raw_Data, 기타일반 시트는 건너뜀
            if "Raw_Data" in sheet_name or "기타" in sheet_name:
                continue
            # 월 필터 적용 (예: "5월"만 내보내기)
            if month_filter and not sheet_name.endswith(month_filter):
                continue

            # 시트 단독 선택 후 PDF 임시 저장
            ws.Select()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp_pdf = tmp.name

            wb.ActiveSheet.ExportAsFixedFormat(
                Type=0,          # xlTypePDF
                Filename=tmp_pdf,
                Quality=0,       # xlQualityStandard
                IncludeDocProperties=False,
                IgnorePrintAreas=False,
                OpenAfterPublish=False,
            )

            # PDF → PNG (300 DPI)
            doc = fitz.open(tmp_pdf)
            safe_name = sheet_name.replace("/", "_").replace("\\", "_")
            out_path = output_dir / f"{safe_name}.png"

            page = doc[0]
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pix.save(str(out_path))
            doc.close()
            os.unlink(tmp_pdf)

            results.append({"sheet": sheet_name, "image": str(out_path)})
            print(f"[INFO] 저장: {out_path.name}", file=sys.stderr)

        wb.Close(SaveChanges=False)
        return results

    finally:
        excel.Quit()
        pythoncom.CoUninitialize()


def main():
    if len(sys.argv) < 2:
        excel_path = Path(r"C:\Users\user\비서\스케줄") / next(
            Path(r"C:\Users\user\비서\스케줄").glob("유튜버별 월정산시트 작성 2026-05_송부용.xlsx")
        ).name
    else:
        excel_path = Path(sys.argv[1])

    # YYYY-MM → "N월" 형태로 월 필터 계산
    stem = excel_path.stem  # 예: "유튜버별 월정산시트 작성 2026-05_송부용"
    import re
    m = re.search(r"(\d{4})-(\d{2})", stem)
    month_filter = f"{int(m.group(2))}월" if m else None

    # 기본 출력 경로: output\N월 정산\  (인자로 지정 시 그 경로 우선)
    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
    elif month_filter:
        output_dir = Path(r"C:\Users\user\비서\output") / f"{month_filter} 정산"
    else:
        output_dir = Path(r"C:\Users\user\비서\output\settlement_images") / excel_path.stem

    print(f"[INFO] 원본: {excel_path}", file=sys.stderr)
    print(f"[INFO] 출력: {output_dir}", file=sys.stderr)

    if not excel_path.exists():
        print(f"[ERROR] 파일 없음: {excel_path}", file=sys.stderr)
        sys.exit(1)

    results = export_sheets_to_images(excel_path, output_dir, month_filter)

    import json
    print(json.dumps({"count": len(results), "images": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
