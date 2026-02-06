
## Actions Taken
4.  **Optimization**:
    *   Analyzed `hobot/service/macro_trading/signals/quant_signals.py` and `ai_strategist.py` to identify used FRED indicators.
    *   Identified that `GDP` (Quarterly Real GDP) was defined in `FRED_INDICATORS` but not used in any analysis logic (Dashboard uses `GDPNOW`, Taylor Rule uses assumptions).
    *   Removed `GDP` from `FRED_INDICATORS` in `hobot/service/macro_trading/collectors/fred_collector.py` to prevent unnecessary data collection.
