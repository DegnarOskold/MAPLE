# MAPLE Autonomous Logic & Parameter Changelog

This document tracks all autonomous logic and parameter adaptations made by MAPLE during her daily and weekly self-evaluations.

*Note: These changes affect MAPLE only. The live TSX Trading Bot is never modified.*

---

### Initial Baseline [2026-09-24 19:00:00]
- **Active Version:** `1.0.0`
- **Initial Cloned Equity:** `~$7,400.77 CAD` (`$3,713.31` Free Cash, `10.0` WCN.TO, `16.0` CCL-B.TO)
- **Position Sizing Engine:** Dynamic tranche range `15% - 35%` based on indicator scoring.
- **Risk Parameters:** Fixed `5.0%` Stop-Loss, `100%` full liquidation on SELL triggers, automated profit target triggers at `Mid-Bollinger Band` or `1.5x ATR`.


### Optimization Log [2026-09-24 19:09:24]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 4

**Breakout / High-Reversal Assets Not Held:**
- **CLS.TO**: Day Gain: `+3.36%` | Low Rebound: `+5.86%` | RSI: `78.89` | Vol: `1.18x`
- **SHOP.TO**: Day Gain: `+2.41%` | Low Rebound: `+3.77%` | RSI: `71.28` | Vol: `0.77x`
- **CSU.TO**: Day Gain: `+2.18%` | Low Rebound: `+3.33%` | RSI: `46.29` | Vol: `1.13x`
- **TECK-B.TO**: Day Gain: `+-0.17%` | Low Rebound: `+3.56%` | RSI: `52.64` | Vol: `1.12x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-09-25 16:10:07]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 0

**Autonomous Action:** Current parameter boundaries remain optimal; no changes required today.


### Optimization Log [2026-09-25 16:30:06]
**Session Type:** Weekly Retrospective & Optimization
**Ending Cash:** `$1206.38` CAD
**Open Positions:** 7
**Weekly Review:** Evaluating stop-loss efficiency and ATR profit target multipliers.
- Target Sizing: Min 15.0% | Base 25.0% | Max 35.0%
- Risk Parameters: Stop Loss `5.0%` | ATR Multiplier `1.5x`
- **Strategy Version:** `1.0.0`


### Optimization Log [2026-09-28 16:10:09]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 0

**Autonomous Action:** Current parameter boundaries remain optimal; no changes required today.


### Optimization Log [2026-09-29 15:42:34]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 3

**Breakout / High-Reversal Assets Not Held:**
- **CLS.TO**: Day Gain: `+2.84%` | Low Rebound: `+1.45%` | RSI: `68.13` | Vol: `0.39x`
- **SHOP.TO**: Day Gain: `+2.57%` | Low Rebound: `+3.67%` | RSI: `67.2` | Vol: `0.42x`
- **ATZ.TO**: Day Gain: `+2.19%` | Low Rebound: `+2.93%` | RSI: `52.4` | Vol: `0.39x`

**Autonomous Action:** Current parameter boundaries remain optimal; no changes required today.


### Optimization Log [2026-09-29 16:10:08]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 3

**Breakout / High-Reversal Assets Not Held:**
- **CLS.TO**: Day Gain: `+2.65%` | Low Rebound: `+1.26%` | RSI: `67.81` | Vol: `0.55x`
- **SHOP.TO**: Day Gain: `+2.86%` | Low Rebound: `+3.96%` | RSI: `67.7` | Vol: `0.79x`
- **ATZ.TO**: Day Gain: `+2.25%` | Low Rebound: `+3.0%` | RSI: `52.6` | Vol: `0.57x`

**Autonomous Action:** Current parameter boundaries remain optimal; no changes required today.


### Optimization Log [2026-10-09 17:06:02]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 15

**Breakout / High-Reversal Assets Not Held:**
- **ABX.TO**: Day Gain: `+2.94%` | Low Rebound: `+1.11%` | RSI: `53.24` | Vol: `0.96x`
- **CLS.TO**: Day Gain: `+2.02%` | Low Rebound: `+2.13%` | RSI: `49.53` | Vol: `0.7x`
- **SHOP.TO**: Day Gain: `+4.12%` | Low Rebound: `+2.99%` | RSI: `84.75` | Vol: `1.04x`
- **AEM.TO**: Day Gain: `+3.2%` | Low Rebound: `+1.36%` | RSI: `56.4` | Vol: `0.7x`
- **CSU.TO**: Day Gain: `+3.15%` | Low Rebound: `+3.15%` | RSI: `66.5` | Vol: `0.67x`
- **TECK-B.TO**: Day Gain: `+5.43%` | Low Rebound: `+2.01%` | RSI: `60.7` | Vol: `1.27x`
- **TIH.TO**: Day Gain: `+0.7%` | Low Rebound: `+2.96%` | RSI: `36.83` | Vol: `0.99x`
- **ATZ.TO**: Day Gain: `+20.53%` | Low Rebound: `+8.82%` | RSI: `82.18` | Vol: `3.74x`
- **FNV.TO**: Day Gain: `+2.21%` | Low Rebound: `+0.46%` | RSI: `51.22` | Vol: `0.65x`
- **SU.TO**: Day Gain: `+2.13%` | Low Rebound: `+2.21%` | RSI: `76.1` | Vol: `0.5x`
- **RUS.TO**: Day Gain: `+2.48%` | Low Rebound: `+2.91%` | RSI: `60.88` | Vol: `0.91x`
- **DSG.TO**: Day Gain: `+2.32%` | Low Rebound: `+1.36%` | RSI: `68.89` | Vol: `0.75x`
- **WPM.TO**: Day Gain: `+2.92%` | Low Rebound: `+1.35%` | RSI: `52.75` | Vol: `0.54x`
- **PAAS.TO**: Day Gain: `+2.59%` | Low Rebound: `+1.06%` | RSI: `52.28` | Vol: `1.56x`
- **AGI.TO**: Day Gain: `+2.4%` | Low Rebound: `+0.84%` | RSI: `50.91` | Vol: `0.71x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-09 17:08:46]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 15

**Breakout / High-Reversal Assets Not Held:**
- **ABX.TO**: Day Gain: `+2.94%` | Low Rebound: `+1.11%` | RSI: `53.24` | Vol: `0.96x`
- **CLS.TO**: Day Gain: `+2.02%` | Low Rebound: `+2.13%` | RSI: `49.53` | Vol: `0.7x`
- **SHOP.TO**: Day Gain: `+4.12%` | Low Rebound: `+2.99%` | RSI: `84.75` | Vol: `1.04x`
- **AEM.TO**: Day Gain: `+3.2%` | Low Rebound: `+1.36%` | RSI: `56.4` | Vol: `0.7x`
- **CSU.TO**: Day Gain: `+3.15%` | Low Rebound: `+3.15%` | RSI: `66.5` | Vol: `0.67x`
- **TECK-B.TO**: Day Gain: `+5.43%` | Low Rebound: `+2.01%` | RSI: `60.7` | Vol: `1.27x`
- **TIH.TO**: Day Gain: `+0.7%` | Low Rebound: `+2.96%` | RSI: `36.83` | Vol: `0.99x`
- **ATZ.TO**: Day Gain: `+20.53%` | Low Rebound: `+8.82%` | RSI: `82.18` | Vol: `3.74x`
- **FNV.TO**: Day Gain: `+2.21%` | Low Rebound: `+0.46%` | RSI: `51.22` | Vol: `0.65x`
- **SU.TO**: Day Gain: `+2.13%` | Low Rebound: `+2.21%` | RSI: `76.1` | Vol: `0.5x`
- **RUS.TO**: Day Gain: `+2.48%` | Low Rebound: `+2.91%` | RSI: `60.88` | Vol: `0.91x`
- **DSG.TO**: Day Gain: `+2.32%` | Low Rebound: `+1.36%` | RSI: `68.89` | Vol: `0.75x`
- **WPM.TO**: Day Gain: `+2.92%` | Low Rebound: `+1.35%` | RSI: `52.75` | Vol: `0.54x`
- **PAAS.TO**: Day Gain: `+2.59%` | Low Rebound: `+1.06%` | RSI: `52.28` | Vol: `1.56x`
- **AGI.TO**: Day Gain: `+2.4%` | Low Rebound: `+0.84%` | RSI: `50.91` | Vol: `0.71x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-09 17:09:02]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 15

**Breakout / High-Reversal Assets Not Held:**
- **ABX.TO**: Day Gain: `+2.94%` | Low Rebound: `+1.11%` | RSI: `53.24` | Vol: `0.96x`
- **CLS.TO**: Day Gain: `+2.02%` | Low Rebound: `+2.13%` | RSI: `49.53` | Vol: `0.7x`
- **SHOP.TO**: Day Gain: `+4.12%` | Low Rebound: `+2.99%` | RSI: `84.75` | Vol: `1.04x`
- **AEM.TO**: Day Gain: `+3.2%` | Low Rebound: `+1.36%` | RSI: `56.4` | Vol: `0.7x`
- **CSU.TO**: Day Gain: `+3.15%` | Low Rebound: `+3.15%` | RSI: `66.5` | Vol: `0.67x`
- **TECK-B.TO**: Day Gain: `+5.43%` | Low Rebound: `+2.01%` | RSI: `60.7` | Vol: `1.27x`
- **TIH.TO**: Day Gain: `+0.7%` | Low Rebound: `+2.96%` | RSI: `36.83` | Vol: `0.99x`
- **ATZ.TO**: Day Gain: `+20.53%` | Low Rebound: `+8.82%` | RSI: `82.18` | Vol: `3.74x`
- **FNV.TO**: Day Gain: `+2.21%` | Low Rebound: `+0.46%` | RSI: `51.22` | Vol: `0.65x`
- **SU.TO**: Day Gain: `+2.13%` | Low Rebound: `+2.21%` | RSI: `76.1` | Vol: `0.5x`
- **RUS.TO**: Day Gain: `+2.48%` | Low Rebound: `+2.91%` | RSI: `60.88` | Vol: `0.91x`
- **DSG.TO**: Day Gain: `+2.32%` | Low Rebound: `+1.36%` | RSI: `68.89` | Vol: `0.75x`
- **WPM.TO**: Day Gain: `+2.92%` | Low Rebound: `+1.35%` | RSI: `52.75` | Vol: `0.54x`
- **PAAS.TO**: Day Gain: `+2.59%` | Low Rebound: `+1.06%` | RSI: `52.28` | Vol: `1.56x`
- **AGI.TO**: Day Gain: `+2.4%` | Low Rebound: `+0.84%` | RSI: `50.91` | Vol: `0.71x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-09 17:09:16]
**Session Type:** Weekly Retrospective & Optimization
**Ending Cash:** CAD 824.99
**Open Positions:** 1
**Weekly Review:** Evaluating stop-loss efficiency and ATR profit target multipliers.
- Target Sizing: Min 15.0% | Base 25.0% | Max 35.0%
- Risk Parameters: Stop Loss `5.0%` | ATR Multiplier `1.5x`
- **Strategy Version:** `1.0.0`


### Optimization Log [2026-10-09 17:22:39]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 15

**Breakout / High-Reversal Assets Not Held:**
- **ABX.TO**: Day Gain: `+2.94%` | Low Rebound: `+1.11%` | RSI: `53.24` | Vol: `0.96x`
- **CLS.TO**: Day Gain: `+2.02%` | Low Rebound: `+2.13%` | RSI: `49.53` | Vol: `0.7x`
- **SHOP.TO**: Day Gain: `+4.12%` | Low Rebound: `+2.99%` | RSI: `84.75` | Vol: `1.04x`
- **AEM.TO**: Day Gain: `+3.2%` | Low Rebound: `+1.36%` | RSI: `56.4` | Vol: `0.7x`
- **CSU.TO**: Day Gain: `+3.15%` | Low Rebound: `+3.15%` | RSI: `66.5` | Vol: `0.67x`
- **TECK-B.TO**: Day Gain: `+5.43%` | Low Rebound: `+2.01%` | RSI: `60.7` | Vol: `1.27x`
- **TIH.TO**: Day Gain: `+0.7%` | Low Rebound: `+2.96%` | RSI: `36.83` | Vol: `0.99x`
- **ATZ.TO**: Day Gain: `+20.53%` | Low Rebound: `+8.82%` | RSI: `82.18` | Vol: `3.74x`
- **FNV.TO**: Day Gain: `+2.21%` | Low Rebound: `+0.46%` | RSI: `51.22` | Vol: `0.65x`
- **SU.TO**: Day Gain: `+2.13%` | Low Rebound: `+2.21%` | RSI: `76.1` | Vol: `0.5x`
- **RUS.TO**: Day Gain: `+2.48%` | Low Rebound: `+2.91%` | RSI: `60.88` | Vol: `0.91x`
- **DSG.TO**: Day Gain: `+2.32%` | Low Rebound: `+1.36%` | RSI: `68.89` | Vol: `0.75x`
- **WPM.TO**: Day Gain: `+2.92%` | Low Rebound: `+1.35%` | RSI: `52.75` | Vol: `0.54x`
- **PAAS.TO**: Day Gain: `+2.59%` | Low Rebound: `+1.06%` | RSI: `52.28` | Vol: `1.56x`
- **AGI.TO**: Day Gain: `+2.4%` | Low Rebound: `+0.84%` | RSI: `50.91` | Vol: `0.71x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-13 16:10:16]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 13

**Breakout / High-Reversal Assets Not Held:**
- **CNQ.TO**: Day Gain: `+4.79%` | Low Rebound: `+3.23%` | RSI: `81.74` | Vol: `0.84x`
- **GIB-A.TO**: Day Gain: `+2.62%` | Low Rebound: `+2.1%` | RSI: `69.46` | Vol: `0.96x`
- **CLS.TO**: Day Gain: `+-1.72%` | Low Rebound: `+9.46%` | RSI: `44.79` | Vol: `1.53x`
- **SHOP.TO**: Day Gain: `+2.96%` | Low Rebound: `+1.64%` | RSI: `87.51` | Vol: `0.85x`
- **CSU.TO**: Day Gain: `+2.98%` | Low Rebound: `+3.09%` | RSI: `75.73` | Vol: `1.3x`
- **TIH.TO**: Day Gain: `+0.18%` | Low Rebound: `+2.64%` | RSI: `37.77` | Vol: `0.68x`
- **ATZ.TO**: Day Gain: `+-0.32%` | Low Rebound: `+6.03%` | RSI: `81.03` | Vol: `1.58x`
- **SU.TO**: Day Gain: `+3.67%` | Low Rebound: `+2.12%` | RSI: `83.15` | Vol: `0.91x`
- **IMO.TO**: Day Gain: `+4.55%` | Low Rebound: `+3.91%` | RSI: `68.22` | Vol: `1.14x`
- **CVE.TO**: Day Gain: `+4.25%` | Low Rebound: `+2.91%` | RSI: `67.33` | Vol: `0.85x`
- **TFII.TO**: Day Gain: `+-1.13%` | Low Rebound: `+2.64%` | RSI: `27.3` | Vol: `1.31x`
- **DSG.TO**: Day Gain: `+2.25%` | Low Rebound: `+1.61%` | RSI: `74.8` | Vol: `1.16x`
- **KXS.TO**: Day Gain: `+2.79%` | Low Rebound: `+3.19%` | RSI: `76.91` | Vol: `2.06x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-14 16:10:13]
**Session Type:** Daily Market Close Assessment
**Missed Opportunities Found:** 3

**Breakout / High-Reversal Assets Not Held:**
- **WCN.TO**: Day Gain: `+2.15%` | Low Rebound: `+1.74%` | RSI: `63.51` | Vol: `1.54x`
- **CSU.TO**: Day Gain: `+1.49%` | Low Rebound: `+2.69%` | RSI: `79.17` | Vol: `0.98x`
- **SAP.TO**: Day Gain: `+2.12%` | Low Rebound: `+2.01%` | RSI: `57.07` | Vol: `0.73x`

**Autonomous Action:** Current parameter boundaries remain optimal; no changes required today.


### Optimization Log [2026-10-15 07:34:15]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 987.82
**Daily NAV Change:** CAD -0.61 (-0.06%) vs Previous Close
**Cumulative Return:** CAD -12.18 (-1.22%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 172.55 (17.5%) | Equity: CAD 815.27 (82.5%)

**Active Position Performance & Drawdown Attribution:**
- **ATRL.TO** (34.7% port): 4 shs @ CAD 85.72 (ACB: CAD 87.91) | Unrealized: **CAD -8.75 (-2.49%)** | Buffer to Stop: CAD 2.43 (2.8%)
- **TECK.B.TO** (9.3% port): 1 shs @ CAD 92.19 (ACB: CAD 93.93) | Unrealized: **CAD -1.74 (-1.85%)** | Buffer to Stop: CAD 2.96 (3.2%)
- **CVE.TO** (9.4% port): 2 shs @ CAD 46.46 (ACB: CAD 47.09) | Unrealized: **CAD -1.25 (-1.33%)** | Buffer to Stop: CAD 1.86 (4.0%)
- **PAAS.TO** (6.1% port): 1 shs @ CAD 60.15 (ACB: CAD 60.95) | Unrealized: **CAD -0.80 (-1.32%)** | Buffer to Stop: CAD 2.53 (4.2%)
- **AGI.TO** (4.4% port): 1 shs @ CAD 43.48 (ACB: CAD 43.76) | Unrealized: **CAD -0.28 (-0.65%)** | Buffer to Stop: CAD 2.15 (4.9%)
- **RUS.TO** (18.6% port): 2 shs @ CAD 91.82 (ACB: CAD 89.96) | Unrealized: **CAD +3.72 (+2.07%)** | Buffer to Stop: CAD 7.18 (7.8%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **ATRL.TO**: Position drawdown: -2.5%; Near stop-loss: 2.8% buffer; High portfolio concentration: 34.7% of NAV (Current: CAD 85.72, Stop: CAD 83.29, Buffer: CAD 2.43 / 2.8%)
- ⚠️ **TECK.B.TO**: Position drawdown: -1.8% (Current: CAD 92.19, Stop: CAD 89.23, Buffer: CAD 2.96 / 3.2%)

**Screened Universe Top Movers (3 non-held candidates):**
- **WCN.TO**: Day Gain: `+2.15%` | Low Rebound: `+1.74%` | RSI: `63.51` | Vol: `1.55x`
- **SAP.TO**: Day Gain: `+2.12%` | Low Rebound: `+2.01%` | RSI: `57.07` | Vol: `0.76x`
- **CSU.TO**: Day Gain: `+1.49%` | Low Rebound: `+2.69%` | RSI: `79.17` | Vol: `1.06x`

**Autonomous Strategy Action:** Risk boundaries and tranche sizing remain verified within operating thresholds.


### Optimization Log [2026-10-15 16:10:14]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 995.43
**Daily NAV Change:** CAD +7.00 (+0.71%) vs Previous Close
**Cumulative Return:** CAD -4.57 (-0.46%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 132.46 (13.3%) | Equity: CAD 862.97 (86.7%)

**Realized Trades Today:**
- RUS.TO SELL 2 shs @ CAD 94.00 | P&L: CAD +8.08 (+4.5%)

**Active Position Performance & Drawdown Attribution:**
- **CVE.TO** (9.1% port): 2 shs @ CAD 45.40 (ACB: CAD 47.09) | Unrealized: **CAD -3.38 (-3.59%)** | Buffer to Stop: CAD 0.80 (1.8%)
- **ATRL.TO** (35.0% port): 4 shs @ CAD 87.08 (ACB: CAD 87.91) | Unrealized: **CAD -3.31 (-0.94%)** | Buffer to Stop: CAD 3.79 (4.3%)
- **TECK.B.TO** (9.4% port): 1 shs @ CAD 93.34 (ACB: CAD 93.93) | Unrealized: **CAD -0.59 (-0.63%)** | Buffer to Stop: CAD 4.58 (4.9%)
- **SAP.TO** (4.0% port): 1 shs @ CAD 39.88 (ACB: CAD 40.09) | Unrealized: **CAD -0.21 (-0.52%)** | Buffer to Stop: CAD 2.00 (5.0%)
- **PAAS.TO** (6.2% port): 1 shs @ CAD 62.15 (ACB: CAD 60.95) | Unrealized: **CAD +1.20 (+1.97%)** | Buffer to Stop: CAD 4.53 (7.3%)
- **AGI.TO** (4.6% port): 1 shs @ CAD 45.43 (ACB: CAD 43.76) | Unrealized: **CAD +1.67 (+3.82%)** | Buffer to Stop: CAD 4.10 (9.0%)
- **RUS.TO** (18.4% port): 2 shs @ CAD 91.52 (ACB: CAD 89.96) | Unrealized: **CAD +3.12 (+1.73%)** | Buffer to Stop: CAD 6.06 (6.6%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **ATRL.TO**: High portfolio concentration: 35.0% of NAV (Current: CAD 87.08, Stop: CAD 83.29, Buffer: CAD 3.79 / 4.3%)
- ⚠️ **CVE.TO**: Position drawdown: -3.6%; Near stop-loss: 1.8% buffer (Current: CAD 45.40, Stop: CAD 44.60, Buffer: CAD 0.80 / 1.8%)

**Screened Universe Top Movers (18 non-held candidates):**
- **ENGH.TO**: Day Gain: `+5.93%` | Low Rebound: `+6.86%` | RSI: `90.32` | Vol: `1.7x`
- **AEM.TO**: Day Gain: `+5.69%` | Low Rebound: `+4.75%` | RSI: `52.5` | Vol: `0.8x`
- **WCN.TO**: Day Gain: `+5.33%` | Low Rebound: `+4.06%` | RSI: `82.01` | Vol: `2.85x`
- **CSU.TO**: Day Gain: `+4.6%` | Low Rebound: `+5.79%` | RSI: `86.29` | Vol: `1.92x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-15 16:14:44]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 995.43
**Daily NAV Change:** CAD +7.00 (+0.71%) vs Previous Close
**Cumulative Return:** CAD -4.57 (-0.46%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 132.46 (13.3%) | Equity: CAD 862.97 (86.7%)

**Active Position Performance & Drawdown Attribution:**
- **CVE.TO** (9.1% port): 2 shs @ CAD 45.40 (ACB: CAD 47.09) | Unrealized: **CAD -3.38 (-3.59%)** | Buffer to Stop: CAD 0.80 (1.8%)
- **ATRL.TO** (35.0% port): 4 shs @ CAD 87.08 (ACB: CAD 87.91) | Unrealized: **CAD -3.31 (-0.94%)** | Buffer to Stop: CAD 3.79 (4.3%)
- **TECK.B.TO** (9.4% port): 1 shs @ CAD 93.34 (ACB: CAD 93.93) | Unrealized: **CAD -0.59 (-0.63%)** | Buffer to Stop: CAD 4.58 (4.9%)
- **SAP.TO** (4.0% port): 1 shs @ CAD 39.88 (ACB: CAD 40.09) | Unrealized: **CAD -0.21 (-0.52%)** | Buffer to Stop: CAD 2.00 (5.0%)
- **PAAS.TO** (6.2% port): 1 shs @ CAD 62.15 (ACB: CAD 60.95) | Unrealized: **CAD +1.20 (+1.97%)** | Buffer to Stop: CAD 4.53 (7.3%)
- **AGI.TO** (4.6% port): 1 shs @ CAD 45.43 (ACB: CAD 43.76) | Unrealized: **CAD +1.67 (+3.82%)** | Buffer to Stop: CAD 4.10 (9.0%)
- **RUS.TO** (18.4% port): 2 shs @ CAD 91.52 (ACB: CAD 89.96) | Unrealized: **CAD +3.12 (+1.73%)** | Buffer to Stop: CAD 6.06 (6.6%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **ATRL.TO**: High portfolio concentration: 35.0% of NAV (Current: CAD 87.08, Stop: CAD 83.29, Buffer: CAD 3.79 / 4.3%)
- ⚠️ **CVE.TO**: Position drawdown: -3.6%; Near stop-loss: 1.8% buffer (Current: CAD 45.40, Stop: CAD 44.60, Buffer: CAD 0.80 / 1.8%)

**Screened Universe Top Movers (18 non-held candidates):**
- **ENGH.TO**: Day Gain: `+5.93%` | Low Rebound: `+6.86%` | RSI: `90.32` | Vol: `1.7x`
- **AEM.TO**: Day Gain: `+5.69%` | Low Rebound: `+4.75%` | RSI: `52.5` | Vol: `0.8x`
- **WCN.TO**: Day Gain: `+5.33%` | Low Rebound: `+4.06%` | RSI: `82.01` | Vol: `2.85x`
- **CSU.TO**: Day Gain: `+4.6%` | Low Rebound: `+5.79%` | RSI: `86.29` | Vol: `1.92x`

**Autonomous Parameter Modifications Applied:**
- [OPTIMIZATION] Adjusted VOLUME_CAPITULATION_RATIO from 1.25x to 1.23x to catch high-reversal opportunities with moderate volume.


### Optimization Log [2026-10-16 16:10:17]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 990.93
**Daily NAV Change:** CAD -4.50 (-0.45%) vs Previous Close
**Cumulative Return:** CAD -9.07 (-0.91%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 132.47 (13.4%) | Equity: CAD 858.46 (86.6%)

**Active Position Performance & Drawdown Attribution:**
- **ATRL.TO** (34.7% port): 4 shs @ CAD 85.96 (ACB: CAD 87.91) | Unrealized: **CAD -7.78 (-2.21%)** | Buffer to Stop: CAD 2.45 (2.9%)
- **TECK-B.TO** (9.2% port): 1 shs @ CAD 91.39 (ACB: CAD 93.93) | Unrealized: **CAD -2.54 (-2.70%)** | Buffer to Stop: CAD 2.16 (2.4%)
- **CVE.TO** (9.4% port): 2 shs @ CAD 46.62 (ACB: CAD 47.09) | Unrealized: **CAD -0.94 (-1.00%)** | Buffer to Stop: CAD 1.88 (4.0%)
- **SAP.TO** (4.0% port): 1 shs @ CAD 39.96 (ACB: CAD 40.09) | Unrealized: **CAD -0.13 (-0.32%)** | Buffer to Stop: CAD 1.87 (4.7%)
- **PAAS.TO** (6.3% port): 1 shs @ CAD 62.53 (ACB: CAD 60.95) | Unrealized: **CAD +1.58 (+2.59%)** | Buffer to Stop: CAD 4.91 (7.8%)
- **AGI.TO** (4.6% port): 1 shs @ CAD 45.46 (ACB: CAD 43.76) | Unrealized: **CAD +1.70 (+3.88%)** | Buffer to Stop: CAD 4.13 (9.1%)
- **RUS.TO** (18.4% port): 2 shs @ CAD 91.01 (ACB: CAD 89.96) | Unrealized: **CAD +2.10 (+1.17%)** | Buffer to Stop: CAD 5.55 (6.1%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **ATRL.TO**: Position drawdown: -2.2%; Near stop-loss: 2.9% buffer; High portfolio concentration: 34.7% of NAV (Current: CAD 85.96, Stop: CAD 83.51, Buffer: CAD 2.45 / 2.9%)
- ⚠️ **TECK-B.TO**: Position drawdown: -2.7%; Near stop-loss: 2.4% buffer (Current: CAD 91.39, Stop: CAD 89.23, Buffer: CAD 2.16 / 2.4%)

**Screened Universe Top Movers (3 non-held candidates):**
- **CNQ.TO**: Day Gain: `+3.19%` | Low Rebound: `+2.37%` | RSI: `83.69` | Vol: `0.37x`
- **IMO.TO**: Day Gain: `+2.86%` | Low Rebound: `+2.17%` | RSI: `75.8` | Vol: `1.18x`
- **SU.TO**: Day Gain: `+2.67%` | Low Rebound: `+1.94%` | RSI: `85.18` | Vol: `0.72x`

**Autonomous Strategy Action:** Risk boundaries and tranche sizing remain verified within operating thresholds.


### Optimization Log [2026-10-19 16:10:18]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 991.74
**Daily NAV Change:** CAD +0.81 (+0.08%) vs Previous Close
**Cumulative Return:** CAD -8.26 (-0.83%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 571.13 (57.6%) | Equity: CAD 420.61 (42.4%)

**Realized Trades Today:**
- RUS.TO SELL 2 shs @ CAD 93.95 | P&L: CAD +7.98 (+4.4%)
- ATRL.TO SELL 4 shs @ CAD 85.70 | P&L: CAD -8.83 (-2.5%)
- TECK-B.TO SELL 1 shs @ CAD 89.29 | P&L: CAD -4.64 (-4.9%)

**Active Position Performance & Drawdown Attribution:**
- **CVE.TO** (9.5% port): 2 shs @ CAD 46.90 (ACB: CAD 47.09) | Unrealized: **CAD -0.38 (-0.40%)** | Buffer to Stop: CAD 2.16 (4.6%)
- **SAP.TO** (4.0% port): 1 shs @ CAD 39.76 (ACB: CAD 40.09) | Unrealized: **CAD -0.33 (-0.82%)** | Buffer to Stop: CAD 1.67 (4.2%)
- **TECK-B.TO** (18.1% port): 2 shs @ CAD 89.61 (ACB: CAD 89.47) | Unrealized: **CAD +0.27 (+0.15%)** | Buffer to Stop: CAD 5.16 (5.8%)
- **AGI.TO** (4.5% port): 1 shs @ CAD 45.11 (ACB: CAD 43.76) | Unrealized: **CAD +1.35 (+3.09%)** | Buffer to Stop: CAD 1.35 (3.0%)
- **PAAS.TO** (6.3% port): 1 shs @ CAD 62.72 (ACB: CAD 60.95) | Unrealized: **CAD +1.77 (+2.91%)** | Buffer to Stop: CAD 1.77 (2.8%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **PAAS.TO**: Near stop-loss: 2.8% buffer (Current: CAD 62.72, Stop: CAD 60.95, Buffer: CAD 1.77 / 2.8%)
- ⚠️ **AGI.TO**: Near stop-loss: 3.0% buffer (Current: CAD 45.11, Stop: CAD 43.76, Buffer: CAD 1.35 / 3.0%)

**Autonomous Strategy Action:** Risk boundaries and tranche sizing remain verified within operating thresholds.


### Optimization Log [2026-10-20 16:10:16]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 991.47
**Daily NAV Change:** CAD -0.27 (-0.03%) vs Previous Close
**Cumulative Return:** CAD -8.53 (-0.85%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 766.61 (77.3%) | Equity: CAD 224.86 (22.7%)

**Realized Trades Today:**
- AGI.TO SELL 1 shs @ CAD 45.47 | P&L: CAD +1.71 (+3.9%)
- TECK-B.TO SELL 2 shs @ CAD 90.50 | P&L: CAD +2.06 (+1.1%)
- PAAS.TO SELL 1 shs @ CAD 62.74 | P&L: CAD +1.79 (+2.9%)

**Active Position Performance & Drawdown Attribution:**
- **RUS.TO** (9.2% port): 1 shs @ CAD 91.17 (ACB: CAD 92.28) | Unrealized: **CAD -1.11 (-1.21%)** | Buffer to Stop: CAD 4.01 (4.4%)
- **CVE.TO** (9.4% port): 2 shs @ CAD 46.63 (ACB: CAD 47.09) | Unrealized: **CAD -0.92 (-0.98%)** | Buffer to Stop: CAD 1.89 (4.0%)
- **SAP.TO** (4.1% port): 1 shs @ CAD 40.44 (ACB: CAD 40.09) | Unrealized: **CAD +0.35 (+0.87%)** | Buffer to Stop: CAD 2.35 (5.8%)

**Autonomous Strategy Action:** Risk boundaries and tranche sizing remain verified within operating thresholds.


### Optimization Log [2026-10-21 16:10:20]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 988.52
**Daily NAV Change:** CAD -2.95 (-0.30%) vs Previous Close
**Cumulative Return:** CAD -11.48 (-1.15%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 588.60 (59.5%) | Equity: CAD 399.92 (40.5%)

**Active Position Performance & Drawdown Attribution:**
- **RUS.TO** (9.1% port): 1 shs @ CAD 89.93 (ACB: CAD 92.28) | Unrealized: **CAD -2.35 (-2.55%)** | Buffer to Stop: CAD 2.77 (3.1%)
- **TECK-B.TO** (17.8% port): 2 shs @ CAD 88.14 (ACB: CAD 89.00) | Unrealized: **CAD -1.71 (-0.96%)** | Buffer to Stop: CAD 3.72 (4.2%)
- **CVE.TO** (9.4% port): 2 shs @ CAD 46.52 (ACB: CAD 47.09) | Unrealized: **CAD -1.14 (-1.21%)** | Buffer to Stop: CAD 1.78 (3.8%)
- **SAP.TO** (4.1% port): 1 shs @ CAD 40.65 (ACB: CAD 40.09) | Unrealized: **CAD +0.56 (+1.40%)** | Buffer to Stop: CAD 2.56 (6.3%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **RUS.TO**: Position drawdown: -2.5% (Current: CAD 89.93, Stop: CAD 87.16, Buffer: CAD 2.77 / 3.1%)

**Autonomous Strategy Action:** Risk boundaries and tranche sizing remain verified within operating thresholds.


### Optimization Log [2026-10-22 16:10:40]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 966.12
**Daily NAV Change:** CAD -22.40 (-2.27%) vs Previous Close
**Cumulative Return:** CAD -33.88 (-3.39%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 230.61 (23.9%) | Equity: CAD 735.51 (76.1%)

**Realized Trades Today:**
- TECK-B.TO SELL 2 shs @ CAD 84.12 | P&L: CAD -9.77 (-5.5%)

**Active Position Performance & Drawdown Attribution:**
- **WPM.TO** (17.9% port): 1 shs @ CAD 172.82 (ACB: CAD 178.75) | Unrealized: **CAD -5.93 (-3.32%)** | Buffer to Stop: CAD 3.90 (2.3%)
- **CVE.TO** (9.3% port): 2 shs @ CAD 44.89 (ACB: CAD 47.09) | Unrealized: **CAD -4.40 (-4.67%)** | Buffer to Stop: CAD 0.15 (0.3%)
- **RUS.TO** (9.3% port): 1 shs @ CAD 89.65 (ACB: CAD 92.28) | Unrealized: **CAD -2.63 (-2.85%)** | Buffer to Stop: CAD 2.49 (2.8%)
- **PAAS.TO** (17.9% port): 3 shs @ CAD 57.53 (ACB: CAD 58.27) | Unrealized: **CAD -2.22 (-1.27%)** | Buffer to Stop: CAD 2.27 (4.0%)
- **AGI.TO** (17.6% port): 4 shs @ CAD 42.41 (ACB: CAD 42.96) | Unrealized: **CAD -2.20 (-1.28%)** | Buffer to Stop: CAD 1.65 (3.9%)
- **SAP.TO** (4.2% port): 1 shs @ CAD 41.03 (ACB: CAD 40.09) | Unrealized: **CAD +0.94 (+2.34%)** | Buffer to Stop: CAD 0.94 (2.3%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **CVE.TO**: Position drawdown: -4.7%; Near stop-loss: 0.3% buffer (Current: CAD 44.89, Stop: CAD 44.74, Buffer: CAD 0.15 / 0.3%)
- ⚠️ **RUS.TO**: Position drawdown: -2.8%; Near stop-loss: 2.8% buffer (Current: CAD 89.65, Stop: CAD 87.16, Buffer: CAD 2.49 / 2.8%)
- ⚠️ **SAP.TO**: Near stop-loss: 2.3% buffer (Current: CAD 41.03, Stop: CAD 40.09, Buffer: CAD 0.94 / 2.3%)
- ⚠️ **WPM.TO**: Position drawdown: -3.3%; Near stop-loss: 2.3% buffer (Current: CAD 172.82, Stop: CAD 168.92, Buffer: CAD 3.90 / 2.3%)

**Autonomous Strategy Action:** Risk boundaries and tranche sizing remain verified within operating thresholds.


### Optimization Log [2026-10-23 16:10:20]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 952.67
**Daily NAV Change:** CAD -13.45 (-1.39%) vs Previous Close
**Cumulative Return:** CAD -47.33 (-4.73%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 487.77 (51.2%) | Equity: CAD 464.90 (48.8%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Precious Metals**: CAD 336.40 (`35.3%` of NAV) ⚠️ [OVER 35% CAP]
- **Base Metals & Materials**: CAD 88.02 (`9.2%` of NAV)
- **Consumer & Packaging**: CAD 40.48 (`4.2%` of NAV)

**Realized Trades Today:**
- CVE.TO SELL 2 shs @ CAD 45.85 | P&L: CAD -2.49 (-2.6%)
- WPM.TO SELL 1 shs @ CAD 166.74 | P&L: CAD -12.01 (-6.7%)

**Active Position Performance & Drawdown Attribution:**
- **PAAS.TO** (Precious Metals, 17.7% port, 1d held): 3 shs @ CAD 56.20 (ACB: CAD 58.27) | Unrealized: **CAD -6.21 (-3.55%)** | Buffer to Stop: CAD 0.94 (1.7%)
- **RUS.TO** (Base Metals & Materials, 9.2% port, 3d held): 1 shs @ CAD 88.02 (ACB: CAD 92.28) | Unrealized: **CAD -4.26 (-4.62%)** | Buffer to Stop: CAD 0.86 (1.0%)
- **AGI.TO** (Precious Metals, 17.6% port, 1d held): 4 shs @ CAD 41.95 (ACB: CAD 42.96) | Unrealized: **CAD -4.04 (-2.35%)** | Buffer to Stop: CAD 1.19 (2.8%)
- **SAP.TO** (Consumer & Packaging, 4.2% port, 8d held): 1 shs @ CAD 40.48 (ACB: CAD 40.09) | Unrealized: **CAD +0.39 (+0.98%)** | Buffer to Stop: CAD 0.39 (1.0%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **RUS.TO**: Position drawdown: -4.6%; Near stop-loss: 1.0% buffer (Current: CAD 88.02, Stop: CAD 87.16, Buffer: CAD 0.86 / 1.0%)
- ⚠️ **SAP.TO**: Near stop-loss: 1.0% buffer (Current: CAD 40.48, Stop: CAD 40.09, Buffer: CAD 0.39 / 1.0%)
- ⚠️ **PAAS.TO**: Position drawdown: -3.6%; Near stop-loss: 1.7% buffer (Current: CAD 56.20, Stop: CAD 55.26, Buffer: CAD 0.94 / 1.7%)
- ⚠️ **AGI.TO**: Position drawdown: -2.4%; Near stop-loss: 2.8% buffer (Current: CAD 41.95, Stop: CAD 40.76, Buffer: CAD 1.19 / 2.8%)

**Autonomous Risk & Strategy Audit:**
- [RISK ALERT] Precious Metals sector concentration at 35.3% of NAV (cap 35%); new Precious Metals entries gated.


### Optimization Log [2026-10-26 16:10:20]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 948.43
**Daily NAV Change:** CAD -4.24 (-0.45%) vs Previous Close
**Cumulative Return:** CAD -51.57 (-5.16%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 907.93 (95.7%) | Equity: CAD 40.50 (4.3%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Consumer & Packaging**: CAD 40.50 (`4.3%` of NAV)

**Realized Trades Today:**
- PAAS.TO SELL 3 shs @ CAD 55.19 | P&L: CAD -10.06 (-5.8%)
- RUS.TO SELL 1 shs @ CAD 88.55 | P&L: CAD -4.17 (-4.5%)
- AGI.TO SELL 4 shs @ CAD 42.04 | P&L: CAD -4.51 (-2.6%)

**Active Position Performance & Drawdown Attribution:**
- **SAP.TO** (Consumer & Packaging, 4.3% port, 11d held): 1 shs @ CAD 40.50 (ACB: CAD 40.09) | Unrealized: **CAD +0.41 (+1.02%)** | Buffer to Stop: CAD 0.41 (1.0%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **SAP.TO**: Near stop-loss: 1.0% buffer (Current: CAD 40.50, Stop: CAD 40.09, Buffer: CAD 0.41 / 1.0%)

**Autonomous Strategy Action:** All sector caps (<= 35%), stop buffers, and daily drawdown metrics within operating thresholds.


### Optimization Log [2026-10-26 16:11:26]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 948.43
**Daily NAV Change:** CAD -4.24 (-0.45%) vs Previous Close
**Cumulative Return:** CAD -51.57 (-5.16%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 907.93 (95.7%) | Equity: CAD 40.50 (4.3%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Consumer & Packaging**: CAD 40.50 (`4.3%` of NAV)

**Realized Trades Today:**
- PAAS.TO SELL 3 shs @ CAD 55.19 | P&L: CAD -10.06 (-5.8%)
- RUS.TO SELL 1 shs @ CAD 88.55 | P&L: CAD -4.17 (-4.5%)
- AGI.TO SELL 4 shs @ CAD 42.04 | P&L: CAD -4.51 (-2.6%)

**Active Position Performance & Drawdown Attribution:**
- **SAP.TO** (Consumer & Packaging, 4.3% port, 11d held): 1 shs @ CAD 40.50 (ACB: CAD 40.09) | Unrealized: **CAD +0.41 (+1.02%)** | Buffer to Stop: CAD 0.41 (1.0%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **SAP.TO**: Near stop-loss: 1.0% buffer (Current: CAD 40.50, Stop: CAD 40.09, Buffer: CAD 0.41 / 1.0%)

**Autonomous Strategy Action:** All sector caps (<= 35%), stop buffers, and daily drawdown metrics within operating thresholds.


### Optimization Log [2026-10-27 16:10:19]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 948.29
**Daily NAV Change:** CAD -0.14 (-0.01%) vs Previous Close
**Cumulative Return:** CAD -51.71 (-5.17%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 907.93 (95.7%) | Equity: CAD 40.36 (4.3%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Consumer & Packaging**: CAD 40.36 (`4.3%` of NAV)

**Active Position Performance & Drawdown Attribution:**
- **SAP.TO** (Consumer & Packaging, 4.3% port, 12d held): 1 shs @ CAD 40.36 (ACB: CAD 40.09) | Unrealized: **CAD +0.27 (+0.67%)** | Buffer to Stop: CAD 0.27 (0.7%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **SAP.TO**: Near stop-loss: 0.7% buffer (Current: CAD 40.36, Stop: CAD 40.09, Buffer: CAD 0.27 / 0.7%)

**Autonomous Strategy Action:** All sector caps (<= 35%), stop buffers, and daily drawdown metrics within operating thresholds.


### Optimization Log [2026-10-28 16:10:37]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 947.26
**Daily NAV Change:** CAD -1.03 (-0.11%) vs Previous Close
**Cumulative Return:** CAD -52.74 (-5.27%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 793.70 (83.8%) | Equity: CAD 153.56 (16.2%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Energy & Uranium**: CAD 153.56 (`16.2%` of NAV)

**Realized Trades Today:**
- SAP.TO SELL 1 shs @ CAD 40.06 | P&L: CAD -0.23 (-0.6%)

**Active Position Performance & Drawdown Attribution:**
- **CNQ.TO** (Energy & Uranium, 16.2% port, 0d held): 2 shs @ CAD 76.78 (ACB: CAD 77.04) | Unrealized: **CAD -0.52 (-0.34%)** | Buffer to Stop: CAD 4.00 (5.2%)

**Autonomous Risk & Strategy Audit:**
- [SIGNAL ATTRIBUTION] Today's BUY fills: 1 Trend/Regular, 0 Capitulation Reversal.


### Optimization Log [2026-10-29 16:10:16]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 946.67
**Daily NAV Change:** CAD -0.59 (-0.06%) vs Previous Close
**Cumulative Return:** CAD -53.33 (-5.33%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 414.47 (43.8%) | Equity: CAD 532.20 (56.2%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Consumer & Packaging**: CAD 196.34 (`20.7%` of NAV)
- **Base Metals & Materials**: CAD 181.76 (`19.2%` of NAV)
- **Energy & Uranium**: CAD 154.10 (`16.3%` of NAV)

**Active Position Performance & Drawdown Attribution:**
- **RUS.TO** (Base Metals & Materials, 19.2% port, 0d held): 2 shs @ CAD 90.88 (ACB: CAD 91.27) | Unrealized: **CAD -0.78 (-0.43%)** [Fill: CAD 90.82, Gross: CAD +0.12, Entry Fee: CAD -0.90] | Buffer to Stop: CAD 4.74 (5.2%)
- **CCL-B.TO** (Consumer & Packaging, 20.7% port, 0d held): 2 shs @ CAD 98.17 (ACB: CAD 98.34) | Unrealized: **CAD -0.34 (-0.17%)** [Fill: CAD 97.85, Gross: CAD +0.64, Entry Fee: CAD -0.98] | Buffer to Stop: CAD 4.98 (5.1%)
- **CNQ.TO** (Energy & Uranium, 16.3% port, 1d held): 2 shs @ CAD 77.05 (ACB: CAD 77.04) | Unrealized: **CAD +0.02 (+0.01%)** [Fill: CAD 76.66, Gross: CAD +0.78, Entry Fee: CAD -0.76] | Buffer to Stop: CAD 4.27 (5.5%)

**Screened Universe Top Movers (2 non-held candidates):**
- **ATZ.TO**: Day Gain: `+2.32%` | Low Rebound: `+3.35%` | RSI: `69.27` | Vol: `0.81x` | Gate: `Overbought Ceiling (Flaw 4/5): RSI_7 (69.27) exceeds hard ceiling (68.`
- **KXS.TO**: Day Gain: `+0.08%` | Low Rebound: `+2.68%` | RSI: `52.82` | Vol: `1.31x` | Gate: `Trend Gatekeeper: EMA_Crossover is 'NEUTRAL (FILTERED)'`

**Autonomous Risk & Strategy Audit:**
- [SIGNAL ATTRIBUTION] Today's BUY fills: 3 Trend/Regular, 0 Capitulation Reversal.


### Optimization Log [2026-10-30 16:10:16]
**Session Type:** Daily Market Close Performance Assessment
**Portfolio Equity NAV:** CAD 934.92
**Daily NAV Change:** CAD -11.75 (-1.24%) vs Previous Close
**Universe Benchmark (32 TSX Equal-Wt):** -2.72% | **Relative Alpha:** +1.48%
**Cumulative Return:** CAD -65.08 (-6.51%) vs CAD 1,000.00 seed
**Capital Breakdown:** Cash: CAD 359.63 (38.5%) | Equity: CAD 575.29 (61.5%)

**Sector Exposure Breakdown (Cap 35.0%):**
- **Consumer & Packaging**: CAD 308.97 (`33.0%` of NAV)
- **Energy & Uranium**: CAD 266.32 (`28.5%` of NAV)

**Today's BUY Executions:**
- RCH.TO BUY 3 shs @ CAD 38.13 (`Regular Trend`)
- SU.TO BUY 1 shs @ CAD 110.57 (`Low-Volume Scaled`)

**Realized Trades Today:**
- RUS.TO SELL 2 shs @ CAD 86.05 | P&L: CAD -11.32 (-6.2%)

**Active Position Performance & Drawdown Attribution:**
- **RCH.TO** (Consumer & Packaging, 12.0% port, 0d held): 3 shs @ CAD 37.53 (ACB: CAD 38.32) | Unrealized: **CAD -2.37 (-2.06%)** [Fill: CAD 38.13, Gross: CAD -1.80, Entry Fee: CAD -0.57] | Buffer to Stop: CAD 1.35 (3.6%)
- **SU.TO** (Energy & Uranium, 11.8% port, 0d held): 1 shs @ CAD 110.12 (ACB: CAD 111.12) | Unrealized: **CAD -1.00 (-0.90%)** [Fill: CAD 110.57, Gross: CAD -0.45, Entry Fee: CAD -0.55] | Buffer to Stop: CAD 5.11 (4.6%)
- **CCL-B.TO** (Consumer & Packaging, 21.0% port, 1d held): 2 shs @ CAD 98.19 (ACB: CAD 98.34) | Unrealized: **CAD -0.30 (-0.15%)** [Fill: CAD 97.85, Gross: CAD +0.68, Entry Fee: CAD -0.98] | Buffer to Stop: CAD 5.00 (5.1%)
- **CNQ.TO** (Energy & Uranium, 16.7% port, 2d held): 2 shs @ CAD 78.10 (ACB: CAD 77.04) | Unrealized: **CAD +2.12 (+1.38%)** [Fill: CAD 76.66, Gross: CAD +2.88, Entry Fee: CAD -0.76] | Buffer to Stop: CAD 5.32 (6.8%)

**Risk Watchlist & Drawdown Drivers:**
- ⚠️ **RCH.TO**: Position drawdown: -2.1% (Current: CAD 37.53, Stop: CAD 36.18, Buffer: CAD 1.35 / 3.6%)

**Screened Universe Top Movers (2 non-held candidates):**
- **IMO.TO**: Day Gain: `+5.37%` | Low Rebound: `+8.09%` | RSI: `67.52` | Vol: `1.97x` | Gate: `Earnings Risk: Earnings call in 0 days (2026-10-30) - High binary gap risk`
- **KXS.TO**: Day Gain: `+0.8%` | Low Rebound: `+2.8%` | RSI: `57.55` | Vol: `0.8x` | Gate: `ELIGIBLE (25%)`

**Autonomous Risk & Strategy Audit:**
- [SIGNAL ATTRIBUTION] Today's BUY fills (2): 1 Regular Trend, 1 Low-Volume Scaled, 0 Capitulation Reversal.
