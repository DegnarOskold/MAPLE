# MAPLE: Autonomous TSX Algorithmic Trading System

**MAPLE** (**M**arket **A**nalyzer & **P**ortfolio **L**edger **E**ngine) is a self-contained, autonomous algorithmic trading system designed for Canadian equities on the Toronto Stock Exchange (TSX). Built from the ground up for strict capital preservation, MAPLE executes rule-based swing-trading strategies across a vetted 32-ticker AAOIFI Shariah-compliant universe, connecting directly to **Interactive Brokers (IBKR) Canada** via the local Client Portal Gateway (or running in zero-risk paper-trading **SIMULATED** mode).

---

## Key Features

- **100% Self-Contained Local Engine**: Zero external folder or third-party cloud dependencies. Market data, technical analysis (`pandas-ta`), corporate earnings calendars, and macro commodity alignment (`GC=F` Gold, `CL=F` Crude Oil) run entirely locally via standard Python libraries.
- **Strict Shariah-Compliant Gatekeeper**: Hardcoded 32-ticker universe vetted for AAOIFI financial ratio and business activity compliance across 6 sectors (Technology, Industrials & Rail, Precious Metals, Energy & Uranium, Base Metals & Materials, Consumer & Packaging).
- **Institutional Risk & Capital Preservation Guards**:
  - **Rule 3 Opening Chop Guard (09:30–10:00 AM ET)**: Zero buy orders during opening price discovery; held assets monitored with a dynamic `2.0%` stop buffer to prevent opening-wick stop-outs while harvesting opening spikes.
  - **Single-Share Whole-Lot Floor (`<= 30%` NAV)**: Tailored for small accounts ($1,000 seed), allowing 1-share entry on valid signals up to 30% of portfolio NAV while enforcing cash reserve ($20 CAD buffer), $400 order cap, and 35% sector caps.
  - **Two-Way Commission Net Hurdle**: Target prices calculate round-trip IBKR trading commissions ($2.00 minimum drag) to guarantee a minimum `+2.5%` net return on invested capital.
  - **Scale-In Cap & Red-Candle Guard**: Maximum 2 entries per position cycle with mandatory 4-hour cooldown and hard block against scaling into red intraday candles.
  - **Automated Breakeven Stop Ratchet**: Once an open position reaches `+2.0%` unrealized gain, its protective stop is automatically ratcheted to cost basis (ACB + commission).
  - **4-Day Stagnation Exit**: Exits stagnant losing positions held $\ge$ 4 days with bearish moving averages, with a built-in deferral for recovering intraday rallies.
  - **Earnings Binary Event Shield**: Blocks new buy entries within 3 trading days of scheduled quarterly earnings reports.
  - **Daily Drawdown Circuit Breaker**: Halts all buying if daily portfolio equity drops $\ge \$40\text{ CAD}$ (4%) vs. previous day close.
- **Autonomous Retrospective & Optimization**: Evaluates daily closing NAV deltas, assesses position attribution, flags risk watchlists, and tunes strategy thresholds after market close (04:10 PM ET).
- **Multi-Channel Telegram Alerts**: Dispatches real-time fill confirmations, pending order updates, scan summaries, and formatted EOD retrospective reports.

---

## Architecture Overview

```
MAPLE/
├── maple_brain.py             # Intraday orchestrator, 32-ticker candidate evaluation, chop guard
├── maple_ledger.py            # Trade execution, position tracking, cash/ACB accounting, risk gates
├── maple_strategy.py          # Dynamic tranche sizing (15%-35%), scoring rules, target/stop math
├── maple_market.py            # Real-time TSX data, 24h-cached earnings calendar, macro commodities
├── maple_optimizer.py         # Daily post-close performance audit, attribution, strategy tuning
├── maple_daemon.py            # Standalone continuous background loop
├── maple_compare.py           # Benchmarks MAPLE performance against S&P/TSX 60 (XIU.TO)
├── ibkr_client.py             # Interactive Brokers Client Portal Gateway REST API client
├── ibkr_keepalive.py          # Gateway SSO session keepalive daemon (45s tickle)
├── telegram_notifier.py       # Telegram notification dispatcher
├── test_risk_guards.py        # 14-point regression self-check test suite
├── start_ibkr_gateway.bat     # Windows launcher for local IBKR Client Portal Gateway
├── run_maple.bat              # Windows launcher for MAPLE continuous daemon
├── requirements.txt           # Python package dependencies
├── .gitignore                 # Protects credentials, account IDs, and trade history
├── .env.example               # Template for environment secrets
├── maple_config.example.json  # Template for core trading parameters
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
- `"initial_cash"`: Your starting account balance in CAD (e.g., `1000.0`).
- Adjust risk thresholds (e.g., `"max_position_pct": 0.25`, `"max_sector_pct": 0.35`, `"daily_loss_limit_cad": 40.0`).

### Step 2: Configure Telegram Notifications (Optional)

If you wish to receive real-time trade alerts and daily EOD performance summaries on Telegram:

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

If trading in `LIVE` mode on Interactive Brokers Canada:

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

Before running live capital, verify that all 14 mathematical risk guards, filters, and standalone decoupling checks pass:

```bash
python test_risk_guards.py
```

Expected output:
```
ALL 14 RISK GUARD, POST-MORTEM & STANDALONE ISOLATION CHECKS PASSED SUCCESSFULLY!
```

---

## Running MAPLE

### Option A: Continuous Standalone Daemon

Run the all-in-one background daemon (monitors market hours, executes scans every 15 minutes, runs opening chop guard, and triggers EOD optimization):

- **Windows**: Double-click `run_maple.bat` (or run `python maple_daemon.py`).
- **Linux/macOS**: `python maple_daemon.py`.

### Option B: Scheduled / Cron Execution

If integrating with system schedulers (`cron`, Windows Task Scheduler, or AI assistants):

| Time (ET) | Frequency | Command | Objective |
| :--- | :--- | :--- | :--- |
| **09:30 – 10:00 AM** | Every 5 min | `python maple_brain.py --chop-guard` | Held-assets profit target harvesting & chop stop protection |
| **10:00 AM – 03:45 PM** | Every 15 min | `python maple_brain.py` | 32-ticker candidate scanning & limit order execution |
| **04:10 PM** | Mon–Fri Close | `python maple_optimizer.py` | Daily performance audit & retrospective logging |

### Manual Single-Scan Execution

To execute an immediate market scan at any time:
```bash
python maple_brain.py
```

To compare current portfolio performance against the benchmark:
```bash
python maple_compare.py
```

---

## Risk Disclaimer

*MAPLE is an automated trading software tool provided for educational and research purposes. Algorithmic trading in financial markets involves substantial risk of capital loss. Past backtested or simulated performance is not indicative of future results. Users are solely responsible for configuring their own risk parameters, testing in SIMULATED mode, and managing their broker accounts.*
