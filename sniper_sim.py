import time
from datetime import datetime, timedelta
import requests
import json
import re
import threading
from threading import Lock
import os
from solders.keypair import Keypair
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.api import Client
from solders.transaction import Transaction
from solders.system_program import transfer, TransferParams
import base58
from mnemonic import Mnemonic
from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins
from typing import Optional
import sniper_trading

# ==========================================
# === BOT CONFIGURATION ===
# ==========================================

# Wallet Settings
SIMULATION_MODE = True     # Set to False to use real wallet
WALLET_TYPE = "private"      # "seed" for seed phrase, "private" for private key
SEED_PHRASE = ""          # Your 12/24 word seed phrase (when WALLET_TYPE = "seed")
PRIVATE_KEY = "Gi5mMxQJvT28K5eZ1Z6Pic88V1CRD3YotRqTpJyaBSGFZ1vUhicTLKnJwJP7JoY6W1syJK7zyN2vDAFRfCcHh7x"          # Your private key (when WALLET_TYPE = "private")
RPC_URL = "https://api.mainnet-beta.solana.com"  # Solana RPC URL

# Trading Settings
STARTING_USD = 100.0      # Starting balance for simulation mode
POSITION_SIZE_USD = 2.0  # Amount to spend per trade
BUY_FEE = 0.005          # 0.5% fee per trade
SELL_FEE = 0.005         # 0.5% fee per trade
TAKE_PROFIT_MULT = 2.0   # Sell at 2x buy price
STOP_LOSS_PCT = 0.8      # Stop loss at 80% of buy price

# Token Filters
MIN_LIQUIDITY_USD = 10000.0  # Minimum liquidity required
MIN_VOLUME_5M_USD = 2000.0   # Minimum 5-minute volume
MAX_PRICE_USD = 1.0          # Maximum token price
MIN_BUY_TX_RATIO = 1.05      # Minimum buy/sell transaction ratio
MIN_PAIR_AGE_SECONDS = 60   # Minimum pair age (1 minute)
MAX_PAIR_AGE_SECONDS = 1800  # Maximum pair age (30 minutes)
MIN_BUYS_5M = 20            # Minimum buys in 5 minutes

# Bot Settings
SIMULATION_DURATION = 60 * 60 * 2  # 2 hours
DEX_POLL_INTERVAL = 1             # Poll every 2 seconds
MAX_TOKENS_PER_POLL = 500          # Maximum tokens to process per poll
MAX_TOKEN_AGE_SECONDS = 1800      # Only look at tokens created in last 30 minutes
TERMINAL_WIDTH = 100              # For formatting output
SUMMARY_INTERVAL = 300            # Status update interval (5 minutes)
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB max log file size
MAX_SEEN_TOKENS = 10000          # Maximum number of seen tokens to store
MAX_TRADES_HISTORY = 1000        # Maximum number of trades to keep in memory
MAX_LOG_LINES = 5000             # Maximum number of log lines to keep in memory

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
            self.last_call = datetime.now()

class SniperSession:
    # --- CONFIG ---
    COINGECKO_SOL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
    PRICE_CHECK_INTERVAL = 120  # seconds (much less frequent to avoid rate limits)
    SOCIAL_REGEX = re.compile(r'(twitter|t\.me|discord|instagram|facebook|youtube|medium|linktr|x\.com)', re.IGNORECASE)
    VOLUME_SPIKE_WINDOW = 12  # 1 minute if interval is 5s
    VOLUME_SPIKE_MULT = 1.15   # Buy if current volume is 1.5x recent average
    WATCHLIST_PRINT_INTERVAL = 180  # 3 minutes in seconds
    DEX_TOKEN_PROFILE_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
    DEX_TOKEN_PAIRS_URL = "https://api.dexscreener.com/token-pairs/v1/solana/"
    LOG_FILE = "logs"
    LOG_BACKUP = "logs.old"

    def __init__(self, seed_phrase: Optional[str] = None, private_key: Optional[str] = None):
        # Initialize locks
        self.lock = Lock()
        self.log_lock = Lock()
        self.log_lines = []
        self.rate_limiter = RateLimiter(calls_per_second=2)
        
        # Use global config
        self.SIMULATION_MODE = SIMULATION_MODE
        self.RPC_URL = RPC_URL
        self.STARTING_USD = STARTING_USD
        self.SIMULATION_DURATION = SIMULATION_DURATION
        self.BUY_FEE = BUY_FEE
        self.SELL_FEE = SELL_FEE
        self.POSITION_SIZE_USD = POSITION_SIZE_USD
        self.TAKE_PROFIT_MULT = TAKE_PROFIT_MULT
        self.STOP_LOSS_PCT = STOP_LOSS_PCT
        self.MIN_LIQUIDITY_USD = MIN_LIQUIDITY_USD
        self.MIN_VOLUME_5M_USD = MIN_VOLUME_5M_USD
        self.MAX_PRICE_USD = MAX_PRICE_USD
        self.MIN_BUY_TX_RATIO = MIN_BUY_TX_RATIO
        self.MIN_PAIR_AGE_SECONDS = MIN_PAIR_AGE_SECONDS
        self.MAX_PAIR_AGE_SECONDS = MAX_PAIR_AGE_SECONDS
        self.MIN_BUYS_5M = MIN_BUYS_5M
        self.DEX_POLL_INTERVAL = DEX_POLL_INTERVAL
        self.MAX_TOKENS_PER_POLL = MAX_TOKENS_PER_POLL
        self.MAX_TOKEN_AGE_SECONDS = MAX_TOKEN_AGE_SECONDS
        self.TERMINAL_WIDTH = TERMINAL_WIDTH
        self.SUMMARY_INTERVAL = SUMMARY_INTERVAL
        
        # Initialize Solana client
        self.client = Client(self.RPC_URL)
        
        # Initialize wallet based on mode
        if not self.SIMULATION_MODE:
            if WALLET_TYPE == "seed":
                # Use provided seed phrase or global config
                seed = seed_phrase or SEED_PHRASE
                if not seed:
                    raise ValueError("Seed phrase required! Set SEED_PHRASE in config or provide when creating session.")
                try:
                    seed_bytes = Bip39SeedGenerator(seed).Generate()
                    bip44_mst = Bip44.FromSeed(seed_bytes, Bip44Coins.SOLANA)
                    account = bip44_mst.Purpose().Coin().Account(0).Change(0).AddressIndex(0)
                    private_key_bytes = account.PrivateKey().Raw().ToBytes()
                    self.keypair = Keypair.new_from_bytes(private_key_bytes)
                    self.wallet_address = str(self.keypair.pubkey())
                    print(f"✅ Wallet loaded from seed phrase")
                except Exception as e:
                    raise ValueError(f"Invalid seed phrase: {e}")
            else:  # private key mode
                # Use provided key or global config
                key = private_key or PRIVATE_KEY
                if not key:
                    raise ValueError("Private key required! Set PRIVATE_KEY in config or provide when creating session.")
                print(f"DEBUG: key={key}, len={len(key)}")
                try:
                    if key.startswith('['):  # Byte array format
                        key = json.loads(key)
                        key_bytes = bytes(key)
                    elif 86 <= len(key) <= 88:  # Base58 format (allow 86-88 chars)
                        try:
                            key_bytes = base58.b58decode(key)
                        except Exception:
                            raise ValueError("Invalid base58 private key")
                    else:
                        raise ValueError("Invalid private key format")
                    self.keypair = Keypair.from_bytes(key_bytes)
                    self.wallet_address = str(self.keypair.pubkey())
                    print(f"✅ Wallet loaded from private key")
                except Exception as e:
                    raise ValueError(f"Invalid private key: {e}")
        else:
            self.keypair = None
            self.wallet_address = "SIMULATION_WALLET"
            
        # Initialize other variables with thread safety
        self.sol_balance = None
        self.sol_usd = None
        self.tokens = {}
        self.seen_tokens = set()
        self.trades = []
        self.start_time = None
        self.last_price_check = 0
        self.session_started = False
        self.token_volumes = {}
        self.watched_tokens = {}
        self.last_watchlist_print = time.time()
        self.dex_thread = None
        self.stop_threads = False
        self.last_summary_print = time.time()
        self.initial_balance_usd = None
        self.session_end_time = None

        # Bind trading functions
        self.execute_buy = sniper_trading.execute_buy.__get__(self)
        self.execute_sell = sniper_trading.execute_sell.__get__(self)
        self.simulate_buy_sim = sniper_trading.simulate_buy_sim.__get__(self)
        self.try_sell_sim = sniper_trading.try_sell_sim.__get__(self)

    def rotate_logs(self):
        """Rotate log files when they get too large"""
        with self.log_lock:
            if os.path.exists(self.LOG_FILE):
                if os.path.exists(self.LOG_BACKUP):
                    os.remove(self.LOG_BACKUP)
                os.rename(self.LOG_FILE, self.LOG_BACKUP)

    def cleanup_collections(self):
        """Clean up memory-intensive collections"""
        with self.lock:
            if len(self.seen_tokens) > MAX_SEEN_TOKENS:
                self.seen_tokens = set(list(self.seen_tokens)[-MAX_SEEN_TOKENS:])
            if len(self.trades) > MAX_TRADES_HISTORY:
                self.trades = self.trades[-MAX_TRADES_HISTORY:]
            if len(self.log_lines) > MAX_LOG_LINES:
                self.log_lines = self.log_lines[-MAX_LOG_LINES:]

    def get_wallet_balance(self):
        """Get wallet balance based on mode"""
        if self.SIMULATION_MODE:
            if self.sol_usd is None or self.sol_usd <= 0:
                return 0
            return self.sol_balance if self.sol_balance is not None else self.STARTING_USD / self.sol_usd
        else:
            try:
                pubkey = PublicKey.from_string(self.wallet_address) if hasattr(PublicKey, 'from_string') else PublicKey(bytes(self.wallet_address, 'utf-8'))
                response = self.client.get_balance(pubkey)
                value = getattr(response, 'value', 0)
                if value > 0:
                    return value / 1e9
            except Exception as e:
                print(f"Error getting wallet balance: {e}")
            return 0

    def fetch_sol_usd(self):
        """Fetch SOL/USD price with proper error handling"""
        try:
            self.rate_limiter.wait()  # Rate limit API calls
            resp = requests.get(self.COINGECKO_SOL, timeout=5)
            resp.raise_for_status()
            price = float(resp.json()["solana"]["usd"])
            if price <= 0:
                raise ValueError("Invalid SOL price")
            return price
        except (requests.RequestException, KeyError, ValueError):
            return None

    def position_size(self):
        """Calculate position size with safety checks"""
        with self.lock:
            if self.sol_usd is None or self.sol_usd <= 0:
                return 0
            usd = min(self.POSITION_SIZE_USD, self.sol_balance * self.sol_usd)
            return usd / self.sol_usd

    def log(self, line):
        """Thread-safe logging with rotation"""
        with self.log_lock:
            try:
                if os.path.exists(self.LOG_FILE) and os.path.getsize(self.LOG_FILE) > MAX_LOG_SIZE:
                    self.rotate_logs()
                with open(self.LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now().isoformat()} - {line}\n")
                self.log_lines.append(line)
                self.cleanup_collections()
            except IOError as e:
                print(f"Error writing to log: {e}")

    def clear_log(self):
        """Thread-safe log clearing"""
        with self.log_lock:
            if os.path.exists(self.LOG_FILE):
                os.remove(self.LOG_FILE)
            self.log_lines = []

    def safe_float(self, val):
        """Safe float conversion with proper error handling"""
        try:
            result = float(val)
            return result if not (result == float('inf') or result == float('-inf') or result != result) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def print_header(self, text):
        print("\n" + "="*self.TERMINAL_WIDTH)
        print(f" {text} ".center(self.TERMINAL_WIDTH, "="))
        print("="*self.TERMINAL_WIDTH)

    def calculate_total_pnl(self):
        realized_pnl = 0
        unrealized_pnl = 0
        
        # Calculate PnL from completed trades
        for trade in self.trades:
            realized_pnl += self.safe_float(trade.get('pnl', 0))
        
        # Calculate unrealized PnL from open positions
        for token in self.tokens.values():
            if not token['sold']:
                buy_price = self.safe_float(token.get('buy_price_usd'))
                cur_price = self.safe_float(token.get('price_usd'))
                amount_left_usd = self.safe_float(token.get('amount_left_usd'))
                
                if buy_price > 0 and cur_price > 0 and amount_left_usd > 0:
                    # Calculate gross value at current price
                    tokens_amount = amount_left_usd / buy_price
                    current_value = tokens_amount * cur_price
                    # Account for sell fee that would be paid
                    current_value *= (1 - self.SELL_FEE)
                    # Calculate unrealized PnL
                    position_pnl = current_value - amount_left_usd
                    unrealized_pnl += position_pnl
        
        total_pnl = realized_pnl + unrealized_pnl
        return realized_pnl, unrealized_pnl, total_pnl

    def print_status(self):
        now = time.time()
        elapsed = now - self.start_time
        remaining = max(0, self.session_end_time - now)
        
        print("\n" + "="*self.TERMINAL_WIDTH)
        print("="*30 + " SESSION STATUS " + "="*30)
        print("="*self.TERMINAL_WIDTH)
        
        # Time info
        print(f"Time Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s | Remaining: {int(remaining//60)}m {int(remaining%60)}s")
        
        # Balance and PnL
        current_balance = self.sol_balance * self.sol_usd
        if len(self.trades) == 0:
            session_pnl = 0.0
        else:
            session_pnl = current_balance - self.initial_balance_usd
        print(f"Initial Balance: ${self.initial_balance_usd:.2f}")
        print(f"Current Balance: ${current_balance:.2f}")
        print(f"Session PnL: ${session_pnl:.2f} ({(session_pnl/self.initial_balance_usd*100):.1f}%)")
        
        # Optionally, print realized/unrealized PnL for trade stats
        realized_pnl, unrealized_pnl, total_pnl = self.calculate_total_pnl()
        print(f"Realized PnL (trades): ${realized_pnl:.2f}")
        print(f"Unrealized PnL (open): ${unrealized_pnl:.2f}")
        print("="*self.TERMINAL_WIDTH)
        
        # Show open positions
        open_tokens = [t for t in self.tokens.values() if not t['sold']]
        if open_tokens:
            print("\n=== OPEN POSITIONS ===")
            for t in open_tokens:
                buy_price = t['buy_price_usd']
                cur_price = t.get('price_usd', 0) or 0
                pnl_pct = ((cur_price - buy_price) / buy_price * 100) if buy_price and cur_price else 0
                print(f"{t['name']} ({t['symbol']}) | Buy: ${buy_price:.8f} | Cur: ${cur_price:.8f} | PnL: {pnl_pct:+.1f}%")

    def print_summary(self):
        if self.sol_balance is None or self.sol_usd is None:
            print("[DEBUG] Skipping summary: sol_balance or sol_usd not initialized yet.")
            return
            
        self.clear_log()
        summary_lines = []
        summary_lines.append("\n=== SESSION SUMMARY (Completed Trades) ===")
        
        # Calculate final balance and session PnL
        final_balance_usd = self.sol_balance * self.sol_usd
        session_pnl = final_balance_usd - self.STARTING_USD
        
        summary_lines.append(f"Final SOL balance: {self.sol_balance:.4f} | Final USD: ${final_balance_usd:.2f}")
        
        # Print trade history
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
        summary_lines.append(f"SESSION PnL (%): {(session_pnl / self.STARTING_USD * 100):.2f}%")
        
        # Print open positions
        open_tokens = [t for t in self.tokens.values() if not t['sold']]
        if open_tokens:
            summary_lines.append("\n=== OPEN POSITIONS (Not Sold) ===")
            open_header = (
                f"{'Address':<44}\t{'Name':<18}\t{'Symbol':<8}\t{'Buy($)':>10}\t{'Cur($)':>10}\t"
                f"{'Amount($)':>10}\t{'UnrealPnL($)':>12}\t{'UnrealPnL(%)':>12}\t{'Status':>10}\t{'Buy Time':>19}"
            )
            summary_lines.append(open_header)
            
            for t in open_tokens:
                buy_price = self.safe_float(t.get('buy_price_usd', 0))
                amount = self.safe_float(t.get('amount_left_usd', 0))
                cur_price = self.safe_float(t.get('price_usd', 0))
                
                if buy_price > 0:
                    tokens_amount = amount / buy_price
                    current_value = tokens_amount * cur_price * (1 - self.SELL_FEE)  # Account for potential sell fee
                    unreal_pnl_usd = current_value - amount
                    unreal_pnl_pct = ((cur_price - buy_price) / buy_price * 100)
                    
                    tp = buy_price * self.TAKE_PROFIT_MULT
                    sl = buy_price * self.STOP_LOSS_PCT
                    
                    if cur_price >= tp:
                        status = "TP HIT"
                    elif cur_price <= sl:
                        status = "SL HIT"
                    else:
                        status = "HOLDING"
                        
                    buy_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t.get('bought_at', 0))) if t.get('bought_at') else 'N/A'
                    
                    open_row = (
                        f"{t.get('address', 'N/A'):<44}\t{t.get('name', 'N/A')[:17]:<18}\t{t.get('symbol', 'N/A')[:7]:<8}\t"
                        f"{buy_price:10.4f}\t{cur_price:10.4f}\t{amount:10.4f}\t{unreal_pnl_usd:12.2f}\t{unreal_pnl_pct:12.2f}\t"
                        f"{status:>10}\t{buy_time_str:>19}"
                    )
                    summary_lines.append(open_row)
                    
            summary_lines.append("=======================")
            
        self.clear_log()
        for line in summary_lines:
            self.log(line)
            print(line)

    def start_streams(self):
        self.dex_thread = threading.Thread(target=self.poll_dexscreener, daemon=True)
        self.dex_thread.start()

    def run(self):
        self.print_header("STARTING BOT")
        mode_str = "SIMULATION MODE" if self.SIMULATION_MODE else "REAL WALLET MODE"
        print(f"Running in {mode_str}")
        
        # Initialize SOL price first
        self.sol_usd = self.fetch_sol_usd()
        if self.sol_usd is None:
            print("❌ Failed to fetch SOL price. Please check your internet connection or API limits.")
            return
        self.sol_balance = self.get_wallet_balance()
        self.initial_balance_usd = self.sol_balance * self.sol_usd
        
        print(f"\nWallet Address: {self.wallet_address}")
        print(f"Starting Balance: {self.sol_balance:.4f} SOL (${self.initial_balance_usd:.2f} USD)")
        print(f"SOL Price: ${self.sol_usd:.2f}")
        
        if self.initial_balance_usd < self.POSITION_SIZE_USD:
            print(f"❌ Insufficient balance for trading! Need minimum ${self.POSITION_SIZE_USD:.2f}, have ${self.initial_balance_usd:.2f}")
            return
            
        print(f"Session Duration: {self.SIMULATION_DURATION/60:.1f} minutes")
        print("="*self.TERMINAL_WIDTH)
        
        # Setup session timing
        self.start_time = time.time()
        self.session_end_time = self.start_time + self.SIMULATION_DURATION
        
        self.start_streams()
        
        last_status = 0
        last_price_check = 0
        PRICE_CHECK_INTERVAL = 5
        
        while time.time() < self.session_end_time and not self.stop_threads:
            now = time.time()
            
            # Update prices and check for sells
            if now - last_price_check >= PRICE_CHECK_INTERVAL:
                new_sol_price = self.fetch_sol_usd()
                if new_sol_price is not None and new_sol_price > 0:
                    self.sol_usd = new_sol_price
                # If fetch fails, keep using the last known self.sol_usd (do not set to None)
                # Update prices for all tokens
                for token in list(self.tokens.values()):
                    if not token['sold']:
                        pool_data = self.fetch_dexscreener_pool(token['address'])
                        if pool_data:
                            token['price_usd'] = self.safe_float(pool_data.get('priceUsd'))
                            self.try_sell(token, now)
                last_price_check = now
            
            # Print status every SUMMARY_INTERVAL
            if now - last_status >= self.SUMMARY_INTERVAL:
                self.print_status()
                last_status = now
            
            time.sleep(0.1)  # Prevent CPU spinning
        
        self.stop_threads = True
        self.print_final_stats()

    def fetch_dexscreener_pool(self, mint):
        try:
            url = self.DEX_TOKEN_PAIRS_URL + mint
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # If the response is a list, return the first item
                if isinstance(data, list) and data:
                    return data[0]
                # If the response is a dict with 'pairs', return the first pair
                if isinstance(data, dict) and 'pairs' in data and data['pairs']:
                    return data['pairs'][0]
        except Exception as e:
            print(f"[ERROR] API error: {e}")
        return None

    def poll_dexscreener(self):
        last_seen = set()
        last_poll_time = 0
        
        while not self.stop_threads:
            try:
                now = time.time()
                
                # Respect polling interval
                if now - last_poll_time < self.DEX_POLL_INTERVAL:
                    time.sleep(0.1)  # Short sleep to prevent CPU spinning
                    continue
                
                print(f"\n[DEBUG] Polling for new tokens...")
                resp = requests.get(self.DEX_TOKEN_PROFILE_URL, timeout=10)
                if resp.status_code != 200:
                    print(f"[ERROR] Dexscreener API error: {resp.status_code}")
                    time.sleep(self.DEX_POLL_INTERVAL)
                    continue

                data = resp.json()
                if not isinstance(data, list):
                    print("[ERROR] Invalid response format from Dexscreener")
                    time.sleep(self.DEX_POLL_INTERVAL)
                    continue

                # Sort tokens by creation time (newest first)
                tokens = []
                for token in data:
                    mint = token.get('tokenAddress')
                    if not mint or mint in self.seen_tokens or mint in last_seen:
                        continue
                        
                    # Get pool info early to check creation time
                    pool_info = self.fetch_dexscreener_pool(mint)
                    if not pool_info:
                        continue
                        
                    # Check pair creation time
                    pair_created_at = self.safe_float(pool_info.get('pairCreatedAt', 0)) / 1000
                    if now - pair_created_at > self.MAX_TOKEN_AGE_SECONDS:
                        continue
                        
                    tokens.append((pair_created_at, token, pool_info))

                # Sort by creation time (newest first) and limit
                tokens.sort(key=lambda x: x[0], reverse=True)
                tokens = tokens[:self.MAX_TOKENS_PER_POLL]

                # Process tokens
                for _, token, pool_info in tokens:
                    mint = token.get('tokenAddress')
                    name = token.get('description','')
                    symbol = token.get('symbol','')
                    
                    # Update token with pool info
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

                    print(f"\n[NEW] {name} ({symbol}) | {mint[:8]}...")
                    
                    # Try to buy
                    self.simulate_buy(token, now)
                    last_seen.add(mint)

                last_poll_time = now

            except Exception as e:
                print(f"[ERROR] poll_dexscreener: {e}")
                time.sleep(self.DEX_POLL_INTERVAL)

    def print_final_stats(self):
        self.print_header("SESSION ENDED")
        
        # Calculate final stats
        realized_pnl, unrealized_pnl, total_pnl = self.calculate_total_pnl()
        final_balance = self.sol_balance * self.sol_usd
        
        print(f"\nFinal Results:")
        print(f"Initial Balance: ${self.initial_balance_usd:.2f}")
        print(f"Final Balance: ${final_balance:.2f}")
        print(f"Total PnL: ${total_pnl:.2f} ({(total_pnl/self.initial_balance_usd*100):+.1f}%)")
        print(f"Realized PnL: ${realized_pnl:.2f}")
        print(f"Unrealized PnL: ${unrealized_pnl:.2f}")
        
        # Trade statistics
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t['pnl'] > 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        print(f"\nTrade Statistics:")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {winning_trades}")
        print(f"Win Rate: {win_rate:.1f}%")
        
        # Show any remaining open positions
        open_positions = [t for t in self.tokens.values() if not t['sold']]
        if open_positions:
            print(f"\nOpen Positions ({len(open_positions)}):")
            for pos in open_positions:
                buy_price = pos['buy_price_usd']
                cur_price = pos.get('price_usd', 0) or 0
                pnl_pct = ((cur_price - buy_price) / buy_price * 100) if buy_price and cur_price else 0
                print(f"{pos['name']} ({pos['symbol']})")
                print(f"Address: {pos['address']}")
                print(f"Buy: ${buy_price:.8f} | Current: ${cur_price:.8f}")
                print(f"PnL: {pnl_pct:+.1f}%")
                print("-" * 50)
        
        print("="*self.TERMINAL_WIDTH)

if __name__ == "__main__":
    session = SniperSession()
    session.run()
