
## Actions Taken
6.  **Chart Visualization Feature (Popup)**:
    *   Added `ChartCard.tsx` component to create reusable, small chart cards with sparklines.
    *   Added `ExpandedChartModal.tsx` component to display a large, detailed chart when a user maximizes a card.
    *   Updated `FredIndicatorStatusModal.tsx` to replace the table view with a grid of `ChartCard` components.
    *   Updated `get_indicators_status` in `fred_collector.py` to fetch and return the last 60 data points (sparkline) for each indicator using a window function query (or fallback).
    *   Updated API response serialization in `main.py` for sparkline dates.

## Result
*   **Visual Grid**: The FRED Indicator Popup now displays a visually appealing grid of charts instead of a text table.
*   **Sparklines**: Users can see the recent trend (last ~2 months) directly on the card.
*   **Expansion**: Users can click the maximize button on any card to see a large, detailed view of the data.
*   **Information**: Latest Values, Frequency, and Update Dates are still preserved in the card layout.
