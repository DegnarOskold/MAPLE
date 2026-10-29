"""
MAPLE Brain Engine
Orchestrates:
1. Fetching live TSX technical indicators locally via maple_market + real-time IBKR Level-1 quotes
2. Checking automated profit targets, opening-chop buffered stops, breakeven ratchets, and stagnation exits
3. Autonomous 32-ticker candidate scanning across the Shariah-compliant TSX basket
4. Enforcing macro commodity alignment, Shariah whitelist, sector/concentration caps, and circuit breakers
5. Calculating dynamic tranche size (with small-account 1-share whole-lot floor up to 30% NAV)
6. Executing real Limit Orders on IBKR (or paper trades in SIMULATED mode)
"""

import os
import sys
import json
import re
import datetime
from typing import Dict, Any, List, Optional

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))

from maple_market import (
    get_stock_data,
    get_corporate_calendar,
    prefetch_histories,
    get_macro_alignment,
    is_macro_aligned,
)
from maple_ledger import (
    get_ledger_state,
    execute_buy,
    execute_sell,
    check_target_stops,
    load_config,
    get_broker_client,
    normalize_ticker,
    ticker_aliases,
    SHARIAH_COMPLIANT_BASKET,
)
from maple_strategy import MapleStrategy


def is_market_open() -> bool:
    """Checks if Canadian TSX is in regular trading hours (09:30 - 16:00 EDT Mon-Fri)."""
    now = datetime.datetime.now()
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def is_opening_chop() -> bool:
    """Rule 3 Guard: Checks if TSX is in the volatile opening 30-min window (09:30 - 10:00 EDT)."""
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    chop_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    chop_end = now.replace(hour=10, minute=0, second=0, microsecond=0)
    return chop_start <= now < chop_end


def log_maple_advice(text: str):
    advice_path = os.path.join(MAPLE_DIR, "maple_advice_history.txt")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(advice_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}]\n{text}\n\n")


def fetch_latest_market_prices(
    tickers: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Retrieves local technical indicator data via maple_market and live TSX quotes from IBKR."""
    data = {}
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"
    broker_client = None
    if is_live:
        try:
            broker_client = get_broker_client()
        except Exception:
            broker_client = None

    norm_tickers = [normalize_ticker(raw_t) for raw_t in tickers]
    prefetched = {}
    if len(norm_tickers) > 2:
        try:
            get_corporate_calendar(norm_tickers)
            prefetched = prefetch_histories(norm_tickers)
        except Exception:
            prefetched = {}

    # Step 1: Base indicators from local maple_market engine
    for t in norm_tickers:
        try:
            if t in prefetched:
                try:
                    sd = get_stock_data(t, mode="SHORT", prefetched_hist=prefetched[t])
                except TypeError:
                    sd = get_stock_data(t, mode="SHORT")
            else:
                sd = get_stock_data(t, mode="SHORT")
            if sd and sd.get("Price") not in ("N/A", None):
                data[t] = sd
        except Exception:
            pass

    # Step 2: Overlay live Level-1 quotes from IBKR
    if broker_client and broker_client.is_authenticated():
        try:
            ticker_to_cid = {}
            for raw_t in tickers:
                t = normalize_ticker(raw_t)
                sym = broker_client.search_symbol(t)
                if sym and sym.get("symbolId"):
                    ticker_to_cid[t] = sym["symbolId"]

            if ticker_to_cid:
                quotes = broker_client.get_quotes(list(ticker_to_cid.values()))
                for t, cid in ticker_to_cid.items():
                    q = quotes.get(cid, {})
                    # Never overwrite real-time yfinance TSX quotes with 15-min delayed IBKR snapshots ('6509': 'DB')
                    if q.get("isDelayed", False) and t in data:
                        continue
                    last_p = q.get("lastTradePrice")
                    if last_p and isinstance(last_p, (int, float)) and last_p > 0:
                        if t not in data:
                            data[t] = {}
                        live_px = float(last_p)
                        data[t]["Price"] = live_px
                        if q.get("bidPrice") is not None:
                            data[t]["Bid"] = q.get("bidPrice")
                        if q.get("askPrice") is not None:
                            data[t]["Ask"] = q.get("askPrice")
                        if q.get("openPrice") and q["openPrice"] > 0:
                            data[t]["Open"] = float(q["openPrice"])

                        # Recompute intraday High/Low and Pct_From_Low using live IBKR quote
                        low_candidates = [
                            float(x) for x in (data[t].get("Low"), q.get("lowPrice"), live_px)
                            if isinstance(x, (int, float)) and x > 0
                        ]
                        if low_candidates:
                            eff_low = min(low_candidates)
                            data[t]["Low"] = eff_low
                            data[t]["Pct_From_Low"] = round(((live_px - eff_low) / eff_low) * 100.0, 2)
                        high_candidates = [
                            float(x) for x in (data[t].get("High"), q.get("highPrice"), live_px)
                            if isinstance(x, (int, float)) and x > 0
                        ]
                        if high_candidates:
                            data[t]["High"] = max(high_candidates)

                        # Re-validate 6-part EMA_Crossover against live IBKR price (Flaw 2 & Flaw 5 guard)
                        ema_5 = data[t].get("EMA_5")
                        ema_9 = data[t].get("EMA_9")
                        if isinstance(ema_5, (int, float)) and ema_5 > 0:
                            if isinstance(ema_9, (int, float)) and ema_5 < ema_9:
                                data[t]["EMA_Crossover"] = "BEARISH (EMA5 < EMA9)"
                            elif data[t].get("EMA_Crossover") == "BULLISH (EMA5 > EMA9)":
                                if live_px < ema_5 or ((live_px - ema_5) / ema_5) > (MapleStrategy.MAX_EMA5_EXTENSION_PCT / 100.0):
                                    data[t]["EMA_Crossover"] = "NEUTRAL (FILTERED)"
        except Exception as e:
            print(f"[MAPLE WARNING] Live IBKR quote overlay error: {e}")

    return data


def parse_bot_signals(bot_advice_text: str) -> List[Dict[str, Any]]:
    """Extracts explicit BUY and SELL actions from the bot's advice text."""
    signals = []
    lines = bot_advice_text.splitlines()

    for line in lines:
        cleaned = line.strip().strip("*").strip()
        upper_line = cleaned.upper()
        if any(neg in upper_line for neg in ["DO NOT BUY", "DON'T BUY", "DO NOT SELL", "DON'T SELL", "AVOID", "PREVIOUSLY", "SKIP"]):
            continue

        # 1. Match Sells: "🔴 **SELL ALERT: CLS.TO (...)**", "SELL ALERT: CCL-B.TO", "1. SELL CCL-B.TO", "SELL CCL-B.TO"
        sell_match = re.search(
            r"^(?:(?:\d+[\.\)]\s*)|(?:🔴\s*))?\*{0,2}SELL(?:\s+ALERT:?)?\*{0,2}\s+\*{0,2}([A-Z0-9\-\.]+(?:\.TO|=F)?)\*{0,2}",
            cleaned,
            re.IGNORECASE,
        )
        if sell_match:
            candidate = sell_match.group(1).upper()
            if candidate in ["ALERT", "TRIGGERS", "IMMEDIATE", "ACTION", "NOW"]:
                continue
            ticker = candidate if (candidate.endswith(".TO") or candidate.endswith("=F")) else f"{candidate}.TO"
            signals.append(
                {"action": "SELL", "ticker": normalize_ticker(ticker), "signal_type": "SELL", "raw_line": cleaned}
            )
            continue

        # 2. Match Buys: "1. BUY ATRL.TO", "BUY ATRL.TO", "SHOP.TO [REGULAR BUY]", "CCO.TO [CAPITULATION REVERSAL]"
        buy_match_numbered = re.search(
            r"(?:^\d+[\.\)]\s*)BUY\s+([A-Z0-9\-\.]+)", cleaned, re.IGNORECASE
        )
        buy_match_bracket = re.search(
            r"(?:(?:🟢|🟣|🟡)?\s*)?(?:\d+[\.\)]\s*)?\*{0,2}([A-Z0-9\-\.]+)\*{0,2}\s*(?:\[|\u2014|--|-)\s*\*{0,2}(REGULAR BUY|CAPITULATION REVERSAL|LOW-VOLUME SCALED ENTRY|BUY)(?:\]|\b)",
            cleaned,
            re.IGNORECASE,
        )

        if buy_match_numbered:
            ticker = buy_match_numbered.group(1).upper()
            if not ticker.endswith(".TO") and not ticker.endswith("=F"):
                ticker += ".TO"
            signals.append(
                {"action": "BUY", "ticker": normalize_ticker(ticker), "signal_type": "REGULAR", "raw_line": cleaned}
            )
        elif buy_match_bracket:
            ticker = buy_match_bracket.group(1).upper()
            sig_type = buy_match_bracket.group(2).upper()
            if not ticker.endswith(".TO") and not ticker.endswith("=F"):
                ticker += ".TO"
            signals.append(
                {"action": "BUY", "ticker": normalize_ticker(ticker), "signal_type": sig_type, "raw_line": cleaned}
            )

    return signals


def evaluate_autonomous_signals(
    market_data: Dict[str, Dict[str, Any]],
    allowed_tickers: set,
    macro_state: Optional[Dict[str, bool]] = None,
    max_share_price: Optional[float] = None,
    held_tickers: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Directly scans all 32 Shariah-compliant TSX tickers for Trend Momentum and Capitulation Reversal setups."""
    MapleStrategy._sync_from_config()
    candidates = []
    held_norm = {normalize_ticker(t) for t in held_tickers} if held_tickers else set()

    for raw_t in sorted(allowed_tickers):
        ticker = normalize_ticker(raw_t)
        if ticker not in SHARIAH_COMPLIANT_BASKET:
            continue
        sd = market_data.get(ticker)
        if not sd or not isinstance(sd.get("Price"), (int, float)) or sd["Price"] <= 0:
            continue
        if max_share_price and max_share_price > 0 and ticker not in held_norm and sd["Price"] > max_share_price:
            continue

        rsi = sd.get("RSI_7")
        vol_ratio = sd.get("Vol_Ratio")
        ema_cross = str(sd.get("EMA_Crossover", ""))

        is_cap_cand = (
            isinstance(rsi, (int, float))
            and rsi < MapleStrategy.RSI_OVERSOLD_MAX
            and isinstance(vol_ratio, (int, float))
            and vol_ratio >= MapleStrategy.VOLUME_CAPITULATION_RATIO
        )
        if is_cap_cand:
            cand_type = "CAPITULATION REVERSAL"
        elif ema_cross == "BULLISH (EMA5 > EMA9)":
            cand_type = (
                "REGULAR BUY"
                if (isinstance(vol_ratio, (int, float)) and vol_ratio >= MapleStrategy.VOLUME_CAPITULATION_RATIO)
                else "LOW-VOLUME SCALED ENTRY"
            )
        else:
            continue

        tranche_pct, rationale = MapleStrategy.calculate_tranche_size(sd, signal_type=cand_type)
        if tranche_pct <= 0.0:
            print(f"[MAPLE FILTER] {ticker} ({cand_type}): {rationale}")
            continue

        aligned, macro_reason = is_macro_aligned(ticker, macro_state)
        if not aligned:
            print(f"[MAPLE MACRO FILTER] {ticker} ({cand_type}): Suppressed - {macro_reason}")
            continue

        vr_val = float(vol_ratio) if isinstance(vol_ratio, (int, float)) else 0.0
        adx_val = float(sd.get("ADX_14")) if isinstance(sd.get("ADX_14"), (int, float)) else 0.0
        candidates.append(
            {
                "action": "BUY",
                "ticker": ticker,
                "signal_type": cand_type,
                "tranche_pct": tranche_pct,
                "rationale": rationale,
                "_rank": (tranche_pct, vr_val, adx_val),
            }
        )

    candidates.sort(key=lambda c: c["_rank"], reverse=True)
    for c in candidates:
        c.pop("_rank", None)
    return candidates


def run_chop_exit_guard() -> Dict[str, Any]:
    """Fast 5-minute opening chop monitor (9:30 - 10:00 AM ET).
    Scans ONLY held assets for profit targets or stop-loss hits to harvest algorithmic spikes.
    Zero buy orders permitted under Rule 3.
    """
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n[MAPLE CHOP EXIT GUARD STARTED] {now_str} ET")

    state = get_ledger_state()
    held_positions = {
        normalize_ticker(t): p for t, p in state.get("positions", {}).items() if p.get("shares", 0) > 0
    }

    if not held_positions:
        print("[MAPLE CHOP GUARD] Portfolio is 100% Cash Fortress. No open positions to monitor. Standing by for 10:00 AM offensive scan.")
        return {"status": "NO_POSITIONS", "action": "NONE"}

    tickers = list(held_positions.keys())
    print(f"[MAPLE CHOP GUARD] Monitoring held assets for algorithmic liquidity spikes: {', '.join(tickers)}")

    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"
    price_map = {}

    # Step 1: Fetch real-time TSX quotes via yfinance first
    for t in tickers:
        try:
            sd = get_stock_data(t, mode="SHORT")
            if sd and sd.get("Price") not in ("N/A", None):
                price_map[t] = float(sd["Price"])
        except Exception:
            pass

    # Step 2: Overlay IBKR Level-1 quote ONLY when real-time (or as fallback if yfinance failed)
    if is_live:
        try:
            client = get_broker_client()
            if client and client.is_authenticated():
                for t in tickers:
                    sym = client.search_symbol(t)
                    if sym:
                        q = client.get_quote(sym["symbolId"])
                        if q.get("isDelayed", False) and t in price_map:
                            continue
                        price = q.get("lastTradePrice") or q.get("bidPrice")
                        if price and isinstance(price, (int, float)) and price > 0:
                            price_map[t] = float(price)
        except Exception as e:
            print(f"[CHOP GUARD WARNING] Live broker quote error: {e}")

    if not price_map:
        print("[MAPLE CHOP GUARD] Quotes currently unavailable for held assets. Holding standing positions.")
        return {"status": "PRICE_UNAVAILABLE", "action": "NONE"}

    # Display price vs target status (with opening-chop stop buffer)
    active_targets = config.get("active_targets", {})
    chop_buf_pct = float(config.get("chop_stop_buffer_pct", 2.0))
    for t, p in price_map.items():
        target_info = None
        for alias in ticker_aliases(t):
            if alias in active_targets:
                target_info = active_targets[alias]
                break
        tgt = target_info.get("target_price", "N/A") if target_info else "N/A"
        stp = target_info.get("stop_loss_price", "N/A") if target_info else "N/A"
        stp_disp = (
            f"CAD {stp} [Chop Floor: CAD {round(float(stp) * (1.0 - chop_buf_pct / 100.0), 2):.2f}]"
            if isinstance(stp, (int, float))
            else str(stp)
        )
        print(f"  * {t}: Current CAD {p:.2f} | Target: CAD {tgt} | Stop: {stp_disp}")

    # Evaluate target and opening-chop buffered stop triggers
    check_target_stops(price_map, is_chop_window=True)

    print(f"[MAPLE CHOP EXIT GUARD COMPLETE] {datetime.datetime.now().strftime('%H:%M:%S')} ET\n")
    return {"status": "SUCCESS", "monitored": tickers}


def run_intraday_scan(bot_advice: str = ""):
    """Executes an interval scan for MAPLE."""
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"

    if is_opening_chop() and is_live:
        print("[MAPLE RULE 3] Opening Chop window (9:30 - 10:00 AM ET). Routing to fast Held-Assets Exit Guard...")
        return run_chop_exit_guard()

    allowed_tickers = set(normalize_ticker(t) for t in config.get("allowed_tickers", []))
    ledger_state = get_ledger_state()

    print(f"\n[MAPLE SCAN STARTED] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {ledger_state.get('mode', 'SIMULATED')} | Available Cash: ${ledger_state['cash']:.2f}")

    market_active = is_market_open()
    if not market_active and is_live:
        print("[MAPLE NOTICE] TSX is currently outside regular trading hours (9:30 AM - 4:00 PM ET).")

    # Step 1: Fetch live prices
    market_data = fetch_latest_market_prices(list(allowed_tickers))
    price_map = {
        t: d["Price"]
        for t, d in market_data.items()
        if isinstance(d.get("Price"), (int, float))
    }

    # Step 2: Auto Target, Stop-Loss, Breakeven Ratchet & Stagnation Exit Check (Intraday execution)
    print("Checking automatic profit targets, stop-losses, breakeven ratchets, and 4-day stagnation exits...")
    check_target_stops(
        price_map,
        market_data=market_data,
        allow_stagnation_exit=(market_active or not is_live) and not is_opening_chop(),
    )

    # Step 3: Evaluate autonomous 32-ticker candidate setups (or explicit CLI override text)
    config = load_config()
    if bot_advice:
        signals = parse_bot_signals(bot_advice)
        print(f"Extracted {len(signals)} explicit signal(s) from CLI input.")
    else:
        macro_state = get_macro_alignment()
        nav_est = float(ledger_state.get("total_equity") or ledger_state.get("cash", 0.0))
        max_share_px = min(
            float(config.get("max_single_order_cad", 400.0)),
            nav_est * max(float(config.get("max_position_pct", 0.25)), float(config.get("max_single_share_nav_pct", 0.30))),
        )
        held_set = {normalize_ticker(t) for t, p in ledger_state.get("positions", {}).items() if p.get("shares", 0) > 0}
        signals = evaluate_autonomous_signals(
            market_data, allowed_tickers, macro_state=macro_state, max_share_price=max_share_px, held_tickers=held_set
        )
        print(
            f"Evaluated {len(market_data)}/{len(allowed_tickers)} Shariah-compliant TSX tickers -> "
            f"{len(signals)} actionable signal(s) (Macro: GC=F={'UP' if macro_state.get('GC=F', True) else 'DOWN'}, "
            f"CL=F={'UP' if macro_state.get('CL=F', True) else 'DOWN'})."
        )

    if signals:
        for sig in signals:
            ticker = normalize_ticker(sig["ticker"])
            action = sig["action"]
            sig_type = sig.get("signal_type", "REGULAR")

            # Circuit Breaker: Whitelist Gatekeeper
            if ticker not in allowed_tickers or ticker not in SHARIAH_COMPLIANT_BASKET:
                print(f"[MAPLE GUARD REJECT] {ticker} - Not in allowed Shariah-compliant basket!")
                continue

            current_price = price_map.get(ticker)
            if not current_price or not isinstance(current_price, (int, float)):
                print(f"[MAPLE] Price unavailable for {ticker}, skipping trade.")
                continue

            stock_info = market_data.get(ticker, {})

            if action == "SELL":
                raw_reason = sig.get('raw_line', 'SELL').encode('ascii', 'ignore').decode('ascii')
                execute_sell(
                    ticker,
                    current_price,
                    reason=f"Signal: {raw_reason}",
                )

            elif action == "BUY":
                if not market_active and is_live:
                    print(f"[MAPLE NOTICE] Skipping live BUY order for {ticker}: TSX market closed.")
                    continue

                if is_opening_chop() and is_live:
                    print(f"[MAPLE RULE 3 GUARD] Skipping live BUY order for {ticker}: Opening Chop Guard active (9:30 AM - 10:00 AM ET).")
                    continue

                # Dynamic Sizing based on technical strength and signal type
                if "tranche_pct" in sig and "rationale" in sig:
                    tranche_pct, rationale = float(sig["tranche_pct"]), str(sig["rationale"])
                else:
                    tranche_pct, rationale = MapleStrategy.calculate_tranche_size(stock_info, signal_type=sig_type)

                if tranche_pct <= 0.0:
                    print(f"[MAPLE SIZING BLOCKED] {ticker}: {rationale}")
                    continue

                curr_cash = get_ledger_state()["cash"]
                allocated = round(curr_cash * tranche_pct, 2)
                raw_shs = allocated / current_price
                estimated_shares = int(raw_shs) + (1 if int(raw_shs) >= 1 and (raw_shs - int(raw_shs)) >= 0.5 and (int(raw_shs) + 1) * current_price <= allocated * 1.15 else 0)
                estimated_shares = max(1, estimated_shares)

                target, stop = MapleStrategy.calculate_targets(
                    current_price, stock_info, shares=estimated_shares, cost_basis=current_price
                )

                print(
                    f"[MAPLE SIZING] {ticker}: {tranche_pct*100:.1f}% tranche (${allocated:.2f}, ~{estimated_shares} shs) | Target: ${target:.2f} | Stop: ${stop:.2f} | Logic: {rationale}"
                )
                execute_buy(
                    ticker,
                    allocated,
                    current_price,
                    target_price=target,
                    stop_loss_price=stop,
                    notes=f"[{sig_type}] Dynamic Tranche {tranche_pct*100:.1f}% ({rationale})",
                    open_price=stock_info.get("Open"),
                )

        log_maple_advice("Processed Autonomous Signals:\n" + json.dumps(signals, indent=2))

    # Output current portfolio equity using real-time price_map marks when available
    updated_state = get_ledger_state()
    refreshed_marks = False
    for t, p in updated_state.get("positions", {}).items():
        if p.get("shares", 0) > 0 and t in price_map:
            p["current_price"] = price_map[t]
            refreshed_marks = True

    total_equity = updated_state.get("total_equity")
    if total_equity is None or refreshed_marks:
        total_equity = round(
            updated_state["cash"]
            + sum(
                p["shares"] * p.get("current_price", price_map.get(t, p["acb"]))
                for t, p in updated_state.get("positions", {}).items()
                if p.get("shares", 0) > 0
            ),
            2,
        )

    print(f"[MAPLE SCAN COMPLETE] Total Equity: ${total_equity:.2f} CAD\n")

    # Dispatch Telegram interval update
    try:
        from telegram_notifier import send_scan_update
        action_msg = f"Processed {len(signals)} trade signal(s)" if signals else "Holding & monitoring positions"
        send_scan_update(
            cash=updated_state["cash"],
            total_equity=total_equity,
            positions=updated_state.get("positions", {}),
            action_taken=action_msg,
        )
    except Exception:
        pass
    return {"status": "SUCCESS", "total_equity": round(total_equity, 2)}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--chop-guard", "--chop", "--exit-guard"):
        run_chop_exit_guard()
    else:
        test_advice = ""
        if len(sys.argv) > 1:
            test_advice = " ".join(sys.argv[1:])
        run_intraday_scan(test_advice)
