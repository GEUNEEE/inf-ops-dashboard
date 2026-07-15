# -*- coding: utf-8 -*-
"""
볼타 전자세금계산서 수정발행 스크립트.

수정발행은 원본 issuanceKey가 반드시 필요하다.
원본은 output/invoices/ 발행로그에서 유튜버명(+월)으로 자동 조회한다.

수정발행 3종:
  changeSupplyCost  공급가액 변동  → --new-amount 또는 --diff (차이값)
  termination       계약의 해제    → 원본 전액 상계
  doubleIssuance    이중발급 취소  → 본문 없음, 원본 상계

기본 test. 실제 수정발행은 --live (국세청으로 실제 나감).

사용 예:
  # 원본 조회만 (어떤 issuanceKey가 잡히는지 확인)
  python amend_invoice.py --recipient 코앞의경제 --find

  # 공급가액 변동: 600,000 -> 500,000 으로 수정 (test, dry-run)
  python amend_invoice.py --recipient 코앞의경제 --type changeSupplyCost \
      --new-amount 500000 --dry-run

  # 계약 해제 (원본 전액 취소)
  python amend_invoice.py --recipient 코앞의경제 --type termination

  # 이중발급 취소
  python amend_invoice.py --recipient 코앞의경제 --type doubleIssuance

  # 원본 issuanceKey 직접 지정
  python amend_invoice.py --issuance-key ABC123... --type termination
"""
import argparse
import datetime as _dt
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bolta_client import BoltaError, load_client  # noqa: E402
import issue_invoice as ii  # noqa: E402  (load_supplier/normalize_name 재사용)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = ii.PROJECT_ROOT
INVOICE_LOG_DIR = os.path.join(PROJECT_ROOT, "output", "invoices")
VAT_RATE = 0.10
AMEND_TYPES = ("changeSupplyCost", "termination", "doubleIssuance")


# ── 발행로그 인덱스 ───────────────────────────────────────
def find_issued(recipient_name, month=None, use_live=False):
    """
    output/invoices/ 발행로그를 최신순으로 훑어 해당 유튜버의 'issued' 건을 찾는다.
    env(TEST/LIVE) 일치, 월 지정 시 월도 일치하는 가장 최근 발행건 반환.
    반환: dict {name, issuanceKey, supplyCost, tax, env, month, log_file} 또는 None
    """
    want_env = "LIVE" if use_live else "TEST"
    norm = ii.normalize_name(recipient_name)
    logs = sorted(glob.glob(os.path.join(INVOICE_LOG_DIR, "*_발행로그_*.json")),
                  reverse=True)
    for path in logs:
        try:
            data = ii.load_json(path)
        except (ValueError, OSError):
            continue
        if data.get("env") != want_env:
            continue
        if month and data.get("month") and data["month"] != month:
            continue
        for r in data.get("results", []):
            if r.get("status") != "issued":
                continue
            if ii.normalize_name(r.get("name", "")) != norm:
                continue
            return {
                "name": r["name"],
                "issuanceKey": r["issuanceKey"],
                "supplyCost": r.get("supplyCost"),
                "tax": r.get("tax"),
                "env": data.get("env"),
                "month": data.get("month"),
                "log_file": os.path.basename(path),
            }
    return None


# ── 페이로드 ──────────────────────────────────────────────
def build_change_items(orig, new_amount=None, diff=None, item_name=None):
    """공급가액 변동 items: 차이값(+/-)을 전달."""
    if diff is None:
        if new_amount is None or orig.get("supplyCost") is None:
            raise SystemExit("[중단] --new-amount 또는 --diff가 필요합니다 "
                             "(원본 공급가액을 알 수 없으면 --diff 사용).")
        diff = int(new_amount) - int(orig["supplyCost"])
    if diff == 0:
        raise SystemExit("[중단] 변동액이 0원입니다. 수정발행 불필요.")
    tax_diff = round(diff * VAT_RATE)
    today = _dt.date.today().isoformat()
    name = item_name or "흑장녹삼 인플루언서 광고 협찬 (공급가액 수정)"
    return diff, tax_diff, [{
        "date": today, "name": name,
        "unitPrice": None, "quantity": None,
        "supplyCost": diff, "tax": tax_diff,
        "specification": None, "description": "공급가액 변동 수정발행",
    }]


# ── 메인 ──────────────────────────────────────────────────
def main():
    ii._ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="볼타 세금계산서 수정발행")
    ap.add_argument("--recipient", help="유튜버명 (발행로그에서 원본 자동 조회)")
    ap.add_argument("--month", help="원본 발행 월 YYYY-MM (조회 정밀도 ↑)")
    ap.add_argument("--issuance-key", help="원본 issuanceKey 직접 지정")
    ap.add_argument("--type", choices=AMEND_TYPES, help="수정발행 유형")
    ap.add_argument("--new-amount", type=int, help="[changeSupplyCost] 변경 후 공급가액")
    ap.add_argument("--diff", type=int, help="[changeSupplyCost] 공급가액 차이값(+/-)")
    ap.add_argument("--date", help="수정발행 작성일자 (기본 오늘)")
    ap.add_argument("--live", action="store_true", help="라이브 수정발행 (기본 test)")
    ap.add_argument("--dry-run", action="store_true", help="발행 없이 미리보기")
    ap.add_argument("--find", action="store_true", help="원본 조회만 하고 종료")
    args = ap.parse_args()

    # 원본 결정
    orig = None
    issuance_key = args.issuance_key
    if not issuance_key:
        if not args.recipient:
            raise SystemExit("[중단] --recipient 또는 --issuance-key가 필요합니다.")
        orig = find_issued(args.recipient, args.month, args.live)
        if not orig:
            env = "LIVE" if args.live else "TEST"
            raise SystemExit(
                f"[중단] {args.recipient}의 발행 기록({env})을 찾을 수 없습니다.\n"
                f"       output/invoices/ 로그 확인 또는 --issuance-key 직접 지정.")
        issuance_key = orig["issuanceKey"]

    print(f"=== 원본 세금계산서 ===")
    if orig:
        print(f"  유튜버: {orig['name']}  /  월: {orig['month']}  /  로그: {orig['log_file']}")
        if orig.get("supplyCost") is not None:
            print(f"  원본 공급가: {orig['supplyCost']:,}  세액: {orig['tax']:,}")
    print(f"  issuanceKey: {issuance_key}")

    if args.find:
        return
    if not args.type:
        raise SystemExit("[중단] --type {changeSupplyCost|termination|doubleIssuance} 필요.")

    env_label = "LIVE" if args.live else "TEST"
    date = args.date or _dt.date.today().isoformat()
    print(f"\n=== 수정발행 [{env_label}] {args.type}"
          f"{' (DRY-RUN)' if args.dry_run else ''} ===")

    # 유형별 미리보기
    change_items = None
    if args.type == "changeSupplyCost":
        diff, tax_diff, change_items = build_change_items(
            orig or {}, args.new_amount, args.diff)
        sign = "+" if diff > 0 else ""
        print(f"  공급가 변동: {sign}{diff:,}  세액 변동: {sign}{tax_diff:,}")
    elif args.type == "termination":
        print(f"  계약 해제 — 원본 전액 상계 (해제일 {date})")
    else:  # doubleIssuance
        print(f"  이중발급 취소 — 원본 상계 (작성일자 원본 자동 적용)")

    if args.dry_run:
        print("\n(DRY-RUN) 실제 수정발행 안 함.")
        return

    # 발행 (test/live 모두 사용자 확인은 호출하는 에이전트/사람이 책임)
    supplier = ii.load_supplier()
    try:
        client = load_client(use_live=args.live,
                             supplier_key=supplier["supplierKey"])
    except ValueError as e:
        raise SystemExit(f"[중단] {e}")

    ref = f"amend-{args.type}-{issuance_key}"
    try:
        if args.type == "changeSupplyCost":
            resp = client.amend_change_supply_cost(
                issuance_key, date, change_items, reference_id=ref)
        elif args.type == "termination":
            resp = client.amend_termination(issuance_key, date, reference_id=ref)
        else:
            resp = client.amend_double_issuance(issuance_key, reference_id=ref)
        new_key = resp.get("issuanceKey")
        print(f"  ✅ 수정발행 완료 issuanceKey={new_key}")
        _write_log(args, env_label, issuance_key, resp)
    except BoltaError as e:
        print(f"  ❌ 수정발행 실패 [{e.status}] {e.code}: {e.message}")
        raise SystemExit(1)


def _write_log(args, env_label, orig_key, resp):
    os.makedirs(INVOICE_LOG_DIR, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(INVOICE_LOG_DIR,
                        f"{args.month or 'manual'}_수정발행_{env_label}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "env": env_label, "type": args.type,
            "original_issuanceKey": orig_key,
            "recipient": args.recipient,
            "result": resp,
            "generated_at": _dt.datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print(f"  로그 저장: {path}")


if __name__ == "__main__":
    main()
