#!/usr/bin/env python3
# build_snapshot.py — STEP 7: 월별 스냅샷 저장 (site/data/history/YYYY-MM.json)
# 사용법: python build_snapshot.py <revenue_json> <mail_kpi_json> <inf_json> <settlement_json> <YYYY-MM>
import sys
import json
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR    = Path(r"C:\Users\user\비서")
HISTORY_DIR = BASE_DIR / "site" / "data" / "history"
LOCAL_HIST  = BASE_DIR / "output" / "history"


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
