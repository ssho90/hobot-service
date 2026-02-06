
## Actions Taken
5.  **UI Enhancement (FRED Popup)**:
    *   Updated `FredIndicatorStatusModal.tsx` to display `Value` (latest value) and `Collected At` (collection timestamp) columns.
    *   Implemented stale data logic: If `last_collected_at` exceeds the threshold for a given `frequency` (e.g., >1 day for daily, >32 days for monthly), a blinking red "traffic light" indicator is displayed.
    *   Updated backend `fred_collector.py` and `main.py` to support new fields (`latest_value`, `last_collected_at`) in `get_indicators_status`.

## Result
*   Popup now shows detailed status including latest data value and collection time.
*   Users can visually identify outdated indicators via the red warning light.
