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

    # 2. Full 32-ticker sector map + 35% sector cap (including resting BUY pending_orders)
    assert set(maple_ledger.SECTOR_MAP.keys()) == maple_ledger.SHARIAH_COMPLIANT_BASKET
    assert all(maple_ledger.get_ticker_sector(t) != "Other" for t in maple_ledger.SHARIAH_COMPLIANT_BASKET)

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
    now = datetime.datetime.now()
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

    # 15. Oct 28 Retrospective Patches: TSX pre-MOC volume curve, whole-share round-up, max_share_price filter, unfiltered mover & fee audit
    assert 0.25 <= maple_market._expected_intraday_vol_fraction(150.0) <= 0.28
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

    print("ALL 15 RISK GUARD, POST-MORTEM & STANDALONE ISOLATION CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_checks()
