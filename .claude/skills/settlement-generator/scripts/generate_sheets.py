#!/usr/bin/env python3
# generate_sheets.py — STEP 5: 정산서 생성 (구간 단가 + VAT)
# 사용법: python generate_sheets.py <bucket_json> <settlement_month(YYYY-MM)>
# bucket_json: parse_order.py stdout JSON
# 출력: output/정산DB_업데이트.xlsx 갱신 + stdout JSON (정산 요약)
import sys
import json
import re
from pathlib import Path
from datetime import datetime, date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR     = Path(r"C:\Users\user\비서")
OUTPUT_DIR   = BASE_DIR / "output"
RAWDATA_PATH = BASE_DIR / "스케줄" / "정산DB_업데이트.xlsx"
CONFIG_PATH  = BASE_DIR / ".claude" / "skills" / "settlement-generator" / "scripts" / "ytber_config.json"
SKIP_LOG     = OUTPUT_DIR / "settlement_skipped.log"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_unit_price(cumulative_qty: int, tier_pricing: list) -> int:
    price = tier_pricing[0]["unit_price"]
    for tier in tier_pricing:
        if cumulative_qty >= tier["min_qty"]:
            price = tier["unit_price"]
    return price


def get_cumulative_qty(rawdata_ws, ytber_name: str) -> int:
    total = 0
    for row in rawdata_ws.iter_rows(min_row=2, values_only=True):
        if row and str(row[2]).strip() == ytber_name and str(row[8]).strip() == "settlement":
            try:
                total += int(row[4]) if row[4] else 0
            except (ValueError, TypeError):
                pass
    return total


def style_header(ws, row, col_count):
    fill = PatternFill("solid", fgColor="1F3864")
    font = Font(bold=True, color="FFFFFF", size=10)
    align = Alignment(horizontal="center", vertical="center")
    for c in range(1, col_count + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = fill
        cell.font = font
        cell.alignment = align


def style_money(ws, row, col):
    ws.cell(row=row, column=col).number_format = '#,##0'


def create_settlement_sheet(wb, ytber_name: str, orders: list, cumulative_qty_before: int,
                             tier_pricing: list, vat_rate: float, month_label: str,
                             general_label: str) -> dict:
    sheet_name = f"{ytber_name} {month_label}"[:31]
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(sheet_name)

    is_general = (ytber_name == general_label)

    # 기본정보 섹션
    ws.append(["정산서"])
    ws.merge_cells("A1:F1")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.append(["인플루언서명", ytber_name if not is_general else "기타/일반 판매",
               "정산월", month_label, "", ""])
    ws.append([""])

    current_unit_price = None
    current_cumulative = cumulative_qty_before

    if not is_general:
        current_unit_price = get_unit_price(current_cumulative, tier_pricing)
        ws.append(["누적수량(이전)", cumulative_qty_before, "현재단가", f"₩{current_unit_price:,}", "", ""])

    ws.append([""])

    # 주문 상세 테이블 헤더
    header_row = ws.max_row + 1
    headers = ["주문번호", "주문일", "상품명", "수량", "주문금액", "정산단가", "정산금액"]
    ws.append(headers)
    style_header(ws, header_row, len(headers))

    # 주문 행
    total_qty = 0
    total_settlement = 0
    total_order_amount = 0

    for order in orders:
        qty = order.get("qty", 0)
        amount = order.get("amount", 0)

        if is_general:
            unit_p = None
            settlement_amt = None
        else:
            # 누적 수량 업데이트 후 단가 결정
            current_cumulative += qty
            unit_p = get_unit_price(current_cumulative, tier_pricing)
            settlement_amt = qty * unit_p

        row_data = [
            order.get("order_no", ""),
            order.get("order_date", ""),
            order.get("product_name", "")[:50],
            qty,
            amount,
            f"₩{unit_p:,}" if unit_p else "-",
            settlement_amt if settlement_amt is not None else "-",
        ]
        ws.append(row_data)

        r = ws.max_row
        style_money(ws, r, 5)
        if not is_general and settlement_amt:
            style_money(ws, r, 7)

        total_qty += qty
        total_order_amount += amount
        if settlement_amt:
            total_settlement += settlement_amt

    ws.append([""])

    # 합계 섹션
    sum_row = ws.max_row + 1
    if is_general:
        ws.append(["합계", "", "", total_qty, total_order_amount, "", "해당없음"])
    else:
        ws.append(["합계", "", "", total_qty, total_order_amount, "", total_settlement])
        style_money(ws, sum_row, 7)
    style_money(ws, sum_row, 5)

    ws.cell(row=sum_row, column=1).font = Font(bold=True)
    ws.cell(row=sum_row, column=7).font = Font(bold=True)

    ws.append([""])

    # VAT 섹션
    if not is_general and total_settlement:
        vat_excluded = int(total_settlement / (1 + vat_rate))
        ws.append(["공급가액(VAT포함)", total_settlement, "VAT 10% 제외 금액", vat_excluded, "", ""])
        r = ws.max_row
        style_money(ws, r, 2)
        style_money(ws, r, 4)
        ws.cell(row=r, column=3).font = Font(color="FF0000", italic=True)

    # 컬럼 너비 조정
    col_widths = [18, 12, 40, 6, 14, 12, 14]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    return {
        "ytber": ytber_name,
        "order_count": len(orders),
        "qty": total_qty,
        "cumulative_qty": current_cumulative if not is_general else None,
        "unit_price": current_unit_price if not is_general else None,
        "settlement_amount": total_settlement if not is_general else None,
        "is_general": is_general,
    }


def main():
    if len(sys.argv) < 3:
        print("사용법: python generate_sheets.py <bucket_json_path_or_-> <YYYY-MM>", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "-":
        bucket_data = json.load(sys.stdin)
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            bucket_data = json.load(f)

    settlement_month = sys.argv[2]  # "YYYY-MM"
    month_parts = settlement_month.split("-")
    month_label = f"{month_parts[1]}월" if len(month_parts) == 2 else settlement_month

    config      = load_config()
    tier_pricing = config["tier_pricing"]
    vat_rate    = config.get("vat_rate", 0.10)
    general_label = config.get("general_sales_label", "기타/일반")

    # Raw_Data 파일 로드 (누적 수량 계산용)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if RAWDATA_PATH.exists():
        wb = openpyxl.load_workbook(RAWDATA_PATH)
    else:
        wb = openpyxl.Workbook()

    if "Raw_Data" not in wb.sheetnames:
        wb.create_sheet("Raw_Data")
    rawdata_ws = wb["Raw_Data"]

    # 정산 대상별 그룹핑
    settlement_orders = bucket_data.get("settlement", [])
    general_orders    = bucket_data.get("general", [])

    # 인플루언서별 그룹핑
    ytber_groups: dict[str, list] = {}
    for order in settlement_orders:
        ytber = order.get("ytber", "")
        ytber_groups.setdefault(ytber, []).append(order)

    summaries = []

    # 정산 대상 시트 생성
    for ytber, orders in ytber_groups.items():
        # 현재 주문 처리 전 누적 수량 (Raw_Data에서 기존 수량 조회)
        cumulative_before = get_cumulative_qty(rawdata_ws, ytber)
        summary = create_settlement_sheet(
            wb, ytber, orders, cumulative_before,
            tier_pricing, vat_rate, month_label, general_label
        )
        summaries.append(summary)
        print(f"[INFO] 정산 시트 생성: {ytber} ({len(orders)}건)", file=sys.stderr)

    # 기타/일반 시트 생성
    if general_orders:
        summary = create_settlement_sheet(
            wb, general_label, general_orders, 0,
            tier_pricing, vat_rate, month_label, general_label
        )
        summaries.append(summary)
        print(f"[INFO] 기타/일반 시트 생성 ({len(general_orders)}건)", file=sys.stderr)

    wb.save(RAWDATA_PATH)
    wb.close()

    result = {
        "settlement_month": settlement_month,
        "sheet_count": len(summaries),
        "summaries": summaries,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
