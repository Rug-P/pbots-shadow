"""
shadow/classifier.py — Classify the trading strategy of a target wallet.

Determines whether the wallet behaves primarily as a market maker, taker, or hybrid,
based on maker/taker fill counts extracted from trade records.
"""

from typing import Dict, List


class StrategyClassifier:
    """
    Classifies a wallet's strategy based on maker vs taker fill ratio.

    Polymarket trade records contain fields that identify which side of each
    trade each wallet was on.  This class counts those occurrences and derives
    a strategy label with a confidence rating.
    """

    # Ratio thresholds
    MAKER_DOMINANT = 0.85
    MAKER_HYBRID = 0.60
    TAKER_DOMINANT = 0.85
    TAKER_HYBRID = 0.60

    # Confidence thresholds (sample size)
    HIGH_CONFIDENCE = 500
    MEDIUM_CONFIDENCE = 100

    def classify(self, trades: List[Dict], address: str) -> Dict:
        """
        Classify the strategy for *address* given its *trades*.

        Args:
            trades: List of raw trade dicts from the Polymarket Data API.
            address: The wallet address being analysed (case-insensitive).

        Returns:
            Dict with strategy_type, maker_count, taker_count, unknown_count,
            total_trades, maker_ratio, taker_ratio, and confidence.
        """
        addr = address.lower()
        maker_count = 0
        taker_count = 0
        unknown_count = 0

        for trade in trades:
            role = self._get_role(trade, addr)
            if role == "maker":
                maker_count += 1
            elif role == "taker":
                taker_count += 1
            else:
                unknown_count += 1

        total = len(trades)
        known = maker_count + taker_count

        if known == 0:
            maker_ratio = 0.0
            taker_ratio = 0.0
        else:
            maker_ratio = maker_count / known
            taker_ratio = taker_count / known

        strategy_type = self._classify_type(maker_ratio, taker_ratio)
        confidence = self._confidence(total)

        return {
            "strategy_type": strategy_type,
            "maker_count": maker_count,
            "taker_count": taker_count,
            "unknown_count": unknown_count,
            "total_trades": total,
            "maker_ratio": round(maker_ratio, 4),
            "taker_ratio": round(taker_ratio, 4),
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_role(self, trade: Dict, addr: str) -> str:
        """
        Determine whether *addr* was the maker or taker in *trade*.

        Tries several field name variants used by different API versions.
        """
        # --- Explicit maker/taker address fields ---
        for field in ("maker_address", "maker"):
            val = trade.get(field)
            if val and str(val).lower() == addr:
                return "maker"

        for field in ("taker_address", "taker"):
            val = trade.get(field)
            if val and str(val).lower() == addr:
                return "taker"

        # --- Infer from order_type / type field ---
        order_type = str(trade.get("order_type", trade.get("type", ""))).lower()
        if "limit" in order_type or "maker" in order_type:
            return "maker"
        if "market" in order_type or "taker" in order_type:
            return "taker"

        # --- Infer from is_maker boolean ---
        is_maker = trade.get("is_maker")
        if is_maker is True:
            return "maker"
        if is_maker is False:
            return "taker"

        return "unknown"

    def _classify_type(self, maker_ratio: float, taker_ratio: float) -> str:
        if maker_ratio >= self.MAKER_DOMINANT:
            return "MARKET_MAKER"
        if taker_ratio >= self.TAKER_DOMINANT:
            return "AGGRESSIVE_TAKER"
        if maker_ratio >= self.MAKER_HYBRID:
            return "HYBRID_MAKER"
        if taker_ratio >= self.TAKER_HYBRID:
            return "HYBRID_TAKER"
        return "BALANCED"

    def _confidence(self, total: int) -> str:
        if total >= self.HIGH_CONFIDENCE:
            return "HIGH"
        if total >= self.MEDIUM_CONFIDENCE:
            return "MEDIUM"
        return "LOW"
