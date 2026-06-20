# Mantle Agent Pulse — ERC-8004 Adoption Tracker

A research tool that collects, verifies, and reports ERC-8004 agent-economy
adoption data on Mantle Mainnet. Built for the **Mantle Research Challenge**
(Track 1: research paper evidence base, Track 2: research agent/tool submission).

## What It Does

1. **Daily Logger** — Scrapes the [ERC-8004 Explorer](https://erc-8004.quicknode.com)
   for agent registration and feedback counts on Mantle, runs RPC sanity checks,
   and appends a timestamped row to local CSV/JSON logs.

2. **On-Chain Verifier** — Independently recounts agent registrations directly
   from Mantle chain data (`eth_getLogs` on Transfer events from zero address),
   diffs against the indexer's number to catch backfill gaps.

3. **Peer-Chain Comparator** — Collects the same ERC-8004 stats for Base, BNB Chain,
   Avalanche C-Chain, Celo, Ethereum (and every other indexed network).

4. **Agent Density Index (ADI)** — Normalizes agent counts by chain TVL
   (from DefiLlama) to enable fair cross-chain comparison:

   ```
   ADI = (registered_agents / chain_TVL_USD) × 1,000,000
        = agents per $1M of chain TVL
   ```

5. **Report Generator** — Produces a Markdown report with trend charts and
   comparison tables, ready for embedding in Track 1/Track 2 posts.

6. **Optional Agent Registration** — Can register itself as an ERC-8004 agent
   on Mantle (sends a real tx, costs MNT gas — gated behind env var + confirmation).

---

## Quick Start (< 5 minutes)

### 1. Clone & Install

```bash
git clone https://github.com/Zireaelst/Mantle-Agent-Pulse-Daily-Logger.git
cd Mantle-Agent-Pulse-Daily-Logger
pip install -r requirements.txt
```

### 2. Run the Daily Logger

```bash
python logger.py
```

This will:
- Scrape Mantle's ERC-8004 page for current agent/feedback counts
- Verify the IdentityRegistry and ReputationRegistry contracts via RPC
- Scrape all peer chains from the /networks page
- Compute ADI for each mapped chain
- Append results to CSV/JSON files in `mantle_agent_pulse_data/`

### 3. Run Full On-Chain Verification (Optional, Slow)

```bash
python logger.py --full-verify
```

This adds an independent on-chain agent recount using chunked `eth_getLogs`.
Takes several minutes — run it once before publishing, not daily.

### 4. Generate Report

```bash
python logger.py --report
```

Creates a Markdown report in `reports/` with trend charts and ADI tables.

### 5. Run Tests

```bash
python tests/test_parsing.py
```

---

## Project Structure

```
mantle-agent-pulse/
├── logger.py                     # Main CLI entry point
├── config.py                     # All constants, addresses, endpoints
├── scraper.py                    # HTML scraper for ERC-8004 Explorer
├── rpc_client.py                 # Mantle RPC client (fallback, verification)
├── adi.py                        # Agent Density Index computation
├── report.py                     # Markdown report + chart generator
├── register.py                   # Optional on-chain agent registration
├── requirements.txt              # Python dependencies
├── SKILL.md                      # Mantle AI Agent Skills file
├── .env.example                  # Env var template (for --register-agent)
├── .gitignore
├── tests/
│   └── test_parsing.py           # Test suite with real HTML fixtures
├── mantle_agent_pulse_data/      # Data directory (append-only)
│   ├── mantle_agent_pulse_log.csv
│   ├── mantle_agent_pulse_log.json
│   ├── peer_chain_data.csv
│   ├── peer_chain_data.json
│   ├── adi_data.csv
│   └── adi_data.json
└── reports/                      # Generated reports
    └── mantle_agent_pulse_report_*.md
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `python logger.py` | Daily snapshot: scrape + RPC check + peer comparison + ADI |
| `python logger.py --full-verify` | + independent on-chain agent recount |
| `python logger.py --report` | Generate Markdown report with charts |
| `python logger.py --register-agent` | Register on ERC-8004 (costs gas!) |
| `python logger.py --peers-only` | Only scrape peer chains |
| `python logger.py -v` | Verbose/debug output |

---

## Agent Density Index (ADI)

The key cross-chain comparison metric for the research paper.

### Formula

```
ADI = (registered_agents / chain_TVL_USD) × 1,000,000
```

### What It Measures

**Registered agents per $1 million of chain TVL.** This normalizes for chain size:
a chain with 100 agents and $10M TVL (ADI = 10.0) has stronger relative adoption
than a chain with 10,000 agents and $5B TVL (ADI = 2.0).

### Data Sources

- **Agent counts**: [ERC-8004 Explorer](https://erc-8004.quicknode.com) public pages
- **TVL**: [DefiLlama](https://defillama.com) free API (`api.llama.fi/v2/chains`)

### Interpretation

| ADI Range | Interpretation |
|-----------|---------------|
| > 1.0 | High relative adoption |
| 0.1–1.0 | Moderate |
| < 0.1 | Low relative to chain size |

---

## Scheduler Setup (Cron / Task Scheduler)

### Linux / macOS (cron)

Run `crontab -e` and add:

```cron
# Mantle Agent Pulse — daily at 9:00 AM UTC
0 9 * * * cd /full/path/to/Mantle-Agent-Pulse-Daily-Logger && /usr/bin/python3 logger.py >> run.log 2>&1
```

Replace `/full/path/to/` with the actual path. To find it:

```bash
cd Mantle-Agent-Pulse-Daily-Logger && pwd
```

### Windows (Task Scheduler)

1. Open **Task Scheduler** → Create Basic Task
2. **Name**: Mantle Agent Pulse
3. **Trigger**: Daily, 9:00 AM
4. **Action**: Start a program
   - **Program**: `python` (or full path to `python.exe`)
   - **Arguments**: `logger.py`
   - **Start in**: `C:\full\path\to\Mantle-Agent-Pulse-Daily-Logger`
5. Check "Open the Properties dialog" and:
   - Under **General** → check "Run whether user is logged on or not"
   - Under **Settings** → check "Run task as soon as possible after a scheduled start is missed"

---

## On-Chain Registration (`--register-agent`)

> **⚠️ This feature costs real MNT gas. Only run it manually.**

### Setup

```bash
cp .env.example .env
# Edit .env and set AGENT_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

### Run

```bash
python logger.py --register-agent
```

### Safety Gates

1. **Private key**: Read only from `AGENT_PRIVATE_KEY` env var (never hardcoded)
2. **Confirmation**: Shows full transaction details and requires typing `REGISTER`
3. **Isolation**: Never called from the daily logger's default path

---

## Verified Addresses & Endpoints

All hardcoded values are documented in `config.py` with verification dates.

| Item | Value | Verified |
|------|-------|----------|
| Chain ID | 5000 | 2026-06-20 |
| IdentityRegistry | `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432` | 2026-06-20 |
| ReputationRegistry | `0x8004baa17c55a88189ae136b182e5fda19de9b63` | 2026-06-20 |
| ValidationRegistry | Not yet deployed ("Coming Soon") | 2026-06-20 |
| RPC (primary) | `https://rpc.mantle.xyz` | 2026-06-20 |
| RPC (fallback 1) | `https://mantle.publicnode.com` | 2026-06-20 |
| RPC (fallback 2) | `https://5000.rpc.thirdweb.com` | 2026-06-20 |
| ERC-8004 Explorer | `https://erc-8004.quicknode.com` | 2026-06-20 |
| DefiLlama API | `https://api.llama.fi/v2/chains` | 2026-06-20 |

---

## Day-0 Data Point

The seed row in `mantle_agent_pulse_data/mantle_agent_pulse_log.csv` was manually
captured from the live ERC-8004 Explorer on **2026-06-20**:

- **Agents: 126** | **Feedback: 1,244** | Validations: Coming Soon | Last indexed block: 96,593,016

An earlier fetch (~15–20 min prior) showed **108 agents / 633 feedback events**.
This jump likely reflects the indexer catching up on backfill rather than a
genuine registration burst — which is precisely why `--full-verify` exists.

---

## Design Decisions

- **HTML scraping over REST API**: The ERC-8004 Explorer's REST API is paywalled
  (x402, $0.001 USDC/request on Base). The website UI is explicitly documented as
  free. We parse the public HTML pages instead.

- **Adaptive chunk shrinking**: `eth_getLogs` calls start with large block ranges
  and automatically halve when the RPC returns "too many results" errors. This
  works reliably across different RPC providers with different limits.

- **Binary search for start block**: Rather than hardcoding a start block number
  (which would be fragile), we binary-search for the block at the target date.

- **APPEND-only logging**: The CSV/JSON files are never overwritten, only appended.
  The seed row is preserved.

- **No fabricated data**: If any source fails, we log `null`/`None` with a note
  explaining what failed. Never fabricate a data point.

---

## License

MIT