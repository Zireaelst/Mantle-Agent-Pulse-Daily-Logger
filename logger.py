#!/usr/bin/env python3
"""
Mantle Agent Pulse — Daily Logger

A research tool that collects, verifies, and reports ERC-8004 agent-economy
data on Mantle Mainnet, for the Mantle Research Challenge (Track 1 paper +
Track 2 tool submission).

Usage:
    python logger.py                     # Daily snapshot: scrape + RPC check + log
    python logger.py --full-verify       # + independent on-chain recount
    python logger.py --report            # Generate the Markdown report
    python logger.py --register-agent    # Register this tool on-chain (costs gas!)
    python logger.py --peers-only        # Only scrape peer chains (no Mantle log)

Outputs:
    mantle_agent_pulse_data/mantle_agent_pulse_log.csv   — Mantle time-series
    mantle_agent_pulse_data/mantle_agent_pulse_log.json  — Same, JSON format
    mantle_agent_pulse_data/peer_chain_data.csv          — Peer chain comparison
    mantle_agent_pulse_data/peer_chain_data.json         — Same, JSON format
    mantle_agent_pulse_data/adi_data.csv                 — Agent Density Index
    mantle_agent_pulse_data/adi_data.json                — Same, JSON format
    reports/mantle_agent_pulse_report_*.md                — Generated reports

Contract addresses (verified 2026-06-20):
    IdentityRegistry:   0x8004a169fb4a3325136eb29fa0ceb6d2e539a432
    ReputationRegistry: 0x8004baa17c55a88189ae136b182e5fda19de9b63
    ValidationRegistry: Not yet deployed ("Coming Soon")

RPC endpoints (tried in order):
    https://rpc.mantle.xyz
    https://mantle.publicnode.com
    https://5000.rpc.thirdweb.com

Data sources:
    https://erc-8004.quicknode.com — ERC-8004 Explorer (public pages, NOT paywalled API)
    https://api.llama.fi/v2/chains — DefiLlama chain TVL data (free, no auth)
"""

import os
import sys
import csv
import json
import argparse
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from config import (
    CSV_LOG_FILE,
    JSON_LOG_FILE,
    PEER_CSV_FILE,
    PEER_JSON_FILE,
    ADI_CSV_FILE,
    ADI_JSON_FILE,
    DATA_DIR,
    PEER_CHAIN_SLUGS,
    SLUG_TO_DEFILLAMA,
    ONCHAIN_START_DATE,
    IDENTITY_REGISTRY_ADDRESS,
)
from scraper import scrape_network, scrape_all_networks_fast, NetworkStats
from rpc_client import (
    connect_rpc,
    get_chain_head,
    rpc_sanity_check,
    estimate_block_at_date,
    count_registrations_onchain,
)
from adi import compute_adi_for_chains
from report import generate_report


# ─── Logging Setup ──────────────────────────────────────────────────────────

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ─── CSV / JSON Append ─────────────────────────────────────────────────────

CSV_FIELDS = [
    "timestamp", "agents", "feedback", "validations", "last_indexed_block",
    "chain_head_block", "identity_registry_deployed", "reputation_registry_deployed",
    "rpc_endpoint", "onchain_agent_count", "indexer_vs_onchain_diff", "notes",
]

PEER_CSV_FIELDS = [
    "timestamp", "network_slug", "network_name", "agents", "feedback",
    "validations", "last_indexed_block", "chain_id",
]

ADI_CSV_FIELDS = [
    "timestamp", "network_slug", "network_name", "defillama_name",
    "agents", "tvl_usd", "adi",
]


def append_csv(filepath: str, row: Dict[str, Any], fields: List[str]) -> None:
    """Append a single row to a CSV file. Creates the file with headers if needed."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0

    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def append_json(filepath: str, row: Dict[str, Any]) -> None:
    """Append a row to a JSON file (which is a JSON array). Creates if needed."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    existing: List[Dict] = []
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    existing.append(row)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, default=str)


# ─── Main Logger Flow ──────────────────────────────────────────────────────

def fire_failure_notification(reason: str) -> None:
    try:
        script = f'display notification "Mantle Agent Pulse run failed: {reason}" with title "Mantle Agent Pulse"'
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        pass

def check_status() -> None:
    """Print total rows, date range covered, detected gaps, and current streak length."""
    if not os.path.exists(CSV_LOG_FILE):
        print("No CSV log file found.")
        return

    with open(CSV_LOG_FILE, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
    
    total_rows = len(reader)
    if total_rows == 0:
        print("CSV log is empty.")
        return

    first_date = reader[0]["timestamp"]
    last_date = reader[-1]["timestamp"]

    # Calculate gaps and streak
    gaps = []
    streak = 1
    
    for i in range(1, len(reader)):
        try:
            prev_ts = datetime.fromisoformat(reader[i-1]["timestamp"].replace("Z", "+00:00"))
            curr_ts = datetime.fromisoformat(reader[i]["timestamp"].replace("Z", "+00:00"))
            delta = curr_ts - prev_ts
            if delta > timedelta(hours=36):
                gaps.append(f"Gap between {prev_ts.date()} and {curr_ts.date()} ({delta.days} days)")
                streak = 1
            else:
                streak += 1
        except Exception:
            pass
            
        if "gap_detected" in reader[i].get("notes", ""):
            pass

    print(f"Total rows: {total_rows}")
    print(f"Date range: {first_date} to {last_date}")
    print(f"Current streak: {streak} days")
    if gaps:
        print("Detected gaps:")
        for g in gaps:
            print(f"  - {g}")
    else:
        print("No gaps detected.")


def run_daily_snapshot(full_verify: bool = False) -> Dict[str, Any]:
    """
    Run the daily Mantle snapshot:
    1. Scrape ERC-8004 explorer for agent/feedback/validation counts
    2. RPC sanity check (chain head, contract bytecode)
    3. (Optional) Full on-chain recount
    4. Append to CSV + JSON

    Returns the row dict.
    """
    logger = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")

    logger.info(f"=== Mantle Agent Pulse — Daily Snapshot ({timestamp}) ===")


    logger.info("Checking for data gaps...")
    if os.path.exists(CSV_LOG_FILE):
        with open(CSV_LOG_FILE, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
            if reader:
                last_row = reader[-1]
                try:
                    last_ts = datetime.fromisoformat(last_row["timestamp"].replace("Z", "+00:00"))
                    delta = now - last_ts
                    if delta > timedelta(hours=36):
                        gap_days = delta.days
                        gap_row = {
                            "timestamp": (last_ts + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                            "agents": last_row.get("agents"),
                            "feedback": last_row.get("feedback"),
                            "validations": last_row.get("validations"),
                            "last_indexed_block": last_row.get("last_indexed_block"),
                            "chain_head_block": last_row.get("chain_head_block"),
                            "identity_registry_deployed": last_row.get("identity_registry_deployed"),
                            "reputation_registry_deployed": last_row.get("reputation_registry_deployed"),
                            "rpc_endpoint": last_row.get("rpc_endpoint"),
                            "onchain_agent_count": last_row.get("onchain_agent_count"),
                            "indexer_vs_onchain_diff": last_row.get("indexer_vs_onchain_diff"),
                            "notes": f"gap_detected: missed {gap_days} days due to logger failure/downtime",
                        }
                        logger.warning(f"Gap detected! Logging missing {gap_days} days.")
                        append_csv(CSV_LOG_FILE, gap_row, CSV_FIELDS)
                        append_json(JSON_LOG_FILE, gap_row)
                except ValueError:
                    pass

    # ── Step 1: Scrape ERC-8004 explorer ────────────────────────────────
    logger.info("Step 1: Scraping ERC-8004 explorer for Mantle stats...")
    stats = scrape_network("mantle-mainnet")

    row: Dict[str, Any] = {
        "timestamp": timestamp,
        "agents": stats.agents,
        "feedback": stats.feedback,
        "validations": stats.validations,
        "last_indexed_block": stats.last_indexed_block,
        "chain_head_block": None,
        "identity_registry_deployed": None,
        "reputation_registry_deployed": None,
        "rpc_endpoint": None,
        "onchain_agent_count": None,
        "indexer_vs_onchain_diff": None,
        "notes": "",
    }

    notes = []
    if stats.scrape_error:
        notes.append(f"Scrape error: {stats.scrape_error}")
        logger.warning(f"Scrape error: {stats.scrape_error}")
        fire_failure_notification(stats.scrape_error)

    # ── Step 2: RPC sanity check ────────────────────────────────────────
    logger.info("Step 2: RPC sanity check...")
    rpc_result = rpc_sanity_check()

    row["chain_head_block"] = rpc_result.get("chain_head_block")
    row["identity_registry_deployed"] = rpc_result.get("identity_registry_deployed")
    row["reputation_registry_deployed"] = rpc_result.get("reputation_registry_deployed")
    row["rpc_endpoint"] = rpc_result.get("rpc_endpoint")

    if rpc_result.get("error"):
        notes.append(f"RPC error: {rpc_result['error']}")
        logger.warning(f"RPC error: {rpc_result['error']}")
        fire_failure_notification(rpc_result['error'])

    # ── Step 3: Full verify (optional) ──────────────────────────────────
    if full_verify:
        logger.info("Step 3: Full on-chain verification...")
        w3 = connect_rpc()
        if w3:
            head = get_chain_head(w3) or row["chain_head_block"]
            if head:
                start_block = estimate_block_at_date(w3, ONCHAIN_START_DATE)
                onchain_count, token_ids = count_registrations_onchain(
                    w3, start_block, head
                )
                row["onchain_agent_count"] = onchain_count

                if stats.agents is not None:
                    diff = stats.agents - onchain_count
                    row["indexer_vs_onchain_diff"] = diff
                    if diff != 0:
                        notes.append(
                            f"Indexer reports {stats.agents}, "
                            f"on-chain recount found {onchain_count} "
                            f"(diff: {diff:+d})"
                        )
                    else:
                        notes.append("On-chain recount matches indexer exactly")
            else:
                notes.append("Could not determine chain head for full verify")
        else:
            notes.append("RPC connection failed for full verify")

    row["notes"] = "; ".join(notes) if notes else ""

    # ── Step 4: Append to logs ──────────────────────────────────────────
    logger.info("Step 4: Appending to CSV and JSON logs...")
    append_csv(CSV_LOG_FILE, row, CSV_FIELDS)
    append_json(JSON_LOG_FILE, row)


    # ── Step 5: Git-based data integrity trail ──────────────────────────
    logger.info("Step 5: Git-based data integrity trail...")
    try:
        if not os.path.exists(".git"):
            subprocess.run(["git", "init"], check=True)
            if os.path.exists(".gitignore"):
                subprocess.run(["git", "add", ".gitignore"], check=True)
        subprocess.run(["git", "add", CSV_LOG_FILE, JSON_LOG_FILE, PEER_CSV_FILE, PEER_JSON_FILE, ADI_CSV_FILE, ADI_JSON_FILE], check=False)
        agents_val = row.get("agents", "N/A")
        feedback_val = row.get("feedback", "N/A")
        msg = f"data: snapshot {timestamp[:10]} — agents={agents_val} feedback={feedback_val} source=quicknode"
        subprocess.run(["git", "commit", "-m", msg], check=False)
        logger.info("Data committed to local git history.")
    except Exception as e:
        logger.error(f"Git integrity trail failed: {e}")

    # ── Print summary ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Mantle Agent Pulse — Snapshot {timestamp[:10]}")
    print(f"{'='*60}")
    print(f"  Agents:          {row['agents'] or 'N/A'}")
    print(f"  Feedback:        {row['feedback'] or 'N/A'}")
    print(f"  Validations:     {row['validations'] or 'N/A'}")
    print(f"  Indexed Block:   {row['last_indexed_block'] or 'N/A'}")
    print(f"  Chain Head:      {row['chain_head_block'] or 'N/A'}")
    print(f"  ID Registry:     {'✅' if row['identity_registry_deployed'] else '❌ or N/A'}")
    print(f"  Rep Registry:    {'✅' if row['reputation_registry_deployed'] else '❌ or N/A'}")

    if full_verify and row["onchain_agent_count"] is not None:
        print(f"  On-chain Count:  {row['onchain_agent_count']}")
        print(f"  Diff (idx-chain):{row['indexer_vs_onchain_diff']:+d}" if row['indexer_vs_onchain_diff'] is not None else "")

    if row["notes"]:
        print(f"  Notes:           {row['notes']}")

    print(f"{'='*60}")
    print(f"  Data saved to: {CSV_LOG_FILE}")
    print(f"                 {JSON_LOG_FILE}")
    print()

    return row


def run_peer_comparison() -> List[Dict[str, Any]]:
    """
    Scrape peer chain stats from the ERC-8004 explorer /networks table.
    Also computes ADI for mapped chains.
    Returns list of peer row dicts.
    """
    logger = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat().replace("+00:00", "Z")

    logger.info("=== Peer Chain Comparison ===")

    # Scrape all networks from the /networks table
    all_stats = scrape_all_networks_fast()

    if not all_stats:
        logger.error("Could not scrape any network data")
        return []

    # Filter to peer chains (+ any others we find)
    peer_slugs_set = set(PEER_CHAIN_SLUGS)
    peer_stats = [s for s in all_stats if s.network_slug in peer_slugs_set]

    # Also log ALL networks to peer files (bonus data)
    rows = []
    for stats in all_stats:
        row = {
            "timestamp": timestamp,
            "network_slug": stats.network_slug,
            "network_name": stats.network_name,
            "agents": stats.agents,
            "feedback": stats.feedback,
            "validations": stats.validations,
            "last_indexed_block": stats.last_indexed_block,
            "chain_id": stats.chain_id,
        }
        append_csv(PEER_CSV_FILE, row, PEER_CSV_FIELDS)
        rows.append(row)

    # Save peer JSON
    append_json_bulk(PEER_JSON_FILE, rows)

    # Print summary for peer chains
    print(f"\n{'='*60}")
    print(f"  Peer Chain Comparison — {timestamp[:10]}")
    print(f"{'='*60}")
    print(f"  {'Chain':<25} {'Agents':>10} {'Feedback':>12}")
    print(f"  {'-'*25} {'-'*10} {'-'*12}")

    for stats in sorted(peer_stats, key=lambda s: s.agents or 0, reverse=True):
        name = stats.network_name or stats.network_slug
        agents_str = f"{stats.agents:,}" if stats.agents is not None else "N/A"
        feedback_str = f"{stats.feedback:,}" if stats.feedback is not None else "N/A"
        print(f"  {name:<25} {agents_str:>10} {feedback_str:>12}")

    print(f"{'='*60}")
    print(f"  Total networks scraped: {len(all_stats)}")
    print(f"  Data saved to: {PEER_CSV_FILE}")
    print()

    # ── ADI computation ─────────────────────────────────────────────────
    logger.info("Computing Agent Density Index (ADI)...")
    adi_records = compute_adi_for_chains(peer_stats)

    if adi_records:
        adi_rows = []
        for rec in adi_records:
            adi_row = {
                "timestamp": timestamp,
                **rec.to_dict(),
            }
            append_csv(ADI_CSV_FILE, adi_row, ADI_CSV_FIELDS)
            adi_rows.append(adi_row)

        # Save ADI JSON (overwrite with latest)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ADI_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in adi_records], f, indent=2, default=str)

        print(f"\n{'='*60}")
        print(f"  Agent Density Index (ADI) — agents per $1M TVL")
        print(f"{'='*60}")
        print(f"  {'Chain':<20} {'Agents':>10} {'TVL ($M)':>12} {'ADI':>10}")
        print(f"  {'-'*20} {'-'*10} {'-'*12} {'-'*10}")

        for rec in adi_records:
            name = rec.network_name[:20]
            agents_str = f"{rec.agents:,}" if rec.agents is not None else "N/A"
            tvl_str = f"${rec.tvl_usd / 1e6:,.1f}M" if rec.tvl_usd else "N/A"
            adi_str = f"{rec.adi:.4f}" if rec.adi is not None else "N/A"
            print(f"  {name:<20} {agents_str:>10} {tvl_str:>12} {adi_str:>10}")

        print(f"{'='*60}")
        print(f"  ADI data saved to: {ADI_CSV_FILE}")
        print()

    return rows


def append_json_bulk(filepath: str, rows: List[Dict[str, Any]]) -> None:
    """Append multiple rows to a JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    existing: List[Dict] = []
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []
    existing.extend(rows)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, default=str)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mantle Agent Pulse — ERC-8004 adoption tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python logger.py                  # Daily snapshot (scrape + RPC + log)
  python logger.py --full-verify    # + on-chain agent recount
  python logger.py --report         # Generate Markdown report
  python logger.py --register-agent # Register on ERC-8004 (costs gas!)
  python logger.py --peers-only     # Only scrape peer chains
  python logger.py -v               # Verbose/debug output
        """,
    )
    parser.add_argument(
        "--full-verify",
        action="store_true",
        help="Run independent on-chain agent recount (slow, chunked eth_getLogs)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate Markdown report with charts and ADI comparison",
    )
    parser.add_argument(
        "--register-agent",
        action="store_true",
        help="Register this tool on Mantle's ERC-8004 IdentityRegistry (costs gas!)",
    )
    parser.add_argument(
        "--peers-only",
        action="store_true",
        help="Only scrape peer chain data (skip Mantle daily log)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print fast pre-submission health check status",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Handle --register-agent separately (never in the daily path)
    if args.register_agent:
        from register import register_agent
        register_agent()
        return

    if args.status:
        check_status()
        return

    # Handle --report
    if args.report:
        report_path = generate_report()
        print(f"Report generated: {report_path}")
        return

    # Normal flow: daily snapshot + peer comparison
    if not args.peers_only:
        try:
            run_daily_snapshot(full_verify=args.full_verify)
        except Exception as e:
            fire_failure_notification(f"Unhandled exception: {e}")
            raise

    # Always run peer comparison (unless explicitly peers_only + report only)
    run_peer_comparison()

    # If full-verify was requested, print a final summary
    if args.full_verify:
        print("\n💡 Full verification complete. Check the notes column in the CSV")
        print("   for the indexer vs on-chain diff.\n")


if __name__ == "__main__":
    main()
