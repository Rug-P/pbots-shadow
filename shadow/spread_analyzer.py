"""
shadow/spread_analyzer.py — Analyse the bid-ask spread captured by a target wallet.

Groups trades by market, separates buys from sells, and estimates the average
spread captured across all markets and for the top-10 most profitable markets.
"""

from collections import defaultdict
from typing import Dict, List, Optional


class SpreadAnalyzer:
    """
    Estimates the spread captured by a wallet per market.

    For each market the wallet traded in, the analyzer computes the average
    buy price and average sell price and uses the difference as a proxy for
    the spread captured.  Only markets where both buys and sells occurred are
    included in the spread calculation.
    """

    TOP_N = 10  # markets to include in the top-markets list

    def analyze(self, trades: List[Dict], address: str) -> Dict:
        """
        Analyse spread capture across all markets.

        Args:
            trades: Raw trade list from the Polymarket Data API.
            address: Target wallet address (case-insensitive).

        Returns:
            Dict with per-market breakdown and aggregate statistics.
        """
        addr = address.lower()
        market_trades: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: {"buys": [], "sells": []}
        )

        for trade in trades:
            market_id = self._get_market_id(trade)
            price = self._get_price(trade)
            if price is None:
                continue

            side = self._get_side(trade, addr)
            if side == "buy":
                market_trades[market_id]["buys"].append(price)
            elif side == "sell":
                market_trades[market_id]["sells"].append(price)

        # Build per-market stats
        market_stats = {}
        for mid, data in market_trades.items():
            buys = data["buys"]
            sells = data["sells"]
            avg_buy = sum(buys) / len(buys) if buys else None
            avg_sell = sum(sells) / len(sells) if sells else None

            spread = None
            if avg_buy is not None and avg_sell is not None:
                spread = avg_sell - avg_buy

            price_sum_proxy = (sum(buys) + sum(sells)) / 2  # rough price-sum proxy, not real USDC volume
            market_stats[mid] = {
                "market_id": mid,
                "buy_count": len(buys),
                "sell_count": len(sells),
                "avg_buy_price": round(avg_buy, 6) if avg_buy is not None else None,
                "avg_sell_price": round(avg_sell, 6) if avg_sell is not None else None,
                "spread_captured": round(spread, 6) if spread is not None else None,
                "volume_proxy": round(price_sum_proxy, 2),
            }

        # Aggregate stats (only markets with a valid spread)
        valid = [
            m for m in market_stats.values() if m["spread_captured"] is not None
        ]
        spreads = [m["spread_captured"] for m in valid]

        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        min_spread = min(spreads) if spreads else 0.0
        max_spread = max(spreads) if spreads else 0.0

        # Total estimated spread P/L (very rough — we don't have share counts)
        total_spread_pnl_est = sum(
            m["spread_captured"] * (m["buy_count"] + m["sell_count"]) / 2
            for m in valid
        )

        # Top markets by spread profit proxy
        top_markets = sorted(
            valid,
            key=lambda m: m["spread_captured"] * (m["buy_count"] + m["sell_count"]),
            reverse=True,
        )[: self.TOP_N]

        tightest: Optional[Dict] = None
        widest: Optional[Dict] = None
        if valid:
            tightest = min(valid, key=lambda m: m["spread_captured"])
            widest = max(valid, key=lambda m: m["spread_captured"])

        return {
            "total_markets": len(market_stats),
            "markets_with_spread": len(valid),
            "avg_spread": round(avg_spread, 6),
            "min_spread": round(min_spread, 6),
            "max_spread": round(max_spread, 6),
            "total_spread_pnl_est": round(total_spread_pnl_est, 2),
            "tightest_market": tightest,
            "widest_market": widest,
            "top_markets": top_markets,
            "all_markets": market_stats,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_market_id(trade: Dict) -> str:
        for field in ("market", "condition_id", "asset_id", "market_id", "token_id"):
            val = trade.get(field)
            if val:
                return str(val)
        return "unknown"

    @staticmethod
    def _get_price(trade: Dict) -> Optional[float]:
        for field in ("price", "avg_price", "execution_price"):
            val = trade.get(field)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _get_side(trade: Dict, addr: str) -> str:
        """
        Determine trade side from the perspective of *addr*.

        For maker trades the side field is from the taker's perspective, so we
        invert it; for taker trades we use the field as-is.
        """
        raw_side = str(trade.get("side", "")).lower()
        is_maker = False

        for field in ("maker_address", "maker"):
            val = trade.get(field)
            if val and str(val).lower() == addr:
                is_maker = True
                break

        if raw_side in ("buy", "sell"):
            if is_maker:
                # The side field is the taker's side, so flip for the maker
                return "sell" if raw_side == "buy" else "buy"
            return raw_side

        # Fall back to outcome or type fields
        outcome = str(trade.get("outcome", "")).lower()
        if outcome in ("buy", "sell"):
            return outcome
        return "unknown"
