import time
from datetime import datetime, timedelta
import requests
import json
import re
import threading
from threading import Lock
import os
import base64
import struct
from typing import Optional, Dict, Any
import asyncio # For websockets
import websockets # For websockets
import sniper_trading
import ssl
import certifi
import traceback

# --- Wallet/Seed Phrase Imports ---
import base58
from mnemonic import Mnemonic
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# Solders/Solana-Py imports
from solders.transaction import VersionedTransaction, Transaction
from solders.message import MessageV0
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.api import Client
from solana.rpc.types import TxOpts
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.instruction import Instruction, AccountMeta
from solders.sysvar import RENT # Corrected import name for SYSVAR_RENT_PUBKEY
from solana.rpc.commitment import Commitment
import solana.rpc.commitment as sol_commitment

# --- SPL Token Program Imports ---
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID, WRAPPED_SOL_MINT # Corrected NATIVE_MINT to WRAPPED_SOL_MINT
from spl.token.instructions import get_associated_token_address, create_associated_token_account, close_account, CloseAccountParams, transfer, TransferParams

# --- DIRECTLY DEFINING TOKEN_PROGRAM_ID AND NATIVE_MINT (already present, good) ---
# TOKEN_PROGRAM_ID = PublicKey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5mW")
# NATIVE_MINT = PublicKey.from_string("So11111111111111111111111111111111111111112") # This is now WRAPPED_SOL_MINT

# Raydium AMM V2 Program ID - frequently involved in new pool creation logs
RAYDIUM_AMM_V2_PROGRAM_ID = PublicKey.from_string("675kPX9MHTjRWKDhwPNV32YqUHPZBYUtDxPVyWFugyX5")
# Raydium AMM V4 Program ID - more common for new pools and direct swaps
RAYDIUM_AMM_V4_PROGRAM_ID = PublicKey.from_string("675kPX9MHTjRWKDhwPNV32YqUHPZBYUtDxPVyWFugyX5") # Often the same as V2 for general purpose, but can differ

# (Copy all config constants from sniper_sim.py here)
SIMULATION_MODE = True
WALLET_TYPE = "private"
SEED_PHRASE = ""
PRIVATE_KEY = ""
RPC_LIST = [
    "https://mainnet.helius-rpc.com/?api-key=3be2d48e-7192-43bf-8323-b80943ab0f1a",
    "https://solana-mainnet.api.syndica.io/api-key/4AM18sWSra766qjy6ZsawZ8KK5uLkk7ik5yRun719egHCNwqXDzuMvNx3HvkPz33H8AujKzdyP55oGxvrSA9Ehp9MFokeNXK3vg",
    "https://rpc.ankr.com/solana"
]

STARTING_USD = 100.0
POSITION_SIZE_USD = 20.0
BUY_FEE = 0.005
SELL_FEE = 0.005
TAKE_PROFIT_PCT = 30
STOP_LOSS_PCT = 15
MIN_LIQUIDITY_USD = 100.0
MIN_VOLUME_5M_USD = 200.0
MAX_PRICE_USD = 10.0
MIN_BUY_TX_RATIO = 0.5
# Relaxed MIN_PAIR_AGE_SECONDS slightly for earlier entries
MIN_PAIR_AGE_SECONDS = 2 # Reduced from 60 seconds
MAX_PAIR_AGE_SECONDS = 1800 # Original value: 30 minutes in seconds
MIN_BUYS_5M = 20
SIMULATION_DURATION = 60 * 60 * 2
DEX_POLL_INTERVAL = 1 # This will now be primarily for "manual" refreshes or fallback
MAX_TOKENS_PER_POLL = 500
MAX_TOKEN_AGE_SECONDS = 1800
TERMINAL_WIDTH = 100
SUMMARY_INTERVAL = 300
MAX_LOG_SIZE = 10 * 1024 * 1024
MAX_SEEN_TOKENS = 10000
MAX_TRADES_HISTORY = 1000
MAX_LOG_LINES = 5000

# --- NEW JUPITER API CONFIG (kept for reference, but will be bypassed for direct swaps) ---
JUPITER_V6_API_BASE = "https://public.jupiterapi.com"
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
DEFAULT_SLIPPAGE_BPS = 100 # 100 basis points = 1% slippage. Adjust as needed.
DEFAULT_PRIORITIZATION_FEE_LAMPORTS_PER_CU = 0 # Or a fixed value like 1000000

class RateLimiter:
    def __init__(self, calls_per_second=2):
        self.calls_per_second = calls_per_second
        self.last_call = datetime.now()
        self.lock = Lock()

    def wait(self):
        with self.lock:
            now = datetime.now()
            time_since_last = (now - self.last_call).total_seconds()
            if time_since_last < 1/self.calls_per_second:
                time.sleep(1/self.calls_per_second - time_since_last)
            self.last_call = now # Update last_call to current time

class RotatingSolanaClient:
    def __init__(self, rpc_list, commitment="confirmed", logger=None):
        self.rpc_list = rpc_list
        self.commitment = commitment
        self.current = 0
        self.clients = [Client(url) for url in rpc_list]
        self.logger = logger
        if self.logger:
            self.logger(f"[RotatingSolanaClient] Initialized with endpoints: {rpc_list}")
        else:
            print(f"[RotatingSolanaClient] Initialized with endpoints: {rpc_list}")

    def _log(self, msg):
        if self.logger:
            self.logger(msg)
        else:
            print(msg)

    def _rotate(self):
        prev = self.current
        self.current = (self.current + 1) % len(self.clients)
        self._log(f"[RotatingSolanaClient] Rotating RPC endpoint from {self.rpc_list[prev]} to {self.rpc_list[self.current]}")

    def _with_failover(self, func, *args, **kwargs):
        last_exc = None
        for attempt in range(len(self.clients)):
            client = self.clients[self.current]
            url = self.rpc_list[self.current]
            try:
                self._log(f"[RotatingSolanaClient] Using endpoint: {url} (attempt {attempt+1})")
                result = func(client, *args, **kwargs)
                self._log(f"[RotatingSolanaClient] Success on endpoint: {url}")
                return result
            except Exception as e:
                self._log(f"[RotatingSolanaClient] Exception on endpoint {url}: {e}. Rotating...")
                last_exc = e
                self._rotate()
        self._log(f"[RotatingSolanaClient] All endpoints failed. Raising last exception.")
        if last_exc is not None:
            raise last_exc
        raise Exception("All RPC endpoints failed")

    def get_latest_blockhash(self, *args, **kwargs):
        self._log(f"[RotatingSolanaClient] Fetching latest blockhash...")
        return self._with_failover(lambda c: c.get_latest_blockhash(*args, **kwargs))

    def send_raw_transaction(self, *args, **kwargs):
        self._log(f"[RotatingSolanaClient] Sending raw transaction...")
        return self._with_failover(lambda c: c.send_raw_transaction(*args, **kwargs))

    def confirm_transaction(self, *args, **kwargs):
        self._log(f"[RotatingSolanaClient] Confirming transaction...")
        return self._with_failover(lambda c: c.confirm_transaction(*args, **kwargs))

    def get_account_info(self, *args, **kwargs):
        self._log(f"[RotatingSolanaClient] Fetching account info...")
        return self._with_failover(lambda c: c.get_account_info(*args, **kwargs))

    def get_balance(self, *args, **kwargs):
        self._log(f"[RotatingSolanaClient] Fetching balance...")
        return self._with_failover(lambda c: c.get_balance(*args, **kwargs))

    def get_client(self):
        return self.clients[self.current]

class SniperSession:
    COINGECKO_SOL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
    # Adjusted interval for more conservative CoinGecko polling
    PRICE_CHECK_INTERVAL = 15 # Increased from 30 seconds to 60 seconds
    SOCIAL_REGEX = re.compile(r'(twitter|t\.me|discord|instagram|facebook|youtube|medium|linktr|x\.com)', re.IGNORECASE)
    VOLUME_SPIKE_WINDOW = 12
    VOLUME_SPIKE_MULT = 1.15
    WATCHLIST_PRINT_INTERVAL = 180
    DEX_TOKEN_PROFILE_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
    DEX_TOKEN_PAIRS_URL = "https://api.dexscreener.com/token-pairs/v1/solana/"
    LOG_FILE = "logs"
    LOG_BACKUP = "logs.old"
    open_positions_file = "open_positions.json"

    def __init__(self, log_callback=None, status_callback=None, **kwargs):
        self.lock = Lock()
        self.log_lock = Lock()
        # Separate rate limiters for different APIs if needed
        self.dexscreener_rate_limiter = RateLimiter(calls_per_second=1)
        # Further reduced calls_per_second for CoinGecko to prevent 429 errors
        self.coingecko_rate_limiter = RateLimiter(calls_per_second=1)
        self.jupiter_rate_limiter = RateLimiter(calls_per_second=10) 

        self.log_lines = []
        self.tokens = {}
        self.seen_tokens = set()
        self.trades = []
        self.SIMULATION_MODE = kwargs.get("simulation", SIMULATION_MODE)
        self.RPC_URL = kwargs.get("rpc_url", RPC_LIST[0])
        self.STARTING_USD = STARTING_USD
        self.SIMULATION_DURATION = kwargs.get("duration", SIMULATION_DURATION)
        if self.SIMULATION_DURATION < 100000:
            self.SIMULATION_DURATION = self.SIMULATION_DURATION * 60
        self.BUY_FEE = BUY_FEE
        self.SELL_FEE = SELL_FEE
        self.POSITION_SIZE_USD = kwargs.get("position_size", POSITION_SIZE_USD)
        self.TAKE_PROFIT_PCT = kwargs.get("take_profit", 30)
        self.STOP_LOSS_PCT = kwargs.get("stop_loss", 15)
        self.TAKE_PROFIT_MULT = 1 + (self.TAKE_PROFIT_PCT / 100)
        self.STOP_LOSS_MULT = 1 - (self.STOP_LOSS_PCT / 100)
        
        # --- FILTERS FOR SNIPING NEW TOKENS ---
        self.MIN_LIQUIDITY_USD = kwargs.get("min_liquidity", MIN_LIQUIDITY_USD)
        self.MIN_VOLUME_5M_USD = kwargs.get("min_volume_5m_usd", MIN_VOLUME_5M_USD)
        self.MAX_PRICE_USD = kwargs.get("max_price", MAX_PRICE_USD)
        self.MIN_BUY_TX_RATIO = kwargs.get("min_buy_tx_ratio", MIN_BUY_TX_RATIO)
        self.MIN_BUYS_5M = kwargs.get("min_buys_5m", MIN_BUYS_5M)
        self.MIN_PAIR_AGE_SECONDS = kwargs.get("min_pair_age", MIN_PAIR_AGE_SECONDS) # Updated value
        self.MAX_PAIR_AGE_SECONDS = kwargs.get("max_pair_age", MAX_PAIR_AGE_SECONDS)

        # Save callbacks early so self.log() works even before the rest of __init__ finishes
        self.log_callback = log_callback
        self.status_callback = status_callback

        # By default, automatic initial filters (legacy) are OFF. They simply skip the
        # old heuristics but DO NOT overwrite the user-provided GUI thresholds.
        self.disable_initial_filters = not kwargs.get("enable_initial_filters", False)

        self.DEX_POLL_INTERVAL = DEX_POLL_INTERVAL
        self.MAX_TOKENS_PER_POLL = MAX_TOKENS_PER_POLL
        self.MAX_TOKEN_AGE_SECONDS = MAX_TOKEN_AGE_SECONDS
        self.TERMINAL_WIDTH = TERMINAL_WIDTH
        self.SUMMARY_INTERVAL = SUMMARY_INTERVAL

        self.client = None
        if not self.SIMULATION_MODE:
            wallet_type = kwargs.get("wallet_type", WALLET_TYPE)
            if wallet_type == "private" or wallet_type == "seed":
                self.client = RotatingSolanaClient(RPC_LIST, logger=self.log)
            else:
                self.client = Client(self.RPC_URL)
        self.stop_threads = False
        self.keypair = None
        self.wallet_address = "SIMULATION_WALLET"
        self.websocket_triggered_poll = False # Flag to indicate WS triggered a poll

        # Debug log for MIN_BUY_TX_RATIO at initialization
        self.log(f"[INIT DEBUG] MIN_BUY_TX_RATIO set to: {self.MIN_BUY_TX_RATIO}")

        if not self.SIMULATION_MODE:
            wallet_type = kwargs.get("wallet_type", WALLET_TYPE)
            if wallet_type == "private":
                private_key_str = kwargs.get("private_key", PRIVATE_KEY).strip()
                try:
                    if private_key_str.startswith('['):
                        private_key_bytes = bytes(json.loads(private_key_str))
                    else:
                        private_key_bytes = base58.b58decode(private_key_str)

                    self.keypair = Keypair.from_bytes(private_key_bytes)
                    self.wallet_address = str(self.keypair.pubkey()) if self.keypair is not None else 'N/A'
                    self.log(f"✅ Wallet initialized: {self.wallet_address[:8]}...{self.wallet_address[-8:]}")
                except Exception as e:
                    self.log(f"❌ Invalid private key format: {str(e)}")
                    self.wallet_address = None
            elif wallet_type == "seed":
                seed_phrase = kwargs.get("seed_phrase", SEED_PHRASE)
                try:
                    seed_generator = Bip39SeedGenerator(seed_phrase)
                    seed_bytes = seed_generator.Generate()
                    bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.SOLANA)
                    account = bip44_ctx.Purpose().Coin().Account(0)
                    address_key = account.Change(Bip44Changes.CHAIN_EXT).AddressIndex(0)
                    private_key = address_key.PrivateKey().Raw().ToBytes()  # 32 bytes
                    # Get the 32-byte public key (skip 0x00 prefix if present)
                    public_key = address_key.PublicKey().RawCompressed().ToBytes()
                    if len(public_key) == 33 and public_key[0] == 0x00:
                        public_key = public_key[1:]
                    elif len(public_key) == 33:
                        public_key = public_key[1:]
                    # If it's already 32 bytes, use as is
                    keypair_bytes = private_key + public_key  # 64 bytes
                    self.keypair = Keypair.from_bytes(keypair_bytes)
                    self.wallet_address = str(self.keypair.pubkey()) if self.keypair is not None else 'N/A'
                    self.log(f"Initialized wallet from seed phrase: {self.wallet_address}")
                except Exception as e:
                    self.log(f"❌ Error initializing keypair from seed: {e}")
                    self.wallet_address = None

        self.sol_balance = None
        self.sol_usd = None
        self.start_time = None
        self.last_price_check = 0
        self.session_started = False
        self.token_volumes = {}
        self.watched_tokens = {}
        self.last_watchlist_print = time.time()
        self.websocket_thread = None
        self.polling_thread = None
        self.last_summary_print = time.time()
        self.initial_balance_usd = None
        self.session_end_time = None
        
        # Asyncio event loop and task for WebSockets
        self.loop = asyncio.new_event_loop()
        self.websocket_task = None

        self.execute_buy_token = sniper_trading.execute_buy_token.__get__(self)
        self.execute_sell_token = sniper_trading.execute_sell_token.__get__(self)
        self.try_sell = sniper_trading.SniperSession.try_sell.__get__(self)

        self.buy_lock = threading.Lock()
        if not hasattr(self, 'sol_balance') or self.sol_balance is None:
            self.sol_balance = 0.0
        if not hasattr(self, 'sol_usd') or self.sol_usd is None:
            self.sol_usd = 1.0
            
        # Load any existing open positions
        self.load_open_positions()

    def simulate_buy(self, token, now, from_watchlist=False, force=False):
        mint = token.get('mint') or token.get('address') or token.get('tokenAddress')
        if not mint:
            msg = "[ERROR] Buy: token address (mint) is None, cannot proceed."
            self.log(msg)
            return False, msg
        pool_data = self.fetch_dexscreener_pool(mint)
        if not pool_data:
            msg = f"[ERROR] Buy: Could not fetch pool data for {mint}. Cannot perform direct swap."
            self.log(msg)
            return False, msg
        name = token.get('name', '') or token.get('description', '')
        symbol = token.get('symbol', '')
        if force:
            # Manual buy: skip all filters
            self.log(f"[MANUAL BUY] Skipping all filters for {name} ({symbol}) - Mint: {mint}")
            buy_price = self.safe_float(token.get('price_usd'))
            liquidity = self.safe_float(token.get('liquidity_usd'))
            volume_5m = self.safe_float(token.get('volume_m5'))
            buys_5m = self.safe_float(token.get('txns_m5_buys'))
            sells_5m = self.safe_float(token.get('txns_m5_sells'))
            buy_sell_ratio = buys_5m / sells_5m if sells_5m > 0 else float('inf')
            pair_created_at = self.safe_float(token.get('pairCreatedAt', 0)) / 1000
            pair_age = now - pair_created_at
            total_supply = token.get('totalSupply')
            try:
                total_supply = float(total_supply)
            except (TypeError, ValueError):
                total_supply = 0.0
            try:
                buy_price_val = float(buy_price)
            except (TypeError, ValueError):
                buy_price_val = 0.0
            market_cap = total_supply * buy_price_val
            self.log("\n✨ MANUAL BUY - ALL FILTERS SKIPPED ✨")
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
                    msg = f"❌ Not enough balance (${available_balance_usd:.2f} available, need ${self.POSITION_SIZE_USD:.2f})"
                    self.log(msg)
                    return False, msg
                if not self.SIMULATION_MODE:
                    wallet_balance = self.get_wallet_balance()
                    if wallet_balance <= 0:
                        msg = "[ERROR] Manual buy: Wallet balance 0 SOL."
                        self.log(msg)
                        return False, msg
                    if sol_amount > wallet_balance:
                        msg = f"[ERROR] Manual buy: Insufficient SOL balance (have {wallet_balance:.4f}, need {sol_amount:.4f})."
                        self.log(msg)
                        return False, msg
                buy_result = asyncio.run(self.execute_buy_token(mint, sol_amount, pool_data))
                if isinstance(buy_result, tuple):
                    ok, err = buy_result
                else:
                    ok, err = buy_result, None
                if ok:
                    self.log(f"[INFO] Manual buy executed: {sol_amount:.4f} SOL into {symbol}")
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
                    return True, None
                else:
                    return False, err or "Manual buy failed for unknown reason."
            return False, "Manual buy failed for unknown reason."
        # Automated buy: apply all filters
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
        total_supply = token.get('totalSupply')
        try:
            total_supply = float(total_supply)
        except (TypeError, ValueError):
            total_supply = 0.0
        try:
            buy_price_val = float(buy_price)
        except (TypeError, ValueError):
            buy_price_val = 0.0
        market_cap = total_supply * buy_price_val
        self.log(f"[DEBUG BUY FILTER] Market Cap: ${market_cap:,.2f}")
        settings = getattr(self, 'settings', {}) if hasattr(self, 'settings') else {}
        require_socials = settings.get('require_socials', False)
        min_percent_burned = settings.get('min_percent_burned', 0)
        require_immutable = settings.get('require_immutable', False)
        max_percent_top_holders = settings.get('max_percent_top_holders', 100)
        block_risky_wallets = settings.get('block_risky_wallets', False)
        if require_socials:
            if not has_required_socials(token):
                self.log(f"❌ [FILTER FAILED] No socials found for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] Socials found for {name} ({symbol})")
        if min_percent_burned > 0:
            percent_burned = get_burn_percent(mint, total_supply)
            if percent_burned < min_percent_burned:
                self.log(f"❌ [FILTER FAILED] Only {percent_burned:.2f}% burned < Min {min_percent_burned}% for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] {percent_burned:.2f}% burned ≥ Min {min_percent_burned}% for {name} ({symbol})")
        if require_immutable:
            if not is_immutable_metadata(mint):
                self.log(f"❌ [FILTER FAILED] Metadata is mutable for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] Metadata is immutable for {name} ({symbol})")
        if max_percent_top_holders < 100:
            percent_top = get_top_holders_percent(mint, total_supply, top_n=5)
            if percent_top > max_percent_top_holders:
                self.log(f"❌ [FILTER FAILED] Top 5 holders own {percent_top:.2f}% > Max {max_percent_top_holders}% for {name} ({symbol})")
                return False
            else:
                self.log(f"[FILTER PASS] Top 5 holders own {percent_top:.2f}% ≤ Max {max_percent_top_holders}% for {name} ({symbol})")
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
                    self.log("[ERROR] Buy: Wallet balance 0 SOL.")
                    return False
                if sol_amount > wallet_balance:
                    self.log(f"[ERROR] Buy: Insufficient SOL balance (have {wallet_balance:.4f}, need {sol_amount:.4f}).")
                    return False
            if asyncio.run(self.execute_buy_token(mint, sol_amount, pool_data)):
                self.log(f"[INFO] Buy executed: {sol_amount:.4f} SOL into {symbol}")
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

    def log(self, line):
        if self.log_callback:
            self.log_callback(line)
        # File logging disabled
        self.log_lines.append(line)
        self.cleanup_collections()

    def update_status(self, status):
        if self.status_callback:
            self.status_callback(status)

    def stop(self):
        self.stop_threads = True
        self.update_status("Stopped")

        # Cancel websocket task if it exists and loop is running
        if getattr(self, 'websocket_task', None) and self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.websocket_task.cancel)

        time.sleep(0.2)

        # Gracefully stop the event-loop only if it is still running
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
            try:
                fut = asyncio.run_coroutine_threadsafe(asyncio.sleep(0.05), self.loop)
                fut.result(timeout=1)
            except (asyncio.TimeoutError, RuntimeError):
                # Loop already stopped / cancelled – safe to ignore
                pass
            except asyncio.CancelledError:
                self.log("Background task was cancelled cleanly.")

    def run(self):
        self.update_status("Running")
        self.print_header("STARTING BOT")
        mode_str = "SIMULATION MODE" if self.SIMULATION_MODE else "REAL WALLET MODE"
        self.log(f"Running in {mode_str}")
        self.sol_usd = self.fetch_sol_usd()
        if self.sol_usd is None or self.sol_usd == 0:
            self.log("❌ Failed to fetch SOL price. Please check your internet connection or API limits.")
            self.update_status("Error")
            return
        if self.SIMULATION_MODE:
            self.sol_balance = 100.0 / self.sol_usd
            # Create a simulation keypair
            self.keypair = Keypair()
            self.wallet_address = str(self.keypair.pubkey()) if self.keypair is not None else 'N/A'
            self.log(f"[DEBUG] Created simulation keypair with address: {self.wallet_address}")
        else:
            self.sol_balance = self.get_wallet_balance()
        if self.sol_balance is None or self.sol_balance == 0:
            self.log("❌ Failed to fetch wallet balance. Please check your wallet settings.")
            self.update_status("Error")
            return
        self.initial_balance_usd = self.sol_balance * self.sol_usd
        self.log(f"\nWallet Address: {self.wallet_address}")
        self.log(f"Starting Balance: {self.sol_balance:.4f} SOL (${self.initial_balance_usd:.2f} USD)")
        self.log(f"SOL Price: ${self.sol_usd:.2f}")
        if self.initial_balance_usd < self.POSITION_SIZE_USD:
            self.log(f"❌ Insufficient balance for trading! Need minimum ${self.POSITION_SIZE_USD:.2f}, have ${self.initial_balance_usd:.2f}")
            self.update_status("Error")
            return
        self.log(f"Session Duration: {self.SIMULATION_DURATION/60:.1f} minutes")
        self.log("="*self.TERMINAL_WIDTH)
        self.start_time = time.time()
        self.session_end_time = self.start_time + self.SIMULATION_DURATION
        self.start_streams()

        last_status = 0
        last_price_check = 0
        current_sol_price_check_interval = self.PRICE_CHECK_INTERVAL 

        while time.time() < self.session_end_time and not self.stop_threads:
            now = time.time()
            if now - last_price_check >= current_sol_price_check_interval:
                self.log("[DEBUG] Performing price check for open positions...")
                new_sol_price = self.fetch_sol_usd()
                if new_sol_price is not None and new_sol_price > 0:
                    self.sol_usd = new_sol_price
                    self.log(f"[DEBUG] Updated SOL price to ${self.sol_usd:.2f}")
                else:
                    self.log("[DEBUG] Failed to update SOL price.")

                for token in list(self.tokens.values()):
                    if not token['sold']:
                        address = token.get('address')
                        if not address:
                            self.log("[ERROR] Skipping price update: token address is None for an open position.")
                            continue
                        pool_data = self.fetch_dexscreener_pool(address)
                        if pool_data:
                            token['price_usd'] = self.safe_float(pool_data.get('priceUsd'))
                            token['priceUsd'] = token['price_usd']
                            self.log(f"[DEBUG] Updated price for {token.get('symbol', 'N/A')}: ${token['price_usd']:.8f}")
                            self.try_sell(token, now)
                        else:
                            self.log(f"[WARNING] Could not fetch latest pool data for open position {token.get('symbol', 'N/A')}.")
                last_price_check = now
            if now - last_status >= self.SUMMARY_INTERVAL:
                self.print_status()
                last_status = now
            time.sleep(0.1)
        self.stop_threads = True
        self.print_final_stats()
        self.update_status("Stopped")

    def print_header(self, text):
        line = "\n" + "="*self.TERMINAL_WIDTH + "\n"
        line += f" {text} ".center(self.TERMINAL_WIDTH, "=") + "\n"
        line += "="*self.TERMINAL_WIDTH
        self.log(line)

    def cleanup_collections(self):
        with self.lock:
            if len(self.seen_tokens) > MAX_SEEN_TOKENS:
                self.seen_tokens = set(list(self.seen_tokens)[-MAX_SEEN_TOKENS:])
            if len(self.trades) > MAX_TRADES_HISTORY:
                self.trades = self.trades[-MAX_TRADES_HISTORY:]
            if len(self.log_lines) > MAX_LOG_LINES:
                self.log_lines = self.log_lines[-MAX_LOG_LINES:]

    def fetch_sol_usd(self):
        """Fetch SOL/USD price with proper error handling"""
        try:
            self.coingecko_rate_limiter.wait()
            resp = requests.get(self.COINGECKO_SOL, timeout=5)
            resp.raise_for_status()
            price = float(resp.json()["solana"]["usd"])
            if price <= 0:
                raise ValueError("Invalid SOL price")
            return price
        except (requests.RequestException, KeyError, ValueError) as e:
            self.log(f"Error fetching SOL price: {e}")
            return None

    def get_wallet_balance(self) -> float:
        if self.SIMULATION_MODE:
            if self.sol_usd is None or self.sol_usd <= 0:
                return 0
            return self.sol_balance if self.sol_balance is not None else self.STARTING_USD / self.sol_usd
        else:
            try:
                if self.wallet_address is None or self.client is None:
                    return 0
                pubkey = PublicKey.from_string(self.wallet_address)
                response = self.client.get_balance(pubkey)
                value = getattr(response, 'value', 0)
                return value / 1e9
            except Exception as e:
                self.log(f"[ERROR] Failed to get wallet balance: {e}")
                return 0

    def position_size(self):
        with self.lock:
            if self.sol_usd is None or self.sol_usd <= 0:
                return 0
            usd = min(self.POSITION_SIZE_USD, self.sol_balance * self.sol_usd)
            return usd / self.sol_usd

    def clear_log(self):
        with self.log_lock:
            if os.path.exists(self.LOG_FILE):
                os.remove(self.LOG_FILE)

    def safe_float(self, val):
        try:
            result = float(val)
            return result if not (result == float('inf') or result == float('-inf') or result != result) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def calculate_total_pnl(self):
        realized_pnl = 0
        unrealized_pnl = 0
        for trade in self.trades:
            realized_pnl += self.safe_float(trade.get('pnl', 0))
        for token in self.tokens.values():
            if not token['sold']:
                buy_price = self.safe_float(token.get('buy_price_usd'))
                cur_price = self.safe_float(token.get('price_usd'))
                amount_left_usd = self.safe_float(token.get('amount_left_usd'))
                if buy_price > 0 and cur_price > 0 and amount_left_usd > 0:
                    tokens_amount = amount_left_usd / buy_price
                    current_value = tokens_amount * cur_price
                    current_value *= (1 - self.SELL_FEE)
                    position_pnl = current_value - amount_left_usd
                    unrealized_pnl += position_pnl
        total_pnl = realized_pnl + unrealized_pnl
        return realized_pnl, unrealized_pnl, total_pnl

    def _get_token_decimals_from_chain(self, mint_address: str) -> Optional[int]:
        """
        Fetches the decimals of an SPL token by querying its mint account on chain.
        """
        try:
            if mint_address is None or self.client is None:
                return None
            if isinstance(mint_address, str):
                mint_pubkey = PublicKey.from_string(mint_address)
            else:
                return None
            account_info = self.client.get_account_info(mint_pubkey, commitment=Commitment.confirmed) if self.client is not None else None
            recent_blockhash = self.client.get_latest_blockhash(commitment=Commitment.confirmed).value.blockhash if self.client is not None else None

            if account_info is None or account_info.value is None:
                self.log(f"❌ Failed to get account info for mint: {mint_address}")
                return None

            account_data = account_info.value.data
            # SPL Token Mint state is 82 bytes, decimals at offset 44
            if not account_data or len(account_data) < 45: 
                self.log(f"❌ Invalid account data for mint (too short or empty): {mint_address}")
                return None

            # The decimals are at byte offset 44 in the Mint account data
            decimals = struct.unpack('<B', account_data[44:45])[0]
            return decimals
        except Exception as e:
            self.log(f"❌ Error fetching decimals for {mint_address}: {e}")
            return None

    def _get_jupiter_quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int) -> Optional[dict]:
        """
        Fetches a swap quote from Jupiter Aggregator.
        Amount must be in atomic units (lamports for SOL, token_amount * 10^decimals for SPL tokens).
        """
        try:
            self.jupiter_rate_limiter.wait()
            url = JUPITER_QUOTE_API
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(int(amount)),
                "slippageBps": str(slippage_bps),
                "onlyDirectRoutes": "false", # Allow indirect routes for better liquidity
                # Bypass Jupiter's new token restrictions by not filtering for age, and not using blocklists
                # Optionally, you could add 'enforceSingleTx': 'false' to try to force a route
            }
            response = requests.get(url, params=params, timeout=10)
            self.log(f"[JUPITER] Quote request URL: {response.url}")
            if response.status_code != 200:
                self.log(f"❌ Jupiter quote failed with status {response.status_code}. Response: {response.text}")
                return None
            data = response.json()
            self.log(f"[JUPITER] Quote response: {json.dumps(data)[:500]}")
            # Jupiter may restrict new tokens by not returning a routePlan or by returning an error
            if not data or 'routePlan' not in data:
                self.log(f"❌ Jupiter quote failed: {data.get('error', 'No route found in response')}. Full response: {json.dumps(data)}")
                # Bypass: If Jupiter blocks, still return the data for further attempts
                return data if data else None
            return data
        except requests.exceptions.RequestException as e:
            self.log(f"❌ Jupiter quote network error: {e}")
            return None
        except json.JSONDecodeError as e:
            self.log(f"❌ Jupiter quote JSON decode error: {e}. Response text: {response.text}")
            return None
        except Exception as e:
            self.log(f"❌ Unexpected error getting Jupiter quote: {e}")
            return None

    def _get_jupiter_swap_transaction_raw(self, quote_response: dict) -> Optional[bytes]:
        """
        Requests Jupiter to build a serialized swap transaction from a quote.
        """
        try:
            self.jupiter_rate_limiter.wait()
            url = JUPITER_SWAP_API
            headers = {"Content-Type": "application/json"}
            payload = {
                "quoteResponse": quote_response,
                "userPublicKey": str(self.keypair.pubkey()),
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "dynamicSlippage": {"maxBps": DEFAULT_SLIPPAGE_BPS},
                "prioritizationFeeLamports": DEFAULT_PRIORITIZATION_FEE_LAMPORTS_PER_CU,
            }
            self.log(f"[JUPITER] Swap payload: {json.dumps(payload)[:500]}")
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code != 200:
                self.log(f"❌ Jupiter swap transaction build failed with status {response.status_code}. Response: {response.text}")
                return None
            data = response.json()
            self.log(f"[JUPITER] Swap response: {json.dumps(data)[:500]}")
            if not data or 'swapTransaction' not in data:
                self.log(f"❌ Jupiter swap transaction build failed: {data.get('error', 'No swapTransaction in response')}. Full response: {json.dumps(data)}")
                return None
            raw_transaction_bytes = base64.b64decode(data['swapTransaction'])
            return raw_transaction_bytes
        except requests.exceptions.RequestException as e:
            self.log(f"❌ Jupiter swap transaction network error: {e}")
            return None
        except json.JSONDecodeError as e:
            self.log(f"❌ Jupiter swap transaction JSON decode error: {e}. Response text: {response.text}")
            return None
        except Exception as e:
            self.log(f"❌ Unexpected error building Jupiter swap transaction: {e}")
            return None

    def _get_associated_token_account(self, owner: PublicKey, mint: PublicKey) -> PublicKey:
        """
        Derives the associated token account address for a given owner and mint.
        """
        return get_associated_token_address(owner, mint)

    def log_event(self, message):
        self.log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

    async def _check_and_create_ata(self, owner: PublicKey, mint: PublicKey) -> Optional[PublicKey]:
        """Check if ATA exists for owner/mint pair, create if not."""
        try:
            ata = get_associated_token_address(owner, mint)
            self.log(f"[DEBUG] Checking ATA for {mint}")
            try:
                if self.client is None:
                    self.log(f"[ERROR] No client available for get_account_info.")
                    return None
                account_info = self.client.get_account_info(ata)
                if account_info and account_info.value:
                    self.log(f"[DEBUG] ATA exists for {mint}")
                    return ata
            except Exception as e:
                self.log(f"[DEBUG] ATA does not exist for {mint}, creating... (Error: {e})")
            self.log(f"[DEBUG] Creating new ATA for {mint}")
            self.log(f"[DEBUG] Owner: {owner}")
            self.log(f"[DEBUG] Mint: {mint}")
            try:
                create_ata_ix = create_associated_token_account(
                    payer=owner,
                    owner=owner,
                    mint=mint
                )
                self.log(f"[DEBUG] ATA instruction created successfully")
            except Exception as e:
                self.log(f"[ERROR] Failed to create ATA instruction: {e}")
                return None
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Only rotate if RotatingSolanaClient
                    endpoint = None
                    from sniper_bot import RotatingSolanaClient  # local import to avoid circular
                    if self.client is not None and isinstance(self.client, RotatingSolanaClient):
                        if hasattr(self.client, '_rotate'):
                            self.client._rotate()
                        if hasattr(self.client, 'get_client'):
                            client_obj = self.client.get_client()
                            endpoint = getattr(client_obj, 'endpoint_uri', str(client_obj))
                        else:
                            endpoint = str(self.client)
                    else:
                        endpoint = str(self.client) if self.client is not None else 'None'
                    self.log_event(f"[ATA] Attempt {attempt+1}: Using endpoint {endpoint}")
                    if self.client is None:
                        self.log_event(f"[ATA] No client available for blockhash fetch.")
                        return None
                    self.log_event(f"[ATA] Attempt {attempt+1}: Fetching fresh blockhash for ATA creation")
                    recent_blockhash = self.client.get_latest_blockhash(commitment=sol_commitment.Confirmed).value.blockhash
                    self.log_event(f"[ATA] Fetched blockhash: {recent_blockhash}")
                    instructions = [create_ata_ix]
                    message = MessageV0.try_compile(
                        payer=owner,
                        instructions=instructions,
                        address_lookup_table_accounts=[],
                        recent_blockhash=recent_blockhash
                    )
                    self.log_event(f"[ATA] Message compiled successfully (attempt {attempt+1})")
                    if self.keypair is None:
                        self.log_event("[ATA] No keypair available for signing transaction.")
                        return None
                    transaction = VersionedTransaction(message, [self.keypair])
                    self.log_event(f"[ATA] Transaction created (attempt {attempt+1})")
                    transaction_signed = True
                    self.log_event(f"[ATA] Transaction signed successfully (conventional wallet).")
                    self.log_event(f"[ATA] Sending ATA creation transaction for {mint} (attempt {attempt+1})")
                    resp = self.client.send_raw_transaction(bytes(transaction))
                    self.log_event(f"[ATA] send_raw_transaction response: {resp}")
                    if not resp or not hasattr(resp, 'value') or 'BlockhashNotFound' in str(resp):
                        self.log_event(f"[ATA] Failed to send ATA creation transaction (blockhash issue): {resp}")
                        time.sleep(1)
                        continue
                    signature = resp.value
                    self.log_event(f"[ATA] ATA creation transaction sent with signature: {signature}")
                    conf = self.client.confirm_transaction(signature, commitment=sol_commitment.Confirmed)
                    self.log_event(f"[ATA] Confirmation response: {conf}")
                    if conf and conf.value:
                        self.log_event(f"[ATA] Successfully created ATA {ata}")
                        return ata
                    else:
                        self.log_event(f"[ATA] ATA creation transaction failed to confirm (attempt {attempt+1})")
                        time.sleep(1)
                        continue
                except Exception as e:
                    self.log_event(f"[ATA] Failed during transaction creation/sending (attempt {attempt+1}): {e}\n{traceback.format_exc()}")
                    time.sleep(1)
                    continue
            self.log_event(f"❌ All attempts to create ATA failed for {mint}")
            return None
        except Exception as e:
            self.log(f"❌ Error checking/creating ATA for {mint}: {e}\n{traceback.format_exc()}")
            return None

    def _get_raydium_pool_keys(self, token_mint_address: str, pool_info: Dict[str, Any]) -> Optional[Dict[str, PublicKey]]:
        """
        ATTENTION: THIS FUNCTION IS A SIMULATED PLACEHOLDER FOR REAL-WORLD EXECUTION.
        For actual live trading, you MUST replace the placeholder PublicKeys with
        values obtained by fetching and deserializing the on-chain state of the Raydium AMM pool.

        Attempts to derive or fetch necessary Raydium pool keys for a direct swap.
        
        Args:
            token_mint_address (str): The mint address of the token to swap.
            pool_info (Dict[str, Any]): The pool information from Dexscreener.
                                        Expected to contain 'pairAddress', 'baseToken', 'quoteToken'.

        Returns:
            Optional[Dict[str, PublicKey]]: A dictionary of PublicKeys required for the swap instruction,
                                            or None if keys cannot be determined.
        """
        try:
            # The pairAddress from Dexscreener is typically the AMM ID (pool ID)
            amm_id = PublicKey.from_string(pool_info.get('pairAddress'))
            
            base_mint = PublicKey.from_string(pool_info['baseToken']['address'])
            quote_mint = PublicKey.from_string(pool_info['quoteToken']['address'])

            # Determine which is coin and which is pc based on the token_mint_address
            is_buying_token = (PublicKey.from_string(token_mint_address) == base_mint)
            
            # AMM Authority is typically derived from AMM ID and program ID
            # This is a common pattern for Raydium V4 pools.
            amm_authority, _ = PublicKey.find_program_address(
                [bytes(amm_id)],
                RAYDIUM_AMM_V4_PROGRAM_ID
            )

            # --- CRITICAL: THE FOLLOWING PUBLIC KEYS ARE PLACEHOLDERS ---
            # In a real bot, these accounts hold the actual state of the liquidity pool
            # and the associated Serum market. You MUST fetch their real public keys
            # by querying the Solana blockchain for the AMM_ID's account data and
            # deserializing it according to Raydium's program IDL.
            # Example: Fetch amm_id account info, parse its data to get market_id,
            # then fetch market_id account info to get coin/pc vaults, bids, asks, etc.

            # Common Serum DEX Program ID (usually fixed for Raydium V4 pools)
            SERUM_DEX_PROGRAM_ID = PublicKey.from_string("9xQeWvG816bUx9EPjH2ExZ7mMLP7WMQmfR9ws21VWG9A")

            # Placeholder for amm_open_orders and amm_target_orders
            # These are accounts managed by the AMM program.
            amm_open_orders = PublicKey.new_unique() # Placeholder
            amm_target_orders = PublicKey.new_unique() # Placeholder

            # Placeholder for pool token accounts (vaults where assets are stored within the AMM)
            pool_coin_token_account = PublicKey.new_unique() # Placeholder for base token vault
            pool_pc_token_account = PublicKey.new_unique()   # Placeholder for quote token vault

            # LP Mint address (can often be found in Dexscreener pool_info)
            lp_mint_address = PublicKey.from_string(pool_info.get('lpMint')) if pool_info.get('lpMint') else PublicKey.new_unique()

            # Placeholder for Serum Market ID and its associated accounts
            # The market_id is usually found within the AMM_ID's account data.
            # The vaults, bids, asks, event_queue are found within the market_id's account data.
            market_id_str = pool_info.get('marketId') # Dexscreener might provide this
            market_id = PublicKey.from_string(market_id_str) if market_id_str else PublicKey.new_unique() # Placeholder if not found

            market_coin_vault = PublicKey.new_unique() # Placeholder
            market_pc_vault = PublicKey.new_unique()   # Placeholder
            market_bids = PublicKey.new_unique()       # Placeholder
            market_asks = PublicKey.new_unique()       # Placeholder
            market_event_queue = PublicKey.new_unique() # Placeholder

            # Additional Raydium V4 accounts that might be needed depending on the exact swap instruction
            pool_withdraw_queue = PublicKey.new_unique() # Placeholder
            pool_lp_vault = PublicKey.new_unique()       # Placeholder

            # Raydium swap instruction requires specific accounts in a precise order.
            # The order and exact accounts depend on the Raydium AMM version and swap type.
            # This is a generic set for a common swap instruction, but the placeholders
            # MUST be replaced with real on-chain data.
            pool_keys = {
                "program_id": RAYDIUM_AMM_V4_PROGRAM_ID,
                "amm_id": amm_id,
                "amm_authority": amm_authority,
                "amm_open_orders": amm_open_orders,
                "amm_target_orders": amm_target_orders,
                "pool_coin_token_account": pool_coin_token_account,
                "pool_pc_token_account": pool_pc_token_account,
                "lp_mint_address": lp_mint_address,
                "market_program_id": SERUM_DEX_PROGRAM_ID,
                "market_id": market_id,
                "market_coin_vault": market_coin_vault,
                "market_pc_vault": market_pc_vault,
                "market_bids": market_bids,
                "market_asks": market_asks,
                "market_event_queue": market_event_queue,
                "pool_withdraw_queue": pool_withdraw_queue,
                "pool_lp_vault": pool_lp_vault,
                "pool_version": 4, # Assuming V4
            }
            
            # For buy (SOL -> Token), input is SOL, output is Token
            # For sell (Token -> SOL), input is Token, output is SOL
            if is_buying_token: # Buying the token means SOL is input, token is output
                pool_keys["input_mint"] = WRAPPED_SOL_MINT
                pool_keys["output_mint"] = PublicKey.from_string(token_mint_address)
            else: # Selling the token means Token is input, SOL is output
                pool_keys["input_mint"] = PublicKey.from_string(token_mint_address)
                pool_keys["output_mint"] = WRAPPED_SOL_MINT

            self.log(f"Simulated Raydium Pool Keys for {token_mint_address[:8]}...: {pool_keys}")
            return pool_keys

        except Exception as e:
            self.log(f"❌ Error deriving Raydium pool keys for {token_mint_address}: {e}")
            return None

    async def execute_direct_swap(self, 
                                  token_mint_address: str, 
                                  amount_in_atomic: int, 
                                  is_buy: bool, 
                                  pool_info: Dict[str, Any]) -> bool:
        """
        Executes a direct on-chain swap using Raydium AMM V4.
        """
        if self.SIMULATION_MODE:
            action = "buy" if is_buy else "sell"
            self.log_event(f"SIMULATION: Attempting direct {action} of token {token_mint_address[:8]}... with {amount_in_atomic} atomic units.")
            return True
        if not self.keypair:
            self.log_event("❌ Direct swap error: Wallet keypair not initialized for live mode.")
            return False
        payer = self.keypair.pubkey() if self.keypair is not None else None
        token_mint_pubkey = PublicKey.from_string(token_mint_address)
        pool_keys = self._get_raydium_pool_keys(token_mint_address, pool_info)
        if not pool_keys:
            self.log_event(f"❌ Direct swap failed: Could not get Raydium pool keys for {token_mint_address}.")
            return False
        if is_buy:
            source_token_account = await self._check_and_create_ata(payer, WRAPPED_SOL_MINT)
            destination_token_account = await self._check_and_create_ata(payer, token_mint_pubkey)
        else:
            source_token_account = self._get_associated_token_account(payer, token_mint_pubkey)
            destination_token_account = await self._check_and_create_ata(payer, WRAPPED_SOL_MINT)
        if source_token_account is None or destination_token_account is None:
            self.log_event(f"❌ Direct swap failed: Could not get/create necessary ATAs.")
            return False
        instructions = []
        instructions.append(set_compute_unit_price(DEFAULT_PRIORITIZATION_FEE_LAMPORTS_PER_CU))
        instructions.append(set_compute_unit_limit(200000))
        min_amount_out_atomic = 1
        instruction_data = b'\x08' + amount_in_atomic.to_bytes(8, 'little') + min_amount_out_atomic.to_bytes(8, 'little')
        accounts = [
            AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=pool_keys["amm_id"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["amm_authority"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=pool_keys["amm_open_orders"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["amm_target_orders"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["pool_coin_token_account"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["pool_pc_token_account"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["lp_mint_address"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["market_program_id"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=pool_keys["market_id"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["market_bids"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["market_asks"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["market_event_queue"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["market_coin_vault"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["market_pc_vault"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
            AccountMeta(pubkey=source_token_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=destination_token_account, is_signer=False, is_writable=True),
            AccountMeta(pubkey=RENT, is_signer=False, is_writable=False),
            AccountMeta(pubkey=pool_keys["pool_withdraw_queue"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=pool_keys["pool_lp_vault"], is_signer=False, is_writable=True),
        ]
        swap_instruction = Instruction(
            program_id=RAYDIUM_AMM_V4_PROGRAM_ID,
            accounts=accounts,
            data=instruction_data
        )
        instructions.append(swap_instruction)
        if not is_buy and destination_token_account == self._get_associated_token_account(payer, WRAPPED_SOL_MINT):
            close_wsol_ix = close_account(
                CloseAccountParams(
                    account=destination_token_account,
                    destination=payer,
                    owner=payer,
                    program_id=TOKEN_PROGRAM_ID
                )
            )
            instructions.append(close_wsol_ix)
        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                endpoint = None
                from sniper_bot import RotatingSolanaClient  # local import to avoid circular
                if self.client is not None and isinstance(self.client, RotatingSolanaClient):
                    if hasattr(self.client, '_rotate'):
                        self.client._rotate()
                    if hasattr(self.client, 'get_client'):
                        client_obj = self.client.get_client()
                        endpoint = getattr(client_obj, 'endpoint_uri', str(client_obj))
                    else:
                        endpoint = str(self.client)
                else:
                    endpoint = str(self.client) if self.client is not None else 'None'
                self.log_event(f"[SWAP] Attempt {attempt}: Using endpoint {endpoint}")
                if self.client is None:
                    self.log_event(f"[SWAP] No client available for blockhash fetch.")
                    return False
                self.log_event(f"[SWAP] Attempt {attempt}: Fetching fresh blockhash for direct swap")
                recent_blockhash = self.client.get_latest_blockhash(commitment=sol_commitment.Confirmed).value.blockhash
                self.log_event(f"[SWAP] Fetched blockhash: {recent_blockhash}")
                transaction = VersionedTransaction(
                    MessageV0.try_compile(
                        payer=payer,
                        instructions=instructions,
                        address_lookup_table_accounts=[],
                        recent_blockhash=recent_blockhash,
                    ),
                    []
                )
                if self.keypair is None:
                    self.log("❌ No keypair available for signing transaction.")
                    return False
                transaction = VersionedTransaction(transaction.message, [self.keypair])
                transaction_signed = True
                if not transaction_signed:
                    self.log("❌ Transaction was not signed. Aborting.")
                    return False
                self.log_event("[SWAP] Sending direct swap transaction to Solana network...")
                raw_tx = bytes(transaction)
                result = self.client.send_raw_transaction(raw_tx)
                self.log_event(f"[SWAP] Transaction result: {result}")
                if not result.value:
                    self.log_event(f"[SWAP] Direct swap failed: Transaction error")
                    continue
                else:
                    signature = result.value
                    self.log_event(f"[SWAP] Transaction sent with signature: {signature}")
                    conf = self.client.confirm_transaction(signature, commitment=sol_commitment.Confirmed)
                    self.log_event(f"[SWAP] Confirmation response: {conf}")
                    if conf and conf.value:
                        self.log_event(f"[SWAP] Direct swap transaction confirmed: {signature}")
                        return True
                    self.log_event(f"[SWAP] Direct swap failed: Transaction not confirmed")
                    continue
            except Exception as e:
                self.log_event(f"[SWAP] Direct swap network error (attempt {attempt}): {e}")
                if "Blockhash not found" in str(e) and attempt < MAX_RETRIES:
                    self.log_event("[SWAP] Retrying with a new blockhash...")
                    time.sleep(1)
                    continue
                else:
                    self.log_event("[SWAP] Giving up after max retries or non-blockhash error.")
                    return False
        self.log_event("[SWAP] All attempts to send direct swap transaction failed.")
        return False

    def print_status(self):
        now = time.time()
        elapsed = now - self.start_time
        remaining = max(0, self.session_end_time - now)
        self.log("\n" + "="*self.TERMINAL_WIDTH)
        self.log("="*30 + " SESSION STATUS " + "="*30)
        self.log("="*self.TERMINAL_WIDTH)
        self.log(f"Time Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s | Remaining: {int(remaining//60)}m {int(elapsed%60)}s")
        
        current_sol_usd_value = self.sol_balance * self.sol_usd
        realized_pnl, unrealized_pnl, total_pnl = self.calculate_total_pnl()

        self.log(f"[DEBUG PNL] Initial Balance USD: ${self.initial_balance_usd:.2f}")
        self.log(f"[DEBUG PNL] Current SOL Balance: {self.sol_balance:.4f} SOL")
        self.log(f"[DEBUG PNL] Current SOL Price: ${self.sol_usd:.2f}")
        self.log(f"[DEBUG PNL] Current USD Balance (SOL * Price): ${current_sol_usd_value:.2f}")
        self.log(f"[DEBUG PNL] Realized PnL (from trades list): ${realized_pnl:.2f}")
        self.log(f"[DEBUG PNL] Unrealized PnL (open positions): ${unrealized_pnl:.2f}")
        self.log(f"[DEBUG PNL] Total PnL (realized + unrealized): ${total_pnl:.2f}")

        session_pnl = total_pnl
        if self.initial_balance_usd and self.initial_balance_usd != 0:
            pnl_pct = (session_pnl / self.initial_balance_usd * 100)
        else:
            pnl_pct = 0.0
        
        # Current Balance should reflect the initial balance plus all PnL
        current_total_portfolio_value = self.initial_balance_usd + total_pnl
        
        self.log(f"Initial Balance: ${self.initial_balance_usd:.2f}")
        self.log(f"Current Balance: ${current_total_portfolio_value:.2f}")
        self.log(f"Session PnL: ${session_pnl:.2f} ({pnl_pct:.1f}%)")
        self.log("="*self.TERMINAL_WIDTH)
        open_tokens = [t for t in self.tokens.values() if not t['sold']]
        if open_tokens:
            self.log("\n=== OPEN POSITIONS ===")
            for t in open_tokens:
                address = t.get('address')
                if not address:
                    self.log("[ERROR] Skipping price update: token address is None.")
                    continue
                buy_price = t.get('buy_price_usd', 0)
                cur_price = t.get('price_usd', 0) or 0
                pnl_pct = ((cur_price - buy_price) / buy_price * 100) if buy_price and cur_price else 0
                self.log(f"{t['name']} ({t['symbol']}) | Buy: ${buy_price:.8f} | Cur: ${cur_price:.8f} | PnL: {pnl_pct:+.1f}%")

    def print_final_stats(self):
        # This function is called at the end of the session
        if self.sol_balance is None or self.sol_usd is None:
            self.log("[DEBUG] Skipping final summary: sol_balance or sol_usd not initialized yet.")
            return
        self.clear_log()
        summary_lines = []
        summary_lines.append("\n=== SESSION SUMMARY (Completed Trades) ===")
        
        realized_pnl, unrealized_pnl, total_pnl = self.calculate_total_pnl()
        # Ensure final_balance_usd correctly reflects initial balance plus total PnL
        final_balance_usd = self.initial_balance_usd + total_pnl
        session_pnl = total_pnl

        summary_lines.append(f"Final SOL balance: {self.sol_balance:.4f} | Final USD (approx): ${final_balance_usd:.2f}")
        header = (
            f"{'Address':<44}\t{'Name':<18}\t{'Symbol':<8}\t{'Buy($)':>10}\t{'Sell($)':>10}\t"
            f"{'Amount($)':>10}\t{'PnL($)':>10}\t{'PnL(%)':>8}\t{'Reason':>12}\t{'Buy Time':>19}\t{'Sell Time':>19}"
        )
        summary_lines.append(header)
        for t in self.trades:
            buy_price = self.safe_float(t.get('buy_price_usd', 0))
            sell_price = self.safe_float(t.get('sell_price_usd', 0))
            amount = self.safe_float(t.get('amount_usd', 0))
            pnl_usd = self.safe_float(t.get('pnl', 0))
            pnl_pct = ((sell_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
            buy_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t.get('buy_time', 0))) if t.get('buy_time') else 'N/A'
            sell_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t.get('sell_time', 0))) if t.get('sell_time') else 'N/A'
            row = (
                f"{t.get('address', 'N/A'):<44}\t{t.get('name', 'N/A')[:17]:<18}\t{t.get('symbol', 'N/A')[:7]:<8}\t"
                f"{buy_price:10.4f}\t{sell_price:10.4f}\t{amount:10.4f}\t{pnl_usd:10.2f}\t{pnl_pct:8.2f}\t"
                f"{t.get('reason', 'N/A'):>12}\t{buy_time_str:>19}\t{sell_time_str:>19}"
            )
            summary_lines.append(row)
        summary_lines.append("=======================")
        summary_lines.append(f"SESSION PnL (USD): ${session_pnl:.2f}")
        if self.STARTING_USD and self.STARTING_USD != 0:
            summary_lines.append(f"SESSION PnL (%): {(session_pnl / self.STARTING_USD * 100):.2f}%")
        else:
            summary_lines.append(f"SESSION PnL (%): N/A (Starting USD is 0)")
        
        open_tokens = [t for t in self.tokens.values() if not t['sold']]
        if open_tokens:
            summary_lines.append("\n=== OPEN POSITIONS (Not Sold) ===")
            open_header = (
                f"{'Address':<44}\t{'Name':<18}\t{'Symbol':<8}\t{'Buy($)':>10}\t{'Cur($)':>10}\t"
                f"{'Amount($)':>10}\t{'UnrealPnL($)':>12}\t{'UnrealPnL(%)':>12}\t{'Status':>10}\t{'Buy Time':>19}"
            )
            summary_lines.append(open_header)
            for t in open_tokens:
                buy_price = t.get('buy_price_usd', 0)
                cur_price = t.get('price_usd', 0) or 0
                amount_left_usd = self.safe_float(t.get('amount_left_usd'))
                pnl_if_sold = (amount_left_usd / buy_price * cur_price * (1 - self.SELL_FEE)) - amount_left_usd if buy_price > 0 and cur_price > 0 else 0
                pnl_pct = ((cur_price - buy_price) / buy_price * 100) if buy_price and cur_price else 0
                self.log(f"{t['name']} ({t['symbol']}) | Buy: ${buy_price:.8f} | Cur: ${cur_price:.8f} | PnL: {pnl_pct:+.1f}% (Simulated Sell PnL: ${pnl_if_sold:.2f})")
        
        for line in summary_lines:
            self.log(line)
        self.log("="*self.TERMINAL_WIDTH)


    def rotate_logs(self):
        with self.log_lock:
            if os.path.exists(self.LOG_FILE):
                if os.path.exists(self.LOG_BACKUP):
                    os.remove(self.LOG_BACKUP)
                os.rename(self.LOG_FILE, self.LOG_BACKUP)

    def manual_sell_token(self, address):
        now = time.time()
        token = None
        for t in self.tokens.values():
            if t.get('address') == address and not t.get('sold', False):
                token = t
                break
        if not token:
            self.log(f"[ERROR] Manual sell: Token not found or already sold for address {address}.")
            return False
        result = self.try_sell(token, now, force=True)
        if not result:
            self.log(f"[ERROR] Manual sell failed for token: {token.get('name', 'N/A')} ({token.get('symbol', 'N/A')})")
        return result

    def manual_buy_token(self, token_info, force=True):
        now = time.time()
        result, message = self.simulate_buy(token_info, now, from_watchlist=False, force=force)
        if result:
            return True, f"Manual buy SUCCESS for token: {token_info.get('name', 'N/A')} ({token_info.get('symbol', 'N/A')})\nWarning: Manual buy ignores all filters and settings. Proceed with caution!"
        else:
            return False, message or f"Manual buy FAILED for token: {token_info.get('name', 'N/A')} ({token_info.get('symbol', 'N/A')})\nWarning: Manual buy ignores all filters and settings. Proceed with caution!"

    def _get_websocket_url(self, http_url: str) -> str:
        """Converts an HTTP RPC URL to a WebSocket URL."""
        if http_url.startswith("https"):
            return "wss" + http_url[5:]
        elif http_url.startswith("http"):
            return "ws" + http_url[4:]
        return http_url # Assume it's already a WebSocket URL

    def fetch_dexscreener_pool(self, mint):
        if not mint:
            # Only log if mint is None (unexpected)
            self.log("[ERROR] Token address (mint) is None, cannot fetch info.")
            return None
        if mint.startswith("0x"):
            # Do not log, just skip
            return None
        # Validate Solana mint address: base58, 32 bytes (44 chars), no dots
        if not (isinstance(mint, str) and mint and "." not in mint and not mint.startswith("0x")):
            return None
        url1 = self.DEX_TOKEN_PAIRS_URL + str(mint)
        try:
            self.dexscreener_rate_limiter.wait()
            resp1 = requests.get(url1, timeout=5)
            if resp1.status_code == 200:
                data1 = resp1.json()
                if isinstance(data1, dict) and 'pairs' in data1 and data1['pairs']:
                    return data1['pairs'][0]
                elif isinstance(data1, list) and data1:
                    return data1[0]
            url2 = f"https://api.dexscreener.com/pairs/solana/{mint}"
            resp2 = requests.get(url2, timeout=5)
            if resp2.status_code == 200:
                data2 = resp2.json()
                if isinstance(data2, dict) and 'pair' in data2 and data2['pair']:
                    return data2['pair']
                elif isinstance(data2, list) and data2:
                    return data2[0]
            error_msg = (
                f"[ERROR] Dexscreener API: No pool data found for {mint}.\n"
                f"/token-pairs status: {resp1.status_code}, body: {resp1.text[:200]}\n"
                f"/pairs status: {resp2.status_code}, body: {resp2.text[:200]}"
            )
            self.log(error_msg)
            print(f"[DEBUG FETCH] Returning None. Reason: {error_msg}")
            return None
        except requests.exceptions.RequestException as e:
            error_msg = f"[ERROR] Network error fetching Dexscreener pool for {mint}: {e}"
            self.log(error_msg)
            print(f"[DEBUG FETCH] Returning None. Reason: {error_msg}")
            return None
        except json.JSONDecodeError as e:
            error_msg = f"[ERROR] JSON decode error from Dexscreener API for {mint}: {e}."
            self.log(error_msg)
            print(f"[DEBUG FETCH] Returning None. Reason: {error_msg}")
            return None
        except Exception as e:
            error_msg = f"[ERROR] Unexpected error fetching Dexscreener pool for {mint}: {e}"
            self.log(error_msg)
            print(f"[DEBUG FETCH] Returning None. Reason: {error_msg}")
            return None

    async def _listen_for_program_logs(self):
        """
        Listens to Solana program logs via WebSocket for new liquidity pool creations.
        When a new pool creation log is detected, it triggers an immediate Dexscreener poll.
        """
        ws_url = self._get_websocket_url(self.RPC_URL)
        self.log(f"Connecting to WebSocket RPC: {ws_url}")

        ssl_context = ssl.create_default_context(cafile=certifi.where())

        while not self.stop_threads:
            try:
                async with websockets.connect(ws_url, ssl=ssl_context, ping_interval=20, ping_timeout=20) as websocket:
                    subscribe_request = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "programSubscribe",
                        "params": [
                            str(RAYDIUM_AMM_V2_PROGRAM_ID), # Using V2 for listening, as it's common for init logs
                            {
                                "encoding": "jsonParsed",
                                "commitment": "confirmed",
                                "filters": []
                            }
                        ]
                    }
                    await websocket.send(json.dumps(subscribe_request))
                    
                    response = await websocket.recv()
                    parsed_response = json.loads(response)
                    if 'result' in parsed_response:
                        subscription_id = parsed_response['result']
                        self.log(f"Subscribed to Raydium AMM V2 logs with ID: {subscription_id}")
                    else:
                        self.log(f"❌ Failed to subscribe to program logs: {parsed_response.get('error', 'Unknown error')}")
                        await asyncio.sleep(5)
                        continue

                    while not self.stop_threads:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)

                            if data.get('method') == 'programNotification':
                                logs = data['params']['result']['value'].get('logs')
                                signature = data['params']['result']['value'].get('signature')
                                if logs:
                                    new_pool_detected = False
                                    for log_line in logs:
                                        if "Program log: initialize2" in log_line or "Program log: initialize_pool" in log_line:
                                            self.log(f"🚀 New Raydium pool initialization detected! Signature: {signature}")
                                            new_pool_detected = True
                                            break
                                    
                                    if new_pool_detected:
                                        self.websocket_triggered_poll = True
                                        self.log(f"Triggered immediate Dexscreener poll for new token.")

                        except websockets.exceptions.ConnectionClosedOK:
                            self.log("WebSocket connection closed gracefully.")
                            break
                        except websockets.exceptions.ConnectionClosed as e:
                            self.log(f"WebSocket connection closed unexpectedly: {e}")
                            break
                        except asyncio.CancelledError:
                            self.log("WebSocket listener cancelled.")
                            break
                        except Exception as e:
                            self.log(f"Error in WebSocket listener: {e}")
                            await asyncio.sleep(1)

            except Exception as e:
                self.log(f"WebSocket connection error: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)


    def poll_dexscreener(self):
        last_seen = set()
        last_poll_time = 0
        while not self.stop_threads:
            try:
                now = time.time()
                if not self.websocket_triggered_poll and (now - last_poll_time < self.DEX_POLL_INTERVAL):
                    time.sleep(0.1)
                    continue
                
                self.log(f"\n[DEBUG] Polling for new tokens (triggered by WS: {self.websocket_triggered_poll})...")
                self.websocket_triggered_poll = False

                self.dexscreener_rate_limiter.wait()
                resp = requests.get(self.DEX_TOKEN_PROFILE_URL, timeout=10)
                
                if resp.status_code != 200:
                    self.log(f"[ERROR] Dexscreener API error: Status {resp.status_code}, Response: {resp.text}")
                    time.sleep(self.DEX_POLL_INTERVAL)
                    continue
                
                data = resp.json()
                # The Dexscreener token profiles API returns a list, not a dict with 'pairs'
                if not isinstance(data, list):
                    self.log(f"[ERROR] Invalid response format from Dexscreener token profiles: {json.dumps(data)}")
                    time.sleep(self.DEX_POLL_INTERVAL)
                    continue
                
                tokens_found_in_poll = 0
                tokens_to_process = []
                for token in data:
                    mint = token.get('tokenAddress')
                    if not mint or mint in self.seen_tokens or mint in last_seen:
                        continue
                    # Silently skip non-Solana addresses
                    if mint.startswith("0x"):
                        continue

                    pool_info = self.fetch_dexscreener_pool(mint) 
                    if not pool_info:
                        # fetch_dexscreener_pool will now log a more specific error
                        continue
                    pair_created_at = self.safe_float(pool_info.get('pairCreatedAt', 0)) / 1000
                    if not getattr(self, 'disable_initial_filters', False):
                        if now - pair_created_at > self.MAX_TOKEN_AGE_SECONDS:
                            continue
                    tokens_to_process.append((pair_created_at, token, pool_info))
                
                tokens_to_process.sort(key=lambda x: x[0], reverse=True)
                tokens_to_process = tokens_to_process[:self.MAX_TOKENS_PER_POLL]
                
                for _, token, pool_info in tokens_to_process:
                    mint = token.get('tokenAddress')
                    name = token.get('description','')
                    symbol = token.get('symbol','')
                    liquidity = pool_info.get('liquidity') or {}
                    token['liquidity_usd'] = float(liquidity.get('usd', 0) or 0)
                    token['liquidity_base'] = float(liquidity.get('base', 0) or 0)
                    token['liquidity_quote'] = float(liquidity.get('quote', 0) or 0)
                    token['price_usd'] = float(pool_info.get('priceUsd', 0) or 0)
                    token['price_native'] = float(pool_info.get('priceNative', 0) or 0)
                    token['pairCreatedAt'] = pool_info.get('pairCreatedAt')
                    volume = pool_info.get('volume') or {}
                    token['volume_m5'] = float(volume.get('m5', 0) or 0)
                    txns = pool_info.get('txns') or {}
                    token['txns_m5_buys'] = int(txns.get('m5', {}).get('buys', 0) or 0)
                    token['txns_m5_sells'] = int(txns.get('m5', {}).get('sells', 0) or 0)
                    self.log(f"\n[NEW] {name} ({symbol}) | {mint[:8]}...")
                    # Evaluate GUI (user) filters; if they pass, simulate_buy may execute a buy
                    self.simulate_buy(token, now, force=False)
                    self.seen_tokens.add(mint)
                    last_seen.add(mint)
                    tokens_found_in_poll += 1
                
                self.log(f"[DEBUG] Finished polling. Found {tokens_found_in_poll} new tokens.")
                last_poll_time = now
            except Exception as e:
                self.log(f"[ERROR] poll_dexscreener: {e}")
                time.sleep(self.DEX_POLL_INTERVAL)

    def start_streams(self):
        self.polling_thread = threading.Thread(target=self.poll_dexscreener, daemon=True)
        self.polling_thread.start()

        def run_websocket_loop():
            asyncio.set_event_loop(self.loop)
            self.websocket_task = self.loop.create_task(self._listen_for_program_logs())
            try:
                self.loop.run_forever()
            except asyncio.CancelledError:
                self.log("WebSocket loop cancelled.")
            except Exception as e:
                self.log(f"WebSocket loop encountered error: {e}")
            finally:
                pending_tasks = asyncio.all_tasks(self.loop)
                for task in pending_tasks:
                    if task is not None and hasattr(task, 'cancel'):
                        task.cancel()
                self.loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                self.loop.close()
                self.log("WebSocket loop closed.")

        self.websocket_thread = threading.Thread(target=run_websocket_loop, daemon=True)
        self.websocket_thread.start()

    def clear_initial_filters(self):
        """Set all initial snipe filters to their most permissive values."""
        self.MIN_LIQUIDITY_USD = 0.0
        self.MIN_VOLUME_5M_USD = 0.0
        self.MAX_PRICE_USD = float("inf")
        self.MIN_BUY_TX_RATIO = 0.0
        self.MIN_BUYS_5M = 0
        self.MIN_PAIR_AGE_SECONDS = 0
        self.MAX_PAIR_AGE_SECONDS = float("inf")
        self.log("[CONFIG] Initial snipe filters disabled – polling will include all tokens.")

    def try_sell(self, token, now, force=False):
        if token['sold']:
            self.log(f"[ERROR] Try sell: Token already sold: {token.get('name', 'N/A')} ({token.get('symbol', 'N/A')})")
            return False
        mint = token['address']
        name = token['name']
        symbol = token['symbol']
        cur_price = float(self.safe_float(token.get('price_usd')) or 0.0)
        buy_price = float(self.safe_float(token.get('buy_price_usd')) or 0.0)
        sell_amt_usd = float(self.safe_float(token.get('amount_left_usd')) or 0.0)
        pnl = sell_amt_usd and (cur_price - buy_price) * (sell_amt_usd / buy_price) if buy_price else 0
        trade = {
            'address': mint,
            'buy_price_usd': buy_price,
            'sell_price_usd': cur_price,
            'amount_usd': sell_amt_usd,
            'buy_time': token.get('bought_at'),
            'sell_time': now,
            'pnl': pnl,
            'name': name,
            'symbol': symbol,
            'reason': 'MANUAL',
            'fraction': 1.0,
            'sold': True,
        }
        if mint in self.tokens:
            self.tokens.pop(mint)
        self.trades.append(trade)
        self.log(f"[DEBUG] Closed trades count: {len(self.trades)}")
        self.update_open_positions_file()
        return True

    def update_open_positions_file(self):
        """Save all open (unsold) positions to open_positions.json."""
        open_positions = [t for t in self.tokens.values() if not t.get('sold', False)]
        try:
            with open(self.open_positions_file, 'w', encoding='utf-8') as f:
                json.dump(open_positions, f, indent=2)
        except Exception as e:
            self.log(f"[ERROR] Failed to update open positions file: {e}")

    def load_open_positions(self):
        """Load open positions from open_positions.json."""
        try:
            if os.path.exists(self.open_positions_file):
                with open(self.open_positions_file, 'r', encoding='utf-8') as f:
                    positions = json.load(f)
                    for pos in positions:
                        if 'address' in pos and not pos.get('sold', False):
                            self.tokens[pos['address']] = pos
        except Exception as e:
            self.log(f"[ERROR] Failed to load open positions: {e}")

def has_required_socials(token):
    socials = token.get('socials', {})
    social_fields = ['twitter', 'telegram', 'discord', 'website', 'medium', 'facebook', 'instagram', 'youtube']
    for field in social_fields:
        if token.get(field) or (isinstance(socials, dict) and socials.get(field)):
            return True
    return False

def get_burn_percent(mint, total_supply):
    # Dummy implementation, replace with real API call
    return 0.0

def is_immutable_metadata(mint):
    # Dummy implementation, replace with real API call
    return True

def get_top_holders_percent(mint, total_supply, top_n=5):
    # Dummy implementation, replace with real API call
    return 0.0

def has_risky_wallet(mint):
    # Dummy implementation, replace with real API call
    return False

if __name__ == "__main__":
    print("Running sniper_bot.py directly for demonstration.")
    print("Set SIMULATION_MODE = False and provide a PRIVATE_KEY or SEED_PHRASE to test live transactions.")

    bot_session = SniperSession(simulation=True, rpc_url="https://api.mainnet-beta.solana.com")
    
    try:
        bot_session.run()
    except KeyboardInterrupt:
        print("\nStopping bot...")
    finally:
        bot_session.stop()
        print("Bot stopped.")
