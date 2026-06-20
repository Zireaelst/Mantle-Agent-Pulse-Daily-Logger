"""
Mantle Agent Pulse — HTML Scraper for ERC-8004 Explorer

Scrapes the Quicknode ERC-8004 explorer public pages (NOT the paywalled REST API).
Extracts agent count, feedback count, validation count, and last indexed block
from both per-network pages and the /networks listing table.

The parser uses regex against raw HTML rather than BeautifulSoup for the per-network
page because the stat cards use CSS classes, not semantic IDs, making regex on the
label+value pattern more reliable than DOM traversal that could break on class renames.

For the /networks listing table, we parse the HTML table structure.
"""

import re
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

import requests
from bs4 import BeautifulSoup

from config import (
    ERC8004_EXPLORER_BASE,
    ERC8004_NETWORKS_URL,
    HTTP_TIMEOUT,
    HTTP_RETRIES,
    HTTP_BACKOFF,
)

logger = logging.getLogger(__name__)


@dataclass
class NetworkStats:
    """Stats for a single network from the ERC-8004 explorer."""
    network_slug: str
    network_name: str = ""
    agents: Optional[int] = None
    feedback: Optional[int] = None
    validations: Optional[str] = None  # "Coming Soon" or an int-as-string
    last_indexed_block: Optional[int] = None
    chain_id: Optional[int] = None
    scrape_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def fetch_page(url: str) -> Optional[str]:
    """
    Fetch a page with retries and exponential backoff.
    Returns the HTML text or None on failure.
    """
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT, headers={
                "User-Agent": "MantleAgentPulse/1.0 (research-tool)"
            })
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            wait = HTTP_BACKOFF ** attempt
            logger.warning(
                f"Fetch attempt {attempt}/{HTTP_RETRIES} failed for {url}: {e}. "
                f"Retrying in {wait:.1f}s..."
            )
            if attempt < HTTP_RETRIES:
                time.sleep(wait)
    logger.error(f"All {HTTP_RETRIES} fetch attempts failed for {url}")
    return None


def parse_network_page(html: str, slug: str) -> NetworkStats:
    """
    Parse a per-network page (e.g. /networks/mantle-mainnet) to extract stats.

    The page has stat cards like:
        <div class="...">Agents</div>
        <div class="...">137</div>

    We use regex to find label-value pairs in the article cards.
    """
    stats = NetworkStats(network_slug=slug)

    # Extract network name from h1
    h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
    if h1_match:
        name = h1_match.group(1).strip()
        # Strip "ERC-8004 Agents on " prefix
        name = re.sub(r'^ERC-8004\s+Agents\s+on\s+', '', name)
        stats.network_name = name

    # Parse stat cards — each is an <article> with a label div and a value div.
    # Pattern: label in uppercase text-xs div, value in text-3xl div.
    card_pattern = re.compile(
        r'<article[^>]*>\s*'
        r'<div[^>]*>([^<]+)</div>\s*'
        r'<div[^>]*>\s*'
        r'(?:<span[^>]*>)?'        # optional span wrapper
        r'([\s\S]*?)'              # value (could be text or "Coming Soon" span)
        r'(?:</span>)?'            # optional closing span
        r'\s*</div>\s*'
        r'</article>',
        re.DOTALL
    )

    for card_match in card_pattern.finditer(html):
        label = card_match.group(1).strip().lower()
        raw_value = card_match.group(2).strip()

        # Clean the value: strip HTML tags, whitespace
        clean_value = re.sub(r'<[^>]+>', '', raw_value).strip()
        # Remove commas from numbers
        clean_number = clean_value.replace(',', '').strip()

        if 'agent' in label and 'chain' not in label:
            try:
                stats.agents = int(clean_number)
            except ValueError:
                stats.agents = None
        elif 'feedback' in label:
            try:
                stats.feedback = int(clean_number)
            except ValueError:
                stats.feedback = None
        elif 'validation' in label and 'event' in label:
            if 'coming soon' in clean_value.lower():
                stats.validations = "Coming Soon"
            else:
                stats.validations = clean_number
        elif 'last indexed' in label or 'indexed block' in label:
            try:
                stats.last_indexed_block = int(clean_number)
            except ValueError:
                stats.last_indexed_block = None
        elif 'chain id' in label:
            try:
                stats.chain_id = int(clean_number)
            except ValueError:
                stats.chain_id = None

    return stats


def scrape_network(slug: str) -> NetworkStats:
    """Scrape stats for a single network from its ERC-8004 explorer page."""
    url = f"{ERC8004_EXPLORER_BASE}/networks/{slug}"
    logger.info(f"Scraping {url}...")

    html = fetch_page(url)
    if html is None:
        return NetworkStats(
            network_slug=slug,
            scrape_error=f"Failed to fetch {url} after {HTTP_RETRIES} retries"
        )

    try:
        stats = parse_network_page(html, slug)
        if stats.agents is None and stats.feedback is None:
            stats.scrape_error = "Parsed page but found no agent/feedback data"
        return stats
    except Exception as e:
        return NetworkStats(
            network_slug=slug,
            scrape_error=f"Parse error: {e}"
        )


def discover_network_slugs() -> List[str]:
    """
    Fetch the /networks page and extract all network slugs dynamically.
    Returns a list of slug strings (e.g. ['mantle-mainnet', 'base-mainnet', ...]).
    """
    logger.info(f"Discovering network slugs from {ERC8004_NETWORKS_URL}...")
    html = fetch_page(ERC8004_NETWORKS_URL)
    if html is None:
        logger.warning("Could not fetch /networks page, using hardcoded slugs")
        return []

    # Slugs appear in href="/networks/{slug}"
    slugs = re.findall(r'href="/networks/([a-z0-9-]+)"', html)
    # Deduplicate while preserving order
    seen = set()
    unique_slugs = []
    for s in slugs:
        if s not in seen:
            seen.add(s)
            unique_slugs.append(s)

    logger.info(f"Discovered {len(unique_slugs)} network slugs: {unique_slugs}")
    return unique_slugs


def parse_networks_table(html: str) -> List[NetworkStats]:
    """
    Parse the /networks page HTML table to get stats for all networks at once.
    This is faster than scraping each network page individually.

    The table has columns: Network, EIP-155 chain id, Agents, Feedback, Validations, Last indexed block
    """
    results = []

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="ds-table")
    if not table:
        logger.warning("Could not find ds-table on /networks page")
        return results

    tbody = table.find("tbody")
    if not tbody:
        logger.warning("No tbody in networks table")
        return results

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue

        # Extract slug from the link
        link = cells[0].find("a")
        if not link or "href" not in link.attrs:
            continue
        href = link["href"]
        slug_match = re.search(r'/networks/([a-z0-9-]+)', href)
        if not slug_match:
            continue
        slug = slug_match.group(1)

        # Extract network name from the link text.
        # The span contains SVG icons + text; NavigableString children
        # give us just the text nodes, skipping SVG content.
        name = ""
        name_span = cells[0].find("span", recursive=True)
        if name_span:
            from bs4 import NavigableString
            text_parts = [
                s.strip() for s in name_span.find_all(string=True, recursive=False)
                if s.strip()
            ]
            if text_parts:
                name = " ".join(text_parts)
            else:
                # Fallback: derive from slug
                name = slug.replace("-", " ").title()

        # Extract values
        def parse_cell_int(cell) -> Optional[int]:
            text = cell.get_text(strip=True).replace(",", "")
            try:
                return int(text)
            except ValueError:
                return None

        chain_id = parse_cell_int(cells[1])
        agents = parse_cell_int(cells[2])
        feedback = parse_cell_int(cells[3])

        # Validations might be "Coming Soon"
        val_text = cells[4].get_text(strip=True)
        if "coming soon" in val_text.lower():
            validations = "Coming Soon"
        else:
            validations = val_text.replace(",", "")

        last_block = parse_cell_int(cells[5])

        results.append(NetworkStats(
            network_slug=slug,
            network_name=name,
            agents=agents,
            feedback=feedback,
            validations=validations,
            last_indexed_block=last_block,
            chain_id=chain_id,
        ))

    return results


def scrape_all_networks_fast() -> List[NetworkStats]:
    """
    Scrape all network stats from the /networks table page in a single request.
    Falls back to individual page scraping if the table parse fails.
    """
    html = fetch_page(ERC8004_NETWORKS_URL)
    if html is None:
        logger.error("Failed to fetch /networks page")
        return []

    results = parse_networks_table(html)
    if results:
        logger.info(f"Parsed {len(results)} networks from /networks table")
    else:
        logger.warning("Table parse returned empty, falling back to individual scrapes")
        slugs = discover_network_slugs()
        for slug in slugs:
            results.append(scrape_network(slug))
            time.sleep(0.5)  # Be polite

    return results
