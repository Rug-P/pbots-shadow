"""
shadow/leaderboard_scanner.py — Discover profitable bots from the Polymarket leaderboard.

Tries several known public API endpoints to retrieve the leaderboard and filters
results by minimum profit and minimum trade count thresholds.
"""

import time
from typing import Dict, List, Optional

import requests
from rich.console import Console

console = Console()

DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


class LeaderboardScanner:
    """
    Scans the Polymarket leaderboard for high-performing wallets.

    Filters by minimum profit and minimum trade count and applies simple
    heuristics to flag potential bot wallets (very high trade counts or
    unusually consistent P/L patterns).
    """

    # Heuristic threshold: wallets with this many trades are likely automated
    BOT_TRADE_THRESHOLD = 500

    def __init__(
        self,
        data_api: str = DATA_API,
        gamma_api: str = GAMMA_API,
    ):
        self.data_api = data_api.rstrip("/")
        self.gamma_api = gamma_api.rstrip("/")

    def scan(
        self,
        min_profit: float = 10_000,
        min_trades: int = 1_000,
    ) -> List[Dict]:
        """
        Scan the leaderboard and return potential bot wallets.

        Args:
            min_profit: Minimum profit (USDC) to include.
            min_trades: Minimum number of trades to include.

        Returns:
            List of wallet dicts with address, profit, trade_count,
            volume, and is_likely_bot flag.
        """
        console.print("[cyan]🔍 Scanning Polymarket leaderboard…[/cyan]")
        raw = self._fetch_leaderboard()

        if not raw:
            console.print(
                "[yellow]⚠️  No leaderboard data retrieved. "
                "The endpoint may have changed.[/yellow]"
            )
            return []

        results = []
        for entry in raw:
            address = self._get_address(entry)
            profit = self._get_profit(entry)
            trades = self._get_trade_count(entry)
            volume = self._get_volume(entry)

            if profit < min_profit:
                continue
            if trades < min_trades:
                continue

            results.append(
                {
                    "address": address,
                    "profit_usdc": round(profit, 2),
                    "trade_count": trades,
                    "volume_usdc": round(volume, 2),
                    "is_likely_bot": trades >= self.BOT_TRADE_THRESHOLD,
                    "profit_per_trade": round(profit / trades, 4) if trades > 0 else 0,
                }
            )

        results.sort(key=lambda x: x["profit_usdc"], reverse=True)
        console.print(
            f"[green]✅ Found [bold]{len(results)}[/bold] wallets "
            f"matching criteria (min_profit={min_profit:,}, min_trades={min_trades:,})[/green]"
        )
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_leaderboard(self) -> List[Dict]:
        """Try multiple known endpoint patterns."""
        endpoints = [
            f"{self.data_api}/leaderboard",
            f"{self.data_api}/leaderboard?limit=200",
            f"{self.gamma_api}/leaderboard",
            f"{self.data_api}/profiles?limit=200&sortBy=profit&order=desc",
            f"{self.data_api}/users?limit=200&sortBy=profit&order=desc",
        ]
        for url in endpoints:
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and data:
                        console.print(f"[dim]📋 Leaderboard fetched from {url}[/dim]")
                        return data
                    if isinstance(data, dict):
                        for key in ("data", "users", "traders", "leaderboard", "results"):
                            if key in data and isinstance(data[key], list):
                                return data[key]
                time.sleep(0.3)
            except Exception as exc:
                console.print(f"[dim]  Endpoint failed ({url}): {exc}[/dim]")
        return []

    @staticmethod
    def _get_address(entry: Dict) -> str:
        for field in ("address", "wallet", "user", "proxy_wallet", "proxyWallet"):
            val = entry.get(field)
            if val:
                return str(val)
        return "unknown"

    @staticmethod
    def _get_profit(entry: Dict) -> float:
        for field in ("profit", "pnl", "realized_pnl", "realizedPnl", "totalProfit"):
            val = entry.get(field)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return 0.0

    @staticmethod
    def _get_trade_count(entry: Dict) -> int:
        for field in ("trades_count", "tradesCount", "trade_count", "trades", "num_trades"):
            val = entry.get(field)
            if val is not None:
                try:
                    return int(val)
                except (TypeError, ValueError):
                    pass
        return 0

    @staticmethod
    def _get_volume(entry: Dict) -> float:
        for field in ("volume", "total_volume", "totalVolume", "volumeUsd"):
            val = entry.get(field)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
        return 0.0
