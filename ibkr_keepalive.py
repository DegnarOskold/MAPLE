"""
IBKR Session Keepalive Daemon for MAPLE
Pings https://localhost:5000/v1/api/tickle every 45 seconds to keep
the Client Portal Gateway SSO session active throughout the trading day.
"""

import time
import datetime
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GATEWAY_URL = "https://localhost:5000/v1/api"
INTERVAL_SECONDS = 45


def run_keepalive():
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] IBKR Keepalive Daemon started.")
    session = requests.Session()
    session.verify = False

    while True:
        try:
            res = session.post(f"{GATEWAY_URL}/tickle", timeout=5)
            if res.status_code == 200:
                # Session is healthy and kept alive
                pass
            elif res.status_code == 401:
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [IBKR WARNING] Gateway session unauthenticated / expired. Please log in at https://localhost:5000")
            else:
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [IBKR INFO] Tickle status code: {res.status_code}")
        except Exception as e:
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [IBKR ERROR] Cannot connect to Gateway: {e}")

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run_keepalive()
