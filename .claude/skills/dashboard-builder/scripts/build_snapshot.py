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

MARGIN_SETTLEMENT = 45000
MARGIN_GENERAL    = 84000


def tier_price(cum: int) -> int:
    if cum >= 100: return 25000
    if cum >= 30:  return 22000
    return 20000


def compute_operating_profit(inf_summary: dict, total_unit_count: int) -> int:
    """인플루언서별 스냅샷에서 영업이익 계산 (구간 단가 적용)"""
    op = 0
    known_qty = 0
    for info in inf_summary.values():
        qty = info.get("qty", 0)
        known_qty += qty
        cum = info.get("cumulative_qty") or 0
        is_gen = info.get("is_general", False)
        if is_gen:
            op += qty * MARGIN_GENERAL
        else:
            prev_cum = max(cum - qty, 0)
            for q in range(prev_cum, cum):
                op += MARGIN_SETTLEMENT - tier_price(q + 1)
    misc_qty = total_unit_count - known_qty
    if misc_qty > 0:
        op += misc_qty * MARGIN_GENERAL
    return op


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

    # 인플루언서별 집계 — 기존 + 신규 합산
    inf_summary = dict(prev.get("influencers", {}))
    for s in settlement.get("summaries", []):
        ytber = s.get("ytber", "")
        existing = inf_summary.get(ytber, {})
        is_gen = s.get("is_general", False)
        inf_summary[ytber] = {
            "order_count":    (existing.get("order_count", 0) or 0) + s.get("order_count", 0),
            "qty":            (existing.get("qty", 0) or 0) + s.get("qty", 0),
            "cumulative_qty": s.get("cumulative_qty"),       # 항상 최신값 (DB 기준)
            "unit_price":     s.get("unit_price"),           # 최신 단가
            "amount":         (existing.get("amount") or 0) + (s.get("settlement_amount") or 0),
            "is_general":     is_gen,
        }

    total_gross      = (prev.get("gross_revenue") or 0) + revenue.get("gross_revenue", 0)
    total_unit_count = (prev.get("unit_count") or 0) + revenue.get("unit_count", 0)
    op               = compute_operating_profit(inf_summary, total_unit_count)

    snapshot = {
        "month":        target_month,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gross_revenue":        total_gross,
        "net_profit":           (prev.get("net_profit") or 0) + revenue.get("net_profit", 0),
        "order_count":          (prev.get("order_count") or 0) + revenue.get("order_count", 0),
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
