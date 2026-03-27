"""
shadow/inventory_tracker.py — Track net inventory / position over time.

Reconstructs the running net position for each market to determine whether the
wallet is delta-neutral (pure market maker) or takes directional risk.
"""

from collections import defaultdict
from typing import Dict, List, Optional

from dateutil import parser as dateutil_parser
from datetime import timezone


class InventoryTracker:
    """
    Tracks net position per market and overall inventory risk.

    For each market, buys increase and sells decrease the running position.
    The delta-neutral score measures how close the wallet stays to zero net
    exposure across all its open positions.
    """

    def analyze(self, trades: List[Dict], address: str) -> Dict:
        """
        Analyse inventory management for *address* given its *trades*.

        Returns:
            Dict with max_exposure, avg_exposure, markets_with_open_inventory,
            delta_neutral_score, and per-market position snapshots.
        """
        addr = address.lower()
        # {market_id: [(timestamp, delta), ...]}
        market_timeline: Dict[str, List] = defaultdict(list)

        for trade in trades:
            mid = self._get_market_id(trade)
            size = self._get_size(trade)
            ts = self._get_timestamp(trade)
            side = self._get_side(trade, addr)

            if side == "unknown":
                continue  # skip trades where side cannot be determined

            delta = size if side == "buy" else -size
            market_timeline[mid].append((ts, delta))

        # Per-market stats
        market_profiles = {}
        all_net_positions = []
        all_holding_durations = []

        for mid, events in market_timeline.items():
            events.sort(key=lambda x: x[0] or 0)
            running = 0.0
            peak_long = 0.0
            peak_short = 0.0
            snapshots = []
            open_since: Optional[float] = None

            for ts, delta in events:
                running += delta
                snapshots.append(running)
                if abs(running) > 0 and open_since is None:
                    open_since = ts
                if running > peak_long:
                    peak_long = running
                if running < peak_short:
                    peak_short = running
                # When position crosses zero, record holding duration
                if abs(running) < 1e-8 and open_since is not None and ts is not None:
                    if ts > open_since:
                        all_holding_durations.append(ts - open_since)
                    open_since = None

            final_position = running
            all_net_positions.append(abs(final_position))

            market_profiles[mid] = {
                "market_id": mid,
                "final_net_position": round(final_position, 4),
                "peak_long": round(peak_long, 4),
                "peak_short": round(peak_short, 4),
                "trade_count": len(events),
                "has_open_inventory": abs(final_position) > 0.01,
            }

        markets_with_inventory = sum(
            1 for m in market_profiles.values() if m["has_open_inventory"]
        )

        max_exposure = max(all_net_positions) if all_net_positions else 0.0
        avg_exposure = (
            sum(all_net_positions) / len(all_net_positions) if all_net_positions else 0.0
        )

        # Delta-neutral score: fraction of time position is near zero
        # Proxy: fraction of markets that resolved to near-zero net position
        total = len(market_profiles)
        neutral = total - markets_with_inventory
        delta_neutral_score = neutral / total if total > 0 else 0.0

        avg_holding_s = (
            sum(all_holding_durations) / len(all_holding_durations)
            if all_holding_durations
            else None
        )

        return {
            "total_markets": total,
            "markets_with_open_inventory": markets_with_inventory,
            "max_exposure": round(max_exposure, 4),
            "avg_exposure": round(avg_exposure, 4),
            "delta_neutral_score": round(delta_neutral_score, 4),
            "avg_holding_time_s": round(avg_holding_s, 1) if avg_holding_s else None,
            "market_profiles": market_profiles,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_market_id(trade: Dict) -> str:
        for field in ("asset_id", "market", "condition_id", "market_id", "token_id"):
            val = trade.get(field)
            if val:
                return str(val)
        return "unknown"

    @staticmethod
    def _get_size(trade: Dict) -> float:
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
        return 0.0

    @staticmethod
    def _get_timestamp(trade: Dict) -> Optional[float]:
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
                    return dateutil_parser.parse(val).replace(tzinfo=timezone.utc).timestamp()
                except (ValueError, OverflowError):
                    pass
        return None

    @staticmethod
    def _get_side(trade: Dict, addr: str) -> str:
        # Primary: trader_side field (real Polymarket Data API)
        trader_side = str(trade.get("trader_side", "")).upper()
        if trader_side in ("MAKER", "TAKER"):
            is_maker = trader_side == "MAKER"
        else:
            # Fallback: _fetch_role injected by fetcher
            fetch_role = str(trade.get("_fetch_role", "")).upper()
            if fetch_role in ("MAKER", "TAKER"):
                is_maker = fetch_role == "MAKER"
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
            if is_maker:
                return "sell" if raw_side == "buy" else "buy"
            return raw_side

        # Fallback: try outcome
        outcome = str(trade.get("outcome", "")).lower()
        if outcome in ("buy", "sell"):
            return outcome
        return "unknown"  # don't assume a side to avoid silent data errors
