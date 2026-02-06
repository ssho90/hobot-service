
## Actions Taken
7.  **Dashboard Integration**:
    *   Replaced the mock-data based `MacroIndicators.tsx` with the new real-time `ChartCard` grid system.
    *   Fetched live data from `/api/macro-trading/fred-indicators` within `MacroIndicators`.
    *   Implemented grouping logic:
        *   **Liquidity**: WALCL, RRPONTSYD, WTREGEN
        *   **Employment**: PAYEMS, UNRATE
        *   **Prices**: CPIAUCSL, PCEPI, FEDFUNDS, DFII10
        *   **Growth/Risk**: GDPNOW, DGS10, DGS2, BAMLH0A0HYM2, Philly Fed Indices
    *   Added **Stale Data Warning** (Red Traffic Light) directly to the Dashboard cards. Logic checks `last_collected_at` against frequency thresholds.
    *   Integrated `ExpandedChartModal` for full-screen view of any dashboard chart.

## Result
*   Main dashboard now shows **Real** FRED data.
*   Outdated indicators are instantly visible with a **Red Pulse** animation on the card.
*   Users can drill down into any chart directly from the dashboard.
