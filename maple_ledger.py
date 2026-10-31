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
def get_broker_client():
    """Factory to instantiate the active broker client (IBKR or Questrade)."""
    cfg = load_config()
    broker = cfg.get("broker", "IBKR").upper()
    if broker == "IBKR":
        from ibkr_client import IBKRClient
        return IBKRClient()
    else:
        from questrade_client import QuestradeClient
        return QuestradeClient()

MAPLE_DIR = os.path.dirname(os.path.abspath(__file__))
TRADES_FILE = os.path.join(MAPLE_DIR, "maple_trades.csv")
CONFIG_FILE = os.path.join(MAPLE_DIR, "maple_config.json")
ADVICE_FILE = os.path.join(MAPLE_DIR, "maple_advice_history.txt")
NAV_FILE = os.path.join(MAPLE_DIR, "maple_daily_nav.json")

# Strict Gatekeeper Universe: No order may be submitted outside this basket (32 vetted tickers)
SHARIAH_COMPLIANT_BASKET = {
    "CNQ.TO", "ABX.TO", "CP.TO", "GIB-A.TO", "WCN.TO", "CLS.TO",
    "SHOP.TO", "AEM.TO", "CNR.TO", "CCO.TO", "CSU.TO", "TECK-B.TO",
    "SAP.TO", "TIH.TO", "CCL-B.TO", "ATRL.TO", "ATZ.TO", "STN.TO", "FNV.TO",
    "SU.TO", "IMO.TO", "CVE.TO", "TFII.TO", "RUS.TO", "DSG.TO",
    "KXS.TO", "ENGH.TO", "WPM.TO", "PAAS.TO", "AGI.TO", "WFG.TO", "RCH.TO"
}

SECTOR_MAP = {
    # Precious Metals (6)
    "ABX.TO": "Precious Metals", "AEM.TO": "Precious Metals", "FNV.TO": "Precious Metals",
    "WPM.TO": "Precious Metals", "PAAS.TO": "Precious Metals", "AGI.TO": "Precious Metals",
    # Energy & Uranium (5)
    "CNQ.TO": "Energy & Uranium", "SU.TO": "Energy & Uranium", "IMO.TO": "Energy & Uranium",
    "CVE.TO": "Energy & Uranium", "CCO.TO": "Energy & Uranium",
    # Base Metals & Materials (3)
    "TECK-B.TO": "Base Metals & Materials", "RUS.TO": "Base Metals & Materials", "WFG.TO": "Base Metals & Materials",
    # Technology (7)
    "SHOP.TO": "Technology", "CSU.TO": "Technology", "GIB-A.TO": "Technology",
    "CLS.TO": "Technology", "DSG.TO": "Technology", "KXS.TO": "Technology", "ENGH.TO": "Technology",
    # Industrials & Rail (7)
    "CP.TO": "Industrials & Rail", "CNR.TO": "Industrials & Rail", "WCN.TO": "Industrials & Rail",
    "TIH.TO": "Industrials & Rail", "ATRL.TO": "Industrials & Rail", "STN.TO": "Industrials & Rail", "TFII.TO": "Industrials & Rail",
    # Consumer & Packaging (4)
    "SAP.TO": "Consumer & Packaging", "ATZ.TO": "Consumer & Packaging",
    "CCL-B.TO": "Consumer & Packaging", "RCH.TO": "Consumer & Packaging",
}


def get_ticker_sector(ticker: str) -> str:
    """Returns canonical sector classification for any Shariah-compliant TSX ticker."""
    return SECTOR_MAP.get(normalize_ticker(ticker), "Other")


def normalize_ticker(ticker: str) -> str:
    """Normalizes TSX dual-class tickers (e.g. TECK.B.TO or TECK.B -> TECK-B.TO)."""
    t = ticker.strip().upper()
    if not t or t == "CASH":
        return t
    base = t[:-3] if t.endswith(".TO") else t
    return f"{base.replace('.', '-')}.TO"


def ticker_aliases(ticker: str) -> list[str]:
    """Returns canonical hyphen and dot aliases for a TSX ticker."""
    norm = normalize_ticker(ticker)
    base_hyphen = norm[:-3] if norm.endswith(".TO") else norm
    base_dot = base_hyphen.replace("-", ".")
    return list(dict.fromkeys([norm, f"{base_dot}.TO", base_hyphen, base_dot, ticker.strip().upper()]))



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
    t_str = (today_str or datetime.datetime.now().strftime("%Y-%m-%d"))[:10]
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
    t_str = (today_str or datetime.datetime.now().strftime("%Y-%m-%d"))[:10]
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
                            last_csv_cash_today = float(cb)
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
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
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

    if is_live:
        try:
            client = get_broker_client()
            if not client.is_authenticated():
                raise ConnectionError("Broker gateway is not authenticated (please log in at https://localhost:5000)")
            account_id = config.get("account_id") or client.get_primary_account_id()
            balances = client.get_balances(account_id)
            if float(balances.get("total_equity", 0.0)) <= 0.0 and float(balances.get("cash", 0.0)) <= 0.0:
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
            broker_name = config.get("broker", "IBKR")
            print(f"[MAPLE WARNING] Failed to query live {broker_name} state ({e}), falling back to local ledger.")

    # Simulated or fallback ledger reconstruction
    positions: Dict[str, Dict[str, Any]] = {}
    cash = 0.0

    if not os.path.exists(TRADES_FILE):
        return {"positions": positions, "cash": 0.0, "total_equity": 0.0, "mode": "SIMULATED", "live_verified": False}

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

            if ticker.upper() == "CASH":
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
        "live_verified": False
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
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


def execute_buy(
    ticker: str,
    allocated_cash: float,
    current_price: float,
    target_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
    notes: str = "",
    open_price: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Executes a BUY order.
    In LIVE mode: validates Shariah whitelist, daily drawdown vs previous close, concentration & sector caps,
    scale-in cooldown/green-candle guard, submits a Limit Day Order, and polls for fill confirmation.
    In SIMULATED mode: updates local ledger.
    """
    ticker = normalize_ticker(ticker)
    config = load_config()
    is_live = config.get("trading_mode", "").upper() == "LIVE"

    # Circuit Breaker 1: Strict Shariah Basket Gatekeeper
    if ticker not in SHARIAH_COMPLIANT_BASKET:
        print(f"[MAPLE GATEKEEPER REJECT] {ticker} is NOT in the Shariah-compliant basket! Order blocked.")
        return None

    # Block duplicate order if already working on book
    pending_orders = config.get("pending_orders", {})
    if any(a in pending_orders for a in ticker_aliases(ticker)):
        print(f"[MAPLE] Pending order already active for {ticker}. Skipping duplicate BUY.")
        return None

    def _passes_scale_in_guards(active_tickers: Optional[set] = None, fallback_px: float = 0.0) -> bool:
        buy_counts = get_position_buy_counts(active_tickers=active_tickers) if active_tickers is not None else get_position_buy_counts()
        eff_count = buy_counts.get(ticker, 0)
        if active_tickers is not None and ticker in active_tickers and eff_count == 0:
            eff_count = 1
        if eff_count >= 2:
            print(f"[MAPLE SCALE CAP] {ticker} already has {eff_count} entries in active cycle (max 2 entries allowed). Order blocked.")
            return False
        if eff_count >= 1:
            cooldown_hrs = float(config.get("scale_in_cooldown_hours", 4.0))
            last_map = get_position_last_buy_info(active_tickers=active_tickers) if active_tickers is not None else get_position_last_buy_info()
            last_buy = last_map.get(ticker)
            if last_buy and last_buy.get("last_buy_dt"):
                elapsed_hrs = (datetime.datetime.now() - last_buy["last_buy_dt"]).total_seconds() / 3600.0
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
    if not is_live and not _passes_scale_in_guards():
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
        try:
            client = get_broker_client()
            if not client.is_authenticated():
                print("[MAPLE LIVE BLOCKED] Broker gateway not authenticated. Please log in at https://localhost:5000")
                return None
            account_id = config.get("account_id") or client.get_primary_account_id()

            # Circuit Breaker 2 & 3: Dynamic Order Cap + Cash-Flow-Adjusted Daily Drawdown Limit (4% of ref NAV)
            balances = client.get_balances(account_id)
            total_equity = float(balances.get("total_equity", 1000.0))
            cash_available = float(balances.get("cash", 0.0))
            try:
                reconcile_capital_flows(cash_available, live_equity=total_equity, config=config)
            except Exception:
                pass
            max_single_cap = get_effective_order_cap(config, total_equity)
            if allocated_cash > max_single_cap:
                allocated_cash = max_single_cap

            ref_nav = _get_reference_nav(config)
            daily_loss_limit = get_effective_daily_loss_limit(config, ref_nav)
            drawdown = ref_nav - total_equity
            if drawdown >= daily_loss_limit:
                print(f"[MAPLE CIRCUIT BREAKER] Daily loss limit exceeded vs prev close (${ref_nav:.2f}): -${drawdown:.2f} >= ${daily_loss_limit:.2f}. All buying halted.")
                return None

            # Circuit Breaker 4: Position Concentration Cap (default 25% of portfolio NAV) + Live Scale-In Reconciliation
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
            if not _passes_scale_in_guards(active_tickers=live_held, fallback_px=existing_acb):
                return None
            existing_val = existing_shares * current_price
            max_pos_cad = total_equity * max_pos_pct
            if existing_val + allocated_cash > max_pos_cad:
                allocated_cash = max(0.0, max_pos_cad - existing_val)
                if allocated_cash < min_trade_thresh:
                    print(f"[MAPLE CONCENTRATION GUARD] {ticker} already at ${existing_val:.2f} ({existing_val/total_equity*100:.1f}% of NAV, cap {max_pos_pct*100:.0f}%). Order blocked.")
                    return None

            # Circuit Breaker 5: Sector Exposure Cap (default 35% of portfolio NAV across held + resting BUY orders)
            held_sector_tickers = set()
            held_sector_cad = 0.0
            for p in positions_raw:
                p_sym = normalize_ticker(p.get("symbol", ""))
                p_qty = float(p.get("openQuantity", 0.0))
                if p_qty > 0 and get_ticker_sector(p_sym) == target_sector:
                    held_sector_tickers.add(p_sym)
                    p_px = current_price if p_sym == ticker else float(p.get("currentPrice") or p.get("averageEntryPrice") or 0.0)
                    held_sector_cad += p_qty * p_px
            # Include any same-scan fill not yet reflected in broker positions_raw or pending_orders
            pending_norm = {normalize_ticker(k) for k in pending_orders.keys()}
            for t_sym, t_info in get_position_last_buy_info().items():
                if (
                    get_ticker_sector(t_sym) == target_sector
                    and t_sym not in held_sector_tickers
                    and t_sym not in pending_norm
                    and t_info.get("last_buy_dt")
                    and (datetime.datetime.now() - t_info["last_buy_dt"]).total_seconds() < 600
                ):
                    held_sector_cad += float(t_info.get("shares", 0.0)) * float(t_info.get("last_buy_price", 0.0))

            sector_exposure = held_sector_cad + pending_sector_cad
            max_sector_cad = total_equity * max_sector_pct
            if sector_exposure + allocated_cash > max_sector_cad:
                allocated_cash = max(0.0, max_sector_cad - sector_exposure)
                if allocated_cash < min_trade_thresh:
                    print(
                        f"[MAPLE SECTOR CAP] {target_sector} exposure at ${sector_exposure:.2f} ({sector_exposure/total_equity*100:.1f}% of NAV, cap {max_sector_pct*100:.0f}%). Blocking {ticker}."
                    )
                    return None

            cash_available = balances.get("cash", 0.0)
            # Cash Reserve Buffer ($20 CAD minimum left for liquidity/ECN)
            safe_cash = max(0.0, cash_available - 20.0)
            if allocated_cash > safe_cash:
                allocated_cash = safe_cash

            if allocated_cash < min_trade_thresh:
                print(f"[MAPLE] Insufficient free cash for {ticker}: ${allocated_cash:.2f} (Available: ${cash_available:.2f})")
                return None

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

            print(f"[MAPLE LIVE ORDER] Placing Limit BUY: {shares} {ticker} @ ${limit_price:.2f} (Account #{account_id})...")
            order_res = client.place_limit_order(account_id, symbol_id, "Buy", shares, limit_price)
            order_id = order_res.get("orderId")
            if not order_id and "orders" in order_res and order_res["orders"]:
                order_id = order_res["orders"][0].get("id")

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
            if order_status == "Filled" or cum_fill >= shares:
                actual_px = avg_fill_price if avg_fill_price > 0 else limit_price
                new_shares = existing_shares + shares
                blended_acb = ((existing_shares * existing_acb) + (shares * actual_px)) / new_shares if existing_shares > 0 else actual_px
                eff_stop = round(blended_acb * (1.0 - stop_pct / 100.0), 2) if existing_shares > 0 else (stop_loss_price if stop_loss_price else round(actual_px * (1.0 - stop_pct / 100.0), 2))

                bal_after = client.get_balances(account_id)
                rem_cash = bal_after.get("cash", cash_available - (shares * actual_px))

                order_note = f"LIVE LIMIT ORDER #{order_id} | {notes}".strip()
                log_trade(ticker, "BUY", shares, actual_px, new_shares, rem_cash, notes=order_note)

                if "active_targets" not in config:
                    config["active_targets"] = {}
                config["active_targets"][ticker] = {
                    "target_price": target_price,
                    "stop_loss_price": eff_stop,
                }
                save_config(config)

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action="BUY",
                        shares=shares,
                        price=actual_px,
                        order_id=order_id,
                        target_price=target_price,
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
                print(f"[MAPLE LIVE WORKING ORDER] Limit Buy #{order_id} active on TSX book ({order_status}, fills: {cum_fill}/{shares} shs).")
                if "pending_orders" not in config:
                    config["pending_orders"] = {}
                config["pending_orders"][ticker] = {
                    "order_id": str(order_id),
                    "action": "BUY",
                    "shares": shares,
                    "existing_shares": existing_shares,
                    "acb": existing_acb,
                    "limit_price": limit_price,
                    "target_price": target_price,
                    "stop_loss_price": stop_loss_price,
                    "reason": notes,
                    "conid": symbol_id,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                        notes=f"Resting limit buy on TSX book ({notes})"
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
    state = get_ledger_state()
    cash = state["cash"]
    total_equity = state.get("total_equity", cash)
    max_single_cap = get_effective_order_cap(config, total_equity)
    if allocated_cash > max_single_cap:
        allocated_cash = max_single_cap
    existing_pos = state["positions"].get(ticker, {})
    current_shares = existing_pos.get("shares", 0.0)
    existing_acb = existing_pos.get("acb", current_price)
    existing_val = current_shares * current_price
    if existing_val + allocated_cash > total_equity * max_pos_pct:
        allocated_cash = max(0.0, total_equity * max_pos_pct - existing_val)

    sim_sector_cad = pending_sector_cad + sum(
        p["shares"] * (current_price if normalize_ticker(t) == ticker else float(p.get("current_price") or p.get("acb") or 0.0))
        for t, p in state["positions"].items()
        if p.get("shares", 0.0) > 0 and get_ticker_sector(t) == target_sector
    )
    if sim_sector_cad + allocated_cash > total_equity * max_sector_pct:
        allocated_cash = max(0.0, total_equity * max_sector_pct - sim_sector_cad)
        if allocated_cash < min_trade_thresh:
            print(
                f"[MAPLE SECTOR CAP] {target_sector} exposure at ${sim_sector_cad:.2f} ({sim_sector_cad/total_equity*100:.1f}% of NAV, cap {max_sector_pct*100:.0f}%). Blocking {ticker}."
            )
            return None

    if allocated_cash > cash:
        allocated_cash = cash
    if allocated_cash < min_trade_thresh:
        print(f"[MAPLE] Insufficient or capped cash for {ticker}: ${allocated_cash:.2f}")
        return None

    max_single_share_pct = float(config.get("max_single_share_nav_pct", 0.30))
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

    actual_cost = round(shares * current_price, 2)
    new_cash = round(cash - actual_cost, 2)
    new_shares = current_shares + shares
    blended_acb = ((current_shares * existing_acb) + actual_cost) / new_shares if current_shares > 0 else current_price
    stop_pct = config.get("stop_loss_pct", 5.0)
    eff_stop = round(blended_acb * (1.0 - stop_pct / 100.0), 2) if current_shares > 0 else (stop_loss_price if stop_loss_price else round(current_price * (1.0 - stop_pct / 100.0), 2))

    log_trade(ticker, "BUY", shares, current_price, new_shares, new_cash, notes=notes)

    if "active_targets" not in config:
        config["active_targets"] = {}
    config["active_targets"][ticker] = {
        "target_price": target_price,
        "stop_loss_price": eff_stop,
    }
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
    ticker: str, current_price: float, reason: str = ""
) -> Optional[Dict[str, Any]]:
    """Executes a 100% position liquidation.
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

            shares = int(pos.get("openQuantity", 0))
            if shares <= 0:
                print(f"[MAPLE LIVE SELL] Open shares for {ticker} is 0.")
                return None

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

            print(f"[MAPLE LIVE ORDER] Placing Marketable Limit SELL: {shares} {ticker} @ Limit CAD ${limit_price:.2f} (Account #{account_id}, Reason: {reason})...")
            order_res = client.place_limit_order(account_id, symbol_id, "Sell", shares, limit_price)
            order_id = order_res.get("orderId")
            if not order_id and "orders" in order_res and order_res["orders"]:
                order_id = order_res["orders"][0].get("id")

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

                bal_after = client.get_balances(account_id)
                new_cash = float(bal_after.get("cash", 0.0)) if bal_after else 0.0

                default_comm = float(config.get("commission_per_order_cad", 1.0))
                implied_comm = round(proceeds - (new_cash - cash_before), 2) if (cash_before > 0 and new_cash > cash_before) else -1.0
                exit_comm = implied_comm if 0.05 <= implied_comm <= 5.00 else default_comm
                cost_basis_total = shares * acb
                pnl = round(proceeds - cost_basis_total - exit_comm, 2)
                pnl_pct = round((pnl / cost_basis_total) * 100, 2) if cost_basis_total > 0 else 0.0

                order_note = f"LIVE LIMIT SELL #{order_id} FILLED | {reason} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)".strip()
                log_trade(ticker, "SELL", shares, actual_px, 0.0, new_cash, notes=order_note)

                for alias in ticker_aliases(ticker):
                    if "active_targets" in config and alias in config["active_targets"]:
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
                print(f"[MAPLE LIVE WORKING ORDER] Limit Sell #{order_id} active on TSX book ({order_status}, fills: {cum_fill}/{shares} shs). Position retained until filled.")
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
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                        notes=f"Resting marketable limit sell on TSX book ({reason})"
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
    shares = pos.get("shares", 0.0)

    if shares <= 0:
        return None

    proceeds = round(shares * current_price, 2)
    sim_comm = float(config.get("commission_per_order_cad", 0.0))
    new_cash = round(state["cash"] + proceeds - sim_comm, 2)
    acb = pos.get("acb", current_price)
    cost_basis_total = shares * acb
    pnl = round(proceeds - cost_basis_total - sim_comm, 2)
    pnl_pct = round((pnl / cost_basis_total) * 100, 2) if cost_basis_total > 0 else 0.0

    notes = f"{reason} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)"
    log_trade(ticker, "SELL", shares, current_price, 0.0, new_cash, notes=notes.strip())

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
            if not order_id:
                del updated_pending[raw_ticker]
                changed = True
                continue

            status_res = client.get_order_status(account_id, str(order_id))
            status_str = status_res.get("order_status", "")
            cum_fill = float(status_res.get("cum_fill", 0.0))
            shares = float(p_info.get("shares", 0.0))
            limit_px = float(p_info.get("limit_price", 0.0))
            reason = p_info.get("reason", "")
            action = p_info.get("action", "SELL").upper()

            if status_str == "Filled" or (shares > 0 and cum_fill >= shares):
                actual_px = limit_px
                for px_key in ["average_price", "price", "avg_price", "avgPrice"]:
                    if status_res.get(px_key) and float(status_res.get(px_key, 0)) > 0:
                        actual_px = float(status_res.get(px_key))
                        break

                print(f"[MAPLE LIVE FILL CONFIRMED] Order #{order_id} for {shares} {ticker} FILLED @ CAD {actual_px:.2f}!")
                bal_after = client.get_balances(account_id)
                new_cash = bal_after.get("cash", 0.0)

                acb = float(p_info.get("acb", 0.0))
                existing_shs = float(p_info.get("existing_shares", 0.0))
                try:
                    live_positions = client.get_positions(account_id)
                    aliases = set(ticker_aliases(ticker))
                    live_pos = next((p for p in live_positions if normalize_ticker(p.get("symbol", "")) in aliases or p.get("symbol", "").upper() in aliases), None)
                    new_shares = float(live_pos.get("openQuantity", 0.0)) if live_pos else (0.0 if action == "SELL" else (existing_shs + shares))
                except Exception:
                    new_shares = 0.0 if action == "SELL" else (existing_shs + shares)
                if acb > 0 and action == "SELL":
                    proceeds = round(shares * actual_px, 2)
                    default_comm = float(config.get("commission_per_order_cad", 1.0))
                    cash_before = float(p_info.get("cash_before", 0.0))
                    implied_comm = (
                        round(proceeds - (new_cash - cash_before), 2)
                        if (cash_before > 0 and new_cash > cash_before and len(pending) == 1)
                        else -1.0
                    )
                    exit_comm = implied_comm if 0.05 <= implied_comm <= 5.00 else default_comm
                    cost_basis_total = shares * acb
                    pnl = round(proceeds - cost_basis_total - exit_comm, 2)
                    pnl_pct = round((pnl / cost_basis_total) * 100, 2) if cost_basis_total > 0 else 0.0
                else:
                    pnl = None
                    pnl_pct = None
                pnl_str = f" | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)" if pnl is not None else ""

                order_note = f"LIVE LIMIT {action} #{order_id} FILLED | {reason}{pnl_str}".strip()
                log_trade(ticker, action, shares, actual_px, new_shares, new_cash, notes=order_note)

                if action == "SELL":
                    for alias in ticker_aliases(ticker):
                        if "active_targets" in config and alias in config["active_targets"]:
                            del config["active_targets"][alias]
                elif action == "BUY":
                    if "active_targets" not in config:
                        config["active_targets"] = {}
                    stop_pct = config.get("stop_loss_pct", 5.0)
                    blended_acb = ((existing_shs * acb) + (shares * actual_px)) / new_shares if (existing_shs > 0 and new_shares > 0) else actual_px
                    eff_stop = p_info.get("stop_loss_price") or round(blended_acb * (1.0 - stop_pct / 100.0), 2)
                    config["active_targets"][ticker] = {
                        "target_price": p_info.get("target_price"),
                        "stop_loss_price": eff_stop
                    }

                del updated_pending[raw_ticker]
                changed = True

                try:
                    from telegram_notifier import send_trade_alert
                    send_trade_alert(
                        ticker=ticker,
                        action=action,
                        shares=shares,
                        price=actual_px,
                        order_id=order_id,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        notes=f"FILLED on TSX book: {reason}"
                    )
                except Exception:
                    pass

            elif status_str in ["Cancelled", "Inactive"] and cum_fill == 0:
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


def get_position_holding_days(active_tickers: Optional[set] = None) -> Dict[str, int]:
    """Reconstructs the number of calendar days each currently open position has been held."""
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

    now = datetime.datetime.now()
    return {
        t: max(0, (now - dt).days)
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


def check_target_stops(
    market_prices: Dict[str, float],
    market_data: Optional[Dict[str, Dict[str, Any]]] = None,
    allow_stagnation_exit: bool = False,
    is_chop_window: bool = False,
):
    """Automatically executes exits if prices touch target sell, protective stop, or 4-day bearish stagnation,
    and ratchets stop-losses to breakeven once a position reaches >= +2.0% unrealized gain.
    """
    sync_working_orders()
    state = get_ledger_state()
    config = load_config()
    active_targets = config.get("active_targets", {})
    init_portfolio = config.get("initial_portfolio", {})
    held_set = {normalize_ticker(t) for t, p in state["positions"].items() if p.get("shares", 0) > 0}
    holding_days = get_position_holding_days(active_tickers=held_set)

    from maple_strategy import MapleStrategy
    MapleStrategy._sync_from_config()

    for raw_ticker, pos in state["positions"].items():
        ticker = normalize_ticker(raw_ticker)
        shares = pos.get("shares", 0.0)
        if shares <= 0:
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

        if acb > 0 and price > acb:
            gain_pct = ((price - acb) / acb) * 100.0
            if gain_pct >= MapleStrategy.BREAKEVEN_TRIGGER_PCT or (near_earnings and price >= round(acb * 1.003, 2)):
                comm_per_order = float(config.get("commission_per_order_cad", MapleStrategy.COMMISSION_PER_ORDER_CAD))
                # IBKR LIVE avgCost (acb) already includes entry commission; SIMULATED acb is raw fill price
                comm_mult = 1.0 if (state.get("mode") == "LIVE" and state.get("live_verified")) else 2.0
                comm_breakeven = round(acb + (comm_mult * comm_per_order) / max(1.0, float(shares)), 2)
                raw_breakeven = round(acb, 2)
                # Prefer commission-adjusted breakeven if price has at least a 0.4% cushion above it; otherwise raw ACB
                candidate_stop = comm_breakeven if price >= round(comm_breakeven * 1.004, 2) else raw_breakeven
                if candidate_stop < price and (stop is None or candidate_stop > stop):
                    old_stop = stop
                    stop = candidate_stop
                    config.setdefault("active_targets", {}).setdefault(matched_alias, {})["target_price"] = target
                    config["active_targets"][matched_alias]["stop_loss_price"] = stop
                    save_config(config)
                    tag = "EARNINGS BREAKEVEN RATCHET" if (near_earnings and gain_pct < MapleStrategy.BREAKEVEN_TRIGGER_PCT) else "BREAKEVEN RATCHET"
                    print(
                        f"[MAPLE {tag}] Ratcheted stop-loss for {ticker} from CAD {old_stop} to breakeven CAD {stop:.2f} (Price CAD {price:.2f}, +{gain_pct:.2f}%)"
                    )

        # 1. Target Hit
        if target is not None and price >= target:
            execute_sell(
                ticker,
                price,
                reason=f"AUTO TARGET HIT: CAD {price:.2f} (Target CAD {target:.2f})",
            )
            continue

        # 2. Stop-Loss Hit (buffered during 9:30-10:00 AM opening chop to prevent opening-wick shakeouts)
        if stop is not None:
            chop_buf_pct = float(config.get("chop_stop_buffer_pct", 2.0)) if is_chop_window else 0.0
            eff_stop = round(stop * (1.0 - chop_buf_pct / 100.0), 2) if chop_buf_pct > 0 else stop
            if price <= eff_stop:
                stop_label = f"Chop-Buffered Stop CAD {eff_stop:.2f} [Base CAD {stop:.2f}]" if chop_buf_pct > 0 else f"Stop CAD {stop:.2f}"
                execute_sell(
                    ticker,
                    price,
                    reason=f"AUTO STOP-LOSS HIT: CAD {price:.2f} ({stop_label})",
                )
                continue
            elif is_chop_window and price <= stop:
                print(
                    f"[MAPLE CHOP BUFFER] {ticker} dipped to CAD {price:.2f} (<= base stop CAD {stop:.2f}), "
                    f"holding above opening-chop floor CAD {eff_stop:.2f} (-{chop_buf_pct:.1f}% buffer until 10:00 AM)."
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
