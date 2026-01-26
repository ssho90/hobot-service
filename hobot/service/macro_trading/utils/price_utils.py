
import math

def adjust_to_tick_size(price: float) -> int:
    """
    Adjust the given price to the nearest valid tick size based on KRX ETF rules.
    
    User Request: Default to ETF tick size logic.
    
    KRX ETF Tick Size Rules:
    - Price < 2,000: 1 won
    - Price >= 2,000: 5 won
    
    Args:
        price: The raw price input (float or int)
        
    Returns:
        int: The adjusted price as an integer
    """
    price = float(price)
    
    if price < 2000:
        tick_size = 1
    else:
        tick_size = 5
        
    # Round to nearest tick
    adjusted_price = round(price / tick_size) * tick_size
    
    return int(adjusted_price)
