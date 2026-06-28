#!/usr/bin/env python3
# notify.py — STEP 8: 카카오톡 메모챗 알림 메시지 생성 (제품별 매출·수익 포함)
# 실제 MCP 호출은 Claude Code 에이전트가 담당. 이 스크립트는 메시지 텍스트를 stdout으로 출력.
# 사용법: python notify.py <revenue_json> <bucket_json> <settlement_json> [YYYY-MM]
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
CONFIG_PATH = BASE_DIR / ".claude" / "skills" / "settlement-generator" / "scripts" / "ytber_config.json"
SITE_URL    = "geuneee.github.io/inf-ops-dashboard/"

ICONS = {"흑염소": "🐐", "화장품": "💄", "올리브오일캡슐": "🫒", "수면영양제": "😴"}
SHORT = {"올리브오일캡슐": "올리브"}   # 카톡 표기용 짧은 이름


def _load(p) -> dict:
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def main():
    if len(sys.argv) < 4:
        print("사용법: python notify.py <revenue_json> <bucket_json> <settlement_json> [YYYY-MM]", file=sys.stderr)
        sys.exit(1)

    revenue    = _load(sys.argv[1])
    bucket     = _load(sys.argv[2])
    settlement = _load(sys.argv[3])
    month  = sys.argv[4] if len(sys.argv) > 4 else datetime.now().strftime("%Y-%m")
    mlabel = int(month[5:7])

    # 설정: 기본 제품(흑염소) + 제품 표시 순서
    default_product, product_order = "흑염소", []
    try:
        cfg = _load(CONFIG_PATH)
        default_product = cfg.get("product_registry", {}).get("default_product", "흑염소")
        product_order   = [p["key"] for p in cfg.get("products", [])]
    except Exception:
        pass

    # 월별 스냅샷에서 제품별 매출·수익 (흑염소 수익은 top-level net_profit)
    by_product, goat_profit = {}, 0
    snap_path = HISTORY_DIR / f"{month}.json"
    if snap_path.exists():
        try:
            snap = json.loads(snap_path.read_text(encoding="utf-8"))
            by_product  = snap.get("by_product", {})
            goat_profit = snap.get("net_profit", 0)
        except Exception:
            pass

    new_count    = bucket.get("new_count", 0)
    unregistered = bucket.get("unregistered", [])

    # 합계 + 제품별 행
    prod_rows = []
    if by_product:
        total_rev    = sum(v.get("gross_revenue", 0) for v in by_product.values())
        total_profit = goat_profit + sum(v.get("net_profit", 0) for k, v in by_product.items() if k != default_product)
        ordered = product_order + [k for k in by_product if k not in product_order]
        for k in ordered:
            v = by_product.get(k)
            if not v or not v.get("gross_revenue"):
                continue
            prof = goat_profit if k == default_product else v.get("net_profit", 0)
            prod_rows.append((SHORT.get(k, k), ICONS.get(k, "📦"), v["gross_revenue"], prof))
    else:
        total_rev    = revenue.get("gross_revenue", 0)
        total_profit = revenue.get("net_profit", 0)

    # 메시지 (FULL → 200자 초과 시 단계적 압축)
    head = []
    if new_count:
        head.append(f"📦 {mlabel}월 신규 {new_count}건 처리")
    head.append(f"📊 {mlabel}월 매출 ₩{total_rev:,} / 수익 ₩{total_profit:,}")
    link = f"🔗 {SITE_URL}"

    full = head + [f"{ic}{nm} ₩{rev:,} (수익 {pf:,})" for nm, ic, rev, pf in prod_rows] + [link]
    msg = "\n".join(full)
    if len(msg) > 200:
        # 1차 압축: 제품별 매출만 한 줄에 모음
        prod_line = "  ".join(f"{ic}{nm} ₩{rev:,}" for nm, ic, rev, pf in prod_rows)
        msg = "\n".join(head + ([prod_line] if prod_line else []) + [link])
        if len(msg) > 200:
            # 2차 압축: 합계만
            msg = "\n".join(head + [link])

    print(msg)

    # 미등재 즉시 알림 (별도 메시지)
    if unregistered:
        unreg = {}
        for u in unregistered:
            n = u["name"]
            unreg.setdefault(n, {"건수": 0, "수량": 0})
            unreg[n]["건수"] += 1
            unreg[n]["수량"] += u.get("qty", 0)
        lines2 = ["⚠️ [즉시 확인] 관리탭 미등재 인플루언서"]
        for n, d in unreg.items():
            lines2.append(f"• {n} — {d['건수']}건, {d['수량']}개")
        lines2.append("인플루언서관리 시트에 추가하거나 제외 목록에 등록해 주세요.")
        print("\n--- 미등재 즉시 알림 ---\n" + "\n".join(lines2))


if __name__ == "__main__":
    main()
