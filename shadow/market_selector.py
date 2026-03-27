"""
shadow/market_selector.py — Analyse which markets a target wallet prefers.

Fetches market metadata from the Gamma API, groups trades by market, and
produces a category-level breakdown with fee-preference analysis.
"""

import json
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional

import requests
from rich.console import Console

console = Console()

GAMMA_API = "https://gamma-api.polymarket.com"
CACHE_DIR = "data"


class MarketAnalyzer:
    """
    Identifies which markets and categories a wallet focuses on.

    For each market traded, the analyzer attempts to retrieve metadata from the
    Gamma API (title, category, end date, fee tier) and caches the result
    locally so repeated runs don't hit the API again.
    """

    TOP_N = 10

    def __init__(self, gamma_api: str = GAMMA_API, cache_dir: str = CACHE_DIR):
        self.gamma_api = gamma_api.rstrip("/")
        self.cache_dir = cache_dir
        self._meta_cache: Dict[str, Dict] = {}
        self._meta_cache_path = os.path.join(cache_dir, "market_metadata.json")
        self._load_meta_cache()

    def analyze(self, trades: List[Dict]) -> Dict:
        """
        Analyse market selection patterns for *trades*.

        Returns:
            Dict with top markets by trade count, top markets by volume,
            category distribution, and fee-tier preference.
        """
        market_trades: Dict[str, List[Dict]] = defaultdict(list)
        for trade in trades:
            mid = self._get_market_id(trade)
            market_trades[mid].append(trade)

        # Build per-market stats
        market_stats: List[Dict] = []
        for mid, mtrades in market_trades.items():
            meta = self._get_market_meta(mid)
            volume = sum(self._get_volume(t) for t in mtrades)
            tags = meta.get("tags") or []
            category = meta.get("category") or (tags[0] if tags else "unknown")
            market_stats.append(
                {
                    "market_id": mid,
                    "title": meta.get("question") or meta.get("title") or mid[:20],
                    "category": category,
                    "end_date": meta.get("end_date_iso") or meta.get("endDate") or meta.get("end_date"),
                    "fee_rate": meta.get("makerFeeRate") or meta.get("taker_fee_rate") or 0,
                    "trade_count": len(mtrades),
                    "volume_usd": round(volume, 2),
                }
            )

        # Aggregates
        total_trades = sum(m["trade_count"] for m in market_stats)
        total_volume = sum(m["volume_usd"] for m in market_stats)

        # Category distribution
        category_counts: Dict[str, int] = defaultdict(int)
        category_volume: Dict[str, float] = defaultdict(float)
        for m in market_stats:
            cat = m["category"] or "unknown"
            category_counts[cat] += m["trade_count"]
            category_volume[cat] += m["volume_usd"]

        # Top markets
        top_by_trades = sorted(market_stats, key=lambda m: m["trade_count"], reverse=True)[: self.TOP_N]
        top_by_volume = sorted(market_stats, key=lambda m: m["volume_usd"], reverse=True)[: self.TOP_N]

        # Fee preference
        fee_markets = sum(1 for m in market_stats if (m["fee_rate"] or 0) > 0)
        zero_fee_markets = len(market_stats) - fee_markets

        self._save_meta_cache()

        return {
            "total_unique_markets": len(market_stats),
            "total_trades": total_trades,
            "total_volume_usd": round(total_volume, 2),
            "top_markets_by_trades": top_by_trades,
            "top_markets_by_volume": top_by_volume,
            "category_distribution": {
                k: {
                    "trade_count": category_counts[k],
                    "volume_usd": round(category_volume[k], 2),
                    "pct": round(category_counts[k] / total_trades * 100, 1) if total_trades else 0,
                }
                for k in sorted(category_counts, key=category_counts.get, reverse=True)
            },
            "fee_enabled_markets": fee_markets,
            "zero_fee_markets": zero_fee_markets,
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
    def _get_volume(trade: Dict) -> float:
        # size from the real API is in USDC base units (6 decimals); compute price * size / 1e6
        price = trade.get("price")
        size = trade.get("size")
        if price is not None and size is not None:
            try:
                return abs(float(price) * float(size) / 1e6)
            except (TypeError, ValueError):
                pass
        # Fallback: pre-computed USDC amount fields
        for field in ("usdc_amount", "usdcSize", "notional", "amount"):
            val = trade.get(field)
            if val is not None:
                try:
                    return abs(float(val))
                except (TypeError, ValueError):
                    pass
        return 0.0

    def _get_market_meta(self, market_id: str) -> Dict:
        if market_id in self._meta_cache:
            return self._meta_cache[market_id]

        meta = self._fetch_market_meta(market_id)
        self._meta_cache[market_id] = meta
        return meta

    def _fetch_market_meta(self, market_id: str) -> Dict:
        """Try to fetch market metadata from Gamma API."""
        if not market_id or market_id == "unknown":
            return {}

        urls = [
            f"{self.gamma_api}/markets/{market_id}",
            f"{self.gamma_api}/markets?conditionId={market_id}",
            f"{self.gamma_api}/markets?id={market_id}",
            f"{self.gamma_api}/markets?clob_token_ids=[{market_id}]",
        ]
        for url in urls:
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        return data[0]
                    if isinstance(data, dict) and data:
                        return data
                time.sleep(0.1)
            except Exception:
                pass
        return {}

    def _load_meta_cache(self) -> None:
        try:
            if os.path.exists(self._meta_cache_path):
                with open(self._meta_cache_path, "r") as fh:
                    self._meta_cache = json.load(fh)
        except (json.JSONDecodeError, OSError):
            self._meta_cache = {}

    def _save_meta_cache(self) -> None:
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self._meta_cache_path, "w") as fh:
                json.dump(self._meta_cache, fh)
        except OSError as exc:
            console.print(f"[yellow]⚠️  Could not save market metadata cache: {exc}[/yellow]")
