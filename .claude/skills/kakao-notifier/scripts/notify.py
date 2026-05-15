#!/usr/bin/env python3
# notify.py — STEP 8: 카카오톡 메모챗 알림 메시지 생성
# 실제 MCP 호출은 Claude Code 에이전트가 담당.
# 이 스크립트는 메시지 텍스트를 stdout으로 출력한다.
# 사용법: python notify.py <revenue_json> <bucket_json> <settlement_json>
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR   = Path(r"C:\Users\user\비서")
SITE_URL   = "https://{YOUR_GITHUB_PAGES_URL}"  # 실제 URL로 교체


def fmt_money(v: int) -> str:
    return f"₩{v:,}"


def main():
    if len(sys.argv) < 4:
        print("사용법: python notify.py <revenue_json> <bucket_json> <settlement_json>", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        revenue = json.load(f)
    with open(sys.argv[2], encoding="utf-8") as f:
        bucket = json.load(f)
    with open(sys.argv[3], encoding="utf-8") as f:
        settlement = json.load(f)

    new_count      = bucket.get("new_count", 0)
    settlement_cnt = len([s for s in settlement.get("summaries", []) if not s.get("is_general")])
    general_cnt    = len(bucket.get("general", []))
    unregistered   = bucket.get("unregistered", [])

    gross = revenue.get("gross_revenue", 0)
    profit = revenue.get("net_profit", 0)

    lines = []
    lines.append("📦 주문 처리 완료")
    lines.append(f"• 신규 {new_count}건 | 정산 {settlement_cnt}명 | 기타 {general_cnt}건")

    if unregistered:
        unreg_map: dict[str, dict] = {}
        for u in unregistered:
            n = u["name"]
            if n not in unreg_map:
                unreg_map[n] = {"name": n, "건수": 0, "수량": 0}
            unreg_map[n]["건수"] += 1
            unreg_map[n]["수량"] += u.get("qty", 0)
        lines.append("")
        lines.append("⚠️ 관리탭 미등재 인플루언서")
        for item in unreg_map.values():
            lines.append(f"  • {item['name']} ({item['건수']}건 / {item['수량']}개)")

    lines.append("")
    lines.append(f"💰 이번달 매출: {fmt_money(gross)}")
    lines.append(f"📊 수익: {fmt_money(profit)}")
    lines.append("")
    lines.append(f"🔗 대시보드: {SITE_URL}")

    message = "\n".join(lines)
    print(message)

    # 미등재 즉시 알림 메시지 (별도)
    if unregistered:
        lines2 = ["⚠️ [즉시 확인 필요] 관리탭 미등재 인플루언서 발견"]
        for item in unreg_map.values():
            lines2.append(f"• {item['name']} — {item['건수']}건, {item['수량']}개")
        lines2.append("\n인플루언서관리 시트에 추가하거나 제외 목록에 등록해 주세요.")
        print("\n--- 미등재 즉시 알림 ---\n" + "\n".join(lines2))


if __name__ == "__main__":
    main()
