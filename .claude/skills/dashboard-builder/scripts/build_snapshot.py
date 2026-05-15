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

    total_sent = mail_kpi.get("total_sent", 0)
    exp_total  = inf_data.get("exp_total", 0)
    ad_total   = inf_data.get("ad_total", 0)

    # 인플루언서별 집계
    inf_summary = {}
    for s in settlement.get("summaries", []):
        ytber = s.get("ytber", "")
        inf_summary[ytber] = {
            "qty": s.get("qty", 0),
            "amount": s.get("settlement_amount"),
            "is_general": s.get("is_general", False),
        }

    snapshot = {
        "month":        target_month,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gross_revenue": revenue.get("gross_revenue", 0),
        "net_profit":    revenue.get("net_profit", 0),
        "order_count":   revenue.get("order_count", 0),
        "unit_count":    revenue.get("unit_count", 0),
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
