import requests
import base64
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
import base58
from solders.signature import Signature
from solders.hash import Hash
from solders.message import VersionedMessage, to_bytes_versioned

# Jupiter endpoints
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"

# SOL and your target token mint address
SOL_MINT = "So11111111111111111111111111111111111111112"
TARGET_TOKEN_MINT = "98FtSGzKktXL88ewViwmbfKVw2duXUwuhRfRi7kibonk"

# Test parameters
amount_sol = 0.02
amount_lamports = int(amount_sol * 1e9)
slippage_bps = 50  # 0.5%

# --- USER: FILL IN YOUR PRIVATE KEY HERE (base58 string or array) ---
PRIVATE_KEY = "Gi5mMxQJvT28K5eZ1Z6Pic88V1CRD3YotRqTpJyaBSGFZ1vUhicTLKnJwJP7JoY6W1syJK7zyN2vDAFRfCcHh7x"  # e.g. "[1,2,3,...]" or base58 string

if PRIVATE_KEY.startswith("["):
    import json
    private_key_bytes = bytes(json.loads(PRIVATE_KEY))
else:
    private_key_bytes = base58.b58decode(PRIVATE_KEY)

keypair = Keypair.from_bytes(private_key_bytes)
user_public_key = str(keypair.pubkey())

# 0. Check SOL balance before proceeding
client = Client("https://api.mainnet-beta.solana.com")
try:
    balance_resp = client.get_balance(keypair.pubkey())
    sol_balance = int(getattr(balance_resp, "value", 0))
    print(f"Wallet balance: {sol_balance} lamports ({sol_balance/1e9} SOL)")
    if sol_balance < amount_lamports:
        print(f"ERROR: Insufficient SOL balance for swap. You have {sol_balance} lamports, need {amount_lamports}.")
        exit(1)
except Exception as e:
    print("ERROR: Could not fetch wallet balance:", e)
    exit(1)

# 1. Get quote
params = {
    "inputMint": SOL_MINT,
    "outputMint": TARGET_TOKEN_MINT,
    "amount": str(amount_lamports),
    "slippageBps": str(slippage_bps),
}
try:
    quote_resp = requests.get(JUPITER_QUOTE_API, params=params, timeout=10)
    print("Quote status:", quote_resp.status_code)
    quote_data = quote_resp.json()
    print("Quote response:", quote_data)
    if quote_resp.status_code != 200 or "routePlan" not in quote_data:
        print("ERROR: No valid route found for swap or Jupiter API error.")
        exit(1)
except Exception as e:
    print("ERROR: Failed to fetch quote from Jupiter:", e)
    exit(1)

# 2. Get swap transaction (if quote is valid)
payload = {
    "quoteResponse": quote_data,
    "userPublicKey": user_public_key,
    "wrapAndUnwrapSol": True,
    "dynamicComputeUnitLimit": True,
    "dynamicSlippage": {"maxBps": slippage_bps},
}
try:
    swap_resp = requests.post(JUPITER_SWAP_API, json=payload, timeout=20)
    print("Swap status:", swap_resp.status_code)
    swap_data = swap_resp.json()
    print("Swap response:", swap_data)
    if "swapTransaction" not in swap_data:
        print("ERROR: No swapTransaction in Jupiter response.")
        exit(1)
except Exception as e:
    print("ERROR: Failed to fetch swap transaction from Jupiter:", e)
    exit(1)

swap_txn_bytes = base64.b64decode(swap_data["swapTransaction"])
print("Swap transaction length:", len(swap_txn_bytes))
# Decode the transaction
try:
    txn = VersionedTransaction.from_bytes(swap_txn_bytes)
    print("\n=== Jupiter Swap Transaction Debug ===")
    print("Decoded transaction:")
    print(txn)
    print("\n--- Signature Debug ---")
    print("Signatures before signing:")
    for i, sig in enumerate(txn.signatures):
        print(f"  [{i}] {sig}")
    print("Message:")
    print(txn.message)
    print(f"Your public key: {keypair.pubkey()}")
    # Find my signer index
    my_pk = keypair.pubkey()
    try:
        signer_index = list(txn.message.account_keys).index(my_pk)
    except ValueError:
        raise RuntimeError("Your pubkey is not one of the transaction signers!")
    # Sign the transaction using the keypair
    msg_bytes = to_bytes_versioned(txn.message)
    sig = keypair.sign_message(msg_bytes)
    print("type(sig):", type(sig))
    # Set the entire signatures array explicitly
    txn.signatures = [sig] + txn.signatures[1:]
    print("Signatures after signing:")
    for i, sig in enumerate(txn.signatures):
        print(f"  [{i}] {sig}")
    print("=== End Debug ===\n")
    print("signer_index:", signer_index)
    print("account_keys[signer_index]:", txn.message.account_keys[signer_index])
    print("keypair pubkey:", keypair.pubkey())
    print("num_required_signatures:", txn.message.header.num_required_signatures)
    print("signatures:", txn.signatures)
    signed_txn_bytes = bytes(txn)
    # Send using solana-py
    print("Sending transaction to mainnet...")
    send_resp = client.send_raw_transaction(signed_txn_bytes)
    print("Signature:", getattr(send_resp, "value", send_resp))
except Exception as e:
    # Try to print simulation logs if available
    if hasattr(e, 'args') and e.args and isinstance(e.args[0], dict):
        err_data = e.args[0]
        if 'data' in err_data and 'logs' in err_data['data']:
            print("Transaction simulation logs:")
            for log in err_data['data']['logs']:
                print(log)
    print("Error decoding/signing/sending transaction:", e)
    if 'insufficient lamports' in str(e):
        print("ERROR: Your wallet does not have enough SOL to complete this swap.")
    elif 'No valid route' in str(e):
        print("ERROR: Jupiter could not find a route for this swap. The token may not be supported or liquidity is too low.")
    elif 'slippage' in str(e):
        print("ERROR: Slippage too high. Try increasing slippage tolerance or reducing trade size.")
    else:
        print("ERROR: An unknown error occurred. See above for details.")
    exit(1) 
