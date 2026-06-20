"""
Mantle Agent Pulse — Report Generator

Produces a Markdown report with:
- Latest Mantle ERC-8004 snapshot
- Registration count trend over time from CSV history
- ADI comparison table across peer chains
- A matplotlib PNG chart showing the trend

The report is designed to be presentable as-is for the Track 1/Track 2 posts.
"""

import os
import csv
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from config import (
    CSV_LOG_FILE,
    PEER_CSV_FILE,
    ADI_CSV_FILE,
    ADI_JSON_FILE,
    REPORT_DIR,
    DATA_DIR,
)

logger = logging.getLogger(__name__)


def _load_csv_rows(filepath: str) -> List[Dict[str, str]]:
    """Load a CSV file and return a list of dicts (one per row)."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _load_json_rows(filepath: str) -> List[Dict[str, Any]]:
    """Load a JSON file (expected to be a list of dicts)."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_trend_chart(csv_path: str, output_path: str) -> bool:
    """
    Generate a matplotlib PNG chart showing the agent registration trend
    over time from the Mantle CSV log.

    Returns True if chart was created, False on error.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        logger.warning("matplotlib not available, skipping chart generation")
        return False

    rows = _load_csv_rows(csv_path)
    if len(rows) < 1:
        logger.warning("Not enough data points for a trend chart")
        return False

    dates = []
    agents = []
    feedback = []

    for row in rows:
        try:
            dt = datetime.fromisoformat(row.get("timestamp", "").replace("Z", "+00:00"))
            dates.append(dt)
        except (ValueError, AttributeError):
            continue

        try:
            agents.append(int(row.get("agents", 0) or 0))
        except (ValueError, TypeError):
            agents.append(0)

        try:
            feedback.append(int(row.get("feedback", 0) or 0))
        except (ValueError, TypeError):
            feedback.append(0)

    if not dates:
        logger.warning("No valid dates found in CSV for chart")
        return False

    fig, ax1 = plt.subplots(figsize=(10, 5))

    # Style
    fig.patch.set_facecolor("#0f1115")
    ax1.set_facecolor("#0f1115")

    color_agents = "#6366f1"  # indigo
    color_feedback = "#22d3ee"  # cyan

    ax1.plot(dates, agents, color=color_agents, marker="o", linewidth=2,
             markersize=6, label="Agents", zorder=3)
    ax1.set_xlabel("Date", color="#a1a1aa", fontsize=10)
    ax1.set_ylabel("Registered Agents", color=color_agents, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=color_agents, colors="#a1a1aa")
    ax1.tick_params(axis="x", colors="#a1a1aa")

    ax2 = ax1.twinx()
    ax2.plot(dates, feedback, color=color_feedback, marker="s", linewidth=2,
             markersize=5, label="Feedback Events", linestyle="--", zorder=2)
    ax2.set_ylabel("Feedback Events", color=color_feedback, fontsize=10)
    ax2.tick_params(axis="y", labelcolor=color_feedback, colors="#a1a1aa")

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())

    # Grid
    ax1.grid(True, alpha=0.15, color="#a1a1aa")
    ax1.spines["top"].set_visible(False)
    ax1.spines["bottom"].set_color("#333")
    ax1.spines["left"].set_color("#333")
    ax1.spines["right"].set_color("#333")
    ax2.spines["top"].set_visible(False)
    ax2.spines["bottom"].set_color("#333")
    ax2.spines["left"].set_color("#333")
    ax2.spines["right"].set_color("#333")

    # Legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
               facecolor="#1a1a2e", edgecolor="#333", labelcolor="#e4e4e7",
               fontsize=9)

    plt.title("Mantle ERC-8004 Agent Economy — Registration Trend",
              color="#e4e4e7", fontsize=13, pad=15)
    plt.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()

    logger.info(f"Trend chart saved to {output_path}")
    return True


def generate_report() -> str:
    """
    Generate the full Markdown report.
    Returns the path to the generated report file.
    """
    os.makedirs(REPORT_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"mantle_agent_pulse_report_{timestamp}.md")
    chart_path = os.path.join(REPORT_DIR, f"trend_chart_{timestamp}.png")

    # Load data
    mantle_rows = _load_csv_rows(CSV_LOG_FILE)
    adi_records = _load_json_rows(ADI_JSON_FILE)
    peer_rows = _load_csv_rows(PEER_CSV_FILE)

    # Generate chart
    chart_generated = generate_trend_chart(CSV_LOG_FILE, chart_path)

    # Build report
    lines = []
    lines.append("# Mantle Agent Pulse — ERC-8004 Adoption Report")
    lines.append("")
    lines.append(f"*Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append("")

    # ── Latest Mantle Snapshot ─────────────────────────────────────────
    lines.append("## Latest Mantle Mainnet Snapshot")
    lines.append("")

    if mantle_rows:
        latest = mantle_rows[-1]
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Timestamp | {latest.get('timestamp', 'N/A')} |")
        lines.append(f"| Registered Agents | {latest.get('agents', 'N/A')} |")
        lines.append(f"| Feedback Events | {latest.get('feedback', 'N/A')} |")
        lines.append(f"| Validations | {latest.get('validations', 'N/A')} |")
        lines.append(f"| Last Indexed Block | {latest.get('last_indexed_block', 'N/A')} |")
        lines.append(f"| Chain Head Block | {latest.get('chain_head_block', 'N/A')} |")
        lines.append(f"| Identity Registry Deployed | {latest.get('identity_registry_deployed', 'N/A')} |")
        lines.append(f"| Reputation Registry Deployed | {latest.get('reputation_registry_deployed', 'N/A')} |")

        onchain_count = latest.get("onchain_agent_count", "")
        if onchain_count:
            lines.append(f"| On-chain Agent Count (full-verify) | {onchain_count} |")
            diff = latest.get("indexer_vs_onchain_diff", "")
            if diff:
                lines.append(f"| Indexer vs On-chain Diff | {diff} |")

        notes = latest.get("notes", "")
        if notes:
            lines.append("")
            lines.append(f"**Notes:** {notes}")
    else:
        lines.append("*No Mantle data available yet. Run `python logger.py` first.*")

    lines.append("")

    # ── Registration Trend ─────────────────────────────────────────────
    lines.append("## Registration Trend Over Time")
    lines.append("")

    if chart_generated:
        chart_rel = os.path.basename(chart_path)
        lines.append(f"![Mantle ERC-8004 Registration Trend]({chart_rel})")
        lines.append("")

    if len(mantle_rows) > 1:
        lines.append("| Date | Agents | Feedback | Last Indexed Block |")
        lines.append("|------|--------|----------|--------------------|")
        for row in mantle_rows:
            ts = row.get("timestamp", "")[:10]  # Just the date
            lines.append(
                f"| {ts} "
                f"| {row.get('agents', 'N/A')} "
                f"| {row.get('feedback', 'N/A')} "
                f"| {row.get('last_indexed_block', 'N/A')} |"
            )
    elif len(mantle_rows) == 1:
        lines.append("*Only one data point so far. Run the logger daily to build the trend.*")
    else:
        lines.append("*No historical data available yet.*")

    lines.append("")

    # ── Peer Chain Comparison ──────────────────────────────────────────
    lines.append("## Peer Chain Comparison (ERC-8004 Explorer)")
    lines.append("")

    if peer_rows:
        # Get the latest timestamp's rows
        latest_ts = peer_rows[-1].get("timestamp", "")
        latest_peers = [r for r in peer_rows if r.get("timestamp") == latest_ts]

        if latest_peers:
            lines.append(f"*Data from: {latest_ts[:10]}*")
            lines.append("")
            lines.append("| Chain | Agents | Feedback |")
            lines.append("|-------|--------|----------|")
            for row in sorted(latest_peers,
                            key=lambda r: int(r.get("agents", 0) or 0),
                            reverse=True):
                chain_name = row.get("network_name") or row.get("network_slug", "?")
                lines.append(
                    f"| {chain_name} "
                    f"| {row.get('agents', 'N/A')} "
                    f"| {row.get('feedback', 'N/A')} |"
                )
    else:
        lines.append("*No peer chain data available yet. Run `python logger.py` first.*")

    lines.append("")

    # ── ADI Comparison ─────────────────────────────────────────────────
    lines.append("## Agent Density Index (ADI) — Cross-Chain Comparison")
    lines.append("")
    lines.append(
        "**Formula:** `ADI = (registered_agents / chain_TVL_USD) × 1,000,000`"
    )
    lines.append("")
    lines.append(
        "ADI measures registered agents per $1M of chain TVL, normalizing for "
        "chain size to enable fair cross-chain comparison."
    )
    lines.append("")

    if adi_records:
        lines.append("| Chain | Agents | TVL ($) | ADI (agents/$1M) |")
        lines.append("|-------|--------|---------|------------------|")
        for rec in adi_records:
            name = rec.get("network_name", "?")
            agents_val = rec.get("agents", "N/A")
            tvl = rec.get("tvl_usd")
            adi_val = rec.get("adi")

            tvl_str = f"${tvl:,.0f}" if tvl is not None else "N/A"
            adi_str = f"{adi_val:.4f}" if adi_val is not None else "N/A"

            lines.append(f"| {name} | {agents_val} | {tvl_str} | {adi_str} |")
    else:
        lines.append("*No ADI data available yet. Run `python logger.py` first.*")

    lines.append("")

    # ── Methodology ────────────────────────────────────────────────────
    lines.append("## Methodology")
    lines.append("")
    lines.append("### Data Collection")
    lines.append("- **Agent/feedback counts**: Scraped from the [ERC-8004 Explorer]"
                 "(https://erc-8004.quicknode.com) public web UI (not the paywalled REST API)")
    lines.append("- **TVL data**: [DefiLlama](https://defillama.com) free API (`api.llama.fi/v2/chains`)")
    lines.append("- **On-chain verification** (`--full-verify`): Direct `eth_getLogs` scan of "
                 "Transfer events from the zero address on the IdentityRegistry contract")
    lines.append("")
    lines.append("### Key Assumptions & Limitations")
    lines.append("- The ERC-8004 indexer may be mid-backfill at any given time; "
                 "a single snapshot should not be treated as ground truth")
    lines.append("- TVL is a point-in-time metric and can fluctuate significantly")
    lines.append("- ADI does not account for agent quality, activity, or economic impact")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report generated by [Mantle Agent Pulse](https://github.com/Zireaelst/Mantle-Agent-Pulse-Daily-Logger) — "
                 "a research tool for the Mantle Research Challenge*")

    report_content = "\n".join(lines)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    logger.info(f"Report saved to {report_path}")
    return report_path
