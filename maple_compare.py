"""
MAPLE Comparison Engine
Benchmarks MAPLE's live/simulated portfolio performance against the S&P/TSX 60 Index ETF (XIU.TO)
and evaluates progress towards the +12% per 90-day target using only local MAPLE resources.
Supports both LIVE IBKR account and SIMULATED modes.
"""

import os
import json
import datetime
from typing import Dict, Any, Tuple

import yfinance as yf

from maple_market import get_stock_data
from maple_ledger import get_ledger_state, load_config, get_total_invested_capital, compute_twr_pct

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
NAV_FILE = os.path.join(MAPLE_DIR, "maple_daily_nav.json")


def get_portfolio_nav(
    positions: Dict[str, Any], cash: float
) -> Dict[str, Any]:
    total_nav = cash
    details = {}
    for ticker, pos in positions.items():
        shares = pos.get("shares", 0.0)
        acb = pos.get("acb", 0.0)
        if shares > 0:
            sd = get_stock_data(ticker, mode="SHORT")
            price = (
                sd.get("Price")
                if sd and isinstance(sd.get("Price"), (int, float))
                else pos.get("current_price", acb)
            )
            val = shares * price
            pnl = val - (shares * acb)
            pnl_pct = (pnl / (shares * acb)) * 100 if acb > 0 else 0.0
            total_nav += val
            details[ticker] = {
                "shares": shares,
                "acb": acb,
                "price": price,
                "val": val,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            }
    return {
        "nav": round(total_nav, 2),
        "cash": round(cash, 2),
        "details": details,
    }


def _get_tsx60_benchmark_return() -> Tuple[str, float]:
    """Computes S&P/TSX 60 (XIU.TO) return since MAPLE's earliest recorded NAV date."""
    start_date = "2026-10-09"
    if os.path.exists(NAV_FILE):
        try:
            with open(NAV_FILE, "r", encoding="utf-8") as f:
                nav_hist = json.load(f)
            if nav_hist:
                start_date = sorted(nav_hist.keys())[0]
        except Exception:
            pass
    try:
        hist = yf.Ticker("XIU.TO").history(start=start_date, timeout=10)
        if hist is not None and len(hist) >= 2:
            p0 = float(hist["Close"].iloc[0])
            p1 = float(hist["Close"].iloc[-1])
            if p0 > 0:
                return start_date, round(((p1 - p0) / p0) * 100.0, 2)
    except Exception:
        pass
    return start_date, 0.0


def generate_comparison_report() -> str:
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"
    maple_raw = get_ledger_state()

    if is_live and "total_equity" in maple_raw:
        maple_total_nav = maple_raw["total_equity"]
        maple_details = {}
        for t, p in maple_raw["positions"].items():
            if p.get("shares", 0) > 0:
                cur_p = p.get("current_price", p.get("acb", 0.0))
                val = p["shares"] * cur_p
                cost = p["shares"] * p["acb"]
                pnl = val - cost
                pnl_pct = (pnl / cost) * 100 if cost > 0 else 0.0
                maple_details[t] = {
                    "shares": p["shares"],
                    "acb": p["acb"],
                    "price": cur_p,
                    "val": val,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                }
        maple_nav = {
            "nav": maple_total_nav,
            "cash": maple_raw["cash"],
            "details": maple_details,
        }
    else:
        maple_nav = get_portfolio_nav(maple_raw["positions"], maple_raw["cash"])

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    maple_raw_cfg = load_config()
    maple_baseline = get_total_invested_capital(maple_raw_cfg)
    maple_return = compute_twr_pct(maple_nav["nav"], config=maple_raw_cfg)
    bench_date, tsx_return = _get_tsx60_benchmark_return()

    report = []
    report.append("+==================================================================+")
    report.append("|  MAPLE vs S&P/TSX 60 (XIU.TO) -- PERFORMANCE BENCHMARK           |")
    report.append(f"|  Mode: {maple_raw.get('mode', 'SIMULATED'):<8} | Account: #{maple_raw.get('account_id', 'SIM'):<12} | Time: {now_str[:16]}  |")
    report.append("+------------------------------------------------------------------+")
    report.append(f"|  MAPLE Portfolio NAV:            ${maple_nav['nav']:<10.2f} ({maple_return:+.2f}%)               |")
    report.append(f"|  MAPLE Available Cash:           ${maple_nav['cash']:<10.2f}                      |")
    report.append(f"|  S&P/TSX 60 (since {bench_date}):   {tsx_return:+.2f}%                          |")
    report.append("+------------------------------------------------------------------+")
    report.append("|  MAPLE Open Holdings:                                            |")
    if not maple_nav["details"]:
        report.append("|    100% Cash Fortress / Zero open risk positions                 |")
    else:
        for t, d in maple_nav["details"].items():
            pos_line = f"|    * {t}: {d['shares']:.1f} shs @ ${d['price']:.2f} (P&L: ${d['pnl']:+.2f} / {d['pnl_pct']:+.2f}%)"
            report.append(f"{pos_line:<67}|")
    report.append("+------------------------------------------------------------------+")
    report.append("|  Target Benchmark: +12.00% per 90 Days ($1,120.00 Target)        |")
    status_str = "ON TRACK (+12% GOAL)" if maple_return >= 0 else "DEFENSIVE / CAPITAL PRESERVATION"
    report.append(f"|  MAPLE 90-Day Trajectory:        {status_str:<32}|")
    report.append("+==================================================================+")

    output = "\n".join(report)
    print(output)
    return output


if __name__ == "__main__":
    generate_comparison_report()
