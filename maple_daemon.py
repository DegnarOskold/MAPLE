"""
MAPLE Standalone Daemon
Allows MAPLE to run autonomously in the background even if Antigravity is closed.
Loops every 15 minutes during US market trading hours (9:30 AM - 4:00 PM ET Mon-Fri),
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
from maple_market import now_et_naive, is_nyse_trading_day, is_nyse_holiday, get_nyse_close_hour_min
from maple_optimizer import run_daily_self_assessment
from maple_ledger import get_ledger_state


def get_seconds_until_next_interval() -> int:
    """Calculates seconds until the next :00, :15, :30, or :45 minute mark."""
    now = now_et_naive()
    minutes = now.minute
    seconds = now.second
    next_quarter = ((minutes // 15) + 1) * 15
    remaining_minutes = next_quarter - minutes
    total_seconds = (remaining_minutes * 60) - seconds + 10
    return max(15, total_seconds)


def start_daemon():
    print("=" * 65)
    print("           MAPLE AUTONOMOUS LIVE TRADING DAEMON             ")
    print("=" * 65)
    state = get_ledger_state()
    print(f"Trading Mode:    {state.get('mode', 'LIVE')}")
    print(f"Broker Account:  #{state.get('account_id', 'N/A')}")
    print(f"Cash Available:  ${state.get('cash', 0.0):.2f} USD")
    print(f"Total Equity:    ${state.get('total_equity', state.get('cash', 0.0)):.2f} USD")
    print("Daemon active. Press Ctrl+C at any time to halt.")
    print("=" * 65 + "\n")

    last_retrospective_date = None

    while True:
        try:
            now = now_et_naive()
            today_str = now.strftime("%Y-%m-%d")

            # 1. Market Hours Check (NYSE regular trading hours in ET, respecting holidays & 1:00 PM early closes)
            if is_market_open():
                print(f"\n[DAEMON WAKEUP] {now.strftime('%Y-%m-%d %H:%M:%S')} ET - Running live market scan...")
                run_intraday_scan()
            else:
                close_h, close_m = get_nyse_close_hour_min(now.date())
                close_dt = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
                mins_after_close = (now - close_dt).total_seconds() / 60.0
                # 2. Post-Close Daily Retrospective 5-25 min after NYSE close on valid trading days only
                if is_nyse_trading_day(now.date()) and 5.0 <= mins_after_close <= 25.0:
                    if last_retrospective_date != today_str:
                        print(f"\n[DAEMON] Running daily post-close self-assessment...")
                        run_daily_self_assessment()
                        last_retrospective_date = today_str
                else:
                    if now.weekday() >= 5:
                        status = "Weekend (Markets Closed)"
                    elif is_nyse_holiday(now.date()):
                        status = "NYSE Holiday (Markets Closed)"
                    elif now.hour < 9 or (now.hour == 9 and now.minute < 30):
                        status = "Pre-Market (Opens 9:30 AM ET)"
                    else:
                        status = "After-Hours (Markets Closed)"
                    print(f"[{now.strftime('%H:%M:%S')} ET] {status} - Standing by.")

            # Calculate sleep duration to next 15-min boundary
            sleep_sec = get_seconds_until_next_interval()
            next_run = now_et_naive() + datetime.timedelta(seconds=sleep_sec)
            print(f"Sleeping {sleep_sec // 60}m {sleep_sec % 60}s (Next scan at {next_run.strftime('%H:%M:%S')} ET)...")
            time.sleep(sleep_sec)

        except KeyboardInterrupt:
            print("\n[DAEMON STOPPED] MAPLE daemon terminated by user.")
            break
        except Exception as e:
            print(f"[DAEMON ERROR] Unexpected error: {e}. Retrying in 60 seconds...")
            time.sleep(60)


if __name__ == "__main__":
    start_daemon()
