"""
데이터 교차 검증 스크립트
settlement.json / revenue.json / dashboard.json / history/*.json 간 일관성 검사
run_pipeline.py STEP 10에서 자동 호출됨
"""
import json, glob, os, openpyxl
from pathlib import Path
from collections import defaultdict

BASE = Path(r"C:\Users\user\비서")

def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)

sett  = load(BASE / "output/tmp/settlement.json")
rev   = load(BASE / "output/tmp/revenue.json")
inf   = load(BASE / "output/tmp/inf.json")
dash  = load(BASE / "site/data/dashboard.json")
cfg   = load(BASE / ".claude/skills/settlement-generator/scripts/ytber_config.json")

hist_files = sorted((BASE / "site/data/history").glob("*.json"))
history = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in hist_files}

P  = cfg["product_unit_price"]     # 120,000
G  = cfg["general_unit_price"]     # 130,000
GS = cfg["general_settlement_price"]  # 84,000
L  = cfg["labor_cost_per_unit"]    # 10,000

errors = []
warnings = []

def ok(label):   print(f"  ✅ {label}")
def err(label):  print(f"  ❌ {label}"); errors.append(label)
def warn(label): print(f"  ⚠️  {label}"); warnings.append(label)

# ── 1. settlement.json 수량·금액 수기 검증 ───────────────────────
print("\n[1] settlement.json 수량·금액 검증")
s_qty  = sum(s["qty"] for s in sett["summaries"] if not s["is_general"])
g_qty  = sum(s["qty"] for s in sett["summaries"] if s["is_general"])
s_amt  = sum(s["settlement_amount"] or 0 for s in sett["summaries"] if not s["is_general"])
gross_calc = s_qty * P + g_qty * G
inf_cost_calc = s_amt + g_qty * GS
sponsor = sum(
    40000 for v in inf.get("per_influencer", {}).values()
    if isinstance(v, dict) and sett["settlement_month"].replace("-","") and
    any(m == sett["settlement_month"] for m in v.get("exp_months", []))
)
labor = (s_qty + g_qty) * L
net_calc  = gross_calc - inf_cost_calc - sponsor
oper_calc = net_calc - labor

print(f"  settlement {s_qty}개 × ₩{P:,} + general {g_qty}개 × ₩{G:,} = ₩{gross_calc:,}")
print(f"  정산비 ₩{s_amt:,} + 기타 {g_qty}×₩{GS:,} = ₩{inf_cost_calc:,} / 협찬 ₩{sponsor:,} / 노무 ₩{labor:,}")

if gross_calc == rev["gross_revenue"]:
    ok(f"gross_revenue ✅ ₩{gross_calc:,}")
else:
    err(f"gross_revenue: 계산={gross_calc:,} vs revenue.json={rev['gross_revenue']:,}")

if net_calc == rev["net_profit"]:
    ok(f"net_profit ✅ ₩{net_calc:,}")
else:
    err(f"net_profit: 계산={net_calc:,} vs revenue.json={rev['net_profit']:,}")

if oper_calc == rev["operating_profit"]:
    ok(f"operating_profit ✅ ₩{oper_calc:,}")
else:
    err(f"operating_profit: 계산={oper_calc:,} vs revenue.json={rev['operating_profit']:,}")

# ── 2. 미등재 인플루언서 ─────────────────────────────────────────
print("\n[2] 미등재(unregistered) 인플루언서 확인")
unreg = sett.get("unregistered", [])
if unreg:
    err(f"미등재 인플루언서 발견: {[u['name'] for u in unreg]}")
else:
    ok("미등재 없음")

# ── 3. 누적 수량 → 단가 구간 경고 ──────────────────────────────────
print("\n[3] 인플루언서별 누적 수량 및 단가 구간 확인")

# 히스토리 누적 (이전 월 ground truth)
hist_cum: dict[str, int] = defaultdict(int)
current_month = sett["settlement_month"]
for month, h in sorted(history.items()):
    if month >= current_month:
        continue
    for name, v in h.get("influencers", {}).items():
        if not v.get("is_general"):
            hist_cum[name] += v.get("qty", 0)

# 현재 월 settlement.json에서 가져오기
for s in sett["summaries"]:
    if s["is_general"]:
        continue
    name = s["ytber"]
    prior = hist_cum.get(name, 0)
    this_qty = s["qty"]
    cum_total = prior + this_qty
    tier = "₩20,000" if cum_total < 30 else ("₩22,000" if cum_total < 100 else "₩25,000")
    next_tier = 30 - cum_total if cum_total < 30 else (100 - cum_total if cum_total < 100 else None)
    msg = f"{name}: 이전누적 {prior}개 + 이번 {this_qty}개 = {cum_total}개 → {tier}"
    if next_tier is not None and next_tier <= 5:
        warn(f"{msg}  ⚠️ 다음 구간까지 {next_tier}개 남음")
    else:
        ok(msg)

# ── 4. 히스토리 전월 gross 역산 검증 ─────────────────────────────
print("\n[4] 전월 history 파일 gross_revenue 역산 검증")
for month, h in sorted(history.items()):
    infs = h.get("influencers", {})
    s_q = sum(v.get("qty", 0) for v in infs.values() if not v.get("is_general"))
    g_q = sum(v.get("qty", 0) for v in infs.values() if v.get("is_general"))
    calc = s_q * P + g_q * G
    if calc == h["gross_revenue"]:
        ok(f"{month}: gross ₩{h['gross_revenue']:,} (settlement {s_q}개 + general {g_q}개) ✅")
    else:
        err(f"{month}: gross 불일치 — 계산 ₩{calc:,} vs 파일 ₩{h['gross_revenue']:,}")

# ── 5. trends vs history 정합성 ───────────────────────────────────
print("\n[5] dashboard.json trends vs history 정합성")
for month, h in sorted(history.items()):
    if month not in dash.get("trends", {}).get("months", []):
        warn(f"{month}: dashboard trends에 없음")
        continue
    idx = dash["trends"]["months"].index(month)
    for key in ("gross_revenue", "net_profit", "operating_profit"):
        t_val = dash["trends"][key][idx]
        h_val = h[key]
        if t_val == h_val:
            ok(f"{month}.{key}: ₩{t_val:,}")
        else:
            err(f"{month}.{key}: trends={t_val:,} vs history={h_val:,}")

# ── 6. dashboard.revenue vs 현재 월 snapshot ──────────────────────
print("\n[6] dashboard.revenue vs 현재월 snapshot")
snap = history.get(current_month, {})
if snap:
    dr = dash["revenue"]
    for key in ("gross_revenue", "net_profit", "operating_profit"):
        if dr[key] == snap.get(key):
            ok(f"{key}: ₩{dr[key]:,}")
        else:
            err(f"{key}: dashboard={dr[key]:,} vs snapshot={snap.get(key):,}")
else:
    warn(f"현재 월({current_month}) snapshot 없음")

# ── 결과 요약 ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
if errors:
    print(f"❌ 검증 오류 {len(errors)}건 / ⚠️  경고 {len(warnings)}건")
    for e in errors:
        print(f"  ❌ {e}")
    for w in warnings:
        print(f"  ⚠️  {w}")
else:
    print(f"✅ 전체 검증 통과 (경고 {len(warnings)}건)")
    for w in warnings:
        print(f"  ⚠️  {w}")
