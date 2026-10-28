"""
MAPLE Strategy & Dynamic Sizing Engine
Houses scoring rules, dynamic tranche calculation (15% to 35%),
and logic parameters that can be autonomously evolved by maple_optimizer.py.
"""

from typing import Dict, Any, Tuple, Optional


class MapleStrategy:
    """Strategy parameters and dynamic scoring rules.

    This class and its parameters are designed for autonomous self-tuning
    by MAPLE during daily/weekly reviews.
    """

    VERSION = "1.0.0"

    # Base Sizing Bounds
    MIN_TRANCHE_PCT = 0.15
    BASE_TRANCHE_PCT = 0.25
    MAX_TRANCHE_PCT = 0.35

    # Thresholds
    VOLUME_CAPITULATION_RATIO = 1.25
    CAPITULATION_MIN_BOUNCE_PCT = 1.50
    CAPITULATION_MAX_TRANCHE_PCT = 0.15
    VOLUME_SINGLE_BYPASS_RATIO = 1.50
    VOLUME_BOOST_RATIO = 1.60
    ADX_TREND_THRESHOLD = 20.0
    ADX_STRONG_THRESHOLD = 28.0
    RSI_OVERSOLD_MAX = 35.0
    RSI_SWEETSPOT_LOW = 40.0
    RSI_SWEETSPOT_HIGH = 62.0
    RSI_STANDARD_MAX = 65.0
    RSI_OVERBOUGHT_LIMIT = 68.0
    MAX_EMA5_EXTENSION_PCT = 3.0

    # Stop Loss & Profit Target Heuristics
    STOP_LOSS_PCT = 5.0
    BREAKEVEN_TRIGGER_PCT = 2.0
    ATR_TARGET_MULTIPLIER = 1.5
    STAGNATION_DAYS = 4
    COMMISSION_PER_ORDER_CAD = 1.00
    MIN_NET_PROFIT_PCT = 2.5

    @classmethod
    def _sync_from_config(cls):
        """Syncs tunable strategy parameters from maple_config.json."""
        try:
            from maple_ledger import load_config
            cfg = load_config()
            sp = cfg.get("sizing_parameters", {})
            cls.MIN_TRANCHE_PCT = float(sp.get("min_tranche_pct", cls.MIN_TRANCHE_PCT))
            cls.BASE_TRANCHE_PCT = float(sp.get("base_tranche_pct", cls.BASE_TRANCHE_PCT))
            cls.MAX_TRANCHE_PCT = float(sp.get("max_tranche_pct", cls.MAX_TRANCHE_PCT))
            cls.VOLUME_CAPITULATION_RATIO = float(sp.get("volume_capitulation_ratio", cls.VOLUME_CAPITULATION_RATIO))
            cls.CAPITULATION_MIN_BOUNCE_PCT = float(sp.get("capitulation_min_bounce_pct", cls.CAPITULATION_MIN_BOUNCE_PCT))
            cls.CAPITULATION_MAX_TRANCHE_PCT = float(sp.get("capitulation_max_tranche_pct", cls.CAPITULATION_MAX_TRANCHE_PCT))
            cls.VOLUME_BOOST_RATIO = float(sp.get("volume_boost_threshold", cls.VOLUME_BOOST_RATIO))
            cls.ADX_STRONG_THRESHOLD = float(sp.get("adx_strong_trend", cls.ADX_STRONG_THRESHOLD))
            cls.STOP_LOSS_PCT = float(cfg.get("stop_loss_pct", cls.STOP_LOSS_PCT))
            cls.COMMISSION_PER_ORDER_CAD = float(cfg.get("commission_per_order_cad", cls.COMMISSION_PER_ORDER_CAD))
            cls.MIN_NET_PROFIT_PCT = float(cfg.get("min_net_profit_pct", cls.MIN_NET_PROFIT_PCT))
        except Exception:
            pass

    @classmethod
    def calculate_tranche_size(
        cls, stock_data: Dict[str, Any], signal_type: str = "REGULAR"
    ) -> Tuple[float, str]:
        """Calculates dynamic tranche percentage (between MIN and MAX) based on technical setup.
        Enforces strict entry gatekeepers for EMA_Crossover, Price vs EMA_5, and single-bypass limits.
        """
        cls._sync_from_config()
        # 1. Earnings Risk Gatekeeper: Block buying within 3 days of an earnings report
        days_to_earnings = stock_data.get("days_to_earnings")
        if isinstance(days_to_earnings, (int, float)) and 0 <= days_to_earnings <= 3:
            ed_str = stock_data.get("earnings_date", "Soon")
            return 0.0, f"BLOCKED by Earnings Risk: Earnings call in {days_to_earnings} days ({ed_str}) - High binary gap risk"

        vol_ratio = stock_data.get("Vol_Ratio")
        adx = stock_data.get("ADX_14")
        rsi = stock_data.get("RSI_7")
        price = stock_data.get("Price")
        open_px = stock_data.get("Open")
        pct_from_low = stock_data.get("Pct_From_Low")
        ema_5 = stock_data.get("EMA_5")
        ema_cross = str(stock_data.get("EMA_Crossover", ""))

        # Tightened Contrarian Capitulation Reversal Path:
        # Requires RSI < 35, Vol_Ratio >= 1.25x, confirmed green candle (Price > Open),
        # and >= 1.50% intraday rebound off low; caps starter size at 15% (no volume-surge boost).
        is_capitulation = ("CAPITULATION" in signal_type.upper()) or (
            isinstance(rsi, (int, float))
            and rsi < cls.RSI_OVERSOLD_MAX
            and isinstance(vol_ratio, (int, float))
            and vol_ratio >= cls.VOLUME_CAPITULATION_RATIO
        )

        if is_capitulation:
            if not (isinstance(rsi, (int, float)) and rsi < cls.RSI_OVERSOLD_MAX):
                return 0.0, f"BLOCKED by Capitulation Filter: RSI_7 ({rsi}) must be < {cls.RSI_OVERSOLD_MAX}"
            if not (isinstance(vol_ratio, (int, float)) and vol_ratio >= cls.VOLUME_CAPITULATION_RATIO):
                return 0.0, f"BLOCKED by Capitulation Filter: Vol_Ratio ({vol_ratio}x) below {cls.VOLUME_CAPITULATION_RATIO}x washout minimum"
            if not (isinstance(price, (int, float)) and isinstance(open_px, (int, float)) and open_px > 0 and price > open_px):
                return 0.0, f"BLOCKED by Capitulation Knife-Catch Guard: Red/flat intraday candle (Price ${price} <= Open ${open_px})"
            if not (isinstance(pct_from_low, (int, float)) and pct_from_low >= cls.CAPITULATION_MIN_BOUNCE_PCT):
                return 0.0, f"BLOCKED by Capitulation Bounce Filter: Rebound off low ({pct_from_low}%) < {cls.CAPITULATION_MIN_BOUNCE_PCT:.2f}% minimum"
            cap_pct = round(min(cls.MIN_TRANCHE_PCT, cls.CAPITULATION_MAX_TRANCHE_PCT), 4)
            return cap_pct, (
                f"Capitulation Reversal Starter (RSI {rsi}, Vol {vol_ratio}x, "
                f"+{pct_from_low:.2f}% off low, Green > Open ${open_px:.2f}) - capped at {cap_pct*100:.0f}%"
            )

        # 2. Hard Momentum & Structural Entry Gatekeepers (for all non-capitulation entries)
        single_bypass_used = False
        if True:
            # Gate A: Confirmed 6-part Bullish EMA Crossover
            if ema_cross != "BULLISH (EMA5 > EMA9)":
                return 0.0, f"BLOCKED by Trend Gatekeeper: EMA_Crossover is '{ema_cross}' (requires confirmed 6-part BULLISH crossover)"

            # Gate B: Live Price vs EMA_5 (Flaw 2 intraday rejection & Flaw 5 >3% overextension cap)
            if isinstance(price, (int, float)) and isinstance(ema_5, (int, float)) and ema_5 > 0:
                if price < ema_5:
                    return 0.0, f"BLOCKED by Price Rejection Filter (Flaw 2): Live Price (${price:.2f}) is below EMA_5 (${ema_5:.2f})"
                ema5_ext_pct = ((price - ema_5) / ema_5) * 100.0
                if ema5_ext_pct > cls.MAX_EMA5_EXTENSION_PCT:
                    return 0.0, f"BLOCKED by Overextension Cap (Flaw 5): Live Price (${price:.2f}) is +{ema5_ext_pct:.2f}% above EMA_5 (${ema_5:.2f}), exceeding {cls.MAX_EMA5_EXTENSION_PCT:.1f}% limit"

            # Gate C: Hard Overbought Ceiling & Single-Bypass Limit (Flaw 4)
            if isinstance(rsi, (int, float)) and rsi > cls.RSI_OVERBOUGHT_LIMIT:
                return 0.0, f"BLOCKED by Overbought Ceiling (Flaw 4/5): RSI_7 ({rsi}) exceeds hard ceiling ({cls.RSI_OVERBOUGHT_LIMIT})"

            if isinstance(vol_ratio, (int, float)) and vol_ratio < 0.80:
                return 0.0, f"BLOCKED by Low Volume: Vol_Ratio ({vol_ratio}x) below 0.80x minimum threshold"

            adx_ok = isinstance(adx, (int, float)) and adx >= cls.ADX_TREND_THRESHOLD
            rsi_std_ok = isinstance(rsi, (int, float)) and rsi <= cls.RSI_STANDARD_MAX
            has_bypass_vol = isinstance(vol_ratio, (int, float)) and vol_ratio >= cls.VOLUME_SINGLE_BYPASS_RATIO

            if not adx_ok and not rsi_std_ok:
                return 0.0, f"BLOCKED by Double-Bypass Guard (Flaw 4): Weak ADX ({adx} < {cls.ADX_TREND_THRESHOLD}) AND Elevated RSI ({rsi} > {cls.RSI_STANDARD_MAX}) cannot both be bypassed by volume"
            elif not adx_ok or not rsi_std_ok:
                if not has_bypass_vol:
                    return 0.0, f"BLOCKED by Trend/RSI Filter: ADX={adx}, RSI={rsi} requires Vol_Ratio >= {cls.VOLUME_SINGLE_BYPASS_RATIO}x single-bypass (got {vol_ratio}x)"
                single_bypass_used = True

        score = 0
        reasons = []

        if isinstance(vol_ratio, (int, float)):
            if vol_ratio >= cls.VOLUME_BOOST_RATIO:
                score += 2
                reasons.append(f"Volume Surge {vol_ratio}x (+2)")
            elif vol_ratio >= cls.VOLUME_CAPITULATION_RATIO:
                score += 1
                reasons.append(f"Above-avg Volume {vol_ratio}x (+1)")
            elif vol_ratio < 0.8:
                score -= 1
                reasons.append(f"Low Volume {vol_ratio}x (-1)")

        if isinstance(adx, (int, float)):
            if adx >= cls.ADX_STRONG_THRESHOLD:
                score += 1
                reasons.append(f"Strong Trend ADX {adx} (+1)")
            elif adx < cls.ADX_TREND_THRESHOLD:
                score -= 1
                reasons.append(f"Weak Trend ADX {adx} (-1)")

        if isinstance(rsi, (int, float)):
            if cls.RSI_SWEETSPOT_LOW <= rsi <= cls.RSI_SWEETSPOT_HIGH:
                score += 1
                reasons.append(f"Prime RSI {rsi} (+1)")
            elif rsi > cls.RSI_STANDARD_MAX:
                score -= 1
                reasons.append(f"Elevated RSI {rsi} (-1)")

        # Map score to percentage
        if score >= 3:
            tranche_pct = cls.MAX_TRANCHE_PCT
        elif score == 2:
            tranche_pct = 0.30
        elif score in [0, 1]:
            tranche_pct = cls.BASE_TRANCHE_PCT
        elif score == -1:
            tranche_pct = 0.20
        else:
            tranche_pct = cls.MIN_TRANCHE_PCT

        # Cap tranche at BASE_TRANCHE_PCT (25%) if a single-bypass was used (prevents volume surge from over-sizing a weak-ADX or high-RSI entry)
        if single_bypass_used and tranche_pct > cls.BASE_TRANCHE_PCT:
            tranche_pct = cls.BASE_TRANCHE_PCT
            reasons.append("Capped at 25% by Single-Bypass Rule")

        # Cap for scaled entries
        if "SCALED" in signal_type.upper() or "LOW-VOLUME" in signal_type.upper():
            tranche_pct = min(tranche_pct, 0.20)
            reasons.append("Capped by Scaled Entry Rule")

        reason_str = ", ".join(reasons) if reasons else "Neutral baseline"
        return round(tranche_pct, 4), reason_str

    @classmethod
    def calculate_targets(
        cls,
        current_price: float,
        stock_data: Dict[str, Any],
        shares: float = 1.0,
        cost_basis: Optional[float] = None,
    ) -> Tuple[float, float]:
        """Calculates Target Sell Price and Stop Loss Price.
        Explicitly factors in two-way trade commissions (entry + exit) to guarantee
        that the target yields a meaningful NET return on invested capital.
        """
        cls._sync_from_config()
        base_price = float(cost_basis) if (cost_basis and cost_basis > 0) else float(current_price)
        eff_shares = max(1.0, float(shares or 1.0))

        # Two-way round-trip commission drag per share ($1.00 buy + $1.00 sell = $2.00 min on IBKR)
        roundtrip_comm_per_share = (2.0 * cls.COMMISSION_PER_ORDER_CAD) / eff_shares

        # Minimum net hurdle: base price + round-trip commissions + net profit %
        min_net_hurdle = base_price + roundtrip_comm_per_share + (base_price * (cls.MIN_NET_PROFIT_PCT / 100.0))
        min_target = round(min_net_hurdle, 2)

        atr = stock_data.get("ATR_5")
        bb_mid = stock_data.get("BB_Mid")

        stop_loss = round(base_price * (1.0 - cls.STOP_LOSS_PCT / 100.0), 2)

        # 2. Ex-Dividend Adjustment: Account for mechanical price drop if ex-date is within 3 days
        days_to_ex_div = stock_data.get("days_to_ex_dividend")
        if isinstance(days_to_ex_div, (int, float)) and 0 <= days_to_ex_div <= 3:
            stop_loss = round(stop_loss * 0.99, 2)

        target = None
        if isinstance(bb_mid, (int, float)) and bb_mid >= min_target:
            target = round(float(bb_mid), 2)
        elif isinstance(atr, (int, float)) and atr > 0:
            target = round(base_price + (atr * cls.ATR_TARGET_MULTIPLIER), 2)
        else:
            target = round(base_price * 1.035, 2)  # 3.5% fallback target

        target = max(target, min_target)
        return target, stop_loss
