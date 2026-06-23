# -*- coding: utf-8 -*-
"""
스케줄 디스패처: 현재 시각 기준으로 오늘 아직 실행 안 한 슬롯을 실행.
슬롯: 12:00 pull / 18:00 pull / 20:00 push.
상태파일(output/sync_state.json)에 슬롯별 마지막 실행 날짜 기록 → 중복 실행 방지.
/loop 의 매 틱에서 호출. 표준출력에 'RAN: ...' / 'KAKAO_PENDING: yes|no' 보고.
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_sync

STATE = r"C:\Users\user\비서\output\sync_state.json"
KAKAO = run_sync.KAKAO_PENDING
SLOTS = [("12:00", "pull"), ("18:00", "pull"), ("20:00", "push")]

def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def main():
    nowdt = datetime.datetime.now()
    today = nowdt.strftime("%Y-%m-%d")
    hhmm_now = nowdt.strftime("%H:%M")
    state = load_state()
    ran = []
    for hhmm, direction in SLOTS:
        if hhmm_now >= hhmm and state.get(hhmm) != today:
            rc = run_sync.run(direction)
            if rc == 0:
                state[hhmm] = today
                ran.append((hhmm, direction))
            elif rc == 2:
                print("SKIP %s %s: 파일 잠금 — 다음 틱 재시도" % (hhmm, direction))
            else:
                print("ERR %s %s rc=%d" % (hhmm, direction, rc))
    save_state(state)
    # 다음 슬롯 안내
    nxt = next((h for h, _ in SLOTS if hhmm_now < h), "내일 12:00")
    print("RAN:", ran if ran else "none")
    print("NEXT_SLOT:", nxt)
    print("KAKAO_PENDING:", "yes" if os.path.exists(KAKAO) else "no")

if __name__ == "__main__":
    main()
