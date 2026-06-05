#!/usr/bin/env python3
# build_kpi.py — KPI 집계 및 dashboard.json 직렬화
# 사용법: python build_kpi.py <mail_kpi_json> <inf_json> <revenue_json> <settlement_summary_json>
# 모든 인수를 파일 경로 또는 '-' (stdin)로 받음. 순서 고정.
import sys
import json
import re
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

GROSS_PRICE_PER_UNIT = 120000  # 매출 단가
COGS_PER_UNIT        = 36000   # 원가
MARGIN_GENERAL       = 84000   # 기타/일반 정산가


def tier_price(cum: int) -> int:
    if cum >= 100: return 25000
    if cum >= 30:  return 22000
    return 20000

DISPLAY_STATUS_MAP = {
    "미팅_대기": "미팅대기",
    "미팅_진행": "미팅진행",
    "체험진행_1차": "1차 체험진행",
    "체험진행_2차": "2차 체험진행",
    "체험진행_3차": "3차 체험진행",
    "광고예정_1차": "1차 광고예정",
    "광고예정_2차": "2차 광고예정",
    "광고완료_1차": "1차 광고완료",
    "기타": "기타",
}


def load_json(path_or_dash: str) -> dict:
    if path_or_dash == "-":
        return json.load(sys.stdin)
    with open(path_or_dash, encoding="utf-8-sig") as f:
        return json.load(f)


GROSS_PRICE_INF = 120000  # 정산대상 인플루언서 매출 단가
GROSS_PRICE_GEN = 130000  # 기타/일반 매출 단가
COGS_PER_UNIT   = 36000   # 원가 (개당)


def build_profit_analysis(per_influencer: dict | None = None) -> dict:
    """history 파일 기반으로 월별·인플루언서별 영업이익 집계.
    기여수익(정산대상) = 12만×qty − 정산액 − 원가(3.6만×qty) − 해당월 협찬원가
    기여수익(기타/일반) = 13만×qty − 원가(3.6만×qty)"""
    if not HISTORY_DIR.exists():
        return {}

    per_influencer = per_influencer or {}

    inf_exp_months: dict[str, list[str]] = {}
    for name, info in per_influencer.items():
        if isinstance(info, dict):
            inf_exp_months[name] = [m for m in info.get("exp_months", []) if m]

    monthly: dict = {}
    cumulative = 0
    inf_cum: dict = {}

    for p in sorted(HISTORY_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            month      = d.get("month", p.stem)
            gross      = d.get("gross_revenue", 0)
            op         = d.get("operating_profit", 0)
            unit_count = d.get("unit_count", 0)

            cumulative += op
            monthly[month] = {
                "gross_revenue":         gross,
                "unit_count":            unit_count,
                "operating_profit":      op,
                "operating_profit_rate": round(op / gross, 4) if gross else 0,
                "cumulative_profit":     cumulative,
            }

            known_qty = 0
            GEN_KEY = "기타/일반"
            for name, info in d.get("influencers", {}).items():
                qty    = info.get("qty", 0)
                amount = info.get("amount") or 0
                is_gen = info.get("is_general", False)
                is_waived = info.get("settlement_waived", False)
                known_qty += qty

                if is_waived:
                    # 정산안받음 → 기타/일반에 수량·기여수익 합산
                    if GEN_KEY not in inf_cum:
                        inf_cum[GEN_KEY] = {"qty": 0, "settlement": 0, "contribution": 0}
                    inf_cum[GEN_KEY]["qty"] += qty
                    inf_cum[GEN_KEY]["contribution"] += qty * (GROSS_PRICE_INF - COGS_PER_UNIT)
                    continue

                if name not in inf_cum:
                    inf_cum[name] = {"qty": 0, "settlement": 0, "contribution": 0}
                inf_cum[name]["qty"] += qty

                if is_gen:
                    # 기타/일반: 매출 13만 − 원가 3.6만
                    inf_cum[name]["contribution"] += qty * (GROSS_PRICE_GEN - COGS_PER_UNIT)
                else:
                    # 정산대상: 매출 12만 − 정산액 − 원가 3.6만 − 해당월 협찬원가
                    month_sponsor = inf_exp_months.get(name, []).count(month) * 40000
                    inf_cum[name]["settlement"]   += amount
                    inf_cum[name]["contribution"] += qty * (GROSS_PRICE_INF - COGS_PER_UNIT) - amount - month_sponsor

            misc_qty = unit_count - known_qty
            if misc_qty > 0:
                key = "(미등재/기타)"
                if key not in inf_cum:
                    inf_cum[key] = {"qty": 0, "settlement": 0, "contribution": 0}
                inf_cum[key]["qty"]          += misc_qty
                inf_cum[key]["contribution"] += misc_qty * (GROSS_PRICE_GEN - COGS_PER_UNIT)

        except Exception as e:
            print(f"[WARN] history 오류 {p.name}: {e}", file=sys.stderr)

    return {
        "note": "기여수익(정산대상)=12만×qty−정산액−원가3.6만×qty−해당월협찬원가 / 기여수익(기타)=13만×qty−원가3.6만×qty",
        "monthly": monthly,
        "influencer_cumulative": inf_cum,
    }


def load_history() -> dict:
    """기존 history 파일에서 trends 데이터 재구성"""
    months = []
    reply_rates, exp_rates, ad_rates, meeting_rates = [], [], [], []
    gross_revenues, net_profits = [], []
    total_sents, replieds, meeting_totals, exp_totals, ad_totals = [], [], [], [], []
    operating_profits, operating_profit_rates = [], []

    if not HISTORY_DIR.exists():
        return {}
    for p in sorted(HISTORY_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            months.append(d.get("month", p.stem))
            reply_rates.append(d.get("reply_rate", 0))
            exp_rates.append(d.get("exp_rate", 0))
            ad_rates.append(d.get("ad_rate", 0))
            meeting_rates.append(d.get("meeting_rate", 0))
            gross_revenues.append(d.get("gross_revenue", 0))
            net_profits.append(d.get("net_profit", 0))
            total_sents.append(d.get("total_sent", 0))
            replieds.append(d.get("replied", 0))
            meeting_totals.append(d.get("meeting_total", 0))
            exp_totals.append(d.get("exp_total", 0))
            ad_totals.append(d.get("ad_total", 0))
            operating_profits.append(d.get("operating_profit", 0))
            operating_profit_rates.append(d.get("operating_profit_rate", 0))
        except Exception:
            pass
    # exp_by_month: 가장 최근 history 파일에서 읽거나 없으면 빈 dict
    exp_by_month: dict = {}
    for p in sorted(HISTORY_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if "exp_by_month" in d:
                exp_by_month = d["exp_by_month"]
        except Exception:
            pass

    return {
        "months":                months,
        "reply_rate":            reply_rates,
        "exp_rate":              exp_rates,
        "ad_rate":               ad_rates,
        "meeting_rate":          meeting_rates,
        "gross_revenue":         gross_revenues,
        "net_profit":            net_profits,
        "total_sent":            total_sents,
        "replied":               replieds,
        "meeting_total":         meeting_totals,
        "exp_total":             exp_totals,
        "ad_total":              ad_totals,
        "exp_by_month":          exp_by_month,
        "operating_profit":      operating_profits,
        "operating_profit_rate": operating_profit_rates,
    }


def get_inf_info(per_influencer: dict, ytber: str) -> tuple[str, int, int, list]:
    """per_influencer에서 (status_key, exp_count, sponsor_cost, exp_months) 반환.
    구버전(문자열) / 신버전(dict) 양쪽 호환."""
    raw = per_influencer.get(ytber, "")
    if isinstance(raw, dict):
        return (raw.get("status", "기타"), raw.get("exp_count", 0),
                raw.get("sponsor_cost", 0), raw.get("exp_months", []))
    return raw, 0, 0, []


def build_settlement_summary(settlement_data: dict, per_influencer: dict, current_month: str | None = None) -> dict:
    summary = {}
    for s in settlement_data.get("summaries", []):
        ytber = s.get("ytber", "")
        status_key, exp_cnt, sponsor_cost, exp_months = get_inf_info(per_influencer, ytber)
        display_status = DISPLAY_STATUS_MAP.get(status_key, status_key)
        if s.get("is_general"):
            qty = s.get("qty", 0)
            summary[ytber] = {
                "건수": s.get("order_count", 0),
                "수량": qty,
                "단가": MARGIN_GENERAL,
                "금액": qty * MARGIN_GENERAL,
                "정산대상": False,
                "현재상태": display_status,
            }
        elif s.get("settlement_waived"):
            summary[ytber] = {
                "건수": s.get("order_count", 0),
                "수량": s.get("qty", 0),
                "누적수량": s.get("cumulative_qty"),
                "현재단가": s.get("unit_price"),
                "금액": 0,
                "체험횟수": exp_cnt,
                "협찬원가": sponsor_cost,
                "체험월목록": exp_months,
                "정산대상": False,
                "정산안받음": True,
                "현재상태": display_status,
            }
        else:
            summary[ytber] = {
                "건수": s.get("order_count", 0),
                "수량": s.get("qty", 0),
                "누적수량": s.get("cumulative_qty"),
                "현재단가": s.get("unit_price"),
                "금액": s.get("settlement_amount"),
                "체험횟수": exp_cnt,
                "협찬원가": sponsor_cost,
                "체험월목록": exp_months,
                "정산대상": True,
                "현재상태": display_status,
            }

    # 현재 월 히스토리에서 settlement.json에 없는 인플루언서 보완
    # (이전 파이프라인 실행에서 처리된 인플루언서도 settlement_summary에 표시)
    month_key = current_month or datetime.now().strftime("%Y-%m")
    hist_path = HISTORY_DIR / f"{month_key}.json"
    if hist_path.exists():
        try:
            hist = json.loads(hist_path.read_text(encoding="utf-8"))
            for ytber, info in hist.get("influencers", {}).items():
                if ytber in summary:
                    continue
                status_key, exp_cnt, sponsor_cost, exp_months = get_inf_info(per_influencer, ytber)
                display_status = DISPLAY_STATUS_MAP.get(status_key, status_key)
                if info.get("is_general"):
                    qty = info.get("qty", 0)
                    summary[ytber] = {
                        "건수": info.get("order_count", 0),
                        "수량": qty,
                        "단가": MARGIN_GENERAL,
                        "금액": qty * MARGIN_GENERAL,
                        "정산대상": False,
                        "현재상태": display_status,
                    }
                elif info.get("settlement_waived"):
                    summary[ytber] = {
                        "건수": info.get("order_count", 0),
                        "수량": info.get("qty", 0),
                        "누적수량": info.get("cumulative_qty"),
                        "현재단가": info.get("unit_price"),
                        "금액": 0,
                        "체험횟수": exp_cnt,
                        "협찬원가": sponsor_cost,
                        "체험월목록": exp_months,
                        "정산대상": False,
                        "정산안받음": True,
                        "현재상태": display_status,
                    }
                else:
                    summary[ytber] = {
                        "건수": info.get("order_count", 0),
                        "수량": info.get("qty", 0),
                        "누적수량": info.get("cumulative_qty"),
                        "현재단가": info.get("unit_price"),
                        "금액": info.get("amount"),
                        "체험횟수": exp_cnt,
                        "협찬원가": sponsor_cost,
                        "체험월목록": exp_months,
                        "정산대상": True,
                        "현재상태": display_status,
                    }
        except Exception as e:
            print(f"[WARN] 히스토리 병합 오류: {e}", file=sys.stderr)

    # per_influencer 전체 순회 — 주문이 없어도 등재된 인플루언서는 현재상태 표시
    for ytber, raw in per_influencer.items():
        if ytber in summary:
            continue
        status_key, exp_cnt, sponsor_cost, exp_months = get_inf_info(per_influencer, ytber)
        display_status = DISPLAY_STATUS_MAP.get(status_key, status_key)
        summary[ytber] = {
            "건수": 0,
            "수량": 0,
            "누적수량": 0,
            "현재단가": None,
            "금액": 0,
            "체험횟수": exp_cnt,
            "협찬원가": sponsor_cost,
            "체험월목록": exp_months,
            "정산대상": True,
            "현재상태": display_status,
        }

    return summary


def build_influencer_files(settlement_data: dict, per_influencer: dict) -> None:
    INF_DIR.mkdir(parents=True, exist_ok=True)

    history_by_ytber: dict[str, list] = {}
    if HISTORY_DIR.exists():
        for p in sorted(HISTORY_DIR.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                month = d.get("month", p.stem)
                for ytber, info in d.get("influencers", {}).items():
                    history_by_ytber.setdefault(ytber, []).append({
                        "month": month,
                        "qty": info.get("qty", 0),
                        "amount": info.get("amount"),
                    })
            except Exception:
                pass

    for s in settlement_data.get("summaries", []):
        if s.get("is_general"):
            continue
        ytber = s.get("ytber", "")
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', ytber)
        status_key, exp_cnt, sponsor_cost, _ = get_inf_info(per_influencer, ytber)
        display_status = DISPLAY_STATUS_MAP.get(status_key, status_key)

        data = {
            "name": ytber,
            "current_status": display_status,
            "cumulative_qty": s.get("cumulative_qty"),
            "current_tier_price": s.get("unit_price"),
            "monthly_orders": history_by_ytber.get(ytber, []),
            "upcoming_schedule": [],
        }

        out_path = INF_DIR / f"{safe_name}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] 인플루언서 JSON: {out_path.name}", file=sys.stderr)


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

    # KPI: 체험·광고 전환율은 인플루언서관리 시트 확정값 / 미팅은 메일시트 누적값 우선
    total_sent    = mail_kpi.get("total_sent", 0)
    meeting_total = mail_kpi.get("meeting_total", 0)
    exp_total     = inf_data.get("exp_total", mail_kpi.get("exp_total_approx", 0))
    ad_total      = inf_data.get("ad_total", mail_kpi.get("ad_total", 0))

    mail_funnel = {
        "total_sent":    total_sent,
        "etc_excluded":  mail_kpi.get("etc_excluded", 0),
        "replied":       mail_kpi.get("replied", 0),
        "reply_rate":    mail_kpi.get("reply_rate", 0),
        "meeting_total": meeting_total,
        "meeting_rate":  round(meeting_total / total_sent, 4) if total_sent else 0,
        "exp_total":     exp_total,
        "exp_rate":      round(exp_total / total_sent, 4) if total_sent else 0,
        "ad_total":      ad_total,
        "ad_rate":       round(ad_total / total_sent, 4) if total_sent else 0,
    }

    per_influencer = inf_data.get("per_influencer", {})
    build_influencer_files(settlement, per_influencer)

    trends = load_history()

    alerts = {"unregistered_influencers": []}

    dashboard = {
        "generated_at":           now.isoformat(timespec="seconds"),
        "current_month":          current_month,
        "revenue":                revenue,
        "mail_funnel":            mail_funnel,
        "inf_status":             inf_data.get("inf_status", {}),
        "settlement_month":       int(current_month.split("-")[1]),
        "settlement_summary":     build_settlement_summary(settlement, per_influencer, current_month),
        "trends":                 trends,
        "mail_funnel_by_month":   mail_kpi.get("by_month", {}),
        "ad_by_month":            inf_data.get("ad_by_month", {}),
        "profit_analysis":        build_profit_analysis(per_influencer),
        "alerts":                 alerts,
    }

    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DIR / "dashboard.json"
    out_path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[INFO] dashboard.json 저장: {out_path}", file=sys.stderr)
    print(json.dumps(dashboard, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
