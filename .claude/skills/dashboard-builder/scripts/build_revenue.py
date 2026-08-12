#!/usr/bin/env python3
# build_revenue.py — STEP 6: 매출·수익 집계
# 사용법: python build_revenue.py <bucket_json> <settlement_summary_json> <inf_json>
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


def get_sponsor_cost_for_month(per_influencer: dict, target_month: str) -> int:
    """해당 월에 체험 날짜가 있는 인플루언서의 협찬원가 합산."""
    total = 0
    for info in per_influencer.values():
        if not isinstance(info, dict):
            continue
        for ym in info.get("exp_months", []):
            if ym == target_month:
                total += 40000
    return total


def main():
    if len(sys.argv) < 3:
        print("사용법: python build_revenue.py <bucket_json> <settlement_summary_json> [inf_json] [YYYY-MM]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8-sig") as f:
        bucket_data = json.load(f)
    with open(sys.argv[2], encoding="utf-8-sig") as f:
        settlement_data = json.load(f)

    # inf_json, target_month 선택 인수
    inf_data = {}
    target_month = None
    for arg in sys.argv[3:]:
        if len(arg) == 7 and arg[4] == "-":
            target_month = arg
        else:
            try:
                with open(arg, encoding="utf-8-sig") as f:
                    inf_data = json.load(f)
            except Exception:
                pass

    config = load_config()
    product_unit_price       = config.get("product_unit_price", 120000)
    general_unit_price       = config.get("general_unit_price", 130000)
    general_settlement_price = config.get("general_settlement_price", 84000)
    labor_cost_per_unit      = config.get("labor_cost_per_unit", 20000)

    settlement_orders = bucket_data.get("settlement", [])
    general_orders    = bucket_data.get("general", [])
    excluded_orders   = bucket_data.get("excluded", [])

    # 수량은 항상 settlement.json 누계(월 전체) 기준으로 계산
    # bucket은 신규 배치분만 담고 있어 과소계산되므로 사용 안 함
    all_orders    = settlement_orders + general_orders + excluded_orders
    order_count   = sum(s.get("order_count", 0) for s in settlement_data.get("summaries", []))
    unit_count    = sum(s.get("qty", 0) for s in settlement_data.get("summaries", []) if not s.get("is_general", False))
    general_count = sum(s.get("qty", 0) for s in settlement_data.get("summaries", []) if s.get("is_general", False))

    total_qty = unit_count + general_count

    # 매출: 인플루언서 수량 × 120,000 + 기타/일반 수량 × 130,000
    gross_revenue = unit_count * product_unit_price + general_count * general_unit_price

    # 인플루언서 정산 비용 (settlement 버킷) + 기타/일반 정산 비용 (84,000/개)
    influencer_cost = sum(
        s.get("settlement_amount") or 0
        for s in settlement_data.get("summaries", [])
        if not s.get("is_general", False)
    )
    general_settlement_cost = general_count * general_settlement_price
    influencer_cost += general_settlement_cost

    # 협찬원가: 해당 월에 체험 날짜가 있는 건 × 40,000
    per_influencer = inf_data.get("per_influencer", {})
    if target_month:
        sponsor_cost = get_sponsor_cost_for_month(per_influencer, target_month)
    else:
        # target_month 미지정 시 전체 합산
        sponsor_cost = sum(
            info.get("sponsor_cost", 0)
            for info in per_influencer.values()
            if isinstance(info, dict)
        )

    # 수익 = 매출 - 정산비 - 협찬원가
    net_profit = gross_revenue - influencer_cost - sponsor_cost

    # 영업이익 = 수익 - 눈길 인건비(qty × 20,000)
    labor_cost       = total_qty * labor_cost_per_unit
    operating_profit = net_profit - labor_cost

    revenue = {
        "order_count":      order_count,
        "unit_count":       total_qty,
        "gross_revenue":    int(gross_revenue),
        "influencer_cost":  int(influencer_cost),
        "sponsor_cost":     int(sponsor_cost),
        "labor_cost":       int(labor_cost),
        "net_profit":       int(net_profit),
        "operating_profit": int(operating_profit),
    }

    print(json.dumps(revenue, ensure_ascii=False, indent=2))
    print(f"[INFO] 매출 {gross_revenue:,}원 / 수익 {net_profit:,}원 / 영업이익 {operating_profit:,}원", file=sys.stderr)


if __name__ == "__main__":
    main()
