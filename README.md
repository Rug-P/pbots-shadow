# 🌑 PBot's Shadow

> *"If you can't beat them, study them. Then beat them."*

**Competitive intelligence system for Polymarket bots.**

Reverse-engineer the strategies of the most profitable bots on Polymarket using only public on-chain data.

---

## ✨ Features

- 🕵️ **Spy** — Fetch every single trade a target wallet has ever made via the Polymarket Data API
- 🧠 **Classify** — Determine whether the bot is a Market Maker, Aggressive Taker, or Hybrid
- 📊 **Analyze** — 7 deep analysis modules: spread, timing, market selection, inventory, P/L, resolution behavior
- 📋 **Report** — Beautiful terminal intelligence reports powered by `rich`
- 🔍 **Discover** — Scan the Polymarket leaderboard to find new profitable bots automatically

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      PBot's Shadow                          │
│                                                             │
│  ┌──────────┐    ┌────────────┐    ┌────────────────────┐  │
│  │  FETCH   │───▶│  CLASSIFY  │───▶│      ANALYZE       │  │
│  │          │    │            │    │                    │  │
│  │ fetcher  │    │ classifier │    │ spread_analyzer    │  │
│  │ 27K+     │    │ maker vs   │    │ timing_analyzer    │  │
│  │ trades   │    │ taker ratio│    │ market_selector    │  │
│  │ cached   │    │ confidence │    │ inventory_tracker  │  │
│  └──────────┘    └────────────┘    │ pnl_decomposer     │  │
│                                    │ resolution_behavior│  │
│                                    └────────────┬───────┘  │
│                                                 │          │
│                                    ┌────────────▼───────┐  │
│                                    │       REPORT        │  │
│                                    │  terminal + .md    │  │
│                                    └────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Rug-P/pbots-shadow.git
cd pbots-shadow
pip install -r requirements.txt
pip install -e .
```

### 2. Configure Targets

Edit `config/targets.yaml` to add wallets you want to spy on.  
PBot-1 is already pre-configured as the primary target.

### 3. Run

```bash
# Full intelligence report on PBot-1
python -m tools.shadow_cli spy --target pbot-1

# Force re-fetch all trades (bypass cache)
python -m tools.shadow_cli spy --target pbot-1 --force-refresh

# Spy by raw address
python -m tools.shadow_cli spy --address 0x88f46b9e5d86b4fb85be55ab0ec4004264b9d4db

# Discover new profitable bots from leaderboard
python -m tools.shadow_cli discover --min-profit 10000 --min-trades 1000

# Compare multiple targets
python -m tools.shadow_cli compare --targets pbot-1,swisstony

# List all configured targets
python -m tools.shadow_cli list-targets

# Check cache status
python -m tools.shadow_cli cache-info --target pbot-1
```

---

## 📋 Sample Output

```
🌑 PBot's Shadow — Intelligence Report
══════════════════════════════════════════════════
🎯 Target: PBot-1 (0x88f46b...9d4db)
📊 Trades Analyzed: 27,451
⏱️  Period: 2025-06-15 → 2026-03-27

═══ STRATEGY CLASSIFICATION ═══
🏷️  Type: MARKET MAKER (93.2% maker fills)
📊 Maker: 25,500 | Taker: 1,951
🎯 Confidence: HIGH

═══ TIMING PROFILE ═══
⚡ Speed Class: FAST_BOT
📈 Avg Interval: 12.4s
📊 Trades/Day: ~890
🕐 Peak Hours: 14:00-18:00 UTC

═══ SPREAD ANALYSIS ═══
💰 Avg Spread: $0.028/share
🔬 Tightest: $0.008 (crypto 5min markets)
🔭 Widest: $0.045 (politics long-term)

═══ MARKET SELECTION ═══
┌──────────────────────────────────────────────────┐
│ Market                 │ Trades │ Volume   │ Pct  │
├──────────────────────────────────────────────────┤
│ Crypto 5min            │  8,234 │ $450,000 │ 30%  │
│ NBA 2025-26            │  5,102 │ $280,000 │ 18%  │
│ US Politics            │  3,891 │ $150,000 │ 14%  │
└──────────────────────────────────────────────────┘

═══ INVENTORY MANAGEMENT ═══
📦 Max Exposure: $4,200
📊 Avg Position: $890
🎯 Delta-Neutral Score: 0.92/1.00

═══ P/L DECOMPOSITION ═══
💵 Spread P/L: $51,200 (87.6%)
🎯 Resolution P/L: $7,250 (12.4%)

═══ RESOLUTION BEHAVIOR ═══
🏁 Pattern: STOPS_EARLY (reduces quoting 2h before close)

═══ ACTIONABLE INSIGHTS ═══
💡 Bot is a highly automated market maker with 93.2% maker ratio
💡 FAST_BOT speed class (avg 12.4s between trades)
💡 Strongly prefers short-duration, high-volume markets
💡 Near-neutral inventory management — pure spread capture
💡 Copy strategy: place resting orders on top 3 market categories
```

---

## 🔬 How It Works — The 7 Analysis Modules

| Module | What It Reveals |
|--------|----------------|
| **classifier** | Maker vs taker ratio — the fundamental strategy type |
| **spread_analyzer** | How much spread is captured per trade, per market |
| **timing_analyzer** | Bot speed, peak hours, trading frequency |
| **market_selector** | Which markets/categories it prefers and why |
| **inventory_tracker** | How positions are managed — delta-neutral or directional? |
| **pnl_decomposer** | What % of profits come from spreads vs market resolution |
| **resolution_behavior** | What happens as markets approach their closing time |

---

## 🎯 Target Wallets

| Name | Address | Status | Notes |
|------|---------|--------|-------|
| **PBot-1** | `0x88f46b9e5d86b4fb85be55ab0ec4004264b9d4db` | ✅ Active | Suspected pure market maker. ~27K+ trades. ~$58K/month |
| majorexploiter | TBD | 🔄 Pending | +$2.4M profit. $6.95M volume. Top #1 all-time |
| swisstony | TBD | 🔄 Pending | +$856K profit. $137M volume. Liquidity provider |

---

## 🤝 Contributing

1. Fork the repo
2. Add a new analysis module to `shadow/`
3. Register it in `tools/shadow_cli.py`
4. Submit a PR

Ideas for new modules: order-book reconstruction, cross-market correlation, gas/fee analysis, wallet clustering.

---

## ⚠️ Disclaimer

This tool only uses **publicly available on-chain data** from Polymarket's public APIs.  
No private keys, no scraping, no ToS violations. Educational purposes only.

---

## 📄 License

MIT — do whatever you want, just don't be evil.
