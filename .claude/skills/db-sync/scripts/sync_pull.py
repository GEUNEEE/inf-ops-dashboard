# -*- coding: utf-8 -*-
"""
공유본 -> 로컬 단방향 델타 (12:00 / 18:00).
스냅샷 3자 비교로 '직원이 공유본에서 바꾼 것'만 추출.
 - 메일발송현황: 신규 행 append + 직원 응답열(회신/상태/미팅/협찬/광고수락) 갱신. 형 열 보존.
 - 인플루언서관리: 직원 변경 셀 반영 + 신규 인물 추가.
 - 충돌(직원·형이 같은 셀을 스냅샷 이후 서로 다르게 수정) = 적용 안 함, 리포트.
기본 dry-run(계산만). 적용은 sync_apply가 수행.
"""
import sync_core as C

def compute_pull(local_path=None, shared_path=None, snap=None):
    local_path = local_path or C.latest_local()
    shared_path = shared_path or C.SHARED_FILE
    snap = snap or C.load_snapshot()
    if snap is None:
        raise RuntimeError("스냅샷 없음 — 먼저 베이스라인 캡처 필요")

    lm, _ = C.load_mail(local_path)
    sm, _ = C.load_mail(shared_path)
    li, _, _ = C.load_inf(local_path)
    si, _, _ = C.load_inf(shared_path)

    snap_ms = snap.get("mail_shared", {})   # 직전 동기화 시점 공유본 emp
    snap_ml = snap.get("mail", {})          # 직전 동기화 시점 로컬 emp
    snap_is = snap.get("inf_shared", {})
    snap_il = snap.get("inf", {})

    d = {"mail_append": [], "mail_status": [], "mail_conflict": [],
         "inf_add": [], "inf_update": [], "inf_conflict": []}

    # ---- 메일발송현황 ----
    for k, sv in sm.items():
        if k not in snap_ms and k not in lm:
            d["mail_append"].append({"key": k, "name": sv["name"], "url": sv["url"],
                                      "full": sv.get("full")})
            continue
        if k not in lm:
            continue
        for label, new in sv["emp"].items():
            base_s = snap_ms.get(k, {}).get(label, "")
            if new == base_s:
                continue  # 직원이 안 건드림
            cur_l = lm[k]["emp"].get(label, "")
            base_l = snap_ml.get(k, {}).get(label, "")
            if cur_l != base_l and cur_l != new:
                d["mail_conflict"].append({"key": k, "name": sv["name"], "label": label,
                                            "shared": new, "local": cur_l})
            elif cur_l != new:
                d["mail_status"].append({"key": k, "name": sv["name"], "label": label,
                                          "row": lm[k]["row"], "new": new})

    # ---- 인플루언서관리 ----
    for k, sv in si.items():
        # 공유본에 있고 로컬에 없으면 무조건 추가(스냅샷 무관). 스냅샷에 묶여 안 흐르던 신규 인플 블라인드스팟 해소.
        if k not in li:
            d["inf_add"].append({"key": k, "name": sv["name"], "cells": sv["cells"]})
            continue
        for label, new in sv["cells"].items():
            cur_l = li[k]["cells"].get(label, "")
            if new == cur_l:
                continue   # 이미 동일
            base_s = snap_is.get(k, {}).get(label, "")
            base_l = snap_il.get(k, {}).get(label, "")
            # 빈칸 보강: 로컬이 줄곧 비어 있고(스냅샷에서도 빈칸) 공유본에 값 → 무손실 채움.
            # 스냅샷에 묶여 안 흐르던 '직원 전용 추가분'을 흐르게 함. 로컬이 값을 지운 경우(base_l!="")는 제외.
            if cur_l == "" and base_l == "" and new != "":
                d["inf_update"].append({"key": k, "name": sv["name"], "col": li[k]["col"],
                                         "label": label, "new": new})
                continue
            if new == base_s:
                continue
            if cur_l != base_l and cur_l != new:
                d["inf_conflict"].append({"key": k, "name": sv["name"], "label": label,
                                           "shared": new, "local": cur_l})
            elif cur_l != new:
                d["inf_update"].append({"key": k, "name": sv["name"], "col": li[k]["col"],
                                         "label": label, "new": new})
    return d

def fmt_report(d):
    L = []
    L.append("[공유본->로컬 PULL 델타]")
    L.append("  메일 신규행 추가: %d" % len(d["mail_append"]))
    for x in d["mail_append"][:20]:
        L.append("     + %s | %s" % (x["name"][:18], x["url"][:40]))
    L.append("  메일 상태 갱신: %d" % len(d["mail_status"]))
    for x in d["mail_status"][:20]:
        L.append("     ~ %s [%s] = %s" % (x["name"][:14], x["label"], x["new"]))
    L.append("  인플관리 신규 추가: %d" % len(d["inf_add"]))
    for x in d["inf_add"]:
        L.append("     + %s" % x["name"])
    L.append("  인플관리 셀 갱신: %d" % len(d["inf_update"]))
    for x in d["inf_update"][:20]:
        L.append("     ~ %s [%s] = %s" % (x["name"][:14], x["label"], x["new"]))
    nc = len(d["mail_conflict"]) + len(d["inf_conflict"])
    L.append("  >>> 충돌(확인필요, 미적용): %d <<<" % nc)
    for x in d["mail_conflict"] + d["inf_conflict"]:
        L.append("     ! %s [%s] 공유='%s' / 로컬='%s'" %
                 (x["name"][:14], x["label"], str(x["shared"])[:24], str(x["local"])[:24]))
    return "\n".join(L)

if __name__ == "__main__":
    d = compute_pull()
    print(fmt_report(d))
