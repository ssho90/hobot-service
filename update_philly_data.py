
import sys
import os
import logging
from datetime import date, timedelta

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, "hobot"))

from dotenv import load_dotenv
load_dotenv()

from service.macro_trading.collectors.fred_collector import get_fred_collector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_philly_data():
    collector = get_fred_collector()
    
    # New Philly Fed IDs and STLFSI4
    philly_ids = [
        "GACDFSA066MSFRBPHI", # Current Activity
        "NOCDFSA066MSFRBPHI", # New Orders
        "GAFDFSA066MSFRBPHI", # Future Activity
        "STLFSI4"             # Financial Stress Index
    ]
    
    logger.info("Starting update for Philly Fed data...")
    
    for series_id in philly_ids:
        try:
            logger.info(f"Fetching {series_id}...")
            # Fetch last 5 years to be safe
            data = collector.fetch_indicator(series_id, start_date=date.today() - timedelta(days=365*5))
            
            if not data.empty:
                saved = collector.save_to_db(series_id, data)
                logger.info(f"Saved {saved} records for {series_id}")
            else:
                logger.warning(f"No data found for {series_id}")
                
        except Exception as e:
            logger.error(f"Error updating {series_id}: {e}")

if __name__ == "__main__":
    update_philly_data()
