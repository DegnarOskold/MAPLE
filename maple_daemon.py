"""
MAPLE Standalone Daemon
Allows MAPLE to run autonomously in the background even if Antigravity is closed.
Loops every 30 minutes during TSX trading hours (9:30 AM - 4:00 PM ET Mon-Fri),
executing real-time market scans, target/stop checking, and limit order placement.
Executes the daily retrospective and self-optimization at 4:10 PM ET.
"""

import os
import sys
import time
import datetime

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
if MAPLE_DIR not in sys.path:
    sys.path.insert(0, MAPLE_DIR)

from maple_brain import run_intraday_scan, is_market_open
from maple_optimizer import run_daily_self_assessment
from maple_ledger import get_ledger_state


def get_seconds_until_next_interval() -> int:
    """Calculates seconds until the next :00, :15, :30, or :45 minute mark."""
    now = datetime.datetime.now()
    minutes = now.minute
    seconds = now.second
    next_quarter = ((minutes // 15) + 1) * 15
    remaining_minutes = next_quarter - minutes
    total_seconds = (remaining_minutes * 60) - seconds
    return max(15, total_seconds)


def start_daemon():
    print("=" * 65)
    print("           MAPLE AUTONOMOUS LIVE TRADING DAEMON             ")
    print("=" * 65)
    state = get_ledger_state()
    print(f"Trading Mode:    {state.get('mode', 'LIVE')}")
    print(f"Broker Account:  #{state.get('account_id', 'N/A')}")
    print(f"Cash Available:  ${state.get('cash', 0.0):.2f} CAD")
    print(f"Total Equity:    ${state.get('total_equity', state.get('cash', 0.0)):.2f} CAD")
    print("Daemon active. Press Ctrl+C at any time to halt.")
    print("=" * 65 + "\n")

    last_retrospective_date = None

    while True:
        try:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # 1. Market Hours Check (09:30 - 16:00 ET Mon-Fri)
            if is_market_open():
                print(f"\n[DAEMON WAKEUP] {now.strftime('%Y-%m-%d %H:%M:%S')} - Running live market scan...")
                run_intraday_scan()
            else:
                # 2. Post-Close Daily Retrospective at ~16:10 ET Mon-Fri
                if now.weekday() < 5 and now.hour == 16 and 5 <= now.minute <= 25:
                    if last_retrospective_date != today_str:
                        print(f"\n[DAEMON] Running daily post-close self-assessment...")
                        run_daily_self_assessment()
                        last_retrospective_date = today_str
                else:
                    if now.weekday() >= 5:
                        status = "Weekend (Markets Closed)"
                    elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
                        status = "Pre-Market (Opens 9:30 AM ET)"
                    else:
                        status = "After-Hours (Markets Closed)"
                    print(f"[{now.strftime('%H:%M:%S')}] {status} - Standing by.")

            # Calculate sleep duration to next 30-min boundary
            sleep_sec = get_seconds_until_next_interval()
            next_run = datetime.datetime.now() + datetime.timedelta(seconds=sleep_sec)
            print(f"Sleeping {sleep_sec // 60}m {sleep_sec % 60}s (Next scan at {next_run.strftime('%H:%M:%S')})...")
            time.sleep(sleep_sec)

        except KeyboardInterrupt:
            print("\n[DAEMON STOPPED] MAPLE daemon terminated by user.")
            break
        except Exception as e:
            print(f"[DAEMON ERROR] Unexpected error: {e}. Retrying in 60 seconds...")
            time.sleep(60)


if __name__ == "__main__":
    start_daemon()
