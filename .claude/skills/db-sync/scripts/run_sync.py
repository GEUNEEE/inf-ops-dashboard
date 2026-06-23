# -*- coding: utf-8 -*-
"""
db-sync 오케스트레이터.
  --dir pull : 공유본 -> 로컬 (12:00 / 18:00)
  --dir push : 로컬 -> 공유본 (20:00, 인플관리만)
절차: 잠금확인 -> 델타계산 -> 안전변경 적용 -> 충돌 리포트+카톡 -> 스냅샷 갱신.
충돌은 적용하지 않고, 스냅샷에 마커를 박아 해결될 때까지 매 실행 재노출.
"""
import os, sys, json, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_core as C, sync_pull as P, sync_push as PU, sync_apply as A

CONFLICT_MARK = "<<CONFLICT_UNRESOLVED>>"
KAKAO_PENDING = r"C:\Users\user\비서\output\tmp\sync_kakao_pending.txt"   # 주문 파이프라인 kakao_pending.txt와 분리
REPORT_DIR    = r"C:\Users\user\비서\output\sync_reports"
LOG           = r"C:\Users\user\비서\output\sync_run.log"

def now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (now(), msg))
    print(msg)

def lock_exists(path):
    d, n = os.path.dirname(path), os.path.basename(path)
    return os.path.exists(os.path.join(d, "~$" + n))

def patch_snapshot_conflicts(conflicts_inf, conflicts_mail):
    """충돌 셀의 스냅샷 baseline을 마커로 덮어 다음 실행에도 재탐지되게 함."""
    snap = C.load_snapshot()
    if snap is None:
        return
    for x in conflicts_inf:
        for side in ("inf", "inf_shared"):
            snap.setdefault(side, {}).setdefault(x["key"], {})[x["label"]] = CONFLICT_MARK
    for x in conflicts_mail:
        for side in ("mail", "mail_shared"):
            snap.setdefault(side, {}).setdefault(x["key"], {})[x["label"]] = CONFLICT_MARK
    with open(C.snap_path("base"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)

def write_report(direction, delta, conf_inf, conf_mail):
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    p = os.path.join(REPORT_DIR, "conflict_%s_%s.txt" % (direction, stamp))
    lines = ["[%s] %s 동기화 충돌 — 확인 필요 (미적용)" % (now(), direction), ""]
    for x in conf_inf:
        lines.append("인플관리 | %s [%s]" % (x["name"], x["label"]))
        lines.append("   공유본: %s" % x["shared"])
        lines.append("   로컬  : %s" % x["local"])
    for x in conf_mail:
        lines.append("메일 | %s [%s] 공유='%s' 로컬='%s'" % (x["name"], x["label"], x["shared"], x["local"]))
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return p

def write_kakao(text):
    os.makedirs(os.path.dirname(KAKAO_PENDING), exist_ok=True)
    with open(KAKAO_PENDING, "w", encoding="utf-8") as f:
        f.write(text)

def run(direction, dry_run=False):
    local, shared = C.latest_local(), C.SHARED_FILE
    if lock_exists(local) or lock_exists(shared):
        log("[중단] 파일 열림(잠금). local잠금=%s shared잠금=%s" % (lock_exists(local), lock_exists(shared)))
        return 2
    snap = C.load_snapshot()
    if snap is None:
        log("[중단] 스냅샷 없음 — 베이스라인 먼저 캡처"); return 3

    if direction == "pull":
        d = P.compute_pull(local, shared, snap)
        conf_inf, conf_mail = d["inf_conflict"], d["mail_conflict"]
        report = P.fmt_report(d)
    else:
        d = PU.compute_push(local, shared, snap)
        conf_inf, conf_mail = d["inf_conflict"], []
        report = PU.fmt_report(d)
    log(report)

    if dry_run:
        log("[dry-run] 적용 생략"); return 0

    # 변경·충돌이 전혀 없으면 파일 재저장 생략(불필요한 openpyxl 재기록 방지)
    total = sum(len(v) for v in d.values())
    if total == 0:
        log("변경 없음 — 적용/스냅샷/카톡 생략"); return 0

    target = local if direction == "pull" else shared
    source = shared if direction == "pull" else local
    applied, bkp = A.apply_delta(source, target, d, inf_add_front=(direction == "pull"))
    log("적용: %s | 백업: %s" % (applied, os.path.basename(bkp)))

    # 스냅샷 갱신(현재상태) + 충돌 마커 박기
    C.save_snapshot(now() + "_" + direction)
    patch_snapshot_conflicts(conf_inf, conf_mail)

    # 카톡 메시지
    nconf = len(conf_inf) + len(conf_mail)
    arrow = "공유본→로컬" if direction == "pull" else "로컬→공유본"
    msg = ["🔄 DB 동기화 (%s)" % arrow]
    if direction == "pull":
        msg.append("• 신규행 %d · 상태갱신 %d" % (applied["mail_append"], applied["mail_status"]))
        msg.append("• 인플 갱신 %d · 신규인플 %d" % (applied["inf_update"], applied["inf_add"]))
    else:
        msg.append("• 인플 갱신 %d · 신규인플 %d" % (applied["inf_update"], applied["inf_add"]))
    if nconf:
        msg.append("⚠️ 확인 필요 %d건 (미적용) — 리포트 확인" % nconf)
        rp = write_report(direction, d, conf_inf, conf_mail)
        log("충돌 리포트: %s" % rp)
    msg.append("🕒 %s" % now())
    write_kakao("\n".join(msg))
    log("카톡 대기 메시지 작성: %s" % KAKAO_PENDING)
    return 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, choices=["pull", "push"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.dir, a.dry_run))
