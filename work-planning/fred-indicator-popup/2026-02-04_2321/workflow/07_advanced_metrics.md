
## Actions Taken
9.  **Advanced Metrics Implementation (Backend & Frontend)**:
    *   **Net Liquidity**:
        *   Added `NETLIQ` to `fred_collector.py`.
        *   Added logic in `fred_collector.py` to calculate `Net Liquidity` (`WALCL` - `WTREGEN` - `RRPONTSYD`) by combining weekly Fed assets with daily TGA/RRP data (forward filling weekly data).
        *   Configured the collector to automatically compute and save `NETLIQ` to the database after collecting raw indicators.
    *   **Yield Spread (10Y-2Y)**:
        *   Added `T10Y2Y` (10-Year Minus 2-Year Treasury Constant Maturity) to `fred_collector.py` to fetch directly from FRED.
    *   **High Yield Spread**:
        *   Confirmed `BAMLH0A0HYM2` is already being collected.
    *   **Frontend Groups Update**:
        *   Updated `MacroIndicators.tsx` to include `NETLIQ` in the "Liquidity" group.
        *   Updated `MacroIndicators.tsx` to include `T10Y2Y`, `VIXCLS`, `STLFSI4` in the "Growth & Risk" group.

## Result
*   Dashboard now displays sophisticated derived metrics:
    *   **Net Liquidity**: Shows the actual liquidity trend in the market.
    *   **10Y-2Y Spread**: Key recession indicator is now explicitly tracked.
    *   **Risk Metrics**: VIX and Financial Stress Index are added/grouped for better risk assessment.
