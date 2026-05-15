#!/usr/bin/env python3
# build_kpi.py — KPI 집계 및 dashboard.json 직렬화
# 사용법: python build_kpi.py <mail_kpi_json> <inf_json> <revenue_json> <settlement_summary_json>
# 모든 인수를 파일 경로 또는 '-' (stdin)로 받음. 순서 고정.
import sys
import json
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR   = Path(r"C:\Users\user\비서")
SITE_DIR   = BASE_DIR / "site" / "data"
HISTORY_DIR = SITE_DIR / "history"
INF_DIR    = SITE_DIR / "influencer"


def load_json(path_or_dash: str) -> dict:
    if path_or_dash == "-":
        return json.load(sys.stdin)
    with open(path_or_dash, encoding="utf-8") as f:
        return json.load(f)


def load_history() -> dict:
    """기존 history 파일에서 trends 데이터 재구성"""
    months, reply_rates, exp_rates, ad_rates, gross_revenues, net_profits = [], [], [], [], [], []
    if not HISTORY_DIR.exists():
        return {}
    for p in sorted(HISTORY_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            months.append(d.get("month", p.stem))
            reply_rates.append(d.get("reply_rate", 0))
            exp_rates.append(d.get("exp_rate", 0))
            ad_rates.append(d.get("ad_rate", 0))
            gross_revenues.append(d.get("gross_revenue", 0))
            net_profits.append(d.get("net_profit", 0))
        except Exception:
            pass
    return {
        "months": months,
        "reply_rate": reply_rates,
        "exp_rate": exp_rates,
        "ad_rate": ad_rates,
        "gross_revenue": gross_revenues,
        "net_profit": net_profits,
    }


def build_settlement_summary(settlement_data: dict) -> dict:
    summary = {}
    for s in settlement_data.get("summaries", []):
        ytber = s.get("ytber", "")
        if s.get("is_general"):
            summary[ytber] = {
                "건수": s.get("order_count", 0),
                "수량": s.get("qty", 0),
                "금액": None,
                "정산대상": False,
            }
        else:
            summary[ytber] = {
                "건수": s.get("order_count", 0),
                "수량": s.get("qty", 0),
                "누적수량": s.get("cumulative_qty"),
                "현재단가": s.get("unit_price"),
                "금액": s.get("settlement_amount"),
                "정산대상": True,
            }
    return summary


def main():
    if len(sys.argv) < 5:
        print("사용법: python build_kpi.py <mail_json> <inf_json> <revenue_json> <settlement_json>", file=sys.stderr)
        sys.exit(1)

    mail_kpi    = load_json(sys.argv[1])
    inf_data    = load_json(sys.argv[2])
    revenue     = load_json(sys.argv[3])
    settlement  = load_json(sys.argv[4])

    now = datetime.now()
    current_month = now.strftime("%Y-%m")

    # KPI: 체험·광고 전환율은 인플루언서관리 시트에서 확정값 사용
    total_sent = mail_kpi.get("total_sent", 0)
    exp_total  = inf_data.get("exp_total", mail_kpi.get("exp_total_approx", 0))
    ad_total   = inf_data.get("ad_total", mail_kpi.get("ad_total", 0))

    mail_funnel = {
        "total_sent":    total_sent,
        "etc_excluded":  mail_kpi.get("etc_excluded", 0),
        "replied":       mail_kpi.get("replied", 0),
        "reply_rate":    mail_kpi.get("reply_rate", 0),
        "meeting_total": mail_kpi.get("meeting_total", 0),
        "meeting_rate":  mail_kpi.get("meeting_rate", 0),
        "exp_total":     exp_total,
        "exp_rate":      round(exp_total / total_sent, 4) if total_sent else 0,
        "ad_total":      ad_total,
        "ad_rate":       round(ad_total / total_sent, 4) if total_sent else 0,
    }

    trends = load_history()

    alerts = {}
    unregistered = settlement.get("unregistered", [])
    if unregistered:
        # 이름별 집계
        unreg_map: dict[str, dict] = {}
        for u in unregistered:
            n = u["name"]
            if n not in unreg_map:
                unreg_map[n] = {"name": n, "건수": 0, "수량": 0}
            unreg_map[n]["건수"] += 1
            unreg_map[n]["수량"] += u.get("qty", 0)
        alerts["unregistered_influencers"] = list(unreg_map.values())

    dashboard = {
        "generated_at":      now.isoformat(timespec="seconds"),
        "current_month":     current_month,
        "revenue":           revenue,
        "mail_funnel":       mail_funnel,
        "inf_status":        inf_data.get("inf_status", {}),
        "settlement_month":  int(current_month.split("-")[1]),
        "settlement_summary": build_settlement_summary(settlement),
        "trends":            trends,
        "alerts":            alerts,
    }

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DIR / "dashboard.json"
    out_path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[INFO] dashboard.json 저장: {out_path}", file=sys.stderr)
    print(json.dumps(dashboard, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
