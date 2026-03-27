"""
reports/generator.py — Generate formatted intelligence reports.

Produces beautiful terminal output using the `rich` library and optionally
exports a Markdown file with the full intelligence report.
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


class ReportGenerator:
    """
    Renders analysis results as a rich terminal report and/or a Markdown file.

    Usage::

        gen = ReportGenerator()
        gen.print_report(results, "PBot-1", "0x88f46b...")
        gen.export_markdown(results, "PBot-1", "reports/pbot1_report.md")
    """

    def print_report(
        self, results: Dict, target_name: str, address: str
    ) -> None:
        """Print the full intelligence report to the terminal."""
        c = console

        # Header
        c.print()
        c.rule("[bold magenta]🌑 PBot's Shadow — Intelligence Report[/bold magenta]")
        c.print()
        c.print(f"[bold]🎯 Target:[/bold] {target_name} ([dim]{address}[/dim])")

        trades = results.get("classification", {}).get("total_trades", 0)
        c.print(f"[bold]📊 Trades Analyzed:[/bold] {trades:,}")

        timing = results.get("timing", {})
        if timing.get("first_trade") and timing.get("last_trade"):
            c.print(
                f"[bold]⏱️  Period:[/bold] "
                f"{timing['first_trade'][:10]} → {timing['last_trade'][:10]}"
            )

        # Strategy Classification
        self._print_section("STRATEGY CLASSIFICATION", self._render_classification(results))

        # Timing Profile
        self._print_section("TIMING PROFILE", self._render_timing(results))

        # Spread Analysis
        self._print_section("SPREAD ANALYSIS", self._render_spread(results))

        # Market Selection
        self._print_section("MARKET SELECTION", self._render_market_selection(results))

        # Inventory Management
        self._print_section("INVENTORY MANAGEMENT", self._render_inventory(results))

        # P/L Decomposition
        self._print_section("P/L DECOMPOSITION", self._render_pnl(results))

        # Resolution Behavior
        self._print_section("RESOLUTION BEHAVIOR", self._render_resolution(results))

        # Actionable Insights
        insights = self._generate_insights(results)
        self._print_section("ACTIONABLE INSIGHTS", self._render_insights(insights))

        c.rule("[dim]End of Report[/dim]")
        c.print()

    def export_markdown(
        self, results: Dict, target_name: str, filepath: str
    ) -> None:
        """Export the report as a Markdown file at *filepath*."""
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        lines = self._build_markdown(results, target_name)
        with open(filepath, "w") as fh:
            fh.write("\n".join(lines))
        console.print(f"[green]📄 Report saved to {filepath}[/green]")

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _print_section(self, title: str, content) -> None:
        console.print()
        console.rule(f"[bold cyan]═══ {title} ═══[/bold cyan]", style="cyan")
        if isinstance(content, str):
            console.print(content)
        else:
            console.print(content)

    def _render_classification(self, results: Dict) -> str:
        clf = results.get("classification", {})
        if not clf:
            return "[dim]No data[/dim]"
        st = clf.get("strategy_type", "UNKNOWN")
        mr = clf.get("maker_ratio", 0) * 100
        mc = clf.get("maker_count", 0)
        tc = clf.get("taker_count", 0)
        conf = clf.get("confidence", "?")
        color = "green" if "MAKER" in st else "yellow" if "HYBRID" in st else "red"
        return (
            f"[bold {color}]🏷️  Type: {st}[/bold {color}] ({mr:.1f}% maker fills)\n"
            f"📊 Maker: [green]{mc:,}[/green] | Taker: [red]{tc:,}[/red]\n"
            f"🎯 Confidence: [bold]{conf}[/bold]"
        )

    def _render_timing(self, results: Dict) -> str:
        t = results.get("timing", {})
        if not t:
            return "[dim]No data[/dim]"
        sc = t.get("speed_class", "UNKNOWN")
        ai = t.get("avg_interval_s", 0)
        tpd = t.get("trades_per_day", 0)
        pw = t.get("peak_hour_window_utc", "unknown")
        return (
            f"⚡ Speed Class: [bold yellow]{sc}[/bold yellow]\n"
            f"📈 Avg Interval: [cyan]{ai}s[/cyan]\n"
            f"📊 Trades/Day: [cyan]~{tpd:.0f}[/cyan]\n"
            f"🕐 Peak Hours: [cyan]{pw}[/cyan]"
        )

    def _render_spread(self, results: Dict) -> str:
        s = results.get("spread", {})
        if not s:
            return "[dim]No data[/dim]"
        avg = s.get("avg_spread", 0)
        mn = s.get("min_spread", 0)
        mx = s.get("max_spread", 0)
        tightest = s.get("tightest_market", {}) or {}
        widest = s.get("widest_market", {}) or {}

        lines = [
            f"💰 Avg Spread: [bold green]${avg:.4f}/share[/bold green]",
            f"🔬 Tightest: [green]${mn:.4f}[/green] (market: {tightest.get('market_id', 'N/A')[:20]})",
            f"🔭 Widest:   [red]${mx:.4f}[/red] (market: {widest.get('market_id', 'N/A')[:20]})",
        ]
        if s.get("top_markets"):
            table = Table(show_header=True, header_style="bold magenta", box=None)
            table.add_column("Market ID", style="dim", width=24)
            table.add_column("Buys", justify="right")
            table.add_column("Sells", justify="right")
            table.add_column("Spread", justify="right", style="green")
            for m in s["top_markets"][:5]:
                sp = m.get("spread_captured")
                table.add_row(
                    m.get("market_id", "?")[:24],
                    str(m.get("buy_count", 0)),
                    str(m.get("sell_count", 0)),
                    f"${sp:.4f}" if sp is not None else "N/A",
                )
            console.print("\n".join(lines))
            console.print(table)
            return ""
        return "\n".join(lines)

    def _render_market_selection(self, results: Dict) -> object:
        ms = results.get("market_selection", {})
        if not ms:
            return "[dim]No data[/dim]"

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Market", style="dim", max_width=32)
        table.add_column("Category", style="cyan")
        table.add_column("Trades", justify="right")
        table.add_column("Volume", justify="right", style="green")
        table.add_column("%", justify="right")

        total = ms.get("total_trades", 1) or 1
        for m in ms.get("top_markets_by_trades", [])[:10]:
            pct = m.get("trade_count", 0) / total * 100
            table.add_row(
                m.get("title", m.get("market_id", "?"))[:32],
                m.get("category", "?")[:16],
                f"{m.get('trade_count', 0):,}",
                f"${m.get('volume_usd', 0):,.0f}",
                f"{pct:.1f}%",
            )
        return table

    def _render_inventory(self, results: Dict) -> str:
        inv = results.get("inventory", {})
        if not inv:
            return "[dim]No data[/dim]"
        me = inv.get("max_exposure", 0)
        ae = inv.get("avg_exposure", 0)
        dn = inv.get("delta_neutral_score", 0)
        mwi = inv.get("markets_with_open_inventory", 0)
        ht = inv.get("avg_holding_time_s")
        holding = f"{ht:.0f}s" if ht else "N/A"
        return (
            f"📦 Max Exposure: [bold red]${me:,.4f}[/bold red] shares\n"
            f"📊 Avg Exposure: [yellow]${ae:,.4f}[/yellow] shares\n"
            f"🎯 Delta-Neutral Score: [bold green]{dn:.2f}/1.00[/bold green]\n"
            f"🏪 Markets w/ Open Inventory: [yellow]{mwi}[/yellow]\n"
            f"⏱️  Avg Holding Time: [cyan]{holding}[/cyan]"
        )

    def _render_pnl(self, results: Dict) -> str:
        pnl = results.get("pnl", {})
        if not pnl:
            return "[dim]No data[/dim]"
        sp = pnl.get("spread_pnl", 0)
        rp = pnl.get("resolution_pnl", 0)
        tp = pnl.get("total_pnl", 0)
        spct = pnl.get("spread_pct", 0)
        rpct = pnl.get("resolution_pct", 0)
        return (
            f"💵 Spread P/L:     [bold green]${sp:,.4f}[/bold green] ({spct:.1f}%)\n"
            f"🎯 Resolution P/L: [bold cyan]${rp:,.4f}[/bold cyan] ({rpct:.1f}%)\n"
            f"💰 Total P/L Est:  [bold yellow]${tp:,.4f}[/bold yellow]"
        )

    def _render_resolution(self, results: Dict) -> str:
        rb = results.get("resolution", {})
        if not rb:
            return "[dim]No data[/dim]"
        op = rb.get("overall_pattern", "UNKNOWN")
        analyzed = rb.get("markets_analyzed", 0)
        color = "green" if op == "STOPS_EARLY" else "yellow"
        return (
            f"🏁 Pattern: [bold {color}]{op}[/bold {color}]\n"
            f"📊 Markets Analyzed: [cyan]{analyzed}[/cyan]"
        )

    @staticmethod
    def _render_insights(insights: List[str]) -> str:
        return "\n".join(f"💡 {i}" for i in insights)

    # ------------------------------------------------------------------
    # Insight generation
    # ------------------------------------------------------------------

    def _generate_insights(self, results: Dict) -> List[str]:
        insights = []
        clf = results.get("classification", {})
        timing = results.get("timing", {})
        inv = results.get("inventory", {})
        pnl = results.get("pnl", {})
        resolution = results.get("resolution", {})

        st = clf.get("strategy_type", "")
        mr = clf.get("maker_ratio", 0) * 100
        if st:
            insights.append(
                f"Bot is a [bold]{st.replace('_', ' ').title()}[/bold] "
                f"with {mr:.1f}% maker ratio"
            )

        sc = timing.get("speed_class", "")
        ai = timing.get("avg_interval_s", 0)
        if sc:
            insights.append(f"{sc} speed class (avg {ai}s between trades)")

        ms = results.get("market_selection", {})
        cats = ms.get("category_distribution", {})
        if cats:
            top_cat = next(iter(cats))
            top_pct = cats[top_cat].get("pct", 0)
            insights.append(
                f"Primarily trades [bold]{top_cat}[/bold] ({top_pct:.0f}% of trades)"
            )

        dn = inv.get("delta_neutral_score", 0)
        if dn > 0.8:
            insights.append(
                f"Near-neutral inventory management (score {dn:.2f}) — pure spread capture"
            )
        else:
            insights.append(
                f"Takes directional risk (delta-neutral score {dn:.2f})"
            )

        spct = pnl.get("spread_pct", 0)
        if spct > 70:
            insights.append(
                f"~{spct:.0f}% of P/L from spread capture — copy-able with resting orders"
            )

        pattern = resolution.get("overall_pattern", "")
        if pattern and pattern != "INSUFFICIENT_DATA":
            insights.append(f"Resolution risk management: {pattern.replace('_', ' ').title()}")

        if not insights:
            insights.append("Not enough data for insights — try fetching more trades")

        return insights

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------

    def _build_markdown(self, results: Dict, target_name: str) -> List[str]:
        clf = results.get("classification", {})
        timing = results.get("timing", {})
        spread = results.get("spread", {})
        pnl = results.get("pnl", {})
        inv = results.get("inventory", {})
        resolution = results.get("resolution", {})
        ms = results.get("market_selection", {})

        lines = [
            f"# 🌑 PBot's Shadow — Intelligence Report: {target_name}",
            f"",
            f"_Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
            f"",
            f"---",
            f"",
            f"## Strategy Classification",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Type | `{clf.get('strategy_type', 'N/A')}` |",
            f"| Maker Ratio | {clf.get('maker_ratio', 0)*100:.1f}% |",
            f"| Maker Count | {clf.get('maker_count', 0):,} |",
            f"| Taker Count | {clf.get('taker_count', 0):,} |",
            f"| Confidence | {clf.get('confidence', 'N/A')} |",
            f"",
            f"## Timing Profile",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Speed Class | `{timing.get('speed_class', 'N/A')}` |",
            f"| Avg Interval | {timing.get('avg_interval_s', 0)}s |",
            f"| Trades/Day | ~{timing.get('trades_per_day', 0):.0f} |",
            f"| Peak Hours UTC | {timing.get('peak_hour_window_utc', 'N/A')} |",
            f"",
            f"## Spread Analysis",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Avg Spread | ${spread.get('avg_spread', 0):.6f} |",
            f"| Min Spread | ${spread.get('min_spread', 0):.6f} |",
            f"| Max Spread | ${spread.get('max_spread', 0):.6f} |",
            f"",
            f"## P/L Decomposition",
            f"",
            f"| Source | Amount | % |",
            f"|--------|--------|---|",
            f"| Spread P/L | ${pnl.get('spread_pnl', 0):,.4f} | {pnl.get('spread_pct', 0):.1f}% |",
            f"| Resolution P/L | ${pnl.get('resolution_pnl', 0):,.4f} | {pnl.get('resolution_pct', 0):.1f}% |",
            f"| **Total** | **${pnl.get('total_pnl', 0):,.4f}** | 100% |",
            f"",
            f"## Inventory Management",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Max Exposure | {inv.get('max_exposure', 0):,.4f} shares |",
            f"| Avg Exposure | {inv.get('avg_exposure', 0):,.4f} shares |",
            f"| Delta-Neutral Score | {inv.get('delta_neutral_score', 0):.2f} |",
            f"",
            f"## Resolution Behavior",
            f"",
            f"Pattern: **{resolution.get('overall_pattern', 'N/A')}**",
            f"",
            f"---",
            f"",
            f"_This report was generated by [PBot's Shadow](https://github.com/Rug-P/pbots-shadow). "
            f"Only publicly available data was used._",
        ]
        return lines
