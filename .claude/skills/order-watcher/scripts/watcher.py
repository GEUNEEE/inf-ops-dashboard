#!/usr/bin/env python3
# watcher.py — /input 폴더 감시, 스마트스토어 주문 xlsx 드롭 감지 시 파이프라인 트리거
# 실행: python watcher.py (백그라운드 데몬으로 상시 실행)
import sys
import time
import subprocess
import logging
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

BASE_DIR   = Path(r"C:\Users\user\비서")
INPUT_DIR  = BASE_DIR / "input"
PYTHON_EXE = BASE_DIR / ".venv" / "Scripts" / "python.exe"
LOG_PATH   = BASE_DIR / "output" / "watcher.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


def is_order_file(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("스마트스토어_주문조회_")
        and name.endswith(".xlsx")
        and not name.startswith("~$")
        and name != "order_decrypted.xlsx"
    )


def run_pipeline(xlsx_path: Path):
    log.info(f"주문 파일 감지: {xlsx_path.name} → 파이프라인 시작")
    # Claude Code가 파이프라인 전체를 조율하므로 감지 사실을 로그에 기록하고
    # 실제 처리는 메인 에이전트가 수행한다.
    # 단독 실행 시에는 아래 스크립트를 직접 호출할 수 있다.
    try:
        result = subprocess.run(
            [str(PYTHON_EXE), str(BASE_DIR / ".claude" / "skills" / "order-watcher" / "scripts" / "run_pipeline.py"),
             str(xlsx_path)],
            capture_output=True, text=True, encoding="utf-8"
        )
        if result.returncode == 0:
            log.info(f"파이프라인 완료: {xlsx_path.name}")
        else:
            log.error(f"파이프라인 실패:\n{result.stderr}")
    except Exception as e:
        log.error(f"파이프라인 실행 오류: {e}")


class OrderFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if is_order_file(p):
            # 파일 쓰기 완료 대기
            time.sleep(2)
            run_pipeline(p)

    def on_moved(self, event):
        if event.is_directory:
            return
        p = Path(event.dest_path)
        if is_order_file(p):
            time.sleep(2)
            run_pipeline(p)


def main():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    log.info(f"watchdog 시작 — 감시 폴더: {INPUT_DIR}")

    observer = Observer()
    observer.schedule(OrderFileHandler(), str(INPUT_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
        log.info("watchdog 종료")

    observer.join()


if __name__ == "__main__":
    main()
