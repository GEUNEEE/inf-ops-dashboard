#!/usr/bin/env python3
# build_yk.py — 영끌러님 대시보드 데이터 생성 (site/yk/data/)
#
# 종합 파이프라인 스크립트를 import 해 "ㅇ" 명단으로 필터한 결과를 같은 키 구조로 만든다.
#   - 명단: 종합 관리시트 `영끌러님 관리` 행 ㅇ (parse_inf.parse_master → yk_marked)
#   - 메일 퍼널: 유튜브/뷰티/슬립이지 공유 파일의 `구분`=ㅇ 행 (parse_mail)
#   - 매출·수량: Raw_Data를 ㅇ 명단으로 필터해 월×제품 집계 (build_snapshot.aggregate_*)
#   - 정산금·누적수량·단가: 종합 output/tmp/settlement.json 을 이름으로 필터 (재계산 안 함)
# 출력: <out>/dashboard.json, <out>/history/YYYY-MM.json, <out>/influencer/<name>.json
#
# 사용법: PYTHONUTF8=1 python build_yk.py [--no-filter] [--out DIR] [--month YYYY-MM]
#   --no-filter : ㅇ 무시, 전원·전체 행 대상 (종합 dashboard.json 과의 정합 검증용)
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(r"C:\Users\user\비서")
_SKILLS = BASE_DIR / ".claude" / "skills"
for _sub in ("excel-parser", "dashboard-builder"):
    _p = str(_SKILLS / _sub / "scripts")
    if _p not in sys.path:
        sys.path.insert(0, _p)

import parse_mail as PM      # noqa: E402
import parse_inf as PI       # noqa: E402
import build_snapshot as BS  # noqa: E402
import build_kpi as BK       # noqa: E402

DEFAULT_OUT        = BASE_DIR / "site" / "yk" / "data"
MASTER_HISTORY_DIR = BASE_DIR / "site" / "data" / "history"
SETTLEMENT_JSON    = BASE_DIR / "output" / "tmp" / "settlement.json"
UNASSIGNED         = "미지정"

# 메일 파일 종류 → 제품 (파일 종류로 고정)
MAIL_KINDS = [("유튜브", "흑염소"), ("뷰티", "화장품"), ("슬립이지", "수면영양제")]
# ㅇ 매출이 없어도 항상 보여주는 제품 탭
ALWAYS_PRODUCTS = {"흑염소", "화장품", "수면영양제"}

SPONSOR_COST_PER_EXP = PI.SPONSOR_COST_PER_EXP


def log(msg):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- 순수 헬퍼 (tests/test_build_yk.py)
def mail_cum_through(by_month: dict, month: str) -> dict:
    """메일 by_month {ym: {sent,replied,meeting,exp,ad}} 를 month 까지 누적 합산."""
    sent = replied = meeting = exp = ad = 0
    for ym, d in (by_month or {}).items():
        if ym <= month:
            sent    += d.get("sent", 0)
            replied += d.get("replied", 0)
            meeting += d.get("meeting", 0)
            exp     += d.get("exp", 0)
            ad      += d.get("ad", 0)
    return {
        "total_sent":    sent,
        "replied":       replied,
        "meeting_total": meeting,
        "exp_total":     exp,
        "ad_total":      ad,
        "reply_rate":    round(replied / sent, 4) if sent else 0,
        "meeting_rate":  round(meeting / sent, 4) if sent else 0,
        "exp_rate":      round(exp / sent, 4) if sent else 0,
        "ad_rate":       round(ad / sent, 4) if sent else 0,
    }


def filter_settlement(settlement: dict, names) -> dict:
    """종합 settlement.json 을 이름 집합으로 필터 (정산금·누적수량·단가 재계산 없음)."""
    names = set(names)
    out = dict(settlement)
    out["summaries"] = [s for s in settlement.get("summaries", []) if s.get("ytber") in names]
    out["unregistered"] = [u for u in settlement.get("unregistered", [])
                           if (u.get("name") if isinstance(u, dict) else u) in names]
    return out


def resolve_products(names, product_by_name: dict, raw_products: dict) -> dict:
    """이름별 제품: 종합 관리시트 `제품` 행 → Raw_Data 추정 → 미지정."""
    return {n: (product_by_name.get(n) or raw_products.get(n) or UNASSIGNED) for n in names}


# ---------------------------------------------------------------- 입력 수집
def raw_products_by_name(config: dict) -> dict:
    """Raw_Data 에서 유튜버(name_map 정규화)별 가장 많이 주문된 제품 → {name: product}."""
    import openpyxl
    out: dict = {}
    if not BS.RAWDATA_PATH.exists():
        return out
    name_map = config.get("name_map", {})
    default_product = config.get("product_registry", {}).get("default_product", "흑염소")
    counts: dict = {}
    try:
        wb = openpyxl.load_workbook(BS.RAWDATA_PATH, data_only=True, read_only=True)
        ws = wb["Raw_Data"]
    except Exception as e:
        log(f"[WARN] Raw_Data 제품 추정 실패: {e}")
        return out
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        raw_name = str(row[BS.RAW_COL_YTBER] or "").strip()
        if not raw_name:
            continue
        name = name_map.get(raw_name, raw_name)
        product = str((row[BS.RAW_COL_PRODUCT] if len(row) > BS.RAW_COL_PRODUCT else "") or "").strip() or default_product
        c = counts.setdefault(name, {})
        c[product] = c.get(product, 0) + 1
    wb.close()
    for name, c in counts.items():
        out[name] = max(c.items(), key=lambda kv: kv[1])[0]
    return out


def collect_mail(no_filter: bool) -> tuple[dict, dict]:
    """3개 공유 파일 → {product: parse_mail 결과(+source_file)}, 합산 결과."""
    owner_filter = None if no_filter else PM.is_owner_mark
    by_product: dict = {}
    for kind, product in MAIL_KINDS:
        path = PM.find_shared_xlsx(kind)
        if path is None:
            log(f"[WARN] {kind} 공유 파일 없음 → {product} 퍼널 0")
            r = PM.empty_result()
            r["source_file"] = None
        else:
            try:
                r = PM.parse_mail_workbook(path, owner_filter=owner_filter)
            except Exception as e:
                log(f"[WARN] {kind} 메일발송현황 파싱 실패 ({path.name}): {e}")
                r = PM.empty_result()
            r["source_file"] = path.name
        by_product[product] = r
        log(f"[INFO] 메일 {kind}({product}): {r.get('source_file')} — 발송 {r['total_sent']}건, "
            f"회신 {r['replied']}건, 체험 {r['exp_total_approx']}건, 광고 {r['ad_total']}건")
    merged = PM.merge_mail_results(list(by_product.values()))
    return by_product, merged


def load_master_history(month: str) -> dict:
    p = MASTER_HISTORY_DIR / f"{month}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[WARN] 종합 history 읽기 실패 {p.name}: {e}")
        return {}


# ---------------------------------------------------------------- 월별 스냅샷
def build_month_snapshot(month: str, config: dict, inf: dict, mail_merged: dict,
                         name_filter, yk_set, no_filter: bool) -> tuple[dict, dict]:
    """한 달치 yk 스냅샷(history/YYYY-MM.json 형식) + revenue dict."""
    default_product = config.get("product_registry", {}).get("default_product", "흑염소")
    cogs = int(config.get("cogs_per_unit", 0))

    by_product, by_store = BS.aggregate_by_product_store(month, config, name_filter=name_filter)
    cosmetics = BS.aggregate_cosmetics_breakdown(month, name_filter=name_filter)
    trials    = BS.aggregate_product_trials(month, name_filter=name_filter)

    manual = BS.manual_sales_for(config, month) if no_filter else []
    for m in manual:
        pd = by_product.setdefault(m["product"], {"qty": 0, "order_count": 0, "gross_revenue": 0, "net_profit": 0})
        pd["qty"] += m["qty"]; pd["order_count"] += 1; pd["gross_revenue"] += m["amount"]
    manual_fee = sum(m.get("fee", 0) for m in manual)

    # 인플루언서별 (정산금·누적수량은 종합 history 값 그대로, 명단으로만 필터)
    master = load_master_history(month)
    influencers: dict = {}
    for name, d in master.get("influencers", {}).items():
        if no_filter or name in yk_set:
            influencers[name] = dict(d)
    # (협찬만 있고 주문이 없는 달은 종합과 동일하게 카드 없음 — 정합 유지)

    pd_def        = by_product.get(default_product, {})
    gross         = int(pd_def.get("gross_revenue", 0))
    unit_count    = int(pd_def.get("qty", 0))
    order_count   = int(pd_def.get("order_count", 0))
    influencer_cost = sum(int(d.get("amount") or 0) for d in influencers.values() if not d.get("is_general"))
    sponsor_cost    = sum(int(d.get("sponsor_cost_this_month") or 0) for d in influencers.values())
    cogs_cost       = unit_count * cogs
    net_profit      = gross - influencer_cost - sponsor_cost - cogs_cost - manual_fee

    if no_filter and master:
        labor_cost  = int(master.get("labor_cost", 0))
        labor_qty   = int(master.get("labor_qty", 0))
        labor_basis = master.get("labor_basis", "all")
    else:
        labor_cost, labor_qty, labor_basis = 0, 0, "none"
    operating_profit = net_profit - labor_cost

    cum = mail_cum_through(mail_merged.get("by_month", {}), month)
    exp_total = sum(v for ym, v in inf.get("exp_by_month", {}).items() if ym <= month)
    ad_total  = sum(v for ym, v in inf.get("ad_by_month", {}).items() if ym <= month)
    total_sent = cum["total_sent"]

    snap = {
        "month":                 month,
        "generated_at":          datetime.now().isoformat(timespec="seconds"),
        "gross_revenue":         gross,
        "net_profit":            int(net_profit),
        "order_count":           order_count,
        "unit_count":            unit_count,
        "operating_profit":      int(operating_profit),
        "operating_profit_rate": round(operating_profit / gross, 4) if gross else 0,
        "labor_cost":            labor_cost,
        "labor_qty":             labor_qty,
        "labor_basis":           labor_basis,
        "total_sent":            total_sent,
        "replied":               cum["replied"],
        "meeting_total":         cum["meeting_total"],
        "exp_total":             exp_total,
        "ad_total":              ad_total,
        "reply_rate":            cum["reply_rate"],
        "exp_rate":              round(exp_total / total_sent, 4) if total_sent else 0,
        "ad_rate":               round(ad_total / total_sent, 4) if total_sent else 0,
        "meeting_rate":          cum["meeting_rate"],
        "inf_status":            inf.get("inf_status", {}),
        "influencers":           influencers,
    }
    if manual:
        snap["manual_sales"] = manual
    if by_product:
        snap["by_product"] = by_product
    if by_store:
        snap["by_store"] = by_store
    if cosmetics.get("by_option") or cosmetics.get("by_channel"):
        snap["cosmetics_breakdown"] = cosmetics
    if trials:
        snap["product_trials"] = trials

    revenue = {
        "order_count":      order_count + len(manual),
        "unit_count":       unit_count,
        "gross_revenue":    gross,
        "influencer_cost":  int(influencer_cost),
        "sponsor_cost":     int(sponsor_cost),
        "cogs_cost":        int(cogs_cost),
        "labor_cost":       labor_cost,
        "labor_qty":        labor_qty,
        "labor_basis":      labor_basis,
        "net_profit":       int(net_profit),
        "operating_profit": int(operating_profit),
    }
    if manual:
        revenue["manual_sales_amount"] = sum(m["amount"] for m in manual)
        revenue["manual_sales_qty"]    = sum(m["qty"] for m in manual)
        revenue["manual_sales_fee"]    = manual_fee
    return snap, revenue


def funnel_dict(r: dict, exp_total=None, ad_total=None) -> dict:
    """parse_mail 결과 → dashboard mail_funnel 형식 (체험·광고는 인자로 덮어쓸 수 있음)."""
    total = r.get("total_sent", 0)
    meeting = r.get("meeting_total", 0)
    exp = r.get("exp_total_approx", 0) if exp_total is None else exp_total
    ad  = r.get("ad_total", 0) if ad_total is None else ad_total
    return {
        "total_sent":    total,
        "etc_excluded":  r.get("etc_excluded", 0),
        "replied":       r.get("replied", 0),
        "reply_rate":    r.get("reply_rate", 0),
        "meeting_total": meeting,
        "meeting_rate":  round(meeting / total, 4) if total else 0,
        "exp_total":     exp,
        "exp_rate":      round(exp / total, 4) if total else 0,
        "ad_total":      ad,
        "ad_rate":       round(ad / total, 4) if total else 0,
    }


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-filter", action="store_true", help="ㅇ 무시, 전원 대상 (정합 검증용)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--month", default=None, help="정산 기준 월 YYYY-MM (기본: settlement.json)")
    args = ap.parse_args()
    no_filter = args.no_filter
    out_dir = Path(args.out)
    hist_dir = out_dir / "history"
    inf_dir  = out_dir / "influencer"

    config   = PI.load_config()
    name_map = config.get("name_map", {})

    # 1) 종합 관리시트 → ㅇ 명단
    master_xlsx = PI.find_master_xlsx()
    inf_all = PI.parse_master(master_xlsx, config)
    yk_set = set(inf_all.get("yk_marked", []))
    if no_filter:
        yk_set = {name_map.get(n, n) for n in inf_all.get("managed_set", [])}
        name_filter = None
        inf = inf_all
        log(f"[INFO] --no-filter: 전원 {len(yk_set)}명 · 메일 전체 행")
    else:
        name_filter = (lambda raw: name_map.get(str(raw).strip(), str(raw).strip()) in yk_set)
        inf = PI.parse_master(master_xlsx, config, name_filter=lambda n: n in yk_set)
        log(f"[INFO] 영끌러님 ㅇ 명단: {len(yk_set)}명 ({inf_all.get('source_file')})")
        if not yk_set:
            log("[WARN] ㅇ 표시된 인플루언서가 없습니다 — 매출·인플루언서 카드는 비어 있고 메일 퍼널만 집계됩니다")
    per_influencer = inf.get("per_influencer", {})

    # 2) 메일 퍼널 (파일별 = 제품별)
    mail_by_product, mail_merged = collect_mail(no_filter)

    # 3) 정산 (종합 결과 필터)
    settlement = {}
    if SETTLEMENT_JSON.exists():
        try:
            settlement = json.loads(SETTLEMENT_JSON.read_text(encoding="utf-8-sig"))
        except Exception as e:
            log(f"[WARN] settlement.json 읽기 실패: {e}")
    settlement_f = settlement if no_filter else filter_settlement(settlement, yk_set)
    settle_month = args.month or settlement.get("settlement_month") or datetime.now().strftime("%Y-%m")

    # 4) 월별 스냅샷 (종합 history 월 ∪ 정산 월)
    months = sorted({p.stem for p in MASTER_HISTORY_DIR.glob("*.json")} | {settle_month})
    hist_dir.mkdir(parents=True, exist_ok=True)
    for stale in hist_dir.glob("*.json"):
        if stale.stem not in months:
            stale.unlink()
    revenue_by_month: dict = {}
    for m in months:
        snap, rev = build_month_snapshot(m, config, inf, mail_merged, name_filter, yk_set, no_filter)
        revenue_by_month[m] = rev
        (hist_dir / f"{m}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[INFO] history {len(months)}개월 저장: {months[0]}~{months[-1]}")

    # 5) build_kpi 재사용 (yk 디렉터리로 바꿔서)
    BK.HISTORY_DIR = hist_dir
    BK.INF_DIR     = inf_dir
    inf_dir.mkdir(parents=True, exist_ok=True)
    for stale in inf_dir.glob("*.json"):
        stale.unlink()
    BK.build_influencer_files(settlement_f, per_influencer)
    now = datetime.now()
    current_month = now.strftime("%Y-%m")
    trends             = BK.load_history()
    settlement_summary = BK.build_settlement_summary(settlement_f, per_influencer, current_month)
    profit_analysis    = BK.build_profit_analysis(per_influencer)

    # 6) 제품 메타 (올리브 등 비핵심 제품은 ㅇ 매출 0이면 숨김)
    meta = BK.load_product_meta()
    bpm = trends.get("by_product_by_month", {})
    sold = {k for md in bpm.values() for k, d in md.items() if (d.get("qty") or 0) > 0 or (d.get("gross_revenue") or 0) > 0}
    products = [p for p in meta.get("products", []) if p.get("default") or p["key"] in ALWAYS_PRODUCTS or p["key"] in sold]

    # 7) 퍼널·요약
    mail_funnel = funnel_dict(mail_merged, exp_total=inf.get("exp_total", 0), ad_total=inf.get("ad_total", 0))
    mail_funnel_by_product = {}
    for product, r in mail_by_product.items():
        d = funnel_dict(r)
        d["by_month"] = r.get("by_month", {})
        d["source_file"] = r.get("source_file")
        mail_funnel_by_product[product] = d

    influencer_products = resolve_products(sorted(yk_set), inf_all.get("product_by_name", {}),
                                           raw_products_by_name(config))
    cur_bp = bpm.get(settle_month, {})
    ops_by_product = {}
    for product, r in mail_by_product.items():
        pdm = cur_bp.get(product, {})
        ops_by_product[product] = {
            "sent":          r.get("total_sent", 0),
            "replied":       r.get("replied", 0),
            "meeting":       r.get("meeting_total", 0),
            "exp":           r.get("exp_total_approx", 0),
            "ad":            r.get("ad_total", 0),
            "qty":           pdm.get("qty", 0),
            "order_count":   pdm.get("order_count", 0),
            "gross_revenue": pdm.get("gross_revenue", 0),
            "influencers":   sum(1 for v in influencer_products.values() if v == product),
            "source_file":   r.get("source_file"),
        }
    unassigned = sorted(n for n, v in influencer_products.items() if v == UNASSIGNED)
    ops_summary = {
        "month":         settle_month,
        "managed_count": len(yk_set),
        "total_sent":    mail_funnel["total_sent"],
        "replied":       mail_funnel["replied"],
        "reply_rate":    mail_funnel["reply_rate"],
        "meeting_total": mail_funnel["meeting_total"],
        "exp_total":     mail_funnel["exp_total"],
        "ad_total":      mail_funnel["ad_total"],
        "by_product":    ops_by_product,
        "influencer_products": influencer_products,
        "unassigned":    unassigned,
    }

    revenue = revenue_by_month.get(settle_month) or {
        "order_count": 0, "unit_count": 0, "gross_revenue": 0, "influencer_cost": 0, "sponsor_cost": 0,
        "cogs_cost": 0, "labor_cost": 0, "labor_qty": 0, "labor_basis": "none", "net_profit": 0, "operating_profit": 0}

    dashboard = {
        "generated_at":          now.isoformat(timespec="seconds"),
        "current_month":         current_month,
        "owner":                 "영끌러님",
        "filter_mode":           "all" if no_filter else "owner",
        "products":              products,
        "stores":                meta.get("stores", {}),
        "revenue":               revenue,
        "mail_funnel":           mail_funnel,
        "mail_funnel_by_product": mail_funnel_by_product,
        "inf_status":            inf.get("inf_status", {}),
        "settlement_month":      int(settle_month.split("-")[1]),
        "settlement_summary":    settlement_summary,
        "trends":                trends,
        "mail_funnel_by_month":  mail_merged.get("by_month", {}),
        "ad_by_month":           inf.get("ad_by_month", {}),
        "ad_inf_count_by_month": {},
        "profit_analysis":       profit_analysis,
        "cosmetics_breakdown":   BS.aggregate_cosmetics_breakdown(None, name_filter=name_filter),
        "product_trials":        BS.aggregate_product_trials(None, name_filter=name_filter),
        "manual_sales":          BS.manual_sales_for(config) if no_filter else [],
        "alerts":                {"unregistered_influencers": [], "product_unassigned": unassigned},
        "ops_summary":           ops_summary,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "dashboard.json"
    out_path.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[INFO] dashboard.json 저장: {out_path}")
    log(f"[INFO] 담당 {len(yk_set)}명 │ 발송 {mail_funnel['total_sent']} → 회신 {mail_funnel['replied']}"
        f"({mail_funnel['reply_rate']*100:.1f}%) → 미팅 {mail_funnel['meeting_total']} → 체험 {mail_funnel['exp_total']}"
        f" → 광고 {mail_funnel['ad_total']} │ {settle_month} 매출 {revenue['gross_revenue']:,}원")
    if unassigned:
        log(f"[WARN] 제품 미지정 {len(unassigned)}명: {', '.join(unassigned)} — 종합 관리시트 `제품` 행에 입력 필요")


if __name__ == "__main__":
    main()
