#!/usr/bin/env python3
# generate_sheets.py — STEP 5: 정산서 생성 (송부용 - 템플릿 복사 방식)
# 사용법: python generate_sheets.py <bucket_json_path> <YYYY-MM>
# 출력: 유튜버별 월정산시트 작성 YYYY-MM_송부용.xlsx 생성 + stdout JSON (정산 요약)
import sys
import json
import shutil
import re
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import openpyxl

BASE_DIR      = Path(r"C:\Users\user\비서")
RAWDATA_PATH  = BASE_DIR / "스케줄" / "정산DB_업데이트.xlsx"
CONFIG_PATH   = BASE_DIR / ".claude" / "skills" / "settlement-generator" / "scripts" / "ytber_config.json"
TEMPLATE_PATH = BASE_DIR / "스케줄" / "유튜버별 월정산시트 작성 4월분_송부용.xlsx"

# 정산DB Raw_Data 컬럼 인덱스 (0-based)
RAW_COL_DATE   = 2   # 주문일시
RAW_COL_STATUS = 3   # 주문상태
RAW_COL_YTBER  = 5   # 유튜버 이름
RAW_COL_CLAIM  = 6   # 클레임상태
RAW_COL_QTY    = 12  # 수량

# 템플릿 시트명 → ytber명 매핑 (처리 순서 포함)
TEMPLATE_SHEET_MAP = [
    ("마성민 4월",       "마성민"),
    ("나이스부부 4월",   "나이스부부"),
    ("C맹씨 4월",        "C맹씨"),
    ("The조치패밀리 4월", "The 조치 패밀리"),
    ("기타일반 4월",     "기타/일반"),
]

# 삭제할 구형 시트 (이전 월 히스토리 등)
OLD_SHEETS = ["Raw_Data3월", "마성민 3월", "나이스부부 3월", "유튜버별 정산 시트 만들기"]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_tier_price(cumulative_qty: int, tier_pricing: list) -> int:
    price = tier_pricing[0]["unit_price"]
    for tier in tier_pricing:
        if cumulative_qty >= tier["min_qty"]:
            price = tier["unit_price"]
    return price


def get_month_orders(rawdata_ws, target_month: str) -> list:
    """정산DB Raw_Data에서 해당 월 주문 전체(취소 포함) 추출"""
    orders = []
    for row in rawdata_ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        order_date_str = str(row[RAW_COL_DATE] or "")
        if not order_date_str.startswith(target_month):
            continue
        status = str(row[RAW_COL_STATUS] or "")
        claim  = str(row[RAW_COL_CLAIM]  or "")
        orders.append({
            "order_no":     str(row[0]  or ""),
            "order_no2":    str(row[1]  or ""),
            "order_date":   order_date_str,
            "order_status": status,
            "delivery":     str(row[4]  or ""),
            "ytber":        str(row[RAW_COL_YTBER] or ""),
            "claim_status": claim,
            "claim_qty":    str(row[7]  or ""),
            "product_id":   str(row[8]  or ""),
            "product_name": str(row[9]  or ""),
            "option1":      str(row[10] or ""),
            "option2":      str(row[11] or ""),
            "qty":          int(row[RAW_COL_QTY]) if row[RAW_COL_QTY] else 0,
            "buyer_name":   str(row[13] or ""),
            "buyer_id":     str(row[14] or ""),
            "is_cancelled": ("취소" in status or "취소완료" in claim),
        })
    return orders


def get_cumulative_qty_before(rawdata_ws, ytber_name: str, target_month: str) -> int:
    """해당 월 이전까지의 해당 ytber 비취소 누적 수량"""
    total = 0
    for row in rawdata_ws.iter_rows(min_row=2, values_only=True):
        if not row or row[RAW_COL_YTBER] is None:
            continue
        if str(row[RAW_COL_YTBER]).strip() != ytber_name:
            continue
        if str(row[RAW_COL_DATE] or "").startswith(target_month):
            continue
        status = str(row[RAW_COL_STATUS] or "")
        claim  = str(row[RAW_COL_CLAIM]  or "")
        if "취소" in status or "취소완료" in claim:
            continue
        try:
            total += int(row[RAW_COL_QTY]) if row[RAW_COL_QTY] else 0
        except (ValueError, TypeError):
            pass
    return total


def main():
    if len(sys.argv) < 3:
        print("사용법: python generate_sheets.py <bucket_json_path> <YYYY-MM>", file=sys.stderr)
        sys.exit(1)

    bucket_path      = sys.argv[1]
    settlement_month = sys.argv[2]  # "YYYY-MM"

    if bucket_path == "-":
        bucket_data = json.load(sys.stdin)
    else:
        with open(bucket_path, encoding="utf-8-sig") as f:
            bucket_data = json.load(f)

    year, month   = int(settlement_month[:4]), int(settlement_month[5:7])
    config        = load_config()
    tier_pricing  = config["tier_pricing"]
    general_label = config.get("general_sales_label", "기타/일반")
    ytber_info_map = config.get("ytber_info", {})

    # 정산DB 로드 (현월 주문 추출 + 누적 수량 계산)
    if not RAWDATA_PATH.exists():
        print(f"[ERROR] 정산DB 없음: {RAWDATA_PATH}", file=sys.stderr)
        sys.exit(1)

    rawdata_wb = openpyxl.load_workbook(RAWDATA_PATH, data_only=True, read_only=True)
    if "Raw_Data" not in rawdata_wb.sheetnames:
        print("[ERROR] 정산DB에 Raw_Data 시트 없음", file=sys.stderr)
        rawdata_wb.close()
        sys.exit(1)
    rawdata_ws = rawdata_wb["Raw_Data"]

    month_orders = get_month_orders(rawdata_ws, settlement_month)
    print(f"[INFO] {settlement_month} 주문 {len(month_orders)}건 (취소 포함)", file=sys.stderr)

    # ytber별 정상/취소 분류
    ytber_ok  = {}   # ytber → 비취소 주문 리스트
    ytber_can = {}   # ytber → 취소 주문 리스트
    for o in month_orders:
        ytber = o["ytber"]
        if o["is_cancelled"]:
            ytber_can.setdefault(ytber, []).append(o)
        else:
            ytber_ok.setdefault(ytber, []).append(o)

    # 템플릿 복사
    output_name = f"유튜버별 월정산시트 작성 {settlement_month}_송부용.xlsx"
    output_path = BASE_DIR / "스케줄" / output_name
    shutil.copy(TEMPLATE_PATH, output_path)
    print(f"[INFO] 템플릿 복사: {output_path.name}", file=sys.stderr)

    # 출력 파일 열기 (수식 보존)
    wb = openpyxl.load_workbook(output_path)

    # ── Raw_Data 갱신 ──────────────────────────────────────────────────────
    ws_raw = wb["Raw_Data"]
    if ws_raw.max_row > 1:
        ws_raw.delete_rows(2, ws_raw.max_row - 1)
    for o in month_orders:
        ws_raw.append([
            o["order_no"], o["order_no2"], o["order_date"],
            o["order_status"], o["delivery"],
            o["ytber"],          # F열: 직접 ytber명 (수식 대신 값 기입)
            o["claim_status"], o["claim_qty"],
            o["product_id"], o["product_name"],
            o["option1"], o["option2"],
            o["qty"], o["buyer_name"], o["buyer_id"],
        ])

    # ── 정산 시트별 처리 ───────────────────────────────────────────────────
    summaries = []

    for tmpl_sheet, ytber_name in TEMPLATE_SHEET_MAP:
        if tmpl_sheet not in wb.sheetnames:
            print(f"[WARN] 템플릿 시트 없음: {tmpl_sheet}", file=sys.stderr)
            continue

        ws = wb[tmpl_sheet]
        is_general = (ytber_name == general_label)
        ytber_info = ytber_info_map.get(ytber_name, {})

        # 기준 월 업데이트
        if is_general:
            ws["C17"] = month   # 기타일반 시트는 C17 참조
        else:
            ws["I4"] = month    # 일반 인플루언서 시트는 I4 참조

        # 개인 판매 링크 (모든 시트)
        link = ytber_info.get("smartstore_link", "")
        if link:
            ws["C6"] = link

        # 계좌 정보 (비기타 인플루언서만)
        if not is_general:
            acct_name = ytber_info.get("account_name", "")
            acct_bank = ytber_info.get("account_bank", "")
            acct_no   = ytber_info.get("account_no", "")
            if acct_name and acct_bank and acct_no:
                ws["C9"] = f"{acct_name}\n{acct_bank} {acct_no}"

        # 정산 단가 업데이트 (기타일반 제외)
        cum_before = 0
        unit_price = None
        if not is_general:
            cum_before = get_cumulative_qty_before(rawdata_ws, ytber_name, settlement_month)
            ok_list    = ytber_ok.get(ytber_name, [])
            month_qty  = sum(o["qty"] for o in ok_list)
            total_cum  = cum_before + month_qty
            unit_price = get_tier_price(total_cum, tier_pricing)
            ws["C14"] = unit_price

        # 시트명 변경 (템플릿 4월 → 현재 월)
        safe_name  = re.sub(r'[\\/*?:\[\]/]', '', ytber_name)
        ws.title   = f"{safe_name} {month}월"[:31]

        # 집계 (summaries용)
        ok_list   = ytber_ok.get(ytber_name, [])
        can_list  = ytber_can.get(ytber_name, [])
        final_qty = sum(o["qty"] for o in ok_list)
        cum_total = (cum_before + final_qty) if not is_general else None
        amount    = (final_qty * unit_price) if (not is_general and unit_price is not None) else None

        summaries.append({
            "ytber":             ytber_name,
            "order_count":       len(ok_list),
            "qty":               final_qty,
            "cumulative_qty":    cum_total,
            "unit_price":        unit_price,
            "settlement_amount": amount,
            "is_general":        is_general,
        })
        print(
            f"[INFO] 정산 시트: {ytber_name} → {ws.title} "
            f"(정상 {len(ok_list)}건/{final_qty}개, 취소 {len(can_list)}건)",
            file=sys.stderr,
        )

    # ── 구형 시트 삭제 ─────────────────────────────────────────────────────
    for old in OLD_SHEETS:
        if old in wb.sheetnames:
            del wb[old]
            print(f"[INFO] 구형 시트 삭제: {old}", file=sys.stderr)

    rawdata_wb.close()

    wb.calculation.calcMode = "auto"
    wb.save(output_path)
    wb.close()
    print(f"[INFO] 저장 완료: {output_path}", file=sys.stderr)

    result = {
        "settlement_month": settlement_month,
        "output_path":      str(output_path),
        "sheet_count":      len(summaries),
        "summaries":        summaries,
        "unregistered":     bucket_data.get("unregistered", []),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
