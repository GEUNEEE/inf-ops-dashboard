#!/usr/bin/env python3
# parse_order.py — STEP 3-4: 주문 파일 복호화 + 버킷 분류 + Raw_Data 반영
# 사용법: python parse_order.py <암호화_xlsx_경로> <managed_set_json> [--import-mode]
# 출력: stdout JSON (버킷 분류 결과 + 신규 건수)
import sys
import json
import re
import io
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import msoffcrypto
import openpyxl
from dotenv import load_dotenv
import os

BASE_DIR     = Path(r"C:\Users\user\비서")
INPUT_DIR    = BASE_DIR / "input"
OUTPUT_DIR   = BASE_DIR / "output"
RAWDATA_PATH = BASE_DIR / "스케줄" / "정산DB_업데이트.xlsx"
CONFIG_PATH  = BASE_DIR / ".claude" / "skills" / "settlement-generator" / "scripts" / "ytber_config.json"
SKIP_LOG     = OUTPUT_DIR / "settlement_skipped.log"

DECRYPTED_PATH = INPUT_DIR / "order_decrypted.xlsx"
ORDER_SHEET    = "주문조회"
RAWDATA_SHEET  = "Raw_Data"

# 상품명에서 유튜버명 추출 패턴
YTBER_PATTERN = re.compile(r"\[([^\]]+?)\s*구독자")

# 주문 파일 열 인덱스 (0-based)
COL_ORDER_NO    = 0   # 상품주문번호
COL_ORDER_DATE  = 1   # 주문일
COL_PRODUCT_NAME = 10 # 상품명
COL_QTY         = 17  # 수량
COL_AMOUNT      = 18  # 주문금액
COL_ORDER_STATUS = 4  # 주문상태
COL_CLAIM_STATUS = 5  # 클레임상태


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def decrypt_xlsx(encrypted_path: Path, password: str) -> Path:
    with open(encrypted_path, "rb") as f:
        office_file = msoffcrypto.OfficeFile(f)
        office_file.load_key(password=password)
        decrypted = io.BytesIO()
        office_file.decrypt(decrypted)

    DECRYPTED_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DECRYPTED_PATH, "wb") as out:
        out.write(decrypted.getvalue())

    print(f"[INFO] 복호화 완료: {DECRYPTED_PATH}", file=sys.stderr)
    return DECRYPTED_PATH


def get_existing_order_nos(rawdata_wb) -> set:
    if RAWDATA_SHEET not in rawdata_wb.sheetnames:
        return set()
    ws = rawdata_wb[RAWDATA_SHEET]
    nos = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row and row[0] is not None:
            nos.add(str(row[0]).strip())
    return nos


def safe_str(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def safe_int(val, default=0) -> int:
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def extract_ytber(product_name: str, name_map: dict) -> str | None:
    m = YTBER_PATTERN.search(product_name)
    if not m:
        return None
    raw_name = m.group(1).strip()
    return name_map.get(raw_name, raw_name)


def is_cancelled(order_status: str, claim_status: str) -> bool:
    return "취소" in order_status or "취소완료" in claim_status


def main():
    if len(sys.argv) < 3:
        print("사용법: python parse_order.py <암호화_xlsx> <managed_set_json>", file=sys.stderr)
        sys.exit(1)

    encrypted_path = Path(sys.argv[1])
    managed_set = set(json.loads(sys.argv[2]))

    load_dotenv(BASE_DIR / ".env")
    password = os.environ.get("SMARTSTORE_XLSX_PASSWORD", "")
    if not password:
        print("[ERROR] .env에 SMARTSTORE_XLSX_PASSWORD가 없습니다.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    name_map  = config.get("name_map", {})
    excludes  = set(config.get("exclude", []))

    # 복호화
    try:
        decrypted_path = decrypt_xlsx(encrypted_path, password)
    except Exception as e:
        print(f"[ERROR] 복호화 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # 주문 파일 로드
    try:
        order_wb = openpyxl.load_workbook(decrypted_path, data_only=True, read_only=True)
    except Exception as e:
        print(f"[ERROR] 복호화 파일 로드 실패: {e}", file=sys.stderr)
        sys.exit(1)

    if ORDER_SHEET not in order_wb.sheetnames:
        print(f"[ERROR] 시트 '{ORDER_SHEET}' 없음. 목록: {order_wb.sheetnames}", file=sys.stderr)
        sys.exit(1)

    order_ws = order_wb[ORDER_SHEET]

    # Raw_Data 기존 주문번호 로드
    rawdata_wb = None
    existing_nos = set()
    if RAWDATA_PATH.exists():
        try:
            rawdata_wb = openpyxl.load_workbook(RAWDATA_PATH)
            existing_nos = get_existing_order_nos(rawdata_wb)
            print(f"[INFO] 기존 Raw_Data: {len(existing_nos)}건", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Raw_Data 읽기 실패, 신규 파일 생성: {e}", file=sys.stderr)
            rawdata_wb = openpyxl.Workbook()

    if rawdata_wb is None:
        rawdata_wb = openpyxl.Workbook()

    # Raw_Data 시트 준비
    if RAWDATA_SHEET not in rawdata_wb.sheetnames:
        ws_raw = rawdata_wb.create_sheet(RAWDATA_SHEET)
        ws_raw.append([
            "상품주문번호", "주문일", "유튜버명", "상품명", "수량", "주문금액",
            "주문상태", "클레임상태", "버킷", "반영일시"
        ])
    else:
        ws_raw = rawdata_wb[RAWDATA_SHEET]

    # 주문 분류
    buckets = {
        "settlement": [],   # 정산 대상
        "general":    [],   # 기타/일반
        "excluded":   [],   # 정산 제외 (미등재)
        "skipped":    [],   # 완전 제외 or 취소
    }
    unregistered = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_count = 0

    rows_iter = order_ws.iter_rows(min_row=2, values_only=True)
    for row in rows_iter:
        if not row or row[COL_ORDER_NO] is None:
            continue

        order_no     = safe_str(row[COL_ORDER_NO])
        order_date   = safe_str(row[COL_ORDER_DATE])
        product_name = safe_str(row[COL_PRODUCT_NAME])
        qty          = safe_int(row[COL_QTY], 1)
        amount       = safe_float(row[COL_AMOUNT])
        order_status = safe_str(row[COL_ORDER_STATUS])
        claim_status = safe_str(row[COL_CLAIM_STATUS])

        # 취소 건 스킵
        if is_cancelled(order_status, claim_status):
            buckets["skipped"].append({"order_no": order_no, "reason": "취소"})
            continue

        # 중복 체크
        if order_no in existing_nos:
            continue

        # 유튜버명 추출
        ytber = extract_ytber(product_name, name_map)

        if ytber is None:
            # 기타/일반
            bucket = "general"
        elif ytber in excludes:
            # 완전 제외
            bucket = "skipped"
            buckets["skipped"].append({"order_no": order_no, "ytber": ytber, "reason": "완전제외"})
            continue
        elif ytber in managed_set:
            # 정산 대상
            bucket = "settlement"
        else:
            # 정산 제외 (미등재)
            bucket = "excluded"
            unregistered.append({"name": ytber, "order_no": order_no, "qty": qty})
            _write_skip_log(ytber, qty, order_no)

        order_record = {
            "order_no":    order_no,
            "order_date":  order_date,
            "ytber":       ytber or config.get("general_sales_label", "기타/일반"),
            "product_name": product_name,
            "qty":         qty,
            "amount":      amount,
            "bucket":      bucket,
        }
        buckets[bucket].append(order_record)
        existing_nos.add(order_no)
        new_count += 1

        # Raw_Data 반영 (완전제외·취소 제외)
        ws_raw.append([
            order_no, order_date,
            ytber or config.get("general_sales_label", "기타/일반"),
            product_name, qty, amount,
            order_status, claim_status, bucket, now_str
        ])

    order_wb.close()

    # Raw_Data 저장
    RAWDATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    rawdata_wb.save(RAWDATA_PATH)
    rawdata_wb.close()
    print(f"[INFO] Raw_Data 저장: {RAWDATA_PATH} (신규 {new_count}건)", file=sys.stderr)

    result = {
        "new_count":     new_count,
        "settlement":    buckets["settlement"],
        "general":       buckets["general"],
        "excluded":      buckets["excluded"],
        "skipped_count": len(buckets["skipped"]),
        "unregistered":  unregistered,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


def _write_skip_log(ytber: str, qty: int, order_no: str):
    SKIP_LOG.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"[{now}] 정산 제외 기록\n"
        f"유튜버명: {ytber} | 주문번호: {order_no} | 수량: {qty}개 | 사유: 인플루언서관리 시트 미등재\n\n"
    )
    with open(SKIP_LOG, "a", encoding="utf-8") as f:
        f.write(line)


if __name__ == "__main__":
    main()
