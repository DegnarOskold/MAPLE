# MAPLE: Autonomous US Equities Algorithmic Trading System

**MAPLE** (**M**arket **A**nalyzer & **P**ortfolio **L**edger **E**ngine) is a self-contained, autonomous algorithmic trading system designed for US equities on **NYSE and NASDAQ**. Built from the ground up for strict capital preservation, MAPLE executes rule-based swing-trading strategies across a **47-ticker AAOIFI Shariah-compliant, Zoya-certified US universe**, connecting directly to **Interactive Brokers (IBKR)** via the local Client Portal Gateway with `SMART` USD routing (or running in zero-risk paper-trading **SIMULATED** mode).

---

## Key Features

- **100% Self-Contained Local Engine**: Market data (`yfinance`), technical analysis (`pandas-ta`), corporate earnings calendars, and macro alignment (`GC=F` Gold, `CL=F` Crude Oil, `^VIX` Panic Regime) run locally via standard Python libraries.
- **Strict Shariah-Compliant Gatekeeper**: Hardcoded **47-ticker** US equity universe vetted for AAOIFI financial ratio and business activity compliance across 6 sectors (**Technology**, **Healthcare**, **Energy**, **Industrials**, **Consumer**, **Materials**).
- **Institutional Risk & Capital Preservation Guards**:
  - **Rule 3 Opening Chop Guard (09:30–10:00 AM ET)**: Zero buy orders during opening price discovery; held assets monitored with a dynamic `2.0%` stop buffer to prevent opening-wick stop-outs while harvesting opening spikes.
  - **Single-Share Whole-Lot Floor (`<= 30%` NAV)**: Allows 1-share entry on valid signals up to 30% of portfolio NAV while enforcing dynamic order caps, `15%–35%` tranches, and `35%` max sector concentration.
  - **Two-Way Commission Net Hurdle**: Target prices calculate round-trip IBKR commissions (`$2.00` minimum drag) to guarantee a minimum `+2.5%` net return on invested capital (`+3.5%` target cap on oversold Capitulation Reversal mean-reversion bounces).
  - **Trend & Volume Discipline**: Hard `ADX >= 15.0` trend floor (disallowing Single-Bypass in dead sideways chop), `1.00x` minimum volume ratio for scaled entries, `RSI <= 68.0` overbought ceiling, max `3.0%` EMA5 extension cap, and `^VIX >= 25` (or `+10%` spike) macro panic gating.
  - **Scale-In Cap & Red-Candle Guard**: Maximum 2 entries per position cycle with mandatory 4-hour cooldown, `+0.5%` / `+1.0%` progress hurdle over Entry #1, and hard block against scaling into red intraday candles.
  - **Tiered Automated Stop Ratchets**:
    - `+2.0%` unrealized gain: **Tier 0.5** half-risk stop (`-2.5%` below ACB)
    - `+2.5%` unrealized gain: **Tier 1** breakeven stop (`ACB + $0.50`)
    - `+3.0%` unrealized gain: **Tier 2** profit-lock stop (`+1.5%` net above ACB)
    - `+4.5%` unrealized gain: **Tier 3** trailing stop (`-1.25%` below live price)
  - **4-Trading-Day Stagnation Exit**: Exits stagnant losing positions held $\ge 4$ weekday trading sessions with bearish EMA alignment (`EMA5 < EMA9` or below both EMAs), with a built-in deferral for recovering intraday rallies.
  - **Earnings Binary Event Shield**: Blocks new buy entries within 3 trading days of scheduled quarterly earnings reports.
  - **Daily Drawdown Circuit Breaker**: Halts all buying if daily portfolio equity drops $\ge 4\%$ (or configured `daily_loss_limit_cad` floor) vs. previous day close.
- **Autonomous Retrospective & Optimization**: Evaluates daily closing NAV deltas (cash-flow & TWR adjusted), position attribution, risk watchlists, and filtered vs. actionable movers after market close (`04:10 PM ET`).
- **Multi-Channel Telegram Alerts**: Dispatches real-time fill confirmations, pending order updates, scan summaries, and formatted EOD retrospective reports.

---

## Architecture Overview

```
MAPLE/
├── maple_brain.py               # Intraday orchestrator, 47-ticker US evaluation, chop guard
├── maple_ledger.py              # Trade execution, position tracking, cash/ACB accounting, risk gates
├── maple_strategy.py            # Dynamic tranche sizing, scoring rules, target/stop math
├── maple_market.py              # Real-time US data, 24h-cached earnings calendar, macro alignment
├── maple_optimizer.py           # Daily post-close performance audit, attribution, changelog logging
├── maple_daemon.py              # Standalone continuous background loop
├── maple_compare.py             # Benchmarks MAPLE performance against S&P 500 (SPY)
├── maple_backtest.py            # Read-only 1-year US walk-forward backtester CLI
├── ibkr_client.py               # Interactive Brokers Client Portal Gateway REST API client (SMART/USD)
├── ibkr_keepalive.py            # Gateway SSO session keepalive daemon (45s tickle)
├── telegram_notifier.py         # Telegram notification dispatcher
├── test_risk_guards.py          # 28-point regression self-check test suite
├── start_ibkr_gateway.bat       # Windows launcher for local IBKR Client Portal Gateway
├── run_maple.bat                # Windows launcher for MAPLE continuous daemon
├── requirements.txt             # Python package dependencies
├── .gitignore                   # Protects credentials, account IDs, and trade history
├── .env.example                 # Template for environment secrets
├── maple_config.example.json    # Template for core trading parameters (USD / 47 US equities)
└── telegram_config.example.json # Template for Telegram bot settings
```

---

## Getting Started

### 1. Prerequisites

- **Python**: Version `3.10` or higher (`miniforge3` or standard CPython).
- **Java**: JRE 8 or higher (required by the Interactive Brokers Client Portal Gateway if running in `LIVE` mode).
- **Operating System**: Windows, Linux, or macOS.

### 2. Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/DegnarOskold/MAPLE.git
   cd MAPLE
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## Confidential Configuration Setup

To ensure security, all confidential credentials, account numbers, and personal trade records are excluded from version control via `.gitignore`. End users must configure their own local settings before starting.

### Step 1: Configure Core Trading Parameters (`maple_config.json`)

Copy the example configuration:
```bash
cp maple_config.example.json maple_config.json
```

Open `maple_config.json` in your text editor and customize:
- `"trading_mode"`: Set to `"SIMULATED"` for risk-free paper trading or `"LIVE"` for real broker execution.
- `"account_id"`: Set to your Interactive Brokers account number (e.g., `"U12345678"`). In `SIMULATED` mode, this can be left as `"SIM"`.
- `"account_currency"`: `"USD"` for US equities.
- `"initial_cash"`: Your starting account balance in USD (e.g., `1000.0`).
- Adjust risk thresholds (e.g., `"max_position_pct": 0.25`, `"max_sector_pct": 0.35`, `"daily_loss_limit_pct": 0.04`).

### Step 2: Configure Telegram Notifications (Optional)

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram and copy your API Token.
2. Retrieve your Telegram User or Channel Chat ID (via [@userinfobot](https://t.me/userinfobot)).
3. Copy the configuration template:
   ```bash
   cp telegram_config.example.json telegram_config.json
   ```
4. Insert your credentials:
   ```json
   {
       "telegram_bot_token": "YOUR_TELEGRAM_BOT_TOKEN_HERE",
       "telegram_chat_id": "YOUR_TELEGRAM_CHAT_ID_HERE",
       "notify_on_trades": true,
       "notify_on_scans": true,
       "notify_on_circuit_breakers": true,
       "notify_on_close": true
   }
   ```
   *(Alternatively, copy `.env.example` to `.env` and configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` there).*

### Step 3: Interactive Brokers Client Portal Gateway Setup (LIVE Mode Only)

1. Download the **Interactive Brokers Client Portal Web API Gateway** from the official IBKR website:
   [https://www.interactivebrokers.github.io/cpwebapi/](https://www.interactivebrokers.github.io/cpwebapi/)
2. Extract the archive into a folder named `clientportal/` inside the `MAPLE/` root directory.
3. Launch the gateway:
   - On Windows: Double-click `start_ibkr_gateway.bat` (or execute `clientportal\bin\run.bat root\conf.yaml`).
   - On Linux/macOS: Run `bin/run.sh root/conf.yaml`.
4. Open your web browser and navigate to:
   ```
   https://localhost:5000
   ```
   *(Accept the self-signed SSL certificate warning).*
5. Log in with your Interactive Brokers credentials and complete 2-factor authentication.
6. Start the keepalive daemon to maintain your session active throughout the trading day:
   ```bash
   python ibkr_keepalive.py
   ```

---

## Verifying the Test Suite

Before running live capital, verify that all 28 mathematical risk guards, filters, and standalone decoupling checks pass:

```bash
python test_risk_guards.py
```

Expected output:
```
ALL 28 RISK GUARD, POST-MORTEM & STANDALONE ISOLATION CHECKS PASSED SUCCESSFULLY!
```

---

## Running MAPLE

### Option A: Continuous Standalone Daemon

Run the all-in-one background daemon (monitors US market hours, executes scans every 15 minutes, runs opening chop guard, and triggers EOD optimization):

- **Windows**: Double-click `run_maple.bat` (or run `python maple_daemon.py`).
- **Linux/macOS**: `python maple_daemon.py`.

### Option B: Scheduled / Cron Execution

If integrating with system schedulers (`cron`, Windows Task Scheduler, or AI assistants):

| Time (ET) | Frequency | Command | Objective |
| :--- | :--- | :--- | :--- |
| **09:30 – 10:00 AM** | Every 5 min | `python maple_brain.py --chop-guard` | Held-assets profit target harvesting & chop stop protection |
| **10:00 AM – 03:45 PM** | Every 15 min | `python maple_brain.py` | 47-ticker US candidate scanning & limit order execution |
| **04:10 PM** | Mon–Fri Close | `python maple_optimizer.py` | Daily performance audit & retrospective logging |

### Manual Single-Scan Execution

To execute an immediate market scan at any time:
```bash
python maple_brain.py
```

To compare current portfolio performance against the S&P 500 (`SPY`) benchmark:
```bash
python maple_compare.py
```

---

## Risk Disclaimer

*MAPLE is an automated trading software tool provided for educational and research purposes. Algorithmic trading in financial markets involves substantial risk of capital loss. Past backtested or simulated performance is not indicative of future results. Users are solely responsible for configuring their own risk parameters, testing in SIMULATED mode, and managing their broker accounts.*
