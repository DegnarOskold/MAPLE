"""Runnable self-check for MAPLE's risk guards & Friday audit bug fixes (Oct 25, 2026)."""

import datetime
from unittest.mock import MagicMock, patch

import ibkr_client
import maple_brain
import maple_ledger
import maple_optimizer
import telegram_notifier
from maple_strategy import MapleStrategy


def run_checks():
    # 1. Tighten (not disable) Capitulation Reversal
    red_cap, r1 = MapleStrategy.calculate_tranche_size(
        {"RSI_7": 29.0, "Vol_Ratio": 4.59, "Open": 60.00, "Price": 58.20, "Pct_From_Low": 2.10, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
        signal_type="CAPITULATION REVERSAL",
    )
    assert red_cap == 0.0 and "Knife-Catch Guard" in r1, f"Red-candle capitulation not blocked: {red_cap}, {r1}"

    weak_bounce, r2 = MapleStrategy.calculate_tranche_size(
        {"RSI_7": 29.0, "Vol_Ratio": 2.75, "Open": 58.00, "Price": 58.30, "Pct_From_Low": 0.90, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
        signal_type="CAPITULATION REVERSAL",
    )
    assert weak_bounce == 0.0 and "Bounce Filter" in r2, f"Weak-bounce capitulation not blocked: {weak_bounce}, {r2}"

    valid_cap, r3 = MapleStrategy.calculate_tranche_size(
        {"RSI_7": 29.0, "Vol_Ratio": 4.59, "Open": 58.00, "Price": 59.10, "Pct_From_Low": 1.90, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
        signal_type="CAPITULATION REVERSAL",
    )
    assert valid_cap == 0.15 and "Starter" in r3, f"Valid capitulation should size at 0.15: {valid_cap}, {r3}"

    # 2. Full 47-ticker US sector map + 35% sector cap (including resting BUY pending_orders)
    assert set(maple_ledger.SECTOR_MAP.keys()) == maple_ledger.SHARIAH_COMPLIANT_BASKET
    assert all(maple_ledger.get_ticker_sector(t) != "Other" for t in maple_ledger.SHARIAH_COMPLIANT_BASKET)
    _legacy_tsx_bkt = set(maple_ledger.SHARIAH_COMPLIANT_BASKET) | set(maple_ledger._LEGACY_TSX_SECTORS.keys())
    _legacy_tsx_patch = patch.object(maple_ledger, "SHARIAH_COMPLIANT_BASKET", _legacy_tsx_bkt)
    _legacy_brain_patch = patch.object(maple_brain, "SHARIAH_COMPLIANT_BASKET", _legacy_tsx_bkt)
    _legacy_tsx_patch.start()
    _legacy_brain_patch.start()

    base_cfg = {
        "trading_mode": "SIMULATED",
        "max_single_order_cad": 400.0,
        "min_trade_cad": 50.0,
        "max_position_pct": 0.25,
        "max_sector_pct": 0.35,
        "scale_in_cooldown_hours": 4.0,
        "commission_per_order_cad": 1.0,
        "pending_orders": {"PAAS.TO": {"action": "BUY", "shares": 3, "limit_price": 58.0}},  # $174 pending
        "active_targets": {},
    }
    sim_state = {
        "mode": "SIMULATED",
        "live_verified": False,
        "cash": 400.0,
        "total_equity": 1000.0,
        "positions": {
            "WPM.TO": {"shares": 1.0, "acb": 175.0, "current_price": 175.0},  # $175 held + $174 pending = $349 (34.9% of $1000)
            "RUS.TO": {"shares": 1.0, "acb": 90.0, "current_price": 90.0},
        },
    }
    with patch.object(maple_ledger, "load_config", return_value=dict(base_cfg)), \
         patch.object(maple_ledger, "get_ledger_state", return_value=sim_state), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"WPM.TO": 1, "RUS.TO": 1}):
        # ABX.TO is Precious Metals; only $1 room left before $350 (35%) cap (< $50 min_trade_cad) -> blocked
        res_sec = maple_ledger.execute_buy("ABX.TO", 150.0, 28.0)
        assert res_sec is None, "Sector cap failed to block Precious Metals breach"

    # 3. Scale-in 4h cooldown & red-candle guard on Entry #2
    from maple_market import now_et_naive
    now = now_et_naive()
    with patch.object(maple_ledger, "load_config", return_value=dict(base_cfg)), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"RUS.TO": 1}), \
         patch.object(maple_ledger, "get_position_last_buy_info", return_value={"RUS.TO": {"last_buy_dt": now - datetime.timedelta(minutes=15), "last_buy_price": 90.0, "shares": 1.0}}):
        assert maple_ledger.execute_buy("RUS.TO", 100.0, 91.0, open_price=89.5) is None, "15-min scale-in was not blocked"

    with patch.object(maple_ledger, "load_config", return_value=dict(base_cfg)), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"RUS.TO": 1}), \
         patch.object(maple_ledger, "get_position_last_buy_info", return_value={"RUS.TO": {"last_buy_dt": now - datetime.timedelta(hours=5), "last_buy_price": 90.0, "shares": 1.0}}):
        assert maple_ledger.execute_buy("RUS.TO", 100.0, 89.0, open_price=90.5) is None, "Red-candle scale-in was not blocked"

    # 4 & 5a. Stagnation price<min(EMA5,EMA9) exit (CVE.TO) + LIVE commission-accurate breakeven ratchet (SAP.TO)
    sells = []
    saved_cfgs = []
    live_cfg = {
        "trading_mode": "LIVE",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {
            "CVE.TO": {"target_price": 49.27, "stop_loss_price": 44.74},
            "SAP.TO": {"target_price": 43.09, "stop_loss_price": 40.09},
        },
        "initial_portfolio": {},
    }
    live_state = {
        "mode": "LIVE",
        "live_verified": True,
        "cash": 230.61,
        "total_equity": 966.12,
        "positions": {
            "CVE.TO": {"shares": 2.0, "acb": 47.09, "current_price": 44.89},
            "SAP.TO": {"shares": 1.0, "acb": 40.09, "current_price": 41.30},
        },
    }
    mkt = {
        "CVE.TO": {"Price": 44.89, "EMA_5": 45.93, "EMA_9": 45.88, "EMA_Crossover": "NEUTRAL (FILTERED)"},
        "SAP.TO": {"Price": 41.30, "EMA_5": 40.80, "EMA_9": 40.50, "EMA_Crossover": "BULLISH (EMA5 > EMA9)"},
    }
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=live_state), \
         patch.object(maple_ledger, "load_config", return_value=live_cfg), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: saved_cfgs.append(c)), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"CVE.TO": 8, "SAP.TO": 2}), \
         patch.object(maple_ledger, "execute_sell", side_effect=lambda t, p, reason="": sells.append((t, p, reason))):
        maple_ledger.check_target_stops({"CVE.TO": 44.89, "SAP.TO": 41.30}, market_data=mkt, allow_stagnation_exit=True)

    assert len(sells) == 1 and sells[0][0] == "CVE.TO" and "AUTO STAGNATION EXIT" in sells[0][2], f"CVE.TO stagnation exit failed: {sells}"
    assert live_cfg["active_targets"]["SAP.TO"]["stop_loss_price"] == 41.09, (
        f"SAP.TO LIVE breakeven stop expected 41.09, got {live_cfg['active_targets']['SAP.TO']['stop_loss_price']}"
    )

    # 5b. Optimizer attribution flags stagnant losers & sector concentration
    with patch.object(maple_optimizer, "get_position_holding_days", return_value={"CVE.TO": 8, "SAP.TO": 2}):
        attr, watch = maple_optimizer.calculate_position_attribution(live_state["positions"], 966.12)
        assert any(w["ticker"] == "CVE.TO" and "Stagnant" in w["note"] for w in watch), f"Missing stagnant flag: {watch}"

    # 6. Delayed IBKR quote ('6509': 'DB') blocked from overwriting real-time yfinance prices
    ib = ibkr_client.IBKRClient.__new__(ibkr_client.IBKRClient)
    delayed_snap = ib._parse_quote_snapshot({"31": "55.46", "84": "55.40", "86": "55.50", "6509": "DB"})
    realtime_snap = ib._parse_quote_snapshot({"31": "55.12", "84": "55.10", "86": "55.15", "6509": "RP"})
    assert delayed_snap["isDelayed"] is True and realtime_snap["isDelayed"] is False

    mock_broker = MagicMock()
    mock_broker.is_authenticated.return_value = True
    mock_broker.search_symbol.side_effect = lambda t: {"symbolId": 101 if t == "PAAS.TO" else 102}
    mock_broker.get_quotes.return_value = {
        101: {"lastTradePrice": 55.46, "bidPrice": 55.40, "askPrice": 55.50, "isDelayed": True},
        102: {"lastTradePrice": 40.55, "bidPrice": 40.52, "askPrice": 40.58, "isDelayed": False},
    }
    yf_map = {
        "PAAS.TO": {"Price": 55.00, "Open": 56.10, "High": 56.20, "Low": 54.95, "EMA_5": 55.80, "EMA_9": 56.00, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
        "SAP.TO": {"Price": 40.40, "Open": 40.10, "High": 40.60, "Low": 40.05, "EMA_5": 40.30, "EMA_9": 40.20, "EMA_Crossover": "BULLISH (EMA5 > EMA9)"},
    }
    with patch.object(maple_brain, "get_broker_client", return_value=mock_broker), \
         patch.object(maple_brain, "get_stock_data", side_effect=lambda t, mode="SHORT": dict(yf_map[t])):
        merged = maple_brain.fetch_latest_market_prices(["PAAS.TO", "SAP.TO"])
        assert merged["PAAS.TO"]["Price"] == 55.00, f"Delayed IBKR quote overwrote yfinance: {merged['PAAS.TO']}"
        assert merged["SAP.TO"]["Price"] == 40.55, f"Real-time IBKR quote failed to overlay: {merged['SAP.TO']}"

    chop_checked = []
    mock_broker.get_quote.side_effect = lambda cid: (
        {"lastTradePrice": 55.46, "bidPrice": 55.40, "isDelayed": True}
        if cid == 101
        else {"lastTradePrice": 40.55, "bidPrice": 40.52, "isDelayed": False}
    )
    chop_state = {"positions": {"PAAS.TO": {"shares": 3.0, "acb": 58.27}, "SAP.TO": {"shares": 1.0, "acb": 40.09}}}
    with patch.object(maple_brain, "get_ledger_state", return_value=chop_state), \
         patch.object(maple_brain, "load_config", return_value={"trading_mode": "LIVE", "active_targets": {}}), \
         patch.object(maple_brain, "get_broker_client", return_value=mock_broker), \
         patch.object(maple_brain, "get_stock_data", side_effect=lambda t, mode="SHORT": dict(yf_map[t])), \
         patch.object(maple_brain, "check_target_stops", side_effect=lambda pm, **kw: chop_checked.append((dict(pm), kw))):
        maple_brain.run_chop_exit_guard()
        assert chop_checked and chop_checked[0][0]["PAAS.TO"] == 55.00 and chop_checked[0][0]["SAP.TO"] == 40.55, f"Chop guard price mismatch: {chop_checked}"
        assert chop_checked[0][1].get("is_chop_window") is True, f"Chop guard must pass is_chop_window=True: {chop_checked}"

    # 7. Green-day rally exception defers 4-day stagnation exit on recovering positions (Oct 23 CVE.TO case)
    deferred_sells = []
    cve_rally_state = {
        "mode": "LIVE",
        "live_verified": True,
        "cash": 230.62,
        "total_equity": 966.12,
        "positions": {"CVE.TO": {"shares": 2.0, "acb": 47.09, "current_price": 45.66}},
    }
    cve_rally_mkt = {
        "CVE.TO": {
            "Price": 45.66,
            "Open": 45.25,
            "Prev_Close": 44.88,
            "EMA_5": 45.80,
            "EMA_9": 45.87,
            "EMA_Crossover": "BEARISH (EMA5 < EMA9)",
        }
    }
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=cve_rally_state), \
         patch.object(maple_ledger, "load_config", return_value=dict(live_cfg)), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"CVE.TO": 8}), \
         patch.object(maple_ledger, "execute_sell", side_effect=lambda t, p, reason="": deferred_sells.append((t, p, reason))):
        maple_ledger.check_target_stops({"CVE.TO": 45.66}, market_data=cve_rally_mkt, allow_stagnation_exit=True)
    assert deferred_sells == [], f"CVE.TO green-day rally should defer stagnation exit, got: {deferred_sells}"

    # 8. Net-of-exit-commission realized P&L in execute_sell & sync_working_orders
    sell_broker = MagicMock()
    sell_broker.is_authenticated.return_value = True
    sell_broker.get_positions.return_value = [{"symbol": "CVE", "openQuantity": 2, "symbolId": 777, "averageEntryPrice": 47.09}]
    sell_broker.get_balances.side_effect = [{"cash": 230.62}, {"cash": 321.86}]  # +$91.24 net vs $91.70 gross -> $0.46 exit comm
    sell_broker.get_quote.return_value = {"bidPrice": 46.80, "lastTradePrice": 46.85, "isDelayed": True}
    sell_broker.place_limit_order.return_value = {"orderId": "1922370702"}
    sell_broker.get_order_status.return_value = {"order_status": "Filled", "cum_fill": 2, "average_price": 45.85}

    logged_trades = []
    with patch.object(maple_ledger, "load_config", return_value={"trading_mode": "LIVE", "account_id": "U12345678", "commission_per_order_cad": 1.0, "active_targets": {}}), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: None), \
         patch.object(maple_ledger, "get_broker_client", return_value=sell_broker), \
         patch.object(maple_ledger, "log_trade", side_effect=lambda *args, **kw: logged_trades.append((args, kw))), \
         patch.object(telegram_notifier, "send_trade_alert", return_value=True), \
         patch("time.sleep", return_value=None):
        sell_res = maple_ledger.execute_sell("CVE.TO", 45.66, reason="AUTO STAGNATION EXIT")

    # Also verify delayed quote bid ($46.80) was ignored in favor of current_price ($45.66 * 0.997 = $45.52)
    placed_limit = sell_broker.place_limit_order.call_args[0][4]
    assert placed_limit == 45.52, f"Delayed quote polluted sell limit price: {placed_limit}"
    assert sell_res["pnl"] == -2.94 and sell_res["pnl_pct"] == -3.12, f"Expected net P&L -2.94 (-3.12%), got: {sell_res}"

    sync_broker = MagicMock()
    sync_broker.is_authenticated.return_value = True
    sync_broker.get_order_status.return_value = {"order_status": "Filled", "cum_fill": 1, "average_price": 166.74}
    sync_broker.get_balances.return_value = {"cash": 487.77}
    sync_broker.get_positions.return_value = []
    sync_cfg = {
        "trading_mode": "LIVE",
        "account_id": "U12345678",
        "commission_per_order_cad": 1.0,
        "pending_orders": {
            "WPM.TO": {"order_id": "1922370857", "action": "SELL", "shares": 1, "acb": 175.47, "limit_price": 165.19, "cash_before": 321.86, "reason": "STOP-LOSS"}
        },
        "active_targets": {},
    }
    with patch.object(maple_ledger, "load_config", return_value=sync_cfg), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: None), \
         patch.object(maple_ledger, "get_broker_client", return_value=sync_broker), \
         patch.object(maple_ledger, "log_trade", side_effect=lambda *args, **kw: logged_trades.append((args, kw))), \
         patch.object(telegram_notifier, "send_trade_alert", return_value=True):
        maple_ledger.sync_working_orders()
    assert "P&L: $-9.56 (-5.45%)" in logged_trades[-1][1]["notes"], f"Unexpected sync P&L note: {logged_trades[-1]}"

    # 9. Bold Markdown SELL ALERT parser
    sample_advice = "\n".join([
        "**Portfolio Status:**",
        "- **CLS.TO:** -$2.45 (-3.10%) 📉 *(STAGNATION EXIT: Held > 4 days, Negative, Bearish Cross. SELL)*",
        "**Actionable Alerts:**",
        "🔴 **SELL ALERT: CLS.TO (Stop Loss Triggered @ -5%)**",
        "🔴 **SELL ALERT: ATRL.TO (Stagnation Exit)**",
        "DO NOT SELL SAP.TO",
        "- Holding steady. No immediate technical setups or sell triggers.",
    ])
    parsed = maple_brain.parse_bot_signals(sample_advice)
    assert [(s["action"], s["ticker"]) for s in parsed] == [("SELL", "CLS.TO"), ("SELL", "ATRL.TO")], f"Parser mismatch: {parsed}"

    # 10. Fix 1: Ghost CSV holdings (CCL-B.TO) ignored when reconciling against live IBKR holdings
    assert "CCL-B.TO" not in maple_ledger.get_position_buy_counts(active_tickers={"SAP.TO"})
    assert "CCL-B.TO" not in maple_ledger.get_position_holding_days(active_tickers={"SAP.TO"})

    live_buy_broker = MagicMock()
    live_buy_broker.is_authenticated.return_value = True
    live_buy_broker.get_balances.return_value = {"cash": 907.93, "total_equity": 948.43}
    live_buy_broker.get_positions.return_value = [{"symbol": "SAP", "openQuantity": 1, "averageEntryPrice": 40.09, "currentPrice": 40.50}]
    live_buy_broker.search_symbol.return_value = {"symbolId": 888}
    live_buy_broker.get_quote.return_value = {"askPrice": 95.00, "lastTradePrice": 94.95, "isDelayed": False}
    live_buy_broker.place_limit_order.return_value = {"orderId": "20001"}
    live_buy_broker.get_order_status.return_value = {"order_status": "Filled", "cum_fill": 2, "average_price": 95.00}
    with patch.object(maple_ledger, "load_config", return_value={"trading_mode": "LIVE", "account_id": "U12345678", "max_single_order_cad": 400.0, "min_trade_cad": 50.0, "max_position_pct": 0.25, "max_sector_pct": 0.35, "max_single_share_nav_pct": 0.30, "pending_orders": {}, "active_targets": {}}), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: None), \
         patch.object(maple_ledger, "get_broker_client", return_value=live_buy_broker), \
         patch.object(maple_ledger, "_get_reference_nav", return_value=948.43), \
         patch.object(maple_ledger, "reconcile_capital_flows", return_value=0.0), \
         patch.object(maple_ledger, "log_trade", side_effect=lambda *a, **kw: None), \
         patch.object(telegram_notifier, "send_trade_alert", return_value=True), \
         patch("time.sleep", return_value=None):
        # Even with current_price <= open_price (95.00 <= 96.00), CCL-B.TO has 0 live shares so it MUST NOT trigger Scale-In #2 red-candle block!
        ccl_res = maple_ledger.execute_buy("CCL-B.TO", 200.0, 95.00, open_price=96.00)
        assert ccl_res and ccl_res["shares"] == 2, f"Ghost CSV row blocked fresh CCL-B.TO entry: {ccl_res}"

    # 11. Fix 2: 1-Share Whole-Lot Floor up to 30% of NAV ($240 SHOP.TO allowed; $347 CLS.TO blocked)
    floor_cfg = {
        "trading_mode": "SIMULATED",
        "max_single_order_cad": 400.0,
        "min_trade_cad": 50.0,
        "max_position_pct": 0.25,
        "max_sector_pct": 0.35,
        "max_single_share_nav_pct": 0.30,
        "pending_orders": {},
        "active_targets": {},
    }
    floor_state = {
        "mode": "SIMULATED",
        "live_verified": False,
        "cash": 907.93,
        "total_equity": 948.43,
        "positions": {"SAP.TO": {"shares": 1.0, "acb": 40.09, "current_price": 40.50}},
    }
    with patch.object(maple_ledger, "load_config", return_value=dict(floor_cfg)), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: None), \
         patch.object(maple_ledger, "get_ledger_state", return_value=floor_state), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"SAP.TO": 1}), \
         patch.object(maple_ledger, "log_trade", side_effect=lambda *a, **kw: None):
        shop_res = maple_ledger.execute_buy("SHOP.TO", 181.59, 240.00)  # 25.3% of NAV <= 30% -> 1 share
        cls_res = maple_ledger.execute_buy("CLS.TO", 226.98, 346.97)    # 36.6% of NAV > 30% -> blocked
        assert shop_res and shop_res["shares"] == 1, f"1-share floor failed for SHOP.TO: {shop_res}"
        assert cls_res is None, f"Oversized CLS.TO (>30% NAV) should be blocked: {cls_res}"

    # 12. Fix 3: Direct 32-ticker autonomous scanner + macro commodity alignment
    scan_mkt = {
        "SHOP.TO": {"Price": 240.0, "Open": 236.0, "EMA_5": 238.0, "EMA_9": 235.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.75, "ADX_14": 31.0, "RSI_7": 55.0},
        "AEM.TO": {"Price": 246.0, "Open": 242.0, "EMA_5": 244.0, "EMA_9": 241.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.80, "ADX_14": 32.0, "RSI_7": 56.0},
        "WFG.TO": {"Price": 102.0, "Open": 100.0, "Pct_From_Low": 2.1, "EMA_5": 105.0, "EMA_9": 107.0, "EMA_Crossover": "BEARISH (EMA5 < EMA9)", "Vol_Ratio": 1.90, "ADX_14": 25.0, "RSI_7": 28.0},
    }
    sigs_gold_down = maple_brain.evaluate_autonomous_signals(
        scan_mkt, maple_ledger.SHARIAH_COMPLIANT_BASKET, macro_state={"GC=F": False, "CL=F": True}
    )
    assert [s["ticker"] for s in sigs_gold_down] == ["SHOP.TO", "WFG.TO"], f"Autonomous scan ranking/macro mismatch: {sigs_gold_down}"

    # 13. Fix 4: Opening Chop 2% stop buffer prevents opening-wick stop-outs while harvesting targets immediately
    chop_sells = []
    chop_cfg = {
        "trading_mode": "LIVE",
        "chop_stop_buffer_pct": 2.0,
        "pending_orders": {},
        "active_targets": {
            "PAAS.TO": {"target_price": 62.35, "stop_loss_price": 55.26},  # 2% chop floor = $54.15
            "SAP.TO": {"target_price": 43.09, "stop_loss_price": 40.09},
        },
        "initial_portfolio": {},
    }
    chop_live_state = {
        "mode": "LIVE",
        "live_verified": True,
        "cash": 500.0,
        "total_equity": 960.0,
        "positions": {
            "PAAS.TO": {"shares": 3.0, "acb": 58.27, "current_price": 55.21},
            "SAP.TO": {"shares": 1.0, "acb": 40.09, "current_price": 43.15},
        },
    }
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=chop_live_state), \
         patch.object(maple_ledger, "load_config", return_value=chop_cfg), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: None), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"PAAS.TO": 3, "SAP.TO": 5}), \
         patch.object(maple_ledger, "execute_sell", side_effect=lambda t, p, reason="": chop_sells.append((t, p, reason))):
        maple_ledger.check_target_stops({"PAAS.TO": 55.21, "SAP.TO": 43.15}, is_chop_window=True)
        assert [s[0] for s in chop_sells] == ["SAP.TO"], f"PAAS.TO should survive $55.21 wick in chop, SAP.TO target should harvest: {chop_sells}"
        maple_ledger.check_target_stops({"PAAS.TO": 54.10}, is_chop_window=True)
        assert chop_sells[-1][0] == "PAAS.TO" and "Chop-Buffered Stop" in chop_sells[-1][2], f"Deep crash should still stop out in chop: {chop_sells}"

    # 14. Zero external TSX-Trader dependency across all MAPLE runtime modules & config
    import os
    import sys
    import maple_compare
    import maple_market
    assert all("TSX-Trader" not in p for p in sys.path), f"External TSX-Trader leaked into sys.path: {sys.path}"
    for fname in ("maple_brain.py", "maple_ledger.py", "maple_optimizer.py", "maple_compare.py", "maple_market.py", "maple_config.json"):
        fpath = os.path.join(maple_ledger.MAPLE_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            txt = f.read()
        assert "TSX-Trader" not in txt and "market_analyzer" not in txt, f"External dependency remained in {fname}!"

    # 15. Oct 28 / US Volume Curve: US pre-close volume curve (~38.8% at 150m), whole-share round-up, max_share_price filter, unfiltered mover & fee audit
    assert 0.38 <= maple_market._expected_intraday_vol_fraction(150.0) <= 0.40
    assert maple_market._expected_intraday_vol_fraction(390.0) == 1.0
    assert maple_ledger._size_whole_shares("CNQ.TO", 226.98, 76.76, 0.0, 0.0, 947.23, 0.25, 400.0, 0.0, 0.35, 887.93, 0.30) == 3
    assert maple_ledger._size_whole_shares("CNQ.TO", 226.98, 76.76, 0.0, 0.0, 900.00, 0.25, 400.0, 0.0, 0.35, 887.93, 0.30) == 2

    cap_scan_mkt = dict(scan_mkt, **{"CSU.TO": {"Price": 3348.10, "Open": 3310.0, "EMA_5": 3320.0, "EMA_9": 3290.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.35, "ADX_14": 40.4, "RSI_7": 62.0}})
    sigs_affordable = maple_brain.evaluate_autonomous_signals(
        cap_scan_mkt, maple_ledger.SHARIAH_COMPLIANT_BASKET, macro_state={"GC=F": False, "CL=F": True}, max_share_price=284.18
    )
    assert "CSU.TO" not in [s["ticker"] for s in sigs_affordable] and "SHOP.TO" in [s["ticker"] for s in sigs_affordable]

    with patch.object(maple_optimizer, "get_position_holding_days", return_value={"CNQ.TO": 0}), \
         patch.object(maple_optimizer, "get_position_last_buy_info", return_value={"CNQ.TO": {"fill_acb": 76.66, "shares": 2.0}}):
        cnq_attr, _ = maple_optimizer.calculate_position_attribution({"CNQ.TO": {"shares": 2.0, "acb": 77.04, "current_price": 76.78}}, 947.26)
        assert cnq_attr[0]["gross_pnl"] == 0.24 and cnq_attr[0]["entry_fee_cad"] == 0.76, f"Fee/gross split mismatch: {cnq_attr}"

    with patch.object(maple_optimizer, "get_ledger_state", return_value={"positions": {}}), \
         patch.object(maple_optimizer, "get_stock_data", return_value={"Price": 420.54, "Prev_Close": 388.35, "Pct_From_Low": 5.66, "RSI_7": 49.71, "Vol_Ratio": 1.59, "ADX_14": 32.52, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"}):
        movers = maple_optimizer.scan_missed_opportunities(["CLS.TO"])
        assert len(movers) == 1 and movers[0]["eligible"] is False and "Trend Gatekeeper" in movers[0]["gate_status"], f"Gated top mover hidden: {movers}"

    # 16. Oct 29 Retrospective Patches: scale-in #2 price-progress guard, post-scale target math, 3-bucket BUY audit & untruncated gate strings
    old_buy_dt = now - datetime.timedelta(hours=5.0)
    with patch.object(maple_ledger, "load_config", return_value={"trading_mode": "SIMULATED", "scale_in_cooldown_hours": 4.0, "pending_orders": {}}), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"CCL-B.TO": 1}), \
         patch.object(maple_ledger, "get_position_last_buy_info", return_value={"CCL-B.TO": {"last_buy_dt": old_buy_dt, "last_buy_price": 97.72, "fill_acb": 97.72, "shares": 1.0}}), \
         patch.object(maple_ledger, "get_ledger_state", return_value={"cash": 500.0, "total_equity": 950.0, "positions": {"CCL-B.TO": {"shares": 1.0, "acb": 97.72, "current_price": 97.85}}}), \
         patch.object(maple_ledger, "log_trade"):
        assert maple_ledger.execute_buy("CCL-B.TO", 100.0, 97.85, notes="[LOW-VOLUME SCALED ENTRY]", open_price=97.00) is None
        assert maple_ledger.execute_buy("CCL-B.TO", 100.0, 98.10, notes="[REGULAR BUY]", open_price=97.00) is None
        assert maple_ledger.execute_buy("CCL-B.TO", 100.0, 98.95, notes="[LOW-VOLUME SCALED ENTRY]", open_price=97.00) is not None

    tgt_2sh, _ = MapleStrategy.calculate_targets(97.98, {"ATR_5": 1.96, "BB_Mid": 96.26}, shares=2.0, cost_basis=98.095)
    tgt_1sh, _ = MapleStrategy.calculate_targets(97.98, {"ATR_5": 1.96, "BB_Mid": 96.26}, shares=1.0)
    assert tgt_2sh == 101.55 and tgt_2sh < tgt_1sh, f"Post-scale target mismatch: 2sh={tgt_2sh}, 1sh={tgt_1sh}"

    buys_29 = maple_optimizer.get_daily_buy_trades("2026-10-29")
    assert [b["bucket"] for b in buys_29] == ["Regular Trend", "Low-Volume Scaled", "Low-Volume Scaled"], f"Unexpected BUY buckets: {buys_29}"

    with patch.object(maple_optimizer, "get_ledger_state", return_value={"positions": {}}), \
         patch.object(maple_optimizer, "get_stock_data", return_value={"Price": 94.33, "Prev_Close": 92.20, "Pct_From_Low": 2.9, "RSI_7": 70.64, "Vol_Ratio": 0.81, "ADX_14": 25.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)"}):
        atz_movers = maple_optimizer.scan_missed_opportunities(["ATZ.TO"])
        assert "(68.0)" in atz_movers[0]["gate_status"], f"Gate status truncated mid-number: {atz_movers}"

    # 17. Oct 30 Retrospective Patches: 5d/1m fresh bar overlay, dynamic trading-day earnings + green breakeven ratchet, thin-liquidity cap & Friday WoW summary
    import pandas as pd
    stale_6mo = pd.DataFrame(
        {"Open": [108.5, 109.2], "High": [110.0, 110.8], "Low": [108.0, 109.0], "Close": [108.65, 110.12], "Volume": [3000000, 2100000]},
        index=pd.to_datetime(["2026-10-29", "2026-10-30"]),
    )
    fresh_5d = pd.DataFrame(
        {"Open": [109.2], "High": [111.3], "Low": [109.0], "Close": [111.11], "Volume": [3676072]},
        index=pd.to_datetime(["2026-10-30"]),
    )
    merged_eod = maple_market._overlay_fresh_bar(stale_6mo, df_5d=fresh_5d)
    assert float(merged_eod["Close"].iloc[-1]) == 111.11 and int(merged_eod["Volume"].iloc[-1]) == 3676072

    fresh_1m = pd.DataFrame(
        {"Open": [110.2], "High": [111.6], "Low": [108.9], "Close": [111.55], "Volume": [3700000]},
        index=pd.DatetimeIndex(["2026-10-30 15:45:00-04:00"]),
    )
    merged_intraday = maple_market._overlay_fresh_bar(stale_6mo, df_5d=fresh_5d, df_1m=fresh_1m, today_date=datetime.date(2026, 10, 30))
    assert float(merged_intraday["Close"].iloc[-1]) == 111.55 and float(merged_intraday["High"].iloc[-1]) == 111.6

    refreshed_cal = maple_market._refresh_calendar_days(
        {"SU.TO": {"earnings_date": "2026-11-03", "days_to_earnings": 99, "ex_dividend_date": "N/A"}},
        ref_date=datetime.date(2026, 10, 30),  # Friday -> Tuesday = 4 calendar days, 2 trading days
    )
    assert refreshed_cal["SU.TO"]["days_to_earnings"] == 4 and refreshed_cal["SU.TO"]["trading_days_to_earnings"] == 2
    su_gate, su_reason = MapleStrategy.calculate_tranche_size(
        {"Price": 110.57, "Open": 109.20, "EMA_5": 109.8, "EMA_9": 109.1, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 0.95, "ADX_14": 25.0, "RSI_7": 55.0, **refreshed_cal["SU.TO"]}
    )
    assert su_gate == 0.0 and "2 trading days" in su_reason, f"Trading-day earnings gate failed: {su_gate}, {su_reason}"

    thin_pct, thin_reason = MapleStrategy.calculate_tranche_size(
        {"Price": 38.13, "Open": 37.60, "EMA_5": 37.70, "EMA_9": 37.50, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 2.63, "Vol_SMA_10": 70810.0, "Intraday_Dollar_Vol": 667275.0, "ADX_14": 30.0, "RSI_7": 58.0}
    )
    assert thin_pct == MapleStrategy.BASE_TRANCHE_PCT and "Thin-Liquidity" in thin_reason, f"RCH.TO thin-liquidity cap failed: {thin_pct}, {thin_reason}"

    earn_cfg = {
        "trading_mode": "LIVE",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {"SU.TO": {"target_price": 115.30, "stop_loss_price": 105.01}},
        "initial_portfolio": {},
    }
    earn_state = {
        "mode": "LIVE",
        "live_verified": True,
        "cash": 359.63,
        "total_equity": 936.73,
        "positions": {"SU.TO": {"shares": 1.0, "acb": 111.12, "current_price": 111.60}},  # +0.43% (< +2.0% normal trigger), 1 trading day to earnings
    }
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=earn_state), \
         patch.object(maple_ledger, "load_config", return_value=earn_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"SU.TO": 1}), \
         patch.object(maple_ledger, "execute_sell") as mock_earn_sell:
        maple_ledger.check_target_stops({"SU.TO": 111.60}, market_data={"SU.TO": {"Price": 111.60, "trading_days_to_earnings": 1, "earnings_date": "2026-11-03"}})
        assert mock_earn_sell.call_count == 0 and earn_cfg["active_targets"]["SU.TO"]["stop_loss_price"] == 111.12, f"Pre-earnings breakeven ratchet failed: {earn_cfg}"

    with patch.object(maple_optimizer, "get_position_holding_days", return_value={"SU.TO": 0}), \
         patch.object(maple_optimizer, "get_position_last_buy_info", return_value={"SU.TO": {"fill_acb": 110.57, "shares": 1.0}}):
        _, earn_watch = maple_optimizer.calculate_position_attribution(
            {"SU.TO": {"shares": 1.0, "acb": 111.12, "current_price": 111.11, "stop_loss_price": 105.01}},
            936.73,
            calendar_map={"SU.TO": {"earnings_date": "2026-11-03", "trading_days_to_earnings": 2}},
        )
        assert any(w["ticker"] == "SU.TO" and "Earnings risk in 2 trading day(s)" in w["note"] for w in earn_watch), f"Missing held earnings watchlist flag: {earn_watch}"

    with patch.object(maple_optimizer, "load_nav_history", return_value={"2026-10-23": {"nav": 952.67}}):
        wk = maple_optimizer.get_weekly_summary("2026-10-30", 936.73, config={"initial_cash": 1000.0, "capital_contributions": {}})
        assert wk and wk["base_date"] == "2026-10-23" and wk["wow_pnl"] == -15.94 and wk["wow_pct"] == -1.67, f"Weekly summary math mismatch: {wk}"

    # 18. Nov 3 CAD $4,000 Deposit Scaling: auto-reconciliation, dynamic 25% order cap, 4% daily loss breaker & cash-flow-adjusted TWR
    dep_cfg = {
        "trading_mode": "LIVE",
        "initial_cash": 1000.0,
        "max_single_order_cad": 400.0,
        "max_position_pct": 0.25,
        "daily_loss_limit_cad": 40.0,
        "daily_loss_limit_pct": 0.04,
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "capital_contributions": {},
    }
    import json, tempfile
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False, encoding="utf-8") as tmp_nav:
        tmp_nav_path = tmp_nav.name
        json.dump({"2026-10-23": {"nav": 952.67, "cash": 400.0}, "2026-10-30": {"nav": 936.73, "cash": 359.63}}, tmp_nav)
    try:
        with patch.object(maple_ledger, "NAV_FILE", tmp_nav_path), \
             patch.object(maple_ledger, "save_config"):
            # Stock sale alone (cash up, equity flat) must NOT be misclassified as an external deposit
            assert maple_ledger.reconcile_capital_flows(907.93, live_equity=948.43, config=dep_cfg, today_str="2026-11-01") == 0.0
            # Real $4,000 deposit moves BOTH cash (+$4,000) and equity (+$4,025)
            inflow = maple_ledger.reconcile_capital_flows(4359.63, live_equity=4961.73, config=dep_cfg, today_str="2026-11-01")
            assert inflow == 4000.0 and dep_cfg["capital_contributions"] == {"2026-11-01": 4000.0}, f"Deposit auto-detect failed: {inflow}, {dep_cfg}"
            # Second scan on same day must NOT double-count the $4,000 deposit
            inflow_repeat = maple_ledger.reconcile_capital_flows(4359.63, live_equity=4961.73, config=dep_cfg, today_str="2026-11-01")
            assert inflow_repeat == 0.0 and dep_cfg["capital_contributions"] == {"2026-11-01": 4000.0}

        assert maple_ledger.get_effective_order_cap(dep_cfg, 936.73) == 400.0
        assert maple_ledger.get_effective_order_cap(dep_cfg, 4961.73) == 1240.43
        assert maple_ledger.get_effective_daily_loss_limit(dep_cfg, 4936.73) == 197.47
        assert maple_ledger.get_total_invested_capital(dep_cfg, up_to_date="2026-11-03") == 5000.0

        # At $4,961.73 (+$25.00 trading gain on top of $936.73 + $4,000 deposit): TWR reflects true performance, NOT +396%
        with patch.object(maple_ledger, "NAV_FILE", tmp_nav_path):
            twr_at_deposit = maple_ledger.compute_twr_pct(4936.73, config=dep_cfg, today_str="2026-11-03")
            twr_plus_25 = maple_ledger.compute_twr_pct(4961.73, config=dep_cfg, today_str="2026-11-03")
    finally:
        if os.path.exists(tmp_nav_path):
            os.remove(tmp_nav_path)
    assert twr_at_deposit == -6.33 and twr_plus_25 == -5.85, f"Unexpected TWR across $4,000 deposit: {twr_at_deposit}, {twr_plus_25}"

    with patch.object(maple_optimizer, "load_nav_history", return_value={"2026-10-30": {"nav": 936.73}}):
        wk_dep = maple_optimizer.get_weekly_summary("2026-11-06", 5010.00, config=dep_cfg)
        assert wk_dep and wk_dep["wow_pnl"] == 73.27 and wk_dep["wow_pct"] == 1.48, f"Deposit-week WoW math distorted: {wk_dep}"

    sent_msgs = []
    with patch.object(maple_ledger, "get_total_invested_capital", return_value=5000.0), \
         patch.object(telegram_notifier, "load_telegram_config", return_value={"notify_on_scans": True}), \
         patch.object(telegram_notifier, "is_configured", return_value=True), \
         patch.object(telegram_notifier, "send_telegram_message", side_effect=lambda m: sent_msgs.append(m) or True):
        telegram_notifier.send_scan_update(cash=2377.11, total_equity=4924.82, positions={})
    assert sent_msgs and "-1.50% vs USD 5,000 invested" in sent_msgs[0], f"Scan update still used $1000 seed: {sent_msgs}"

    # 19. Nov 2 Geopolitical Hardening: VIX panic regime filter, event-week 15%-20% tranche cap, and tiered profit-lock / trailing ratchet
    assert maple_market.is_macro_aligned("SHOP.TO", {"GC=F": True, "CL=F": True, "VIX_PANIC": True})[0] is False
    assert maple_market.is_macro_aligned("CNQ.TO", {"GC=F": True, "CL=F": True, "VIX_PANIC": True})[0] is True
    assert maple_market.is_macro_aligned("AEM.TO", {"GC=F": True, "CL=F": False, "VIX_PANIC": True})[0] is True

    ew_pct, _ = MapleStrategy.calculate_tranche_size(
        {"Price": 78.50, "Open": 77.50, "EMA_5": 77.80, "EMA_9": 77.10, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 2.0, "Vol_SMA_10": 500000.0, "Intraday_Dollar_Vol": 5000000.0, "ADX_14": 32.0, "RSI_7": 55.0}
    )
    assert ew_pct == MapleStrategy.MAX_TRANCHE_PCT, f"Max tranche cap should match config ({MapleStrategy.MAX_TRANCHE_PCT}), got {ew_pct}"

    ratch_cfg = {
        "trading_mode": "LIVE",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {
            "SU.TO": {"target_price": 115.30, "stop_loss_price": 105.01},
            "CNQ.TO": {"target_price": 84.00, "stop_loss_price": 72.78},
        },
        "initial_portfolio": {},
    }
    ratch_state = {
        "mode": "LIVE",
        "live_verified": True,
        "cash": 4359.63,
        "total_equity": 4961.73,
        "positions": {
            "SU.TO": {"shares": 1.0, "acb": 111.12, "current_price": 114.60},   # +3.13% (>3.0% & >75% to 115.30) -> Tier 2 (+1.5% net above 112.12 = 113.80)
            "CNQ.TO": {"shares": 2.0, "acb": 77.04, "current_price": 80.50},   # +4.49% (>=4.0%) -> Tier 3 (80.50 * 0.9875 = 79.49)
        },
    }
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=ratch_state), \
         patch.object(maple_ledger, "load_config", return_value=ratch_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"SU.TO": 1, "CNQ.TO": 2}), \
         patch.object(maple_ledger, "execute_sell"):
        maple_ledger.check_target_stops({"SU.TO": 114.60, "CNQ.TO": 80.50})
        assert ratch_cfg["active_targets"]["SU.TO"]["stop_loss_price"] == 113.80, f"Tier 2 profit-lock failed: {ratch_cfg}"
        assert ratch_cfg["active_targets"]["CNQ.TO"]["stop_loss_price"] == 79.49, f"Tier 3 trailing ratchet failed: {ratch_cfg}"

    # 20. Nov 2 Retrospective Patches: Entry #1 red-candle block, ratcheted stop preservation on scale-in, dynamic min_trade_cad & 09:30 stale-bar guard
    atz_pct, atz_r = MapleStrategy.calculate_tranche_size(
        {"Price": 155.05, "Open": 156.98, "EMA_5": 154.10, "EMA_9": 152.80, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 0.92, "ADX_14": 26.0, "RSI_7": 54.0},
        signal_type="LOW-VOLUME SCALED ENTRY",
    )
    assert atz_pct == 0.0 and "Intraday Red-Candle Guard" in atz_r, f"ATZ.TO afternoon breakdown not blocked: {atz_pct}, {atz_r}"

    assert maple_ledger.get_effective_min_trade({"min_trade_cad": 50.0}, 1000.0) == 50.0
    assert maple_ledger.get_effective_min_trade({"min_trade_cad": 50.0}, 4906.17) == 245.31

    tfii_cfg = {
        "trading_mode": "SIMULATED",
        "min_trade_cad": 50.0,
        "max_position_pct": 0.25,
        "max_sector_pct": 0.35,
        "scale_in_cooldown_hours": 4.0,
        "pending_orders": {},
        "active_targets": {"TFII.TO": {"target_price": 157.25, "stop_loss_price": 134.54}},
    }
    tfii_state = {
        "mode": "SIMULATED",
        "live_verified": False,
        "cash": 1548.80,
        "total_equity": 4906.17,
        "positions": {"TFII.TO": {"shares": 4.0, "acb": 132.30, "current_price": 135.24}},
    }
    with patch.object(maple_ledger, "load_config", return_value=tfii_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_ledger_state", return_value=tfii_state), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"TFII.TO": 1}), \
         patch.object(maple_ledger, "get_position_last_buy_info", return_value={"TFII.TO": {"last_buy_dt": now - datetime.timedelta(hours=5), "last_buy_price": 132.30, "shares": 4.0}}), \
         patch.object(maple_ledger, "log_trade"):
        # Sub-5% NAV tranche ($232.32 < $245.31) and capped 1-share scale-in ($135.24 < $245.31 when 4*135.24 + 2*135.24 ok vs 8*135.24 capped) blocked
        assert maple_ledger.execute_buy("TFII.TO", 232.32, 135.24, open_price=133.50) is None
        # Valid 2-share scale-in ($270.48 >= $245.31) preserves ratcheted stop capped at -2.5% below new $133.28 blended ACB ($129.95 vs -5% $126.62)
        res_tfii = maple_ledger.execute_buy("TFII.TO", 300.00, 135.24, target_price=157.25, open_price=133.50)
        assert res_tfii and res_tfii["shares"] == 2
        assert tfii_cfg["active_targets"]["TFII.TO"]["stop_loss_price"] == 129.95, f"Scale-in half-risk stop cap mismatch: {tfii_cfg}"

        # Position near 25% cap ($1,226.54) with $253.54 room (>= $245.31) -> sizes 1 share ($139.00 < $245.31) -> blocked by MIN TRADE GUARD
        tfii_state["positions"] = {"CP.TO": {"shares": 7.0, "acb": 127.00, "current_price": 139.00}}
    with patch.object(maple_ledger, "load_config", return_value=tfii_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_ledger_state", return_value=tfii_state), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={"CP.TO": 1}), \
         patch.object(maple_ledger, "get_position_last_buy_info", return_value={"CP.TO": {"last_buy_dt": now - datetime.timedelta(hours=5), "last_buy_price": 127.00, "shares": 7.0}}), \
         patch.object(maple_ledger, "log_trade"):
        assert maple_ledger.execute_buy("CP.TO", 300.00, 139.00, open_price=136.00) is None, "1-share capped scale-in (<5% NAV) was not blocked"

    stale_yf = {
        "CNQ.TO": {"Price": 78.42, "Bar_Date": "2026-10-30", "Stale_Intraday": True},
        "SAP.TO": {"Price": 40.40, "Bar_Date": "2026-10-30", "Stale_Intraday": True},
    }
    stale_broker = MagicMock()
    stale_broker.is_authenticated.return_value = True
    stale_broker.search_symbol.side_effect = lambda t: {"symbolId": 301 if t == "CNQ.TO" else 302}
    stale_broker.get_quotes.return_value = {
        301: {"lastTradePrice": 78.42, "isDelayed": True},
        302: {"lastTradePrice": 40.95, "isDelayed": False},
    }
    stale_broker.get_quote.side_effect = lambda cid: stale_broker.get_quotes.return_value[cid]
    stale_chop_calls = []
    with patch.object(maple_brain, "load_config", return_value={"trading_mode": "LIVE", "active_targets": {}}), \
         patch.object(maple_brain, "is_market_open", return_value=True), \
         patch.object(maple_brain, "is_opening_chop", return_value=True), \
         patch.object(maple_brain, "get_broker_client", return_value=stale_broker), \
         patch.object(maple_brain, "get_ledger_state", return_value={"positions": {"CNQ.TO": {"shares": 2.0, "acb": 77.04}, "SAP.TO": {"shares": 1.0, "acb": 40.09}}}), \
         patch.object(maple_brain, "get_stock_data", side_effect=lambda t, mode="SHORT": dict(stale_yf[t])), \
         patch.object(maple_brain, "check_target_stops", side_effect=lambda pm, **kw: stale_chop_calls.append(dict(pm))):
        live_mkt = maple_brain.fetch_latest_market_prices(["CNQ.TO", "SAP.TO"])
        assert "CNQ.TO" not in live_mkt and live_mkt.get("SAP.TO", {}).get("Price") == 40.95, f"Stale bar filter failed in fetch_latest_market_prices: {live_mkt}"
        maple_brain.run_chop_exit_guard()
        assert stale_chop_calls == [{"SAP.TO": 40.95}], f"Stale bar filter failed in run_chop_exit_guard: {stale_chop_calls}"

    # 21. Nov 9 Weekly Retrospective Patches: Tier 0.5 Half-Risk Ratchet (+2.0% -> -2.5%), +2.5% Breakeven Trigger,
    #     Post-Stop/Stagnation 4h Re-Entry Cooldown, Capitulation +4.50% Overextension Ceiling, and NAV-Anchored Tranche Sizing
    over_cap, r_over = MapleStrategy.calculate_tranche_size(
        {"RSI_7": 29.9, "Vol_Ratio": 1.83, "Open": 180.00, "Price": 185.00, "Pct_From_Low": 4.92, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
        signal_type="CAPITULATION REVERSAL",
    )
    assert over_cap == 0.0 and "Overextension Filter" in r_over, f"Over-bounced SHOP.TO capitulation not blocked: {over_cap}, {r_over}"

    tier_cfg = {
        "trading_mode": "LIVE",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {
            "CCO.TO": {"target_price": 111.47, "stop_loss_price": 93.99},
            "WCN.TO": {"target_price": 274.77, "stop_loss_price": 250.77},
        },
        "initial_portfolio": {},
    }
    tier_state = {
        "mode": "LIVE",
        "live_verified": True,
        "cash": 1853.20,
        "total_equity": 4993.96,
        "positions": {
            "CCO.TO": {"shares": 5.0, "acb": 98.96, "current_price": 101.00},   # +2.06% (>=2.0%, <2.5%) -> Tier 0.5 Half-Risk (98.96 * 0.975 = 96.49)
            "WCN.TO": {"shares": 2.0, "acb": 264.47, "current_price": 271.50},  # +2.66% (>=2.5%, <3.0%) -> Tier 1 Breakeven (264.47 + 0.50 = 264.97)
        },
    }
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=tier_state), \
         patch.object(maple_ledger, "load_config", return_value=tier_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"CCO.TO": 1, "WCN.TO": 1}), \
         patch.object(maple_ledger, "execute_sell"):
        maple_ledger.check_target_stops({"CCO.TO": 101.00, "WCN.TO": 271.50})
        assert tier_cfg["active_targets"]["CCO.TO"]["stop_loss_price"] == 96.49, f"Tier 0.5 half-risk ratchet failed: {tier_cfg}"
        assert tier_cfg["active_targets"]["WCN.TO"]["stop_loss_price"] == 264.97, f"Tier 1 +2.5% breakeven ratchet failed: {tier_cfg}"

    with patch.object(maple_ledger, "load_config", return_value={"trading_mode": "SIMULATED", "scale_in_cooldown_hours": 4.0, "pending_orders": {}}), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={}), \
         patch.object(maple_ledger, "get_last_loss_exit_info", return_value={"TFII.TO": {"last_exit_dt": now - datetime.timedelta(minutes=45), "last_exit_price": 132.84, "notes": "AUTO STOP-LOSS"}}):
        assert maple_ledger.execute_buy("TFII.TO", 750.0, 135.46, open_price=133.00) is None, "45-min post-stop re-entry was not blocked"

    # 22. Nov 10 Fix: Stale config overwrite guard in check_target_stops when execute_sell + ratchet occur in same pass
    disk_cfg = {
        "trading_mode": "LIVE",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {
            "TFII.TO": {"target_price": 154.56, "stop_loss_price": 130.05},
            "CCO.TO": {"target_price": 111.47, "stop_loss_price": 102.92},
        },
        "initial_portfolio": {},
    }
    def _mock_sell_mutates_disk(tk, px, reason=""):
        disk_cfg["active_targets"].pop(tk, None)
        disk_cfg["pending_orders"]["WORKING_TEST"] = {"order_id": "999"}

    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value={
             "mode": "LIVE",
             "live_verified": True,
             "cash": 1133.72,
             "total_equity": 5041.39,
             "positions": {
                 "TFII.TO": {"shares": 4.0, "acb": 137.14, "current_price": 129.90},
                 "CCO.TO": {"shares": 8.0, "acb": 99.69, "current_price": 104.38},
             },
         }), \
         patch.object(maple_ledger, "load_config", side_effect=lambda: {
             **disk_cfg,
             "active_targets": {k: dict(v) for k, v in disk_cfg["active_targets"].items()},
             "pending_orders": {k: dict(v) for k, v in disk_cfg["pending_orders"].items()},
         }), \
         patch.object(maple_ledger, "save_config", side_effect=lambda c: disk_cfg.update(c)), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"TFII.TO": 5, "CCO.TO": 1}), \
         patch.object(maple_ledger, "execute_sell", side_effect=_mock_sell_mutates_disk):
        maple_ledger.check_target_stops({"TFII.TO": 129.90, "CCO.TO": 104.38})
        assert "TFII.TO" not in disk_cfg["active_targets"], f"Stale config resurrected sold TFII.TO: {disk_cfg}"
        assert disk_cfg["active_targets"]["CCO.TO"]["stop_loss_price"] == 103.08, f"CCO.TO ratchet missing: {disk_cfg}"
        assert "WORKING_TEST" in disk_cfg["pending_orders"], f"Stale config wiped pending_orders: {disk_cfg}"

    # 23. Nov 13 Fixes: Low-volume 1.00x floor & 15% cap, total-CAD fee attribution, Day-3 stagnation warning & near-cap/liquidity alerts
    lv_block, lv_reason = MapleStrategy.calculate_tranche_size(
        {"Price": 116.50, "Open": 115.80, "EMA_5": 116.00, "EMA_9": 115.20, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 0.90, "ADX_14": 40.0, "RSI_7": 58.0},
        signal_type="LOW-VOLUME SCALED ENTRY",
    )
    assert lv_block == 0.0 and "Low Volume" in lv_reason, f"Sub-1.00x low-volume entry not blocked: {lv_block}, {lv_reason}"

    lv_cap, lv_cap_r = MapleStrategy.calculate_tranche_size(
        {"Price": 116.50, "Open": 115.80, "EMA_5": 116.00, "EMA_9": 115.20, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.05, "ADX_14": 40.0, "RSI_7": 58.0},
        signal_type="LOW-VOLUME SCALED ENTRY",
    )
    min_pct_int = int(round(MapleStrategy.MIN_TRANCHE_PCT * 100))
    assert lv_cap == MapleStrategy.MIN_TRANCHE_PCT and f"Capped at {min_pct_int}%" in lv_cap_r, f"Scaled entry exceeded {min_pct_int}% floor: {lv_cap}, {lv_cap_r}"

    with patch.object(maple_optimizer, "get_position_holding_days", return_value={"ENGH.TO": 3}), \
         patch.object(maple_optimizer, "get_position_last_buy_info", return_value={"ENGH.TO": {"fill_acb": 18.60, "shares": 41.0}}):
        engh_attr, engh_watch = maple_optimizer.calculate_position_attribution(
            {"ENGH.TO": {"shares": 41.0, "acb": 18.62439025, "current_price": 18.15}},
            5028.58,
        )
        assert engh_attr[0]["entry_fee_cad"] == 1.00, f"High-share entry fee hidden: {engh_attr}"
        assert engh_watch and "Approaching Day-4 stagnation check tomorrow" in engh_watch[0]["note"], f"Day-3 early stagnation warning missing: {engh_watch}"

    # 24. Nov 13 EOD Fixes: Post-sell ledger refresh in run_intraday_scan, EMA-aware Day-4 watchlist note, and same-day changelog deduplication
    pre_exit_state = {"mode": "SIMULATED", "cash": 388.03, "total_equity": 5022.84, "positions": {"TECK-B.TO": {"shares": 8.0, "acb": 90.0}}}
    post_exit_state = {"mode": "SIMULATED", "cash": 1078.67, "total_equity": 5022.84, "positions": {}}
    seen_held_args = []
    import importlib
    with patch.object(maple_brain, "is_opening_chop", return_value=False), \
         patch.object(maple_brain, "is_market_open", return_value=True), \
         patch.object(maple_brain, "load_config", return_value={"trading_mode": "SIMULATED", "allowed_tickers": ["TECK-B.TO"], "max_position_pct": 0.25}), \
         patch.object(maple_brain, "get_ledger_state", side_effect=[pre_exit_state, post_exit_state, post_exit_state]), \
         patch.object(maple_brain, "fetch_latest_market_prices", return_value={"TECK-B.TO": {"Price": 86.33}}), \
         patch.object(maple_brain, "check_target_stops"), \
         patch.object(maple_brain, "get_macro_alignment", return_value={"GC=F": True, "CL=F": True, "VIX_PANIC": False}), \
         patch.object(importlib, "reload", side_effect=lambda m: m), \
         patch.object(telegram_notifier, "send_scan_update", return_value=True), \
         patch.object(maple_brain, "evaluate_autonomous_signals", side_effect=lambda md, at, macro_state=None, max_share_price=None, held_tickers=None: (seen_held_args.append(set(held_tickers or set())), [])[1]):
        maple_brain.run_intraday_scan()
        assert seen_held_args and seen_held_args[0] == set(), f"Stale pre-exit held_tickers passed to Step 3: {seen_held_args}"

    with patch.object(maple_optimizer, "get_position_holding_days", return_value={"ATRL.TO": 4, "TECK-B.TO": 4}), \
         patch.object(maple_optimizer, "get_position_last_buy_info", return_value={}):
        _, stag_watch = maple_optimizer.calculate_position_attribution(
            {
                "ATRL.TO": {"shares": 6.0, "acb": 91.68, "current_price": 91.23},
                "TECK-B.TO": {"shares": 8.0, "acb": 90.06, "current_price": 86.33},
            },
            5022.84,
            stock_data_map={
                "ATRL.TO": {"EMA_5": 91.10, "EMA_9": 90.40, "EMA_Crossover": "BULLISH (EMA5 > EMA9)"},
                "TECK-B.TO": {"EMA_5": 87.20, "EMA_9": 88.10, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
            },
        )
        watch_map = {w["ticker"]: w["note"] for w in stag_watch}
        assert "retained (Bullish EMA5 > EMA9)" in watch_map["ATRL.TO"], f"Bullish 4d hold mislabeled as stagnant: {watch_map}"
        assert "Stagnant loser" in watch_map["TECK-B.TO"], f"Bearish 4d loser missing stagnant flag: {watch_map}"

    import json, tempfile
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False, encoding="utf-8") as tmpf:
        tmp_path = tmpf.name
        today_pfx = datetime.datetime.now().strftime("%Y-%m-%d")
        tmpf.write(
            f"\n\n### Optimization Log [2026-11-12 16:11:03]\nPrior day entry\n"
            f"\n\n### Optimization Log [{today_pfx} 15:46:30]\nEarly duplicate\n"
        )
    try:
        with patch.object(maple_optimizer, "CHANGELOG_FILE", tmp_path):
            maple_optimizer.log_to_changelog("Final close entry")
        with open(tmp_path, "r", encoding="utf-8") as rf:
            dedup_text = rf.read()
        assert "Prior day entry" in dedup_text and "Early duplicate" not in dedup_text and "Final close entry" in dedup_text, (
            f"Same-day changelog deduplication failed: {dedup_text}"
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # 25. Nov 16 EOD Fixes: Trading-day (weekday) holding count across weekends & accrued dividend capital breakdown
    assert maple_ledger._count_trading_days(
        datetime.datetime(2026, 11, 13, 10, 1, 19),
        datetime.datetime(2026, 11, 16, 16, 11, 4),
    ) == 1, "Friday buy evaluated on Monday should be 1 trading day held, not 3 calendar days"
    assert maple_ledger._count_trading_days(
        datetime.datetime(2026, 11, 12, 10, 15, 45),
        datetime.datetime(2026, 11, 16, 16, 11, 4),
    ) == 2, "Thursday buy evaluated on Monday should be 2 trading days held, not 4 calendar days"
    assert maple_ledger._count_trading_days(
        datetime.datetime(2026, 11, 10, 11, 0, 41),
        datetime.datetime(2026, 11, 16, 16, 11, 4),
    ) == 4, "Tuesday buy evaluated next Monday should be 4 trading days held, not 6 calendar days"

    # 26. Nov 16 Weekly Audit Fixes: ADX >= 15.0 hard trend floor (disallowing Single-Bypass in dead chop) & +3.5% Capitulation target cap
    adx_chop_pct, adx_chop_r = MapleStrategy.calculate_tranche_size(
        {"Price": 89.81, "Open": 88.50, "EMA_5": 89.20, "EMA_9": 88.80, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 2.08, "ADX_14": 9.42, "RSI_7": 55.91},
        signal_type="REGULAR BUY",
    )
    assert adx_chop_pct == 0.0 and "Trend Floor" in adx_chop_r, f"Sub-15 ADX chop was not blocked: {adx_chop_pct}, {adx_chop_r}"

    adx_bypass_pct, adx_bypass_r = MapleStrategy.calculate_tranche_size(
        {"Price": 89.81, "Open": 88.50, "EMA_5": 89.20, "EMA_9": 88.80, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 2.08, "ADX_14": 17.5, "RSI_7": 55.91},
        signal_type="REGULAR BUY",
    )
    assert adx_bypass_pct > 0.0 and "Single-Bypass Rule" in adx_bypass_r, f"Valid 15-20 ADX single-bypass failed: {adx_bypass_pct}, {adx_bypass_r}"

    rus_cap_tgt, rus_cap_stp = MapleStrategy.calculate_targets(
        76.91,
        {"ATR_5": 2.80, "BB_Mid": 80.76, "RSI_7": 27.22},
        shares=10.0,
        cost_basis=76.91,
        signal_type="CAPITULATION REVERSAL",
    )
    assert rus_cap_tgt == 79.60 and rus_cap_stp == 73.06, f"Capitulation target not capped at +3.5%: tgt={rus_cap_tgt}, stp={rus_cap_stp}"

    # 27. US Equities Migration: 53 Zoya-certified US tickers (incl. AVGO, LLY, AMD, PANW, SNPS, CDNS; excluding COST)
    _legacy_tsx_patch.stop()
    _legacy_brain_patch.stop()
    assert len(maple_ledger.SHARIAH_COMPLIANT_BASKET) == 53, f"Expected 53 US tickers, got {len(maple_ledger.SHARIAH_COMPLIANT_BASKET)}"
    assert {"AVGO", "LLY", "AMD", "PANW", "SNPS", "CDNS"}.issubset(maple_ledger.SHARIAH_COMPLIANT_BASKET)
    assert "COST" not in maple_ledger.SHARIAH_COMPLIANT_BASKET, "COST (Zoya questionable) must remain excluded"
    assert maple_ledger.normalize_ticker("NVDA") == "NVDA" and maple_ledger.normalize_ticker("BRK.B") == "BRK-B"
    assert maple_ledger.normalize_ticker("PAAS.TO") == "PAAS.TO"
    assert maple_market.is_macro_aligned("NEM", {"GC=F": False, "CL=F": True, "VIX_PANIC": True})[0] is False
    assert maple_market.is_macro_aligned("XOM", {"GC=F": False, "CL=F": True, "VIX_PANIC": True})[0] is True

    # 28. Strategy Review Upgrades: SMA_50 primary trend gate, clamped ATR stop [3.25%, 5.0%], Ret_20d + SPY<SMA50 filter, and maple_backtest
    sma50_block, sma50_r = MapleStrategy.calculate_tranche_size(
        {"Price": 140.0, "Open": 138.0, "EMA_5": 139.0, "EMA_9": 137.5, "SMA_50": 148.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.4, "ADX_14": 25.0, "RSI_7": 55.0},
        signal_type="REGULAR BUY",
    )
    assert sma50_block == 0.0 and "Primary Trend Gate" in sma50_r, f"Below-SMA50 trend buy was not blocked: {sma50_block}, {sma50_r}"

    _, low_vol_stp = MapleStrategy.calculate_targets(100.0, {"ATR_5": 1.10, "BB_Mid": 104.0}, shares=10.0, cost_basis=100.0)
    assert low_vol_stp == 96.75, f"Low-volatility ATR stop should clamp to -3.25% ($96.75), got {low_vol_stp}"

    rank_mkt = {
        "AAPL": {"Price": 350.0, "Open": 345.0, "EMA_5": 348.0, "EMA_9": 344.0, "SMA_50": 330.0, "Ret_20d": 2.5, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.50, "ADX_14": 30.0, "RSI_7": 55.0},
        "NVDA": {"Price": 155.0, "Open": 152.0, "EMA_5": 154.0, "EMA_9": 151.0, "SMA_50": 140.0, "Ret_20d": 11.2, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.50, "ADX_14": 29.0, "RSI_7": 55.0},
        "TXN": {"Price": 295.0, "Open": 292.0, "EMA_5": 294.0, "EMA_9": 291.0, "SMA_50": 285.0, "Ret_20d": 4.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.60, "ADX_14": 17.5, "RSI_7": 55.0},
        "NKE": {"Price": 36.20, "Open": 35.50, "Pct_From_Low": 2.50, "EMA_5": 37.0, "EMA_9": 38.0, "SMA_50": 42.0, "Ret_20d": -10.0, "EMA_Crossover": "BEARISH (EMA5 < EMA9)", "Vol_Ratio": 1.60, "ADX_14": 28.0, "RSI_7": 26.0},
    }
    ranked_sigs = maple_brain.evaluate_autonomous_signals(
        rank_mkt, {"AAPL", "NVDA", "TXN", "NKE"}, macro_state={"GC=F": True, "CL=F": True, "VIX_PANIC": False, "SPY_BELOW_SMA50": True}
    )
    assert [s["ticker"] for s in ranked_sigs] == ["NVDA", "AAPL"], f"Ret_20d tie-breaker or SPY_BELOW_SMA50 gate (Single-Bypass/Capitulation) failed: {ranked_sigs}"
    cap_above_spy = maple_brain.evaluate_autonomous_signals(
        rank_mkt, {"NKE"}, macro_state={"GC=F": True, "CL=F": True, "VIX_PANIC": False, "SPY_BELOW_SMA50": False}
    )
    assert [s["ticker"] for s in cap_above_spy] == ["NKE"], f"Capitulation Reversal should pass when SPY >= 50-SMA: {cap_above_spy}"

    elev_sigs = maple_brain.evaluate_autonomous_signals(
        rank_mkt, {"AAPL"}, macro_state={"GC=F": True, "CL=F": True, "VIX_ELEVATED": True, "VIX_PANIC": False, "SPY_BELOW_SMA50": False}
    )
    calm_sigs = maple_brain.evaluate_autonomous_signals(
        rank_mkt, {"AAPL"}, macro_state={"GC=F": True, "CL=F": True, "VIX_ELEVATED": False, "VIX_PANIC": False, "SPY_BELOW_SMA50": False}
    )
    assert len(elev_sigs) == 1 and elev_sigs[0]["tranche_pct"] == round(calm_sigs[0]["tranche_pct"] * 0.5, 4) and "0.5x VIX Elevated" in elev_sigs[0]["rationale"], f"VIX_ELEVATED half-size failed: {elev_sigs}"

    with patch.object(maple_optimizer, "get_ledger_state", return_value={"positions": {}}), \
         patch.object(maple_optimizer, "get_stock_data", return_value={"Price": 170.59, "Prev_Close": 166.43, "Open": 167.21, "Pct_From_Low": 2.16, "RSI_7": 61.03, "Vol_Ratio": 1.31, "ADX_14": 30.4, "EMA_5": 168.58, "EMA_9": 168.36, "SMA_50": 157.74, "EMA_Crossover": "BULLISH (EMA5 > EMA9)"}):
        vix_movers = maple_optimizer.scan_missed_opportunities(["GILD"], macro_state={"VIX_PANIC": True})
        assert len(vix_movers) == 1 and vix_movers[0]["eligible"] is False and "Macro Filter" in vix_movers[0]["gate_status"], f"VIX-blocked mover falsely marked eligible: {vix_movers}"

    # 29. Idle-Cash SPUS Sweep: bypasses 35% cap & stop-loss, supports partial unwind
    with patch.object(maple_ledger, "load_config", return_value={"trading_mode": "SIMULATED", "max_position_pct": 0.35, "max_sector_pct": 0.35, "pending_orders": {}, "active_targets": {}}), \
         patch.object(maple_ledger, "save_config") as mock_save, \
         patch.object(maple_ledger, "get_ledger_state", return_value={"cash": 8000.0, "total_equity": 9000.0, "positions": {}}), \
         patch.object(maple_ledger, "log_trade"):
        sp_buy = maple_ledger.execute_buy("SPUS", 7000.0, 50.0, notes="[IDLE-CASH SWEEP]")
        assert sp_buy is not None and sp_buy["shares"] == 140 and mock_save.call_count == 0, f"SPUS sweep buy failed: {sp_buy}"
    with patch.object(maple_ledger, "load_config", return_value={"trading_mode": "SIMULATED", "pending_orders": {}, "active_targets": {}}), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_ledger_state", return_value={"cash": 1000.0, "total_equity": 8000.0, "positions": {"SPUS": {"shares": 140.0, "acb": 50.0}}}), \
         patch.object(maple_ledger, "log_trade") as mock_log:
        sp_sell = maple_ledger.execute_sell("SPUS", 51.0, reason="Sweep Unwind", shares_to_sell=30)
        assert sp_sell is not None and sp_sell["shares"] == 30 and mock_log.call_args[0][4] == 110.0, f"SPUS partial unwind failed: {sp_sell}"
    with patch.object(maple_ledger, "sync_working_orders"), \
         patch.object(maple_ledger, "load_config", return_value={"trading_mode": "SIMULATED", "active_targets": {}, "initial_portfolio": {}}), \
         patch.object(maple_ledger, "get_ledger_state", return_value={"cash": 1000.0, "total_equity": 7000.0, "positions": {"SPUS": {"shares": 140.0, "acb": 50.0}}}), \
         patch.object(maple_ledger, "execute_sell") as mock_stop_sell:
        maple_ledger.check_target_stops({"SPUS": 40.0})
        assert mock_stop_sell.call_count == 0, "check_target_stops should never stop out SPUS sweep ETF"

    import maple_backtest
    assert callable(maple_backtest.run_backtest) and maple_backtest.run_backtest({})["trades"] == 0

    # 30. Nov 25 Execution & Safety Hardening (Items 1-8):
    # (1) Profit-locked stop preserved on scale-in when blended gain >= +2.5%
    pg_scale_cfg = {"active_targets": {"PG": {"target_price": 112.0, "stop_loss_price": 104.68}}}
    assert maple_ledger._resolve_buy_stop(pg_scale_cfg, "PG", 96.90, 106.00, 4.0, blended_acb=102.00) == 104.68

    # (2) Partial-fill terminal cleanup in sync_working_orders + SWEEP_ETF excluded from active_targets
    pf_broker = MagicMock()
    pf_broker.is_authenticated.return_value = True
    pf_broker.get_order_status.side_effect = [
        {"order_status": "Inactive", "cum_fill": 4, "average_price": 98.50},
        {"order_status": "Filled", "cum_fill": 20, "average_price": 54.10},
    ]
    pf_broker.get_balances.return_value = {}  # Also verifies empty get_balances fallback
    pf_broker.get_positions.return_value = [{"symbol": "KO", "openQuantity": 4}, {"symbol": "SPUS", "openQuantity": 20}]
    pf_cfg = {
        "trading_mode": "LIVE",
        "account_id": "U12345678",
        "commission_per_order_cad": 1.0,
        "pending_orders": {
            "KO": {"order_id": "301", "action": "BUY", "shares": 10, "existing_shares": 0, "acb": 0.0, "limit_price": 98.50, "cash_before": 1000.0, "target_price": 102.0, "stop_loss_price": 95.30, "stock_data": {"ATR_5": 1.1, "BB_Mid": 100.0}, "signal_type": "REGULAR BUY"},
            "SPUS": {"order_id": "302", "action": "BUY", "shares": 20, "existing_shares": 0, "acb": 0.0, "limit_price": 54.10, "cash_before": 2000.0},
        },
        "active_targets": {},
    }
    pf_logs = []
    with patch.object(maple_ledger, "load_config", return_value=pf_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_broker_client", return_value=pf_broker), \
         patch.object(maple_ledger, "log_trade", side_effect=lambda *a, **kw: pf_logs.append(a)), \
         patch.object(telegram_notifier, "send_trade_alert", return_value=True):
        rem_pend = maple_ledger.sync_working_orders()
    assert rem_pend == {} and "KO" in pf_cfg["active_targets"] and "SPUS" not in pf_cfg["active_targets"], f"Partial-fill sync bug: {pf_cfg}"
    assert pf_logs[0][2] == 4 and pf_logs[0][5] == 605.0, f"Partial fill qty or empty-balance cash fallback wrong: {pf_logs[0]}"

    # (3) LIVE fail-closed abort + circuit breaker alert (never send fake scan update on CSV fallback)
    breaker_alerts, fake_scans = [], []
    with patch.object(maple_brain, "load_config", return_value={"trading_mode": "LIVE", "allowed_tickers": ["AAPL"]}), \
         patch.object(maple_brain, "is_opening_chop", return_value=False), \
         patch.object(maple_brain, "is_market_open", return_value=True), \
         patch.object(maple_brain, "get_ledger_state", return_value={"mode": "SIMULATED", "live_verified": False, "live_fallback": True, "live_error": "401 unauthenticated", "cash": 900.0, "positions": {}}), \
         patch.object(telegram_notifier, "send_circuit_breaker_alert", side_effect=lambda *a, **kw: breaker_alerts.append(a) or True), \
         patch.object(telegram_notifier, "send_scan_update", side_effect=lambda *a, **kw: fake_scans.append(a) or True):
        halt_res = maple_brain.run_intraday_scan()
    assert halt_res["status"] == "BROKER_UNAVAILABLE" and len(breaker_alerts) == 1 and fake_scans == [], f"LIVE fail-closed failed: {halt_res}"

    # (5) IBKR replyId guard blocks margin/GFV prompts while allowing benign price-cap prompts
    ib_guard = ibkr_client.IBKRClient.__new__(ibkr_client.IBKRClient)
    ib_guard.base_url = "https://localhost:5000/v1/api"
    ib_guard.session = MagicMock()
    ib_guard.session.post.side_effect = [
        MagicMock(json=lambda: [{"id": "r_gfv", "message": ["Cash account Good Faith Violation warning"]}]),
        MagicMock(json=lambda: {"confirmed": False}),
    ]
    gfv_res = ib_guard.place_limit_order("U123", 265598, "Buy", 1, 200.0)
    assert gfv_res["orderId"] is None and "Good Faith" in gfv_res.get("rejected_reason", ""), f"Unsafe GFV prompt not blocked: {gfv_res}"

    ib_guard.session.post.side_effect = [
        MagicMock(json=lambda: [{"id": "r_cap", "message": ["Order price exceeds Percentage constraint of 3%"]}]),
        MagicMock(json=lambda: [{"order_id": "987654"}]),
    ]
    ok_res = ib_guard.place_limit_order("U123", 265598, "Buy", 1, 200.0)
    assert ok_res["orderId"] == "987654", f"Benign price-cap prompt failed to confirm: {ok_res}"

    # (6) NYSE holiday (Thanksgiving 2026-11-26) & 1:00 PM early close (Black Friday 2026-11-27, Dec 24)
    assert maple_market.is_nyse_holiday(datetime.date(2026, 11, 26)) is True
    assert maple_market.is_nyse_trading_day(datetime.date(2026, 11, 26)) is False
    assert maple_ledger._count_trading_days(datetime.datetime(2026, 11, 25, 10, 0), datetime.datetime(2026, 11, 27, 10, 0)) == 1
    assert maple_market.is_nyse_early_close(datetime.date(2026, 11, 27)) is True
    assert maple_market.get_nyse_close_hour_min(datetime.date(2026, 11, 27)) == (13, 0)
    assert maple_market.get_nyse_close_hour_min(datetime.date(2026, 12, 24)) == (13, 0)

    # (7) Held position removed from allowed_tickers still fetched for stop/target protection
    fetched_lists = []
    orphan_state = {"mode": "SIMULATED", "cash": 5000.0, "total_equity": 6000.0, "positions": {"NKE": {"shares": 10.0, "acb": 36.0}}}
    with patch.object(maple_brain, "is_opening_chop", return_value=False), \
         patch.object(maple_brain, "is_market_open", return_value=True), \
         patch.object(maple_brain, "load_config", return_value={"trading_mode": "SIMULATED", "allowed_tickers": ["AAPL"], "idle_cash_sweep": False}), \
         patch.object(maple_brain, "get_ledger_state", return_value=orphan_state), \
         patch.object(maple_brain, "fetch_latest_market_prices", side_effect=lambda tks: (fetched_lists.append(list(tks)), {"AAPL": {"Price": 350.0}, "NKE": {"Price": 34.0}})[1]), \
         patch.object(maple_brain, "check_target_stops"), \
         patch.object(maple_brain, "get_macro_alignment", return_value={"GC=F": True, "CL=F": True, "VIX_PANIC": False}), \
         patch.object(importlib, "reload", side_effect=lambda m: m), \
         patch.object(telegram_notifier, "send_scan_update", return_value=True):
        maple_brain.run_intraday_scan()
    assert fetched_lists and set(fetched_lists[0]) == {"AAPL", "NKE"}, f"Removed held ticker NKE omitted from quote fetch: {fetched_lists}"

    # (8) Post-fill target_price & ATR stop recomputed from actual filled share count and price
    recomp_cfg = {"trading_mode": "SIMULATED", "commission_per_order_cad": 1.0, "min_net_profit_pct": 2.5, "max_single_share_nav_pct": 0.30, "pending_orders": {}, "active_targets": {}}
    with patch.object(maple_ledger, "load_config", return_value=recomp_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_ledger_state", return_value={"cash": 1000.0, "total_equity": 1000.0, "positions": {}}), \
         patch.object(maple_ledger, "get_position_buy_counts", return_value={}), \
         patch.object(maple_ledger, "log_trade"):
        # Pre-fill passed target_price=102.90 (assuming 5 shs -> $0.40/sh comm), but allocated $100 buys 1 share -> must recompute to $104.50 ($100 + $2 comm + $2.50)
        maple_ledger.execute_buy("KO", 100.0, 100.0, target_price=102.90, stock_data={"ATR_5": 1.0, "BB_Mid": 99.0}, signal_type="REGULAR BUY")
    assert recomp_cfg["active_targets"]["KO"] == {"target_price": 104.50, "stop_loss_price": 96.75}, f"Post-fill target/ATR-stop recompute failed: {recomp_cfg}"

    # 31. Strategy Expectancy Upgrades: SMA_200 Capitulation guard, ATR_14 [3.0%, 7.5%] + 2.5x uncapped trend target, Ret_63d ranking & R-multiple ratchets
    nke_cap_block, nke_cap_r = MapleStrategy.calculate_tranche_size(
        {"Price": 36.0, "Open": 35.2, "Pct_From_Low": 2.4, "RSI_7": 28.0, "Vol_Ratio": 1.6, "SMA_200": 48.0, "EMA_Crossover": "BEARISH (EMA5 < EMA9)"},
        signal_type="CAPITULATION REVERSAL",
    )
    assert nke_cap_block == 0.0 and "SMA_200" in nke_cap_r, f"Below-SMA200 capitulation knife-catch not blocked: {nke_cap_block}, {nke_cap_r}"

    # High-beta stock ($100, ATR_14=$4.00 -> 2.2*ATR=8.8% clamped to 7.5% -> stop $92.50; trend target ignores BB_Mid=$103.50 and sets $100 + 2.5*$4 = $110.00)
    hb_tgt, hb_stp = MapleStrategy.calculate_targets(
        100.0, {"ATR_14": 4.00, "ATR_5": 3.80, "BB_Mid": 103.50, "RSI_7": 55.0}, shares=10.0, cost_basis=100.0, signal_type="REGULAR BUY"
    )
    assert hb_tgt == 110.00 and hb_stp == 92.50, f"ATR_14 uncapped target / 7.5% stop clamp mismatch: tgt={hb_tgt}, stp={hb_stp}"

    # R-multiple ratchet: 1R = $7.50 ($100 ACB, $92.50 init_stop). At +3.5% ($103.50 = +0.47R), MUST NOT prematurely breakeven-ratchet; at +1.1R ($108.25), ratchets to comm breakeven ($100.10)
    r_cfg = {
        "trading_mode": "LIVE",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {"NVDA": {"target_price": 118.75, "stop_loss_price": 92.50, "initial_stop_price": 92.50}},
        "initial_portfolio": {},
    }
    r_state = {"mode": "LIVE", "live_verified": True, "cash": 5000.0, "total_equity": 6035.0, "positions": {"NVDA": {"shares": 10.0, "acb": 100.0, "current_price": 103.50}}}
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=r_state), \
         patch.object(maple_ledger, "load_config", return_value=r_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"NVDA": 1}), \
         patch.object(maple_ledger, "execute_sell"):
        maple_ledger.check_target_stops({"NVDA": 103.50}, market_data={"NVDA": {"ATR_14": 4.0}})
        assert r_cfg["active_targets"]["NVDA"]["stop_loss_price"] == 92.50, f"+0.47R noise move should not choke high-beta trade: {r_cfg}"
        maple_ledger.check_target_stops({"NVDA": 108.25}, market_data={"NVDA": {"ATR_14": 4.0}})
        assert r_cfg["active_targets"]["NVDA"]["stop_loss_price"] == 100.10, f"+1.10R move should ratchet to comm breakeven ($100.10): {r_cfg}"

    # Ret_63d leader ranking prioritizes sustained 3-month RS leader over single-day volume spike in laggard
    rs_mkt = {
        "CSCO": {"Price": 60.0, "Open": 59.0, "EMA_5": 59.5, "EMA_9": 58.8, "SMA_50": 56.0, "Ret_63d": 4.0, "Ret_20d": 2.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.55, "ADX_14": 30.0, "RSI_7": 55.0},
        "ANET": {"Price": 110.0, "Open": 108.0, "EMA_5": 109.0, "EMA_9": 107.5, "SMA_50": 98.0, "Ret_63d": 24.5, "Ret_20d": 9.0, "EMA_Crossover": "BULLISH (EMA5 > EMA9)", "Vol_Ratio": 1.35, "ADX_14": 30.0, "RSI_7": 55.0},
    }
    rs_sigs = maple_brain.evaluate_autonomous_signals(rs_mkt, {"CSCO", "ANET"}, macro_state={"GC=F": True, "CL=F": True})
    assert [s["ticker"] for s in rs_sigs] == ["ANET", "CSCO"], f"Ret_63d RS ranking failed: {rs_sigs}"

    # 32. Variant D (STAGE2_RS) Multi-Week Swing: Top-RS Stage-2 entry, uncapped target, intraday dip immunity & EOD SMA_50/EMA_21 exits
    s2_mkt = {
        "AVGO": {"Price": 205.0, "Open": 202.0, "EMA_21": 198.0, "SMA_50": 185.0, "SMA_50_Rising": True, "SMA_200": 155.0, "RSI_14": 62.0, "ATR_14": 5.0, "RS_Score": 28.4},
        "LLY": {"Price": 840.0, "Open": 832.0, "EMA_21": 815.0, "SMA_50": 780.0, "SMA_50_Rising": True, "SMA_200": 700.0, "RSI_14": 59.0, "ATR_14": 18.0, "RS_Score": 22.1},
        "NKE": {"Price": 70.0, "Open": 69.0, "EMA_21": 68.0, "SMA_50": 72.0, "SMA_50_Rising": False, "SMA_200": 82.0, "RSI_14": 48.0, "ATR_14": 2.0, "RS_Score": -12.0},
    }
    s2_sigs = maple_brain.evaluate_autonomous_signals(
        s2_mkt, {"AVGO", "LLY", "NKE"}, macro_state={"GC=F": True, "CL=F": True}, strategy_mode="STAGE2_RS"
    )
    assert [s["ticker"] for s in s2_sigs] == ["AVGO", "LLY"] and all(s["tranche_pct"] == 0.20 for s in s2_sigs), f"Variant D Stage-2 signals mismatch: {s2_sigs}"
    s2_tgt, s2_stp = MapleStrategy.calculate_targets(205.0, s2_mkt["AVGO"], shares=10.0, cost_basis=205.0, signal_type="STAGE2_RS")
    assert s2_tgt is None and s2_stp == 191.0, f"Variant D should have uncapped target (None) & 2.8x ATR hard stop ($191.00), got {s2_tgt}, {s2_stp}"

    s2_sells = []
    s2_cfg = {
        "trading_mode": "LIVE",
        "strategy_mode": "STAGE2_RS",
        "commission_per_order_cad": 1.0,
        "pending_orders": {},
        "active_targets": {"AVGO": {"strategy_mode": "STAGE2_RS", "target_price": None, "stop_loss_price": 191.0, "peak_price": 240.0, "initial_stop_price": 191.0}},
        "initial_portfolio": {},
    }
    s2_state = {"mode": "LIVE", "live_verified": True, "cash": 4000.0, "total_equity": 8700.0, "positions": {"AVGO": {"shares": 20.0, "acb": 200.0, "current_price": 235.0}}}
    with patch.object(maple_ledger, "sync_working_orders", return_value={}), \
         patch.object(maple_ledger, "get_ledger_state", return_value=s2_state), \
         patch.object(maple_ledger, "load_config", return_value=s2_cfg), \
         patch.object(maple_ledger, "save_config"), \
         patch.object(maple_ledger, "get_position_holding_days", return_value={"AVGO": 12}), \
         patch.object(maple_ledger, "execute_sell", side_effect=lambda t, p, reason="": s2_sells.append((t, p, reason))):
        # Mid-day dip below EMA_21 ($238) while above catastrophic stop ($221) MUST NOT exit intraday (is_eod_window=False)
        maple_ledger.check_target_stops({"AVGO": 235.0}, market_data={"AVGO": {"EMA_21": 238.0, "SMA_50": 215.0, "ATR_14": 5.0}}, is_eod_window=False, top_keep_tickers={"AVGO"})
        assert s2_sells == [], f"Variant D exited prematurely on mid-day EMA_21 dip: {s2_sells}"
        # Near close (is_eod_window=True) at +17.5% (>= +15% profit harvest) with Close < EMA_21 -> harvests winner cleanly!
        maple_ledger.check_target_stops({"AVGO": 235.0}, market_data={"AVGO": {"EMA_21": 238.0, "SMA_50": 215.0, "ATR_14": 5.0}}, is_eod_window=True, top_keep_tickers={"AVGO"})
        assert len(s2_sells) == 1 and "AUTO STAGE-2 EMA_21 EXIT" in s2_sells[0][2], f"Variant D EOD profit harvest failed: {s2_sells}"

    # 33. Optimizer STAGE2_RS parity: Top-N RS rank + SPY<SMA50&200 macro filter + RSI_14 + no 4d stagnation flag on STAGE2_RS holdings
    opt_sd = {
        "AAPL": {"Price": 210.0, "Prev_Close": 205.0, "Open": 206.0, "Pct_From_Low": 3.0, "EMA_21": 202.0, "SMA_50": 195.0, "SMA_50_Rising": True, "SMA_200": 180.0, "RSI_14": 61.5, "RSI_7": 68.2, "Vol_Ratio": 1.2, "RS_Score": 15.0},
        "CSX": {"Price": 36.0, "Prev_Close": 35.0, "Open": 35.2, "Pct_From_Low": 3.2, "EMA_21": 35.0, "SMA_50": 34.0, "SMA_50_Rising": True, "SMA_200": 32.0, "RSI_14": 55.4, "RSI_7": 59.1, "Vol_Ratio": 1.3, "RS_Score": 3.8},
    }
    with patch.object(maple_optimizer, "get_ledger_state", return_value={"positions": {}}), \
         patch.object(maple_optimizer, "load_config", return_value={"strategy_mode": "STAGE2_RS", "rs_top_n": 1, "active_targets": {}}):
        missed_s2 = maple_optimizer.scan_missed_opportunities(
            ["AAPL", "CSX"],
            macro_state={"GC=F": True, "CL=F": True, "SPY_BELOW_SMA50": True, "SPY_BELOW_SMA200": True},
            stock_data_map=opt_sd,
        )
    by_tk = {m["ticker"]: m for m in missed_s2}
    assert by_tk["AAPL"]["eligible"] is False and "SPY below both 50-SMA and 200-SMA" in by_tk["AAPL"]["gate_status"] and by_tk["AAPL"]["rsi"] == 61.5
    assert by_tk["CSX"]["eligible"] is False and "RS Rank Filter: Rank #2 outside Top 1" in by_tk["CSX"]["gate_status"]

    with patch.object(maple_optimizer, "get_position_holding_days", return_value={"AVGO": 6, "KO": 6}), \
         patch.object(maple_optimizer, "get_position_last_buy_info", return_value={}), \
         patch.object(maple_optimizer, "load_config", return_value={"active_targets": {"AVGO": {"strategy_mode": "STAGE2_RS", "stop_loss_price": 190.0}, "KO": {"stop_loss_price": 93.5}}}):
        _, wl_s2 = maple_optimizer.calculate_position_attribution(
            {
                "AVGO": {"shares": 5.0, "acb": 200.0, "current_price": 198.0, "stop_loss_price": 190.0},
                "KO": {"shares": 10.0, "acb": 98.0, "current_price": 97.2, "stop_loss_price": 93.5},
            },
            5000.0,
        )
    wl_map = {w["ticker"]: w["note"] for w in wl_s2}
    assert "AVGO" not in wl_map and "Stagnant loser" in wl_map.get("KO", ""), f"STAGE2_RS stagnation watchlist scoping failed: {wl_map}"

    print("ALL 33 RISK GUARD, POST-MORTEM & STANDALONE ISOLATION CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_checks()
