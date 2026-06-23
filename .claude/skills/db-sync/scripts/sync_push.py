# -*- coding: utf-8 -*-
"""
로컬 -> 공유본 단방향 델타 (20:00). 설계상 인플루언서관리 시트만.
(메일발송현황은 공유본->로컬 pull 전용 — 1회 시드 이후 push 안 함)
스냅샷 3자 비교로 '형이 로컬에서 바꾼 것'만 추출해 공유본에 반영.
충돌(형·직원이 같은 셀을 스냅샷 이후 서로 다르게 수정) = 미적용, 리포트.
"""
import sync_core as C

def compute_push(local_path=None, shared_path=None, snap=None):
    local_path = local_path or C.latest_local()
    shared_path = shared_path or C.SHARED_FILE
    snap = snap or C.load_snapshot()
    if snap is None:
        raise RuntimeError("스냅샷 없음 — 먼저 베이스라인 캡처 필요")

    li, _, _ = C.load_inf(local_path)
    si, _, _ = C.load_inf(shared_path)
    snap_il = snap.get("inf", {})          # 직전 동기화 로컬
    snap_is = snap.get("inf_shared", {})   # 직전 동기화 공유본

    d = {"inf_add": [], "inf_update": [], "inf_conflict": []}
    for k, lv in li.items():
        # 로컬에 있고 공유본에 없으면 무조건 추가(스냅샷 무관). 신규 인플 블라인드스팟 해소.
        if k not in si:
            d["inf_add"].append({"key": k, "name": lv["name"], "cells": lv["cells"]})
            continue
        for label, new in lv["cells"].items():
            cur_s = si[k]["cells"].get(label, "")
            if new == cur_s:
                continue   # 이미 동일
            base_l = snap_il.get(k, {}).get(label, "")
            base_s = snap_is.get(k, {}).get(label, "")
            # 빈칸 보강: 공유본이 줄곧 비어 있고(스냅샷에서도 빈칸) 로컬에 값 → 무손실 채움.
            # 스냅샷에 묶여 안 흐르던 '로컬 전용 추가분'을 흐르게 함. 공유본이 값을 지운 경우(base_s!="")는 제외.
            if cur_s == "" and base_s == "" and new != "":
                d["inf_update"].append({"key": k, "name": lv["name"], "col": si[k]["col"],
                                         "label": label, "new": new})
                continue
            if new == base_l:
                continue   # 형이 안 건드림
            if cur_s != base_s and cur_s != new:
                d["inf_conflict"].append({"key": k, "name": lv["name"], "label": label,
                                           "shared": cur_s, "local": new})
            elif cur_s != new:
                d["inf_update"].append({"key": k, "name": lv["name"], "col": si[k]["col"],
                                         "label": label, "new": new})
    return d

def fmt_report(d):
    L = ["[로컬->공유본 PUSH 델타 (인플관리)]"]
    L.append("  신규 추가: %d" % len(d["inf_add"]))
    for x in d["inf_add"]:
        L.append("     + %s" % x["name"])
    L.append("  셀 갱신: %d" % len(d["inf_update"]))
    for x in d["inf_update"][:20]:
        L.append("     ~ %s [%s] = %s" % (x["name"][:14], x["label"], x["new"]))
    L.append("  >>> 충돌(확인필요, 미적용): %d <<<" % len(d["inf_conflict"]))
    for x in d["inf_conflict"]:
        L.append("     ! %s [%s] 공유='%s' / 로컬='%s'" %
                 (x["name"][:14], x["label"], str(x["shared"])[:24], str(x["local"])[:24]))
    return "\n".join(L)

if __name__ == "__main__":
    print(fmt_report(compute_push()))
