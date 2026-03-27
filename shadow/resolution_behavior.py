"""
shadow/resolution_behavior.py — Analyse how a wallet behaves near market resolution.

Compares trading activity in the windows before market close against the
wallet's baseline activity to classify the risk-management behaviour pattern.
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from dateutil import parser as dateutil_parser


class ResolutionAnalyzer:
    """
    Classifies how the target wallet behaves in the hours leading up to
    market resolution.

    Patterns:
    - STOPS_EARLY    — activity drops sharply well before close
    - WIDENS_SPREAD  — fewer fills but activity continues (needs LOB data)
    - CLOSES_POSITIONS — net sell-off of inventory near close
    - CONTINUES_NORMAL — activity unchanged near resolution
    - INSUFFICIENT_DATA — not enough data to classify
    """

    WINDOWS_HOURS = [24, 12, 6, 2, 1]

    def analyze(self, trades: List[Dict], market_metadata: Dict[str, Dict]) -> Dict:
        """
        Analyse resolution behaviour for the provided *trades*.

        Args:
            trades: Raw trade list.
            market_metadata: Dict mapping market_id → metadata dict.
                             Metadata must contain an 'endDate' or 'end_date_iso'
                             field for the market to be included in the analysis.

        Returns:
            Dict with per-market analysis and an overall behavioural pattern.
        """
        # Group trades by market
        market_trades: Dict[str, List[Dict]] = defaultdict(list)
        for trade in trades:
            mid = self._get_market_id(trade)
            market_trades[mid].append(trade)

        results = {}
        patterns = []

        for mid, mtrades in market_trades.items():
            meta = market_metadata.get(mid, {})
            end_dt = self._get_end_date(meta)
            if end_dt is None:
                continue

            analysis = self._analyze_market(mtrades, end_dt)
            results[mid] = analysis
            patterns.append(analysis["pattern"])

        overall_pattern = self._aggregate_patterns(patterns)

        return {
            "markets_analyzed": len(results),
            "overall_pattern": overall_pattern,
            "per_market": results,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _analyze_market(self, trades: List[Dict], end_dt: datetime) -> Dict:
        timestamps = sorted(
            t for t in (self._get_ts(trade) for trade in trades) if t is not None
        )
        if not timestamps:
            return {"pattern": "INSUFFICIENT_DATA", "window_counts": {}}

        # Baseline: trades per hour over the full history
        first_ts = timestamps[0]
        end_ts = end_dt.timestamp()
        if end_ts <= first_ts:
            # end date is before the first trade — data issue, can't classify
            return {"pattern": "INSUFFICIENT_DATA", "window_counts": {}}
        total_hours = max((end_ts - first_ts) / 3600, 1)
        baseline_tph = len(timestamps) / total_hours

        window_counts = {}
        for hours in self.WINDOWS_HOURS:
            cutoff = end_dt.timestamp() - hours * 3600
            count = sum(1 for ts in timestamps if ts >= cutoff)
            window_counts[hours] = {
                "trade_count": count,
                "trades_per_hour": round(count / hours, 2),
            }

        pattern = self._classify_pattern(baseline_tph, window_counts)
        return {
            "pattern": pattern,
            "baseline_trades_per_hour": round(baseline_tph, 2),
            "window_counts": window_counts,
        }

    @staticmethod
    def _classify_pattern(baseline_tph: float, window_counts: Dict) -> str:
        if baseline_tph < 0.01:
            return "INSUFFICIENT_DATA"

        # Check 2h and 1h windows
        h2_tph = window_counts.get(2, {}).get("trades_per_hour", baseline_tph)
        h1_tph = window_counts.get(1, {}).get("trades_per_hour", baseline_tph)

        if h1_tph < baseline_tph * 0.2:
            return "STOPS_EARLY"
        if h2_tph < baseline_tph * 0.3:
            return "CLOSES_POSITIONS"
        if h1_tph >= baseline_tph * 0.8:
            return "CONTINUES_NORMAL"
        return "WIDENS_SPREAD"

    @staticmethod
    def _aggregate_patterns(patterns: List[str]) -> str:
        if not patterns:
            return "INSUFFICIENT_DATA"
        counts: Dict[str, int] = defaultdict(int)
        for p in patterns:
            counts[p] += 1
        return max(counts, key=counts.get)

    @staticmethod
    def _get_market_id(trade: Dict) -> str:
        for field in ("asset_id", "market", "condition_id", "market_id", "token_id"):
            val = trade.get(field)
            if val:
                return str(val)
        return "unknown"

    @staticmethod
    def _get_end_date(meta: Dict) -> Optional[datetime]:
        for field in ("end_date_iso", "endDate", "end_date", "closeTime"):
            val = meta.get(field)
            if not val:
                continue
            if isinstance(val, (int, float)):
                try:
                    return datetime.fromtimestamp(val, tz=timezone.utc)
                except (OSError, OverflowError, ValueError):
                    pass
            if isinstance(val, str):
                try:
                    parsed = dateutil_parser.parse(val)
                    if parsed.tzinfo is not None:
                        return parsed.astimezone(timezone.utc)
                    return parsed.replace(tzinfo=timezone.utc)
                except (ValueError, OverflowError):
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
                    return dateutil_parser.parse(val).replace(tzinfo=timezone.utc).timestamp()
                except (ValueError, OverflowError):
                    pass
        return None
