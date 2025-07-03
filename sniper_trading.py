import asyncio
from typing import Optional, Dict, Any
import traceback
import threading
import requests
import json
import base64

# Imports for Solana and trading logic
from solders.transaction import VersionedTransaction, Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.system_program import transfer, TransferParams
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import Instruction, AccountMeta
from solders.sysvar import RENT
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID, WRAPPED_SOL_MINT
from spl.token.instructions import get_associated_token_address, create_associated_token_account, close_account, CloseAccountParams, transfer as spl_transfer, TransferParams as SPLTransferParams
import base58
import time
import re
from solana.rpc.commitment import Commitment
from solders.message import Message, MessageV0

# FIRST_EDIT: add constant for confirmed commitment string
COMMITMENT_CONFIRMED = "confirmed"  # Solana RPC commitment level

# SECOND_EDIT: helper function to send and confirm VersionedTransaction using current solana-py API
async def _send_and_confirm_tx(self, transaction: VersionedTransaction) -> bool:
    """Send a (versioned) transaction and wait for confirmation.

    Returns True if the transaction was confirmed, False otherwise.
    """
    try:
        # Serialize transaction to bytes and submit
        raw_tx: bytes = bytes(transaction) if isinstance(transaction, VersionedTransaction) else transaction.serialize()
        resp = self.client.send_raw_transaction(
            raw_tx,
            opts=TxOpts(skip_preflight=False, preflight_commitment=COMMITMENT_CONFIRMED),
        )
        # `resp` can be a dict or an RPC Response object depending on solana-py version
        sig = getattr(resp, "value", None) or resp.get("result")
        if not sig:
            self.log(f"❌ RPC send_raw_transaction returned unexpected format: {resp}")
            return False
        self.log(f"Submitted transaction {sig}, awaiting confirmation…")
        conf = self.client.confirm_transaction(sig, commitment=COMMITMENT_CONFIRMED)
        # `conf.value` may be None if still confirming; loop until done or timeout
        max_wait_sec = 30
        waited = 0
        while waited < max_wait_sec:
            value = getattr(conf, "value", conf.get("result", {}))
            if value and value.get("err") is None:
                self.log(f"✅ Transaction {sig} confirmed in slot {value.get('slot')}")
                return True
            await asyncio.sleep(1)
            waited += 1
            conf = self.client.confirm_transaction(sig, commitment=COMMITMENT_CONFIRMED)
        self.log(f"❌ Transaction {sig} not confirmed within {max_wait_sec}s: {conf}")
        return False
    except Exception as exc:
        self.log(f"❌ Error sending/confirming tx: {exc}\n{traceback.format_exc()}")
        return False

# THIRD_EDIT: add constant and helper for sending transactions with current solana-py API
COMMITMENT_CONFIRMED = "confirmed"  # Standard commitment level string

async def _send_and_confirm_tx(self, transaction: VersionedTransaction) -> bool:
    """Send the given transaction and wait for confirmation.

    Returns True on success, False otherwise.
    """
    try:
        raw_tx = bytes(transaction) if isinstance(transaction, VersionedTransaction) else transaction.serialize()
        resp = self.client.send_raw_transaction(
            raw_tx,
            opts=TxOpts(skip_preflight=False, preflight_commitment=COMMITMENT_CONFIRMED),
        )
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
        self.log(f"SIMULATION: Attempting to buy token {token_mint_address[:8]}... for {amount_to_spend_sol:.4f} SOL (Jupiter/Direct Swap)")
        return True
    amount_sol_lamports = int(amount_to_spend_sol * 1e9)
    input_mint = str(WRAPPED_SOL_MINT)
    output_mint = token_mint_address
    for attempt in range(1, 4):
        self.log(f"Attempting Jupiter buy for {token_mint_address[:8]}... (Attempt {attempt}/3)")
        slippage_bps = getattr(self, 'DEFAULT_SLIPPAGE_BPS', 100)
        quote_response = self._get_jupiter_quote(input_mint, output_mint, amount_sol_lamports, slippage_bps)
        self.log(f"[BUY] Quote outAmount={quote_response.get('outAmount') if quote_response else 'N/A'}, priceImpactPct={quote_response.get('priceImpactPct') if quote_response else 'N/A'}")
        if quote_response:
            raw_transaction_bytes = self._get_jupiter_swap_transaction_raw(quote_response)
            self.log(f"[BUY] Jupiter tx bytes length: {len(raw_transaction_bytes) if raw_transaction_bytes else 0}")
            if raw_transaction_bytes:
                try:
                    self.log(f"Sending Jupiter swap transaction for {token_mint_address[:8]}...")
                    # 1. Deserialize the transaction
                    swap_transaction_bytes = base64.b64decode(raw_transaction_bytes)
                    transaction = VersionedTransaction.from_bytes(swap_transaction_bytes)
                    # 2. Log public key and keypair type
                    self.log(f"[DEBUG] Wallet public key: {self.keypair.pubkey()}")
                    self.log(f"[DEBUG] Keypair type: {type(self.keypair)}")
                    # 3. Log signatures before signing
                    sigs_before = [str(s) for s in getattr(transaction, 'signatures', [])]
                    self.log(f"[DEBUG] Signatures before signing: {sigs_before}")
                    # 4. Sign the transaction with the wallet keypair
                    transaction.sign([self.keypair])
                    # 5. Log signatures after signing
                    sigs_after = [str(s) for s in getattr(transaction, 'signatures', [])]
                    self.log(f"[DEBUG] Signatures after signing: {sigs_after}")
                    result = await _send_and_confirm_tx(self, transaction)
                    self.log(f"[BUY] Transaction result: {result}")
                    if result:
                        self.log("✅ Jupiter swap transaction confirmed.")
                        return True
                    else:
                        self.log(f"❌ Jupiter swap failed: Transaction not confirmed")
                        return False
                except Exception as e:
                    self.log(f"❌ Jupiter swap network error: {e}\n{traceback.format_exc()}")
            else:
                self.log(f"❌ Failed to get raw Jupiter swap transaction for {token_mint_address[:8]}...")
        else:
            self.log(f"❌ Failed to get Jupiter quote for {token_mint_address[:8]}...")
        if attempt < 3:
            self.log(f"Retrying Jupiter swap in 1 second...")
            await asyncio.sleep(1)
    self.log(f"⚠️ Jupiter buy failed after 3 attempts for {token_mint_address[:8]}.... Falling back to direct Raydium swap.")
    self.log(f"Attempting direct on-chain buy of {token_mint_address[:8]}... with {amount_to_spend_sol:.4f} SOL ({amount_sol_lamports} lamports)...")
    return await self.execute_direct_swap(
        token_mint_address=token_mint_address,
        amount_in_atomic=amount_sol_lamports,
        is_buy=True,
        pool_info=pool_info
    )

async def execute_sell_token(self, token_mint_address: str, amount_tokens_to_sell: float, pool_info: Dict[str, Any]) -> bool:
    self.log(f"[SELL] Called with token_mint_address={token_mint_address}, amount_tokens_to_sell={amount_tokens_to_sell}, pool_info_keys={list(pool_info.keys()) if pool_info else None}")
    if self.SIMULATION_MODE:
        self.log(f"SIMULATION: Attempting to sell {amount_tokens_to_sell:.4f} of token {token_mint_address[:8]}... (Jupiter/Direct Swap)")
        return True
    token_decimals = self._get_token_decimals_from_chain(token_mint_address)
    if token_decimals is None:
        self.log(f"❌ Sell failed: Could not determine decimals for token {token_mint_address}.")
        return False
    amount_tokens_atomic = int(amount_tokens_to_sell * (10**token_decimals))
    input_mint = token_mint_address
    output_mint = str(WRAPPED_SOL_MINT)
    for attempt in range(1, 4):
        self.log(f"Attempting Jupiter sell for {token_mint_address[:8]}... (Attempt {attempt}/3)")
        slippage_bps = getattr(self, 'DEFAULT_SLIPPAGE_BPS', 100)
        quote_response = self._get_jupiter_quote(input_mint, output_mint, amount_tokens_atomic, slippage_bps)
        self.log(f"[SELL] Quote outAmount={quote_response.get('outAmount') if quote_response else 'N/A'}, priceImpactPct={quote_response.get('priceImpactPct') if quote_response else 'N/A'}")
        if quote_response:
            raw_transaction_bytes = self._get_jupiter_swap_transaction_raw(quote_response)
            self.log(f"[SELL] Jupiter tx bytes length: {len(raw_transaction_bytes) if raw_transaction_bytes else 0}")
            if raw_transaction_bytes:
                try:
                    self.log(f"Sending Jupiter swap transaction for {token_mint_address[:8]}...")
                    # 1. Deserialize the transaction
                    swap_transaction_bytes = base64.b64decode(raw_transaction_bytes)
                    transaction = VersionedTransaction.from_bytes(swap_transaction_bytes)
                    # 2. Log public key and keypair type
                    self.log(f"[DEBUG] Wallet public key: {self.keypair.pubkey()}")
                    self.log(f"[DEBUG] Keypair type: {type(self.keypair)}")
                    # 3. Log signatures before signing
                    sigs_before = [str(s) for s in getattr(transaction, 'signatures', [])]
                    self.log(f"[DEBUG] Signatures before signing: {sigs_before}")
                    # 4. Sign the transaction with the wallet keypair
                    transaction.sign([self.keypair])
                    # 5. Log signatures after signing
                    sigs_after = [str(s) for s in getattr(transaction, 'signatures', [])]
                    self.log(f"[DEBUG] Signatures after signing: {sigs_after}")
                    result = await _send_and_confirm_tx(self, transaction)
                    self.log(f"[SELL] Transaction result: {result}")
                    if result:
                        self.log("✅ Jupiter swap transaction confirmed.")
                        return True
                    else:
                        self.log(f"❌ Jupiter swap failed: Transaction not confirmed")
                        return False
                except Exception as e:
                    self.log(f"❌ Jupiter swap network error: {e}\n{traceback.format_exc()}")
            else:
                self.log(f"❌ Failed to get raw Jupiter swap transaction for {token_mint_address[:8]}...")
        else:
            self.log(f"❌ Failed to get Jupiter quote for {token_mint_address[:8]}...")
        if attempt < 3:
            self.log(f"Retrying Jupiter swap in 1 second...")
            await asyncio.sleep(1)
    self.log(f"⚠️ Jupiter sell failed after 3 attempts for {token_mint_address[:8]}.... Falling back to direct Raydium swap.")
    self.log(f"Attempting direct on-chain sell of {amount_tokens_to_sell:.4f} of {token_mint_address[:8]}... ({amount_tokens_atomic} atomic units)...")
    return await self.execute_direct_swap(
        token_mint_address=token_mint_address,
        amount_in_atomic=amount_tokens_atomic,
        is_buy=False,
        pool_info=pool_info
    )

class SniperSession:
    def __init__(self, *args, **kwargs):
        self.buy_lock = threading.Lock()
        # ... existing code ...

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
        self.log(f"Take Profit Target: ${buy_price * self.TAKE_PROFIT_MULT:.6f} (+{self.TAKE_PROFIT_PCT:.2f}%)")
        self.log(f"Stop Loss Target: ${buy_price * self.STOP_LOSS_MULT:.6f} (-{self.STOP_LOSS_PCT:.2f}%)")
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
        tp = buy_price * self.TAKE_PROFIT_MULT
        sl = buy_price * self.STOP_LOSS_MULT
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
            self.log(f"\n💰 SOLD {name} ({symbol})")
            self.log(f"Address: {mint}")
            self.log(f"Price: ${cur_price:.8f}")
            self.log(f"PnL: ${pnl_usd:.2f} ({(cur_price - buy_price) / buy_price * 100:+.1f}%)")
            self.log(f"Reason: {reason}")
            return True
        return False

# --- BUY/SELL LOGIC FROM sniper_sim.py ---

def execute_buy(self, token_address, amount_sol):
    if self.SIMULATION_MODE:
        return True
    current_balance = self.get_wallet_balance()
    if current_balance < amount_sol:
        print(f"DEBUG: Insufficient balance to buy (have {current_balance:.4f} SOL, need {amount_sol:.4f} SOL)")
        return False
    try:
        transfer_params = TransferParams(
            from_pubkey=self.keypair.public_key,
            to_pubkey=PublicKey(token_address),
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
        transaction = VersionedTransaction(message, [self.keypair])
        result = self.client.send_transaction(
            transaction,
            self.keypair,
        )
        if "result" in result:
            print(f"✅ Buy transaction sent: {result['result']}")
            return True
        else:
            print(f"❌ Buy failed: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Buy error: {e}")
        return False

def execute_sell(self, token_address, amount_tokens):
    if self.SIMULATION_MODE:
        return True
    try:
        transfer_params = TransferParams(
            from_pubkey=self.keypair.public_key,
            to_pubkey=PublicKey(token_address),
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
        transaction = VersionedTransaction(message, [self.keypair])
        result = self.client.send_transaction(
            transaction,
            self.keypair,
        )
        if "result" in result:
            print(f"✅ Sell transaction sent: {result['result']}")
            return True
        else:
            print(f"❌ Sell failed: {result.get('error', 'Unknown error')}")
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
    tp = buy_price * self.TAKE_PROFIT_MULT
    sl = buy_price * self.STOP_LOSS_PCT
    print(f"[DEBUG] try_sell: buy_price={buy_price}, cur_price={cur_price}, TP={tp}, SL={sl}, TAKE_PROFIT_MULT={self.TAKE_PROFIT_MULT}")
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
    # Solscan API: https://public-api.solscan.io/token/holders?tokenAddress=...&offset=0&limit=20
    try:
        url = f"https://public-api.solscan.io/token/holders?tokenAddress={mint}&offset=0&limit=10"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
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