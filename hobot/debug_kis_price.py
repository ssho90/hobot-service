
import os
import time
import logging
from dotenv import load_dotenv
from service.macro_trading.kis.kis_api import KISAPI
import concurrent.futures

# Setup logging
logging.basicConfig(level=logging.DEBUG)
load_dotenv(override=True)

def fetch_price_task(api, ticker):
    try:
        print(f"Fetching {ticker}...")
        # Add delay to match the fix
        time.sleep(0.5)
        start = time.time()
        price = api.get_current_price(ticker)
        duration = time.time() - start
        return ticker, price, duration
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return ticker, None, 0

def fetch_prices_concurrently():
    # Load credentials from .env
    app_key = os.getenv("TEST_HT_API_KEY")
    app_secret = os.getenv("TEST_HT_SECRET_KEY")
    account_no = os.getenv("TEST_HT_ACCOUNT")
    
    # Assume simulation for debugging/dev environment as per logs
    is_simulation = True 

    if not app_key or not app_secret or not account_no:
        print("Error: Missing credentials in .env file")
        return

    print(f"Using credentials from .env: Account {account_no} (Simulation: {is_simulation})")

    # Create API instance (it handles token internally)
    api = KISAPI(app_key, app_secret, account_no, is_simulation=is_simulation)
    
    # Fails: '138230', '133690', '357870', '453850'
    # Success: '458730'
    tickers = ['138230', '133690', '357870', '453850', '458730', '005930', '000660'] 
    
    print(f"Starting concurrent fetch for {len(tickers)} tickers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(fetch_price_task, api, ticker): ticker for ticker in tickers}
        
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                t, price, duration = future.result()
                print(f"Result: {t} -> {price} ({duration:.2f}s)")
            except Exception as e:
                print(f"Exception for {ticker}: {e}")

if __name__ == "__main__":
    fetch_prices_concurrently()
