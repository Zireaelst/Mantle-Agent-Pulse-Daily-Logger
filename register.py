"""
Mantle Agent Pulse — On-Chain Agent Registration

Optional feature: register this tool itself on Mantle's ERC-8004 IdentityRegistry.
This sends a REAL transaction and costs REAL MNT gas.

Gated behind:
(a) Private key read ONLY from the AGENT_PRIVATE_KEY environment variable
(b) Explicit interactive confirmation prompt showing exact tx details
(c) Never called from the daily logger's default path

Usage:
    python logger.py --register-agent

Requires:
    - AGENT_PRIVATE_KEY env var set (or in .env file)
    - The wallet must be funded with MNT for gas
"""

import os
import sys
import logging
from typing import Optional

from web3 import Web3

from config import (
    IDENTITY_REGISTRY_ADDRESS,
    IDENTITY_REGISTRY_ABI,
    MANTLE_CHAIN_ID,
)
from rpc_client import connect_rpc

logger = logging.getLogger(__name__)


def register_agent(
    name: str = "mantle-agent-pulse",
    metadata_uri: str = "https://github.com/Zireaelst/Mantle-Agent-Pulse-Daily-Logger",
) -> Optional[str]:
    """
    Register this tool as an agent on Mantle's ERC-8004 IdentityRegistry.

    This function:
    1. Reads the private key from AGENT_PRIVATE_KEY env var
    2. Connects to Mantle RPC
    3. Builds the registerAgent transaction
    4. Shows all tx details and asks for explicit confirmation
    5. Signs and sends the transaction
    6. Returns the transaction hash

    Returns:
        Transaction hash string, or None if cancelled/failed.
    """
    # Load env vars (from .env if present)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Read overrides from env
    name = os.environ.get("AGENT_NAME", name)
    metadata_uri = os.environ.get("AGENT_METADATA_URI", metadata_uri)

    # (a) Private key from env var only
    private_key = os.environ.get("AGENT_PRIVATE_KEY")
    if not private_key:
        logger.error(
            "AGENT_PRIVATE_KEY environment variable not set.\n"
            "Set it in your .env file or export it:\n"
            "  export AGENT_PRIVATE_KEY=0xYOUR_PRIVATE_KEY_HERE\n"
            "WARNING: Never commit your private key!"
        )
        return None

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # Connect to RPC
    w3 = connect_rpc()
    if w3 is None:
        logger.error("Could not connect to any Mantle RPC endpoint")
        return None

    # Derive account address
    try:
        account = w3.eth.account.from_key(private_key)
        sender = account.address
    except Exception as e:
        logger.error(f"Invalid private key: {e}")
        return None

    # Check balance
    balance_wei = w3.eth.get_balance(sender)
    balance_mnt = w3.from_wei(balance_wei, "ether")
    logger.info(f"Wallet {sender}: {balance_mnt:.6f} MNT")

    if balance_wei == 0:
        logger.error("Wallet has zero MNT balance. Fund it before registering.")
        return None

    # Build transaction
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(IDENTITY_REGISTRY_ADDRESS),
        abi=IDENTITY_REGISTRY_ABI,
    )

    try:
        nonce = w3.eth.get_transaction_count(sender)
        gas_price = w3.eth.gas_price

        tx = contract.functions.registerAgent(name, metadata_uri).build_transaction({
            "chainId": MANTLE_CHAIN_ID,
            "from": sender,
            "nonce": nonce,
            "gasPrice": gas_price,
        })

        # Estimate gas
        try:
            gas_estimate = w3.eth.estimate_gas(tx)
            tx["gas"] = int(gas_estimate * 1.2)  # 20% buffer
        except Exception as e:
            logger.warning(f"Gas estimation failed ({e}), using default 300,000")
            tx["gas"] = 300_000

        gas_cost_wei = tx["gas"] * gas_price
        gas_cost_mnt = w3.from_wei(gas_cost_wei, "ether")

    except Exception as e:
        logger.error(f"Failed to build transaction: {e}")
        return None

    # (b) Interactive confirmation
    print("\n" + "=" * 60)
    print("  ERC-8004 AGENT REGISTRATION — TRANSACTION DETAILS")
    print("=" * 60)
    print(f"  Network:        Mantle Mainnet (chain id {MANTLE_CHAIN_ID})")
    print(f"  Contract:       {IDENTITY_REGISTRY_ADDRESS}")
    print(f"  Function:       registerAgent(name, metadataURI)")
    print(f"  Agent Name:     {name}")
    print(f"  Metadata URI:   {metadata_uri}")
    print(f"  From:           {sender}")
    print(f"  Balance:        {balance_mnt:.6f} MNT")
    print(f"  Est. Gas:       {tx['gas']:,}")
    print(f"  Gas Price:      {w3.from_wei(gas_price, 'gwei'):.2f} Gwei")
    print(f"  Est. Gas Cost:  {gas_cost_mnt:.6f} MNT")
    print("=" * 60)
    print("\n  ⚠️  This will send a REAL transaction on Mantle Mainnet.")
    print("  ⚠️  MNT will be spent on gas. This cannot be undone.\n")

    confirm = input("  Type 'REGISTER' to confirm, anything else to cancel: ").strip()

    if confirm != "REGISTER":
        print("  ❌ Registration cancelled.")
        return None

    # (c) Sign and send
    try:
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"\n  ✅ Transaction sent: {tx_hash_hex}")
        print(f"  🔗 View on explorer: https://mantlescan.xyz/tx/{tx_hash_hex}")
        print("  ⏳ Waiting for confirmation...")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] == 1:
            print(f"  ✅ Registration confirmed in block {receipt['blockNumber']}")
            print(f"  ⛽ Gas used: {receipt['gasUsed']:,}")
            logger.info(f"Agent registered: tx={tx_hash_hex}, block={receipt['blockNumber']}")
            return tx_hash_hex
        else:
            print("  ❌ Transaction reverted!")
            logger.error(f"Registration tx reverted: {tx_hash_hex}")
            return None

    except Exception as e:
        logger.error(f"Transaction failed: {e}")
        return None
