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

BASE_DIR      = Path(r"C:\Users\user\비서")
PYTHON_EXE    = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
SKILLS_DIR    = BASE_DIR / ".claude" / "skills"
OUTPUT_DIR    = BASE_DIR / "output"
SCHEDULE_DIR  = BASE_DIR / "스케줄"
INPUT_DIR     = BASE_DIR / "input"
ENV_PYTHONUTF8 = {"PYTHONUTF8": "1", **os.environ}


def find_latest_order_file() -> Path | None:
    """스케줄 폴더(우선) → input 폴더 순으로 최신 스마트스토어 주문조회 파일 반환"""
    candidates = []
    for folder in (SCHEDULE_DIR, INPUT_DIR):
        candidates.extend(folder.glob("스마트스토어_주문조회_*.xlsx"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stem)


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
        print("사용법: python run_pipeline.py <암호화_xlsx|--latest> [--month YYYY-MM]", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--latest":
        xlsx_path = find_latest_order_file()
        if xlsx_path is None:
            print("[ERROR] 스케줄/input 폴더에 주문조회 파일이 없습니다.", file=sys.stderr)
            sys.exit(1)
        print(f"[INFO] 최신 주문 파일 자동 선택: {xlsx_path}", file=sys.stderr)
    else:
        xlsx_path = Path(sys.argv[1])
    target_month = datetime.now().strftime("%Y-%m")
    if "--month" in sys.argv:
        idx = sys.argv.index("--month")
        if idx + 1 < len(sys.argv):
            target_month = sys.argv[idx + 1]

    # --store A|B : 이 주문 파일의 스토어(슬립케어랩=B, 초방리농장=A)
    file_store = None
    if "--store" in sys.argv:
        idx = sys.argv.index("--store")
        if idx + 1 < len(sys.argv):
            file_store = sys.argv[idx + 1].strip().upper()

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
    parse_order_args = [str(xlsx_path), managed_set]
    if file_store:
        parse_order_args += ["--store", file_store]
    bucket_data = run_script(
        SKILLS_DIR / "excel-parser" / "scripts" / "parse_order.py",
        *parse_order_args
    )
    bucket_json = save_temp_json(bucket_data, "bucket.json")

    new_count = bucket_data.get("new_count", 0)
    if new_count == 0:
        print("[INFO] 신규 주문 0건 — Raw_Data 기준으로 정산·대시보드 재빌드", file=sys.stderr)
    else:
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
        str(bucket_json), str(settlement_json), str(inf_json), target_month
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

    # 카카오톡 알림 메시지 생성 → 파일 저장 (MCP 호출은 Claude 에이전트가 담당)
    print("[NOTIFY] 카카오톡 메시지 생성...", file=sys.stderr)
    try:
        kakao_result = subprocess.run(
            [PYTHON_EXE,
             str(SKILLS_DIR / "kakao-notifier" / "scripts" / "notify.py"),
             str(revenue_json), str(bucket_json), str(settlement_json)],
            capture_output=True, text=True, encoding="utf-8", env=ENV_PYTHONUTF8
        )
        if kakao_result.returncode == 0 and kakao_result.stdout.strip():
            pending_path = OUTPUT_DIR / "tmp" / "kakao_pending.txt"
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.write_text(kakao_result.stdout.strip(), encoding="utf-8")
            print(f"[NOTIFY] 메시지 저장: {pending_path}", file=sys.stderr)
        else:
            print(f"[WARN] notify.py 실패: {kakao_result.stderr[-300:]}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] 카카오톡 메시지 생성 실패: {e}", file=sys.stderr)

    # STEP 10 — 데이터 검증
    print("[STEP 10] 데이터 정합성 검증...", file=sys.stderr)
    verify_script = BASE_DIR / "스케줄" / "verify_data.py"
    if verify_script.exists():
        verify_result = subprocess.run(
            [PYTHON_EXE, str(verify_script)],
            capture_output=True, text=True, encoding="utf-8", env=ENV_PYTHONUTF8
        )
        print(verify_result.stdout, file=sys.stderr)
        if verify_result.returncode != 0 or "❌" in verify_result.stdout:
            print("[WARN] 검증 오류 발견 — 위 결과를 확인하세요.", file=sys.stderr)
        else:
            print("[INFO] 검증 통과 ✅", file=sys.stderr)
    else:
        print("[WARN] verify_data.py 없음 — 검증 생략", file=sys.stderr)

    # 처리 완료된 주문 파일 → 주문조회 old 폴더로 이동
    old_dir = SCHEDULE_DIR / "주문조회 old"
    old_dir.mkdir(exist_ok=True)
    dest = old_dir / xlsx_path.name
    if xlsx_path.resolve() != dest.resolve():
        try:
            shutil.move(str(xlsx_path), str(dest))
            print(f"[INFO] 주문 파일 이동: {xlsx_path.name} → 주문조회 old/", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] 파일 이동 실패: {e}", file=sys.stderr)
    else:
        print(f"[INFO] 주문 파일 이미 주문조회 old/ 위치", file=sys.stderr)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"파이프라인 완료: 신규 {new_count}건 처리", file=sys.stderr)
    print(f"매출: ₩{revenue_data.get('gross_revenue', 0):,} / 수익: ₩{revenue_data.get('net_profit', 0):,}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
