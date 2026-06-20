---
name: mantle-agent-pulse
description: >
  Collect, verify, and report ERC-8004 agent-economy adoption data on Mantle Mainnet.
  Use this skill when you need to track agent registrations, compute the Agent Density Index (ADI)
  for cross-chain comparison, or generate research reports on ERC-8004 adoption across EVM chains.
  This skill is designed for the Mantle Research Challenge (Track 1: research paper, Track 2: research agent/tool).
metadata:
  version: "1.0.0"
  author: Zireaelst
  license: MIT
  chain: Mantle Mainnet (EIP-155 chain id 5000)
  standard: ERC-8004
  data_sources:
    - https://erc-8004.quicknode.com (public pages, not paywalled API)
    - https://api.llama.fi/v2/chains (DefiLlama, free, no auth)
    - Mantle RPC (direct on-chain verification)
compatibility:
  python: ">=3.8"
  os: [linux, macos, windows]
---

# Mantle Agent Pulse — AI Agent Skill

## When to Use This Skill

Use this skill when you need to:

- **Track ERC-8004 adoption** on Mantle Mainnet over time
- **Compare agent registrations** across EVM chains (Mantle, Base, BNB, Ethereum, Avalanche, Celo, etc.)
- **Compute the Agent Density Index (ADI)** — a normalized metric for cross-chain comparison
- **Verify indexer accuracy** by independently recounting agent registrations from on-chain data
- **Generate research reports** with trend charts and comparison tables
- **Register an AI agent** on Mantle's ERC-8004 IdentityRegistry (optional, costs gas)

## Workflow

### Step 1: Daily Data Collection

Run the daily logger to collect a snapshot:

```bash
python logger.py
```

This performs:
1. **Scrape** the ERC-8004 Explorer public page for Mantle Mainnet stats (agents, feedback, validations, last indexed block)
2. **RPC sanity check** — connect to Mantle RPC, verify chain head, confirm IdentityRegistry and ReputationRegistry contracts have deployed bytecode
3. **Peer chain scrape** — collect the same stats for Base, BNB Chain, Avalanche, Celo, Ethereum from the /networks table
4. **ADI computation** — fetch TVL from DefiLlama, compute `ADI = (agents / TVL_USD) × 1,000,000` for each chain
5. **Append** one row per run to CSV and JSON log files (never overwrite)

### Step 2: On-Chain Verification (Optional, Slow)

Run `--full-verify` to independently recount agent registrations:

```bash
python logger.py --full-verify
```

This adds:
- Binary-search to find the block at the ERC-8004 genesis date (~Feb 2026)
- Adaptive chunked `eth_getLogs` scan for `Transfer(from=0x0)` events on the IdentityRegistry
- Diff between the indexer's reported count and the on-chain recount

### Step 3: Report Generation

Generate a presentable Markdown report:

```bash
python logger.py --report
```

The report includes:
- Latest Mantle snapshot
- Registration trend chart (matplotlib PNG)
- Peer chain comparison table
- ADI comparison table with formula documentation

### Step 4: On-Chain Registration (Optional, Costs Gas)

Register this tool as an ERC-8004 agent:

```bash
export AGENT_PRIVATE_KEY=0xYOUR_KEY
python logger.py --register-agent
```

This is triple-gated:
- Private key from environment variable only (never hardcoded)
- Interactive confirmation prompt showing exact transaction details
- Never called from the daily logger's default path

## Output Files

| File | Description |
|------|-------------|
| `mantle_agent_pulse_data/mantle_agent_pulse_log.csv` | Mantle time-series (append-only) |
| `mantle_agent_pulse_data/mantle_agent_pulse_log.json` | Same data, JSON format |
| `mantle_agent_pulse_data/peer_chain_data.csv` | All ERC-8004 networks' stats |
| `mantle_agent_pulse_data/adi_data.csv` | Agent Density Index per chain |
| `reports/mantle_agent_pulse_report_*.md` | Generated research reports |

## Key Metric: Agent Density Index (ADI)

```
ADI = (registered_agents / chain_TVL_USD) × 1,000,000
```

ADI measures registered agents per $1M of chain TVL. It normalizes for chain size,
enabling fair cross-chain comparison of ERC-8004 adoption. A higher ADI indicates
stronger agent-economy adoption relative to the chain's overall economic activity.

## Dependencies

```
requests beautifulsoup4 web3 matplotlib python-dotenv
```

## Limitations

- The ERC-8004 indexer may be mid-backfill; never treat a single read as ground truth
- TVL is a point-in-time metric that fluctuates
- ADI does not account for agent quality, activity, or economic impact
- The `--full-verify` on-chain scan is slow (minutes to hours depending on block range)
