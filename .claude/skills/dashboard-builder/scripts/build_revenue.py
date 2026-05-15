#!/usr/bin/env python3
# build_revenue.py — STEP 6: 매출·수익 집계
# 사용법: python build_revenue.py <bucket_json> <settlement_summary_json>
# 출력: stdout JSON (revenue 딕셔너리)
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

CONFIG_PATH = Path(r"C:\Users\user\비서\.claude\skills\settlement-generator\scripts\ytber_config.json")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    if len(sys.argv) < 3:
        print("사용법: python build_revenue.py <bucket_json> <settlement_summary_json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8-sig") as f:
        bucket_data = json.load(f)
    with open(sys.argv[2], encoding="utf-8-sig") as f:
        settlement_data = json.load(f)

    config = load_config()
    personal_fee_per_order    = config.get("personal_fee_per_order", 10000)
    fixed_misc_cost_per_order = config.get("fixed_misc_cost_per_order", 50000)

    settlement_orders = bucket_data.get("settlement", [])
    general_orders    = bucket_data.get("general", [])
    excluded_orders   = bucket_data.get("excluded", [])

    # 매출: 정산대상 + 기타/일반 + 정산제외 합산 (완전제외 제외)
    all_orders = settlement_orders + general_orders + excluded_orders
    gross_revenue = sum(o.get("amount", 0) for o in all_orders)

    # 버킷이 비어있으면(신규 0건 재실행) settlement.json 누계에서 주문/수량 복원
    if not all_orders and settlement_data.get("summaries"):
        order_count = sum(s.get("order_count", 0) for s in settlement_data["summaries"])
        unit_count  = sum(s.get("qty", 0) for s in settlement_data["summaries"])
    else:
        order_count = len(all_orders)
        unit_count  = sum(o.get("qty", 0) for o in all_orders)

    # 인플루언서 정산 비용 (settlement 버킷만)
    influencer_cost = sum(
        s.get("settlement_amount") or 0
        for s in settlement_data.get("summaries", [])
        if not s.get("is_general", False)
    )

    personal_fee = personal_fee_per_order * order_count
    misc_cost    = fixed_misc_cost_per_order * order_count
    net_profit   = gross_revenue - influencer_cost - personal_fee - misc_cost

    revenue = {
        "order_count":     order_count,
        "unit_count":      unit_count,
        "gross_revenue":   int(gross_revenue),
        "influencer_cost": int(influencer_cost),
        "personal_fee":    int(personal_fee),
        "misc_cost":       int(misc_cost),
        "net_profit":      int(net_profit),
    }

    print(json.dumps(revenue, ensure_ascii=False, indent=2))
    print(f"[INFO] 매출 {gross_revenue:,}원 / 수익 {net_profit:,}원", file=sys.stderr)


if __name__ == "__main__":
    main()
