"""
tools/shadow_cli.py — Main CLI entry point for PBot's Shadow.

Commands:
  spy          — Full intelligence report for a target wallet
  compare      — Compare multiple targets side-by-side
  discover     — Scan leaderboard for new bot wallets
  list-targets — Show configured targets
  cache-info   — Show cache status for a target
"""

import os
import sys

import click
import yaml
from rich.console import Console
from rich.table import Table

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shadow.fetcher import TradeFetcher
from shadow.classifier import StrategyClassifier
from shadow.spread_analyzer import SpreadAnalyzer
from shadow.timing_analyzer import TimingAnalyzer
from shadow.market_selector import MarketAnalyzer
from shadow.inventory_tracker import InventoryTracker
from shadow.pnl_decomposer import PnLDecomposer
from shadow.resolution_behavior import ResolutionAnalyzer
from shadow.leaderboard_scanner import LeaderboardScanner
from reports.generator import ReportGenerator

console = Console()

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "targets.yaml",
)


def _load_config() -> dict:
    """Load targets.yaml. Returns an empty dict if the file is missing."""
    try:
        with open(CONFIG_PATH, "r") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        console.print(f"[yellow]⚠️  Config not found at {CONFIG_PATH}[/yellow]")
        return {}
    except yaml.YAMLError as exc:
        console.print(f"[red]❌ YAML parse error in config: {exc}[/red]")
        return {}


def _resolve_target(config: dict, target_name: str) -> dict:
    """Find a target by name (case-insensitive) in targets.yaml."""
    targets = config.get("targets", [])
    for t in targets:
        if t.get("name", "").lower() == target_name.lower():
            return t
    return {}


def _run_full_analysis(address: str, config: dict, force_refresh: bool) -> dict:
    """Run the complete analysis pipeline and return all results."""
    settings = config.get("settings", {})

    # 1. Fetch trades
    fetcher = TradeFetcher(config=settings)
    trades = fetcher.fetch_trades(address, force_refresh=force_refresh)

    if not trades:
        console.print("[red]❌ No trades found for this address.[/red]")
        return {}

    console.print(f"[dim]🔬 Analysing {len(trades):,} trades…[/dim]")

    # 2. Classification
    clf = StrategyClassifier().classify(trades, address)

    # 3. Spread
    spread = SpreadAnalyzer().analyze(trades, address)

    # 4. Timing
    timing = TimingAnalyzer().analyze(trades)

    # 5. Market selection
    market = MarketAnalyzer(
        gamma_api=settings.get("gamma_api", "https://gamma-api.polymarket.com"),
        cache_dir=settings.get("cache_dir", "data"),
    ).analyze(trades)

    # 6. Inventory
    inventory = InventoryTracker().analyze(trades, address)

    # 7. P/L decomposition
    pnl = PnLDecomposer().analyze(trades, address)

    # 8. Resolution behavior (uses market metadata from the selector step)
    res_analyzer = ResolutionAnalyzer()
    # Build a metadata dict from the market selector results
    market_meta = {}
    for m in market.get("top_markets_by_trades", []):
        mid = m.get("market_id")
        if mid:
            market_meta[mid] = m
    resolution = res_analyzer.analyze(trades, market_meta)

    return {
        "classification": clf,
        "spread": spread,
        "timing": timing,
        "market_selection": market,
        "inventory": inventory,
        "pnl": pnl,
        "resolution": resolution,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """🌑 PBot's Shadow — Competitive intelligence for Polymarket bots."""


@cli.command()
@click.option("--target", "-t", default=None, help="Target name from targets.yaml")
@click.option("--address", "-a", default=None, help="Raw wallet address (0x…)")
@click.option(
    "--force-refresh",
    is_flag=True,
    default=False,
    help="Bypass cache and re-fetch all trades",
)
@click.option(
    "--export",
    default=None,
    help="Export report to a Markdown file (e.g. reports/pbot1.md)",
)
def spy(target, address, force_refresh, export):
    """Run a full intelligence report on a target wallet."""
    config = _load_config()

    if not target and not address:
        console.print("[red]❌ Provide --target <name> or --address <0x…>[/red]")
        raise SystemExit(1)

    if target and not address:
        tdata = _resolve_target(config, target)
        if not tdata:
            console.print(f"[red]❌ Target '{target}' not found in config.[/red]")
            raise SystemExit(1)
        address = tdata.get("address", "")
        if not address:
            console.print(
                f"[yellow]⚠️  Target '{target}' has no address configured yet.[/yellow]"
            )
            raise SystemExit(1)
        target_name = tdata.get("name", target)
    else:
        target_name = target or address[:10] + "…"

    console.print(
        f"\n[bold magenta]🌑 PBot's Shadow[/bold magenta] — spying on "
        f"[bold]{target_name}[/bold] ([dim]{address}[/dim])\n"
    )

    results = _run_full_analysis(address, config, force_refresh)
    if not results:
        raise SystemExit(1)

    gen = ReportGenerator()
    gen.print_report(results, target_name, address)

    if export:
        gen.export_markdown(results, target_name, export)


@cli.command()
@click.option(
    "--targets",
    "-t",
    required=True,
    help="Comma-separated target names (e.g. pbot-1,swisstony)",
)
def compare(targets):
    """Compare multiple target wallets side-by-side."""
    config = _load_config()
    names = [n.strip() for n in targets.split(",")]

    table = Table(title="🌑 Target Comparison", show_header=True, header_style="bold magenta")
    table.add_column("Metric")
    for name in names:
        table.add_column(name, justify="center")

    all_results = {}
    for name in names:
        tdata = _resolve_target(config, name)
        address = tdata.get("address", "")
        if not address:
            console.print(f"[yellow]⚠️  Skipping '{name}' — no address configured.[/yellow]")
            all_results[name] = {}
            continue
        console.print(f"\n[cyan]Analysing {name}…[/cyan]")
        all_results[name] = _run_full_analysis(address, config, False)

    def _row(label, extractor):
        row = [label]
        for name in names:
            r = all_results.get(name, {})
            try:
                row.append(str(extractor(r)))
            except Exception:
                row.append("N/A")
        return row

    table.add_row(*_row("Strategy", lambda r: r.get("classification", {}).get("strategy_type", "?")))
    table.add_row(*_row("Maker %", lambda r: f"{r.get('classification', {}).get('maker_ratio', 0)*100:.1f}%"))
    table.add_row(*_row("Speed", lambda r: r.get("timing", {}).get("speed_class", "?")))
    table.add_row(*_row("Trades/Day", lambda r: f"~{r.get('timing', {}).get('trades_per_day', 0):.0f}"))
    table.add_row(*_row("Avg Spread", lambda r: f"${r.get('spread', {}).get('avg_spread', 0):.4f}"))
    table.add_row(*_row("Delta-Neutral", lambda r: f"{r.get('inventory', {}).get('delta_neutral_score', 0):.2f}"))

    console.print(table)


@cli.command()
@click.option("--min-profit", default=10_000, show_default=True, help="Minimum profit (USDC)")
@click.option("--min-trades", default=1_000, show_default=True, help="Minimum number of trades")
def discover(min_profit, min_trades):
    """Scan the leaderboard to discover new profitable bot wallets."""
    config = _load_config()
    settings = config.get("settings", {})

    scanner = LeaderboardScanner(
        data_api=settings.get("polymarket_data_api", "https://data-api.polymarket.com"),
        gamma_api=settings.get("gamma_api", "https://gamma-api.polymarket.com"),
    )
    wallets = scanner.scan(min_profit=min_profit, min_trades=min_trades)

    if not wallets:
        console.print("[yellow]No wallets found matching the criteria.[/yellow]")
        return

    table = Table(title="🔍 Discovered Wallets", header_style="bold magenta")
    table.add_column("Address", style="dim")
    table.add_column("Profit", justify="right", style="green")
    table.add_column("Trades", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Bot?", justify="center")

    for w in wallets[:20]:
        table.add_row(
            w["address"],
            f"${w['profit_usdc']:,.0f}",
            f"{w['trade_count']:,}",
            f"${w['volume_usdc']:,.0f}",
            "✅" if w["is_likely_bot"] else "❓",
        )
    console.print(table)


@cli.command("list-targets")
def list_targets():
    """Show all configured targets from targets.yaml."""
    config = _load_config()
    targets = config.get("targets", [])

    if not targets:
        console.print("[yellow]No targets configured in config/targets.yaml[/yellow]")
        return

    table = Table(title="🎯 Configured Targets", header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Address", style="dim")
    table.add_column("Status")
    table.add_column("Priority", justify="center")
    table.add_column("Notes")

    for t in targets:
        addr = t.get("address") or "[dim]TBD[/dim]"
        status = t.get("status", "?")
        status_icon = "✅" if status == "active" else "🔄"
        table.add_row(
            t.get("name", "?"),
            addr,
            f"{status_icon} {status}",
            str(t.get("priority", "?")),
            (t.get("notes") or "")[:60],
        )
    console.print(table)


@cli.command("cache-info")
@click.option("--target", "-t", default=None, help="Target name from targets.yaml")
@click.option("--address", "-a", default=None, help="Raw wallet address (0x…)")
def cache_info(target, address):
    """Show cache status for a target wallet."""
    config = _load_config()
    settings = config.get("settings", {})

    if not target and not address:
        console.print("[red]❌ Provide --target <name> or --address <0x…>[/red]")
        raise SystemExit(1)

    if target and not address:
        tdata = _resolve_target(config, target)
        address = tdata.get("address", "")
        if not address:
            console.print(f"[yellow]⚠️  Target '{target}' has no address configured.[/yellow]")
            raise SystemExit(1)

    fetcher = TradeFetcher(config=settings)
    info = fetcher.get_cache_info(address)

    table = Table(title=f"📦 Cache Info — {address[:16]}…", header_style="bold magenta")
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Cached", "✅ Yes" if info["cached"] else "❌ No")
    table.add_row("Trade Count", f"{info['trade_count']:,}")
    table.add_row(
        "Cache Age",
        f"{info['age_hours']:.1f}h" if info["age_hours"] is not None else "N/A",
    )
    if info.get("cached_at"):
        table.add_row("Cached At", info["cached_at"])
    table.add_row("Path", info["path"])

    console.print(table)


if __name__ == "__main__":
    cli()
