import base64
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

# Deserialize the transaction
transaction = VersionedTransaction.from_bytes(base64.b64decode(swap_transaction))

# Log public key
print("Wallet public key:", keypair.pubkey())

# Sign the transaction
transaction.sign([keypair])

# Log signatures
print("Signatures after signing:", transaction.signatures)

# Serialize and send
raw_tx = transaction.serialize()
client.send_raw_transaction(raw_tx)