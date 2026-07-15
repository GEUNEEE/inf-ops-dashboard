# -*- coding: utf-8 -*-
"""
볼타 전자세금계산서 발행 메인 스크립트.

금액 소스 두 가지를 모두 지원한다:
  1) 정산DB 자동  : --month YYYY-MM  -> site/data/history/YYYY-MM.json 의
                     influencers[name].amount(공급가액) 사용
  2) 수동 입력    : --recipient "코앞의경제" --amount 600000

VAT 10%를 자동 계산해 세금계산서로 발행한다 (공급가 + 세액).
기본은 test 키. 실제 발행은 --live 플래그 필요.

사용 예:
  # 미리보기(dry-run): 이번 달 정산 대상 전체
  python issue_invoice.py --month 2026-06 --dry-run

  # 특정 인플루언서 1건, 금액 수동
  python issue_invoice.py --recipient 코앞의경제 --amount 600000 --dry-run

  # 실제 발행 (test)
  python issue_invoice.py --month 2026-06 --recipient 코앞의경제

  # 라이브 발행
  python issue_invoice.py --month 2026-06 --recipient 코앞의경제 --live
"""
import argparse
import datetime as _dt
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bolta_client import BoltaClient, BoltaError, load_client  # noqa: E402

def _ensure_utf8_stdio():
    """stdout/stderr를 UTF-8로 1회만 재설정 (중복 import 시 닫힘 충돌 방지)."""
    if getattr(_ensure_utf8_stdio, "_done", False):
        return
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    else:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    _ensure_utf8_stdio._done = True


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
VAT_RATE = 0.10


# ── 설정/데이터 로드 ──────────────────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_supplier():
    cfg = load_json(os.path.join(SCRIPT_DIR, "supplier_config.json"))
    missing = [k for k in ("identificationNumber", "organizationName",
                           "representativeName") if not cfg.get(k)]
    if missing:
        raise SystemExit(
            f"[중단] supplier_config.json 미완성 필드: {missing}\n"
            f"       output의 사업자등록증 정보로 채운 뒤 다시 실행하세요."
        )
    if not cfg.get("supplierKey"):
        raise SystemExit(
            "[중단] supplier_config.json의 supplierKey가 비어 있습니다.\n"
            "       먼저 공급자 등록(--register-supplier)을 1회 실행하세요."
        )
    email = (cfg.get("manager") or {}).get("email", "")
    if not email or "TODO" in email or "example.com" in email:
        raise SystemExit(
            "[중단] supplier_config.json의 manager.email이 placeholder입니다.\n"
            "       세금계산서 발급 알림을 받을 우리쪽 담당자 이메일로 교체하세요."
        )
    return cfg


def load_recipients():
    data = load_json(os.path.join(SCRIPT_DIR, "recipients.json"))
    return data.get("recipients", {})


def normalize_name(name):
    """ytber_config.json의 name_map으로 유튜버명 정규화."""
    cfg_path = os.path.join(
        PROJECT_ROOT, ".claude", "skills", "settlement-generator",
        "scripts", "ytber_config.json")
    try:
        name_map = load_json(cfg_path).get("name_map", {})
    except FileNotFoundError:
        name_map = {}
    return name_map.get(name, name)


# ── 금액 소스 ─────────────────────────────────────────────
def amounts_from_month(month):
    """site/data/history/YYYY-MM.json 에서 인플루언서별 공급가액(amount) 추출."""
    path = os.path.join(PROJECT_ROOT, "site", "data", "history", f"{month}.json")
    if not os.path.exists(path):
        raise SystemExit(f"[중단] 월별 정산 스냅샷이 없습니다: {path}")
    snap = load_json(path)
    out = {}
    for name, info in snap.get("influencers", {}).items():
        if info.get("is_general"):
            continue  # 기타/일반은 계산서 발행 대상 아님
        amount = info.get("amount") or 0
        if amount > 0:
            out[normalize_name(name)] = int(amount)
    return out


# ── 페이로드 구성 ─────────────────────────────────────────
def build_payload(supplier, recipient, supply_cost, month, item_date=None,
                  item_name=None):
    """세금계산서 정발행 payload 구성. supply_cost = 공급가액."""
    tax = round(supply_cost * VAT_RATE)
    today = _dt.date.today().isoformat()
    item_date = item_date or today
    item_name = item_name or supplier.get(
        "default_item_name", "인플루언서 광고 협찬")
    desc = f"{month} 인플루언서 협찬 정산" if month else None

    return {
        "date": today,
        "purpose": supplier.get("default_purpose", "CLAIM"),
        "supplier": {
            "identificationNumber": supplier["identificationNumber"],
            "taxRegistrationId": supplier.get("taxRegistrationId"),
            "organizationName": supplier["organizationName"],
            "representativeName": supplier["representativeName"],
            "address": supplier.get("address"),
            "businessItem": supplier.get("businessItem"),
            "businessType": supplier.get("businessType"),
            "manager": {
                "email": supplier["manager"]["email"],
                "name": supplier["manager"].get("name"),
                "telephone": supplier["manager"].get("telephone"),
            },
        },
        "supplied": {
            "identificationNumber": recipient["identificationNumber"],
            "taxRegistrationId": recipient.get("taxRegistrationId"),
            "organizationName": recipient["organizationName"],
            "representativeName": recipient["representativeName"],
            "address": recipient.get("address"),
            "businessItem": recipient.get("businessItem"),
            "businessType": recipient.get("businessType"),
            "managers": recipient["managers"],
        },
        "items": [{
            "date": item_date,
            "name": item_name,
            "unitPrice": None,
            "quantity": None,
            "supplyCost": supply_cost,
            "tax": tax,
            "specification": None,
            "description": None,
        }],
        "description": desc,
    }


def validate_recipient(name, rec):
    errs = []
    idn = (rec.get("identificationNumber") or "").replace("-", "")
    if not idn or not idn.isdigit() or len(idn) not in (10, 13):
        errs.append("식별번호(사업자 10자리 또는 주민 13자리) 누락/형식오류")
    if not rec.get("organizationName"):
        errs.append("상호명 누락")
    if not rec.get("representativeName"):
        errs.append("대표자명 누락")
    mgrs = rec.get("managers") or []
    email = (mgrs[0].get("email") or "").strip() if mgrs else ""
    if not email:
        errs.append("담당자 이메일 누락 (필수)")
    elif "TODO" in email or "example.com" in email:
        errs.append("담당자 이메일이 placeholder (실제 이메일로 교체 필요)")
    return errs


# ── 메인 ──────────────────────────────────────────────────
def cmd_register_supplier(args):
    cfg = load_json(os.path.join(SCRIPT_DIR, "supplier_config.json"))
    missing = [k for k in ("identificationNumber", "organizationName",
                           "representativeName") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"[중단] supplier_config.json 미완성 필드: {missing}")
    env_label = "LIVE" if args.live else "TEST"
    print(f"=== 공급자 등록 [{env_label}] ===")
    try:
        client = load_client(use_live=args.live)
    except ValueError as e:
        raise SystemExit(f"[중단] {e}")
    try:
        resp = client.register_supplier(
            cfg["identificationNumber"], cfg["organizationName"],
            cfg["representativeName"], cfg.get("taxRegistrationId"))
    except BoltaError as e:
        raise SystemExit(f"[중단] 공급자 등록 실패 [{e.status}] {e.code}: {e.message}")
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    key = resp.get("supplierKey")
    if key:
        print(f"\n>> supplierKey: {key}")
        print(">> 이 값을 supplier_config.json의 \"supplierKey\"에 저장하면 발행 준비 완료.")


def main():
    _ensure_utf8_stdio()
    ap = argparse.ArgumentParser(description="볼타 전자세금계산서 발행")
    ap.add_argument("--month", help="정산월 YYYY-MM (정산DB 자동 금액)")
    ap.add_argument("--recipient", help="특정 유튜버명만 발행")
    ap.add_argument("--amount", type=int, help="공급가액 수동 지정 (--recipient와 함께)")
    ap.add_argument("--live", action="store_true", help="라이브 발행 (기본 test)")
    ap.add_argument("--dry-run", action="store_true", help="발행하지 않고 payload만 출력")
    ap.add_argument("--register-supplier", action="store_true",
                    help="공급자 등록 1회 실행 (supplierKey 발급)")
    args = ap.parse_args()

    if args.register_supplier:
        return cmd_register_supplier(args)

    # 발행 대상 = {정규화이름: 공급가액}
    targets = {}
    if args.recipient and args.amount is not None:
        targets[normalize_name(args.recipient)] = args.amount
    elif args.month:
        targets = amounts_from_month(args.month)
        if args.recipient:
            n = normalize_name(args.recipient)
            targets = {n: targets[n]} if n in targets else {}
            if not targets:
                raise SystemExit(f"[중단] {args.recipient}의 {args.month} 정산 금액이 없습니다.")
    else:
        raise SystemExit("[중단] --month 또는 (--recipient + --amount)가 필요합니다.")

    if not targets:
        raise SystemExit("[중단] 발행 대상이 없습니다.")

    supplier = load_supplier() if not args.dry_run else _supplier_for_dryrun()
    recipients = load_recipients()

    env_label = "LIVE" if args.live else "TEST"
    print(f"=== 볼타 계산서 발행 [{env_label}]{' (DRY-RUN)' if args.dry_run else ''} ===")

    results = []
    client = None
    if not args.dry_run:
        try:
            client = load_client(use_live=args.live,
                                 supplier_key=supplier["supplierKey"])
        except ValueError as e:
            raise SystemExit(f"[중단] {e}")

    for name, supply_cost in targets.items():
        rec = recipients.get(name)
        if not rec:
            print(f"[스킵] {name}: recipients.json에 사업자정보 없음 → 사업자등록증 필요")
            results.append({"name": name, "status": "no_recipient_info"})
            continue
        errs = validate_recipient(name, rec)
        if errs:
            print(f"[스킵] {name}: {', '.join(errs)}")
            results.append({"name": name, "status": "invalid", "errors": errs})
            continue

        tax = round(supply_cost * VAT_RATE)
        payload = build_payload(supplier, rec, supply_cost, args.month)
        print(f"\n- {name}: 공급가 {supply_cost:,} + 세액 {tax:,} = {supply_cost+tax:,}원")

        if args.dry_run:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            results.append({"name": name, "status": "dry_run",
                           "supplyCost": supply_cost, "tax": tax})
            continue

        ref = f"inv-{args.month or 'manual'}-{name}-{supply_cost}"
        try:
            resp = client.issue_tax_invoice(payload, reference_id=ref)
            key = resp.get("issuanceKey")
            print(f"  ✅ 발행 완료 issuanceKey={key}")
            results.append({"name": name, "status": "issued",
                           "issuanceKey": key, "supplyCost": supply_cost, "tax": tax})
        except BoltaError as e:
            print(f"  ❌ 발행 실패 [{e.status}] {e.code}: {e.message}")
            results.append({"name": name, "status": "error",
                           "code": e.code, "message": e.message})

    if not args.dry_run:
        _write_log(args, env_label, results)

    print("\n=== 요약 ===")
    for r in results:
        print(f"  {r['name']}: {r['status']}")


def _supplier_for_dryrun():
    """dry-run은 supplierKey 없이도 미리보기 가능하도록 부분 검증만."""
    cfg = load_json(os.path.join(SCRIPT_DIR, "supplier_config.json"))
    return cfg


def _write_log(args, env_label, results):
    out_dir = os.path.join(PROJECT_ROOT, "output", "invoices")
    os.makedirs(out_dir, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = args.month or "manual"
    path = os.path.join(out_dir, f"{tag}_발행로그_{env_label}_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"env": env_label, "month": args.month,
                   "generated_at": _dt.datetime.now().isoformat(),
                   "results": results}, f, ensure_ascii=False, indent=2)
    print(f"\n로그 저장: {path}")


if __name__ == "__main__":
    main()
