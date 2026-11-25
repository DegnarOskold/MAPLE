"""
MAPLE Ledger Engine
Handles trade execution, ACB (Adjusted Cost Base) tracking, cash balance,
target/stop auto-execution, and portfolio valuation.
Supports both LIVE trading (via QuestradeClient with Limit Orders)
and SIMULATED paper-trading mode.
"""

import os
import csv
import json
import datetime
from typing import Dict, Any, Optional

from maple_market import now_et_naive, count_nyse_trading_days
def get_broker_client():
    """Factory to instantiate the active Interactive Brokers client."""
    from ibkr_client import IBKRClient
    return IBKRClient()

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(MAPLE_DIR, "maple_trades.csv")
CONFIG_FILE = os.path.join(MAPLE_DIR, "maple_config.json")
ADVICE_FILE = os.path.join(MAPLE_DIR, "maple_advice_history.txt")
NAV_FILE = os.path.join(MAPLE_DIR, "maple_daily_nav.json")

# Strict Gatekeeper Universe: No order may be submitted outside this basket (53 Zoya-certified US tickers; COST excluded)
SHARIAH_COMPLIANT_BASKET = {
    # Technology & Semiconductors (19)
    "AAPL", "NVDA", "AVGO", "AMD", "ANET", "QCOM", "TXN", "AMAT", "LRCX", "MRVL", "ON",
    "CRWD", "PANW", "FTNT", "SNPS", "CDNS", "CRM", "ADBE", "CSCO",
    # Healthcare & MedTech (9)
    "LLY", "JNJ", "ABBV", "MRK", "GILD", "ISRG", "BSX", "EW", "DHR",
    # Energy (5)
    "XOM", "CVX", "COP", "EOG", "SLB",
    # Industrials & Logistics (7)
    "ETN", "EMR", "ROK", "ITW", "ODFL", "FAST", "CSX",
    # Consumer & Retail (8)
    "PG", "KO", "PEP", "HD", "TJX", "TSLA", "NKE", "MNST",
    # Materials & Mining (5)
    "APD", "SHW", "VMC", "FCX", "NEM",
}

SECTOR_MAP = {
    # Technology & Semiconductors (19)
    "AAPL": "Technology", "NVDA": "Technology", "AVGO": "Technology", "AMD": "Technology",
    "ANET": "Technology", "QCOM": "Technology", "TXN": "Technology", "AMAT": "Technology",
    "LRCX": "Technology", "MRVL": "Technology", "ON": "Technology", "CRWD": "Technology",
    "PANW": "Technology", "FTNT": "Technology", "SNPS": "Technology", "CDNS": "Technology",
    "CRM": "Technology", "ADBE": "Technology", "CSCO": "Technology",
    # Healthcare & MedTech (9)
    "LLY": "Healthcare", "JNJ": "Healthcare", "ABBV": "Healthcare", "MRK": "Healthcare",
    "GILD": "Healthcare", "ISRG": "Healthcare", "BSX": "Healthcare", "EW": "Healthcare", "DHR": "Healthcare",
    # Energy (5)
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "EOG": "Energy", "SLB": "Energy",
    # Industrials & Logistics (7)
    "ETN": "Industrials", "EMR": "Industrials", "ROK": "Industrials", "ITW": "Industrials",
    "ODFL": "Industrials", "FAST": "Industrials", "CSX": "Industrials",
    # Consumer & Retail (8)
    "PG": "Consumer", "KO": "Consumer", "PEP": "Consumer", "HD": "Consumer",
    "TJX": "Consumer", "TSLA": "Consumer", "NKE": "Consumer", "MNST": "Consumer",
    # Materials & Mining (5)
    "APD": "Materials", "SHW": "Materials", "VMC": "Materials", "FCX": "Materials", "NEM": "Materials",
}

_LEGACY_TSX_SECTORS = {
    "ABX.TO": "Precious Metals", "AEM.TO": "Precious Metals", "FNV.TO": "Precious Metals",
    "WPM.TO": "Precious Metals", "PAAS.TO": "Precious Metals", "AGI.TO": "Precious Metals",
    "CNQ.TO": "Energy & Uranium", "SU.TO": "Energy & Uranium", "IMO.TO": "Energy & Uranium",
    "CVE.TO": "Energy & Uranium", "CCO.TO": "Energy & Uranium",
    "TECK-B.TO": "Base Metals & Materials", "RUS.TO": "Base Metals & Materials", "WFG.TO": "Base Metals & Materials",
    "SHOP.TO": "Technology", "CSU.TO": "Technology", "GIB-A.TO": "Technology",
    "CLS.TO": "Technology", "DSG.TO": "Technology", "KXS.TO": "Technology", "ENGH.TO": "Technology",
    "CP.TO": "Industrials & Rail", "CNR.TO": "Industrials & Rail", "WCN.TO": "Industrials & Rail",
    "TIH.TO": "Industrials & Rail", "ATRL.TO": "Industrials & Rail", "STN.TO": "Industrials & Rail", "TFII.TO": "Industrials & Rail",
    "SAP.TO": "Consumer & Packaging", "ATZ.TO": "Consumer & Packaging",
    "CCL-B.TO": "Consumer & Packaging", "RCH.TO": "Consumer & Packaging",
}


SWEEP_ETF = "SPUS"


def get_ticker_sector(ticker: str) -> str:
    """Returns canonical sector classification for any Shariah-compliant ticker."""
    norm = normalize_ticker(ticker)
    if norm == SWEEP_ETF:
        return "Shariah ETF (Sweep)"
    return SECTOR_MAP.get(norm, _LEGACY_TSX_SECTORS.get(norm, "Other"))


def normalize_ticker(ticker: str) -> str:
    """Normalizes US tickers (e.g. BRK.B -> BRK-B) while preserving explicit .TO suffixes."""
    t = ticker.strip().upper()
    if not t or t == "CASH":
        return t
    if t.endswith(".TO"):
        return f"{t[:-3].replace('.', '-')}.TO"
    return t.replace(".", "-")


def ticker_aliases(ticker: str) -> list[str]:
    """Returns canonical hyphen and dot aliases for US or TSX tickers."""
    norm = normalize_ticker(ticker)
    if norm.endswith(".TO"):
        base_hyphen = norm[:-3]
        base_dot = base_hyphen.replace("-", ".")
        return list(dict.fromkeys([norm, f"{base_dot}.TO", base_hyphen, base_dot, ticker.strip().upper()]))
    base_dot = norm.replace("-", ".")
    return list(dict.fromkeys([norm, base_dot, ticker.strip().upper()]))



def load_config() -> Dict[str, Any]:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: Dict[str, Any]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def get_net_contributions(
    config: Optional[Dict[str, Any]] = None,
    after_date: Optional[str] = None,
    up_to_date: Optional[str] = None,
) -> float:
    """Returns net external cash inflows/outflows recorded in config['capital_contributions'] over (after_date, up_to_date]."""
    cfg = config if config is not None else load_config()
    contribs = cfg.get("capital_contributions") or {}
    if not isinstance(contribs, dict):
        return 0.0
    total = 0.0
    for d_str, amt in contribs.items():
        d_key = str(d_str)[:10]
        if after_date and d_key <= after_date[:10]:
            continue
        if up_to_date and d_key > up_to_date[:10]:
            continue
        try:
            total += float(amt)
        except (TypeError, ValueError):
            pass
    return round(total, 2)


def get_total_invested_capital(
    config: Optional[Dict[str, Any]] = None,
    up_to_date: Optional[str] = None,
) -> float:
    """Returns initial_cash plus cumulative net external capital contributions."""
    cfg = config if config is not None else load_config()
    return round(float(cfg.get("initial_cash", 1000.0)) + get_net_contributions(cfg, up_to_date=up_to_date), 2)


def compute_twr_pct(
    current_equity: float,
    config: Optional[Dict[str, Any]] = None,
    today_str: Optional[str] = None,
    nav_history: Optional[Dict[str, Any]] = None,
) -> float:
    """Computes cash-flow-adjusted Time-Weighted Return (%) chained across maple_daily_nav.json snapshots."""
    cfg = config if config is not None else load_config()
    seed = float(cfg.get("initial_cash", 1000.0))
    hist = nav_history
    if hist is None:
        hist = {}
        if os.path.exists(NAV_FILE):
            try:
                with open(NAV_FILE, "r", encoding="utf-8") as f:
                    hist = json.load(f)
            except Exception:
                hist = {}
    t_str = (today_str or now_et_naive().strftime("%Y-%m-%d"))[:10]
    dates = [d for d in sorted(hist.keys()) if d < t_str]
    if not dates:
        inv = get_total_invested_capital(cfg, up_to_date=t_str)
        return round(((current_equity - inv) / inv) * 100.0, 2) if inv > 0 else 0.0

    growth = 1.0
    first_d = dates[0]
    first_nav = float(hist[first_d].get("nav") or seed)
    init_base = seed + get_net_contributions(cfg, up_to_date=first_d)
    if init_base > 0 and first_nav > 0:
        growth *= first_nav / init_base

    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        n0 = float(hist[d0].get("nav") or 0.0)
        n1 = float(hist[d1].get("nav") or 0.0)
        denom = n0 + get_net_contributions(cfg, after_date=d0, up_to_date=d1)
        if denom > 0 and n1 > 0:
            growth *= n1 / denom

    last_d = dates[-1]
    last_nav = float(hist[last_d].get("nav") or 0.0)
    final_denom = last_nav + get_net_contributions(cfg, after_date=last_d, up_to_date=t_str)
    if final_denom > 0 and current_equity > 0:
        growth *= current_equity / final_denom

    return round((growth - 1.0) * 100.0, 2)


def get_effective_order_cap(config: Dict[str, Any], total_equity: float) -> float:
    """Scales max_single_order_cad dynamically with portfolio NAV (at least config floor or max_position_pct of NAV)."""
    base_cap = float(config.get("max_single_order_cad", 400.0))
    max_pos_pct = float(config.get("max_position_pct", 0.25))
    return round(max(base_cap, total_equity * max_pos_pct), 2)


def get_effective_min_trade(config: Dict[str, Any], total_equity: float) -> float:
    """Scales min_trade_cad dynamically with portfolio NAV (at least config floor or min_trade_pct of NAV)."""
    base_min = float(config.get("min_trade_cad", 50.0))
    min_pct = float(config.get("min_trade_pct", 0.05))
    return round(max(base_min, total_equity * min_pct), 2)


def _resolve_buy_stop(
    config: Dict[str, Any],
    ticker: str,
    candidate_stop: float,
    fill_price: float,
    existing_shares: float,
    blended_acb: Optional[float] = None,
) -> float:
    """Preserves ratcheted stop_loss_price (< fill_price) when scaling in without wiping out profit-locked stops."""
    if existing_shares > 0:
        eff_acb = blended_acb if (isinstance(blended_acb, (int, float)) and blended_acb > 0) else fill_price
        trail_cap = round(fill_price * 0.9875, 2)
        post_scale_gain_pct = (((fill_price - eff_acb) / eff_acb) * 100.0) if eff_acb > 0 else 0.0
        # When blended position remains >= +2.5% in profit, preserve ratcheted stop up to -1.25% below fill;
        # when blending pulls gain below +2.5%, cap at half-risk (-2.5% below blended ACB) to prevent tight-stop shakeouts.
        max_scale_stop = trail_cap if post_scale_gain_pct >= 2.5 else min(trail_cap, round(eff_acb * 0.975, 2))
        active_targets = config.get("active_targets", {})
        for alias in ticker_aliases(ticker):
            existing_stop = (active_targets.get(alias) or {}).get("stop_loss_price")
            if isinstance(existing_stop, (int, float)) and existing_stop < fill_price:
                candidate_stop = max(candidate_stop, min(float(existing_stop), max_scale_stop))
    return round(candidate_stop, 2)


def get_effective_daily_loss_limit(config: Dict[str, Any], ref_nav: float) -> float:
    """Scales daily drawdown circuit breaker to max(daily_loss_limit_cad, daily_loss_limit_pct * ref_nav)."""
    base_lim = float(config.get("daily_loss_limit_cad", 40.0))
    lim_pct = float(config.get("daily_loss_limit_pct", 0.04))
    return round(max(base_lim, ref_nav * lim_pct), 2)


def reconcile_capital_flows(
    live_cash: float,
    live_equity: Optional[float] = None,
    config: Optional[Dict[str, Any]] = None,
    today_str: Optional[str] = None,
) -> float:
    """Auto-detects settled external broker deposits/withdrawals (>= CAD $250 in BOTH cash and equity)."""
    cfg = config if config is not None else load_config()
    if cfg.get("pending_orders"):
        return 0.0
    if not os.path.exists(NAV_FILE):
        return 0.0
    t_str = (today_str or now_et_naive().strftime("%Y-%m-%d"))[:10]
    try:
        with open(NAV_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        return 0.0

    prev_dates = [d for d in sorted(history.keys()) if d < t_str]
    if not prev_dates:
        return 0.0
    last_date = prev_dates[-1]
    prev_cash = float(history[last_date].get("cash", 0.0))
    prev_nav = float(history[last_date].get("nav", 0.0))

    comm_est = float(cfg.get("commission_per_order_cad", 1.0))
    net_trade_cash = 0.0
    last_csv_cash_today: Optional[float] = None
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    d_row = row.get("Date", "")[:10]
                    if last_date < d_row <= t_str:
                        act = row.get("Action", "").strip().upper()
                        qty = float(row.get("Quantity", 0.0))
                        px = float(row.get("Price", 0.0))
                        if act == "BUY":
                            net_trade_cash -= (qty * px + comm_est)
                        elif act == "SELL":
                            net_trade_cash += (qty * px - comm_est)
                            cb = row.get("Cash_Balance")
                            if cb not in (None, ""):
                                cb_val = float(cb)
                                if cb_val > 0.0:
                                    last_csv_cash_today = cb_val
        except Exception:
            return 0.0

    contribs = cfg.setdefault("capital_contributions", {})
    prior_recorded = get_net_contributions(cfg, after_date=last_date, up_to_date=t_str)
    already_today = float(contribs.get(t_str, 0.0))
    rough_unrecorded = live_cash - (prev_cash + net_trade_cash + prior_recorded)
    if abs(rough_unrecorded) < 250.0:
        return 0.0

    # External deposits/withdrawals move BOTH cash and total_equity in the same direction (unlike stock sales or price swings)
    if live_equity is not None and prev_nav > 0:
        eq_unrecorded = float(live_equity) - (prev_nav + prior_recorded)
        if abs(eq_unrecorded) < 250.0 or (eq_unrecorded * rough_unrecorded) <= 0:
            return 0.0

    if already_today == 0.0 and last_csv_cash_today is not None:
        exact_delta = round(live_cash - last_csv_cash_today, 2)
    elif net_trade_cash == 0.0 and prior_recorded == 0.0:
        exact_delta = round(live_cash - prev_cash, 2)
    else:
        exact_delta = round(rough_unrecorded, 2)

    if abs(exact_delta) < 250.0:
        return 0.0

    contribs[t_str] = round(already_today + exact_delta, 2)
    save_config(cfg)
    print(f"[MAPLE CAPITAL FLOW] Auto-detected settled external cash flow on {t_str}: CAD {exact_delta:+.2f} (Total {t_str}: CAD {contribs[t_str]:+.2f})")
    return exact_delta


def _get_reference_nav(config: Dict[str, Any]) -> float:
    """Returns previous day's closing NAV adjusted for any settled capital contributions since that close."""
    today_str = now_et_naive().strftime("%Y-%m-%d")
    if os.path.exists(NAV_FILE):
        try:
            with open(NAV_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            prev_dates = [d for d in sorted(history.keys()) if d < today_str]
            if prev_dates:
                last_date = prev_dates[-1]
                nav = float(history[last_date].get("nav", 0.0))
                if nav > 0:
                    return round(nav + get_net_contributions(config, after_date=last_date, up_to_date=today_str), 2)
        except Exception:
            pass
    return get_total_invested_capital(config, up_to_date=today_str)


def get_ledger_state() -> Dict[str, Any]:
    """Returns current portfolio state.
    In LIVE mode, queries active broker API (IBKR/Questrade) for real account balances and positions.
    In SIMULATED mode, reconstructs state from maple_trades.csv.
    """
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"
    live_fallback = False
    live_error = ""

    if is_live:
        try:
            client = get_broker_client()
            if not client.is_authenticated():
                raise ConnectionError("Broker gateway is not authenticated (please log in at https://localhost:5000)")
            account_id = config.get("account_id") or client.get_primary_account_id()
            balances = client.get_balances(account_id)
            if not balances or (float(balances.get("total_equity", 0.0)) <= 0.0 and float(balances.get("cash", 0.0)) <= 0.0):
                raise ValueError("Broker returned 0 equity/cash or is re-authenticating.")
            positions_raw = client.get_positions(account_id)
            active_targets = config.get("active_targets", {})

            positions = {}
            for p in positions_raw:
                sym = normalize_ticker(p.get("symbol", ""))
                shares = float(p.get("openQuantity", 0.0))
                if shares > 0:
                    acb = float(p.get("averageEntryPrice", 0.0))
                    cur_p = float(p.get("currentPrice", acb))
                    tgt, stp = None, None
                    for alias in ticker_aliases(sym):
                        if alias in active_targets:
                            tgt = active_targets[alias].get("target_price")
                            stp = active_targets[alias].get("stop_loss_price")
                            break
                    positions[sym] = {
                        "shares": shares,
                        "acb": round(acb, 2),
                        "total_cost": round(shares * acb, 2),
                        "current_price": cur_p,
                        "symbol_id": p.get("symbolId"),
                        "target_price": tgt,
                        "stop_loss_price": stp if stp else round(acb * 0.95, 2)
                    }

            cash_live = round(float(balances.get("cash", 0.0)), 2)
            eq_live = round(float(balances.get("total_equity", 0.0)), 2)
            try:
                reconcile_capital_flows(cash_live, live_equity=eq_live, config=config)
            except Exception:
                pass

            return {
                "positions": positions,
                "cash": cash_live,
                "total_equity": eq_live,
                "buying_power": round(float(balances.get("buying_power", 0.0)), 2),
                "mode": "LIVE",
                "live_verified": True,
                "account_id": account_id
            }
        except Exception as e:
            live_fallback = True
            live_error = str(e)
            broker_name = config.get("broker", "IBKR")
            print(f"[MAPLE WARNING] Failed to query live {broker_name} state ({e}), falling back to local ledger.")

    # Simulated or fallback ledger reconstruction
    positions: Dict[str, Dict[str, Any]] = {}
    cash = 0.0
    usd_only = str(config.get("account_currency", "")).upper() == "USD"

    if not os.path.exists(TRADES_FILE):
        return {
            "positions": positions,
            "cash": 0.0,
            "total_equity": 0.0,
            "mode": "SIMULATED",
            "live_verified": False,
            "live_fallback": live_fallback,
            "live_error": live_error,
        }

    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ticker = normalize_ticker(row["Ticker"])
                action = row["Action"].upper()
                qty = float(row["Quantity"])
                price = float(row["Price"])
                cash_bal = row.get("Cash_Balance")
                if cash_bal not in (None, ""):
                    cash = float(cash_bal)
            except (ValueError, KeyError):
                continue

            if ticker.upper() == "CASH" or (usd_only and ticker.endswith(".TO")):
                continue

            if ticker not in positions:
                positions[ticker] = {
                    "shares": 0.0,
                    "total_cost": 0.0,
                    "acb": 0.0,
                    "target_price": None,
                    "stop_loss_price": None,
                }

            pos = positions[ticker]
            if action in ["BUY", "INIT"]:
                pos["shares"] += qty
                pos["total_cost"] += qty * price
                if pos["shares"] > 0:
                    pos["acb"] = pos["total_cost"] / pos["shares"]
            elif action == "SELL":
                pos["shares"] -= qty
                pos["total_cost"] -= qty * pos["acb"]
                if pos["shares"] <= 0.00001:
                    pos["shares"] = 0.0
                    pos["total_cost"] = 0.0
                    pos["acb"] = 0.0
                    pos["target_price"] = None
                    pos["stop_loss_price"] = None

    active_targets = config.get("active_targets", {})
    init_portfolio = config.get("initial_portfolio", {})
    for t, pos in positions.items():
        if pos["shares"] > 0:
            for alias in ticker_aliases(t):
                if alias in active_targets:
                    pos["target_price"] = active_targets[alias].get("target_price")
                    pos["stop_loss_price"] = active_targets[alias].get("stop_loss_price")
                    break
                elif alias in init_portfolio:
                    pos["target_price"] = init_portfolio[alias].get("target_price")
                    pos["stop_loss_price"] = init_portfolio[alias].get("stop_loss_price")
                    break

    fallback_equity = round(cash + sum(p["shares"] * p["acb"] for p in positions.values() if p["shares"] > 0), 2)
    return {
        "positions": positions,
        "cash": round(cash, 2),
        "total_equity": fallback_equity,
        "mode": "SIMULATED",
        "live_verified": False,
        "live_fallback": live_fallback,
        "live_error": live_error,
    }


def log_trade(
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    shares_balance: float,
    cash_balance: float,
    notes: str = "",
):
    timestamp = now_et_naive().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        timestamp,
        ticker,
        action.upper(),
        f"{quantity:.4f}",
        f"{price:.2f}",
        f"{shares_balance:.4f}",
        f"{cash_balance:.2f}",
        notes,
    ]
    file_exists = os.path.exists(TRADES_FILE)
    with open(TRADES_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "Date",
                    "Ticker",
                    "Action",
                    "Quantity",
                    "Price",
                    "Shares_Balance",
                    "Cash_Balance",
                    "Notes",
                ]
            )
        writer.writerow(row)


def _size_whole_shares(
    ticker: str,
    allocated_cash: float,
    unit_price: float,
    existing_shares: float,
    existing_val: float,
    total_equity: float,
    max_pos_pct: float,
    max_single_cap: float,
    sector_exposure: float,
    max_sector_pct: float,
    avail_cash: float,
    max_single_share_pct: float,
) -> int:
    """Sizes whole shares, rounding >=0.5 fractional shares up when +1 share respects all risk caps."""
    if unit_price <= 0:
        return 0
    shares = int(allocated_cash / unit_price)
    if shares >= 1 and (allocated_cash / unit_price - shares) >= 0.5:
        cand_cost = (shares + 1) * unit_price
        if (
            cand_cost <= allocated_cash * 1.15
            and existing_val + cand_cost <= total_equity * max_pos_pct
            and cand_cost <= max_single_cap
            and sector_exposure + cand_cost <= total_equity * max_sector_pct
            and cand_cost <= avail_cash
        ):
            shares += 1
    elif shares <= 0 and existing_shares == 0:
        if (
            unit_price <= total_equity * max_single_share_pct
            and unit_price <= max_single_cap
            and sector_exposure + unit_price <= total_equity * max_sector_pct
            and unit_price <= avail_cash
        ):
            shares = 1
            print(
                f"[MAPLE 1-SHARE FLOOR] Sizing 1 whole share of {ticker} @ ${unit_price:.2f} "
                f"({unit_price / total_equity * 100:.1f}% of NAV <= {max_single_share_pct * 100:.0f}% single-share cap)."
            )
    return shares


def _preflight_buy(
    ticker: str,
    allocated_cash: float,
    current_price: float,
    notes: str = "",
    open_price: Optional[float] = None,
    check_cash: bool = True,
) -> Optional[Dict[str, Any]]:
    """Validates all pre-trade BUY guards and returns sizing/broker context, or None if blocked."""
    ticker = normalize_ticker(ticker)
    is_sweep = ticker == SWEEP_ETF
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"

    # Circuit Breaker 1: Strict Shariah Basket Gatekeeper (SPUS allowed as idle-cash sweep ETF)
    if not is_sweep and ticker not in SHARIAH_COMPLIANT_BASKET:
        print(f"[MAPLE GATEKEEPER REJECT] {ticker} is NOT in the Shariah-compliant basket! Order blocked.")
        return None

    # Block duplicate order if already working on book
    pending_orders = config.get("pending_orders", {})
    if any(a in pending_orders for a in ticker_aliases(ticker)):
        print(f"[MAPLE] Pending order already active for {ticker}. Skipping duplicate BUY.")
        return None

    is_stage2_mode = str(config.get("strategy_mode", "")).upper() == "STAGE2_RS"
    max_slots = max(1, int(config.get("max_open_positions", 5)))

    def _passes_scale_in_guards(active_tickers: Optional[set] = None, fallback_px: float = 0.0) -> bool:
        buy_counts = get_position_buy_counts(active_tickers=active_tickers) if active_tickers is not None else get_position_buy_counts()
        eff_count = buy_counts.get(ticker, 0)
        if active_tickers is not None and ticker in active_tickers and eff_count == 0:
            eff_count = 1
        max_entries = 1 if is_stage2_mode else 2
        if eff_count >= max_entries:
            print(f"[MAPLE SCALE CAP] {ticker} already has {eff_count} entry in active cycle (max {max_entries} allowed). Order blocked.")
            return False
        cooldown_hrs = float(config.get("scale_in_cooldown_hours", 4.0))
        now_dt = now_et_naive()
        if eff_count == 0:
            exit_info = get_last_loss_exit_info().get(ticker)
            if exit_info and exit_info.get("last_exit_dt"):
                elapsed_exit_hrs = (now_dt - exit_info["last_exit_dt"]).total_seconds() / 3600.0
                if 0.0 <= elapsed_exit_hrs < cooldown_hrs:
                    print(
                        f"[MAPLE RE-ENTRY COOLDOWN] {ticker} exited via stop/stagnation {elapsed_exit_hrs:.2f}h ago (< {cooldown_hrs:.1f}h cooldown). Blocking whipsaw re-entry."
                    )
                    return False
        if eff_count >= 1:
            last_map = get_position_last_buy_info(active_tickers=active_tickers) if active_tickers is not None else get_position_last_buy_info()
            last_buy = last_map.get(ticker)
            if last_buy and last_buy.get("last_buy_dt"):
                elapsed_hrs = (now_dt - last_buy["last_buy_dt"]).total_seconds() / 3600.0
                if elapsed_hrs < cooldown_hrs:
                    print(
                        f"[MAPLE SCALE COOLDOWN] {ticker} entered {elapsed_hrs:.2f}h ago (< {cooldown_hrs:.1f}h cooldown). Blocking rapid scale-in."
                    )
                    return False
            if isinstance(open_price, (int, float)) and open_price > 0 and current_price <= open_price:
                print(
                    f"[MAPLE SCALE GUARD] Blocking scale-in #2 for {ticker} on red/flat candle (Price ${current_price:.2f} <= Open ${open_price:.2f})."
                )
                return False
            last_px = float((last_buy or {}).get("last_buy_price") or fallback_px or 0.0)
            if last_px > 0:
                min_gain_pct = 1.0 if "LOW-VOLUME" in notes.upper() else 0.5
                req_px = round(last_px * (1.0 + min_gain_pct / 100.0), 2)
                if current_price < req_px:
                    print(
                        f"[MAPLE SCALE GUARD] Blocking scale-in #2 for {ticker}: Price ${current_price:.2f} < ${req_px:.2f} "
                        f"(+{min_gain_pct:.1f}% min progress over Entry #1 ${last_px:.2f})."
                    )
                    return False
        return True

    # In SIMULATED mode, maple_trades.csv is the ledger of record; in LIVE mode, reconcile against IBKR positions first
    if not is_live and not is_sweep and not _passes_scale_in_guards():
        return None

    min_trade_thresh = config.get("min_trade_cad", 50.0)
    max_pos_pct = config.get("max_position_pct", 0.25)
    max_sector_pct = float(config.get("max_sector_pct", 0.35))
    target_sector = get_ticker_sector(ticker)

    pending_sector_cad = sum(
        float(po.get("shares", 0.0)) * float(po.get("limit_price", 0.0))
        for raw_tk, po in pending_orders.items()
        if str(po.get("action", "")).upper() == "BUY" and get_ticker_sector(raw_tk) == target_sector
    )

    if is_live:
        client = get_broker_client()
        if not client.is_authenticated():
            print("[MAPLE LIVE BLOCKED] Broker gateway not authenticated. Please log in at https://localhost:5000")
            return None
        account_id = config.get("account_id") or client.get_primary_account_id()

        balances = client.get_balances(account_id)
        if not balances or (float(balances.get("total_equity", 0.0)) <= 0.0 and float(balances.get("cash", 0.0)) <= 0.0):
            print(f"[MAPLE LIVE BLOCKED] Broker returned empty/zero balances for {ticker}; aborting buy.")
            return None
        total_equity = float(balances.get("total_equity", 1000.0))
        cash_available = float(balances.get("cash", 0.0))
        if check_cash:
            try:
                reconcile_capital_flows(cash_available, live_equity=total_equity, config=config)
            except Exception:
                pass
        min_trade_thresh = get_effective_min_trade(config, total_equity)
        max_single_cap = get_effective_order_cap(config, total_equity)
        if not is_sweep and allocated_cash > max_single_cap:
            allocated_cash = max_single_cap

        ref_nav = _get_reference_nav(config)
        daily_loss_limit = get_effective_daily_loss_limit(config, ref_nav)
        drawdown = ref_nav - total_equity
        if drawdown >= daily_loss_limit:
            msg = f"Daily loss limit exceeded vs prev close (${ref_nav:.2f}): -${drawdown:.2f} >= ${daily_loss_limit:.2f}. All buying halted."
            print(f"[MAPLE CIRCUIT BREAKER] {msg}")
            try:
                from telegram_notifier import send_circuit_breaker_alert
                send_circuit_breaker_alert("Daily Drawdown Limit Hit", msg, cooldown_minutes=120)
            except Exception:
                pass
            return None

        positions_raw = client.get_positions(account_id)
        live_held = {
            normalize_ticker(p.get("symbol", ""))
            for p in positions_raw
            if float(p.get("openQuantity", 0.0)) > 0
        }
        aliases = set(ticker_aliases(ticker))
        existing_pos = next((p for p in positions_raw if normalize_ticker(p.get("symbol", "")) in aliases or p.get("symbol", "").upper() in aliases), None)
        existing_shares = float(existing_pos.get("openQuantity", 0.0)) if existing_pos else 0.0
        existing_acb = float(existing_pos.get("averageEntryPrice", current_price)) if existing_pos else 0.0
        if is_stage2_mode and not is_sweep and existing_shares <= 0:
            non_sweep_open = {t for t in live_held if t != SWEEP_ETF}
            if len(non_sweep_open) >= max_slots:
                print(f"[MAPLE SLOT CAP] Portfolio already holds {len(non_sweep_open)}/{max_slots} Stage-2 positions. Blocking {ticker}.")
                return None
        if not is_sweep and not _passes_scale_in_guards(active_tickers=live_held, fallback_px=existing_acb):
            return None
        existing_val = existing_shares * current_price
        max_pos_cad = total_equity * max_pos_pct
        if not is_sweep and existing_val + allocated_cash > max_pos_cad:
            allocated_cash = max(0.0, max_pos_cad - existing_val)
            if allocated_cash < min_trade_thresh:
                print(f"[MAPLE CONCENTRATION GUARD] {ticker} already at ${existing_val:.2f} ({existing_val/total_equity*100:.1f}% of NAV, cap {max_pos_pct*100:.0f}%). Order blocked.")
                return None

        held_sector_tickers = set()
        held_sector_cad = 0.0
        for p in positions_raw:
            p_sym = normalize_ticker(p.get("symbol", ""))
            p_qty = float(p.get("openQuantity", 0.0))
            if p_qty > 0 and get_ticker_sector(p_sym) == target_sector:
                held_sector_tickers.add(p_sym)
                p_px = current_price if p_sym == ticker else float(p.get("currentPrice") or p.get("averageEntryPrice") or 0.0)
                held_sector_cad += p_qty * p_px
        pending_norm = {normalize_ticker(k) for k in pending_orders.keys()}
        for t_sym, t_info in get_position_last_buy_info().items():
            if (
                get_ticker_sector(t_sym) == target_sector
                and t_sym not in held_sector_tickers
                and t_sym not in pending_norm
                and t_info.get("last_buy_dt")
                and (now_et_naive() - t_info["last_buy_dt"]).total_seconds() < 600
            ):
                held_sector_cad += float(t_info.get("shares", 0.0)) * float(t_info.get("last_buy_price", 0.0))

        sector_exposure = held_sector_cad + pending_sector_cad
        max_sector_cad = total_equity * max_sector_pct
        if not is_sweep and sector_exposure + allocated_cash > max_sector_cad:
            allocated_cash = max(0.0, max_sector_cad - sector_exposure)
            if allocated_cash < min_trade_thresh:
                print(
                    f"[MAPLE SECTOR CAP] {target_sector} exposure at ${sector_exposure:.2f} ({sector_exposure/total_equity*100:.1f}% of NAV, cap {max_sector_pct*100:.0f}%). Blocking {ticker}."
                )
                return None

        safe_cash = max(0.0, cash_available - 20.0)
        if check_cash:
            if allocated_cash > safe_cash:
                allocated_cash = safe_cash
            if allocated_cash < min_trade_thresh:
                print(f"[MAPLE] Insufficient free cash for {ticker}: ${allocated_cash:.2f} (Available: ${cash_available:.2f})")
                return None
        else:
            if allocated_cash < min_trade_thresh:
                print(f"[MAPLE] Insufficient or capped cash for {ticker}: ${allocated_cash:.2f}")
                return None
            max_single_share_pct = float(config.get("max_single_share_nav_pct", 0.30))
            est_shs = (
                int(allocated_cash // current_price)
                if is_sweep and current_price > 0
                else _size_whole_shares(
                    ticker, allocated_cash, current_price, existing_shares, existing_val,
                    total_equity, max_pos_pct, max_single_cap, sector_exposure, max_sector_pct,
                    allocated_cash, max_single_share_pct,
                )
            )
            if est_shs <= 0 or (existing_shares > 0 and est_shs * current_price < min_trade_thresh):
                return None

        return {
            "is_live": True,
            "is_sweep": is_sweep,
            "config": config,
            "client": client,
            "account_id": account_id,
            "total_equity": total_equity,
            "cash_available": cash_available,
            "safe_cash": safe_cash,
            "allocated_cash": allocated_cash,
            "min_trade_thresh": min_trade_thresh,
            "max_single_cap": max_single_cap,
            "max_pos_pct": max_pos_pct,
            "max_sector_pct": max_sector_pct,
            "existing_shares": existing_shares,
            "existing_acb": existing_acb,
            "existing_val": existing_val,
            "sector_exposure": sector_exposure,
        }

    state = get_ledger_state()
    cash = state["cash"]
    total_equity = state.get("total_equity", cash)
    min_trade_thresh = get_effective_min_trade(config, total_equity)
    max_single_cap = get_effective_order_cap(config, total_equity)
    if not is_sweep and allocated_cash > max_single_cap:
        allocated_cash = max_single_cap
    existing_pos = state["positions"].get(ticker, {})
    current_shares = existing_pos.get("shares", 0.0)
    if is_stage2_mode and not is_sweep and current_shares <= 0:
        sim_open = {normalize_ticker(t) for t, p in state["positions"].items() if p.get("shares", 0) > 0 and normalize_ticker(t) != SWEEP_ETF}
        if len(sim_open) >= max_slots:
            print(f"[MAPLE SLOT CAP] Portfolio already holds {len(sim_open)}/{max_slots} Stage-2 positions. Blocking {ticker}.")
            return None
    existing_acb = existing_pos.get("acb", current_price)
    existing_val = current_shares * current_price
    if not is_sweep and existing_val + allocated_cash > total_equity * max_pos_pct:
        allocated_cash = max(0.0, total_equity * max_pos_pct - existing_val)

    sim_sector_cad = pending_sector_cad + sum(
        p["shares"] * (current_price if normalize_ticker(t) == ticker else float(p.get("current_price") or p.get("acb") or 0.0))
        for t, p in state["positions"].items()
        if p.get("shares", 0.0) > 0 and get_ticker_sector(t) == target_sector
    )
    if not is_sweep and sim_sector_cad + allocated_cash > total_equity * max_sector_pct:
        allocated_cash = max(0.0, total_equity * max_sector_pct - sim_sector_cad)
        if allocated_cash < min_trade_thresh:
            print(
                f"[MAPLE SECTOR CAP] {target_sector} exposure at ${sim_sector_cad:.2f} ({sim_sector_cad/total_equity*100:.1f}% of NAV, cap {max_sector_pct*100:.0f}%). Blocking {ticker}."
            )
            return None

    if check_cash and allocated_cash > cash:
        allocated_cash = cash
    if allocated_cash < min_trade_thresh:
        print(f"[MAPLE] Insufficient or capped cash for {ticker}: ${allocated_cash:.2f}")
        return None
    if not check_cash:
        max_single_share_pct = float(config.get("max_single_share_nav_pct", 0.30))
        est_shs = (
            int(allocated_cash // current_price)
            if is_sweep and current_price > 0
            else _size_whole_shares(
                ticker, allocated_cash, current_price, current_shares, existing_val,
                total_equity, max_pos_pct, max_single_cap, sim_sector_cad, max_sector_pct,
                allocated_cash, max_single_share_pct,
            )
        )
        if est_shs <= 0 or (current_shares > 0 and est_shs * current_price < min_trade_thresh):
            return None

    return {
        "is_live": False,
        "is_sweep": is_sweep,
        "config": config,
        "state": state,
        "cash": cash,
        "total_equity": total_equity,
        "allocated_cash": allocated_cash,
        "min_trade_thresh": min_trade_thresh,
        "max_single_cap": max_single_cap,
        "max_pos_pct": max_pos_pct,
        "max_sector_pct": max_sector_pct,
        "current_shares": current_shares,
        "existing_acb": existing_acb,
        "existing_val": existing_val,
        "sim_sector_cad": sim_sector_cad,
    }


def preflight_buy(
    ticker: str,
    allocated_cash: float,
    current_price: float,
    notes: str = "",
    open_price: Optional[float] = None,
) -> float:
    """Returns approved allocation if all non-cash BUY guards pass (before sweep unwind), else 0.0."""
    try:
        ctx = _preflight_buy(ticker, allocated_cash, current_price, notes=notes, open_price=open_price, check_cash=False)
        return float(ctx["allocated_cash"]) if ctx else 0.0
    except Exception:
        return 0.0


def _recompute_targets_from_fill(
    fill_price: float,
    blended_acb: float,
    total_shares: float,
    stop_pct: float,
    existing_shares: float,
    target_price: Optional[float],
    stop_loss_price: Optional[float],
    stock_data: Optional[Dict[str, Any]] = None,
    signal_type: str = "REGULAR",
) -> tuple[Optional[float], float]:
    """Recomputes target and base stop from actual fill price and share count when stock_data is available."""
    if stock_data and not is_sweep_ticker(stock_data.get("_ticker", "")):
        from maple_strategy import MapleStrategy
        tgt, stp = MapleStrategy.calculate_targets(
            fill_price, stock_data, shares=total_shares, cost_basis=blended_acb, signal_type=signal_type
        )
        return tgt, stp
    if existing_shares > 0:
        base_stop = (
            float(stop_loss_price)
            if (isinstance(stop_loss_price, (int, float)) and 0 < stop_loss_price < fill_price)
            else round(blended_acb * (1.0 - stop_pct / 100.0), 2)
        )
    else:
        base_stop = float(stop_loss_price) if stop_loss_price else round(fill_price * (1.0 - stop_pct / 100.0), 2)
    return target_price, base_stop


def is_sweep_ticker(ticker: str) -> bool:
    return normalize_ticker(ticker) == SWEEP_ETF


def execute_buy(
    ticker: str,
    allocated_cash: float,
    current_price: float,
    target_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
    notes: str = "",
    open_price: Optional[float] = None,
    stock_data: Optional[Dict[str, Any]] = None,
    signal_type: str = "REGULAR",
) -> Optional[Dict[str, Any]]:
    """Executes a BUY order.
    In LIVE mode: validates Shariah whitelist, daily drawdown vs previous close, concentration & sector caps,
    scale-in cooldown/green-candle guard, submits a Limit Day Order, and polls for fill confirmation.
    In SIMULATED mode: updates local ledger.
    """
    ticker = normalize_ticker(ticker)
    is_sweep = ticker == SWEEP_ETF
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"

    try:
        ctx = _preflight_buy(ticker, allocated_cash, current_price, notes=notes, open_price=open_price, check_cash=True)
    except Exception as e:
        print(f"[MAPLE LIVE ORDER FAILED] Error executing buy for {ticker}: {e}")
        return None
    if not ctx:
        return None

    allocated_cash = ctx["allocated_cash"]
    min_trade_thresh = ctx["min_trade_thresh"]
    max_single_cap = ctx["max_single_cap"]
    max_pos_pct = ctx["max_pos_pct"]
    max_sector_pct = ctx["max_sector_pct"]

    if is_live:
        try:
            client = ctx["client"]
            account_id = ctx["account_id"]
            total_equity = ctx["total_equity"]
            cash_available = ctx["cash_available"]
            safe_cash = ctx["safe_cash"]
            existing_shares = ctx["existing_shares"]
            existing_acb = ctx["existing_acb"]
            existing_val = ctx["existing_val"]
            sector_exposure = ctx["sector_exposure"]

            # Resolve Symbol and Quote
            sym_obj = client.search_symbol(ticker)
            if not sym_obj:
                print(f"[MAPLE ERROR] Could not resolve broker symbolId for {ticker}")
                return None
            symbol_id = sym_obj["symbolId"]

            quote = client.get_quote(symbol_id)
            is_delayed = quote.get("isDelayed", False)
            ask = None if is_delayed else quote.get("askPrice")
            last = None if is_delayed else quote.get("lastTradePrice")

            # Determine Marketable Limit Price (live Ask with slippage ceiling; live current_price +0.2% if quote delayed)
            if ask and isinstance(ask, (int, float)) and ask > 0:
                if last and isinstance(last, (int, float)) and last > 0 and ask > last * 1.01:
                    limit_price = round(last * 1.002, 2)
                else:
                    limit_price = round(ask, 2)
            elif last and isinstance(last, (int, float)) and last > 0:
                limit_price = round(last, 2)
            elif is_delayed:
                limit_price = round(current_price * 1.002, 2)
            else:
                limit_price = round(current_price, 2)

            max_single_share_pct = float(config.get("max_single_share_nav_pct", 0.30))
            if is_sweep:
                shares = int(min(allocated_cash, safe_cash) // limit_price) if limit_price > 0 else 0
            else:
                shares = _size_whole_shares(
                    ticker,
                    allocated_cash,
                    limit_price,
                    existing_shares,
                    existing_val,
                    total_equity,
                    max_pos_pct,
                    max_single_cap,
                    sector_exposure,
                    max_sector_pct,
                    safe_cash,
                    max_single_share_pct,
                )
            if shares <= 0:
                print(f"[MAPLE] Price ${limit_price:.2f} exceeds allocated cash ${allocated_cash:.2f} for 1 share.")
                return None
            if existing_shares > 0 and shares * limit_price < min_trade_thresh:
                print(
                    f"[MAPLE MIN TRADE GUARD] Scale-in {shares} {ticker} @ ${limit_price:.2f} (${shares * limit_price:.2f}) below dynamic min trade ${min_trade_thresh:.2f}. Blocking fee churn."
                )
                return None

            print(f"[MAPLE LIVE ORDER] Placing Limit BUY: {shares} {ticker} @ ${limit_price:.2f} (Account #{account_id})...")
            order_res = client.place_limit_order(account_id, symbol_id, "Buy", shares, limit_price)
            order_id = order_res.get("orderId")
            if not order_id and "orders" in order_res and order_res["orders"]:
                order_id = order_res["orders"][0].get("id")
            if not order_id or str(order_id).strip().lower() == "none":
                print(f"[MAPLE LIVE ORDER REJECTED] Broker did not return a valid orderId for {ticker} ({order_res.get('raw_response', order_res)})")
                return None

            print(f"[MAPLE LIVE SUCCESS] Limit Buy Order #{order_id} submitted for {shares} {ticker} @ ${limit_price:.2f}")

            import time
            cum_fill = 0.0
            order_status = "Submitted"
            avg_fill_price = limit_price

            for _ in range(3):
                time.sleep(1.0)
                status_info = client.get_order_status(account_id, str(order_id)) if order_id else {}
                order_status = status_info.get("order_status", "Submitted")
                cum_fill = float(status_info.get("cum_fill", 0.0))
                for px_key in ["average_price", "price", "avg_price", "avgPrice"]:
                    if status_info.get(px_key) and float(status_info.get(px_key, 0)) > 0:
                        avg_fill_price = float(status_info.get(px_key))
                        break
                if order_status == "Filled" or cum_fill >= shares:
                    break

            stop_pct = config.get("stop_loss_pct", 5.0)
            default_comm = float(config.get("commission_per_order_cad", 1.0))
            if order_status == "Filled" or cum_fill >= shares:
                actual_px = avg_fill_price if avg_fill_price > 0 else limit_price
                new_shares = existing_shares + shares
                blended_acb = ((existing_shares * existing_acb) + (shares * actual_px)) / new_shares if existing_shares > 0 else actual_px
                eff_target, base_stop = _recompute_targets_from_fill(
                    actual_px, blended_acb, new_shares, stop_pct, existing_shares,
                    target_price, stop_loss_price, stock_data=stock_data if not is_sweep else None, signal_type=signal_type,
                )
                eff_stop = _resolve_buy_stop(config, ticker, base_stop, actual_px, existing_shares, blended_acb=blended_acb)

                bal_after = client.get_balances(account_id)
                est_rem_cash = round(max(0.0, cash_available - (shares * actual_px) - default_comm), 2)
                rem_cash = float(bal_after["cash"]) if (bal_after and "cash" in bal_after) else est_rem_cash

                order_note = f"LIVE LIMIT ORDER #{order_id} | {notes}".strip()
                log_trade(ticker, "BUY", shares, actual_px, new_shares, rem_cash, notes=order_note)

                if not is_sweep:
                    if "active_targets" not in config:
                        config["active_targets"] = {}
                    tgt_rec: Dict[str, Any] = {"target_price": eff_target, "stop_loss_price": eff_stop}
                    if str(signal_type).upper() == "STAGE2_RS":
                        tgt_rec["strategy_mode"] = "STAGE2_RS"
                        tgt_rec["peak_price"] = round(actual_px, 2)
                        tgt_rec["initial_stop_price"] = base_stop
                    elif stock_data and isinstance(stock_data.get("ATR_14"), (int, float)) and stock_data["ATR_14"] > 0:
                        tgt_rec["initial_stop_price"] = base_stop
                    config["active_targets"][ticker] = tgt_rec
                    save_config(config)

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action="BUY",
                        shares=shares,
                        price=actual_px,
                        order_id=order_id,
                        target_price=eff_target,
                        stop_loss_price=eff_stop,
                        notes=notes,
                    )
                except Exception:
                    pass

                return {
                    "ticker": ticker,
                    "action": "BUY",
                    "shares": shares,
                    "price": actual_px,
                    "order_id": order_id,
                    "cash_balance": rem_cash,
                }
            else:
                print(f"[MAPLE LIVE WORKING ORDER] Limit Buy #{order_id} active on IBKR book ({order_status}, fills: {cum_fill}/{shares} shs).")
                if "pending_orders" not in config:
                    config["pending_orders"] = {}
                est_blended = ((existing_shares * existing_acb) + (shares * limit_price)) / (existing_shares + shares) if existing_shares > 0 else limit_price
                pend_target, pending_base_stop = _recompute_targets_from_fill(
                    limit_price, est_blended, existing_shares + shares, stop_pct, existing_shares,
                    target_price, stop_loss_price, stock_data=stock_data if not is_sweep else None, signal_type=signal_type,
                )
                config["pending_orders"][ticker] = {
                    "order_id": str(order_id),
                    "action": "BUY",
                    "shares": shares,
                    "existing_shares": existing_shares,
                    "acb": existing_acb,
                    "limit_price": limit_price,
                    "cash_before": round(cash_available, 2),
                    "target_price": pend_target,
                    "stop_loss_price": _resolve_buy_stop(config, ticker, pending_base_stop, limit_price, existing_shares, blended_acb=est_blended),
                    "signal_type": signal_type,
                    "stock_data": {k: stock_data[k] for k in ("ATR_5", "ATR_14", "BB_Mid", "RSI_7", "days_to_ex_dividend") if k in stock_data} if stock_data else None,
                    "reason": notes,
                    "conid": symbol_id,
                    "timestamp": now_et_naive().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_config(config)

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action="ORDER_SUBMITTED",
                        shares=shares,
                        price=limit_price,
                        order_id=order_id,
                        notes=f"Resting limit buy on IBKR book ({notes})"
                    )
                except Exception:
                    pass

                return {
                    "ticker": ticker,
                    "action": "SUBMITTED",
                    "shares": shares,
                    "price": limit_price,
                    "order_id": order_id,
                    "status": order_status
                }

        except Exception as e:
            print(f"[MAPLE LIVE ORDER FAILED] Error executing buy for {ticker}: {e}")
            return None

    # SIMULATED MODE
    state = ctx["state"]
    cash = ctx["cash"]
    total_equity = ctx["total_equity"]
    current_shares = ctx["current_shares"]
    existing_acb = ctx["existing_acb"]
    existing_val = ctx["existing_val"]
    sim_sector_cad = ctx["sim_sector_cad"]

    max_single_share_pct = float(config.get("max_single_share_nav_pct", 0.30))
    if is_sweep:
        shares = int(allocated_cash // current_price) if current_price > 0 else 0
    else:
        shares = _size_whole_shares(
            ticker,
            allocated_cash,
            current_price,
            current_shares,
            existing_val,
            total_equity,
            max_pos_pct,
            max_single_cap,
            sim_sector_cad,
            max_sector_pct,
            cash,
            max_single_share_pct,
        )
    if shares <= 0:
        return None
    if current_shares > 0 and shares * current_price < min_trade_thresh:
        print(
            f"[MAPLE MIN TRADE GUARD] Scale-in {shares} {ticker} @ ${current_price:.2f} (${shares * current_price:.2f}) below dynamic min trade ${min_trade_thresh:.2f}. Blocking fee churn."
        )
        return None

    actual_cost = round(shares * current_price, 2)
    new_cash = round(cash - actual_cost, 2)
    new_shares = current_shares + shares
    blended_acb = ((current_shares * existing_acb) + actual_cost) / new_shares if current_shares > 0 else current_price
    stop_pct = config.get("stop_loss_pct", 5.0)
    eff_target, base_stop = _recompute_targets_from_fill(
        current_price, blended_acb, new_shares, stop_pct, current_shares,
        target_price, stop_loss_price, stock_data=stock_data if not is_sweep else None, signal_type=signal_type,
    )
    eff_stop = _resolve_buy_stop(config, ticker, base_stop, current_price, current_shares, blended_acb=blended_acb)

    log_trade(ticker, "BUY", shares, current_price, new_shares, new_cash, notes=notes)

    if not is_sweep:
        if "active_targets" not in config:
            config["active_targets"] = {}
        tgt_rec = {"target_price": eff_target, "stop_loss_price": eff_stop}
        if str(signal_type).upper() == "STAGE2_RS":
            tgt_rec["strategy_mode"] = "STAGE2_RS"
            tgt_rec["peak_price"] = round(current_price, 2)
            tgt_rec["initial_stop_price"] = base_stop
        elif stock_data and isinstance(stock_data.get("ATR_14"), (int, float)) and stock_data["ATR_14"] > 0:
            tgt_rec["initial_stop_price"] = base_stop
        config["active_targets"][ticker] = tgt_rec
        save_config(config)

    print(f"[MAPLE SIMULATED TRADE] BOUGHT {shares} {ticker} @ ${current_price:.2f} | Cash: ${new_cash:.2f}")
    return {
        "ticker": ticker,
        "action": "BUY",
        "shares": shares,
        "price": current_price,
        "cash_balance": new_cash,
    }


def execute_sell(
    ticker: str, current_price: float, reason: str = "", shares_to_sell: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Executes a 100% (or partial when shares_to_sell is specified) position liquidation.
    In LIVE mode: submits a Marketable Limit Sell Order to IBKR and polls for fill confirmation.
    In SIMULATED mode: updates local ledger.
    """
    ticker = normalize_ticker(ticker)
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"

    if is_live:
        try:
            client = get_broker_client()
            if not client.is_authenticated():
                print("[MAPLE LIVE BLOCKED] Broker gateway not authenticated. Please log in at https://localhost:5000")
                return None
            account_id = config.get("account_id") or client.get_primary_account_id()
            positions_raw = client.get_positions(account_id)

            aliases = set(ticker_aliases(ticker))
            pos = next((p for p in positions_raw if normalize_ticker(p.get("symbol", "")) in aliases or p.get("symbol", "").upper() in aliases), None)
            if not pos:
                print(f"[MAPLE LIVE SELL] No open position for {ticker} found in account #{account_id}.")
                return None

            open_shares = int(pos.get("openQuantity", 0))
            if open_shares <= 0:
                print(f"[MAPLE LIVE SELL] Open shares for {ticker} is 0.")
                return None
            shares = min(open_shares, int(shares_to_sell)) if (shares_to_sell and int(shares_to_sell) > 0) else open_shares
            rem_shares = max(0, open_shares - shares)

            symbol_id = pos.get("symbolId")
            if not symbol_id:
                sym_obj = client.search_symbol(ticker)
                if sym_obj:
                    symbol_id = sym_obj.get("symbolId")

            if not symbol_id:
                print(f"[MAPLE LIVE SELL] Could not resolve contract symbolId for {ticker}.")
                return None

            # Institutional Marketable Limit Order Pricing:
            # Uses live IBKR bid/last only when real-time; otherwise anchors directly to real-time current_price.
            bal_before = client.get_balances(account_id)
            cash_before = float(bal_before.get("cash", 0.0)) if bal_before else 0.0

            quote = client.get_quote(symbol_id)
            is_delayed = quote.get("isDelayed", False)
            bid = None if is_delayed else quote.get("bidPrice")
            last = None if is_delayed else quote.get("lastTradePrice")
            is_stop_loss = any(k in reason.upper() for k in ["STOP-LOSS", "STOP LOSS", "CIRCUIT"])

            price_cands = [p for p in (bid, last, current_price) if isinstance(p, (int, float)) and p > 0]
            anchor_price = min(price_cands) if price_cands else float(current_price)

            if is_stop_loss:
                limit_price = round(max(0.01, anchor_price * 0.99), 2)
            else:
                limit_price = round(max(0.01, anchor_price * 0.997), 2)

            acct_ccy = str(config.get("account_currency", "USD")).upper()
            print(f"[MAPLE LIVE ORDER] Placing Marketable Limit SELL: {shares} {ticker} @ Limit {acct_ccy} ${limit_price:.2f} (Account #{account_id}, Reason: {reason})...")
            order_res = client.place_limit_order(account_id, symbol_id, "Sell", shares, limit_price)
            order_id = order_res.get("orderId")
            if not order_id and "orders" in order_res and order_res["orders"]:
                order_id = order_res["orders"][0].get("id")
            if not order_id or str(order_id).strip().lower() == "none":
                print(f"[MAPLE LIVE ORDER REJECTED] Broker did not return a valid orderId for {ticker} ({order_res.get('raw_response', order_res)})")
                return None

            print(f"[MAPLE LIVE SUCCESS] Limit Sell Order #{order_id} submitted for {shares} {ticker} @ ${limit_price:.2f}")

            import time
            cum_fill = 0.0
            order_status = "Submitted"
            avg_fill_price = limit_price

            for _ in range(3):
                time.sleep(1.0)
                status_info = client.get_order_status(account_id, str(order_id)) if order_id else {}
                order_status = status_info.get("order_status", "Submitted")
                cum_fill = float(status_info.get("cum_fill", 0.0))

                for px_key in ["average_price", "price", "avg_price", "avgPrice"]:
                    if status_info.get(px_key) and float(status_info.get(px_key, 0)) > 0:
                        avg_fill_price = float(status_info.get(px_key))
                        break

                if order_status == "Filled" or cum_fill >= shares:
                    break

            if order_status == "Filled" or cum_fill >= shares:
                actual_px = avg_fill_price if avg_fill_price > 0 else limit_price
                acb = float(pos.get("averageEntryPrice", current_price))
                proceeds = round(shares * actual_px, 2)

                default_comm = float(config.get("commission_per_order_cad", 1.0))
                bal_after = client.get_balances(account_id)
                est_new_cash = round(max(0.0, cash_before + proceeds - default_comm), 2)
                new_cash = float(bal_after["cash"]) if (bal_after and "cash" in bal_after) else est_new_cash
                implied_comm = round(proceeds - (new_cash - cash_before), 2) if (cash_before > 0 and new_cash > cash_before) else -1.0
                exit_comm = implied_comm if 0.05 <= implied_comm <= 5.00 else default_comm
                cost_basis_total = shares * acb
                pnl = round(proceeds - cost_basis_total - exit_comm, 2)
                pnl_pct = round((pnl / cost_basis_total) * 100, 2) if cost_basis_total > 0 else 0.0

                order_note = f"LIVE LIMIT SELL #{order_id} FILLED | {reason} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)".strip()
                log_trade(ticker, "SELL", shares, actual_px, float(rem_shares), new_cash, notes=order_note)

                for alias in ticker_aliases(ticker):
                    if rem_shares <= 0 and "active_targets" in config and alias in config["active_targets"]:
                        del config["active_targets"][alias]
                    if "pending_orders" in config and alias in config["pending_orders"]:
                        del config["pending_orders"][alias]
                save_config(config)

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action="SELL",
                        shares=shares,
                        price=actual_px,
                        order_id=order_id,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        notes=reason,
                    )
                except Exception:
                    pass

                return {
                    "ticker": ticker,
                    "action": "SELL",
                    "shares": shares,
                    "price": actual_px,
                    "order_id": order_id,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "cash_balance": new_cash,
                }
            else:
                acb = float(pos.get("averageEntryPrice", current_price))
                print(f"[MAPLE LIVE WORKING ORDER] Limit Sell #{order_id} active on IBKR book ({order_status}, fills: {cum_fill}/{shares} shs). Position retained until filled.")
                if "pending_orders" not in config:
                    config["pending_orders"] = {}
                config["pending_orders"][ticker] = {
                    "order_id": str(order_id),
                    "action": "SELL",
                    "shares": shares,
                    "acb": acb,
                    "limit_price": limit_price,
                    "cash_before": round(cash_before, 2),
                    "reason": reason,
                    "conid": symbol_id,
                    "timestamp": now_et_naive().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_config(config)

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action="ORDER_SUBMITTED",
                        shares=shares,
                        price=limit_price,
                        order_id=order_id,
                        notes=f"Resting marketable limit sell on IBKR book ({reason})"
                    )
                except Exception:
                    pass

                return {
                    "ticker": ticker,
                    "action": "SUBMITTED",
                    "shares": shares,
                    "price": limit_price,
                    "order_id": order_id,
                    "status": order_status
                }

        except Exception as e:
            print(f"[MAPLE LIVE SELL FAILED] Error executing sell for {ticker}: {e}")
            return None

    # SIMULATED MODE
    state = get_ledger_state()
    pos = state["positions"].get(ticker, {})
    open_shares = pos.get("shares", 0.0)

    if open_shares <= 0:
        return None
    shares = min(open_shares, float(int(shares_to_sell))) if (shares_to_sell and int(shares_to_sell) > 0) else open_shares
    rem_shares = round(max(0.0, open_shares - shares), 4)

    proceeds = round(shares * current_price, 2)
    sim_comm = float(config.get("commission_per_order_cad", 0.0))
    new_cash = round(state["cash"] + proceeds - sim_comm, 2)
    acb = pos.get("acb", current_price)
    cost_basis_total = shares * acb
    pnl = round(proceeds - cost_basis_total - sim_comm, 2)
    pnl_pct = round((pnl / cost_basis_total) * 100, 2) if cost_basis_total > 0 else 0.0

    notes = f"{reason} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)"
    log_trade(ticker, "SELL", shares, current_price, rem_shares, new_cash, notes=notes.strip())

    if rem_shares <= 0:
        for alias in ticker_aliases(ticker):
            if "active_targets" in config and alias in config["active_targets"]:
                del config["active_targets"][alias]
        save_config(config)

    print(f"[MAPLE SIMULATED TRADE] SOLD {shares} {ticker} @ ${current_price:.2f} ({notes}) | Cash: ${new_cash:.2f}")
    return {
        "ticker": ticker,
        "action": "SELL",
        "shares": shares,
        "price": current_price,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "cash_balance": new_cash,
    }


def sync_working_orders() -> Dict[str, Any]:
    """Checks the status of any pending orders on the broker and updates the ledger accordingly."""
    config = load_config()
    if config.get("trading_mode", "").upper() != "LIVE":
        return {}

    pending = config.get("pending_orders", {})
    if not pending:
        return {}

    try:
        client = get_broker_client()
        if not client.is_authenticated():
            return {}
        account_id = config.get("account_id") or client.get_primary_account_id()

        updated_pending = dict(pending)
        changed = False

        for raw_ticker, p_info in list(pending.items()):
            ticker = normalize_ticker(raw_ticker)
            order_id = p_info.get("order_id")
            if not order_id or str(order_id).strip().lower() == "none":
                print(f"[MAPLE SYNC CLEANUP] Clearing invalid pending order_id ({order_id}) for {ticker}.")
                del updated_pending[raw_ticker]
                changed = True
                continue

            status_res = client.get_order_status(account_id, str(order_id))
            if status_res.get("statusCode") == 400:
                print(f"[MAPLE SYNC CLEANUP] Clearing invalid Order #{order_id} for {ticker}: {status_res.get('error', '400')}")
                del updated_pending[raw_ticker]
                changed = True
                continue
            status_str = status_res.get("order_status", "")
            cum_fill = float(status_res.get("cum_fill", 0.0))
            shares = float(p_info.get("shares", 0.0))
            limit_px = float(p_info.get("limit_price", 0.0))
            reason = p_info.get("reason", "")
            action = p_info.get("action", "SELL").upper()

            acct_ccy = str(config.get("account_currency", "USD")).upper()
            is_terminal = status_str in ("Cancelled", "Inactive", "ApiCancelled", "Rejected")
            is_full_fill = status_str == "Filled" or (shares > 0 and cum_fill >= shares)
            is_partial_terminal = is_terminal and cum_fill > 0

            if is_full_fill or is_partial_terminal:
                filled_shs = cum_fill if is_partial_terminal else (cum_fill if cum_fill > 0 else shares)
                actual_px = limit_px
                for px_key in ["average_price", "price", "avg_price", "avgPrice"]:
                    if status_res.get(px_key) and float(status_res.get(px_key, 0)) > 0:
                        actual_px = float(status_res.get(px_key))
                        break

                fill_tag = f"PARTIAL FILL ({filled_shs:g}/{shares:g} shs, {status_str})" if is_partial_terminal else "FILLED"
                print(f"[MAPLE LIVE FILL CONFIRMED] Order #{order_id} for {filled_shs:g} {ticker} {fill_tag} @ {acct_ccy} {actual_px:.2f}!")
                default_comm = float(config.get("commission_per_order_cad", 1.0))
                cash_before = float(p_info.get("cash_before", 0.0))
                bal_after = client.get_balances(account_id)
                if bal_after and "cash" in bal_after:
                    new_cash = float(bal_after["cash"])
                elif action == "SELL":
                    new_cash = round(max(0.0, cash_before + (filled_shs * actual_px) - default_comm), 2)
                else:
                    new_cash = round(max(0.0, cash_before - (filled_shs * actual_px) - default_comm), 2)

                acb = float(p_info.get("acb", 0.0))
                existing_shs = float(p_info.get("existing_shares", 0.0))
                try:
                    live_positions = client.get_positions(account_id)
                    aliases = set(ticker_aliases(ticker))
                    live_pos = next((p for p in live_positions if normalize_ticker(p.get("symbol", "")) in aliases or p.get("symbol", "").upper() in aliases), None)
                    new_shares = float(live_pos.get("openQuantity", 0.0)) if live_pos else (0.0 if action == "SELL" else (existing_shs + filled_shs))
                except Exception:
                    new_shares = max(0.0, float(shares - filled_shs)) if action == "SELL" else (existing_shs + filled_shs)
                if acb > 0 and action == "SELL":
                    proceeds = round(filled_shs * actual_px, 2)
                    implied_comm = (
                        round(proceeds - (new_cash - cash_before), 2)
                        if (cash_before > 0 and new_cash > cash_before and len(pending) == 1)
                        else -1.0
                    )
                    exit_comm = implied_comm if 0.05 <= implied_comm <= 5.00 else default_comm
                    cost_basis_total = filled_shs * acb
                    pnl = round(proceeds - cost_basis_total - exit_comm, 2)
                    pnl_pct = round((pnl / cost_basis_total) * 100, 2) if cost_basis_total > 0 else 0.0
                else:
                    pnl = None
                    pnl_pct = None
                pnl_str = f" | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)" if pnl is not None else ""

                order_note = f"LIVE LIMIT {action} #{order_id} {fill_tag} | {reason}{pnl_str}".strip()
                log_trade(ticker, action, filled_shs, actual_px, new_shares, new_cash, notes=order_note)

                if action == "SELL":
                    if new_shares <= 0.00001:
                        for alias in ticker_aliases(ticker):
                            if "active_targets" in config and alias in config["active_targets"]:
                                del config["active_targets"][alias]
                elif action == "BUY" and ticker != SWEEP_ETF:
                    if "active_targets" not in config:
                        config["active_targets"] = {}
                    stop_pct = config.get("stop_loss_pct", 5.0)
                    blended_acb = ((existing_shs * acb) + (filled_shs * actual_px)) / new_shares if (existing_shs > 0 and new_shares > 0) else actual_px
                    eff_target, sync_base = _recompute_targets_from_fill(
                        actual_px, blended_acb, new_shares, stop_pct, existing_shs,
                        p_info.get("target_price"), p_info.get("stop_loss_price"),
                        stock_data=p_info.get("stock_data"), signal_type=str(p_info.get("signal_type", "REGULAR")),
                    )
                    eff_stop = _resolve_buy_stop(config, ticker, float(sync_base), actual_px, existing_shs, blended_acb=blended_acb)
                    tgt_rec = {"target_price": eff_target, "stop_loss_price": eff_stop}
                    p_sd = p_info.get("stock_data")
                    if str(p_info.get("signal_type", "")).upper() == "STAGE2_RS":
                        tgt_rec["strategy_mode"] = "STAGE2_RS"
                        tgt_rec["peak_price"] = round(actual_px, 2)
                        tgt_rec["initial_stop_price"] = float(sync_base)
                    elif isinstance(p_sd, dict) and isinstance(p_sd.get("ATR_14"), (int, float)) and p_sd["ATR_14"] > 0:
                        tgt_rec["initial_stop_price"] = float(sync_base)
                    config["active_targets"][ticker] = tgt_rec

                del updated_pending[raw_ticker]
                changed = True

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action=action,
                        shares=filled_shs,
                        price=actual_px,
                        order_id=order_id,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        notes=f"{fill_tag} on IBKR book: {reason}"
                    )
                except Exception:
                    pass

            elif is_terminal and cum_fill <= 0:
                print(f"[MAPLE LIVE ORDER EXPIRED] Order #{order_id} for {ticker} was {status_str} unfilled on broker. Position retained.")
                del updated_pending[raw_ticker]
                changed = True

        if changed:
            config["pending_orders"] = updated_pending
            save_config(config)

        return updated_pending
    except Exception as e:
        print(f"[MAPLE SYNC WARNING] Error syncing working orders: {e}")
        return {}


def _count_trading_days(start_dt: datetime.datetime, end_dt: datetime.datetime) -> int:
    """Counts NYSE trading sessions (excluding weekends and NYSE holidays) elapsed between start_dt and end_dt."""
    return max(0, count_nyse_trading_days(start_dt, end_dt))


def get_position_holding_days(active_tickers: Optional[set] = None) -> Dict[str, int]:
    """Reconstructs the number of trading days (weekdays) each currently open position has been held."""
    if not os.path.exists(TRADES_FILE):
        return {}

    allowed = {normalize_ticker(t) for t in active_tickers} if active_tickers is not None else None
    running_shares: Dict[str, float] = {}
    first_buy_dates: Dict[str, datetime.datetime] = {}

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ticker = normalize_ticker(row.get("Ticker", ""))
                    action = row.get("Action", "").strip().upper()
                    qty = float(row.get("Quantity", 0.0))
                    date_str = row.get("Date", "").strip()
                except (ValueError, KeyError):
                    continue

                if not ticker or ticker == "CASH":
                    continue

                try:
                    dt = datetime.datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
                    except ValueError:
                        continue

                cur_shs = running_shares.get(ticker, 0.0)
                if action in ("BUY", "INIT"):
                    if cur_shs <= 0.00001:
                        first_buy_dates[ticker] = dt
                    running_shares[ticker] = cur_shs + qty
                elif action == "SELL":
                    new_shs = cur_shs - qty
                    if new_shs <= 0.00001:
                        running_shares[ticker] = 0.0
                        first_buy_dates.pop(ticker, None)
                    else:
                        running_shares[ticker] = new_shs
    except Exception:
        return {}

    now = now_et_naive()
    return {
        t: _count_trading_days(dt, now)
        for t, dt in first_buy_dates.items()
        if running_shares.get(t, 0.0) > 0.00001 and (allowed is None or t in allowed)
    }


def get_position_buy_counts(active_tickers: Optional[set] = None) -> Dict[str, int]:
    """Calculates how many times an asset has been bought during its current active position cycle.
    Prevents over-averaging into any single asset (enforcing max 2 entries per position).
    """
    if not os.path.exists(TRADES_FILE):
        return {}

    allowed = {normalize_ticker(t) for t in active_tickers} if active_tickers is not None else None
    running_shares = {}
    buy_counts = {}

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) < 4:
                    continue
                date_str, raw_ticker, action, qty_str = row[0], row[1], row[2], row[3]
                ticker = normalize_ticker(raw_ticker)
                action = action.upper().strip()
                try:
                    qty = float(qty_str)
                except ValueError:
                    continue

                if not ticker or ticker == "CASH":
                    continue

                cur_shs = running_shares.get(ticker, 0.0)
                if action in ("BUY", "INIT"):
                    if cur_shs <= 0.00001:
                        buy_counts[ticker] = 1
                    else:
                        buy_counts[ticker] = buy_counts.get(ticker, 0) + 1
                    running_shares[ticker] = cur_shs + qty
                elif action == "SELL":
                    new_shs = cur_shs - qty
                    if new_shs <= 0.00001:
                        running_shares[ticker] = 0.0
                        buy_counts.pop(ticker, None)
                    else:
                        running_shares[ticker] = new_shs
    except Exception:
        return {}

    return {
        t: count
        for t, count in buy_counts.items()
        if running_shares.get(t, 0.0) > 0.00001 and (allowed is None or t in allowed)
    }


def get_position_last_buy_info(active_tickers: Optional[set] = None) -> Dict[str, Dict[str, Any]]:
    """Returns timestamp, price, and running share count of the most recent BUY for each open position."""
    if not os.path.exists(TRADES_FILE):
        return {}

    allowed = {normalize_ticker(t) for t in active_tickers} if active_tickers is not None else None
    running_shares: Dict[str, float] = {}
    last_buy: Dict[str, Dict[str, Any]] = {}

    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ticker = normalize_ticker(row.get("Ticker", ""))
                    action = row.get("Action", "").strip().upper()
                    qty = float(row.get("Quantity", 0.0))
                    px = float(row.get("Price", 0.0))
                    date_str = row.get("Date", "").strip()
                except (ValueError, KeyError):
                    continue

                if not ticker or ticker == "CASH":
                    continue

                dt = None
                for fmt, sl in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
                    try:
                        dt = datetime.datetime.strptime(date_str[:sl], fmt)
                        break
                    except ValueError:
                        continue

                cur_shs = running_shares.get(ticker, 0.0)
                if action in ("BUY", "INIT"):
                    prev_fill = last_buy.get(ticker, {}).get("fill_acb", px)
                    new_shs = cur_shs + qty
                    fill_acb = ((cur_shs * prev_fill) + (qty * px)) / new_shs if new_shs > 0 else px
                    running_shares[ticker] = new_shs
                    last_buy[ticker] = {"last_buy_dt": dt, "last_buy_price": px, "fill_acb": round(fill_acb, 4), "shares": new_shs}
                elif action == "SELL":
                    new_shs = cur_shs - qty
                    if new_shs <= 0.00001:
                        running_shares[ticker] = 0.0
                        last_buy.pop(ticker, None)
                    else:
                        running_shares[ticker] = new_shs
                        if ticker in last_buy:
                            last_buy[ticker]["shares"] = new_shs
    except Exception:
        return {}

    return {
        t: info
        for t, info in last_buy.items()
        if running_shares.get(t, 0.0) > 0.00001 and (allowed is None or t in allowed)
    }


def get_last_loss_exit_info() -> Dict[str, Dict[str, Any]]:
    """Returns the most recent stop-loss or stagnation SELL timestamp and price for each ticker."""
    if not os.path.exists(TRADES_FILE):
        return {}
    last_exit: Dict[str, Dict[str, Any]] = {}
    try:
        with open(TRADES_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ticker = normalize_ticker(row.get("Ticker", ""))
                action = (row.get("Action") or "").strip().upper()
                notes = (row.get("Notes") or "").upper()
                if not ticker or ticker == "CASH" or action != "SELL":
                    continue
                if not any(k in notes for k in ("STOP-LOSS", "STOP LOSS", "CHOP-BUFFERED STOP", "STAGNATION")):
                    continue
                date_str = (row.get("Date") or "").strip()
                dt = None
                for fmt, sl in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
                    try:
                        dt = datetime.datetime.strptime(date_str[:sl], fmt)
                        break
                    except ValueError:
                        continue
                if dt:
                    last_exit[ticker] = {
                        "last_exit_dt": dt,
                        "last_exit_price": float(row.get("Price") or 0.0),
                        "notes": row.get("Notes", ""),
                    }
    except Exception:
        return {}
    return last_exit


def check_target_stops(
    market_prices: Dict[str, float],
    market_data: Optional[Dict[str, Dict[str, Any]]] = None,
    allow_stagnation_exit: bool = False,
    is_chop_window: bool = False,
    is_eod_window: bool = False,
    top_keep_tickers: Optional[set] = None,
):
    """Automatically executes exits across Stage-2 Multi-Week Swing (Variant D) and legacy swing positions."""
    sync_working_orders()
    state = get_ledger_state()
    config = load_config()
    if config.get("trading_mode", "").upper() == "LIVE" and state.get("live_fallback"):
        print("[MAPLE LIVE HALT] Skipping check_target_stops: broker gateway unreachable/unauthenticated.")
        return
    acct_ccy = str(config.get("account_currency", "USD")).upper()
    active_targets = config.get("active_targets", {})
    init_portfolio = config.get("initial_portfolio", {})
    held_set = {normalize_ticker(t) for t, p in state["positions"].items() if p.get("shares", 0) > 0}
    holding_days = get_position_holding_days(active_tickers=held_set)

    from maple_strategy import MapleStrategy
    MapleStrategy._sync_from_config()

    for raw_ticker, pos in state["positions"].items():
        ticker = normalize_ticker(raw_ticker)
        shares = pos.get("shares", 0.0)
        if shares <= 0 or ticker == SWEEP_ETF:
            continue

        price = None
        for alias in ticker_aliases(ticker):
            if alias in market_prices and market_prices[alias]:
                price = market_prices[alias]
                break
        if price is None or price <= 0:
            continue

        acb = pos.get("acb", price)
        target = None
        stop = None

        target_info = None
        matched_alias = ticker
        for alias in ticker_aliases(ticker):
            if alias in active_targets:
                target_info = active_targets[alias]
                matched_alias = alias
                break
            elif alias in init_portfolio:
                target_info = init_portfolio[alias]
                matched_alias = alias
                break

        if target_info:
            target = target_info.get("target_price")
            stop = target_info.get("stop_loss_price")

        # Fallback default 5% stop
        if stop is None and acb > 0:
            stop = round(acb * 0.95, 2)

        # Check if already has an active working order
        pending_orders = config.get("pending_orders", {})
        pend_match = next((pending_orders[a] for a in ticker_aliases(ticker) if a in pending_orders), None)
        if pend_match:
            pend_id = pend_match.get("order_id")
            print(f"[MAPLE] Order #{pend_id} already active for {ticker}. Skipping duplicate order submission.")
            continue

        # 0. Breakeven Stop Ratchet: Once unrealized gain >= +2.0% (or any >= +0.3% green cushion within <= 3 trading days of earnings)
        sd_pos = None
        if market_data:
            for alias in ticker_aliases(ticker):
                if alias in market_data and market_data[alias]:
                    sd_pos = market_data[alias]
                    break
        earn_td = sd_pos.get("trading_days_to_earnings") if sd_pos else None
        if earn_td is None and sd_pos:
            earn_td = sd_pos.get("days_to_earnings")
        near_earnings = isinstance(earn_td, (int, float)) and 0 <= earn_td <= 3
        is_stage2_pos = bool(target_info and str(target_info.get("strategy_mode", "")).upper() == "STAGE2_RS")

        if is_stage2_pos:
            comm_per_order = float(config.get("commission_per_order_cad", MapleStrategy.COMMISSION_PER_ORDER_CAD))
            comm_mult = 1.0 if (state.get("mode") == "LIVE" and state.get("live_verified")) else 2.0
            comm_breakeven = round(acb + (comm_mult * comm_per_order) / max(1.0, float(shares)), 2)
            prev_peak = float(target_info.get("peak_price") or acb)
            peak_px = round(max(prev_peak, float(price)), 2)
            atr_ref = (
                float(sd_pos["ATR_14"])
                if (sd_pos and isinstance(sd_pos.get("ATR_14"), (int, float)) and sd_pos["ATR_14"] > 0)
                else (acb * 0.025)
            )
            cand_stop = float(stop) if stop is not None else round(acb - MapleStrategy.STAGE2_HARD_STOP_ATR_MULT * atr_ref, 2)
            tag = ""
            if peak_px >= acb * 1.08 or (near_earnings and price >= round(acb * 1.003, 2)):
                be_px = comm_breakeven if price >= round(comm_breakeven * 1.004, 2) else round(acb, 2)
                if be_px < price and be_px > cand_stop:
                    cand_stop = be_px
                    tag = "STAGE-2 BREAKEVEN FLOOR"
            chand_stop = round(peak_px - MapleStrategy.STAGE2_TRAIL_STOP_ATR_MULT * atr_ref, 2)
            if chand_stop < price and chand_stop > cand_stop:
                cand_stop = chand_stop
                tag = "STAGE-2 CATASTROPHIC ATR TRAIL"

            if (stop is None or cand_stop > stop) or peak_px > prev_peak:
                old_stop = stop
                if cand_stop < price and (stop is None or cand_stop > stop):
                    stop = cand_stop
                config = load_config()
                rec = config.setdefault("active_targets", {}).setdefault(matched_alias, {})
                rec["strategy_mode"] = "STAGE2_RS"
                rec["target_price"] = target
                rec["stop_loss_price"] = stop
                rec["peak_price"] = peak_px
                save_config(config)
                active_targets = config.get("active_targets", {})
                if tag and stop != old_stop:
                    gain_pct = ((price - acb) / acb) * 100.0 if acb > 0 else 0.0
                    print(f"[MAPLE {tag}] Ratcheted hard stop for {ticker} from {acct_ccy} {old_stop} to {acct_ccy} {stop:.2f} (Peak {acct_ccy} {peak_px:.2f}, +{gain_pct:.2f}%)")

            # Layer 1: Intraday Catastrophic Hard Stop (with Opening Chop Buffer 9:30-10:00 AM ET)
            if stop is not None:
                chop_buf_pct = float(config.get("chop_stop_buffer_pct", 2.0)) if is_chop_window else 0.0
                eff_stop = round(stop * (1.0 - chop_buf_pct / 100.0), 2) if chop_buf_pct > 0 else stop
                if price <= eff_stop:
                    stop_label = f"Chop-Buffered Hard Stop {acct_ccy} {eff_stop:.2f} [Base {acct_ccy} {stop:.2f}]" if chop_buf_pct > 0 else f"Hard Stop {acct_ccy} {stop:.2f}"
                    execute_sell(ticker, price, reason=f"AUTO STOP-LOSS HIT: {acct_ccy} {price:.2f} ({stop_label})")
                    config = load_config()
                    active_targets = config.get("active_targets", {})
                    continue

            # Layer 2: Close-Confirmed Hybrid SMA_50 / EMA_21 Trend Exit (evaluated near close after >= 5 trading days)
            days_held = holding_days.get(ticker, 0)
            if is_eod_window and not is_chop_window and sd_pos and days_held >= MapleStrategy.STAGE2_MIN_HOLD_DAYS:
                sma_50 = sd_pos.get("SMA_50")
                ema_21 = sd_pos.get("EMA_21")
                gain_pct = ((price - acb) / acb) * 100.0 if acb > 0 else 0.0
                outside_keep = (top_keep_tickers is not None) and (ticker not in top_keep_tickers)
                if isinstance(sma_50, (int, float)) and sma_50 > 0 and price < sma_50:
                    execute_sell(
                        ticker,
                        price,
                        reason=f"AUTO STAGE-2 SMA_50 EXIT: Close {acct_ccy} {price:.2f} < SMA_50 ({acct_ccy} {sma_50:.2f}) after {days_held}d ({gain_pct:+.2f}%)",
                    )
                    config = load_config()
                    active_targets = config.get("active_targets", {})
                    continue
                if isinstance(ema_21, (int, float)) and ema_21 > 0 and price < ema_21 and (gain_pct >= MapleStrategy.STAGE2_PROFIT_HARVEST_PCT or outside_keep):
                    why = f"+{gain_pct:.1f}% profit harvest" if gain_pct >= MapleStrategy.STAGE2_PROFIT_HARVEST_PCT else "RS faded outside Top-20"
                    execute_sell(
                        ticker,
                        price,
                        reason=f"AUTO STAGE-2 EMA_21 EXIT: Close {acct_ccy} {price:.2f} < EMA_21 ({acct_ccy} {ema_21:.2f}) [{why}]",
                    )
                    config = load_config()
                    active_targets = config.get("active_targets", {})
                    continue
            continue

        if acb > 0 and price > acb:
            gain_pct = ((price - acb) / acb) * 100.0
            target_progress = ((price - acb) / (target - acb)) if (target and target > acb) else 0.0
            init_stop = target_info.get("initial_stop_price") if target_info else None
            use_r_ratchet = isinstance(init_stop, (int, float)) and 0 < init_stop < acb
            comm_per_order = float(config.get("commission_per_order_cad", MapleStrategy.COMMISSION_PER_ORDER_CAD))
            # IBKR LIVE avgCost (acb) already includes entry commission; SIMULATED acb is raw fill price
            comm_mult = 1.0 if (state.get("mode") == "LIVE" and state.get("live_verified")) else 2.0
            comm_breakeven = round(acb + (comm_mult * comm_per_order) / max(1.0, float(shares)), 2)
            raw_breakeven = round(acb, 2)
            candidate_stop = None
            tag = ""

            if use_r_ratchet:
                r_unit = max(0.01, float(acb - init_stop))
                r_gain = (price - acb) / r_unit
                atr_trail = (
                    float(sd_pos["ATR_14"])
                    if (sd_pos and isinstance(sd_pos.get("ATR_14"), (int, float)) and sd_pos["ATR_14"] > 0)
                    else (r_unit / MapleStrategy.ATR_STOP_MULTIPLIER)
                )
                if r_gain >= 0.8 or (near_earnings and price >= round(acb * 1.003, 2)):
                    candidate_stop = round(acb - 0.5 * r_unit, 2)
                    tag = "HALF-RISK RATCHET (-0.5R)"
                if r_gain >= 1.0 or (near_earnings and price >= round(acb * 1.003, 2)):
                    be_stop = comm_breakeven if price >= round(comm_breakeven * 1.004, 2) else raw_breakeven
                    if candidate_stop is None or be_stop > candidate_stop:
                        candidate_stop = be_stop
                    tag = "EARNINGS BREAKEVEN RATCHET" if (near_earnings and r_gain < 1.0) else "BREAKEVEN RATCHET (+1.0R)"
                if r_gain >= 1.5:
                    lock_stop = round(comm_breakeven + 0.75 * r_unit, 2)
                    if price >= round(lock_stop * 1.004, 2) and (candidate_stop is None or lock_stop > candidate_stop):
                        candidate_stop = lock_stop
                        tag = "PROFIT-LOCK RATCHET (+0.75R NET)"
                if r_gain >= 2.0:
                    trail_stop = round(price - 1.5 * atr_trail, 2)
                    if candidate_stop is None or trail_stop > candidate_stop:
                        candidate_stop = trail_stop
                        tag = "ATR TRAILING STOP RATCHET (+2.0R)"
            elif (
                gain_pct >= MapleStrategy.HALF_RISK_TRIGGER_PCT
                or gain_pct >= MapleStrategy.BREAKEVEN_TRIGGER_PCT
                or target_progress >= 0.75
                or (near_earnings and price >= round(acb * 1.003, 2))
            ):
                # Legacy %-tier ratchets for pre-existing positions without initial_stop_price
                candidate_stop = round(acb * 0.975, 2)
                tag = "HALF-RISK RATCHET (-2.5%)"
                if gain_pct >= MapleStrategy.BREAKEVEN_TRIGGER_PCT or target_progress >= 0.75 or (near_earnings and price >= round(acb * 1.003, 2)):
                    be_stop = comm_breakeven if price >= round(comm_breakeven * 1.004, 2) else raw_breakeven
                    if be_stop > candidate_stop:
                        candidate_stop = be_stop
                    tag = "EARNINGS BREAKEVEN RATCHET" if (near_earnings and gain_pct < MapleStrategy.BREAKEVEN_TRIGGER_PCT) else "BREAKEVEN RATCHET"
                if gain_pct >= 3.0 or target_progress >= 0.75:
                    lock_stop = round(comm_breakeven * 1.015, 2)
                    if price >= round(lock_stop * 1.004, 2) and lock_stop > candidate_stop:
                        candidate_stop = lock_stop
                        tag = "PROFIT-LOCK RATCHET (+1.5% NET)"
                if gain_pct >= 4.0:
                    trail_stop = round(price * 0.9875, 2)
                    if trail_stop > candidate_stop:
                        candidate_stop = trail_stop
                        tag = "TRAILING STOP RATCHET (-1.25%)"

            if candidate_stop is not None and candidate_stop < price and (stop is None or candidate_stop > stop):
                old_stop = stop
                stop = candidate_stop
                config = load_config()
                active_targets = config.get("active_targets", {})
                config.setdefault("active_targets", {}).setdefault(matched_alias, {})["target_price"] = target
                config["active_targets"][matched_alias]["stop_loss_price"] = stop
                save_config(config)
                print(
                    f"[MAPLE {tag}] Ratcheted stop-loss for {ticker} from {acct_ccy} {old_stop} to {acct_ccy} {stop:.2f} (Price {acct_ccy} {price:.2f}, +{gain_pct:.2f}%)"
                )

        # 1. Target Hit
        if target is not None and price >= target:
            execute_sell(
                ticker,
                price,
                reason=f"AUTO TARGET HIT: {acct_ccy} {price:.2f} (Target {acct_ccy} {target:.2f})",
            )
            config = load_config()
            active_targets = config.get("active_targets", {})
            continue

        # 2. Stop-Loss Hit (buffered during 9:30-10:00 AM opening chop to prevent opening-wick shakeouts)
        if stop is not None:
            chop_buf_pct = float(config.get("chop_stop_buffer_pct", 2.0)) if is_chop_window else 0.0
            eff_stop = round(stop * (1.0 - chop_buf_pct / 100.0), 2) if chop_buf_pct > 0 else stop
            if price <= eff_stop:
                stop_label = f"Chop-Buffered Stop {acct_ccy} {eff_stop:.2f} [Base {acct_ccy} {stop:.2f}]" if chop_buf_pct > 0 else f"Stop {acct_ccy} {stop:.2f}"
                execute_sell(
                    ticker,
                    price,
                    reason=f"AUTO STOP-LOSS HIT: {acct_ccy} {price:.2f} ({stop_label})",
                )
                config = load_config()
                active_targets = config.get("active_targets", {})
                continue
            elif is_chop_window and price <= stop:
                print(
                    f"[MAPLE CHOP BUFFER] {ticker} dipped to {acct_ccy} {price:.2f} (<= base stop {acct_ccy} {stop:.2f}), "
                    f"holding above opening-chop floor {acct_ccy} {eff_stop:.2f} (-{chop_buf_pct:.1f}% buffer until 10:00 AM)."
                )

        # 3. Autonomous Stagnation Exit (Held >= STAGNATION_DAYS, negative P&L, Bearish EMA5 < EMA9 OR Price < both EMAs)
        if allow_stagnation_exit and market_data and acb > 0 and price < acb:
            days_held = holding_days.get(ticker, 0)
            if days_held >= MapleStrategy.STAGNATION_DAYS:
                sd = None
                for alias in ticker_aliases(ticker):
                    if alias in market_data and market_data[alias]:
                        sd = market_data[alias]
                        break
                if sd:
                    ema_cross = str(sd.get("EMA_Crossover", ""))
                    ema_5 = sd.get("EMA_5")
                    ema_9 = sd.get("EMA_9")
                    is_bearish = ("BEARISH" in ema_cross.upper()) or (
                        isinstance(ema_5, (int, float)) and isinstance(ema_9, (int, float)) and ema_5 < ema_9
                    )
                    below_both_emas = (
                        isinstance(ema_5, (int, float))
                        and isinstance(ema_9, (int, float))
                        and price < min(ema_5, ema_9)
                    )
                    if is_bearish or below_both_emas:
                        open_px = sd.get("Open")
                        prev_close = sd.get("Prev_Close")
                        intraday_rally = (
                            isinstance(open_px, (int, float))
                            and open_px > 0
                            and price > open_px
                            and isinstance(prev_close, (int, float))
                            and prev_close > 0
                            and price >= prev_close * 1.01
                        )
                        if intraday_rally:
                            day_chg_pct = ((price - prev_close) / prev_close) * 100.0
                            print(
                                f"[MAPLE STAGNATION DEFERRED] {ticker} held {days_held}d but rallying intraday (Price ${price:.2f} > Open ${open_px:.2f}, {day_chg_pct:+.2f}% vs Prev Close ${prev_close:.2f})."
                            )
                            continue
                        pnl_pct = ((price - acb) / acb) * 100.0
                        tech_reason = (
                            "Bearish EMA5 < EMA9"
                            if is_bearish
                            else f"Price (${price:.2f}) broke below EMA5 (${ema_5:.2f}) & EMA9 (${ema_9:.2f})"
                        )
                        execute_sell(
                            ticker,
                            price,
                            reason=f"AUTO STAGNATION EXIT: Held {days_held}d (>= {MapleStrategy.STAGNATION_DAYS}d) at {pnl_pct:+.2f}% with {tech_reason}",
                        )
                        config = load_config()
                        active_targets = config.get("active_targets", {})
                        continue


if __name__ == "__main__":
    st = get_ledger_state()
    print("MAPLE Current State:")
    print(f"Mode: {st.get('mode')}")
    print(f"Cash: ${st['cash']:.2f}")
    if "total_equity" in st:
        print(f"Total Equity: ${st['total_equity']:.2f}")
    if not st["positions"]:
        print("Positions: None (100% Cash)")
    else:
        for tk, p in st["positions"].items():
            if p["shares"] > 0:
                print(f"- {tk}: {p['shares']} shares @ ${p['acb']:.2f} ACB")
