"""
MAPLE Standalone Walk-Forward Backtester (Read-Only CLI Tool)
Simulates MAPLE's Variant D (Stage-2 Top-RS Multi-Week Swing) or Tactical Swing rules
across the 53 Zoya-certified US equities with zero lookahead and zero side effects.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import pandas_ta as ta
import yfinance as yf

from maple_ledger import SHARIAH_COMPLIANT_BASKET, get_ticker_sector, normalize_ticker
from maple_market import is_macro_aligned, GOLD_LINKED_TICKERS, OIL_LINKED_TICKERS
from maple_strategy import MapleStrategy


def _prepare_indicator_df(df: pd.DataFrame) -> pd.DataFrame:
    """Precomputes daily technical indicators matching maple_market.get_stock_data(mode='SHORT')."""
    out = df.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(out) < 55:
        return pd.DataFrame()
    out.ta.ema(length=5, append=True)
    out.ta.ema(length=9, append=True)
    out.ta.ema(length=21, append=True)
    out.ta.sma(length=50, append=True)
    if len(out) >= 200:
        out.ta.sma(length=200, append=True)
    out.ta.rsi(length=7, append=True)
    out.ta.rsi(length=14, append=True)
    out.ta.atr(length=5, append=True)
    out.ta.atr(length=14, append=True)
    out.ta.bbands(length=20, std=2, append=True)
    out.ta.adx(length=14, append=True)
    out["ATR_14_prev"] = out["ATRr_14"].shift(1) if "ATRr_14" in out else np.nan
    out["SMA50_prev5"] = out["SMA_50"].shift(5) if "SMA_50" in out else np.nan
    out["Vol_SMA_10"] = out["Volume"].shift(1).rolling(window=10).mean()
    out["Ret_20d"] = ((out["Close"] - out["Close"].shift(20)) / out["Close"].shift(20)) * 100.0
    out["Ret_63d"] = ((out["Close"] - out["Close"].shift(63)) / out["Close"].shift(63)) * 100.0
    out["Ret_126d"] = ((out["Close"] - out["Close"].shift(126)) / out["Close"].shift(126)) * 100.0
    return out


def _build_macro_by_date(hist_map: Dict[str, pd.DataFrame]) -> Dict[Any, Dict[str, Any]]:
    """Builds per-session macro alignment state (SPY 50/200-SMA, ^VIX regime, GC=F, CL=F) from hist_map."""
    macro_by_date: Dict[Any, Dict[str, Any]] = {}
    spy = hist_map.get("SPY")
    vix = hist_map.get("^VIX")
    gc = hist_map.get("GC=F")
    cl = hist_map.get("CL=F")

    spy_df = spy.dropna(subset=["Close"]).copy() if (spy is not None and not spy.empty) else pd.DataFrame()
    if not spy_df.empty:
        spy_df["SMA50"] = spy_df["Close"].rolling(50).mean()
        spy_df["SMA200"] = spy_df["Close"].rolling(200).mean()
    vix_df = vix.dropna(subset=["Close"]).copy() if (vix is not None and not vix.empty) else pd.DataFrame()
    if not vix_df.empty:
        vix_df["Prev"] = vix_df["Close"].shift(1)
    gc_df = gc.dropna(subset=["Close"]).copy() if (gc is not None and not gc.empty) else pd.DataFrame()
    if not gc_df.empty:
        gc_df["Up"] = gc_df["Close"] >= gc_df["Close"].shift(1)
    cl_df = cl.dropna(subset=["Close"]).copy() if (cl is not None and not cl.empty) else pd.DataFrame()
    if not cl_df.empty:
        cl_df["Up"] = cl_df["Close"] >= cl_df["Close"].shift(1)

    all_idx = set(spy_df.index) | set(vix_df.index) | set(gc_df.index) | set(cl_df.index)
    for dt in all_idx:
        v_cur = float(vix_df.loc[dt]["Close"]) if dt in vix_df.index else 18.0
        v_prev = float(vix_df.loc[dt]["Prev"]) if (dt in vix_df.index and pd.notna(vix_df.loc[dt]["Prev"])) else v_cur
        s_below50, s_below200 = False, False
        if dt in spy_df.index:
            s_c = float(spy_df.loc[dt]["Close"])
            if pd.notna(spy_df.loc[dt].get("SMA50")):
                s_below50 = s_c < float(spy_df.loc[dt]["SMA50"])
            if pd.notna(spy_df.loc[dt].get("SMA200")):
                s_below200 = s_c < float(spy_df.loc[dt]["SMA200"])
        macro_by_date[dt] = {
            "GC=F": bool(gc_df.loc[dt]["Up"]) if (dt in gc_df.index and pd.notna(gc_df.loc[dt].get("Up"))) else True,
            "CL=F": bool(cl_df.loc[dt]["Up"]) if (dt in cl_df.index and pd.notna(cl_df.loc[dt].get("Up"))) else True,
            "VIX_ELEVATED": bool(v_cur >= 25.0 or (v_prev > 0 and ((v_cur - v_prev) / v_prev) >= 0.10)),
            "VIX_STAGE2_BLOCK": bool(v_cur >= 32.0),
            "VIX_PANIC": bool(v_cur >= 35.0),
            "SPY_BELOW_SMA50": s_below50,
            "SPY_BELOW_SMA200": s_below200,
        }
    return macro_by_date


def _row_to_stock_data(row: pd.Series, prev_row: pd.Series, bb_mid_col: Optional[str]) -> Dict[str, Any]:
    price = float(row["Close"])
    low_px = float(row["Low"])
    open_px = float(row["Open"])
    prev_close = float(prev_row["Close"])
    ema_5 = float(row["EMA_5"]) if "EMA_5" in row and pd.notna(row["EMA_5"]) else 0.0
    ema_9 = float(row["EMA_9"]) if "EMA_9" in row and pd.notna(row["EMA_9"]) else 0.0
    ema_21 = float(row["EMA_21"]) if "EMA_21" in row and pd.notna(row["EMA_21"]) else 0.0
    prev_ema_5 = float(prev_row["EMA_5"]) if "EMA_5" in prev_row and pd.notna(prev_row["EMA_5"]) else ema_5
    sma_50 = float(row["SMA_50"]) if "SMA_50" in row and pd.notna(row["SMA_50"]) else 0.0
    sma_200 = float(row["SMA_200"]) if "SMA_200" in row and pd.notna(row["SMA_200"]) else 0.0
    sma_50_rising = bool(sma_50 >= float(row["SMA50_prev5"])) if pd.notna(row.get("SMA50_prev5")) else True
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
    atr_5 = round(float(row["ATRr_5"]), 2) if "ATRr_5" in row and pd.notna(row["ATRr_5"]) else "N/A"
    atr_14 = round(float(row["ATR_14_prev"]), 2) if "ATR_14_prev" in row and pd.notna(row["ATR_14_prev"]) else atr_5
    ret_20d = round(float(row["Ret_20d"]), 2) if pd.notna(row.get("Ret_20d")) else 0.0
    ret_63d = round(float(row["Ret_63d"]), 2) if pd.notna(row.get("Ret_63d")) else ret_20d
    ret_126d = round(float(row["Ret_126d"]), 2) if pd.notna(row.get("Ret_126d")) else ret_63d
    rs_score = round(0.50 * ret_63d + 0.35 * ret_126d + 0.15 * ret_20d, 2)

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
        "EMA_21": round(ema_21, 2) if ema_21 > 0 else "N/A",
        "SMA_50": round(sma_50, 2) if sma_50 > 0 else "N/A",
        "SMA_50_Rising": sma_50_rising,
        "SMA_200": round(sma_200, 2) if sma_200 > 0 else "N/A",
        "Ret_20d": ret_20d,
        "Ret_63d": ret_63d,
        "Ret_126d": ret_126d,
        "RS_Score": rs_score,
        "RSI_7": round(float(row["RSI_7"]), 2) if "RSI_7" in row and pd.notna(row["RSI_7"]) else "N/A",
        "RSI_14": round(float(row["RSI_14"]), 2) if "RSI_14" in row and pd.notna(row["RSI_14"]) else "N/A",
        "ATR_5": atr_5,
        "ATR_14": atr_14,
        "ADX_14": round(float(row["ADX_14"]), 2) if "ADX_14" in row and pd.notna(row["ADX_14"]) else "N/A",
        "BB_Mid": round(float(row[bb_mid_col]), 2) if bb_mid_col and pd.notna(row.get(bb_mid_col)) else "N/A",
    }


def run_backtest(
    hist_map: Dict[str, pd.DataFrame],
    initial_cash: float = 10000.0,
    commission: float = 1.0,
    max_position_pct: float = 0.25,
    max_sector_pct: float = 0.40,
    strategy_mode: str = "STAGE2_RS",
) -> Dict[str, Any]:
    """Runs a deterministic daily-bar walk-forward simulation over pre-fetched OHLCV DataFrames."""
    MapleStrategy._sync_from_config()
    is_stage2 = str(strategy_mode).upper() == "STAGE2_RS"
    ind_map: Dict[str, pd.DataFrame] = {}
    bb_cols: Dict[str, Optional[str]] = {}
    all_dates = set()

    for sym, df in hist_map.items():
        if sym in ("SPY", "^VIX", "GC=F", "CL=F", "SPUS"):
            continue
        prep = _prepare_indicator_df(df)
        if not prep.empty:
            norm = normalize_ticker(sym)
            ind_map[norm] = prep
            bb_cols[norm] = next((c for c in prep.columns if c.startswith("BBM_")), None)
            warmup = 200 if len(prep) > 205 else 52
            all_dates.update(prep.index[warmup:])

    sim_dates = sorted(all_dates)
    if not sim_dates:
        return {
            "initial_cash": initial_cash,
            "final_nav": initial_cash,
            "total_return_pct": 0.0,
            "cagr_pct": 0.0,
            "trades": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe": 0.0,
            "closed_trades": [],
        }

    macro_by_date = _build_macro_by_date(hist_map)
    default_macro = {
        "GC=F": True, "CL=F": True, "VIX_ELEVATED": False,
        "VIX_STAGE2_BLOCK": False, "VIX_PANIC": False,
        "SPY_BELOW_SMA50": False, "SPY_BELOW_SMA200": False,
    }
    cash = float(initial_cash)
    positions: Dict[str, Dict[str, Any]] = {}
    closed_trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = []
    peak_eq = float(initial_cash)
    max_dd_pct = 0.0
    last_loss_idx: Dict[str, int] = {}

    for d_idx, dt in enumerate(sim_dates):
        macro_state = macro_by_date.get(dt, default_macro)

        # Build daily universe RS ranking
        day_sd: Dict[str, Dict[str, Any]] = {}
        rs_ranked: List[tuple] = []
        for tk, df_t in ind_map.items():
            if dt not in df_t.index:
                continue
            loc = df_t.index.get_loc(dt)
            if isinstance(loc, slice) or loc < 1:
                continue
            sd = _row_to_stock_data(df_t.iloc[loc], df_t.iloc[loc - 1], bb_cols.get(tk))
            day_sd[tk] = sd
            rs_ranked.append((float(sd.get("RS_Score", 0.0)), tk))
        rs_ranked.sort(key=lambda x: (-x[0], x[1]))
        top_rs_tickers = [tk for _, tk in rs_ranked[: MapleStrategy.RS_TOP_N]]
        keep_rs_set = set(tk for _, tk in rs_ranked[: MapleStrategy.RS_KEEP_N])

        # Step 1: Evaluate exits & ratchets on held positions
        for tk in list(positions.keys()):
            sd = day_sd.get(tk)
            if not sd:
                continue
            pos = positions[tk]
            pos["days_held"] += 1
            shs, acb, tgt, stp = pos["shares"], pos["acb"], pos["target"], pos["stop"]
            open_px, high_px, low_px, close_px = sd["Open"], sd["High"], sd["Low"], sd["Price"]
            atr_v = float(sd["ATR_14"]) if isinstance(sd.get("ATR_14"), (int, float)) and sd["ATR_14"] > 0 else (acb * 0.025)

            exit_px, exit_reason = None, None
            if low_px <= stp:
                exit_px = round(min(open_px, stp), 2) if open_px <= stp else stp
                exit_reason = "STOP_LOSS"
            elif tgt is not None and high_px >= tgt:
                exit_px = round(max(open_px, tgt), 2) if open_px >= tgt else tgt
                exit_reason = "TARGET_HIT"
            elif is_stage2 and pos["days_held"] >= MapleStrategy.STAGE2_MIN_HOLD_DAYS:
                s50, e21 = sd.get("SMA_50"), sd.get("EMA_21")
                gain_pct = ((close_px - acb) / acb) * 100.0 if acb > 0 else 0.0
                if isinstance(s50, (int, float)) and s50 > 0 and close_px < s50:
                    exit_px = close_px
                    exit_reason = "STAGE2_SMA50_EXIT"
                elif isinstance(e21, (int, float)) and e21 > 0 and close_px < e21 and (
                    gain_pct >= MapleStrategy.STAGE2_PROFIT_HARVEST_PCT or tk not in keep_rs_set
                ):
                    exit_px = close_px
                    exit_reason = "STAGE2_EMA21_EXIT"
            elif not is_stage2 and pos["days_held"] >= MapleStrategy.STAGNATION_DAYS and close_px < acb:
                e5, e9 = sd.get("EMA_5"), sd.get("EMA_9")
                is_bear = (isinstance(e5, (int, float)) and isinstance(e9, (int, float)) and e5 < e9) or ("BEARISH" in str(sd.get("EMA_Crossover", "")))
                below_both = isinstance(e5, (int, float)) and isinstance(e9, (int, float)) and close_px < e5 and close_px < e9
                intraday_rally = close_px > open_px and sd["Prev_Close"] > 0 and close_px >= sd["Prev_Close"] * 1.01
                if (is_bear or below_both) and not intraday_rally:
                    exit_px = close_px
                    exit_reason = "STAGNATION_EXIT"

            if exit_px is not None:
                proceeds = round(shs * exit_px - commission, 2)
                pnl = round(proceeds - (shs * acb), 2)
                cash = round(cash + proceeds, 2)
                closed_trades.append({"ticker": tk, "pnl": pnl, "reason": exit_reason, "signal_type": pos["signal_type"]})
                if pnl <= 0 and "STOP" in exit_reason:
                    last_loss_idx[tk] = d_idx
                del positions[tk]
                continue

            # Update ratchets at close
            comm_be = round(acb + commission / shs, 2)
            if is_stage2:
                pos["peak"] = max(pos["peak"], close_px)
                cand_stp = stp
                if pos["peak"] >= acb * 1.08 and close_px >= round(comm_be * 1.004, 2):
                    cand_stp = max(cand_stp, comm_be)
                chand = round(pos["peak"] - MapleStrategy.STAGE2_TRAIL_STOP_ATR_MULT * atr_v, 2)
                if chand < close_px:
                    cand_stp = max(cand_stp, chand)
                pos["stop"] = cand_stp
            elif close_px > acb:
                r_unit = max(0.01, acb - pos["init_stop"])
                r_gain = (close_px - acb) / r_unit
                cand_stp = stp
                if r_gain >= 0.8:
                    cand_stp = max(cand_stp, round(acb - 0.5 * r_unit, 2))
                if r_gain >= 1.0:
                    cand_stp = max(cand_stp, comm_be if close_px >= round(comm_be * 1.004, 2) else round(acb, 2))
                if r_gain >= 1.5:
                    lk = round(comm_be + 0.75 * r_unit, 2)
                    if close_px >= round(lk * 1.004, 2):
                        cand_stp = max(cand_stp, lk)
                if r_gain >= 2.0:
                    cand_stp = max(cand_stp, round(close_px - 1.5 * atr_v, 2))
                if cand_stp < close_px and cand_stp > pos["stop"]:
                    pos["stop"] = cand_stp

        pos_val = sum(
            p["shares"] * (day_sd[tk]["Price"] if tk in day_sd else p["acb"])
            for tk, p in positions.items()
        )
        nav = round(cash + pos_val, 2)

        # Step 2: Evaluate candidate entries
        if is_stage2:
            if len(positions) < MapleStrategy.MAX_OPEN_POSITIONS:
                vix_halt = macro_state["VIX_STAGE2_BLOCK"] or macro_state["VIX_PANIC"]
                spy_bear = macro_state["SPY_BELOW_SMA50"] and macro_state["SPY_BELOW_SMA200"]
                for tk in top_rs_tickers:
                    if len(positions) >= MapleStrategy.MAX_OPEN_POSITIONS or tk in positions or last_loss_idx.get(tk) == d_idx:
                        continue
                    sd = day_sd.get(tk)
                    if not sd:
                        continue
                    aligned, _ = is_macro_aligned(tk, macro_state)
                    if not aligned:
                        continue
                    if tk not in GOLD_LINKED_TICKERS and tk not in OIL_LINKED_TICKERS and (vix_halt or spy_bear):
                        continue
                    slot_pct, _ = MapleStrategy.evaluate_stage2_entry(sd)
                    if slot_pct <= 0.0:
                        continue
                    if macro_state["VIX_ELEVATED"] and macro_state["SPY_BELOW_SMA50"] and tk not in GOLD_LINKED_TICKERS and tk not in OIL_LINKED_TICKERS:
                        slot_pct = round(slot_pct * 0.60, 4)

                    px = sd["Price"]
                    sec = get_ticker_sector(tk)
                    sec_val = sum(
                        p["shares"] * (day_sd[ot]["Price"] if ot in day_sd else p["acb"])
                        for ot, p in positions.items() if get_ticker_sector(ot) == sec
                    )
                    sec_room = max(0.0, nav * max_sector_pct - sec_val)
                    alloc = min(cash - commission, nav * slot_pct, nav * max_position_pct, sec_room)
                    shs = int(alloc // px)
                    if shs == 0 and px <= nav * 0.30 and px <= sec_room and px + commission <= cash and alloc >= nav * 0.08:
                        shs = 1
                    if shs < 1 or shs * px < max(150.0, nav * 0.08):
                        continue
                    cost = round(shs * px + commission, 2)
                    if cost > cash:
                        continue
                    acb = round(cost / shs, 4)
                    tgt, stp = MapleStrategy.calculate_targets(px, sd, shares=shs, cost_basis=acb, signal_type="STAGE2_RS")
                    cash = round(cash - cost, 2)
                    positions[tk] = {"shares": shs, "acb": acb, "target": tgt, "stop": stp, "init_stop": stp, "peak": px, "days_held": 0, "signal_type": "STAGE2_RS"}

        pos_val_end = sum(
            p["shares"] * (day_sd[tk]["Price"] if tk in day_sd else p["acb"])
            for tk, p in positions.items()
        )
        end_nav = round(cash + pos_val_end, 2)
        equity_curve.append(end_nav)
        peak_eq = max(peak_eq, end_nav)
        if peak_eq > 0:
            max_dd_pct = max(max_dd_pct, round(((peak_eq - end_nav) / peak_eq) * 100.0, 2))

    final_nav = equity_curve[-1] if equity_curve else initial_cash
    yrs = len(sim_dates) / 252.0
    cagr = round((((final_nav / initial_cash) ** (1.0 / yrs)) - 1.0) * 100.0, 2) if yrs > 0 and final_nav > 0 else 0.0
    wins = [t["pnl"] for t in closed_trades if t["pnl"] > 0]
    losses = [abs(t["pnl"]) for t in closed_trades if t["pnl"] <= 0]
    win_rate = round((len(wins) / len(closed_trades)) * 100.0, 1) if closed_trades else 0.0
    pf = round(sum(wins) / sum(losses), 2) if sum(losses) > 0 else (99.0 if wins else 0.0)
    rets = pd.Series(equity_curve).pct_change().dropna()
    sharpe = round(float(rets.mean() / rets.std() * np.sqrt(252)), 2) if len(rets) > 10 and rets.std() > 0 else 0.0

    return {
        "initial_cash": initial_cash,
        "final_nav": final_nav,
        "total_return_pct": round(((final_nav - initial_cash) / initial_cash) * 100.0, 2),
        "cagr_pct": cagr,
        "years": round(yrs, 2),
        "trades": len(closed_trades),
        "win_rate_pct": win_rate,
        "profit_factor": pf,
        "max_drawdown_pct": max_dd_pct,
        "sharpe": sharpe,
        "closed_trades": closed_trades,
    }


if __name__ == "__main__":
    tickers = sorted(SHARIAH_COMPLIANT_BASKET) + ["SPY", "^VIX", "GC=F", "CL=F"]
    print(f"Downloading 5-year daily bars for {len(SHARIAH_COMPLIANT_BASKET)} Zoya-certified US equities + macro indices...")
    raw = yf.download(tickers, period="5y", group_by="ticker", threads=True, progress=False)
    h_map = {t: raw[t].dropna(how="all") for t in tickers if t in raw}
    res = run_backtest(h_map, initial_cash=10000.0)
    print(f"\n=== MAPLE VARIANT D ({res['years']}Y WALK-FORWARD BACKTEST: 53 SHARIAH US EQUITIES) ===")
    print(f"Starting Capital : ${res['initial_cash']:,.2f} USD")
    print(f"Ending NAV       : ${res['final_nav']:,.2f} USD ({res['total_return_pct']:+.2f}% cumulative | {res['cagr_pct']:+.2f}%/yr CAGR)")
    print(f"Closed Trades    : {res['trades']} | Win Rate: {res['win_rate_pct']:.1f}% | Profit Factor: {res['profit_factor']:.2f}")
    print(f"Max Drawdown     : -{res['max_drawdown_pct']:.2f}% | Annualized Sharpe: {res['sharpe']:.2f}")
