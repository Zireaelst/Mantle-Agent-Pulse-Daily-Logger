"""
Mantle Agent Pulse — Tests

Tests for the parsing logic using fixtures with real captured page content.
Follows the approach described in the README: a fixture with real captured
page text, asserting exact field extraction.
"""

import json
import os
import sys
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import parse_network_page, parse_networks_table, NetworkStats
from adi import compute_adi, ADIRecord


# ─── Fixtures: Real captured HTML snippets ──────────────────────────────────

# This fixture mirrors the actual HTML structure of the Mantle page as fetched
# on 2026-06-20. The regex parser must extract the correct values from this.

MANTLE_PAGE_FIXTURE = """
<h1 class="text-(--foreground) text-3xl sm:text-4xl m-0 mb-2">ERC-8004 Agents on Mantle Mainnet</h1>
<section class="grid grid-cols-2 sm:grid-cols-3 gap-4">
    <article class="bg-(--background) border border-(--border) p-5">
      <div class="text-(--foreground-light) text-xs font-mono uppercase tracking-wider">EIP-155 chain id</div>
      <div class="text-(--foreground) text-3xl font-mono leading-[1.1] mt-1">5000</div>
    </article>
    <article class="bg-(--background) border border-(--border) p-5">
      <div class="text-(--foreground-light) text-xs font-mono uppercase tracking-wider">Agents</div>
      <div class="text-(--foreground) text-3xl font-semibold leading-[1.1] mt-1">137</div>
    </article>
    <article class="bg-(--background) border border-(--border) p-5">
      <div class="text-(--foreground-light) text-xs font-mono uppercase tracking-wider">Feedback events</div>
      <div class="text-(--foreground) text-3xl font-semibold leading-[1.1] mt-1">1,532</div>
    </article>
    <article class="bg-(--background) border border-(--border) p-5">
      <div class="text-(--foreground-light) text-xs font-mono uppercase tracking-wider">Validation events</div>
      <div class="text-(--foreground) text-3xl font-semibold leading-[1.1] mt-1">
          <span class="coming-soon-pill inline-flex items-center px-2 py-0.5 text-xs font-mono uppercase tracking-wider border border-(--border) bg-(--background-elevated) text-(--foreground-light)">
  Coming Soon
</span>
      </div>
    </article>
    <article class="bg-(--background) border border-(--border) p-5">
      <div class="text-(--foreground-light) text-xs font-mono uppercase tracking-wider">Last indexed block</div>
      <div class="text-(--foreground) text-3xl font-mono leading-[1.1] mt-1">
          96,930,543
      </div>
    </article>
</section>
"""

NETWORKS_TABLE_FIXTURE = """
<table class="ds-table">
  <thead>
    <tr>
      <th>Network</th>
      <th>EIP-155 chain id</th>
      <th>Agents</th>
      <th>Feedback</th>
      <th>Validations</th>
      <th>Last indexed block</th>
    </tr>
  </thead>
  <tbody>
      <tr>
        <td>
          <a class="inline-block" href="/networks/base-mainnet">
            <span class="inline-flex w-fit items-center gap-1.5 px-2 py-1 text-xs font-mono uppercase ring-1 ring-inset ring-(--border) text-(--foreground)">
  Base Mainnet
</span>
</a>        </td>
        <td class="font-mono">8453</td>
        <td>55938</td>
        <td>265197</td>
        <td>
            <span class="coming-soon-pill">Coming Soon</span>
        </td>
        <td class="text-(--foreground-light) font-mono">47,600,982</td>
      </tr>
      <tr>
        <td>
          <a class="inline-block" href="/networks/bnb-mainnet">
            <span class="inline-flex w-fit items-center gap-1.5 px-2 py-1 text-xs font-mono uppercase ring-1 ring-inset ring-(--border) text-(--foreground)">
  BNB Chain Mainnet
</span>
</a>        </td>
        <td class="font-mono">56</td>
        <td>139543</td>
        <td>29490</td>
        <td>
            <span class="coming-soon-pill">Coming Soon</span>
        </td>
        <td class="text-(--foreground-light) font-mono">105,406,539</td>
      </tr>
      <tr>
        <td>
          <a class="inline-block" href="/networks/mantle-mainnet">
            <span class="inline-flex w-fit items-center gap-1.5 px-2 py-1 text-xs font-mono uppercase ring-1 ring-inset ring-(--border) text-(--foreground)">
  Mantle Mainnet
</span>
</a>        </td>
        <td class="font-mono">5000</td>
        <td>137</td>
        <td>1532</td>
        <td>
            <span class="coming-soon-pill">Coming Soon</span>
        </td>
        <td class="text-(--foreground-light) font-mono">96,930,501</td>
      </tr>
  </tbody>
</table>
"""


# ─── Tests ──────────────────────────────────────────────────────────────────

def test_parse_network_page_mantle():
    """Test parsing the Mantle per-network page against real captured HTML."""
    stats = parse_network_page(MANTLE_PAGE_FIXTURE, "mantle-mainnet")

    assert stats.network_slug == "mantle-mainnet"
    assert stats.network_name == "Mantle Mainnet"
    assert stats.agents == 137, f"Expected 137 agents, got {stats.agents}"
    assert stats.feedback == 1532, f"Expected 1532 feedback, got {stats.feedback}"
    assert stats.validations == "Coming Soon", f"Expected 'Coming Soon', got {stats.validations}"
    assert stats.last_indexed_block == 96930543, f"Expected 96930543, got {stats.last_indexed_block}"
    assert stats.chain_id == 5000, f"Expected chain id 5000, got {stats.chain_id}"
    assert stats.scrape_error is None

    print("✅ test_parse_network_page_mantle passed")


def test_parse_networks_table():
    """Test parsing the /networks table against real captured HTML."""
    results = parse_networks_table(NETWORKS_TABLE_FIXTURE)

    assert len(results) == 3, f"Expected 3 rows, got {len(results)}"

    # Check Base
    base = next(r for r in results if r.network_slug == "base-mainnet")
    assert base.agents == 55938, f"Expected 55938 Base agents, got {base.agents}"
    assert base.feedback == 265197, f"Expected 265197, got {base.feedback}"
    assert base.chain_id == 8453

    # Check BNB
    bnb = next(r for r in results if r.network_slug == "bnb-mainnet")
    assert bnb.agents == 139543, f"Expected 139543, got {bnb.agents}"
    assert bnb.feedback == 29490

    # Check Mantle
    mantle = next(r for r in results if r.network_slug == "mantle-mainnet")
    assert mantle.agents == 137
    assert mantle.feedback == 1532
    assert mantle.last_indexed_block == 96930501

    print("✅ test_parse_networks_table passed")


def test_adi_computation():
    """Test the ADI formula: agents per $1M TVL."""
    # Mantle example: 137 agents, ~$145M TVL
    adi = compute_adi(137, 145_000_000)
    assert adi is not None
    expected = (137 / 145_000_000) * 1_000_000
    assert abs(adi - expected) < 0.0001, f"Expected ~{expected:.4f}, got {adi:.4f}"

    # Ethereum: 35245 agents, ~$39B TVL
    adi_eth = compute_adi(35245, 39_000_000_000)
    assert adi_eth is not None
    # Mantle should have higher ADI than Ethereum (fewer agents but MUCH smaller TVL)
    # Mantle: 137 / 145M * 1M ≈ 0.945, Ethereum: 35245 / 39B * 1M ≈ 0.000904
    assert adi > adi_eth, f"Mantle ADI ({adi:.4f}) should be higher than Ethereum ADI ({adi_eth:.6f})"

    # Edge cases
    assert compute_adi(None, 100) is None
    assert compute_adi(100, None) is None
    assert compute_adi(100, 0) is None
    assert compute_adi(100, -1) is None

    print("✅ test_adi_computation passed")


def test_csv_append_preserves_seed():
    """Test that CSV append does not overwrite existing data."""
    from logger import append_csv, CSV_FIELDS

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        # Write seed row
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        seed_row = {
            "timestamp": "2026-06-20T21:30:00Z",
            "agents": 126,
            "feedback": 1244,
            "validations": "Coming Soon",
            "last_indexed_block": 96593016,
        }
        writer.writerow(seed_row)
        filepath = f.name

    import csv as csv_mod

    # Append a new row
    new_row = {
        "timestamp": "2026-06-21T09:00:00Z",
        "agents": 140,
        "feedback": 1600,
        "validations": "Coming Soon",
        "last_indexed_block": 97000000,
    }
    append_csv(filepath, new_row, CSV_FIELDS)

    # Verify both rows exist
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv_mod.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    assert rows[0]["timestamp"] == "2026-06-20T21:30:00Z", "Seed row modified!"
    assert rows[0]["agents"] == "126", f"Seed agents modified! Got {rows[0]['agents']}"
    assert rows[1]["timestamp"] == "2026-06-21T09:00:00Z"
    assert rows[1]["agents"] == "140"

    os.unlink(filepath)
    print("✅ test_csv_append_preserves_seed passed")


def test_network_stats_dataclass():
    """Test NetworkStats dataclass serialization."""
    stats = NetworkStats(
        network_slug="test-chain",
        network_name="Test Chain",
        agents=42,
        feedback=100,
        validations="Coming Soon",
        last_indexed_block=1000,
        chain_id=9999,
    )

    d = stats.to_dict()
    assert d["network_slug"] == "test-chain"
    assert d["agents"] == 42
    assert d["validations"] == "Coming Soon"
    assert d["scrape_error"] is None

    print("✅ test_network_stats_dataclass passed")


# ─── Run all tests ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import csv

    print("\n🧪 Running Mantle Agent Pulse tests...\n")

    test_parse_network_page_mantle()
    test_parse_networks_table()
    test_adi_computation()
    test_csv_append_preserves_seed()
    test_network_stats_dataclass()

    print("\n✅ All tests passed!\n")
