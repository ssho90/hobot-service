
from datetime import datetime

BITCOIN_CYCLE_DATA = [
    {"date": "2012-11", "price": 12, "type": "history", "event": "1st Halving"},
    {"date": "2013-12", "price": 1209, "type": "history", "event": "Peak"},
    {"date": "2015-01", "price": 180, "type": "history", "event": "Bottom"},
    {"date": "2016-07", "price": 650, "type": "history", "event": "2nd Halving"},
    {"date": "2017-12", "price": 19328, "type": "history", "event": "Peak"},
    {"date": "2018-12", "price": 3222, "type": "history", "event": "Bottom"},
    {"date": "2020-05", "price": 8600, "type": "history", "event": "3rd Halving"},
    {"date": "2021-11", "price": 66459, "type": "history", "event": "Peak"},
    {"date": "2022-11", "price": 15653, "type": "history", "event": "Bottom"},
    {"date": "2024-04", "price": 63000, "type": "history", "event": "4th Halving"},
    {"date": "2025-08", "price": 125000, "type": "prediction", "event": "Peak (Exp)"},
    {"date": "2026-10", "price": 45000, "type": "prediction", "event": "Bottom (Exp)"},
    {"date": "2028-04", "price": 70000, "type": "prediction", "event": "5th Halving"},
    {"date": "2029-08", "price": 200000, "type": "prediction", "event": "Peak (Exp)"}
]

def test_logic():
    processed_cycle_data = []
    now = datetime(2026, 2, 3) # Simulate current date
    
    for item in BITCOIN_CYCLE_DATA:
        try:
            item_date = datetime.strptime(item["date"], "%Y-%m")
            if item_date <= now:
                new_type = "history"
                new_event = item["event"].replace(" (Exp)", "")
            else:
                new_type = "prediction"
                new_event = item["event"]
                
            processed_cycle_data.append({
                **item,
                "type": new_type,
                "event": new_event
            })
        except ValueError:
            processed_cycle_data.append(item)

    for p in processed_cycle_data:
        print(f"Date: {p['date']}, Type: {p['type']}, Event: {p['event']}")

test_logic()
