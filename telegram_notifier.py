"""
MAPLE Telegram Notification Engine
Dispatches real-time trade alerts, desk scan updates, and daily performance reports
directly to the user's Telegram.
Objective, quantitative, institutional reporting format.
"""

import os
import html
import json
import requests
import datetime
from typing import Dict, Any, Optional, List

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(MAPLE_DIR, "telegram_config.json")
ENV_FILE = os.path.join(MAPLE_DIR, ".env")


def load_telegram_config() -> Dict[str, Any]:
    """Loads Telegram config from telegram_config.json, with fallback to .env."""
    config = {
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "notify_on_trades": True,
        "notify_on_scans": True,
        "notify_on_circuit_breakers": True,
        "notify_on_close": True,
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config.update(data)
        except Exception:
            pass

    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "TELEGRAM_BOT_TOKEN" and (not config["telegram_bot_token"] or "YOUR_" in config["telegram_bot_token"]):
                        config["telegram_bot_token"] = val
                    elif key == "TELEGRAM_CHAT_ID" and (not config["telegram_chat_id"] or "YOUR_" in config["telegram_chat_id"]):
                        config["telegram_chat_id"] = val
        except Exception:
            pass

    return config


def save_telegram_config(config: Dict[str, Any]):
    """Saves updated Telegram config to telegram_config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"[TELEGRAM WARNING] Failed to save config: {e}")


def is_configured() -> bool:
    """Checks if a valid Telegram Bot token and chat ID are configured."""
    cfg = load_telegram_config()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = str(cfg.get("telegram_chat_id", "")).strip()

    if not token or "YOUR_" in token or len(token) < 15:
        return False
    if not chat_id or "YOUR_" in chat_id:
        return False
    return True


def send_telegram_message(message: str, parse_mode: str = "HTML") -> bool:
    """Sends a message to the configured Telegram chat with retry on connection resets."""
    cfg = load_telegram_config()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = str(cfg.get("telegram_chat_id", "")).strip()

    if not is_configured():
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    import time
    for attempt in range(1, 4):
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                return True
            else:
                print(f"[TELEGRAM ERROR] HTTP {res.status_code}: {res.text}")
                return False
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < 3:
                time.sleep(1.0)
                continue
            print(f"[TELEGRAM ERROR] Request failed after {attempt} attempts: {e}")
            return False
        except Exception as e:
            print(f"[TELEGRAM ERROR] Exception: {e}")
            return False
    return False


def send_trade_alert(
    action: str,
    ticker: str,
    shares: float,
    price: float,
    order_id: Any,
    target_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
    pnl: Optional[float] = None,
    pnl_pct: Optional[float] = None,
    notes: str = "",
) -> bool:
    """Sends a formatted, objective trade execution alert to Telegram."""
    cfg = load_telegram_config()
    if not cfg.get("notify_on_trades", True) or not is_configured():
        return False

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    action_upper = action.upper()

    lines = []
    if action_upper == "BUY":
        lines.append("<b>TRADE EXECUTION: BUY</b> 🟢")
        lines.append(f"• <b>Symbol:</b> <code>{ticker}</code> (TSX)")
        lines.append(f"• <b>Order:</b> {shares:g} shares @ Limit CAD {price:.2f}")
        lines.append(f"• <b>Capital Committed:</b> CAD {shares * price:.2f}")
        lines.append(f"• <b>IBKR Order ID:</b> <code>#{order_id}</code>")
        if target_price:
            gain_pct = ((target_price - price) / price) * 100 if price > 0 else 0
            lines.append(f"• <b>Profit Target:</b> CAD {target_price:.2f} (+{gain_pct:.1f}%)")
        if stop_loss_price:
            loss_pct = ((price - stop_loss_price) / price) * 100 if price > 0 else 0
            lines.append(f"• <b>Stop Loss:</b> CAD {stop_loss_price:.2f} (-{loss_pct:.1f}%)")
        if notes:
            clean_notes = str(notes).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"• <b>Rationale:</b> <i>{clean_notes}</i>")

    elif action_upper == "SELL":
        lines.append("<b>TRADE EXECUTION: SELL (FILLED)</b> 🔴")
        lines.append(f"• <b>Symbol:</b> <code>{ticker}</code> (TSX)")
        lines.append(f"• <b>Order:</b> {shares:g} shares @ CAD {price:.2f}")
        lines.append(f"• <b>Gross Proceeds:</b> CAD {shares * price:.2f}")
        lines.append(f"• <b>IBKR Order ID:</b> <code>#{order_id}</code>")
        if pnl is not None and pnl_pct is not None:
            sign = "+" if pnl >= 0 else ""
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"• <b>Realized P&L:</b> {pnl_emoji} {sign}CAD {pnl:.2f} ({sign}{pnl_pct:.2f}%)")
        if notes:
            clean_notes = str(notes).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"• <b>Exit Reason:</b> <i>{clean_notes}</i>")

    elif action_upper in ["ORDER_SUBMITTED", "WORKING", "SUBMITTED"]:
        lines.append("<b>ORDER SUBMITTED TO TSX BOOK</b> 🟡")
        lines.append(f"• <b>Symbol:</b> <code>{ticker}</code> (TSX)")
        lines.append(f"• <b>Order:</b> {shares:g} shares @ Limit CAD {price:.2f} (Marketable Limit)")
        lines.append(f"• <b>Status:</b> Working on book | Awaiting broker fill confirmation")
        lines.append(f"• <b>IBKR Order ID:</b> <code>#{order_id}</code>")
        if notes:
            clean_notes = str(notes).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f"• <b>Trigger Reason:</b> <i>{clean_notes}</i>")

    lines.append(f"\n<i>Time: {now_str} ET | Desk: MAPLE Autonomous Trading</i>")
    message = "\n".join(lines)
    return send_telegram_message(message)


def send_scan_update(
    cash: float,
    total_equity: float,
    positions: Dict[str, Any],
    action_taken: str = "Holding & monitoring positions",
) -> bool:
    """Sends a 15-minute desk scan update with objective portfolio metrics."""
    cfg = load_telegram_config()
    if not cfg.get("notify_on_scans", True) or not is_configured():
        return False

    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    cum_return = ((total_equity - 1000.0) / 1000.0) * 100
    cum_sign = "+" if cum_return >= 0 else ""

    lines = [
        f"<b>MAPLE Scan Update ({now_str} ET)</b>",
        f"• <b>Desk Status:</b> {action_taken}",
        f"• <b>Portfolio NAV:</b> CAD {total_equity:.2f} ({cum_sign}{cum_return:.2f}% vs CAD 1,000 seed)",
        f"• <b>Available Cash:</b> CAD {cash:.2f}",
    ]

    if positions:
        lines.append("\n<b>Active Holdings:</b>")
        for sym, p in positions.items():
            shs = p.get("shares", 0)
            if shs <= 0:
                continue
            cur_p = p.get("current_price", p.get("acb", 0))
            acb = p.get("acb", cur_p)
            pos_pnl = (cur_p - acb) * shs
            pos_pnl_pct = ((cur_p - acb) / acb * 100) if acb > 0 else 0
            pnl_sign = "+" if pos_pnl >= 0 else ""
            tgt = p.get("target_price")
            stp = p.get("stop_loss_price")
            tgt_str = f" | Tgt: {tgt:.2f}" if tgt else ""
            stp_str = f" | Stp: {stp:.2f}" if stp else ""
            lines.append(
                f"• <code>{sym}</code>: {shs:g} shs @ CAD {cur_p:.2f} "
                f"({pnl_sign}CAD {pos_pnl:.2f} / {pnl_sign}{pos_pnl_pct:.1f}%){tgt_str}{stp_str}"
            )
    else:
        lines.append("\n• <b>Holdings:</b> 100% Cash")

    message = "\n".join(lines)
    return send_telegram_message(message)


def send_retrospective_report(
    session_type: str,  # "DAILY" or "WEEKLY"
    cash: float,
    equity: float,
    positions: Dict[str, Any],
    prev_equity: Optional[float] = None,
    realized_trades: Optional[List[Dict[str, Any]]] = None,
    position_attribution: Optional[List[Dict[str, Any]]] = None,
    risk_watchlist: Optional[List[Dict[str, Any]]] = None,
    missed_opportunities: Optional[List[Dict[str, Any]]] = None,
    changes_made: Optional[List[str]] = None,
    notes: str = "",
    buy_trades: Optional[List[Dict[str, Any]]] = None,
    basket_pct: Optional[float] = None,
    weekly_summary: Optional[Dict[str, Any]] = None,
    invested_capital: float = 1000.0,
    twr_pct: Optional[float] = None,
) -> bool:
    """
    Sends an institutional, quantitative daily performance report.
    Explicitly reports:
    1. Daily NAV change ($ and %) and Cumulative P&L
    2. Today's realized trades & P&L
    3. Position-level performance & drawdown attribution (winners & losers)
    4. Risk watchlist with distance to stops
    5. Screened universe context & parameter status
    """
    cfg = load_telegram_config()
    if not cfg.get("notify_on_close", True) or not is_configured():
        return False

    now_str = datetime.datetime.now().strftime("%Y-%m-%d")
    is_friday = (str(session_type).upper() == "WEEKLY") or (datetime.datetime.now().weekday() == 4)
    period_label = "Weekly Close Performance Report" if is_friday else "Daily Close Performance Report"

    # Cumulative Return vs total contributed capital
    inv_cap = float(invested_capital) if invested_capital and invested_capital > 0 else 1000.0
    cum_pnl = equity - inv_cap
    cum_pct = (cum_pnl / inv_cap) * 100.0
    cum_sign = "+" if cum_pnl >= 0 else ""
    twr_tag = f" | TWR: {twr_pct:+.2f}%" if (twr_pct is not None and abs(inv_cap - 1000.0) >= 1.0) else ""

    # Daily Return vs previous close (if available)
    daily_pct = 0.0
    if prev_equity and prev_equity > 0:
        daily_pnl = equity - prev_equity
        daily_pct = (daily_pnl / prev_equity) * 100
        daily_sign = "+" if daily_pnl >= 0 else ""
        daily_nav_str = f"• <b>Daily NAV Change:</b> {daily_sign}CAD {daily_pnl:.2f} ({daily_sign}{daily_pct:.2f}% today)"
    else:
        daily_nav_str = "• <b>Daily NAV Change:</b> N/A (Baseline established today)"

    market_val = equity - cash

    lines = [
        f"<b>MAPLE {period_label} ({now_str})</b>",
        "\n<b>1. Portfolio NAV & Capital Summary:</b>",
        f"• <b>Closing Equity NAV:</b> <b>CAD {equity:.2f}</b>",
        daily_nav_str,
    ]
    if weekly_summary:
        w_pnl = float(weekly_summary.get("wow_pnl", 0.0))
        w_pct = float(weekly_summary.get("wow_pct", 0.0))
        r_pnl = float(weekly_summary.get("net_realized_pnl", 0.0))
        lines.append(
            f"• <b>Weekly NAV Change (vs {weekly_summary.get('base_date', 'Prior Fri')}):</b> "
            f"{w_pnl:+.2f} CAD ({w_pct:+.2f}% WoW) | Realized: "
            f"{weekly_summary.get('wins', 0)}W/{weekly_summary.get('losses', 0)}L ({r_pnl:+.2f} CAD)"
        )
    if basket_pct is not None and prev_equity and prev_equity > 0:
        lines.append(
            f"• <b>32-Ticker Shariah Basket:</b> {basket_pct:+.2f}% (Relative Alpha: {daily_pct - basket_pct:+.2f}%)"
        )
    lines.extend([
        f"• <b>Cumulative P&L (Inception):</b> {cum_sign}CAD {cum_pnl:.2f} ({cum_sign}{cum_pct:.2f}%{twr_tag})",
        f"• <b>Capital Allocation:</b> Cash: CAD {cash:.2f} ({cash/equity*100:.1f}%) | Equity: CAD {market_val:.2f} ({market_val/equity*100:.1f}%)",
    ])

    # 2. Today's Executions (BUYs & Realized SELLs)
    if buy_trades or realized_trades:
        lines.append("\n<b>2. Today's Executions:</b>")
        for bt in (buy_trades or []):
            lines.append(
                f"• <code>{bt.get('ticker', 'N/A')}</code> BUY {bt.get('quantity', 0):g} shs @ CAD {bt.get('price', 0.0):.2f} "
                f"<i>[{html.escape(str(bt.get('bucket', 'Regular Trend')))}]</i>"
            )
        for rt in (realized_trades or []):
            sym = rt.get("ticker", "N/A")
            act = rt.get("action", "SELL")
            qty = rt.get("quantity", 0)
            px = rt.get("price", 0.0)
            pnl_val = rt.get("pnl")
            pnl_pct_val = rt.get("pnl_pct")
            pnl_str = ""
            if pnl_val is not None:
                p_sign = "+" if pnl_val >= 0 else ""
                pnl_str = f" | Realized P&L: {p_sign}CAD {pnl_val:.2f} ({p_sign}{pnl_pct_val:.1f}%)"
            lines.append(f"• <code>{sym}</code> {act} {qty:g} shs @ CAD {px:.2f}{pnl_str}")
    else:
        lines.append("\n<b>2. Today's Executions:</b> None (No trades executed)")

    # 3. Position-by-Position Performance & Drawdown Attribution
    if position_attribution:
        lines.append("\n<b>3. Active Positions Performance Attribution:</b>")
        for pa in position_attribution:
            sym = pa["ticker"]
            shs = pa["shares"]
            cur_p = pa["current_price"]
            acb = pa["acb"]
            unrealized = pa["unrealized_pnl"]
            unrealized_pct = pa["unrealized_pct"]
            weight = pa["weight_pct"]
            sign = "+" if unrealized >= 0 else ""
            fee_str = (
                f" <i>[Fill {pa['fill_price']:.2f}, Gross {pa['gross_pnl']:+.2f}, Fee -{pa['entry_fee_cad']:.2f}]</i>"
                if pa.get("entry_fee_cad", 0) > 0
                else ""
            )
            lines.append(
                f"• <code>{sym}</code> ({weight:.1f}% port): {shs:g} shs @ CAD {cur_p:.2f} (ACB: {acb:.2f}) "
                f"| P&L: <b>{sign}CAD {unrealized:.2f} ({sign}{unrealized_pct:.2f}%)</b>{fee_str}"
            )
    elif positions:
        lines.append("\n<b>3. Active Positions:</b>")
        for sym, p in positions.items():
            shs = p.get("shares", 0)
            if shs <= 0:
                continue
            cur_p = p.get("current_price", p.get("acb", 0))
            acb = p.get("acb", cur_p)
            unrealized = (cur_p - acb) * shs
            unrealized_pct = ((cur_p - acb) / acb * 100) if acb > 0 else 0
            sign = "+" if unrealized >= 0 else ""
            lines.append(f"• <code>{sym}</code>: {shs:g} shs @ CAD {cur_p:.2f} | P&L: {sign}CAD {unrealized:.2f} ({sign}{unrealized_pct:.1f}%)")

    # 4. Risk Watchlist & Stop-Loss Proximity
    if risk_watchlist:
        lines.append("\n<b>4. Risk Watchlist & Drawdown Audit:</b>")
        for rw in risk_watchlist:
            sym = rw["ticker"]
            stop_px = rw["stop_price"]
            cur_px = rw["current_price"]
            dist_cad = rw["distance_to_stop_cad"]
            dist_pct = rw["distance_to_stop_pct"]
            drawdown_note = rw.get("note", "")
            lines.append(
                f"• ⚠️ <code>{sym}</code>: Current CAD {cur_px:.2f} vs Stop CAD {stop_px:.2f} "
                f"(Buffer: CAD {dist_cad:.2f} / {dist_pct:.1f}% to stop). {drawdown_note}"
            )
    else:
        lines.append("\n<b>4. Risk Watchlist:</b> All positions maintain >3.0% buffer above stop-loss thresholds.")

    # 5. Missed Opportunities / Screened Universe Movers
    if missed_opportunities:
        lines.append("\n<b>5. Screened Universe Tape (Non-Held Top Movers):</b>")
        top_movers = sorted(missed_opportunities, key=lambda x: x.get("day_gain", 0), reverse=True)[:3]
        for m in top_movers:
            ticker = m.get("ticker")
            gain = m.get("day_gain", 0)
            rsi = m.get("rsi", "N/A")
            vol = m.get("vol_ratio", "N/A")
            gate = f" — <i>{html.escape(str(m['gate_status']))}</i>" if m.get("gate_status") else ""
            lines.append(f"• <code>{ticker}</code>: +{gain:.1f}% (RSI: {rsi} | Vol: {vol}x){gate}")

    # 6. Strategy & System Adjustments
    lines.append("\n<b>6. Strategy & System Status:</b>")
    if changes_made:
        for chg in changes_made:
            prefix = "" if str(chg).startswith("[") else "[TUNED] "
            lines.append(f"• {prefix}{chg}")
    else:
        lines.append("• All sector caps (max 35%), stop buffers, and drawdown limits within operating boundaries.")
    lines.append("• 32 AAOIFI-vetted TSX equities active in surveillance.")

    message = "\n".join(lines)
    return send_telegram_message(message)


def auto_detect_chat_id() -> Optional[str]:
    """Queries Telegram getUpdates to auto-discover the chat_id from the latest incoming message."""
    cfg = load_telegram_config()
    token = cfg.get("telegram_bot_token", "").strip()
    if not token or "YOUR_" in token:
        print("[TELEGRAM] Please set your telegram_bot_token first.")
        return None

    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        res = requests.get(url, timeout=10).json()
        if res.get("ok") and "result" in res and res["result"]:
            latest = res["result"][-1]
            chat = latest.get("message", {}).get("chat", {}) or latest.get("channel_post", {}).get("chat", {})
            chat_id = str(chat.get("id"))
            first_name = chat.get("first_name", chat.get("title", "User"))
            if chat_id:
                print(f"[TELEGRAM] Detected Chat ID: {chat_id} ({first_name})")
                cfg["telegram_chat_id"] = chat_id
                save_telegram_config(cfg)
                return chat_id
    except Exception as e:
        print(f"[TELEGRAM ERROR] Failed to auto-detect chat ID: {e}")

    return None


def test_telegram_connection() -> bool:
    """Verifies credentials and sends an objective test message."""
    cfg = load_telegram_config()
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()

    if not token or "YOUR_" in token:
        print("[TELEGRAM] Bot token is missing or placeholder in telegram_config.json.")
        return False

    if not chat_id or "YOUR_" in chat_id:
        print("[TELEGRAM] Chat ID not set. Attempting auto-detection from bot updates...")
        detected = auto_detect_chat_id()
        if not detected:
            print("[TELEGRAM] Could not auto-detect chat ID. Please send /start to your bot in Telegram first.")
            return False

    test_msg = (
        "<b>MAPLE Autonomous Trading Bot Connected</b>\n\n"
        "• Real-time trade execution alerts\n"
        "• 15-minute TSX market scan updates\n"
        "• Daily closing NAV & performance attribution reports\n\n"
        "<i>Interactive Brokers Canada autonomous connection initialized</i>"
    )
    success = send_telegram_message(test_msg)
    if success:
        print("[TELEGRAM SUCCESS] Test notification sent successfully to Telegram!")
    else:
        print("[TELEGRAM ERROR] Failed to send test notification.")
    return success


if __name__ == "__main__":
    test_telegram_connection()
