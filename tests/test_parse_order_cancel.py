# tests/test_parse_order_cancel.py — 취소 판정 규칙 + 취소관리 파일 수집 단위 테스트
# 실행: PYTHONUTF8=1 .venv\Scripts\python.exe -m unittest tests.test_parse_order_cancel -v
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SKILLS = BASE / ".claude" / "skills"
sys.path.insert(0, str(SKILLS / "excel-parser" / "scripts"))

import parse_order  # noqa: E402


class CancelRuleTest(unittest.TestCase):
    def test_status_cancel(self):
        self.assertTrue(parse_order.is_cancelled("취소", "취소완료"))
        self.assertTrue(parse_order.is_cancelled("미결제취소", "취소완료"))

    def test_claim_requested_counts_as_cancelled(self):
        # 취소관리 양식: 주문상태는 아직 '결제완료', 취소 처리상태 = '취소요청'
        self.assertTrue(parse_order.is_cancelled("결제완료", "취소요청"))
        self.assertTrue(parse_order.is_cancelled("결제완료", "취소처리중"))
        self.assertTrue(parse_order.is_cancelled("결제완료", "취소완료"))

    def test_withdrawn_is_not_cancelled(self):
        self.assertFalse(parse_order.is_cancelled("배송중", "취소철회"))

    def test_normal_orders(self):
        for st in ("결제완료", "발송대기", "배송중", "배송완료", "구매확정", "결제대기"):
            self.assertFalse(parse_order.is_cancelled(st, ""))

    def test_rule_is_identical_across_scripts(self):
        """build_snapshot·generate_sheets·build_payout_tax 가 parse_order 와 같은 규칙을 쓰는지 소스로 확인."""
        rule = '"취소" in status or ("취소" in claim and "철회" not in claim)'
        old = '"취소완료" in claim'
        for sub, name in (("dashboard-builder", "build_snapshot.py"),
                          ("settlement-generator", "generate_sheets.py"),
                          ("settlement-generator", "build_payout_tax.py")):
            src = (SKILLS / sub / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn(rule, src, name)
            self.assertNotIn(old, src, name)

    def test_pipeline_collects_cancel_management_files(self):
        src = (SKILLS / "order-watcher" / "scripts" / "run_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"스마트스토어_*취소관리_*.xlsx"', src)


if __name__ == "__main__":
    unittest.main()
