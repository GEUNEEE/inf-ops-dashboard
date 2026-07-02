#!/usr/bin/env python3
# build_snapshot.py — STEP 7: 월별 스냅샷 저장 (site/data/history/YYYY-MM.json)
# 사용법: python build_snapshot.py <revenue_json> <mail_kpi_json> <inf_json> <settlement_json> <YYYY-MM>
import sys
import json
import re
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR    = Path(r"C:\Users\user\비서")
HISTORY_DIR = BASE_DIR / "site" / "data" / "history"
LOCAL_HIST  = BASE_DIR / "output" / "history"
RAWDATA_PATH = BASE_DIR / "스케줄" / "정산DB_업데이트.xlsx"
CONFIG_PATH  = BASE_DIR / ".claude" / "skills" / "settlement-generator" / "scripts" / "ytber_config.json"

# Raw_Data 컬럼 인덱스 (0-based) — parse_order.py와 동기화
RAW_COL_DATE    = 2
RAW_COL_STATUS  = 3
RAW_COL_YTBER   = 5
RAW_COL_CLAIM   = 6
RAW_COL_OPTION  = 10  # 옵션정보 (세트 크기 판별)
RAW_COL_QTY     = 12
RAW_COL_PRODUCT = 15  # 신규: 제품
RAW_COL_STORE   = 16  # 신규: 스토어
RAW_COL_AMOUNT  = 17  # 신규: 실제 주문금액 (비흑염소 제품 매출)


def parse_set_size(option_info: str) -> int:
    """옵션정보 텍스트에서 세트 크기(개수) 추출.
    '1+1개'→2, '2+2개'→4, '단품 1개'→1, '2박스'→2, 'N개'→N. 미상이면 1."""
    s = option_info or ""
    m = re.search(r"(\d+)\s*\+\s*(\d+)\s*개", s)
    if m:
        return int(m.group(1)) + int(m.group(2))
    m = re.search(r"단품\s*(\d+)\s*개", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*박스", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*개", s)
    if m:
        return int(m.group(1))
    return 1


def compute_product_profit(product: str, units: int, amount: int, set_size: int, profit_cfg: dict) -> int:
    """제품별 수익 모델 적용. 설정 없으면 0(집계예정)."""
    cfg = profit_cfg.get(product)
    if not cfg:
        return 0
    if cfg.get("type") == "per_unit_set":
        table = cfg.get("unit_profit_by_set", {})
        per = table.get(str(set_size))
        if per is None:
            return 0  # 미정의 세트 크기 → 집계예정
        return int(per) * units
    if cfg.get("type") == "margin":
        fee = amount * cfg.get("fee_rate", 0)
        cost = cfg.get("cost_per_unit", 0) * units
        return int(round(amount - fee - cost))
    return 0


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def aggregate_by_product_store(target_month: str, config: dict) -> tuple[dict, dict]:
    """정산DB Raw_Data에서 해당 월 주문을 제품별·(흑염소)스토어별로 집계.
    - by_product[product] = {qty, order_count, gross_revenue}
    - by_store[store]     = {qty, order_count, gross_revenue}  (store_split 제품, 분리 시점 이후만)
    gross_revenue는 기본 제품(흑염소)만 산출 (다른 제품 단가 미정 → 0)."""
    import openpyxl
    by_product: dict = {}
    by_store: dict = {}
    if not RAWDATA_PATH.exists():
        return by_product, by_store

    reg             = config.get("product_registry", {})
    default_product = reg.get("default_product", "흑염소")
    general_label   = config.get("general_sales_label", "기타/일반")
    inf_price       = config.get("product_unit_price", 120000)
    gen_price       = config.get("general_unit_price", 130000)
    products_cfg    = {p["key"]: p for p in config.get("products", [])}
    profit_cfg      = config.get("product_profit", {})

    try:
        wb = openpyxl.load_workbook(RAWDATA_PATH, data_only=True, read_only=True)
        ws = wb["Raw_Data"]
    except Exception as e:
        print(f"[WARN] Raw_Data 집계 실패: {e}", file=sys.stderr)
        return by_product, by_store

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        date_str = str(row[RAW_COL_DATE] or "")
        if not date_str.startswith(target_month):
            continue
        status = str(row[RAW_COL_STATUS] or "")
        claim  = str(row[RAW_COL_CLAIM]  or "")
        if "취소" in status or "취소완료" in claim:
            continue
        ytber = str(row[RAW_COL_YTBER] or "")
        try:
            qty = int(row[RAW_COL_QTY]) if row[RAW_COL_QTY] else 0
        except (ValueError, TypeError):
            qty = 0

        product = (row[RAW_COL_PRODUCT] if len(row) > RAW_COL_PRODUCT and row[RAW_COL_PRODUCT] else default_product)
        store   = (row[RAW_COL_STORE]   if len(row) > RAW_COL_STORE   and row[RAW_COL_STORE]   else None)
        try:
            order_amount = int(row[RAW_COL_AMOUNT]) if len(row) > RAW_COL_AMOUNT and row[RAW_COL_AMOUNT] else 0
        except (ValueError, TypeError):
            order_amount = 0

        is_gen = (ytber == general_label)
        gross  = qty * (gen_price if is_gen else inf_price)

        pd = by_product.setdefault(product, {"qty": 0, "order_count": 0, "gross_revenue": 0, "net_profit": 0})
        pd["order_count"] += 1
        if product == default_product:
            # 흑염소: 수량=개수, 정산 단가 모델(매출은 top-level snapshot에서 관리)
            pd["qty"]           += qty
            pd["gross_revenue"] += gross
        else:
            # 비흑염소: 세트 크기 반영한 실제 개수 + 제품별 수익 모델
            opt       = str(row[RAW_COL_OPTION]) if len(row) > RAW_COL_OPTION and row[RAW_COL_OPTION] else ""
            set_size  = parse_set_size(opt)
            units     = qty * set_size
            pd["qty"]           += units
            pd["gross_revenue"] += order_amount
            pd["net_profit"]    += compute_product_profit(product, units, order_amount, set_size, profit_cfg)

        # 스토어 분리: store_split 제품 + 분리 시점(store_split_from) 이후 + 스토어 식별된 경우만
        pcfg = products_cfg.get(product, {})
        if pcfg.get("store_split") and store and target_month >= pcfg.get("store_split_from", "9999-99"):
            sd = by_store.setdefault(store, {"qty": 0, "order_count": 0, "gross_revenue": 0})
            sd["qty"]           += qty
            sd["order_count"]   += 1
            sd["gross_revenue"] += gross

    wb.close()
    return by_product, by_store


def main():
    if len(sys.argv) < 6:
        print("사용법: python build_snapshot.py <revenue_json> <mail_json> <inf_json> <settlement_json> <YYYY-MM>",
              file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8-sig") as f:
        revenue = json.load(f)
    with open(sys.argv[2], encoding="utf-8-sig") as f:
        mail_kpi = json.load(f)
    with open(sys.argv[3], encoding="utf-8-sig") as f:
        inf_data = json.load(f)
    with open(sys.argv[4], encoding="utf-8-sig") as f:
        settlement = json.load(f)

    target_month = sys.argv[5]  # "YYYY-MM"

    total_sent    = mail_kpi.get("total_sent", 0)
    replied       = mail_kpi.get("replied", 0)
    meeting_total = mail_kpi.get("meeting_total", 0)
    exp_total     = inf_data.get("exp_total", 0)
    ad_total      = inf_data.get("ad_total", 0)

    # 기존 스냅샷 로드 (같은 월 2회차 이상 처리 시 누계 합산)
    site_path  = HISTORY_DIR / f"{target_month}.json"
    prev = {}
    if site_path.exists():
        try:
            prev = json.loads(site_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # per_influencer에서 exp_months 추출
    per_influencer = inf_data.get("per_influencer", {})
    inf_exp_months: dict[str, list[str]] = {}
    for name, info in per_influencer.items():
        if isinstance(info, dict):
            inf_exp_months[name] = [m for m in info.get("exp_months", []) if m]

    # 인플루언서별 집계 — 덮어쓰기 (재실행 시 누산 방지)
    inf_summary = {}
    for s in settlement.get("summaries", []):
        ytber = s.get("ytber", "")
        is_gen = s.get("is_general", False)
        exp_months_this_month = [m for m in inf_exp_months.get(ytber, []) if m == target_month]
        inf_summary[ytber] = {
            "order_count":    s.get("order_count", 0),
            "qty":            s.get("qty", 0),
            "cumulative_qty": s.get("cumulative_qty"),
            "unit_price":     s.get("unit_price"),
            "amount":         s.get("settlement_amount") or 0,
            "is_general":     is_gen,
            "sponsor_cost_this_month": len(exp_months_this_month) * 40000,
        }

    # 주문은 없지만 해당 월에 체험(협찬)이 잡힌 인플루언서도 카드로 포함
    # (이전 월처럼 인플루언서 카드를 만들기 위함 — 매출/정산 0, 협찬원가만 발생)
    for name, months in inf_exp_months.items():
        if name in inf_summary:
            continue
        cnt = sum(1 for m in months if m == target_month)
        if cnt > 0:
            inf_summary[name] = {
                "order_count":    0,
                "qty":            0,
                "cumulative_qty": None,
                "unit_price":     None,
                "amount":         0,
                "is_general":     False,
                "sponsor_cost_this_month": cnt * 40000,
            }

    # 덮어쓰기 방식: 재실행 시 누적 합산하지 않고 revenue.json 값으로 교체
    total_gross      = revenue.get("gross_revenue", 0)
    total_unit_count = revenue.get("unit_count", 0)
    total_net_profit = revenue.get("net_profit", 0)
    op               = revenue.get("operating_profit", 0)

    snapshot = {
        "month":        target_month,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gross_revenue":        total_gross,
        "net_profit":           total_net_profit,
        "order_count":          revenue.get("order_count", 0),
        "unit_count":           total_unit_count,
        "operating_profit":     op,
        "operating_profit_rate": round(op / total_gross, 4) if total_gross else 0,
        "total_sent":    total_sent,
        "replied":       replied,
        "meeting_total": meeting_total,
        "exp_total":     exp_total,
        "ad_total":      ad_total,
        "reply_rate":    mail_kpi.get("reply_rate", 0),
        "exp_rate":      round(exp_total / total_sent, 4) if total_sent else 0,
        "ad_rate":       round(ad_total / total_sent, 4) if total_sent else 0,
        "meeting_rate":  mail_kpi.get("meeting_rate", 0),
        "inf_status":    inf_data.get("inf_status", {}),
        "influencers":   inf_summary,
    }

    # 제품·스토어별 집계 (Raw_Data 기반)
    cfg = _load_config()
    by_product, by_store = aggregate_by_product_store(target_month, cfg)
    if by_product:
        snapshot["by_product"] = by_product
    if by_store:
        snapshot["by_store"] = by_store

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_HIST.mkdir(parents=True, exist_ok=True)

    filename = f"{target_month}.json"
    site_path  = HISTORY_DIR / filename
    local_path = LOCAL_HIST / filename

    content = json.dumps(snapshot, ensure_ascii=False, indent=2)
    site_path.write_text(content, encoding="utf-8")
    local_path.write_text(content, encoding="utf-8")

    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    print(f"[INFO] 스냅샷 저장: {site_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
