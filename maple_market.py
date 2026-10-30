"""
MAPLE Self-Contained Market Data, Technical Indicator & Macro Alignment Engine.
Computes real-time TSX technicals, 24h-cached corporate calendars, and commodity macro alignment
locally within MAPLE with zero external folder dependencies.
"""

import os
import json
import time
import datetime
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import pandas_ta as ta
import yfinance as yf

try:
    from zoneinfo import ZoneInfo
    _ET_TZ = ZoneInfo("America/Toronto")
except Exception:
    _ET_TZ = None

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
CALENDAR_CACHE_FILE = os.path.join(MAPLE_DIR, "corporate_calendar_cache.json")
CALENDAR_CACHE_TTL = 86400  # 24 hours

GOLD_LINKED_TICKERS = {"ABX.TO", "AEM.TO", "FNV.TO", "WPM.TO", "PAAS.TO", "AGI.TO"}
OIL_LINKED_TICKERS = {"CNQ.TO", "SU.TO", "IMO.TO", "CVE.TO"}


def _now_et() -> datetime.datetime:
    if _ET_TZ is not None:
        return datetime.datetime.now(_ET_TZ)
    return datetime.datetime.now()


def get_corporate_calendar(tickers: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Fetches and caches upcoming earnings and ex-dividend dates locally in MAPLE (24h TTL)."""
    cache_ts = 0.0
    calendar_data: Dict[str, Dict[str, Any]] = {}

    if os.path.exists(CALENDAR_CACHE_FILE):
        try:
            with open(CALENDAR_CACHE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cache_ts = float(raw.get("_timestamp", 0.0))
            if time.time() - cache_ts < CALENDAR_CACHE_TTL and isinstance(raw.get("calendar"), dict):
                calendar_data = dict(raw["calendar"])
        except Exception:
            calendar_data = {}

    req_tickers = list(tickers or [])
    missing = [t for t in req_tickers if t not in calendar_data]
    if not missing and calendar_data:
        return calendar_data

    now_date = datetime.date.today()
    for t in missing:
        ed_str, days_to_ed, ex_div_str, days_to_ex_div = "N/A", None, "N/A", None
        try:
            cal = yf.Ticker(t).calendar
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if isinstance(ed, list) and ed and isinstance(ed[0], datetime.date):
                    ed_date = ed[0]
                    ed_str = ed_date.strftime("%Y-%m-%d")
                    days_to_ed = (ed_date - now_date).days
                ex_div = cal.get("Ex-Dividend Date")
                if isinstance(ex_div, datetime.date):
                    ex_div_str = ex_div.strftime("%Y-%m-%d")
                    days_to_ex_div = (ex_div - now_date).days
        except Exception:
            pass

        calendar_data[t] = {
            "earnings_date": ed_str,
            "days_to_earnings": days_to_ed,
            "ex_dividend_date": ex_div_str,
            "days_to_ex_dividend": days_to_ex_div,
        }

    new_ts = cache_ts if (cache_ts > 0 and time.time() - cache_ts < CALENDAR_CACHE_TTL) else time.time()
    try:
        with open(CALENDAR_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"_timestamp": new_ts, "calendar": calendar_data}, f, indent=2)
    except Exception:
        pass

    return calendar_data


def prefetch_histories(tickers: List[str], period: str = "6mo") -> Dict[str, pd.DataFrame]:
    """Batch-downloads OHLCV histories via yfinance for fast 32-ticker scans."""
    prefetched: Dict[str, pd.DataFrame] = {}
    if len(tickers) <= 1:
        return prefetched
    try:
        raw = yf.download(tickers, period=period, group_by="ticker", threads=True, timeout=15, progress=False)
        for t in tickers:
            try:
                df = raw[t].dropna(how="all")
                if not df.empty:
                    prefetched[t] = df
            except Exception:
                pass
    except Exception:
        pass
    return prefetched


def _expected_intraday_vol_fraction(minutes_passed: float) -> float:
    """TSX pre-MOC cumulative volume curve (~4.5% open cross + ~63.5% continuous + ~32% 4pm MOC)."""
    # ponytail: fixed TSX auction curve; fit per-ticker intraday profile only if small-cap dispersion requires it
    if minutes_passed <= 0.0 or minutes_passed >= 390.0:
        return 1.0
    return 0.045 + 0.635 * (max(minutes_passed, 5.0) / 390.0)


def get_stock_data(
    ticker_symbol: str,
    mode: str = "SHORT",
    prefetched_hist: Optional[pd.DataFrame] = None,
) -> Optional[Dict[str, Any]]:
    """Computes technical indicators and corporate event proximity for a TSX ticker."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        req_cols = {"Open", "High", "Low", "Close", "Volume"}
        if prefetched_hist is not None and not prefetched_hist.empty and req_cols.issubset(prefetched_hist.columns):
            hist = prefetched_hist.copy()
        else:
            hist = ticker.history(period="6mo", timeout=10)
        if hist is None or hist.empty:
            return None

        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else latest
        prev_close = float(prev["Close"])
        gap_pct = ((float(latest["Open"]) - prev_close) / prev_close) * 100.0 if prev_close > 0 else 0.0
        pct_from_low = ((float(latest["Close"]) - float(latest["Low"])) / float(latest["Low"])) * 100.0 if float(latest["Low"]) > 0 else 0.0
        cal = get_corporate_calendar([ticker_symbol]).get(ticker_symbol, {})

        if mode == "SHORT":
            hist.ta.ema(length=5, append=True)
            hist.ta.ema(length=9, append=True)
            hist.ta.sma(length=50, append=True)
            hist.ta.rsi(length=7, append=True)
            hist.ta.atr(length=5, append=True)
            hist.ta.bbands(length=20, std=2, append=True)
            hist.ta.adx(length=14, append=True)

            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else latest

            if len(hist) > 10:
                vol_sma_10 = float(hist["Volume"].iloc[:-1].tail(10).mean())
            else:
                vol_sma_10 = float(hist["Volume"].rolling(window=10).mean().iloc[-1])

            now_et = _now_et()
            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            if now_et < market_open:
                minutes_passed = 0.0
            elif now_et > market_close:
                minutes_passed = 390.0
            else:
                minutes_passed = (now_et - market_open).total_seconds() / 60.0

            adjusted_sma = vol_sma_10 * _expected_intraday_vol_fraction(minutes_passed)
            vol_ratio = (float(latest["Volume"]) / adjusted_sma) if adjusted_sma > 0 else 1.0

            price = float(latest["Close"])
            ema_5 = float(latest["EMA_5"]) if "EMA_5" in latest and pd.notna(latest["EMA_5"]) else 0.0
            ema_9 = float(latest["EMA_9"]) if "EMA_9" in latest and pd.notna(latest["EMA_9"]) else 0.0
            prev_ema_5 = float(prev["EMA_5"]) if "EMA_5" in prev and pd.notna(prev["EMA_5"]) else ema_5
            dmp_14 = float(latest["DMP_14"]) if "DMP_14" in latest and pd.notna(latest["DMP_14"]) else 0.0
            dmn_14 = float(latest["DMN_14"]) if "DMN_14" in latest and pd.notna(latest["DMN_14"]) else 0.0
            sma_50 = float(latest["SMA_50"]) if "SMA_50" in latest and pd.notna(latest["SMA_50"]) else 0.0

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

            bb_lower_col = next((c for c in hist.columns if c.startswith("BBL_")), None)
            bb_mid_col = next((c for c in hist.columns if c.startswith("BBM_")), None)
            bb_upper_col = next((c for c in hist.columns if c.startswith("BBU_")), None)

            return {
                "Prev_Close": round(prev_close, 2),
                "Gap_Pct": round(gap_pct, 2),
                "Pct_From_Low": round(pct_from_low, 2),
                "Open": round(float(latest["Open"]), 2),
                "High": round(float(latest["High"]), 2),
                "Low": round(float(latest["Low"]), 2),
                "Price": round(price, 2),
                "Volume": int(latest["Volume"]),
                "Vol_Ratio": round(vol_ratio, 2),
                "EMA_Crossover": crossover,
                "EMA_5": round(ema_5, 2) if ema_5 > 0 else "N/A",
                "EMA_9": round(ema_9, 2) if ema_9 > 0 else "N/A",
                "RSI_7": round(float(latest["RSI_7"]), 2) if "RSI_7" in latest and pd.notna(latest["RSI_7"]) else "N/A",
                "ATR_5": round(float(latest["ATRr_5"]), 2) if "ATRr_5" in latest and pd.notna(latest["ATRr_5"]) else "N/A",
                "ADX_14": round(float(latest["ADX_14"]), 2) if "ADX_14" in latest and pd.notna(latest["ADX_14"]) else "N/A",
                "BB_Lower": round(float(latest[bb_lower_col]), 2) if bb_lower_col and pd.notna(latest[bb_lower_col]) else "N/A",
                "BB_Mid": round(float(latest[bb_mid_col]), 2) if bb_mid_col and pd.notna(latest[bb_mid_col]) else "N/A",
                "BB_Upper": round(float(latest[bb_upper_col]), 2) if bb_upper_col and pd.notna(latest[bb_upper_col]) else "N/A",
                "earnings_date": cal.get("earnings_date", "N/A"),
                "days_to_earnings": cal.get("days_to_earnings"),
                "ex_dividend_date": cal.get("ex_dividend_date", "N/A"),
                "days_to_ex_dividend": cal.get("days_to_ex_dividend"),
            }

        hist.ta.rsi(length=14, append=True)
        hist.ta.sma(length=50, append=True)
        hist.ta.bbands(length=50, std=2, append=True)
        latest = hist.iloc[-1]
        bb_upper_col = next((c for c in hist.columns if c.startswith("BBU_")), None)
        return {
            "Prev_Close": round(prev_close, 2),
            "Gap_Pct": round(gap_pct, 2),
            "Pct_From_Low": round(pct_from_low, 2),
            "Open": round(float(latest["Open"]), 2),
            "High": round(float(latest["High"]), 2),
            "Low": round(float(latest["Low"]), 2),
            "Price": round(float(latest["Close"]), 2),
            "Volume": int(latest["Volume"]),
            "RSI_14": round(float(latest["RSI_14"]), 2) if "RSI_14" in latest and pd.notna(latest["RSI_14"]) else "N/A",
            "SMA_50": round(float(latest["SMA_50"]), 2) if "SMA_50" in latest and pd.notna(latest["SMA_50"]) else "N/A",
            "BB_Upper": round(float(latest[bb_upper_col]), 2) if bb_upper_col and pd.notna(latest[bb_upper_col]) else "N/A",
            "earnings_date": cal.get("earnings_date", "N/A"),
            "days_to_earnings": cal.get("days_to_earnings"),
            "ex_dividend_date": cal.get("ex_dividend_date", "N/A"),
            "days_to_ex_dividend": cal.get("days_to_ex_dividend"),
        }
    except Exception:
        return None


def get_macro_alignment() -> Dict[str, bool]:
    """Checks intraday/daily directional alignment for Gold (GC=F) and Crude Oil (CL=F)."""
    state = {"GC=F": True, "CL=F": True}
    for sym in ("GC=F", "CL=F"):
        try:
            hist = yf.Ticker(sym).history(period="5d", timeout=8)
            if hist is not None and len(hist) >= 2:
                state[sym] = float(hist["Close"].iloc[-1]) >= float(hist["Close"].iloc[-2])
        except Exception:
            pass
    return state


def is_macro_aligned(ticker: str, macro_state: Optional[Dict[str, bool]] = None) -> Tuple[bool, str]:
    """Verifies underlying commodity tailwind before buying Precious Metals or Oil & Gas stocks."""
    if not macro_state:
        return True, "Aligned"
    t = ticker.strip().upper()
    if t in GOLD_LINKED_TICKERS and not macro_state.get("GC=F", True):
        return False, "Gold futures (GC=F) negative vs prior close"
    if t in OIL_LINKED_TICKERS and not macro_state.get("CL=F", True):
        return False, "Crude Oil futures (CL=F) negative vs prior close"
    return True, "Aligned"
