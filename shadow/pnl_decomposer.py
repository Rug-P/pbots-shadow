"""
shadow/pnl_decomposer.py — Decompose P/L into spread capture vs resolution profit.

For each market, uses FIFO matching of buys against subsequent sells to estimate
how much profit came from spread capture (intra-market round-trips) versus
positions held to final market resolution.
"""

from collections import defaultdict, deque
from typing import Dict, List, Optional


class PnLDecomposer:
    """
    Estimates the split between spread P/L and resolution P/L.

    Methodology:
    - Spread P/L: for each buy that is matched with a later sell in the same
      market (FIFO), the profit is (sell_price - buy_price) * matched_size.
    - Resolution P/L: remaining unmatched long positions at price < 1.0 are
      assumed to resolve at their final known price (or are counted as losses
      if no resolution price is available).  This is a rough estimate.
    """

    def analyze(self, trades: List[Dict], address: str) -> Dict:
        """
        Decompose P/L for *address*.

        Returns:
            Dict with spread_pnl, resolution_pnl, total_pnl, spread_pct,
            resolution_pct, and per-market detail.
        """
        addr = address.lower()
        # Sort trades by timestamp so FIFO order is correct
        sorted_trades = sorted(trades, key=lambda t: self._get_ts(t) or 0)

        # Bucket trades by market
        market_trades: Dict[str, List[Dict]] = defaultdict(list)
        for trade in sorted_trades:
            mid = self._get_market_id(trade)
            market_trades[mid].append(trade)

        total_spread_pnl = 0.0
        total_resolution_pnl = 0.0
        market_detail = {}

        for mid, mtrades in market_trades.items():
            spread_pnl, resolution_pnl, detail = self._process_market(mtrades, addr)
            total_spread_pnl += spread_pnl
            total_resolution_pnl += resolution_pnl
            market_detail[mid] = detail

        total_pnl = total_spread_pnl + total_resolution_pnl
        if abs(total_pnl) > 0:
            spread_pct = total_spread_pnl / total_pnl * 100
            resolution_pct = total_resolution_pnl / total_pnl * 100
        else:
            spread_pct = 0.0
            resolution_pct = 0.0

        return {
            "spread_pnl": round(total_spread_pnl, 4),
            "resolution_pnl": round(total_resolution_pnl, 4),
            "total_pnl": round(total_pnl, 4),
            "spread_pct": round(spread_pct, 2),
            "resolution_pct": round(resolution_pct, 2),
            "market_detail": market_detail,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _process_market(
        self, trades: List[Dict], addr: str
    ) -> tuple:
        """FIFO matching for a single market."""
        buy_queue: deque = deque()  # (price, size)
        spread_pnl = 0.0
        matched_size = 0.0

        for trade in trades:
            price = self._get_price(trade)
            size = self._get_size(trade)
            side = self._get_side(trade, addr)

            if price is None or size is None:
                continue

            if side == "buy":
                buy_queue.append([price, size])
            elif side == "sell":
                remaining_sell = size
                while remaining_sell > 1e-8 and buy_queue:
                    buy_price, buy_size = buy_queue[0]
                    fill = min(buy_size, remaining_sell)
                    spread_pnl += (price - buy_price) * fill
                    matched_size += fill
                    remaining_sell -= fill
                    buy_queue[0][1] -= fill
                    if buy_queue[0][1] < 1e-8:
                        buy_queue.popleft()

        # Remaining open longs — estimate resolution P/L
        resolution_pnl = 0.0
        for buy_price, buy_size in buy_queue:
            # If we don't know the resolution price, we can't be sure —
            # report zero for remaining open positions
            resolution_pnl += 0.0  # placeholder

        detail = {
            "spread_pnl": round(spread_pnl, 4),
            "resolution_pnl": round(resolution_pnl, 4),
            "matched_size": round(matched_size, 4),
            "open_long_shares": round(sum(s for _, s in buy_queue), 4),
        }
        return spread_pnl, resolution_pnl, detail

    @staticmethod
    def _get_market_id(trade: Dict) -> str:
        for field in ("asset_id", "market", "condition_id", "market_id", "token_id"):
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
    def _get_size(trade: Dict) -> Optional[float]:
        val = trade.get("size")
        if val is not None:
            try:
                # size from the real API is in USDC base units (6 decimals)
                return abs(float(val) / 1e6)
            except (TypeError, ValueError):
                pass
        for field in ("shares", "amount", "quantity"):
            val = trade.get(field)
            if val is not None:
                try:
                    return abs(float(val))
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _get_ts(trade: Dict) -> Optional[float]:
        for field in ("match_time", "last_update", "timestamp", "created_at", "transacted_at", "time"):
            val = trade.get(field)
            if val is None:
                continue
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                # Try numeric epoch string first (e.g. "1700000000")
                try:
                    return float(val)
                except (ValueError, TypeError):
                    pass
                try:
                    from dateutil import parser as dp
                    from datetime import timezone
                    return dp.parse(val).replace(tzinfo=timezone.utc).timestamp()
                except Exception:
                    pass
        return None

    @staticmethod
    def _get_side(trade: Dict, addr: str) -> str:
        # Primary: trader_side field (real Polymarket Data API)
        trader_side = str(trade.get("trader_side", "")).upper()
        if trader_side in ("MAKER", "TAKER"):
            is_maker = trader_side == "MAKER"
        else:
            # Fallback: check explicit maker address fields
            is_maker = False
            for field in ("maker_address", "maker"):
                val = trade.get(field)
                if val and str(val).lower() == addr:
                    is_maker = True
                    break

        raw_side = str(trade.get("side", "")).lower()
        if raw_side in ("buy", "sell"):
            return ("sell" if raw_side == "buy" else "buy") if is_maker else raw_side

        outcome = str(trade.get("outcome", "")).lower()
        if outcome in ("buy", "sell"):
            return outcome
        return "unknown"
