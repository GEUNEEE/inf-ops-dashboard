#!/usr/bin/env python3
# run_pipeline.py — STEP 3~9 전체 파이프라인 실행
# 사용법: python run_pipeline.py <암호화_xlsx_경로> [--month YYYY-MM]
import sys
import json
import subprocess
import tempfile
import shutil
import os
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR   = Path(r"C:\Users\user\비서")
PYTHON_EXE = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
SKILLS_DIR = BASE_DIR / ".claude" / "skills"
OUTPUT_DIR = BASE_DIR / "output"
ENV_PYTHONUTF8 = {"PYTHONUTF8": "1", **os.environ}


def run_script(script_path, *args, input_data=None) -> dict:
    cmd = [PYTHON_EXE, str(script_path)] + list(args)
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        input=input_data, env=ENV_PYTHONUTF8
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"스크립트 실패 ({script_path.name}): {result.stderr[-500:]}")
    return json.loads(result.stdout)


def save_temp_json(data: dict, name: str) -> Path:
    p = OUTPUT_DIR / "tmp" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def main():
    if len(sys.argv) < 2:
        print("사용법: python run_pipeline.py <암호화_xlsx> [--month YYYY-MM]", file=sys.stderr)
        sys.exit(1)

    xlsx_path = Path(sys.argv[1])
    target_month = datetime.now().strftime("%Y-%m")
    if "--month" in sys.argv:
        idx = sys.argv.index("--month")
        if idx + 1 < len(sys.argv):
            target_month = sys.argv[idx + 1]

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"파이프라인 시작: {xlsx_path.name} / 정산월: {target_month}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)

    # STEP 1 — 메일발송현황 파싱
    print("[STEP 1] 메일발송현황 파싱...", file=sys.stderr)
    mail_kpi = run_script(SKILLS_DIR / "excel-parser" / "scripts" / "parse_mail.py")
    mail_json = save_temp_json(mail_kpi, "mail_kpi.json")

    # STEP 2 — 인플루언서관리 파싱
    print("[STEP 2] 인플루언서관리 파싱...", file=sys.stderr)
    inf_data = run_script(SKILLS_DIR / "excel-parser" / "scripts" / "parse_inf.py")
    inf_json = save_temp_json(inf_data, "inf.json")
    # ytber_config의 additional_managed를 managed_set에 병합
    CONFIG_PATH = SKILLS_DIR / "settlement-generator" / "scripts" / "ytber_config.json"
    try:
        ytber_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        additional = ytber_cfg.get("additional_managed", [])
    except Exception:
        additional = []
    managed_list = list(set(inf_data.get("managed_set", [])) | set(additional))
    managed_set = json.dumps(managed_list)

    # STEP 3-4 — 복호화 + 버킷 분류 + Raw_Data 반영
    print("[STEP 3-4] 주문 파싱 + 버킷 분류...", file=sys.stderr)
    bucket_data = run_script(
        SKILLS_DIR / "excel-parser" / "scripts" / "parse_order.py",
        str(xlsx_path), managed_set
    )
    bucket_json = save_temp_json(bucket_data, "bucket.json")

    new_count = bucket_data.get("new_count", 0)
    if new_count == 0:
        print("[INFO] 신규 주문 0건 — 이미 반영된 파일입니다. 파이프라인 종료.", file=sys.stderr)
        sys.exit(0)

    print(f"[INFO] 신규 주문 {new_count}건 처리 계속", file=sys.stderr)

    # STEP 5 — 정산서 생성
    print("[STEP 5] 정산서 생성...", file=sys.stderr)
    settlement_data = run_script(
        SKILLS_DIR / "settlement-generator" / "scripts" / "generate_sheets.py",
        str(bucket_json), target_month
    )
    settlement_json = save_temp_json(settlement_data, "settlement.json")

    # STEP 6 — 매출·수익 집계
    print("[STEP 6] 매출·수익 집계...", file=sys.stderr)
    revenue_data = run_script(
        SKILLS_DIR / "dashboard-builder" / "scripts" / "build_revenue.py",
        str(bucket_json), str(settlement_json)
    )
    revenue_json = save_temp_json(revenue_data, "revenue.json")

    # STEP 7 — 월별 스냅샷 저장
    print("[STEP 7] 월별 스냅샷 저장...", file=sys.stderr)
    run_script(
        SKILLS_DIR / "dashboard-builder" / "scripts" / "build_snapshot.py",
        str(revenue_json), str(mail_json), str(inf_json), str(settlement_json), target_month
    )

    # STEP 8 — KPI 집계 → dashboard.json
    print("[STEP 8] dashboard.json 빌드...", file=sys.stderr)
    run_script(
        SKILLS_DIR / "dashboard-builder" / "scripts" / "build_kpi.py",
        str(mail_json), str(inf_json), str(revenue_json), str(settlement_json)
    )

    # STEP 9 — git push (site-publisher)
    print("[STEP 9] site 동기화 (git push)...", file=sys.stderr)
    try:
        run_script(SKILLS_DIR / "site-publisher" / "scripts" / "publish.py", target_month)
    except Exception as e:
        print(f"[WARN] git push 실패 (로컬 저장은 완료): {e}", file=sys.stderr)

    # 카카오톡 알림
    print("[NOTIFY] 카카오톡 알림 전송...", file=sys.stderr)
    try:
        run_script(
            SKILLS_DIR / "kakao-notifier" / "scripts" / "notify.py",
            str(revenue_json), str(bucket_json), str(settlement_json)
        )
    except Exception as e:
        print(f"[WARN] 카카오톡 알림 실패: {e}", file=sys.stderr)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"파이프라인 완료: 신규 {new_count}건 처리", file=sys.stderr)
    print(f"매출: ₩{revenue_data.get('gross_revenue', 0):,} / 수익: ₩{revenue_data.get('net_profit', 0):,}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
