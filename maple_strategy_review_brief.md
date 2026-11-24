# MAPLE Strategy Review & Upgrade Brief (Benchmark vs. Leading GitHub Swing Bots)

**Purpose of this document:**  
Provide a complete, code-accurate technical brief of MAPLE's current swing-trading architecture alongside patterns observed in leading open-source GitHub stock swing-trading bots. Another model or engineer should use this brief to review trade-offs, identify blind spots, and recommend a prioritized, testable implementation plan.

---

## 1. Current MAPLE System Snapshot

- **Universe & Account:** 47 Shariah-compliant US equities (`AAPL` through `NEM` in `maple_config.json` -> `allowed_tickers`), `account_currency: "USD"`, live execution via Interactive Brokers (`IBKR` Client Portal Gateway).
  - *Note:* Several older docstrings/comments (`maple_brain.py`, `maple_market.py`, `maple_optimizer.py`) and pre-migration changelog entries still reference `"32 TSX"`; `maple_config.json` is the live source of truth (47 US tickers, USD).
- **Risk & Sizing Parameters (`maple_config.json`):**
  - `stop_loss_pct`: `5.0%` | `chop_stop_buffer_pct`: `2.0%` (9:30–10:00 AM ET)
  - `sizing_parameters`: `min_tranche_pct: 0.15`, `base_tranche_pct: 0.15`, `max_tranche_pct: 0.20`
  - `max_position_pct`: `0.25` | `max_sector_pct`: `0.35` | `max_single_share_nav_pct`: `0.30`
  - `daily_loss_limit_pct`: `0.04` (`daily_loss_limit_cad`: `40.0`)
  - `commission_per_order_cad`: `1.0` | `min_net_profit_pct`: `2.5%` | `scale_in_cooldown_hours`: `4.0`

### 1.1 Entry Logic (`maple_market.py`, `maple_strategy.py`, `maple_brain.py`)
MAPLE runs two entry paths on daily bars overlaid with live intraday quotes:

1. **Capitulation Reversal Path (`CAPITULATION REVERSAL`):**
   - `RSI_7 < 35.0` AND `Vol_Ratio >= 1.25x` (intraday pace-adjusted vs. 10-day SMA)
   - Intraday green candle: `Price > Open`
   - Rebound off intraday low (`Pct_From_Low`) between `1.50%` and `4.50%`
   - Capped at `15%` tranche (`min(MIN_TRANCHE_PCT, CAPITULATION_MAX_TRANCHE_PCT)`), target `+3.5%`.
2. **Regular Trend / Low-Volume Scaled Path (`REGULAR BUY` / `LOW-VOLUME SCALED ENTRY`):**
   - **Gate A (6-part EMA Crossover):** `EMA_5 > EMA_9`, `Price >= EMA_5`, `EMA_5 > prev_EMA_5`, `DMP_14 > DMN_14`, `(Price - EMA_5) / EMA_5 <= 3.0%`, and not `sma50_ceiling` (`EMA_9 < SMA_50` and within `1.5%` of `SMA_50`).
   - **Gate A2 (Intraday Red-Candle Guard):** `Price > Open`.
   - **Gate C (RSI / ADX / Volume):** `RSI_7 <= 68.0`, `Vol_Ratio >= 1.00x`, `ADX_14 >= 15.0`. Cannot bypass both `ADX_14 < 20.0` and `RSI_7 > 65.0`; a single bypass requires `Vol_Ratio >= 1.50x` and caps tranche at `base_tranche_pct` (`15%`).
3. **Global Entry Filters:**
   - **Earnings Blackout:** Blocked if `0 <= trading_days_to_earnings <= 3`.
   - **Macro Alignment (`maple_market.py`):** Gold tickers (`NEM`, `FCX`, etc.) require `GC=F >= prior close`; Oil tickers (`XOM`, `CVX`, `COP`, `EOG`, `SLB`) require `CL=F >= prior close`; all non-commodity buys are blocked if `^VIX >= 25.0` or `^VIX` spikes `>= +10%` on the day.
4. **Candidate Ranking (`maple_brain.py` -> `evaluate_autonomous_signals`):**
   - Passing candidates are sorted by `(tranche_pct, Vol_Ratio, ADX_14)` descending.

### 1.2 Exit & Risk Management (`maple_strategy.py`, `maple_ledger.py`)
- **Initial Stop & Target (`calculate_targets`):**
  - Stop-loss: flat `-5.0%` below cost basis (widened by an extra `1%` if `0 <= days_to_ex_dividend <= 3`).
  - Target: `+3.5%` for capitulation; otherwise `BB_Mid` (20-period) if `>= min_target`, else `base_price + 1.5 * ATR_5`, else `+3.5%`, floored at `base_price + roundtrip_comm_per_share + 2.5%`.
- **Multi-Tier Stop Ratchet (`check_target_stops`):**
  - `+2.0%` unrealized gain -> Half-Risk stop at `-2.5%` below ACB.
  - `+2.5%` gain (or `>= 75%` to target, or `+0.3%` within 3 trading days of earnings) -> Commission-adjusted Breakeven stop.
  - `+3.0%` gain (or `>= 75%` to target) -> Profit-Lock stop at `+1.5%` net above breakeven.
  - `+4.0%` gain -> Trailing stop at `1.25%` below live price.
- **Opening-Chop Guard:** Between 9:30–10:00 AM ET, buys are blocked and stops are buffered downward by `chop_stop_buffer_pct` (`2.0%`).
- **Stagnation Exit:** `STAGNATION_DAYS = 4` (bearish/stagnant positions exited after 4 days).
- **Execution Mechanism:** Polling-based limit orders evaluated in Python (`check_target_stops`), rather than resting server-side bracket orders at IBKR.

---

## 2. Benchmark GitHub Swing Bots Compared
The comparison drew from the most relevant open-source Python stock swing-trading repositories and strategy frameworks:
- **`fja05680/pinkfish`** (~309 stars): Daily equity backtester implementing Connors-style mean reversion (e.g., RSI-2 / Double 7s) and momentum rotation with 200-SMA regime filters.
- **`abzdel/Swing-Trading-Stock-Bot`** (~50 stars) & **`chand1012/stonks`**: Alpaca-based US equity pullback bots (200-SMA uptrend filter, 50-SMA pullback entries, 0.5%–1.0% account risk per trade, bracket orders).
- **`kevmyung/swing-trading-agent`** (~26 stars): Deterministic Quant Engine + multi-agent workflow featuring market regime classification, ATR-based stops, volatility-adjusted sizing, and momentum/mean-reversion z-scores.
- **`CanJee/trading-bot`**: IBKR + `yfinance` US equity swing bot using composite scoring, server-side IBKR bracket orders, and 7-day rolling indicator weight evaluation.
- **`axidzz/Qullamaggie-Setups`**: Relative-strength momentum scanner (1m/3m/6m leaders consolidating near rising MAs).

---

## 3. Identified Opportunities & Gaps to Evaluate

### Opportunity A: Long-Term Trend Filter (`SMA_200`) & Pullback "Missing Middle"
- **Gap in MAPLE:** MAPLE checks `EMA_5 > EMA_9` and blocks near `SMA_50` when `EMA_9 < SMA_50`, but **never checks `SMA_200` (or `SMA_50 > SMA_200`)**. It can therefore buy short-term 5/9 EMA bounces inside a primary downtrend. Meanwhile, Gate A2 (`Price > Open`) + `EMA_5 > EMA_9` forces Regular entries onto green momentum days, while Capitulation requires `RSI_7 < 35` + `1.25x` volume + `+1.5%` rebound. Healthy pullbacks in Stage-2 uptrends (`Price > SMA_50 > SMA_200`, `RSI_7` in `35–48`, normal volume) are skipped entirely.
- **Questions for Review:**
  1. Should `Price > SMA_200` be a hard gate for Regular Trend buys, or a sizing/score penalty (e.g., cap at `min_tranche_pct` below `SMA_200`)?
  2. Should MAPLE add a 3rd entry archetype (**Uptrend Pullback**: `Price > SMA_200`, `EMA_9 > SMA_50`, `RSI_7` 35–48, near `EMA_9`/`SMA_20` support) without relaxing Gate A2 on weak stocks?

### Opportunity B: ATR-Normalized Stops & Risk-Parity Position Sizing
- **Gap in MAPLE:** MAPLE uses a **flat `-5.0%` stop-loss** for all 47 US stocks (`calculate_targets` only uses `ATR_5` as a target fallback) and fixed `15%–20%` NAV tranches. Across a basket spanning low-volatility defensives (`KO`, `PG`, `JNJ`) and high-beta tech/metals (`NVDA`, `TSLA`, `CRWD`, `MRVL`, `NEM`), a flat 5% stop is ~3–4x ATR on defensives (oversized risk) and ~1x ATR on high-beta names (noise stop-outs).
- **Questions for Review:**
  1. Should initial stop-loss be `clamp(k * ATR_14, min_stop_pct, max_stop_pct)` (e.g., `2.0 * ATR_14` clamped to `[3.0%, 6.5%]`)?
  2. Should tranche size be computed via fixed account risk (`risk_budget_usd / stop_distance_pct`, capped by `max_position_pct` and `max_tranche_pct`) so every trade risks ~`0.75%–1.0%` of NAV regardless of volatility?
  3. Note small-account constraints (`current_cash` / `max_single_order_cad` / whole-share rounding on high-priced names like `ISRG`, `COST`, `LRCX`, `ADBE`, `SHW`).

### Opportunity C: Relative Strength Ranking vs. Volume/ADX Ranking
- **Gap in MAPLE:** `evaluate_autonomous_signals` ranks passing setups by `(tranche_pct, Vol_Ratio, ADX_14)`. Leading momentum bots rank by **multi-horizon relative strength** (e.g., 20-day / 63-day return vs. `SPY`, or Sharpe/z-score) so capital concentrates in sustained leaders rather than single-day volume spikes in laggards.
- **Questions for Review:**
  1. How should a 20d/63d Relative Strength (RS) score vs. `SPY` be weighted alongside `Vol_Ratio` and `ADX_14` in candidate ranking?

### Opportunity D: US Market Regime Filter Beyond `^VIX >= 25`
- **Gap in MAPLE:** `get_macro_alignment` only gates non-commodity buys when `^VIX >= 25` or `^VIX` jumps `>= +10%`. In slow, grinding US equity corrections (`VIX` 17–23), MAPLE stays fully offensive.
- **Questions for Review:**
  1. Should MAPLE add a `SPY` / `QQQ` trend & breadth regime (e.g., `SPY < SMA_50` or `< 35%` of the 47-stock basket above `SMA_20`) to shift into defensive mode (halved max exposure, higher RSI/volume bar, or Capitulation-only)?

### Opportunity E: Historical Walk-Forward Backtester
- **Gap in MAPLE:** `maple_optimizer.py` performs daily/weekly live attribution, but there is **no historical backtest/simulation engine** in the repo to test rule or parameter changes over 2–5 years of daily US data before deploying live.
- **Questions for Review:**
  1. Design a minimal, zero-lookahead daily-bar backtester (using `yfinance` 2–5y history for the 47 tickers + `SPY` + `^VIX`) that mirrors `MapleStrategy` + `check_target_stops` so we can A/B test Opportunities A–D (win rate, profit factor, max drawdown, CAGR, turnover/commissions) before touching live execution.

### Opportunity F: Hybrid Server-Side Catastrophic Stops at IBKR
- **Gap in MAPLE:** MAPLE's polling-based `check_target_stops` enables smart ratchets and the 9:30–10:00 AM chop buffer, but leaves positions unprotected if the local daemon, network, or IBKR Gateway drops during a flash crash.
- **Questions for Review:**
  1. Is it worth submitting a resting **server-side catastrophic stop** at IBKR (e.g., `2%–3%` below MAPLE's soft stop, or `max_stop_loss + chop_buffer`) on entry and cancelling/replacing it when MAPLE exits or ratchets? Evaluate IBKR Client Portal API order-management complexity vs. risk reduction.

---

## 4. Requested Output from the Reviewing Model
Please review this brief and produce:
1. **Critique & Filtering:** Which of Opportunities A–F are genuinely high-ROI for a 47-stock US swing bot with MAPLE's ~`0.5–4` day hold profile (`STAGNATION_DAYS = 4`), and which ones could over-complicate or conflict with MAPLE's existing ratchets/chop guards?
2. **Prioritized Implementation Plan (Phased):**
   - **Phase 1 (Validation):** Spec for the lightweight backtester (Opportunity E) + baseline metrics on the current 47-stock US rules.
   - **Phase 2 (Highest-Impact Strategy/Risk Upgrades):** Exact formulas, thresholds, and files to update (`maple_market.py`, `maple_strategy.py`, `maple_brain.py`, `maple_ledger.py`, `maple_config.json`) — plus cleaning up stale `"32 TSX"` docstrings.
   - **Phase 3 (Execution Hardening):** Whether/how to add server-side catastrophic stops without breaking `sync_working_orders()` or `chop_stop_buffer_pct`.
3. **Edge Cases & Regression Checks:** Specific tests to add to `test_risk_guards.py` for each proposed change.
