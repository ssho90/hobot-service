
## Actions Taken
8.  **Time Elapsed Tag (UI Enhancement)**:
    *   Updated `ChartCard.tsx` to accept a new prop `lastCollectedAt` (timestamp string).
    *   Implemented `formatTimeAgo` utility function within `ChartCard` to calculate human-readable elapsed time (e.g., "Just now", "6h ago", "2d ago").
    *   Added a small gray text tag below the frequency label in `ChartCard` to display this elapsed time.
    *   Updated both `MacroIndicators.tsx` (Dashboard) and `FredIndicatorStatusModal.tsx` (Popup) to pass the `last_collected_at` data to the `ChartCard` component.

## Result
*   Users can now see exactly **how long ago** each indicator was updated by the collector.
*   This provides immediate context on data freshness alongside the "Stale" warning light.
