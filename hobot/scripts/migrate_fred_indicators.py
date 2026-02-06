import sys
import os
import logging
from datetime import date, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.macro_trading.collectors.fred_collector import FREDCollector

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def migrate():
    try:
        collector = FREDCollector()
        
        # 1. Collect T10Y2Y (10-Year Minus 2-Year Treasury Constant Maturity)
        # Fetch last 3 years to ensure good sparkline data
        start_date = date.today() - timedelta(days=365*3)
        
        logger.info("Migrating T10Y2Y...")
        data = collector.fetch_indicator("T10Y2Y", start_date=start_date)
        if not data.empty:
            collector.save_to_db(
                "T10Y2Y", 
                data, 
                "10-Year Minus 2-Year Treasury Constant Maturity", 
                "%", 
                fill_missing=True
            )
        else:
            logger.warning("No data found for T10Y2Y")

        # 2. Update Liquidity Components to ensure NETLIQ is accurate up to now
        # We fetch fresh data for the components
        calc_components = ["WALCL", "WTREGEN", "RRPONTSYD"]
        logger.info(f"Updating components for Net Liquidity: {calc_components}")
        
        for code in calc_components:
            data = collector.fetch_indicator(code, start_date=start_date)
            # Metadata is already in FRED_INDICATORS, so we can just pass code and data
            # save_to_db looks up name/unit if not provided
            collector.save_to_db(code, data)

        # 3. Calculate NETLIQ
        logger.info("Calculating derived NETLIQ...")
        collector.calculate_derived_indicators()
        
        print("Migration and calculation complete.")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
