"""
MAPLE Standalone Walk-Forward Backtester (Read-Only CLI Tool)
Simulates MAPLE's US equity swing-trading rules on daily OHLCV bars with zero lookahead
and zero side effects on live configuration or ledger files.
"""

import datetime
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf

from maple_ledger import SHARIAH_COMPLIANT_BASKET, get_ticker_sector, normalize_ticker
from maple_market import is_macro_aligned
from maple_strategy import MapleStrategy


def _prepare_indicator_df(df: pd.DataFrame) -> pd.DataFrame:
    """Precomputes daily technical indicators matching maple_market.get_stock_data(mode='SHORT')."""
    out = df.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(out) < 55:
        return pd.DataFrame()
    out.ta.ema(length=5, append=True)
    out.ta.ema(length=9, append=True)
    out.ta.sma(length=50, append=True)
    out.ta.rsi(length=7, append=True)
    out.ta.atr(length=5, append=True)
    out.ta.bbands(length=20, std=2, append=True)
    out.ta.adx(length=14, append=True)
    out["Vol_SMA_10"] = out["Volume"].shift(1).rolling(window=10).mean()
    out["Ret_20d"] = ((out["Close"] - out["Close"].shift(20)) / out["Close"].shift(20)) * 100.0
    return out


def _row_to_stock_data(row: pd.Series, prev_row: pd.Series, bb_mid_col: Optional[str]) -> Dict[str, Any]:
    price = float(row["Close"])
    low_px = float(row["Low"])
    open_px = float(row["Open"])
    prev_close = float(prev_row["Close"])
    ema_5 = float(row["EMA_5"]) if "EMA_5" in row and pd.notna(row["EMA_5"]) else 0.0
    ema_9 = float(row["EMA_9"]) if "EMA_9" in row and pd.notna(row["EMA_9"]) else 0.0
    prev_ema_5 = float(prev_row["EMA_5"]) if "EMA_5" in prev_row and pd.notna(prev_row["EMA_5"]) else ema_5
    sma_50 = float(row["SMA_50"]) if "SMA_50" in row and pd.notna(row["SMA_50"]) else 0.0
    dmp_14 = float(row["DMP_14"]) if "DMP_14" in row and pd.notna(row["DMP_14"]) else 0.0
    dmn_14 = float(row["DMN_14"]) if "DMN_14" in row and pd.notna(row["DMN_14"]) else 0.0

    if ema_5 > ema_9 and ema_5 > 0:
        sma50_ceiling = sma_50 > 0 and ema_9 < sma_50 and abs(price - sma_50) / sma_50 <= 0.015
        if (
            price >= ema_5
            and ema_5 > prev_ema_5
            and dmp_14 > dmn_14
            and (price - ema_5) / ema_5 <= 0.03
            and not sma50_ceiling
        ):
            crossover = "BULLISH (EMA5 > EMA9)"
        else:
            crossover = "NEUTRAL (FILTERED)"
    elif ema_5 < ema_9:
        crossover = "BEARISH (EMA5 < EMA9)"
    else:
        crossover = "NEUTRAL"

    vol_sma = float(row["Vol_SMA_10"]) if pd.notna(row.get("Vol_SMA_10")) and float(row["Vol_SMA_10"]) > 0 else float(row["Volume"])
    vol_ratio = round(float(row["Volume"]) / vol_sma, 2) if vol_sma > 0 else 1.0
    pct_from_low = round(((price - low_px) / low_px) * 100.0, 2) if low_px > 0 else 0.0

    return {
        "Price": round(price, 2),
        "Open": round(open_px, 2),
        "High": round(float(row["High"]), 2),
        "Low": round(low_px, 2),
        "Prev_Close": round(prev_close, 2),
        "Pct_From_Low": pct_from_low,
        "Volume": int(row["Volume"]),
        "Vol_SMA_10": round(vol_sma, 0),
        "Intraday_Dollar_Vol": round(float(row["Volume"]) * price, 2),
        "Vol_Ratio": vol_ratio,
        "EMA_Crossover": crossover,
        "EMA_5": round(ema_5, 2) if ema_5 > 0 else "N/A",
        "EMA_9": round(ema_9, 2) if ema_9 > 0 else "N/A",
        "SMA_50": round(sma_50, 2) if sma_50 > 0 else "N/A",
        "Ret_20d": round(float(row["Ret_20d"]), 2) if pd.notna(row.get("Ret_20d")) else 0.0,
        "RSI_7": round(float(row["RSI_7"]), 2) if "RSI_7" in row and pd.notna(row["RSI_7"]) else "N/A",
        "ATR_5": round(float(row["ATRr_5"]), 2) if "ATRr_5" in row and pd.notna(row["ATRr_5"]) else "N/A",
        "ADX_14": round(float(row["ADX_14"]), 2) if "ADX_14" in row and pd.notna(row["ADX_14"]) else "N/A",
        "BB_Mid": round(float(row[bb_mid_col]), 2) if bb_mid_col and pd.notna(row.get(bb_mid_col)) else "N/A",
    }


def run_backtest(
    hist_map: Dict[str, pd.DataFrame],
    initial_cash: float = 10000.0,
    commission: float = 1.0,
    max_sector_pct: float = 0.35,
) -> Dict[str, Any]:
    """Runs a deterministic daily-bar walk-forward simulation over pre-fetched OHLCV DataFrames."""
    MapleStrategy._sync_from_config()
    ind_map: Dict[str, pd.DataFrame] = {}
    bb_cols: Dict[str, Optional[str]] = {}
    all_dates = set()

    for sym, df in hist_map.items():
        if sym in ("SPY", "^VIX", "GC=F", "CL=F"):
            continue
        prep = _prepare_indicator_df(df)
        if not prep.empty:
            ind_map[normalize_ticker(sym)] = prep
            bb_cols[normalize_ticker(sym)] = next((c for c in prep.columns if c.startswith("BBM_")), None)
            all_dates.update(prep.index[52:])

    sim_dates = sorted(all_dates)
    if not sim_dates:
        return {"total_return_pct": 0.0, "trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0}

    cash = float(initial_cash)
    positions: Dict[str, Dict[str, Any]] = {}
    closed_trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = []
    peak_eq = float(initial_cash)
    max_dd_pct = 0.0

    for dt in sim_dates:
        # Step 1: Evaluate exits and ratchets on held positions
        for tk in list(positions.keys()):
            df_t = ind_map.get(tk)
            if df_t is None or dt not in df_t.index:
                continue
            loc = df_t.index.get_loc(dt)
            if isinstance(loc, slice) or loc < 1:
                continue
            row = df_t.iloc[loc]
            prev_row = df_t.iloc[loc - 1]
            sd = _row_to_stock_data(row, prev_row, bb_cols.get(tk))

            pos = positions[tk]
            pos["days_held"] += 1
            shs = pos["shares"]
            acb = pos["acb"]
            tgt = pos["target"]
            stp = pos["stop"]
            high_px, low_px, close_px = sd["High"], sd["Low"], sd["Price"]

            exit_px, exit_reason = None, None
            if low_px <= stp:
                exit_px = round(min(sd["Open"], stp), 2) if sd["Open"] <= stp else stp
                exit_reason = "STOP_LOSS"
            elif high_px >= tgt:
                exit_px = round(max(sd["Open"], tgt), 2) if sd["Open"] >= tgt else tgt
                exit_reason = "TARGET_HIT"
            elif pos["days_held"] >= MapleStrategy.STAGNATION_DAYS and close_px < acb:
                e5, e9 = sd.get("EMA_5"), sd.get("EMA_9")
                is_bear = (isinstance(e5, (int, float)) and isinstance(e9, (int, float)) and e5 < e9) or ("BEARISH" in str(sd.get("EMA_Crossover", "")))
                below_both = isinstance(e5, (int, float)) and isinstance(e9, (int, float)) and close_px < e5 and close_px < e9
                if is_bear or below_both:
                    exit_px = close_px
                    exit_reason = "STAGNATION_EXIT"

            if exit_px is not None:
                proceeds = round(shs * exit_px - commission, 2)
                pnl = round(proceeds - (shs * acb), 2)
                cash = round(cash + proceeds, 2)
                closed_trades.append({"ticker": tk, "pnl": pnl, "reason": exit_reason, "signal_type": pos["signal_type"]})
                del positions[tk]
                continue

            # Apply multi-tier stop ratchets at close
            gain_pct = ((close_px - acb) / acb) * 100.0
            if gain_pct >= 4.5:
                pos["stop"] = max(pos["stop"], round(close_px * 0.9875, 2))
            elif gain_pct >= 3.0:
                pos["stop"] = max(pos["stop"], round(acb * 1.015 + (2.0 * commission) / shs, 2))
            elif gain_pct >= 2.5:
                pos["stop"] = max(pos["stop"], round(acb + (2.0 * commission) / shs, 2))
            elif gain_pct >= 2.0:
                pos["stop"] = max(pos["stop"], round(acb * 0.975, 2))

        # Compute current portfolio equity
        pos_val = sum(
            p["shares"] * (float(ind_map[tk].loc[dt]["Close"]) if dt in ind_map[tk].index else p["acb"])
            for tk, p in positions.items()
        )
        nav = round(cash + pos_val, 2)

        # Step 2: Evaluate candidate entries on remaining universe
        cands = []
        for tk, df_t in ind_map.items():
            if tk in positions or dt not in df_t.index:
                continue
            loc = df_t.index.get_loc(dt)
            if isinstance(loc, slice) or loc < 1:
                continue
            sd = _row_to_stock_data(df_t.iloc[loc], df_t.iloc[loc - 1], bb_cols.get(tk))
            rsi, vr, cross = sd.get("RSI_7"), sd.get("Vol_Ratio"), sd.get("EMA_Crossover")
            if isinstance(rsi, (int, float)) and rsi < MapleStrategy.RSI_OVERSOLD_MAX and isinstance(vr, (int, float)) and vr >= MapleStrategy.VOLUME_CAPITULATION_RATIO:
                sig_t = "CAPITULATION REVERSAL"
            elif cross == "BULLISH (EMA5 > EMA9)":
                sig_t = "REGULAR BUY" if (isinstance(vr, (int, float)) and vr >= MapleStrategy.VOLUME_CAPITULATION_RATIO) else "LOW-VOLUME SCALED ENTRY"
            else:
                continue
            t_pct, rat = MapleStrategy.calculate_tranche_size(sd, signal_type=sig_t)
            if t_pct > 0:
                cands.append((tk, sig_t, t_pct, rat, sd, (t_pct, round(float(vr), 2), float(sd.get("Ret_20d", 0.0)), float(sd.get("ADX_14", 0.0)))))

        cands.sort(key=lambda x: x[5], reverse=True)
        for tk, sig_t, t_pct, rat, sd, _ in cands:
            px = sd["Price"]
            sec = get_ticker_sector(tk)
            sec_val = sum(
                p["shares"] * (float(ind_map[ot].loc[dt]["Close"]) if dt in ind_map[ot].index else p["acb"])
                for ot, p in positions.items()
                if get_ticker_sector(ot) == sec
            )
            sec_room = max(0.0, nav * max_sector_pct - sec_val)
            alloc = min(cash - commission, nav * t_pct, sec_room)
            shs = int(alloc // px)
            if shs < 1 or shs * px < max(50.0, nav * 0.05):
                continue
            cost = round(shs * px + commission, 2)
            if cost > cash:
                continue
            acb = round(cost / shs, 4)
            tgt, stp = MapleStrategy.calculate_targets(px, sd, shares=shs, cost_basis=acb, signal_type=sig_t)
            cash = round(cash - cost, 2)
            positions[tk] = {"shares": shs, "acb": acb, "target": tgt, "stop": stp, "days_held": 0, "signal_type": sig_t}

        pos_val_end = sum(
            p["shares"] * (float(ind_map[tk].loc[dt]["Close"]) if dt in ind_map[tk].index else p["acb"])
            for tk, p in positions.items()
        )
        end_nav = round(cash + pos_val_end, 2)
        equity_curve.append(end_nav)
        peak_eq = max(peak_eq, end_nav)
        if peak_eq > 0:
            max_dd_pct = max(max_dd_pct, round(((peak_eq - end_nav) / peak_eq) * 100.0, 2))

    final_nav = equity_curve[-1] if equity_curve else initial_cash
    wins = [t["pnl"] for t in closed_trades if t["pnl"] > 0]
    losses = [abs(t["pnl"]) for t in closed_trades if t["pnl"] <= 0]
    win_rate = round((len(wins) / len(closed_trades)) * 100.0, 1) if closed_trades else 0.0
    pf = round(sum(wins) / sum(losses), 2) if sum(losses) > 0 else (99.0 if wins else 0.0)

    return {
        "initial_cash": initial_cash,
        "final_nav": final_nav,
        "total_return_pct": round(((final_nav - initial_cash) / initial_cash) * 100.0, 2),
        "trades": len(closed_trades),
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "max_drawdown_pct": max_dd_pct,
        "closed_trades": closed_trades,
    }


if __name__ == "__main__":
    tickers = sorted(SHARIAH_COMPLIANT_BASKET)
    print(f"Downloading 1-year daily bars for {len(tickers)} Zoya-certified US equities...")
    raw = yf.download(tickers, period="1y", group_by="ticker", threads=True, progress=False)
    h_map = {t: raw[t].dropna(how="all") for t in tickers if t in raw}
    res = run_backtest(h_map, initial_cash=10000.0)
    print("\n=== MAPLE 1-YEAR US WALK-FORWARD BACKTEST SUMMARY ===")
    print(f"Starting Capital : ${res['initial_cash']:,.2f} USD")
    print(f"Ending NAV       : ${res['final_nav']:,.2f} USD ({res['total_return_pct']:+.2f}%)")
    print(f"Closed Trades    : {res['trades']} | Win Rate: {res['win_rate_pct']:.1f}% | Profit Factor: {res['profit_factor']:.2f}")
    print(f"Max Drawdown     : -{res['max_drawdown_pct']:.2f}%")
