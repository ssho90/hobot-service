import sys
import os
import logging
from datetime import date, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.macro_trading.collectors.fred_collector import FREDCollector
from service.database.db import get_db_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def update_net_liquidity():
    try:
        collector = FREDCollector()
        
        # We need 2 years of data (730 days)
        # Fetching a bit more to be safe (3 years)
        start_date = date.today() - timedelta(days=365*2 + 30)
        
        logger.info(f"Target Start Date: {start_date}")

        # 1. Ensure raw components are up-to-date and have enough history
        components = ["WALCL", "WTREGEN", "RRPONTSYD"]
        for code in components:
            logger.info(f"Collecting {code}...")
            # fetch_indicator fetches from FRED API
            data = collector.fetch_indicator(code, start_date=start_date)
            
            if not data.empty:
                logger.info(f"Saving {len(data)} records for {code}...")
                # save_to_db saves to database
                collector.save_to_db(code, data, fill_missing=True)
            else:
                logger.warning(f"No data fetched for {code}")

        # 2. Calculate and save Net Liquidity
        # calculate_derived_indicators uses get_latest_data(days=730) internally
        # which queries the DB we just populated.
        logger.info("Calculating Net Liquidity (NETLIQ)...")
        collector.calculate_derived_indicators()
        
        print("Net Liquidity update complete.")
        
    except Exception as e:
        logger.error(f"Update failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    update_net_liquidity()
