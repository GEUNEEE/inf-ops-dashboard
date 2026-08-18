#!/usr/bin/env python3
# run_pipeline.py — STEP 3~9 전체 파이프라인 실행
# 사용법: python run_pipeline.py <암호화_xlsx_경로> [--month YYYY-MM]
import sys
import json
import subprocess
import tempfile
import shutil
import hashlib
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
DOWNLOADS_DIR = Path.home() / "Downloads"
ENV_PYTHONUTF8 = {"PYTHONUTF8": "1", **os.environ}

# 주문 파일 패턴: 주문조회(구) + 발주발송관리(신) + 전체주문배송현황 + 자사몰 zip
ORDER_PATTERNS = ("스마트스토어_주문조회_*.xlsx", "스마트스토어_*발주발송관리_*.xlsx",
                  "스마트스토어_*주문배송현황_*.xlsx", "calix9k_*.zip")


def find_latest_order_file() -> Path | None:
    """주문조회/발주발송관리 파일을 스케줄→input→Downloads 순으로 탐색,
    가장 최근 수정된 파일 반환 (발주발송관리 형식·Downloads 폴더도 인식)."""
    candidates = []
    for folder in (SCHEDULE_DIR, INPUT_DIR, DOWNLOADS_DIR):
        if not folder.exists():
            continue
        for pat in ORDER_PATTERNS:
            candidates.extend(folder.glob(pat))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _content_sig(p: Path) -> str:
    """파일 내용 해시(경로·이름 무관 동일 파일 판별용)."""
    h = hashlib.sha1()
    try:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        # 읽기 실패 시 (이름, 크기)로 대체 시그니처
        return f"nohash:{p.name}:{p.stat().st_size}"


def find_all_order_files() -> tuple[list[Path], list[Path]]:
    """3개 폴더(스케줄→input→Downloads)의 모든 주문 파일을 수집.
    내용이 동일한 중복 파일은 우선순위 높은 폴더의 1개만 남기고 제외.
    반환: (처리할 고유 파일[mtime 오름차순], 제외된 중복 사본)."""
    all_files = []
    for folder in (SCHEDULE_DIR, INPUT_DIR, DOWNLOADS_DIR):
        if not folder.exists():
            continue
        for pat in ORDER_PATTERNS:
            all_files.extend(folder.glob(pat))

    # all_files는 폴더 우선순위 순으로 쌓이므로, 먼저 본 사본(=상위 폴더)을 유지
    unique, dups, seen = [], [], set()
    for p in all_files:
        sig = _content_sig(p)
        if sig in seen:
            dups.append(p)
        else:
            seen.add(sig)
            unique.append(p)
    unique.sort(key=lambda p: p.stat().st_mtime)
    return unique, dups


def parse_cli(argv: list):
    """positional 파일 경로 + 플래그(--month/--store/--latest/--all/--rebuild/--images) 분리."""
    files, month, store, use_latest = [], datetime.now().strftime("%Y-%m"), None, False
    rebuild, images = False, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--month" and i + 1 < len(argv):
            month = argv[i + 1]; i += 2; continue
        if a == "--store" and i + 1 < len(argv):
            store = argv[i + 1].strip().upper(); i += 2; continue
        if a == "--latest":
            use_latest = True
        elif a in ("--all", "--batch"):
            use_latest = False  # 전체 수집(기본값) — 명시용, --batch는 하위호환 별칭
        elif a == "--rebuild":
            rebuild = True  # 주문 파일이 하나도 없어도 Raw_Data 기준으로 재빌드 진행
        elif a == "--images":
            images = True  # STEP 5 완료 후 정산서 xlsx → PNG 이미지까지 내보내기 (월말 전용)
        elif not a.startswith("--"):
            files.append(Path(a))
        i += 1
    return files, month, store, use_latest, rebuild, images


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
        print("사용법: python run_pipeline.py <xlsx...> | --all | --latest  [--month YYYY-MM] [--store A|B] [--rebuild] [--images]", file=sys.stderr)
        sys.exit(1)

    files, target_month, file_store, use_latest, rebuild, images = parse_cli(sys.argv[1:])

    # 처리할 주문 파일 목록 결정
    dup_files = []
    if files:
        order_files = files
    elif use_latest:  # --latest: mtime 최신 1개만
        latest = find_latest_order_file()
        order_files = [latest] if latest else []
        if latest:
            print(f"[INFO] 최신 주문 파일 1개 선택: {latest.name}", file=sys.stderr)
    else:  # 기본값(--all): 전체 폴더 수집 + 내용 중복 제외
        order_files, dup_files = find_all_order_files()
        print(f"[INFO] 전체 주문 파일 수집: {len(order_files)}개 처리 / 중복 {len(dup_files)}개 제외", file=sys.stderr)
        for d in dup_files:
            print(f"  · 중복 제외: {d.parent.name}/{d.name}", file=sys.stderr)

    if not order_files:
        if not rebuild:
            print("[ERROR] 처리할 주문 파일이 없습니다 (스케줄/input/Downloads). "
                  "신규 파일 없이 Raw_Data 기준으로만 재빌드하려면 --rebuild를 추가하세요.", file=sys.stderr)
            sys.exit(1)
        print("[INFO] 주문 파일 없음 — --rebuild 지정됨, Raw_Data 기준으로 재빌드 진행", file=sys.stderr)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"파이프라인 시작: {len(order_files)}개 파일 / 정산월: {target_month}", file=sys.stderr)
    for f in order_files:
        print(f"  • {f.name}", file=sys.stderr)
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

    # STEP 3-4 — 복호화 + 버킷 분류 + Raw_Data 반영 (여러 파일 순차 처리, 중복 자동 제외)
    print(f"[STEP 3-4] 주문 파싱 + 버킷 분류 ({len(order_files)}개 파일)...", file=sys.stderr)
    merged = {"new_count": 0, "settlement": [], "general": [], "excluded": [],
              "other_product": [], "unregistered": [], "cancelled_by_ytber": {}}
    for of in order_files:
        if of.suffix.lower() == ".zip":
            # 자사몰(spoteasy) zip — 화장품 전용, 채널=자사몰
            bd = run_script(SKILLS_DIR / "excel-parser" / "scripts" / "parse_mall_order.py", str(of))
        else:
            po_args = [str(of), managed_set]
            if file_store:
                po_args += ["--store", file_store]
            bd = run_script(SKILLS_DIR / "excel-parser" / "scripts" / "parse_order.py", *po_args)
        n = bd.get("new_count", 0)
        merged["new_count"] += n
        for k in ("settlement", "general", "excluded", "other_product"):
            merged[k].extend(bd.get(k, []))
        merged["unregistered"].extend(bd.get("unregistered", []))
        for y, lst in bd.get("cancelled_by_ytber", {}).items():
            merged["cancelled_by_ytber"].setdefault(y, []).extend(lst)
        print(f"  - {of.name}: 신규 {n}건", file=sys.stderr)

    bucket_json = save_temp_json(merged, "bucket.json")
    new_count = merged["new_count"]
    if new_count == 0:
        print("[INFO] 신규 주문 0건 — Raw_Data 기준으로 정산·대시보드 재빌드", file=sys.stderr)
    else:
        print(f"[INFO] 신규 주문 총 {new_count}건 처리 계속", file=sys.stderr)

    # STEP 5 — 정산서 생성
    print("[STEP 5] 정산서 생성...", file=sys.stderr)
    settlement_data = run_script(
        SKILLS_DIR / "settlement-generator" / "scripts" / "generate_sheets.py",
        str(bucket_json), target_month
    )
    settlement_json = save_temp_json(settlement_data, "settlement.json")

    # STEP 5.5 — 정산서 PNG 이미지 내보내기 (--images 지정 시, 월말 전용)
    if images:
        print("[STEP 5.5] 정산서 이미지 내보내기...", file=sys.stderr)
        settlement_xlsx = SCHEDULE_DIR / f"유튜버별 월정산시트 작성 {target_month}_송부용.xlsx"
        try:
            img_result = subprocess.run(
                [PYTHON_EXE,
                 str(SKILLS_DIR / "settlement-generator" / "scripts" / "export_images.py"),
                 str(settlement_xlsx)],
                capture_output=True, text=True, encoding="utf-8", env=ENV_PYTHONUTF8
            )
            if img_result.stderr:
                print(img_result.stderr, file=sys.stderr)
            if img_result.returncode != 0:
                print(f"[WARN] 이미지 내보내기 실패: {img_result.stderr[-300:]}", file=sys.stderr)
            else:
                img_data = json.loads(img_result.stdout)
                print(f"[INFO] 이미지 {img_data.get('count', 0)}개 저장 완료", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] 이미지 내보내기 실패: {e}", file=sys.stderr)

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
             str(revenue_json), str(bucket_json), str(settlement_json), target_month],
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

    # 처리 완료된 주문 파일 + 제외된 중복 사본 → 주문조회 old 폴더로 정리
    old_dir = SCHEDULE_DIR / "주문조회 old"
    old_dir.mkdir(exist_ok=True)
    for of in order_files + dup_files:
        dest = old_dir / of.name
        if of.resolve() == dest.resolve():
            continue
        try:
            if dest.exists():
                # 동일 이름이 이미 old에 존재(중복 사본) → 원본 삭제
                of.unlink()
                print(f"[INFO] 중복 사본 제거: {of.parent.name}/{of.name}", file=sys.stderr)
            else:
                shutil.move(str(of), str(dest))
                print(f"[INFO] 주문 파일 이동: {of.name} → 주문조회 old/", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] 파일 정리 실패({of.name}): {e}", file=sys.stderr)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"파이프라인 완료: 신규 {new_count}건 처리", file=sys.stderr)
    print(f"매출: ₩{revenue_data.get('gross_revenue', 0):,} / 수익: ₩{revenue_data.get('net_profit', 0):,}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
