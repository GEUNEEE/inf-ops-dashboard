# -*- coding: utf-8 -*-
"""
델타 적용 작성기. compute_pull / compute_push 결과를 대상 파일에 반영.
원칙:
 - 쓰기 값은 SOURCE 파일에서 '원본 타입 그대로' 복사(날짜 보존). 델타의 cv문자열은 비교 전용.
 - 대상 쓰기 전 백업, 임시파일 교체 저장(원자적).
 - 충돌(conflict)은 적용하지 않는다(리포트만).
 - 인플관리 신규열의 수식행(체험종료/중간관리일)은 새 열 기준 수식으로 재작성.
"""
import os, shutil, sys
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.formula.translate import Translator
from copy import copy
import sync_core as C

MAIL_LABEL2COL = {lab: i for i, lab in C.MAIL_EMP_COLS.items()}   # label -> 0-based col


def _insert_inf_at_front(itgt, isrc, scol):
    """인플관리 3열에 isrc[scol] 인플을 삽입. 기존 열(3..N)을 오른쪽으로 한 칸씩 밀고
    값·서식·열너비 보존, 수식은 새 열참조로 변환. (직원이 공유본 맨 앞에 추가하는 패턴과 정렬)"""
    NAME_ROW = C.INF_ROW_NAME
    cols = [c for c in range(3, itgt.max_column + 1)
            if itgt.cell(NAME_ROW, c).value not in (None, "")]
    ROWS = range(1, 47)
    if cols:
        last = max(cols)
        for c in range(last, 2, -1):           # last..3 → 오른쪽으로 이동(덮어쓰기 방지)
            sL, dL = get_column_letter(c), get_column_letter(c + 1)
            for r in ROWS:
                sc = itgt.cell(r, c)
                val = sc.value
                if isinstance(val, str) and val.startswith("="):
                    val = Translator(val, origin="%s%d" % (sL, r)).translate_formula("%s%d" % (dL, r))
                dc = itgt.cell(r, c + 1)
                dc.value = val
                dc._style = copy(sc._style)
            w = itgt.column_dimensions[sL].width
            if w is not None:
                itgt.column_dimensions[dL].width = w
    cl = get_column_letter(3)
    for r in ROWS:
        if r in C.INF_FORMULA_ROWS:
            itgt.cell(r, 3).value = ("=%s27+10" % cl) if r == 28 else ("=%s28+7" % cl)
        else:
            itgt.cell(r, 3).value = isrc.cell(r, scol).value
    # 검증: 3열에 신규 인플 이름이 들어갔는지(실패 시 예외→저장 생략, 백업 보존)
    if itgt.cell(NAME_ROW, 3).value in (None, ""):
        raise RuntimeError("inf front-insert 실패: 3열 이름 비어있음")

def _inf_index(ws):
    """{key: col(1-based)}, {label: row}"""
    rows = {r: ws.cell(row=r, column=1).value for r in range(1, 46)}
    label2row = {C.cv(rows[r]): r for r in C.INF_LABEL_ROWS}
    keymap = {}
    for col in range(3, ws.max_column + 1):
        name = ws.cell(row=C.INF_ROW_NAME, column=col).value
        if name in (None, ""):
            continue
        phone = C.norm_phone(ws.cell(row=C.INF_ROW_PHONE, column=col).value)
        key = phone if phone else "NAME::" + "".join(str(name).split())
        keymap[key] = col
    return keymap, label2row

def _mail_keyrow(ws):
    """{key: row(1-based)}"""
    out, es = {}, 0
    for r in range(7, ws.max_row + 1):
        name = ws.cell(row=r, column=5).value
        url = ws.cell(row=r, column=6).value
        if name in (None, "") and url in (None, ""):
            es += 1
            if es >= 15:
                break
            continue
        es = 0
        key = C.norm_url(C.cv(url)) if C.cv(url) else "NAME::" + "".join(C.cv(name).split())
        if key not in out:
            out[key] = r
    return out

def _last_mail_row(ws):
    last = 6
    for r in range(7, ws.max_row + 1):
        if ws.cell(row=r, column=5).value or ws.cell(row=r, column=6).value:
            last = r
    return last

def apply_delta(source_path, target_path, delta, backup_dir=None, inf_add_front=False):
    """delta(pull 또는 push)를 target에 적용. source에서 원본값 복사. 적용 요약 반환.
    inf_add_front=True면 신규 인플을 target 맨 앞(3열)에 삽입(pull용). False면 끝에 append."""
    # 백업
    backup_dir = backup_dir or os.path.join(os.path.dirname(target_path), "old")
    os.makedirs(backup_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(target_path))[0]
    bkp = os.path.join(backup_dir, base + "_sync백업.xlsx")
    shutil.copy2(target_path, bkp)

    src = openpyxl.load_workbook(source_path, data_only=True)
    tgt = openpyxl.load_workbook(target_path)   # 수식/서식 보존
    applied = {"mail_append": 0, "mail_status": 0, "inf_update": 0, "inf_add": 0}

    # ===== 메일발송현황 =====
    if delta.get("mail_append") or delta.get("mail_status"):
        ssrc = src[C.MAIL_SHEET]; stgt = tgt[C.MAIL_SHEET]
        src_row = _mail_keyrow(ssrc)
        # 신규행 append
        nr = _last_mail_row(stgt) + 1
        for x in delta.get("mail_append", []):
            full = x.get("full")
            if not full:
                sr = src_row.get(x["key"])
                full = [ssrc.cell(row=sr, column=c+1).value for c in range(34)] if sr else None
            if not full:
                continue
            for c, val in enumerate(full):
                if val is not None:
                    stgt.cell(row=nr, column=c+1).value = val
            nr += 1
            applied["mail_append"] += 1
        # 상태 갱신
        tgt_row = _mail_keyrow(stgt)
        for x in delta.get("mail_status", []):
            col0 = MAIL_LABEL2COL.get(x["label"])
            sr = src_row.get(x["key"]); tr = tgt_row.get(x["key"])
            if col0 is None or sr is None or tr is None:
                continue
            stgt.cell(row=tr, column=col0+1).value = ssrc.cell(row=sr, column=col0+1).value
            applied["mail_status"] += 1

    # ===== 인플루언서관리 =====
    if delta.get("inf_update") or delta.get("inf_add"):
        isrc = src[C.INF_SHEET]; itgt = tgt[C.INF_SHEET]
        skey, slab2row = _inf_index(isrc)
        tkey, tlab2row = _inf_index(itgt)
        # 셀 갱신
        for x in delta.get("inf_update", []):
            scol = skey.get(x["key"]); tcol = tkey.get(x["key"])
            row = tlab2row.get(x["label"])
            if scol is None or tcol is None or row is None:
                continue
            itgt.cell(row=row, column=tcol).value = isrc.cell(row=row, column=scol).value
            applied["inf_update"] += 1
        # 신규 인물 = 새 열. front-insert면 공유본 순서 유지 위해 역순으로 삽입(맨 앞에 차례로).
        adds = list(delta.get("inf_add", []))
        for x in (reversed(adds) if inf_add_front else adds):
            scol = skey.get(x["key"])
            if scol is None:
                continue
            if inf_add_front:
                _insert_inf_at_front(itgt, isrc, scol)
                tkey = {k: (c + 1 if c >= 3 else c) for k, c in tkey.items()}
                tkey[x["key"]] = 3
            else:
                ncol = max(tkey.values()) + 1 if tkey else 3
                cl = get_column_letter(ncol)
                for r in range(1, 46):
                    if r in C.INF_FORMULA_ROWS:
                        itgt.cell(row=r, column=ncol).value = ("=%s27+10" % cl) if r == 28 else ("=%s28+7" % cl)
                    else:
                        itgt.cell(row=r, column=ncol).value = isrc.cell(row=r, column=scol).value
                tkey[x["key"]] = ncol
            applied["inf_add"] += 1

    # 원자적 저장
    tmp = target_path + ".synctmp.xlsx"
    tgt.save(tmp)
    os.replace(tmp, target_path)
    src.close(); tgt.close()
    return applied, bkp
