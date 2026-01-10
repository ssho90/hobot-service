
import sys
import os
import logging
from pprint import pprint

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, "hobot"))

from dotenv import load_dotenv
load_dotenv()

from service.macro_trading.collectors.fred_collector import get_fred_collector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_ids():
    collector = get_fred_collector()
    
    ids_to_test = [
        "GACDFSA066MSFRBPHI", # Philly Current
        "NOCDFSA066MSFRBPHI", # Philly New Orders
        "GAFDFSA066MSFRBPHI", # Philly Future
        "PCEPILFE", # Core PCE
        "CPIAUCSL", # CPI
        "STLFSI4", # MOVE
        "GDPNOW", # GDPNow
    ]
    
    print(f"{'ID':<25} | {'Count':<5} | {'Latest Date':<12} | {'Latest Value'}")
    print("-" * 60)
    
    for series_id in ids_to_test:
        try:
            # Fetch enough days to ensure we get something if it exists
            data = collector.get_latest_data(series_id, days=700)
            if len(data) > 0:
                latest_date = data.index[-1].strftime('%Y-%m-%d')
                latest_val = data.iloc[-1]
                print(f"{series_id:<25} | {len(data):<5} | {latest_date:<12} | {latest_val}")
            else:
                print(f"{series_id:<25} | 0     | N/A          | N/A")
        except Exception as e:
            print(f"{series_id:<25} | ERROR | {str(e)}")

if __name__ == "__main__":
    test_ids()
