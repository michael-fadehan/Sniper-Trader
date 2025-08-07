import asyncio
from typing import Optional, Dict, Any, List
import traceback
import threading
import requests
import json
import base64
import logging
import os
import random
import re
import sys
import time
import base58

# Import winsound for Windows beep functionality
try:
    import winsound
except ImportError:
    winsound = None  # Not available on non-Windows systems
from solana.rpc.commitment import Commitment
from solders.message import Message, MessageV0
from solders.commitment_config import CommitmentLevel
from solders.transaction import VersionedTransaction, Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.system_program import transfer, TransferParams
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import Instruction, AccountMeta
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID, WRAPPED_SOL_MINT
from spl.token.instructions import get_associated_token_address, create_associated_token_account, close_account, CloseAccountParams, transfer as spl_transfer, TransferParams as SPLTransferParams

# Use string-based commitment level for compatibility
COMMITMENT_CONFIRMED = "confirmed"  # Standard commitment level string

# SECOND_EDIT: helper function to send and confirm VersionedTransaction using current solana-py API
async def _send_and_confirm_tx(self, transaction: VersionedTransaction) -> bool:
    """Send the given transaction and wait for confirmation.

    Returns True on success, False otherwise.
    """
    try:
        self.log(f"[DEBUG] Transaction message: {transaction.message if hasattr(transaction, 'message') else 'N/A'}")
        self.log(f"[DEBUG] Transaction signatures before send: {[str(s) for s in transaction.signatures]}")
        
        # For Trojan bot wallets, we need to send raw transaction bytes
        raw_tx = bytes(transaction)
        
        # Send without duplicate opts parameter
        resp = self.client.send_raw_transaction(raw_tx)
        
        if not resp.value:
            self.log(f"❌ Unexpected response from send_raw_transaction: {resp}")
            return False
            
        signature = resp.value
        self.log(f"[DEBUG] Transaction sent with signature: {signature}")
        
        # Use string-based commitment for compatibility
        conf = self.client.confirm_transaction(signature, commitment="confirmed")
        if conf and conf.value:
            self.log(f"[DEBUG] Transaction confirmed with status: {conf.value}")
            return True
        
        self.log(f"❌ Transaction failed to confirm: {conf}")
        return False
        
    except Exception as exc:
        self.log(f"❌ Error sending/confirming transaction: {exc}\n{traceback.format_exc()}")
        return False

# THIRD_EDIT: add constant and helper for sending transactions with current solana-py API
async def _send_and_confirm_tx(self, transaction: VersionedTransaction) -> bool:
    """Send the given transaction and wait for confirmation.

    Returns True on success, False otherwise.
    """
    try:
        raw_tx = bytes(transaction) if isinstance(transaction, VersionedTransaction) else transaction.serialize()
        resp = self.client.send_raw_transaction(raw_tx)
        signature = getattr(resp, "value", None) if hasattr(resp, "value") else resp.get("result")
        if not signature:
            self.log(f"❌ Unexpected response from send_raw_transaction: {resp}")
            return False
        self.log(f"⏳ Submitted tx {signature}. Waiting for confirmation…")
        # Poll for confirmation (max 30 s)
        timeout = 30
        for _ in range(timeout):
            conf = self.client.confirm_transaction(signature, commitment=COMMITMENT_CONFIRMED)
            conf_val = getattr(conf, "value", conf.get("result", {}))
            if conf_val and conf_val.get("err") is None:
                self.log("✅ Jupiter swap transaction confirmed.")
                return True
            await asyncio.sleep(1)
        self.log(f"❌ Confirmation timeout for tx {signature}. Last status: {conf}")
        return False
    except Exception as exc:
        self.log(f"❌ Error sending/confirming transaction: {exc}\n{traceback.format_exc()}")
        return False

# --- BUY/SELL LOGIC FROM sniper_bot.py ---

async def execute_buy_token(self, token_mint_address: str, amount_to_spend_sol: float, pool_info: Dict[str, Any]) -> bool:
    self.log(f"[BUY] Called with token_mint_address={token_mint_address}, amount_to_spend_sol={amount_to_spend_sol}, pool_info_keys={list(pool_info.keys()) if pool_info else None}")
    if self.SIMULATION_MODE:
        self.log(f"SIMULATION: Attempting to buy token {token_mint_address[:8]}... for {amount_to_spend_sol:.4f} SOL (Jupiter)")
        return True
    amount_sol_lamports = int(amount_to_spend_sol * 1e9)
    input_mint = str(WRAPPED_SOL_MINT)
    output_mint = token_mint_address
    # 0. Check SOL balance before proceeding
    try:
        balance_resp = self.client.get_balance(self.keypair.pubkey())
        sol_balance = int(getattr(balance_resp, "value", 0))
        self.log(f"Wallet balance: {sol_balance} lamports ({sol_balance/1e9} SOL)")
        if sol_balance < amount_sol_lamports:
            self.log(f"ERROR: Insufficient SOL balance for swap. You have {sol_balance} lamports, need {amount_sol_lamports}.")
            return False
    except Exception as e:
        self.log(f"ERROR: Could not fetch wallet balance: {e}")
        return False
    # Pre-check: Does user have ATA for output token? If not, check for enough SOL for swap + ATA creation
    try:
        from spl.token.instructions import get_associated_token_address
        from solders.pubkey import Pubkey
        owner = self.keypair.pubkey()
        mint = Pubkey.from_string(output_mint) if isinstance(output_mint, str) else output_mint
        ata = get_associated_token_address(owner, mint)
        ata_info = self.client.get_account_info(ata)
        has_ata = ata_info and ata_info.get('result', {}).get('value') is not None
        if not has_ata:
            # Estimate ATA creation cost (approx 0.0021 SOL)
            ata_creation_lamports = int(0.0021 * 1e9)
            total_needed = amount_sol_lamports + ata_creation_lamports
            if sol_balance < total_needed:
                self.log(f"ERROR: Not enough SOL for swap + ATA creation. You have {sol_balance} lamports, need {total_needed} (swap: {amount_sol_lamports}, ATA: {ata_creation_lamports})")
                return False
            else:
                self.log(f"[INFO] No ATA for token {mint}. Will need to create one (cost: {ata_creation_lamports} lamports)")
    except Exception as e:
        self.log(f"[WARN] Could not check ATA existence: {e}")
    for attempt in range(1, 4):
        self.log(f"Attempting Jupiter buy for {token_mint_address[:8]}... (Attempt {attempt}/3)")
        slippage_bps = getattr(self, 'DEFAULT_SLIPPAGE_BPS', 100)
        try:
            quote_response = self._get_jupiter_quote(input_mint, output_mint, amount_sol_lamports, slippage_bps)
            self.log(f"[BUY] Quote outAmount={quote_response.get('outAmount') if quote_response else 'N/A'}, priceImpactPct={quote_response.get('priceImpactPct') if quote_response else 'N/A'}")
            if not quote_response or 'routePlan' not in quote_response:
                self.log(f"ERROR: No valid route found for swap or Jupiter API error.")
                continue
        except Exception as e:
            self.log(f"ERROR: Failed to fetch quote from Jupiter: {e}")
            continue
        try:
            raw_transaction_bytes = self._get_jupiter_swap_transaction_raw(quote_response)
            self.log(f"[BUY] Jupiter tx bytes length: {len(raw_transaction_bytes) if raw_transaction_bytes else 0}")
            if not raw_transaction_bytes:
                self.log(f"ERROR: No swapTransaction in Jupiter response. Full response: {raw_transaction_bytes}")
                continue
            swap_transaction_bytes = decode_base64_with_padding(raw_transaction_bytes)
            try:
                txn = VersionedTransaction.from_bytes(swap_transaction_bytes)
                self.log("\n=== Jupiter Swap Transaction Debug ===")
                self.log(f"Decoded transaction: {txn}")
            except Exception as e:
                self.log(f"ERROR: Failed to decode transaction: {e}. Full Jupiter swap response: {raw_transaction_bytes}")
                continue
            self.log("\n--- Signature Debug ---")
            self.log("Signatures before signing:")
            for i, sig in enumerate(txn.signatures):
                self.log(f"  [{i}] {sig}")
            self.log(f"Message: {txn.message}")
            self.log(f"Your public key: {self.keypair.pubkey()}")
            my_pk = self.keypair.pubkey()
            try:
                signer_index = list(txn.message.account_keys).index(my_pk)
            except ValueError:
                self.log("ERROR: Your pubkey is not one of the transaction signers!")
                return False
            from solders.message import to_bytes_versioned
            msg_bytes = to_bytes_versioned(txn.message)
            sig = self.keypair.sign_message(msg_bytes)
            self.log(f"type(sig): {type(sig)}")
            txn.signatures = [sig] + txn.signatures[1:]
            self.log("Signatures after signing:")
            for i, sig in enumerate(txn.signatures):
                self.log(f"  [{i}] {sig}")
            self.log("=== End Debug ===\n")
            self.log(f"signer_index: {signer_index}")
            self.log(f"account_keys[signer_index]: {txn.message.account_keys[signer_index]}")
            self.log(f"keypair pubkey: {self.keypair.pubkey()}")
            self.log(f"num_required_signatures: {txn.message.header.num_required_signatures}")
            self.log(f"signatures: {txn.signatures}")
            signed_txn_bytes = bytes(txn)
            self.log("Sending transaction to mainnet...")
            send_resp = self.client.send_raw_transaction(signed_txn_bytes)
            signature = getattr(send_resp, "value", send_resp)
            self.log(f"Signature: {signature}")
            if signature:
                self.log("✅ Jupiter swap transaction confirmed.")
                try:
                    if sys.platform == 'win32' and winsound:
                        winsound.MessageBeep()
                except Exception as beep_error:
                    self.log(f"[DEBUG] Beep failed (non-critical): {beep_error}")
                return True
            else:
                self.log(f"❌ Jupiter swap failed: Transaction not confirmed")
                continue
        except Exception as e:
            # Try to print simulation logs if available
            if hasattr(e, 'args') and e.args and isinstance(e.args[0], dict):
                err_data = e.args[0]
                if 'data' in err_data and 'logs' in err_data['data']:
                    self.log("Transaction simulation logs:")
                    for log in err_data['data']['logs']:
                        self.log(log)
            self.log(f"Error decoding/signing/sending transaction: {e}")
            if 'insufficient lamports' in str(e):
                self.log("ERROR: Your wallet does not have enough SOL to complete this swap.")
            elif 'No valid route' in str(e):
                self.log("ERROR: Jupiter could not find a route for this swap. The token may not be supported or liquidity is too low.")
            elif 'slippage' in str(e):
                self.log("ERROR: Slippage too high. Try increasing slippage tolerance or reducing trade size.")
            else:
                self.log("ERROR: An unknown error occurred. See above for details.")
            continue
        if attempt < 3:
            self.log(f"Retrying Jupiter swap in {attempt} second(s)...")
            await asyncio.sleep(attempt + 1)  # progressive backoff, add extra delay for rate limiting
    self.log(f"⚠️ Jupiter buy failed after 3 attempts for {token_mint_address[:8]}. No onchain fallback will be attempted.")
    return False

async def execute_sell_token(self, token_mint_address: str, amount_tokens_to_sell: float, pool_info: dict) -> bool:
    self.log(f"[SELL] Called with token_mint_address={token_mint_address}, amount_tokens_to_sell={amount_tokens_to_sell}, pool_info_keys={list(pool_info.keys()) if pool_info else None}")
    if self.SIMULATION_MODE:
        self.log(f"SIMULATION: Attempting to sell token {token_mint_address[:8]}... for {amount_tokens_to_sell:.4f} tokens (Jupiter)")
        return True
    # 0. Check SPL token balance before proceeding
    try:
        from spl.token.instructions import get_associated_token_address
        ata = get_associated_token_address(self.keypair.pubkey(), Pubkey.from_string(token_mint_address) if isinstance(token_mint_address, str) else token_mint_address)
        token_balance_resp = self.client.get_token_account_balance(ata)
        token_balance = float(token_balance_resp['result']['value']['amount'])
        self.log(f"Token balance: {token_balance} (raw amount)")
        if token_balance < amount_tokens_to_sell:
            self.log(f"ERROR: Insufficient token balance for swap. You have {token_balance}, need {amount_tokens_to_sell}.")
            return False
    except Exception as e:
        self.log(f"ERROR: Could not fetch token balance: {e}")
        return False
    # Convert amount to atomic units (lamports for SPL tokens)
    amount_token_atomic = int(amount_tokens_to_sell)
    input_mint = token_mint_address
    output_mint = str(WRAPPED_SOL_MINT)
    for attempt in range(1, 4):
        self.log(f"Attempting Jupiter sell for {token_mint_address[:8]}... (Attempt {attempt}/3)")
        slippage_bps = getattr(self, 'DEFAULT_SLIPPAGE_BPS', 100)
        try:
            quote_response = self._get_jupiter_quote(input_mint, output_mint, amount_token_atomic, slippage_bps)
            self.log(f"[SELL] Quote outAmount={quote_response.get('outAmount') if quote_response else 'N/A'}, priceImpactPct={quote_response.get('priceImpactPct') if quote_response else 'N/A'}")
            if not quote_response or 'routePlan' not in quote_response:
                self.log(f"ERROR: No valid route found for swap or Jupiter API error.")
                continue
        except Exception as e:
            self.log(f"ERROR: Failed to fetch quote from Jupiter: {e}")
            continue
        try:
            raw_transaction_bytes = self._get_jupiter_swap_transaction_raw(quote_response)
            self.log(f"[SELL] Jupiter tx bytes length: {len(raw_transaction_bytes) if raw_transaction_bytes else 0}")
            if not raw_transaction_bytes:
                self.log(f"ERROR: No swapTransaction in Jupiter response.")
                continue
            swap_transaction_bytes = base64.b64decode(raw_transaction_bytes)
            try:
                txn = VersionedTransaction.from_bytes(swap_transaction_bytes)
                self.log("\n=== Jupiter Swap Transaction Debug (SELL) ===")
                self.log(f"Decoded transaction: {txn}")
            except Exception as e:
                self.log(f"ERROR: Failed to decode transaction: {e}. Full Jupiter swap response: {raw_transaction_bytes}")
                continue
            self.log("\n--- Signature Debug ---")
            self.log("Signatures before signing:")
            for i, sig in enumerate(txn.signatures):
                self.log(f"  [{i}] {sig}")
            self.log(f"Message: {txn.message}")
            self.log(f"Your public key: {self.keypair.pubkey()}")
            my_pk = self.keypair.pubkey()
            try:
                signer_index = list(txn.message.account_keys).index(my_pk)
            except ValueError:
                self.log("ERROR: Your pubkey is not one of the transaction signers!")
                return False
            from solders.message import to_bytes_versioned
            msg_bytes = to_bytes_versioned(txn.message)
            sig = self.keypair.sign_message(msg_bytes)
            self.log(f"type(sig): {type(sig)}")
            txn.signatures = [sig] + txn.signatures[1:]
            self.log("Signatures after signing:")
            for i, sig in enumerate(txn.signatures):
                self.log(f"  [{i}] {sig}")
            self.log("=== End Debug ===\n")
            self.log(f"signer_index: {signer_index}")
            self.log(f"account_keys[signer_index]: {txn.message.account_keys[signer_index]}")
            self.log(f"keypair pubkey: {self.keypair.pubkey()}")
            self.log(f"num_required_signatures: {txn.message.header.num_required_signatures}")
            self.log(f"signatures: {txn.signatures}")
            signed_txn_bytes = bytes(txn)
            self.log("Sending transaction to mainnet...")
            send_resp = self.client.send_raw_transaction(signed_txn_bytes)
            signature = getattr(send_resp, "value", send_resp)
            self.log(f"Signature: {signature}")
            if signature:
                self.log("✅ Jupiter swap transaction confirmed (SELL).")
                try:
                    if sys.platform == 'win32' and winsound:
                        winsound.MessageBeep()
                except Exception as beep_error:
                    self.log(f"[DEBUG] Beep failed (non-critical): {beep_error}")
                return True
            else:
                self.log(f"❌ Jupiter swap failed: Transaction not confirmed (SELL)")
                continue
        except Exception as e:
            # Try to print simulation logs if available
            if hasattr(e, 'args') and e.args and isinstance(e.args[0], dict):
                err_data = e.args[0]
                if 'data' in err_data and 'logs' in err_data['data']:
                    self.log("Transaction simulation logs:")
                    for log in err_data['data']['logs']:
                        self.log(log)
            self.log(f"Error decoding/signing/sending transaction: {e}")
            if 'insufficient lamports' in str(e):
                self.log("ERROR: Your wallet does not have enough SOL to complete this swap.")
            elif 'No valid route' in str(e):
                self.log("ERROR: Jupiter could not find a route for this swap. The token may not be supported or liquidity is too low.")
            elif 'slippage' in str(e):
                self.log("ERROR: Slippage too high. Try increasing slippage tolerance or reducing trade size.")
            else:
                self.log("ERROR: An unknown error occurred. See above for details.")
            continue
        if attempt < 3:
            self.log(f"Retrying Jupiter swap in {attempt} second(s)...")
            await asyncio.sleep(attempt)  # progressive backoff
    self.log(f"⚠️ Jupiter sell failed after 3 attempts for {token_mint_address[:8]}. No onchain fallback will be attempted.")
    return False

    def _get_token_decimals_from_chain(self, mint_address: str):
        # Stub for linter, should be implemented in subclass or main bot
        return 9

class SniperSession:
    """Base class for sniper bot trading functionality"""
    
    def __init__(self, *args, **kwargs):
        self.keypair: Optional[Keypair] = None
        self.client: Any = None  # RPC client
        self.seen_tokens: set = set()  # Use set for .add()
        # Add default filter attributes (copy from sniper_bot.py or set reasonable defaults)
        self.MAX_PRICE_USD = 10.0
        self.MIN_LIQUIDITY_USD = 100.0
        self.MIN_VOLUME_5M_USD = 200.0
        self.MIN_BUYS_5M = 20
        self.MIN_PAIR_AGE_SECONDS = 2
        self.MAX_PAIR_AGE_SECONDS = 1800
        self.MIN_BUY_TX_RATIO = 0.5
        # Add trading and session attributes to fix attribute errors
        self.TAKE_PROFIT_PCT = 30
        self.STOP_LOSS_PCT = 15
        self.POSITION_SIZE_USD = kwargs.get("position_size", kwargs.get("position_size_usd", 20.0))
        self.BUY_FEE = 0.005
        self.sol_usd = 0.0
        import threading
        self.buy_lock = threading.Lock()
        self.SIMULATION_MODE = False
        self.tokens = {}
        self.watched_tokens = set()
        self.trades = []
        self.SELL_FEE = 0.005
        self.open_positions_file = "open_positions.json"
        self.load_open_positions()
    
    async def _send_and_confirm_tx(self, transaction: VersionedTransaction) -> bool:
        """Send the given transaction and wait for confirmation."""
        try:
            raw_tx = bytes(transaction) if isinstance(transaction, VersionedTransaction) else transaction.serialize()
            
            # Send without duplicate opts parameter
            self.log("[DEBUG] Sending raw transaction...")
            resp = self.client.send_raw_transaction(raw_tx)
            
            if not resp.value:
                self.log(f"❌ Unexpected response from send_raw_transaction: {resp}")
                return False
                
            signature = resp.value
            self.log(f"[DEBUG] Transaction sent with signature: {signature}")
            
            # Add retry logic for confirmation
            for attempt in range(3):
                try:
                    conf = self.client.confirm_transaction(signature, commitment="COMMITMENT_CONFIRMED")
                    if conf and conf.value:
                        self.log(f"[DEBUG] Transaction confirmed on attempt {attempt + 1}")
                        return True
                    self.log(f"[DEBUG] Confirmation attempt {attempt + 1} failed, retrying...")
                    await asyncio.sleep(1)
                except Exception as e:
                    self.log(f"[DEBUG] Confirmation error on attempt {attempt + 1}: {e}")
                    if attempt < 2:  # Don't sleep on last attempt
                        await asyncio.sleep(1)
            
            self.log("❌ Transaction failed to confirm after 3 attempts")
            return False
            
        except Exception as exc:
            self.log(f"❌ Error sending/confirming transaction: {exc}\n{traceback.format_exc()}")
            return False

    def log(self, message: str) -> None:
        """Log a message. To be implemented by subclasses."""
        pass

    async def fetch_dexscreener_pool(self, address: str) -> Optional[Dict[str, Any]]:
        """Fetch pool info from DexScreener. To be implemented by subclasses."""
        pass

    def simulate_buy(self, token, now, from_watchlist=False, force=False):
        if not force:
            mint = token.get('mint') or token.get('address') or token.get('tokenAddress')
            if mint:
                self.seen_tokens.add(mint)
            return False
        mint = token.get('mint') or token.get('address') or token.get('tokenAddress')
        if not mint:
            self.log("[ERROR] Buy: token address (mint) is None, cannot proceed.")
            return False
        pool_data = self.fetch_dexscreener_pool(mint)
        if not pool_data:
            self.log(f"[ERROR] Buy: Could not fetch pool data for {mint}. Cannot perform direct swap.")
            return False
        name = token.get('name', '') or token.get('description', '')
        symbol = token.get('symbol', '')
        self.log(f"[DEBUG BUY FILTER] Checking filters for {name} ({symbol}) - Mint: {mint}")
        buy_price = self.safe_float(token.get('price_usd'))
        if buy_price == 0:
            self.log(f"❌ [FILTER FAILED] No price data (price_usd=0) for {name} ({symbol})")
            return False
        if buy_price > self.MAX_PRICE_USD:
            self.log(f"❌ [FILTER FAILED] Price ${buy_price:.8f} > Max ${self.MAX_PRICE_USD:.8f} for {name} ({symbol})")
            return False
        else:
            self.log(f"[FILTER PASS] Price ${buy_price:.8f} ≤ Max ${self.MAX_PRICE_USD:.8f}")
        liquidity = self.safe_float(token.get('liquidity_usd'))
        if liquidity < self.MIN_LIQUIDITY_USD:
            self.log(f"❌ [FILTER FAILED] Low liquidity (${liquidity:.2f} < ${self.MIN_LIQUIDITY_USD:.2f}) for {name} ({symbol})")
            return False
        else:
            self.log(f"[FILTER PASS] Liquidity ${liquidity:,.2f} ≥ Min ${self.MIN_LIQUIDITY_USD:,.2f}")
        volume_5m = self.safe_float(token.get('volume_m5'))
        if volume_5m < self.MIN_VOLUME_5M_USD:
            self.log(f"❌ [FILTER FAILED] Low 5m volume (${volume_5m:.2f} < ${self.MIN_VOLUME_5M_USD:.2f}) for {name} ({symbol})")
            return False
        else:
            self.log(f"[FILTER PASS] 5m Volume ${volume_5m:,.2f} ≥ Min ${self.MIN_VOLUME_5M_USD:,.2f}")
        buys_5m = self.safe_float(token.get('txns_m5_buys'))
        sells_5m = self.safe_float(token.get('txns_m5_sells'))
        buy_sell_ratio = buys_5m / sells_5m if sells_5m > 0 else float('inf')
        if buys_5m < self.MIN_BUYS_5M:
            self.log(f"❌ [FILTER FAILED] Not enough 5m buys ({buys_5m} < {self.MIN_BUYS_5M}) for {name} ({symbol})")
            return False
        else:
            self.log(f"[FILTER PASS] 5m Buys {buys_5m} ≥ Min {self.MIN_BUYS_5M}")
        if sells_5m > 0 and buy_sell_ratio < self.MIN_BUY_TX_RATIO:
            self.log(f"❌ [FILTER FAILED] Low buy/sell ratio ({buy_sell_ratio:.2f} < {self.MIN_BUY_TX_RATIO:.2f}) for {name} ({symbol}) (Buys: {buys_5m}, Sells: {sells_5m})")
            return False
        else:
            self.log(f"[FILTER PASS] Buy/Sell Ratio {buy_sell_ratio:.2f} ≥ Min {self.MIN_BUY_TX_RATIO:.2f}")
        pair_created_at = self.safe_float(token.get('pairCreatedAt', 0)) / 1000
        pair_age = now - pair_created_at
        if pair_age < self.MIN_PAIR_AGE_SECONDS:
            self.log(f"❌ [FILTER FAILED] Too new ({int(pair_age)}s < {self.MIN_PAIR_AGE_SECONDS}s) for {name} ({symbol})")
            return False
        else:
            self.log(f"[FILTER PASS] Pair Age {int(pair_age)}s ≥ Min {self.MIN_PAIR_AGE_SECONDS}s")
        if pair_age > self.MAX_PAIR_AGE_SECONDS:
            self.log(f"❌ [FILTER FAILED] Too old ({int(pair_age)}s > {self.MAX_PAIR_AGE_SECONDS}s) for {name} ({symbol})")
            return False
        total_supply = self.safe_float(token.get('totalSupply'))
        market_cap = total_supply * buy_price if total_supply else 0
        self.log(f"[DEBUG BUY FILTER] Market Cap: ${market_cap:,.2f}")

        # After existing filters, before buying:
        settings = getattr(self, 'settings', {}) if hasattr(self, 'settings') else {}
        require_socials = settings.get('require_socials', False)
        min_percent_burned = settings.get('min_percent_burned', 0)
        require_immutable = settings.get('require_immutable', False)
        max_percent_top_holders = settings.get('max_percent_top_holders', 100)
        block_risky_wallets = settings.get('block_risky_wallets', False)

        # 1. Socials
        if require_socials:
            if not has_required_socials(token):
                self.log(f"❌ [FILTER FAILED] No socials found for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] Socials found for {name} ({symbol})")
        # 2. Burned
        if min_percent_burned > 0:
            percent_burned = get_burn_percent(mint, total_supply)
            if percent_burned < min_percent_burned:
                self.log(f"❌ [FILTER FAILED] Only {percent_burned:.2f}% burned < Min {min_percent_burned}% for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] {percent_burned:.2f}% burned ≥ Min {min_percent_burned}% for {name} ({symbol})")
        # 3. Immutable
        if require_immutable:
            if not is_immutable_metadata(mint):
                self.log(f"❌ [FILTER FAILED] Metadata is mutable for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] Metadata is immutable for {name} ({symbol})")
        # 4. Top holders
        if max_percent_top_holders < 100:
            percent_top = get_top_holders_percent(mint, total_supply, top_n=5)
            if percent_top > max_percent_top_holders:
                self.log(f"❌ [FILTER FAILED] Top 5 holders own {percent_top:.2f}% > Max {max_percent_top_holders}% for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] Top 5 holders own {percent_top:.2f}% ≤ Max {max_percent_top_holders}% for {name} ({symbol})")
        # 5. Risky wallets
        if block_risky_wallets:
            if has_risky_wallet(mint):
                self.log(f"❌ [FILTER FAILED] Risky wallet detected in top holders for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] No risky wallets in top holders for {name} ({symbol})")

        self.log("\n✨ ALL CHECKS PASSED - BUYING ✨")
        self.log(f"Token: {name} ({symbol})")
        self.log(f"Address: {mint}")
        self.log(f"Price: ${buy_price:.8f}")
        self.log(f"Market Cap: ${market_cap:,.2f}")
        self.log(f"Liquidity: ${liquidity:,.2f}")
        self.log(f"5m Volume: ${volume_5m:,.2f}")
        self.log(f"Buy/Sell Ratio: {buy_sell_ratio:.2f} ({buys_5m}/{sells_5m})")
        self.log(f"Take Profit Target: ${buy_price * (1 + self.TAKE_PROFIT_PCT / 100):.6f} (+{self.TAKE_PROFIT_PCT}%)")
        self.log(f"Stop Loss Target: ${buy_price * (1 - self.STOP_LOSS_PCT / 100):.6f} (-{self.STOP_LOSS_PCT}%)")
        buy_amount_usd = self.POSITION_SIZE_USD
        fee = buy_amount_usd * self.BUY_FEE
        net_amt = buy_amount_usd - fee
        sol_amount = buy_amount_usd / self.sol_usd
        with self.buy_lock:
            available_balance_usd = self.sol_balance * self.sol_usd
            if available_balance_usd < self.POSITION_SIZE_USD:
                self.log(f"❌ Not enough balance (${available_balance_usd:.2f} available, need ${self.POSITION_SIZE_USD:.2f})")
                return False
            if not self.SIMULATION_MODE:
                wallet_balance = self.get_wallet_balance()
                if wallet_balance <= 0:
                    self.log("[ERROR] Manual buy: Wallet balance 0 SOL.")
                    return False
                if sol_amount > wallet_balance:
                    self.log(f"[ERROR] Manual buy: Insufficient SOL balance (have {wallet_balance:.4f}, need {sol_amount:.4f}).")
                    return False
            if asyncio.run(self.execute_buy_token(mint, sol_amount, pool_data)):
                self.log(f"[INFO] Manual buy executed: {sol_amount:.4f} SOL into {symbol}")
                # Update balances only in simulation or after on-chain success
                if self.SIMULATION_MODE:
                    self.sol_balance -= sol_amount
                self.tokens[mint] = {
                    'address': mint,
                    'name': name,
                    'symbol': symbol,
                    'bought_at': now,
                    'amount_usd': net_amt,
                    'amount_left_usd': net_amt,
                    'buy_price_usd': buy_price,
                    'sold': False,
                    'sell_price_usd': None,
                    'sell_time': None,
                    'pnl': None
                }
                if pool_data:
                    price = self.safe_float(pool_data.get('priceUsd'))
                    self.tokens[mint]['price_usd'] = price
                    self.tokens[mint]['priceUsd'] = price
                else:
                    self.tokens[mint]['price_usd'] = buy_price
                    self.tokens[mint]['priceUsd'] = buy_price
                self.seen_tokens.add(mint)
                if hasattr(self, 'watched_tokens'):
                    self.watched_tokens.pop(mint, None)
                self.update_open_positions_file()
                return True
        return False

    def try_sell(self, token, now, force=False):
        if token['sold']:
            self.log(f"[ERROR] Try sell: Token already sold: {token.get('name', 'N/A')} ({token.get('symbol', 'N/A')})")
            return False
        mint = token['address']
        name = token['name']
        symbol = token['symbol']
        cur_price = self.safe_float(token.get('price_usd'))
        buy_price = self.safe_float(token.get('buy_price_usd'))
        if cur_price == 0 or buy_price == 0:
            self.log(f"[ERROR] Try sell: No price data for token: {name} ({symbol})")
            return False
        tp = buy_price * (1 + self.TAKE_PROFIT_PCT / 100)
        sl = buy_price * (1 - self.STOP_LOSS_PCT / 100)
        self.log(f"[DEBUG] try_sell: buy_price={buy_price}, cur_price={cur_price}, TP={tp}, SL={sl}, TAKE_PROFIT_PCT={self.TAKE_PROFIT_PCT}, STOP_LOSS_PCT= {self.STOP_LOSS_PCT}, force={force}")
        if not force:
            if cur_price >= tp:
                reason = "TAKE_PROFIT"
            elif cur_price <= sl:
                reason = "STOP_LOSS"
            else:
                return False
        else:
            reason = "MANUAL"
        sell_amt_usd = self.safe_float(token.get('amount_left_usd'))
        token_decimals = self._get_token_decimals_from_chain(mint)
        if token_decimals is None:
            if getattr(self, 'SIMULATION_MODE', False):
                token_decimals = 9  # Default for SPL tokens in simulation
                self.log(f"[SIMULATION] Defaulting decimals to 9 for token {mint}.")
            else:
                self.log(f"❌ Sell failed: Could not determine decimals for token {mint}.")
                return False
        actual_tokens_to_sell = sell_amt_usd / cur_price if cur_price > 0 else 0
        if actual_tokens_to_sell <= 0:
            self.log(f"❌ Sell failed: No tokens to sell for {name} ({symbol}).")
            return False
        pool_data = self.fetch_dexscreener_pool(mint)
        if not pool_data:
            self.log(f"[ERROR] Sell: Could not fetch pool data for {mint}. Cannot perform direct swap.")
            return False
        if asyncio.run(self.execute_sell_token(mint, actual_tokens_to_sell, pool_data)):
            gross_usd = actual_tokens_to_sell * cur_price
            fee = gross_usd * self.SELL_FEE
            net_usd = gross_usd - fee
            # Use correct PnL formula: (sell_price - buy_price) / buy_price * original_investment
            amount_invested = self.safe_float(token.get('amount_invested_usd')) or sell_amt_usd
            pnl_usd = (cur_price - buy_price) / buy_price * amount_invested if buy_price else 0
            sol_received = net_usd / self.sol_usd
            self.sol_balance += sol_received
            token['amount_left_usd'] = 0
            token['sold'] = True
            token['sell_price_usd'] = cur_price
            token['sell_time'] = now
            token['pnl'] = pnl_usd
            self.trades.append({
                'address': mint,
                'buy_price_usd': buy_price,
                'sell_price_usd': cur_price,
                'amount_usd': amount_invested,  # Use original investment amount
                'buy_time': token['bought_at'],
                'sell_time': now,
                'pnl': pnl_usd,
                'name': name,
                'symbol': symbol,
                'reason': reason,
                'fraction': 1.0
            })
            self.log(f"\n💰 SOLD {name} ({symbol})")
            self.log(f"Address: {mint}")
            self.log(f"Price: ${cur_price:.8f}")
            self.log(f"PnL: ${pnl_usd:.2f} ({(cur_price - buy_price) / buy_price * 100:+.1f}%)")
            self.log(f"Reason: {reason}")
            self.update_open_positions_file()
            return True
        return False

    def safe_float(self, val):
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    def get_wallet_balance(self):
        # Stub for linter, should be implemented in subclass or main bot
        return 0.0

    async def execute_buy_token(self, token_mint_address: str, amount_to_spend_sol: float, pool_info: dict) -> bool:
        # Stub for linter, should be implemented in subclass or main bot
        return False

    def update_open_positions_file(self):
        """Save all open (unsold) positions to open_positions.json."""
        open_positions = [t for t in self.tokens.values() if not t.get('sold', False)]
        try:
            with open(self.open_positions_file, 'w', encoding='utf-8') as f:
                json.dump(open_positions, f, indent=2)
        except Exception as e:
            self.log(f"[ERROR] Failed to update open positions file: {e}")

# --- BUY/SELL LOGIC FROM sniper_sim.py ---

def execute_buy(self, token_address, amount_sol):
    # Use VersionedTransaction instead of legacy Transaction
    if self.SIMULATION_MODE:
        return True
    current_balance = self.get_wallet_balance()
    if current_balance < amount_sol:
        print(f"DEBUG: Insufficient balance to buy (have {current_balance:.4f} SOL, need {amount_sol:.4f} SOL)")
        return False
    try:
        transfer_params = TransferParams(
            from_pubkey=self.keypair.public_key,
            to_pubkey=Pubkey(token_address),
            lamports=int(amount_sol * 1e9)
        )
        instruction = transfer(transfer_params)
        recent_blockhash = self.client.get_latest_blockhash(commitment=COMMITMENT_CONFIRMED).value.blockhash
        message = MessageV0.try_compile(
            payer=self.keypair.public_key,
            instructions=[instruction],
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash,
        )
        # Create VersionedTransaction
        transaction = VersionedTransaction(message, [])
        
        # Handle both wallet types
        if hasattr(self.client, 'sign_transaction'):
            # Trojan wallet
            transaction = self.client.sign_transaction(transaction)
            tx_bytes = transaction.serialize()
        else:
            # Conventional wallet
            transaction.sign([self.keypair])
            tx_bytes = bytes(transaction)
        
        # Send without opts parameter
        result = self.client.send_raw_transaction(tx_bytes)
        
        if hasattr(result, 'value') and result.value:
            print(f"✅ Buy transaction sent: {result.value}")
            return True
        elif isinstance(result, dict) and "result" in result:
            print(f"✅ Buy transaction sent: {result['result']}")
            return True
        else:
            print(f"❌ Buy failed: {result}")
            return False
    except Exception as e:
        print(f"❌ Buy error: {e}")
        return False

def execute_sell(self, token_address, amount_tokens):
    # Use VersionedTransaction instead of legacy Transaction
    if self.SIMULATION_MODE:
        return True
    try:
        transfer_params = TransferParams(
            from_pubkey=self.keypair.public_key,
            to_pubkey=Pubkey(token_address),
            lamports=int(amount_tokens)
        )
        instruction = transfer(transfer_params)
        recent_blockhash = self.client.get_latest_blockhash(commitment=COMMITMENT_CONFIRMED).value.blockhash
        message = MessageV0.try_compile(
            payer=self.keypair.public_key,
            instructions=[instruction],
            address_lookup_table_accounts=[],
            recent_blockhash=recent_blockhash,
        )
        # Create VersionedTransaction
        transaction = VersionedTransaction(message, [])
        
        # Handle both wallet types
        if hasattr(self.client, 'sign_transaction'):
            # Trojan wallet
            transaction = self.client.sign_transaction(transaction)
            tx_bytes = transaction.serialize()
        else:
            # Conventional wallet
            transaction.sign([self.keypair])
            tx_bytes = bytes(transaction)
        
        # Send without opts parameter
        result = self.client.send_raw_transaction(tx_bytes)
        
        if hasattr(result, 'value') and result.value:
            print(f"✅ Sell transaction sent: {result.value}")
            return True
        elif isinstance(result, dict) and "result" in result:
            print(f"✅ Sell transaction sent: {result['result']}")
            return True
        else:
            print(f"❌ Sell failed: {result}")
            return False
    except Exception as e:
        print(f"❌ Sell error: {e}")
        return False

def simulate_buy_sim(self, token, now, from_watchlist=False):
    mint = token.get('mint') or token.get('address') or token.get('tokenAddress')
    name = token.get('name', '') or token.get('description', '')
    symbol = token.get('symbol', '')
    buy_price = self.safe_float(token.get('price_usd'))
    if buy_price == 0:
        print(f"❌ No price data")
        return
    if buy_price > self.MAX_PRICE_USD:
        print(f"❌ Price too high (${buy_price:.6f})")
        return
    liquidity = self.safe_float(token.get('liquidity_usd'))
    if liquidity < self.MIN_LIQUIDITY_USD:
        print(f"❌ Low liquidity (${liquidity:.2f})")
        return
    volume_5m = self.safe_float(token.get('volume_m5'))
    if volume_5m < self.MIN_VOLUME_5M_USD:
        print(f"❌ Low volume (${volume_5m:.2f})")
        return
    buys_5m = self.safe_float(token.get('txns_m5_buys'))
    sells_5m = self.safe_float(token.get('txns_m5_sells'))
    buy_sell_ratio = buys_5m / sells_5m if sells_5m > 0 else float('inf')
    if buys_5m < self.MIN_BUYS_5M:
        print(f"❌ Not enough buys ({buys_5m})")
        return
    if sells_5m > 0 and buy_sell_ratio < self.MIN_BUY_TX_RATIO:
        print(f"❌ Low buy/sell ratio ({buy_sell_ratio:.2f})")
        return
    pair_created_at = self.safe_float(token.get('pairCreatedAt', 0)) / 1000
    pair_age = now - pair_created_at
    if pair_age < self.MIN_PAIR_AGE_SECONDS:
        print(f"❌ Too new ({int(pair_age)}s)")
        return
    if pair_age > self.MAX_PAIR_AGE_SECONDS:
        print(f"❌ Too old ({int(pair_age)}s)")
        return
    total_supply = self.safe_float(token.get('totalSupply'))
    market_cap = total_supply * buy_price if total_supply else 0
    print("\n✨ ALL CHECKS PASSED - BUYING ✨")
    print(f"Token: {name} ({symbol})")
    print(f"Address: {mint}")
    print(f"Price: ${buy_price:.8f}")
    print(f"Market Cap: ${market_cap:,.2f}")
    print(f"Liquidity: ${liquidity:,.2f}")
    print(f"5m Volume: ${volume_5m:,.2f}")
    print(f"Buy/Sell Ratio: {buy_sell_ratio:.2f} ({buys_5m}/{sells_5m})")
    available_balance_usd = self.sol_balance * self.sol_usd
    if available_balance_usd < self.POSITION_SIZE_USD:
        print(f"❌ Not enough balance (${available_balance_usd:.2f} available, need ${self.POSITION_SIZE_USD:.2f})")
        return
    buy_amount_usd = self.POSITION_SIZE_USD
    fee = buy_amount_usd * self.BUY_FEE
    net_amt = buy_amount_usd - fee
    sol_amount = buy_amount_usd / self.sol_usd
    if self.execute_buy(mint, sol_amount):
        self.sol_balance -= sol_amount
        self.tokens[mint] = {
            'address': mint,
            'name': name,
            'symbol': symbol,
            'bought_at': now,
            'amount_usd': net_amt,
            'amount_left_usd': net_amt,
            'buy_price_usd': buy_price,
            'sold': False,
            'sell_price_usd': None,
            'sell_time': None,
            'pnl': None
        }
        print(f"Amount: ${net_amt:.2f}")
        print(f"Balance: ${self.sol_balance * self.sol_usd:.2f}")
        self.seen_tokens.add(mint)
        if hasattr(self, 'watched_tokens'):
            self.watched_tokens.pop(mint, None)
        self.update_open_positions_file()

def try_sell_sim(self, token, now):
    if token['sold']:
        return False
    mint = token['address']
    name = token['name']
    symbol = token['symbol']
    cur_price = self.safe_float(token.get('price_usd'))
    buy_price = self.safe_float(token.get('buy_price_usd'))
    if cur_price == 0 or buy_price == 0:
        return False
    tp = buy_price * (1 + self.TAKE_PROFIT_PCT / 100)
    sl = buy_price * (1 - self.STOP_LOSS_PCT / 100)
    print(f"[DEBUG] try_sell: buy_price={buy_price}, cur_price={cur_price}, TP={tp}, SL={sl}, TAKE_PROFIT_PCT={self.TAKE_PROFIT_PCT}")
    if cur_price >= tp:
        reason = "TAKE_PROFIT"
    elif cur_price <= sl:
        reason = "STOP_LOSS"
    else:
        return False
    sell_amt_usd = self.safe_float(token.get('amount_left_usd'))
    tokens_bought = sell_amt_usd / buy_price
    gross_usd = tokens_bought * cur_price
    fee = gross_usd * self.SELL_FEE
    net_usd = gross_usd - fee
    pnl_usd = net_usd - sell_amt_usd
    sol_received = net_usd / self.sol_usd
    self.sol_balance += sol_received
    token['amount_left_usd'] = 0
    token['sold'] = True
    token['sell_price_usd'] = cur_price
    token['sell_time'] = now
    token['pnl'] = pnl_usd
    self.trades.append({
        'address': mint,
        'buy_price_usd': buy_price,
        'sell_price_usd': cur_price,
        'amount_usd': sell_amt_usd,
        'buy_time': token['bought_at'],
        'sell_time': now,
        'pnl': pnl_usd,
        'name': name,
        'symbol': symbol,
        'reason': reason,
        'fraction': 1.0
    })
    print(f"\n💰 SOLD {name} ({symbol})")
    print(f"Address: {mint}")
    print(f"Price: ${cur_price:.8f}")

def has_required_socials(token):
    socials = token.get('socials', {})
    # Dexscreener may provide socials as a dict or as fields like twitter, telegram, etc.
    social_fields = ['twitter', 'telegram', 'discord', 'website', 'medium', 'facebook', 'instagram', 'youtube']
    for field in social_fields:
        if token.get(field) or (isinstance(socials, dict) and socials.get(field)):
            return True
    return False

def get_holders_info(mint):
    # Solscan API: https://public-api.solscan.io/token/holders?tokenAddress=...&offset=0&limit=100
    try:
        url = f"https://public-api.solscan.io/token/holders?tokenAddress={mint}&offset=0&limit=100"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            # Each holder is a dict with 'owner' and 'amount' fields
            return resp.json()
    except Exception as e:
        print(f"[ERROR] Could not fetch holders info: {e}")
    return []

def get_burn_percent(mint, total_supply):
    holders = get_holders_info(mint)
    burn_addresses = [
        '11111111111111111111111111111111',
        'So11111111111111111111111111111111111111112',
        'Burn111111111111111111111111111111111111111',
        '0x000000000000000000000000000000000000dEaD',
    ]
    burned = 0
    for h in holders:
        if h.get('owner') in burn_addresses:
            burned += float(h.get('amount', 0))
    if total_supply:
        return (burned / total_supply) * 100
    return 0

def get_top_holders_percent(mint, total_supply, top_n=5):
    holders = get_holders_info(mint)
    top = holders[:top_n]
    total = 0
    for h in top:
        total += float(h.get('amount', 0))
    if total_supply:
        return (total / total_supply) * 100
    return 0

def is_immutable_metadata(mint):
    # Metaplex metadata: https://api-mainnet.magiceden.dev/v2/tokens/{mint}
    try:
        url = f"https://api-mainnet.magiceden.dev/v2/tokens/{mint}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return not data.get('isMutable', True)
    except Exception as e:
        print(f"[ERROR] Could not fetch metadata: {e}")
    return False

RISKY_WALLETS = set([
    # Add known scammer/rug addresses here
    '11111111111111111111111111111111',
])

def has_risky_wallet(mint):
    holders = get_holders_info(mint)
    for h in holders:
        if h.get('owner') in RISKY_WALLETS:
            return True
    return False 

async def execute_token_transfer(self, from_token_account: Pubkey, to_token_account: Pubkey, 
                               mint_public_id: Pubkey, from_wallet_address: Pubkey, 
                               amount: int, decimals: int = 9):
    """Execute a token transfer transaction using the solders SDK"""
    try:
        from spl.token.constants import TOKEN_PROGRAM_ID
        from spl.token.instructions import transfer_checked, TransferCheckedParams
        
        self.log(f"[DEBUG] Preparing token transfer:")
        self.log(f"[DEBUG] - From token account: {from_token_account}")
        self.log(f"[DEBUG] - To token account: {to_token_account}")
        self.log(f"[DEBUG] - Token mint: {mint_public_id}")
        self.log(f"[DEBUG] - Amount: {amount} (decimals: {decimals})")
        
        transfer_ix = transfer_checked(
            TransferCheckedParams(
                program_id=TOKEN_PROGRAM_ID,
                source=from_token_account,
                mint=mint_public_id,
                destination=to_token_account,
                owner=from_wallet_address,
                amount=amount,
                decimals=decimals,
                signers=[]
            )
        )
        
        result = await self._send_transaction_for_wallet_type(None, transfer_ix)
        if result:
            self.log("✅ Token transfer transaction confirmed")
            return True
        else:
            self.log("❌ Token transfer failed: Transaction not confirmed")
            return False
            
    except Exception as exc:
        self.log(f"❌ Error executing token transfer: {exc}\n{traceback.format_exc()}")
        return False

def _is_trojan_wallet(self) -> bool:
    """Check if we're using a Trojan-style private key wallet"""
    return hasattr(self.client, 'sign_transaction') and not isinstance(self.keypair, Keypair)

async def _send_transaction_for_wallet_type(self, transaction, instruction=None) -> bool:
    """Send transaction handling both wallet types"""
    try:
        if self._is_trojan_wallet():
            # Trojan wallet flow
            self.log("[DEBUG] Using Trojan wallet signing")
            if transaction is None and instruction is not None:
                # Create a new transaction with the instruction
                recent_blockhash = self.client.get_latest_blockhash(commitment="COMMITMENT_CONFIRMED").value.blockhash
                
                # Create a versioned transaction
                message = MessageV0.try_compile(
                    payer=self.keypair.pubkey(),
                    instructions=[instruction],
                    address_lookup_table_accounts=[],
                    recent_blockhash=recent_blockhash
                )
                transaction = VersionedTransaction(message, [])
            
            # Let the client handle signing for Trojan wallets
            signed_tx = self.client.sign_transaction(transaction)
            tx_bytes = signed_tx.serialize()
        else:
            # Conventional wallet flow
            self.log("[DEBUG] Using conventional wallet signing")
            if transaction is None and instruction is not None:
                # Create a new transaction with the instruction
                recent_blockhash = self.client.get_latest_blockhash(commitment="COMMITMENT_CONFIRMED").value.blockhash
                
                # Create a versioned transaction
                message = MessageV0.try_compile(
                    payer=self.keypair.pubkey(),
                    instructions=[instruction],
                    address_lookup_table_accounts=[],
                    recent_blockhash=recent_blockhash
                )
                transaction = VersionedTransaction(message, [])
            
            # Sign the transaction
            # Jupiter transactions are already signed for the user; do not re-sign
            # If you need to re-sign, implement custom logic here
            tx_bytes = bytes(transaction)

        # Common sending logic for both wallet types
        self.log("[DEBUG] Sending transaction...")
        
        # Send without opts parameter
        resp = self.client.send_raw_transaction(tx_bytes)
        
        if not resp.value:
            self.log(f"❌ Unexpected response from send_raw_transaction: {resp}")
            return False
            
        signature = resp.value
        self.log(f"[DEBUG] Transaction sent with signature: {signature}")
        
        # Wait for confirmation
        for attempt in range(3):  # Try up to 3 times
            try:
                conf = self.client.confirm_transaction(signature, commitment="COMMITMENT_CONFIRMED")
                if conf and conf.value:
                    self.log(f"[DEBUG] Transaction confirmed on attempt {attempt + 1}")
                    return True
                self.log(f"[DEBUG] Confirmation attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(1)
            except Exception as e:
                self.log(f"[DEBUG] Confirmation error on attempt {attempt + 1}: {e}")
                if attempt < 2:  # Don't sleep on last attempt
                    await asyncio.sleep(1)
        
        self.log("❌ Transaction failed to confirm after 3 attempts")
        return False
        
    except Exception as exc:
        self.log(f"❌ Error sending/confirming transaction: {exc}\n{traceback.format_exc()}")
        return False

async def create_ata_if_needed(self, mint: Pubkey, owner: Pubkey) -> Optional[Pubkey]:
    """Create ATA if it doesn't exist, with proper error handling"""
    try:
        from spl.token.instructions import get_associated_token_address
        ata = get_associated_token_address(owner, mint)
        
        # Check if ATA exists
        try:
            self.client.get_account_info(ata)
            self.log(f"[DEBUG] ATA exists for mint {mint}")
            return ata
        except Exception:
            self.log(f"[DEBUG] Creating new ATA for mint {mint}")
            
            # Create ATA instruction
            create_ata_ix = create_associated_token_account(
                payer=owner,
                owner=owner,
                mint=mint
            )
            
            # Send as a simple transaction
            result = await self._send_transaction_for_wallet_type(None, create_ata_ix)
            if result:
                self.log(f"[DEBUG] Successfully created ATA {ata}")
                return ata
            else:
                self.log(f"❌ Failed to create ATA for {mint}")
                return None
                
    except Exception as e:
        self.log(f"❌ Error in ATA creation: {e}")
        return None

async def _send_and_confirm_tx(self, transaction: VersionedTransaction) -> bool:
    """Send the given transaction and wait for confirmation."""
    return await self._send_transaction_for_wallet_type(transaction) 

def decode_base64_with_padding(data):
    if isinstance(data, bytes):
        try:
            data = data.decode()
        except Exception:
            # Already bytes, not a base64 string; return as is
            return data
    missing_padding = len(data) % 4
    if missing_padding:
        data += '=' * (4 - missing_padding)
    return base64.b64decode(data) 
