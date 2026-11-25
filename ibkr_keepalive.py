"""
IBKR Session Keepalive Daemon for MAPLE
Pings https://localhost:5000/v1/api/tickle every 45 seconds to keep
the Client Portal Gateway SSO session active throughout the trading day.
"""

import time
import datetime
import requests
import urllib3

from maple_market import now_et_naive, is_nyse_trading_day, get_nyse_close_hour_min

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GATEWAY_URL = "https://localhost:5000/v1/api"
INTERVAL_SECONDS = 45


def _in_live_session_window() -> bool:
    now = now_et_naive()
    if not is_nyse_trading_day(now.date()):
        return False
    close_h, close_m = get_nyse_close_hour_min(now.date())
    start = now.replace(hour=9, minute=25, second=0, microsecond=0)
    end = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0) + datetime.timedelta(minutes=5)
    return start <= now <= end


def _notify_gateway_issue(reason: str):
    if not _in_live_session_window():
        return
    try:
        from maple_ledger import load_config
        if load_config().get("trading_mode", "").upper() != "LIVE":
            return
        from telegram_notifier import send_circuit_breaker_alert
        send_circuit_breaker_alert("IBKR Gateway Disconnected", reason, cooldown_minutes=30)
    except Exception:
        pass


def run_keepalive():
    print(f"[{now_et_naive().strftime('%Y-%m-%d %H:%M:%S')}] IBKR Keepalive Daemon started.")
    session = requests.Session()
    session.verify = False

    while True:
        now_s = now_et_naive().strftime("%Y-%m-%d %H:%M:%S")
        try:
            res = session.post(f"{GATEWAY_URL}/tickle", timeout=5)
            if res.status_code == 200:
                pass
            elif res.status_code == 401:
                msg = "Gateway SSO session unauthenticated / expired (401). Please log in at https://localhost:5000"
                print(f"[{now_s}] [IBKR WARNING] {msg}")
                _notify_gateway_issue(msg)
            else:
                print(f"[{now_s}] [IBKR INFO] Tickle status code: {res.status_code}")
        except Exception as e:
            msg = f"Cannot connect to IBKR Gateway at {GATEWAY_URL}: {e}"
            print(f"[{now_s}] [IBKR ERROR] {msg}")
            _notify_gateway_issue(msg)

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run_keepalive()
