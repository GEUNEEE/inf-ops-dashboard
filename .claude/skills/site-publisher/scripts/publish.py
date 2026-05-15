#!/usr/bin/env python3
# publish.py — STEP 9: site/data/ 갱신 후 git add/commit/push
# 사용법: python publish.py <YYYY-MM>
import sys
import subprocess
from pathlib import Path
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(r"C:\Users\user\비서")
SITE_DIR = BASE_DIR / "site"


def git(cmd: list, cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["git"] + cmd, capture_output=True, text=True, encoding="utf-8", cwd=cwd
    )
    return result.returncode, result.stdout + result.stderr


def push_site(month: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    commit_msg = f"data: {today} 주문 반영 ({month})"

    code, out = git(["add", "site/"], BASE_DIR)
    if code != 0:
        print(f"[ERROR] git add 실패: {out}", file=sys.stderr)
        return False

    code, out = git(["commit", "-m", commit_msg], BASE_DIR)
    if code != 0:
        if "nothing to commit" in out:
            print("[INFO] 변경 없음 — git commit 스킵", file=sys.stderr)
            return True
        print(f"[ERROR] git commit 실패: {out}", file=sys.stderr)
        return False

    code, out = git(["push"], BASE_DIR)
    if code != 0:
        print(f"[WARN] git push 실패, 1회 재시도: {out}", file=sys.stderr)
        code, out = git(["push"], BASE_DIR)
        if code != 0:
            print(f"[ERROR] git push 재시도 실패: {out}", file=sys.stderr)
            return False

    print(f"[INFO] git push 완료: {commit_msg}", file=sys.stderr)
    return True


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m")
    success = push_site(month)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
