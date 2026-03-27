"""
shadow/timing_analyzer.py — Analyse trade timing, frequency, and speed patterns.

Determines whether the target wallet is a high-frequency bot, a moderate-speed
bot, or something operated by a human, and identifies peak operating hours/days.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dateutil import parser as dateutil_parser


class TimingAnalyzer:
    """
    Analyses the temporal patterns of a wallet's trade history.

    Metrics produced:
    - Average / median / min / p95 interval between consecutive trades
    - Speed class (HFT_BOT, FAST_BOT, MODERATE_BOT, SLOW_OR_MANUAL)
    - Trades per day (average)
    - Peak hour and peak day-of-week distributions
    """

    def analyze(self, trades: List[Dict]) -> Dict:
        """
        Analyse timing for the provided *trades*.

        Args:
            trades: Raw trade list sorted by any order (will be re-sorted here).

        Returns:
            Dict with the full timing profile.
        """
        if not trades:
            return self._empty()

        timestamps = []
        for trade in trades:
            ts = self._parse_timestamp(trade)
            if ts is not None:
                timestamps.append(ts)

        if not timestamps:
            return self._empty()

        timestamps.sort()

        # Inter-trade intervals (seconds)
        intervals = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
        ]

        avg_interval = sum(intervals) / len(intervals) if intervals else 0.0
        median_interval = self._percentile(intervals, 50)
        min_interval = min(intervals) if intervals else 0.0
        p95_interval = self._percentile(intervals, 95)

        speed_class = self._classify_speed(avg_interval)

        # Period stats
        first_trade = timestamps[0]
        last_trade = timestamps[-1]
        period_days = max(
            (last_trade - first_trade).total_seconds() / 86400, 1
        )
        trades_per_day = len(timestamps) / period_days

        # Hour-of-day distribution (UTC)
        hour_counts: Dict[int, int] = defaultdict(int)
        day_counts: Dict[int, int] = defaultdict(int)
        for ts in timestamps:
            hour_counts[ts.hour] += 1
            day_counts[ts.weekday()] += 1  # 0=Mon … 6=Sun

        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None
        peak_day = max(day_counts, key=day_counts.get) if day_counts else None

        # Peak hour window (top-3 consecutive hours)
        peak_window = self._peak_window(hour_counts)

        # Trades per hour — peak hour count
        peak_trades_per_hour = hour_counts.get(peak_hour, 0) if peak_hour is not None else 0

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        return {
            "total_trades": len(timestamps),
            "first_trade": first_trade.isoformat(),
            "last_trade": last_trade.isoformat(),
            "period_days": round(period_days, 1),
            "avg_interval_s": round(avg_interval, 2),
            "median_interval_s": round(median_interval, 2),
            "min_interval_s": round(min_interval, 2),
            "p95_interval_s": round(p95_interval, 2),
            "speed_class": speed_class,
            "trades_per_day": round(trades_per_day, 1),
            "peak_hour_utc": peak_hour,
            "peak_hour_window_utc": peak_window,
            "peak_trades_per_hour": peak_trades_per_hour,
            "peak_day_of_week": day_names[peak_day] if peak_day is not None else None,
            "hour_distribution": dict(hour_counts),
            "day_distribution": {
                day_names[k]: v for k, v in day_counts.items()
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_timestamp(trade: Dict) -> Optional[datetime]:
        for field in ("timestamp", "created_at", "transacted_at", "time", "date"):
            val = trade.get(field)
            if val is None:
                continue
            # Unix epoch (int or float)
            if isinstance(val, (int, float)):
                try:
                    return datetime.fromtimestamp(val, tz=timezone.utc)
                except (OSError, OverflowError, ValueError):
                    pass
            # ISO string
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
    def _percentile(data: List[float], pct: int) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * pct / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    @staticmethod
    def _classify_speed(avg_interval_s: float) -> str:
        if avg_interval_s < 5:
            return "HFT_BOT"
        if avg_interval_s < 30:
            return "FAST_BOT"
        if avg_interval_s < 300:
            return "MODERATE_BOT"
        return "SLOW_OR_MANUAL"

    @staticmethod
    def _peak_window(hour_counts: Dict[int, int]) -> str:
        """Return a human-readable UTC peak-activity window (top 3 hours)."""
        if not hour_counts:
            return "unknown"
        top3 = sorted(hour_counts, key=hour_counts.get, reverse=True)[:3]
        top3.sort()
        return f"{top3[0]:02d}:00-{(top3[-1] + 1) % 24:02d}:00 UTC"

    @staticmethod
    def _empty() -> Dict:
        return {
            "total_trades": 0,
            "first_trade": None,
            "last_trade": None,
            "period_days": 0,
            "avg_interval_s": 0,
            "median_interval_s": 0,
            "min_interval_s": 0,
            "p95_interval_s": 0,
            "speed_class": "UNKNOWN",
            "trades_per_day": 0,
            "peak_hour_utc": None,
            "peak_hour_window_utc": "unknown",
            "peak_trades_per_hour": 0,
            "peak_day_of_week": None,
            "hour_distribution": {},
            "day_distribution": {},
        }
