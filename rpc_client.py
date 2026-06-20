"""
Mantle Agent Pulse — RPC Client

Handles direct on-chain interactions with Mantle Mainnet:
- RPC endpoint fallback (try each endpoint until one works)
- Chain head block number
- Contract bytecode verification
- Adaptive chunked eth_getLogs for independent agent registration recount
- Binary-search block estimation from target date

The adaptive chunk-shrinking pattern: start with a large block range for eth_getLogs,
and if the RPC returns an error (often "query returned more than X results" or
"block range too large"), halve the chunk size and retry. This converges to a working
chunk size for any RPC provider's limits.
"""

import time
import logging
import math
from datetime import datetime, timezone
from typing import Optional, Tuple, List

from web3 import Web3

from config import (
    MANTLE_RPC_ENDPOINTS,
    MANTLE_CHAIN_ID,
    IDENTITY_REGISTRY_ADDRESS,
    REPUTATION_REGISTRY_ADDRESS,
    TRANSFER_EVENT_TOPIC,
    ZERO_ADDRESS_TOPIC,
    INITIAL_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    ONCHAIN_START_DATE,
)

logger = logging.getLogger(__name__)


def connect_rpc() -> Optional[Web3]:
    """
    Try each Mantle RPC endpoint in order. Return the first Web3 instance
    that connects and returns chain id 5000. Returns None if all fail.
    """
    for endpoint in MANTLE_RPC_ENDPOINTS:
        try:
            w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={"timeout": 15}))
            if w3.is_connected():
                chain_id = w3.eth.chain_id
                if chain_id == MANTLE_CHAIN_ID:
                    logger.info(f"Connected to {endpoint} (chain id {chain_id})")
                    return w3
                else:
                    logger.warning(
                        f"{endpoint} returned chain id {chain_id}, expected {MANTLE_CHAIN_ID}"
                    )
            else:
                logger.warning(f"Could not connect to {endpoint}")
        except Exception as e:
            logger.warning(f"Error connecting to {endpoint}: {e}")
    return None


def get_chain_head(w3: Web3) -> Optional[int]:
    """Get the current head block number."""
    try:
        return w3.eth.block_number
    except Exception as e:
        logger.error(f"Error getting chain head: {e}")
        return None


def verify_contract_bytecode(w3: Web3, address: str) -> bool:
    """
    Verify that an address has deployed bytecode (i.e. is a smart contract).
    Returns True if bytecode exists and is non-empty, False otherwise.
    """
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(address))
        has_code = len(code) > 0
        if has_code:
            logger.info(f"Contract at {address}: bytecode OK ({len(code)} bytes)")
        else:
            logger.warning(f"Contract at {address}: NO bytecode found!")
        return has_code
    except Exception as e:
        logger.error(f"Error checking bytecode at {address}: {e}")
        return False


def estimate_block_at_date(w3: Web3, target_date_str: str) -> int:
    """
    Binary search to find the block number closest to a target date.
    Mantle's block time is ~2 seconds (OP Stack L2).

    Args:
        w3: Connected Web3 instance
        target_date_str: Date string in YYYY-MM-DD format

    Returns:
        Block number closest to (but not after) the target date
    """
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    target_ts = int(target_dt.timestamp())

    head = w3.eth.block_number

    # Use a rough estimate first: ~2s blocks on Mantle
    seconds_ago = int(time.time()) - target_ts
    blocks_ago = seconds_ago // 2
    estimated_start = max(1, head - blocks_ago)

    # Binary search between estimated_start (could be too low) and head
    lo = max(1, estimated_start - 5_000_000)  # generous lower bound
    hi = head

    logger.info(
        f"Binary searching for block at {target_date_str} "
        f"(ts={target_ts}), range [{lo}, {hi}]"
    )

    for _ in range(50):  # max 50 iterations should be more than enough
        if lo >= hi:
            break
        mid = (lo + hi) // 2
        try:
            block = w3.eth.get_block(mid)
            block_ts = block["timestamp"]
            if block_ts < target_ts:
                lo = mid + 1
            else:
                hi = mid
        except Exception as e:
            logger.warning(f"Error fetching block {mid}: {e}")
            # If we can't fetch a block, try moving up
            lo = mid + 1

    logger.info(f"Estimated block at {target_date_str}: {lo}")
    return lo


def count_registrations_onchain(
    w3: Web3,
    from_block: int,
    to_block: int,
    registry_address: str = IDENTITY_REGISTRY_ADDRESS,
) -> Tuple[int, List[int]]:
    """
    Count agent registrations (Transfer events from zero address = mints)
    directly from chain logs using adaptive chunked eth_getLogs.

    This is the independent on-chain recount used by --full-verify.

    Args:
        w3: Connected Web3 instance
        from_block: Start block (inclusive)
        to_block: End block (inclusive)
        registry_address: Contract address to scan

    Returns:
        Tuple of (total_count, list_of_token_ids)
    """
    checksum_addr = Web3.to_checksum_address(registry_address)
    chunk_size = INITIAL_CHUNK_SIZE
    current_block = from_block
    total_mints = 0
    token_ids: List[int] = []

    total_blocks = to_block - from_block
    logger.info(
        f"Scanning {total_blocks:,} blocks [{from_block:,} → {to_block:,}] "
        f"for Transfer(from=0x0) on {checksum_addr}"
    )

    while current_block <= to_block:
        end_block = min(current_block + chunk_size - 1, to_block)

        try:
            logs = w3.eth.get_logs({
                "fromBlock": current_block,
                "toBlock": end_block,
                "address": checksum_addr,
                "topics": [TRANSFER_EVENT_TOPIC, ZERO_ADDRESS_TOPIC],
            })

            for log_entry in logs:
                total_mints += 1
                # Token ID is the third topic (indexed uint256)
                if len(log_entry["topics"]) >= 3:
                    token_id = int(log_entry["topics"][2].hex(), 16)
                    token_ids.append(token_id)

            progress = ((end_block - from_block) / total_blocks) * 100 if total_blocks > 0 else 100
            logger.info(
                f"  Blocks {current_block:,}–{end_block:,}: "
                f"{len(logs)} mints (total so far: {total_mints}) "
                f"[{progress:.1f}%]"
            )

            current_block = end_block + 1

            # If chunk succeeded, try growing it back (up to initial)
            if chunk_size < INITIAL_CHUNK_SIZE:
                chunk_size = min(chunk_size * 2, INITIAL_CHUNK_SIZE)

        except Exception as e:
            error_str = str(e).lower()
            if (
                "too many" in error_str
                or "block range" in error_str
                or "query returned" in error_str
                or "limit" in error_str
                or "exceed" in error_str
                or "400 client error" in error_str
                or "bad request" in error_str
            ):
                # Adaptive shrink: halve chunk size
                chunk_size = max(chunk_size // 2, MIN_CHUNK_SIZE)
                logger.warning(
                    f"  Range too large, shrinking chunk to {chunk_size:,} blocks"
                )
                if chunk_size <= MIN_CHUNK_SIZE:
                    logger.error(
                        f"  Chunk size at minimum ({MIN_CHUNK_SIZE}), "
                        f"block {current_block} may be stuck. Skipping."
                    )
                    current_block = end_block + 1
            else:
                logger.error(
                    f"  Unexpected error at block {current_block}: {e}. "
                    f"Waiting 5s and retrying..."
                )
                time.sleep(5)

    logger.info(f"On-chain recount complete: {total_mints} total mints")
    return total_mints, token_ids


def rpc_sanity_check() -> dict:
    """
    Quick RPC sanity check:
    - Connect to an RPC endpoint
    - Get chain head block
    - Verify IdentityRegistry has deployed bytecode
    - Verify ReputationRegistry has deployed bytecode

    Returns a dict with results.
    """
    result = {
        "rpc_connected": False,
        "rpc_endpoint": None,
        "chain_id": None,
        "chain_head_block": None,
        "identity_registry_deployed": None,
        "reputation_registry_deployed": None,
        "error": None,
    }

    w3 = connect_rpc()
    if w3 is None:
        result["error"] = "Could not connect to any Mantle RPC endpoint"
        return result

    result["rpc_connected"] = True
    result["rpc_endpoint"] = w3.provider.endpoint_uri
    result["chain_id"] = MANTLE_CHAIN_ID

    head = get_chain_head(w3)
    result["chain_head_block"] = head

    result["identity_registry_deployed"] = verify_contract_bytecode(
        w3, IDENTITY_REGISTRY_ADDRESS
    )
    result["reputation_registry_deployed"] = verify_contract_bytecode(
        w3, REPUTATION_REGISTRY_ADDRESS
    )

    return result
