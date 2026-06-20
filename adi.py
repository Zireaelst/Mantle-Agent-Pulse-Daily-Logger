"""
Mantle Agent Pulse — Agent Density Index (ADI)

Computes the Agent Density Index for cross-chain comparison.

    ADI = (registered_agents / chain_TVL_in_USD) × 1,000,000

    In words: registered agents per $1 million of chain TVL.

This normalizes for chain size, letting us compare Mantle's ERC-8004 adoption
against larger chains like BNB Chain or Ethereum on a level playing field.

A higher ADI means more agent registrations relative to the economic activity
on the chain — a signal of stronger developer/community adoption of the
ERC-8004 standard relative to overall chain usage.

Data sources:
- Agent counts: ERC-8004 Explorer (Quicknode) public web pages
- TVL: DefiLlama free API (api.llama.fi/v2/chains)
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import requests

from config import (
    DEFILLAMA_CHAINS_URL,
    SLUG_TO_DEFILLAMA,
    HTTP_TIMEOUT,
)

logger = logging.getLogger(__name__)


@dataclass
class ADIRecord:
    """One ADI computation record for a chain."""
    network_slug: str
    network_name: str
    defillama_name: str
    agents: Optional[int]
    tvl_usd: Optional[float]
    adi: Optional[float]  # agents per $1M TVL
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fetch_chain_tvls() -> Dict[str, float]:
    """
    Fetch current TVL for all chains from DefiLlama.
    Returns a dict mapping chain name (as DefiLlama reports it) to TVL in USD.
    """
    try:
        resp = requests.get(DEFILLAMA_CHAINS_URL, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        tvl_map: Dict[str, float] = {}
        for chain in data:
            name = chain.get("name", "")
            tvl = chain.get("tvl", 0)
            if name and tvl is not None:
                tvl_map[name] = float(tvl)
        logger.info(f"Fetched TVL data for {len(tvl_map)} chains from DefiLlama")
        return tvl_map
    except Exception as e:
        logger.error(f"Failed to fetch DefiLlama chain TVLs: {e}")
        return {}


def compute_adi(
    agents: Optional[int],
    tvl_usd: Optional[float],
) -> Optional[float]:
    """
    Compute ADI = (agents / tvl_usd) * 1_000_000

    Returns None if either input is None/zero/invalid.
    """
    if agents is None or tvl_usd is None or tvl_usd <= 0:
        return None
    return (agents / tvl_usd) * 1_000_000


def compute_adi_for_chains(
    network_stats: List[Any],  # List of NetworkStats from scraper
    slug_to_defillama: Dict[str, str] = SLUG_TO_DEFILLAMA,
) -> List[ADIRecord]:
    """
    Given scraped network stats and a mapping of slugs to DefiLlama names,
    fetch TVLs and compute ADI for each chain.

    Args:
        network_stats: List of NetworkStats dataclass instances
        slug_to_defillama: Dict mapping ERC-8004 slug → DefiLlama chain name

    Returns:
        List of ADIRecord instances
    """
    tvl_map = fetch_chain_tvls()
    records: List[ADIRecord] = []

    for stats in network_stats:
        slug = stats.network_slug
        dl_name = slug_to_defillama.get(slug)

        if dl_name is None:
            logger.debug(f"No DefiLlama mapping for slug '{slug}', skipping ADI")
            continue

        tvl = tvl_map.get(dl_name)
        if tvl is None:
            logger.warning(
                f"No TVL data from DefiLlama for '{dl_name}' (slug: {slug})"
            )

        adi_value = compute_adi(stats.agents, tvl)

        records.append(ADIRecord(
            network_slug=slug,
            network_name=stats.network_name or dl_name,
            defillama_name=dl_name,
            agents=stats.agents,
            tvl_usd=tvl,
            adi=adi_value,
            error=None if tvl is not None else f"No TVL data for {dl_name}",
        ))

    # Sort by ADI descending (None values last)
    records.sort(key=lambda r: r.adi if r.adi is not None else -1, reverse=True)

    return records
