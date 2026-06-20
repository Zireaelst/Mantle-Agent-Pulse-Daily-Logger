"""
Mantle Agent Pulse — Configuration & Constants

All hardcoded addresses, endpoints, and contract details are documented here
with verification dates. Re-verify on mantlescan.xyz before relying on them
for anything that costs gas.

Last verified: 2026-06-20 against https://erc-8004.quicknode.com/networks/mantle-mainnet
"""

from typing import Dict, List

# ─── Mantle Mainnet ─────────────────────────────────────────────────────────

MANTLE_CHAIN_ID: int = 5000
MANTLE_NATIVE_TOKEN: str = "MNT"

# Public RPC endpoints — tried in order; first to connect + return chain id 5000 wins.
# Verified 2026-06-20.
MANTLE_RPC_ENDPOINTS: List[str] = [
    "https://rpc.mantle.xyz",
    "https://mantle.publicnode.com",
    "https://5000.rpc.thirdweb.com",
]

MANTLE_BLOCK_EXPLORER: str = "https://mantlescan.xyz"

# ─── ERC-8004 Registry Contracts on Mantle Mainnet ──────────────────────────
# Verified 2026-06-20 against https://erc-8004.quicknode.com/networks/mantle-mainnet

IDENTITY_REGISTRY_ADDRESS: str = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
REPUTATION_REGISTRY_ADDRESS: str = "0x8004baa17c55a88189ae136b182e5fda19de9b63"
# ValidationRegistry: not yet deployed as of 2026-06-20 ("Coming Soon")
VALIDATION_REGISTRY_ADDRESS: str = None  # type: ignore

# ERC-721 Transfer event signature (a new agent = mint from zero address)
TRANSFER_EVENT_TOPIC: str = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
ZERO_ADDRESS_TOPIC: str = (
    "0x0000000000000000000000000000000000000000000000000000000000000000"
)

# ─── ERC-8004 Explorer (Quicknode) ──────────────────────────────────────────
# Website UI is NOT paywalled; REST API IS paywalled via x402.
# We use plain HTTP GET + HTML parsing against public pages only.
# Verified 2026-06-20.

ERC8004_EXPLORER_BASE: str = "https://erc-8004.quicknode.com"
ERC8004_NETWORKS_URL: str = f"{ERC8004_EXPLORER_BASE}/networks"

# ─── Peer Chains for Comparison ────────────────────────────────────────────
# Network slugs on the ERC-8004 explorer. Verified live 2026-06-20.
# The scraper will also dynamically discover slugs from /networks.

PEER_CHAIN_SLUGS: List[str] = [
    "mantle-mainnet",
    "base-mainnet",
    "bnb-mainnet",
    "avalanche-mainnet",
    "celo-mainnet",
    "ethereum-mainnet",
]

# Mapping from ERC-8004 explorer network slug to DefiLlama chain name.
# DefiLlama uses its own naming: verified 2026-06-20 against api.llama.fi/v2/chains.
SLUG_TO_DEFILLAMA: Dict[str, str] = {
    "mantle-mainnet": "Mantle",
    "base-mainnet": "Base",
    "bnb-mainnet": "BSC",
    "avalanche-mainnet": "Avalanche",
    "celo-mainnet": "Celo",
    "ethereum-mainnet": "Ethereum",
}

# ─── DefiLlama ──────────────────────────────────────────────────────────────
# Free, no-auth TVL API. Verified 2026-06-20.

DEFILLAMA_CHAINS_URL: str = "https://api.llama.fi/v2/chains"

# ─── Data Paths ─────────────────────────────────────────────────────────────

DATA_DIR: str = "mantle_agent_pulse_data"
CSV_LOG_FILE: str = f"{DATA_DIR}/mantle_agent_pulse_log.csv"
JSON_LOG_FILE: str = f"{DATA_DIR}/mantle_agent_pulse_log.json"
PEER_CSV_FILE: str = f"{DATA_DIR}/peer_chain_data.csv"
PEER_JSON_FILE: str = f"{DATA_DIR}/peer_chain_data.json"
ADI_CSV_FILE: str = f"{DATA_DIR}/adi_data.csv"
ADI_JSON_FILE: str = f"{DATA_DIR}/adi_data.json"
REPORT_DIR: str = "reports"

# ─── On-Chain Scan Defaults ─────────────────────────────────────────────────

# Target date for the start of the on-chain log scan (ERC-8004 live since ~Feb 16 2026)
ONCHAIN_START_DATE: str = "2026-02-01"

# Initial chunk size for eth_getLogs (will shrink adaptively on error)
INITIAL_CHUNK_SIZE: int = 50_000
MIN_CHUNK_SIZE: int = 100

# ─── HTTP Defaults ──────────────────────────────────────────────────────────

HTTP_TIMEOUT: int = 30  # seconds
HTTP_RETRIES: int = 3
HTTP_BACKOFF: float = 2.0  # exponential backoff base

# ─── ERC-8004 IdentityRegistry ABI (minimal, for --register-agent) ──────────
# Only the registerAgent function is needed.

IDENTITY_REGISTRY_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "name", "type": "string"},
            {"internalType": "string", "name": "metadataURI", "type": "string"},
        ],
        "name": "registerAgent",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
        ],
        "name": "Transfer",
        "outputs": [],
        "type": "event",
    },
]
