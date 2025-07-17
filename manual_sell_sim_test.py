import time

def try_sell_sim(token, now, take_profit_pct=30, stop_loss_pct=15, sell_fee=0.005, sol_usd=100):
    print(f"[DEBUG] try_sell_sim called with token: {token}")
    if token.get('sold', False):
        print("[ERROR] Token already sold!")
        return False
    # Get current price (check both 'price_usd' and 'price')
    cur_price = float(token.get('price_usd') or 0)
    if cur_price == 0:
        cur_price = float(token.get('price') or 0)
    # Get buy price (check both 'buy_price_usd' and 'buy_price')
    buy_price = float(token.get('buy_price_usd') or 0)
    if buy_price == 0:
        buy_price = float(token.get('buy_price') or 0)
    if cur_price == 0 or buy_price == 0:
        print(f"[ERROR] No price data: cur_price={cur_price}, buy_price={buy_price}")
        return False
    tp = buy_price * (1 + take_profit_pct / 100)
    sl = buy_price * (1 - stop_loss_pct / 100)
    print(f"[DEBUG] buy_price={buy_price}, cur_price={cur_price}, TP={tp}, SL={sl}")
    # Manual sell always allowed (force=True)
    reason = "MANUAL"
    sell_amt_usd = float(token.get('amount_left_usd') or 0)
    tokens_bought = sell_amt_usd / buy_price if buy_price else 0
    gross_usd = tokens_bought * cur_price
    fee = gross_usd * sell_fee
    net_usd = gross_usd - fee
    pnl_usd = net_usd - sell_amt_usd
    sol_received = net_usd / sol_usd if sol_usd else 0
    # Mark as sold
    token['amount_left_usd'] = 0
    token['sold'] = True
    token['sell_price_usd'] = cur_price
    token['sell_time'] = now
    token['pnl'] = pnl_usd
    print(f"[SUCCESS] SOLD {token.get('name', '')} at ${cur_price:.8f}")
    print(f"[DEBUG] Token after sell: {token}")
    return True

def test_cases():
    now = time.time()
    # Case 1: Normal sell
    token1 = {
        'address': '0xABC',
        'name': 'TestToken',
        'symbol': 'TST',
        'bought_at': now - 1000,
        'amount_usd': 100,
        'amount_left_usd': 100,
        'buy_price_usd': 0.01,
        'price_usd': 0.012,
        'sold': False,
        'sell_price_usd': None,
        'sell_time': None,
        'pnl': None
    }
    print("\n--- Case 1: Normal sell ---")
    try_sell_sim(token1, now)

    # Case 2: Already sold
    print("\n--- Case 2: Already sold ---")
    try_sell_sim(token1, now)

    # Case 3: Missing price_usd, but has price
    token2 = token1.copy()
    token2['sold'] = False
    token2['price_usd'] = 0
    token2['price'] = 0.013
    print("\n--- Case 3: price_usd missing, price present ---")
    try_sell_sim(token2, now)

    # Case 4: Missing both price fields
    token3 = token1.copy()
    token3['sold'] = False
    token3['price_usd'] = 0
    token3['price'] = 0
    print("\n--- Case 4: Both price fields missing ---")
    try_sell_sim(token3, now)

    # Case 5: buy_price_usd missing, but has buy_price
    token4 = token1.copy()
    token4['sold'] = False
    token4['buy_price_usd'] = 0
    token4['buy_price'] = 0.009
    print("\n--- Case 5: buy_price_usd missing, buy_price present ---")
    try_sell_sim(token4, now)

    # Case 6: Both buy_price fields missing
    token5 = token1.copy()
    token5['sold'] = False
    token5['buy_price_usd'] = 0
    token5['buy_price'] = 0
    print("\n--- Case 6: Both buy_price fields missing ---")
    try_sell_sim(token5, now)

if __name__ == "__main__":
    test_cases() 
