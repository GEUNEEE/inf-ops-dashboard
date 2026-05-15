#!/usr/bin/env python3
# generate_sheets.py — STEP 5: 정산서 생성 (양식 포맷)
# 사용법: python generate_sheets.py <bucket_json_path> <YYYY-MM>
# 출력: 정산DB_업데이트.xlsx 갱신 + stdout JSON (정산 요약)
import sys
import json
import re
import calendar
from typing import Optional
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
RAWDATA_PATH = BASE_DIR / "스케줄" / "정산DB_업데이트.xlsx"
CONFIG_PATH  = BASE_DIR / ".claude" / "skills" / "settlement-generator" / "scripts" / "ytber_config.json"

# Raw_Data 컬럼 인덱스 (0-based, 양식 포맷)
RAW_COL_YTBER  = 5   # 유튜버 이름
RAW_COL_STATUS = 3   # 주문상태
RAW_COL_CLAIM  = 6   # 클레임상태
RAW_COL_QTY    = 12  # 수량


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_tier_price(cumulative_qty: int, tier_pricing: list) -> int:
    price = tier_pricing[0]["unit_price"]
    for tier in tier_pricing:
        if cumulative_qty >= tier["min_qty"]:
            price = tier["unit_price"]
    return price


def get_cumulative_qty(rawdata_ws, ytber_name: str) -> int:
    """Raw_Data에서 해당 유튜버의 비취소 누적 수량 합산"""
    total = 0
    for row in rawdata_ws.iter_rows(min_row=2, values_only=True):
        if not row or row[RAW_COL_YTBER] is None:
            continue
        if str(row[RAW_COL_YTBER]).strip() != ytber_name:
            continue
        order_status = str(row[RAW_COL_STATUS] or "")
        claim_status = str(row[RAW_COL_CLAIM] or "")
        if "취소" in order_status or "취소완료" in claim_status:
            continue
        try:
            total += int(row[RAW_COL_QTY]) if row[RAW_COL_QTY] else 0
        except (ValueError, TypeError):
            pass
    return total


def month_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day}"


def set_cell(ws, row, col, value, bold=False, size=None, color=None, align=None, number_fmt=None):
    cell = ws.cell(row=row, column=col, value=value)
    font_kwargs = {"bold": bold}
    if size:
        font_kwargs["size"] = size
    if color:
        font_kwargs["color"] = color
    cell.font = Font(**font_kwargs)
    if align:
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    if number_fmt:
        cell.number_format = number_fmt
    return cell


def write_settlement_sheet(wb, ytber_name: str, orders: list, cancelled: list,
                            cumulative_before: int, tier_pricing: list,
                            vat_rate: float, year: int, month: int,
                            config: dict) -> dict:
    """양식 포맷으로 정산 시트 생성"""
    safe_name = re.sub(r'[\\/*?:\[\]]', '', ytber_name)
    sheet_name = f"{safe_name} {month}월"[:31]
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(sheet_name)

    is_general = (ytber_name == config.get("general_sales_label", "기타/일반"))
    ytber_info = config.get("ytber_info", {}).get(ytber_name, {})
    product_name = config.get("product_name", "흑장녹삼")
    start_date, end_date = month_range(year, month)
    settlement_date = datetime.now().strftime("%Y-%m-%d")

    # 열 너비 설정 (A~K)
    col_widths = {"A": 2, "B": 14, "C": 28, "D": 22, "E": 14, "F": 7, "G": 10, "H": 2, "I": 14, "J": 10}
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width
    ws.row_dimensions[1].height = 8

    # --- 헤더 섹션 ---
    # row 2: 제목
    title = f"{year}년 {month}월 광고수익 정산 내역서"
    set_cell(ws, 2, 2, title, bold=True, size=13, align="left")
    ws.row_dimensions[2].height = 22

    # row 4: 파트너명 / 기준 월
    set_cell(ws, 4, 2, "파트너명", bold=True)
    set_cell(ws, 4, 3, ytber_name)
    set_cell(ws, 4, 9, "기준 월", bold=True)
    set_cell(ws, 4, 10, month)

    # row 5: 판매 상품
    set_cell(ws, 5, 2, "판매 상품", bold=True)
    set_cell(ws, 5, 3, product_name)

    # row 6: 개인 판매 링크
    link = ytber_info.get("smartstore_link", "")
    set_cell(ws, 6, 2, "개인 판매 링크", bold=True)
    set_cell(ws, 6, 3, link if link else "-")

    # row 7: 정산 기간
    set_cell(ws, 7, 2, "정산 기간", bold=True)
    set_cell(ws, 7, 3, f"{start_date} ~ {end_date}")

    # row 8: 정산 일자
    set_cell(ws, 8, 2, "정산 일자", bold=True)
    set_cell(ws, 8, 3, settlement_date)

    # row 9: 계좌 (비기타 인플루언서만)
    if not is_general:
        acct_name = ytber_info.get("account_name", "")
        acct_bank = ytber_info.get("account_bank", "")
        acct_no   = ytber_info.get("account_no", "")
        acct_str = ""
        if acct_name and acct_bank and acct_no:
            acct_str = f"{acct_name}\n{acct_bank} {acct_no}"
        elif acct_name or acct_no:
            acct_str = f"{acct_name} {acct_bank} {acct_no}".strip()
        set_cell(ws, 9, 2, "계좌", bold=True)
        cell = ws.cell(row=9, column=3, value=acct_str)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[9].height = 30

    # --- 집계 섹션 (row 11-15) ---
    total_cancelled_qty = sum(c.get("qty", 0) for c in cancelled)
    final_qty = sum(o.get("qty", 0) for o in orders)
    total_orders = len(orders) + len(cancelled)
    cancel_count = len(cancelled)

    # 구간 단가 계산 (누적 기준)
    current_cumulative = cumulative_before
    if not is_general:
        for o in orders:
            current_cumulative += o.get("qty", 0)
        unit_price = get_tier_price(current_cumulative, tier_pricing)
        settlement_amount = final_qty * unit_price
    else:
        unit_price = None
        settlement_amount = None

    set_cell(ws, 11, 2, "총 주문 건수", bold=True)
    set_cell(ws, 11, 3, total_orders)

    set_cell(ws, 12, 2, "주문 취소 건수", bold=True)
    set_cell(ws, 12, 3, cancel_count)

    set_cell(ws, 13, 2, "최종 판매 수량", bold=True)
    set_cell(ws, 13, 3, final_qty)

    set_cell(ws, 14, 2, "정산 단가", bold=True)
    set_cell(ws, 14, 3, unit_price if unit_price else "-")
    set_cell(ws, 14, 9, "*2.0 2.2 2.5")

    label_15 = "최종 정산 금액 (세전)" if not is_general else "최종 정산 금액"
    set_cell(ws, 15, 2, label_15, bold=True)
    set_cell(ws, 15, 3, settlement_amount if settlement_amount is not None else "-",
             number_fmt='#,##0' if settlement_amount else None)

    # --- 주문 목록 (row 29+) ---
    # 헤더 (row 29)
    order_headers = ["주문번호", "상품명", "주문일시", "구매자명", "수량", "취소여부"]
    header_fill = PatternFill("solid", fgColor="1F3864")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    for ci, hdr in enumerate(order_headers):
        cell = ws.cell(row=29, column=2 + ci, value=hdr)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[29].height = 18

    # 정상 주문 + 취소 주문 합쳐서 날짜순 정렬
    all_rows = []
    for o in orders:
        all_rows.append({**o, "is_cancelled": False})
    for c in cancelled:
        all_rows.append({**c, "is_cancelled": True})
    all_rows.sort(key=lambda x: str(x.get("order_date", "")))

    sum_qty = 0
    for r_idx, o in enumerate(all_rows):
        r = 30 + r_idx
        order_no2 = o.get("order_no2") or o.get("order_no", "")
        ws.cell(row=r, column=2, value=order_no2)
        ws.cell(row=r, column=3, value=o.get("product_name", "")[:40])
        ws.cell(row=r, column=4, value=o.get("order_date", ""))
        ws.cell(row=r, column=5, value=o.get("buyer_name", ""))
        ws.cell(row=r, column=6, value=o.get("qty", 0))
        ws.cell(row=r, column=7, value="취소" if o["is_cancelled"] else "-")
        if not o["is_cancelled"]:
            sum_qty += o.get("qty", 0)

    # 합계 행
    sum_row = 30 + len(all_rows)
    ws.cell(row=sum_row, column=2, value="합계").font = Font(bold=True)
    ws.cell(row=sum_row, column=6, value=sum_qty).font = Font(bold=True)
    if settlement_amount is not None:
        ws.cell(row=sum_row, column=8, value=settlement_amount).number_format = '#,##0'

    return {
        "ytber":             ytber_name,
        "order_count":       len(orders),
        "qty":               final_qty,
        "cumulative_qty":    current_cumulative if not is_general else None,
        "unit_price":        unit_price,
        "settlement_amount": settlement_amount,
        "is_general":        is_general,
    }


def main():
    if len(sys.argv) < 3:
        print("사용법: python generate_sheets.py <bucket_json_path> <YYYY-MM>", file=sys.stderr)
        sys.exit(1)

    bucket_path = sys.argv[1]
    settlement_month = sys.argv[2]  # "YYYY-MM"

    if bucket_path == "-":
        bucket_data = json.load(sys.stdin)
    else:
        with open(bucket_path, encoding="utf-8-sig") as f:
            bucket_data = json.load(f)

    year, month = int(settlement_month[:4]), int(settlement_month[5:7])

    config       = load_config()
    tier_pricing = config["tier_pricing"]
    vat_rate     = config.get("vat_rate", 0.10)
    general_label = config.get("general_sales_label", "기타/일반")

    # Raw_Data 로드 (누적 수량 조회용)
    if RAWDATA_PATH.exists():
        wb = openpyxl.load_workbook(RAWDATA_PATH)
    else:
        wb = openpyxl.Workbook()

    if "Raw_Data" not in wb.sheetnames:
        ws_raw = wb.create_sheet("Raw_Data")
        ws_raw.append([
            "상품주문번호", "주문번호", "주문일시", "주문상태", "배송속성",
            "유튜버 이름", "클레임상태", "수량클레임 여부", "상품번호", "상품명",
            "옵션정보", "판매옵션정보", "수량", "구매자명", "구매자ID"
        ])
    rawdata_ws = wb["Raw_Data"]

    settlement_orders  = bucket_data.get("settlement", [])
    general_orders     = bucket_data.get("general", [])
    cancelled_by_ytber = bucket_data.get("cancelled_by_ytber", {})

    # 인플루언서별 그룹핑
    ytber_groups: dict[str, list] = {}
    for order in settlement_orders:
        ytber = order.get("ytber", "")
        ytber_groups.setdefault(ytber, []).append(order)

    summaries = []

    for ytber, orders in ytber_groups.items():
        cumulative_before = get_cumulative_qty(rawdata_ws, ytber)
        cancelled = cancelled_by_ytber.get(ytber, [])
        summary = write_settlement_sheet(
            wb, ytber, orders, cancelled,
            cumulative_before, tier_pricing, vat_rate,
            year, month, config
        )
        summaries.append(summary)
        print(f"[INFO] 정산 시트 생성: {ytber} (정상 {len(orders)}건, 취소 {len(cancelled)}건)", file=sys.stderr)

    # 기타/일반 시트
    if general_orders:
        cancelled_general = cancelled_by_ytber.get(general_label, [])
        summary = write_settlement_sheet(
            wb, general_label, general_orders, cancelled_general,
            0, tier_pricing, vat_rate, year, month, config
        )
        summaries.append(summary)
        print(f"[INFO] 기타/일반 시트 생성 ({len(general_orders)}건)", file=sys.stderr)

    wb.save(RAWDATA_PATH)
    wb.close()

    result = {
        "settlement_month": settlement_month,
        "sheet_count":      len(summaries),
        "summaries":        summaries,
        "unregistered":     bucket_data.get("unregistered", []),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
