"""
shadow/fetcher.py — Fetch all trades for a target wallet from the Polymarket Data API.

Handles pagination, local caching, rate limiting, and graceful error recovery.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

console = Console()

DEFAULT_CONFIG = {
    "polymarket_data_api": "https://data-api.polymarket.com",
    "default_trade_limit": 500,
    "max_pagination_offset": 50000,
    "cache_dir": "data",
    "rate_limit_delay": 0.5,
}


class TradeFetcher:
    """Fetches all trades for a Polymarket wallet address with caching and pagination."""

    def __init__(self, config: Optional[Dict] = None):
        cfg = {**DEFAULT_CONFIG, **(config or {})}
        self.base_url = cfg["polymarket_data_api"]
        self.limit = int(cfg["default_trade_limit"])
        self.max_offset = int(cfg["max_pagination_offset"])
        self.cache_dir = cfg["cache_dir"]
        self.rate_limit_delay = float(cfg["rate_limit_delay"])
        os.makedirs(self.cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_trades(self, address: str, force_refresh: bool = False) -> List[Dict]:
        """
        Return all trades for *address*.

        Loads from local cache unless *force_refresh* is True or the cache is
        absent.  Shows a rich progress bar while fetching from the remote API.

        Args:
            address: Polymarket wallet address (checksummed or lowercase).
            force_refresh: When True, always hit the live API and overwrite cache.

        Returns:
            List of raw trade dicts as returned by the API.
        """
        cache_path = self._cache_path(address)

        if not force_refresh and os.path.exists(cache_path):
            return self._load_cache(cache_path)

        trades = self._fetch_all_pages(address)
        self._save_cache(cache_path, trades)
        return trades

    def get_cache_info(self, address: str) -> Dict:
        """Return metadata about the local cache for *address*."""
        cache_path = self._cache_path(address)
        if not os.path.exists(cache_path):
            return {"cached": False, "trade_count": 0, "age_hours": None, "path": cache_path}

        mtime = os.path.getmtime(cache_path)
        age_hours = (time.time() - mtime) / 3600
        try:
            with open(cache_path, "r") as fh:
                data = json.load(fh)
            trade_count = len(data.get("trades", []))
            cached_at = data.get("cached_at", "unknown")
        except (json.JSONDecodeError, OSError):
            trade_count = 0
            cached_at = "corrupt"

        return {
            "cached": True,
            "trade_count": trade_count,
            "age_hours": round(age_hours, 2),
            "cached_at": cached_at,
            "path": cache_path,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _cache_path(self, address: str) -> str:
        return os.path.join(self.cache_dir, f"{address.lower()}_trades.json")

    def _load_cache(self, path: str) -> List[Dict]:
        try:
            with open(path, "r") as fh:
                data = json.load(fh)
            trades = data.get("trades", [])
            cached_at = data.get("cached_at", "unknown")
            console.print(
                f"[dim]📦 Loaded [bold]{len(trades):,}[/bold] trades from cache "
                f"(cached at {cached_at})[/dim]"
            )
            return trades
        except (json.JSONDecodeError, OSError) as exc:
            console.print(f"[yellow]⚠️  Cache read error ({exc}), re-fetching…[/yellow]")
            return []

    def _save_cache(self, path: str, trades: List[Dict]) -> None:
        try:
            payload = {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "trade_count": len(trades),
                "trades": trades,
            }
            with open(path, "w") as fh:
                json.dump(payload, fh)
        except OSError as exc:
            console.print(f"[yellow]⚠️  Could not write cache: {exc}[/yellow]")

    def _fetch_all_pages(self, address: str) -> List[Dict]:
        """Paginate through the API and return every trade."""
        all_trades: List[Dict] = []
        offset = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Fetching trades for {address[:10]}…", total=None
            )

            while offset <= self.max_offset:
                url = (
                    f"{self.base_url}/trades"
                    f"?user={address}&limit={self.limit}&offset={offset}"
                )
                batch = self._get_with_retry(url)

                if not batch:
                    break  # no more pages

                all_trades.extend(batch)
                progress.update(
                    task,
                    description=(
                        f"[cyan]Fetching… {len(all_trades):,} trades "
                        f"(offset {offset})"
                    ),
                    advance=len(batch),
                )

                if len(batch) < self.limit:
                    break  # last page

                offset += self.limit
                time.sleep(self.rate_limit_delay)

        console.print(
            f"[green]✅ Fetched [bold]{len(all_trades):,}[/bold] trades from API[/green]"
        )
        return all_trades

    def _get_with_retry(
        self, url: str, max_retries: int = 3, backoff: float = 2.0
    ) -> List[Dict]:
        """GET *url* with exponential back-off on failures."""
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, timeout=30)

                if resp.status_code == 429:
                    wait = backoff ** (attempt + 1)
                    console.print(
                        f"[yellow]⏳ Rate limited — waiting {wait:.0f}s…[/yellow]"
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # The API may return a list directly or wrap it in a dict
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    for key in ("data", "trades", "results"):
                        if key in data and isinstance(data[key], list):
                            return data[key]
                    return []
                return []

            except requests.exceptions.Timeout:
                console.print(
                    f"[yellow]⏳ Timeout on attempt {attempt + 1}/{max_retries}[/yellow]"
                )
            except requests.exceptions.ConnectionError:
                console.print(
                    f"[yellow]🔌 Connection error on attempt {attempt + 1}/{max_retries}[/yellow]"
                )
            except requests.exceptions.HTTPError as exc:
                console.print(f"[red]❌ HTTP error: {exc}[/red]")
                return []
            except (ValueError, KeyError) as exc:
                console.print(f"[red]❌ JSON parse error: {exc}[/red]")
                return []

            if attempt < max_retries - 1:
                time.sleep(backoff ** (attempt + 1))

        console.print("[red]❌ All retries exhausted for URL: " + url + "[/red]")
        return []
