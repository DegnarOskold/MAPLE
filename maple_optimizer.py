"""
MAPLE Optimizer & Retrospective Learning Engine
Runs at daily market close (4:10 PM ET) and weekly close (Friday 4:30 PM ET).

Objectives:
1. Quantitative daily and weekly portfolio performance audit:
   - Closing NAV vs Starting/Previous Close NAV (Daily $ and % delta).
   - Realized trades and P&L from today's executions.
   - Position-by-position performance and drawdown attribution (identifies primary detractors and winners).
   - Risk audit on losing positions (distance to stop loss, volatility, position concentration).
2. Retrospective analysis of screened 32-asset universe:
   - Missed opportunities (stocks that broke out without triggering a buy).
3. Strategy parameter tuning within defined limits:
   - Tunes volume capitulation, tranche sizing, and ATR target multiples when warranted by tape data.
4. Comprehensive audit logging to maple_logic_changelog.md and Telegram performance reporting.
"""

import os
import sys
import csv
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANGELOG_FILE = os.path.join(MAPLE_DIR, "maple_logic_changelog.md")
NAV_FILE = os.path.join(MAPLE_DIR, "maple_daily_nav.json")
TRADES_FILE = os.path.join(MAPLE_DIR, "maple_trades.csv")

from maple_market import get_stock_data, get_corporate_calendar, prefetch_histories
from maple_ledger import (
    load_config,
    save_config,
    get_ledger_state,
    get_net_contributions,
    get_total_invested_capital,
    compute_twr_pct,
    get_ticker_sector,
    get_position_holding_days,
    get_position_last_buy_info,
    normalize_ticker,
)
from maple_strategy import MapleStrategy


def log_to_changelog(entry: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CHANGELOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n### Optimization Log [{timestamp}]\n{entry}\n")


def load_nav_history() -> Dict[str, Any]:
    if os.path.exists(NAV_FILE):
        try:
            with open(NAV_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_nav_snapshot(date_str: str, nav: float, cash: float, positions: Dict[str, Any]):
    history = load_nav_history()
    history[date_str] = {
        "nav": round(nav, 2),
        "cash": round(cash, 2),
        "positions": {
            sym: {
                "shares": p.get("shares", 0),
                "acb": round(p.get("acb", 0), 2),
                "close_price": round(p.get("current_price", p.get("acb", 0)), 2),
                "unrealized_pnl": round((p.get("current_price", p.get("acb", 0)) - p.get("acb", 0)) * p.get("shares", 0), 2)
            }
            for sym, p in positions.items()
            if p.get("shares", 0) > 0
        }
    }
    with open(NAV_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)


def get_previous_close_info(today_str: str) -> Tuple[Optional[str], Optional[float]]:
    history = load_nav_history()
    previous_dates = [d for d in sorted(history.keys()) if d < today_str]
    if previous_dates:
        last_date = previous_dates[-1]
        return last_date, history[last_date].get("nav")
    return None, None


def get_previous_close_nav(today_str: str) -> Optional[float]:
    return get_previous_close_info(today_str)[1]


def get_weekly_summary(
    today_str: str,
    current_equity: float,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Computes cash-flow-adjusted week-over-week NAV delta and weekly realized trade stats."""
    history = load_nav_history()
    today_dt = datetime.date.fromisoformat(today_str[:10])
    monday_str = (today_dt - datetime.timedelta(days=today_dt.weekday())).isoformat()
    prior_dates = [d for d in sorted(history.keys()) if d < monday_str]
    if not prior_dates:
        prior_dates = [d for d in sorted(history.keys()) if d < today_str][:1]
    if not prior_dates:
        return None

    base_date = prior_dates[-1]
    base_nav = float(history[base_date].get("nav") or 0.0)
    if base_nav <= 0:
        return None

    week_flows = get_net_contributions(config, after_date=base_date, up_to_date=today_str)
    adj_base_nav = base_nav + week_flows
    wow_pnl = round(current_equity - adj_base_nav, 2)
    wow_pct = round((wow_pnl / adj_base_nav) * 100.0, 2) if adj_base_nav > 0 else 0.0

    wins, losses, buy_count = 0, 0, 0
    net_realized = 0.0
    if os.path.exists(TRADES_FILE):
        import re
        try:
            with open(TRADES_FILE, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    d_str = row.get("Date", "")[:10]
                    if not (monday_str <= d_str <= today_str):
                        continue
                    act = row.get("Action", "").strip().upper()
                    if act == "BUY":
                        buy_count += 1
                    elif act == "SELL":
                        m = re.search(r"P&L:\s*\$?([-+]?[0-9]*\.?[0-9]+)", row.get("Notes", ""))
                        if m:
                            pval = float(m.group(1))
                            net_realized += pval
                            if pval > 0:
                                wins += 1
                            else:
                                losses += 1
        except Exception:
            pass

    return {
        "base_date": base_date,
        "base_nav": round(base_nav, 2),
        "wow_pnl": wow_pnl,
        "wow_pct": wow_pct,
        "buy_count": buy_count,
        "closed_count": wins + losses,
        "wins": wins,
        "losses": losses,
        "net_realized_pnl": round(net_realized, 2),
    }


def get_daily_realized_trades(today_str: str) -> List[Dict[str, Any]]:
    """Extracts realized SELL trades that occurred today from maple_trades.csv."""
    realized = []
    if not os.path.exists(TRADES_FILE):
        return realized

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trade_date = row.get("Date", "")
                action = row.get("Action", "").upper()
                if trade_date.startswith(today_str) and action == "SELL":
                    notes = row.get("Notes", "")
                    pnl_val = None
                    pnl_pct_val = None
                    # Parse P&L from notes if present: e.g. "P&L: $-19.42 (-11.23%)"
                    import re
                    match = re.search(r"P&L:\s*\$?([-+]?[0-9]*\.?[0-9]+)\s*\(([-+]?[0-9]*\.?[0-9]+)%\)", notes)
                    if match:
                        pnl_val = float(match.group(1))
                        pnl_pct_val = float(match.group(2))

                    realized.append({
                        "ticker": row.get("Ticker", ""),
                        "action": action,
                        "quantity": float(row.get("Quantity", 0)),
                        "price": float(row.get("Price", 0)),
                        "pnl": pnl_val,
                        "pnl_pct": pnl_pct_val,
                        "notes": notes,
                    })
    except Exception as e:
        print(f"[OPTIMIZER WARNING] Failed to read trades for realized P&L: {e}")

    return realized


def get_daily_buy_trades(today_str: str) -> List[Dict[str, Any]]:
    """Extracts BUY fills executed today with 3-bucket signal classification."""
    buys = []
    if not os.path.exists(TRADES_FILE):
        return buys
    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Date", "").startswith(today_str) and row.get("Action", "").upper() == "BUY":
                    notes_up = row.get("Notes", "").upper()
                    bucket = (
                        "Capitulation Reversal"
                        if "CAPITULATION" in notes_up
                        else ("Low-Volume Scaled" if ("LOW-VOLUME" in notes_up or "SCALED" in notes_up) else "Regular Trend")
                    )
                    buys.append({
                        "ticker": row.get("Ticker", ""),
                        "action": "BUY",
                        "quantity": float(row.get("Quantity", 0)),
                        "price": float(row.get("Price", 0)),
                        "bucket": bucket,
                    })
    except Exception as e:
        print(f"[OPTIMIZER WARNING] Failed to read BUY trades: {e}")
    return buys


def calculate_position_attribution(
    positions: Dict[str, Any],
    total_equity: float,
    calendar_map: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Computes performance and risk metrics for each held position:
    - Cost basis (ACB), current market value, unrealized P&L ($ and %)
    - Portfolio concentration (weight %)
    - Stop loss proximity (dollar and percentage distance to stop)
    - Returns (position_attribution, risk_watchlist)
    """
    attribution = []
    risk_watchlist = []
    held_set = {sym for sym, p in positions.items() if float(p.get("shares", 0)) > 0}
    holding_days = get_position_holding_days(active_tickers=held_set)
    buy_info_map = get_position_last_buy_info(active_tickers=held_set)

    for sym, p in positions.items():
        shs = float(p.get("shares", 0))
        if shs <= 0:
            continue
        cur_p = float(p.get("current_price", p.get("acb", 0)))
        acb = float(p.get("acb", cur_p))
        b_info = buy_info_map.get(normalize_ticker(sym), {})
        fill_px = float(b_info.get("fill_acb") or acb)
        fee_drag = round((acb - fill_px) * shs, 2) if (acb - fill_px) >= 0.05 else 0.0
        gross_pnl = round((cur_p - fill_px) * shs, 2) if fee_drag > 0 else round((cur_p - acb) * shs, 2)
        tot_cost = acb * shs
        mkt_val = cur_p * shs
        unrealized = mkt_val - tot_cost
        unrealized_pct = ((cur_p - acb) / acb * 100) if acb > 0 else 0.0
        weight_pct = (mkt_val / total_equity * 100) if total_equity > 0 else 0.0
        stop_px = float(p.get("stop_loss_price") or (acb * 0.95))
        days_held = holding_days.get(sym, 0)
        sector = get_ticker_sector(sym)

        dist_to_stop_cad = cur_p - stop_px
        dist_to_stop_pct = ((cur_p - stop_px) / cur_p * 100) if cur_p > 0 else 0.0

        item = {
            "ticker": sym,
            "sector": sector,
            "days_held": days_held,
            "shares": shs,
            "acb": round(acb, 2),
            "fill_price": round(fill_px, 2),
            "gross_pnl": gross_pnl,
            "entry_fee_cad": fee_drag,
            "current_price": round(cur_p, 2),
            "total_cost": round(tot_cost, 2),
            "market_value": round(mkt_val, 2),
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pct": round(unrealized_pct, 2),
            "weight_pct": round(weight_pct, 1),
            "stop_price": round(stop_px, 2),
            "distance_to_stop_cad": round(dist_to_stop_cad, 2),
            "distance_to_stop_pct": round(dist_to_stop_pct, 2),
        }
        attribution.append(item)

        # Flag for risk watchlist if:
        # 1. Unrealized loss > 1.5%
        # 2. Distance to stop is within 3.0%
        # 3. Position concentration > 25% with negative P&L
        # 4. Held >= STAGNATION_DAYS with negative P&L
        notes = []
        if unrealized_pct <= -1.5:
            notes.append(f"Position drawdown: {unrealized_pct:.1f}%")
        if dist_to_stop_pct <= 3.0:
            notes.append(f"Near stop-loss: {dist_to_stop_pct:.1f}% buffer")
        if weight_pct >= 25.0 and unrealized < 0:
            notes.append(f"High portfolio concentration: {weight_pct:.1f}% of NAV")
        if days_held >= MapleStrategy.STAGNATION_DAYS and unrealized < 0:
            notes.append(f"Stagnant loser: held {days_held}d (>= {MapleStrategy.STAGNATION_DAYS}d)")

        cal_info = (calendar_map or {}).get(normalize_ticker(sym), {})
        earn_td = cal_info.get("trading_days_to_earnings")
        if earn_td is None:
            earn_td = cal_info.get("days_to_earnings")
        if isinstance(earn_td, (int, float)) and 0 <= earn_td <= 3:
            ed_str = cal_info.get("earnings_date", "Soon")
            notes.append(f"Earnings risk in {int(earn_td)} trading day(s) ({ed_str})")

        if notes:
            item_copy = dict(item)
            item_copy["note"] = "; ".join(notes)
            risk_watchlist.append(item_copy)

    # Sort attribution by dollar contribution (detractors first)
    attribution.sort(key=lambda x: x["unrealized_pnl"])
    return attribution, risk_watchlist


def scan_missed_opportunities(
    allowed_tickers: List[str],
    prefetched: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Identifies stocks that gained > 2.0% today or from low of day that MAPLE did not hold,
    filtering out overextended, non-trending, or structurally rejected setups.
    """
    missed = []
    state = get_ledger_state()
    current_held = set(t for t, p in state["positions"].items() if p.get("shares", 0) > 0)

    for ticker in allowed_tickers:
        if ticker in current_held:
            continue
        try:
            data = (
                get_stock_data(ticker, mode="SHORT", prefetched_hist=prefetched[ticker])
                if (prefetched and ticker in prefetched)
                else get_stock_data(ticker, mode="SHORT")
            )
            if not data or data.get("Price") in ("N/A", None):
                continue

            price = data.get("Price", 0.0)
            prev_close = data.get("Prev_Close", price)
            pct_from_low = data.get("Pct_From_Low", 0.0)

            day_gain = ((price - prev_close) / prev_close) * 100 if prev_close > 0 else 0.0

            if day_gain >= 2.0 or (day_gain > 0 and pct_from_low >= 2.5):
                tranche_pct, gate_reason = MapleStrategy.calculate_tranche_size(data)
                gate_status = (
                    f"ELIGIBLE ({tranche_pct*100:.0f}%)"
                    if tranche_pct > 0.0
                    else gate_reason.replace("BLOCKED by ", "").split(" (requires")[0][:130]
                )
                missed.append({
                    "ticker": ticker,
                    "day_gain": round(day_gain, 2),
                    "pct_from_low": round(pct_from_low, 2),
                    "rsi": data.get("RSI_7", "N/A"),
                    "vol_ratio": data.get("Vol_Ratio", "N/A"),
                    "adx": data.get("ADX_14", "N/A"),
                    "ema_crossover": data.get("EMA_Crossover", "N/A"),
                    "eligible": tranche_pct > 0.0,
                    "gate_status": gate_status,
                })
        except Exception:
            pass

    return missed


def run_daily_self_assessment():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"\n[MAPLE DAILY RETROSPECTIVE] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    state = get_ledger_state()
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"
    allowed_tickers = config.get("allowed_tickers", [])

    cash = float(state.get("cash", 0.0))
    equity = float(state.get("total_equity", cash))
    positions = state.get("positions", {})

    # Refresh held position marks with real-time TSX closing prices and compute 32-ticker equal-weight benchmark
    norm_allowed = [normalize_ticker(t) for t in allowed_tickers]
    prefetched = prefetch_histories(norm_allowed) if len(norm_allowed) > 1 else {}
    basket_gains: List[float] = []
    for sym in norm_allowed:
        try:
            sd = (
                get_stock_data(sym, mode="SHORT", prefetched_hist=prefetched[sym])
                if sym in prefetched
                else get_stock_data(sym, mode="SHORT")
            )
            if sd and isinstance(sd.get("Price"), (int, float)) and sd["Price"] > 0:
                if sym in positions and positions[sym].get("shares", 0) > 0:
                    positions[sym]["current_price"] = float(sd["Price"])
                prev_c = sd.get("Prev_Close")
                if isinstance(prev_c, (int, float)) and prev_c > 0:
                    basket_gains.append(((float(sd["Price"]) - float(prev_c)) / float(prev_c)) * 100.0)
        except Exception:
            pass
    refreshed_any = False
    for sym, p in positions.items():
        if p.get("shares", 0) > 0 and sym not in norm_allowed:
            try:
                sd = get_stock_data(sym, mode="SHORT")
                if sd and isinstance(sd.get("Price"), (int, float)) and sd["Price"] > 0:
                    p["current_price"] = float(sd["Price"])
                    refreshed_any = True
            except Exception:
                pass
    if refreshed_any or any(sym in norm_allowed and p.get("shares", 0) > 0 for sym, p in positions.items()):
        equity = round(
            cash + sum(float(p["shares"]) * float(p.get("current_price", p.get("acb", 0))) for p in positions.values() if p.get("shares", 0) > 0),
            2,
        )
    basket_pct = round(sum(basket_gains) / len(basket_gains), 2) if basket_gains else None

    # 1. Historical NAV Tracking & Cash-Flow-Adjusted Daily/Cumulative Delta
    prev_date, raw_prev_equity = get_previous_close_info(today_str)
    day_flows = (
        get_net_contributions(config, after_date=prev_date, up_to_date=today_str)
        if prev_date
        else get_net_contributions(config, up_to_date=today_str)
    )
    prev_equity = round(float(raw_prev_equity) + day_flows, 2) if raw_prev_equity else None
    invested_capital = get_total_invested_capital(config, up_to_date=today_str)
    twr_pct = compute_twr_pct(equity, config=config, today_str=today_str)
    if not is_live or state.get("live_verified", False):
        save_nav_snapshot(today_str, equity, cash, positions)
    else:
        print("[OPTIMIZER WARNING] Broker gateway unauthenticated; skipping maple_daily_nav.json overwrite to protect NAV history.")

    daily_pnl = round(equity - prev_equity, 2) if prev_equity else 0.0
    daily_pct = round((daily_pnl / prev_equity) * 100, 2) if prev_equity else 0.0
    cum_pnl = round(equity - invested_capital, 2)
    cum_pct = round((cum_pnl / invested_capital) * 100, 2) if invested_capital > 0 else 0.0

    # 2. Today's Executions (BUY Entries & Realized SELL Exits)
    buy_trades = get_daily_buy_trades(today_str)
    realized_trades = get_daily_realized_trades(today_str)

    # 3. Position Attribution, Sector Concentration & Risk Watchlist
    held_syms = [normalize_ticker(s) for s, p in positions.items() if float(p.get("shares", 0)) > 0]
    cal_map = get_corporate_calendar(held_syms) if held_syms else {}
    attribution, risk_watchlist = calculate_position_attribution(positions, equity, calendar_map=cal_map)
    max_sector_pct = float(config.get("max_sector_pct", 0.35)) * 100.0
    sector_totals: Dict[str, float] = {}
    for pa in attribution:
        sec = pa.get("sector", "Other")
        sector_totals[sec] = sector_totals.get(sec, 0.0) + float(pa.get("market_value", 0.0))

    # Count today's BUY entries by 3-way signal bucket
    reg_buys = sum(1 for b in buy_trades if b["bucket"] == "Regular Trend")
    scaled_buys = sum(1 for b in buy_trades if b["bucket"] == "Low-Volume Scaled")
    cap_buys = sum(1 for b in buy_trades if b["bucket"] == "Capitulation Reversal")

    # 4. Missed Opportunities
    missed = scan_missed_opportunities(norm_allowed, prefetched=prefetched)
    changes_made = []
    audit_flags = []
    if abs(day_flows) >= 1.0:
        audit_flags.append(
            f"[CAPITAL FLOW] Settled external cash flow CAD {day_flows:+.2f} today; Daily/Weekly/TWR returns cash-flow adjusted."
        )

    for sym in held_syms:
        c_info = cal_map.get(sym, {})
        e_td = c_info.get("trading_days_to_earnings")
        if isinstance(e_td, (int, float)) and 0 <= e_td <= 3:
            audit_flags.append(
                f"[EARNINGS WATCH] Held {sym} reports in {int(e_td)} trading day(s) ({c_info.get('earnings_date', 'Soon')}); stop auto-ratchets to breakeven if green."
            )

    for sec, val in sorted(sector_totals.items(), key=lambda x: x[1], reverse=True):
        sec_pct = (val / equity * 100.0) if equity > 0 else 0.0
        if sec_pct > max_sector_pct:
            audit_flags.append(
                f"[RISK ALERT] {sec} sector concentration at {sec_pct:.1f}% of NAV (cap {max_sector_pct:.0f}%); new {sec} entries gated."
            )

    if daily_pct <= -1.5:
        worst_str = f" (primary open detractor: {attribution[0]['ticker']} CAD {attribution[0]['unrealized_pnl']:+.2f})" if attribution else ""
        audit_flags.append(
            f"[DRAWDOWN AUDIT] Daily NAV delta {daily_pct:+.2f}% (CAD {daily_pnl:+.2f}){worst_str}."
        )
    if buy_trades:
        audit_flags.append(
            f"[SIGNAL ATTRIBUTION] Today's BUY fills ({len(buy_trades)}): {reg_buys} Regular Trend, {scaled_buys} Low-Volume Scaled, {cap_buys} Capitulation Reversal."
        )

    MapleStrategy._sync_from_config()
    if missed:
        print(f"Identified {len(missed)} non-held top basket movers today:")
        for m in missed:
            print(f"  * {m['ticker']}: +{m['day_gain']}% today, +{m['pct_from_low']}% from low (RSI: {m['rsi']}, Vol: {m['vol_ratio']}x | {m.get('gate_status', '')})")

    # 5. Build Comprehensive Quantitative Changelog Entry
    is_friday = datetime.date.fromisoformat(today_str).weekday() == 4
    weekly_summary = get_weekly_summary(today_str, equity, config=config) if is_friday else None
    session_hdr = (
        "Weekly & Daily Market Close Performance Assessment"
        if is_friday
        else "Daily Market Close Performance Assessment"
    )
    day_lbl = "vs Cash-Flow-Adjusted Prior Close" if abs(day_flows) >= 1.0 else "vs Previous Close"
    report = [
        f"**Session Type:** {session_hdr}",
        f"**Portfolio Equity NAV:** CAD {equity:.2f}",
        f"**Daily NAV Change:** CAD {daily_pnl:+.2f} ({daily_pct:+.2f}%) {day_lbl}",
    ]
    if weekly_summary:
        report.append(
            f"**Weekly NAV Change (vs {weekly_summary['base_date']}):** CAD {weekly_summary['wow_pnl']:+.2f} "
            f"({weekly_summary['wow_pct']:+.2f}%) | **Weekly Realized ({weekly_summary['closed_count']} exits: "
            f"{weekly_summary['wins']}W/{weekly_summary['losses']}L):** CAD {weekly_summary['net_realized_pnl']:+.2f}"
        )
    if basket_pct is not None and prev_equity:
        report.append(
            f"**Universe Benchmark (32 TSX Equal-Wt):** {basket_pct:+.2f}% | **Relative Alpha:** {daily_pct - basket_pct:+.2f}%"
        )
    has_contribs = abs(invested_capital - float(config.get("initial_cash", 1000.0))) >= 1.0
    cum_line = (
        f"**Cumulative Return:** CAD {cum_pnl:+.2f} ({cum_pct:+.2f}% on CAD {invested_capital:,.2f} contributed | TWR: {twr_pct:+.2f}%)"
        if has_contribs
        else f"**Cumulative Return:** CAD {cum_pnl:+.2f} ({cum_pct:+.2f}%) vs CAD {invested_capital:,.2f} seed"
    )
    report.extend([
        cum_line,
        f"**Capital Breakdown:** Cash: CAD {cash:.2f} ({cash/equity*100:.1f}%) | Equity: CAD {equity-cash:.2f} ({(equity-cash)/equity*100:.1f}%)",
    ])

    if sector_totals and equity > 0:
        report.append("\n**Sector Exposure Breakdown (Cap 35.0%):**")
        for sec, val in sorted(sector_totals.items(), key=lambda x: x[1], reverse=True):
            sec_pct = (val / equity) * 100.0
            breach_tag = " ⚠️ [OVER 35% CAP]" if sec_pct > max_sector_pct else ""
            report.append(f"- **{sec}**: CAD {val:.2f} (`{sec_pct:.1f}%` of NAV){breach_tag}")

    if buy_trades:
        report.append("\n**Today's BUY Executions:**")
        for bt in buy_trades:
            report.append(f"- {bt['ticker']} BUY {bt['quantity']:g} shs @ CAD {bt['price']:.2f} (`{bt['bucket']}`)")

    if realized_trades:
        report.append("\n**Realized Trades Today:**")
        for rt in realized_trades:
            pnl_s = f" | P&L: CAD {rt['pnl']:+.2f} ({rt['pnl_pct']:+.1f}%)" if rt.get("pnl") is not None else ""
            report.append(f"- {rt['ticker']} {rt['action']} {rt['quantity']:g} shs @ CAD {rt['price']:.2f}{pnl_s}")

    if attribution:
        report.append("\n**Active Position Performance & Drawdown Attribution:**")
        for pa in attribution:
            fee_note = (
                f" [Fill: CAD {pa['fill_price']:.2f}, Gross: CAD {pa['gross_pnl']:+.2f}, Entry Fee: CAD -{pa['entry_fee_cad']:.2f}]"
                if pa.get("entry_fee_cad", 0) > 0
                else ""
            )
            report.append(
                f"- **{pa['ticker']}** ({pa['sector']}, {pa['weight_pct']}% port, {pa['days_held']}d held): {pa['shares']:g} shs @ CAD {pa['current_price']:.2f} (ACB: CAD {pa['acb']:.2f}) "
                f"| Unrealized: **CAD {pa['unrealized_pnl']:+.2f} ({pa['unrealized_pct']:+.2f}%)**{fee_note} | Buffer to Stop: CAD {pa['distance_to_stop_cad']:.2f} ({pa['distance_to_stop_pct']:.1f}%)"
            )

    if risk_watchlist:
        report.append("\n**Risk Watchlist & Drawdown Drivers:**")
        for rw in risk_watchlist:
            report.append(f"- ⚠️ **{rw['ticker']}**: {rw['note']} (Current: CAD {rw['current_price']:.2f}, Stop: CAD {rw['stop_price']:.2f}, Buffer: CAD {rw['distance_to_stop_cad']:.2f} / {rw['distance_to_stop_pct']:.1f}%)")

    if missed:
        report.append(f"\n**Screened Universe Top Movers ({len(missed)} non-held candidates):**")
        for m in sorted(missed, key=lambda x: x.get("day_gain", 0), reverse=True)[:4]:
            gate_tag = f" | Gate: `{m['gate_status']}`" if m.get("gate_status") else ""
            report.append(f"- **{m['ticker']}**: Day Gain: `+{m['day_gain']}%` | Low Rebound: `+{m['pct_from_low']}%` | RSI: `{m['rsi']}` | Vol: `{m['vol_ratio']}x`{gate_tag}")

    status_items = [f"[OPTIMIZATION] {c}" for c in changes_made] + audit_flags
    if status_items:
        report.append("\n**Autonomous Risk & Strategy Audit:**")
        for item in status_items:
            report.append(f"- {item}")
    else:
        report.append("\n**Autonomous Strategy Action:** All sector caps (<= 35%), stop buffers, and daily drawdown metrics within operating thresholds.")

    log_entry = "\n".join(report)
    log_to_changelog(log_entry)
    print("Daily self-assessment completed and logged.\n")

    # 6. Dispatch Objective Retrospective to Telegram
    try:
        from telegram_notifier import send_retrospective_report
        send_retrospective_report(
            session_type="WEEKLY" if is_friday else "DAILY",
            cash=cash,
            equity=equity,
            positions=positions,
            prev_equity=prev_equity,
            invested_capital=invested_capital,
            twr_pct=twr_pct,
            realized_trades=realized_trades,
            buy_trades=buy_trades,
            basket_pct=basket_pct,
            weekly_summary=weekly_summary,
            position_attribution=attribution,
            risk_watchlist=risk_watchlist,
            missed_opportunities=missed,
            changes_made=status_items,
        )
        print("[OPTIMIZER] Daily performance report successfully sent to Telegram.")
    except Exception as e:
        print(f"[OPTIMIZER WARNING] Failed to send Telegram close report: {e}")

    return log_entry


if __name__ == "__main__":
    run_daily_self_assessment()
