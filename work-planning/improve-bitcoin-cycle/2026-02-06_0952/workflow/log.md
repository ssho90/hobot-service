# Workflow Log

## 2026-02-06
- **09:53 - 11:15**: Previous fixes (Time Axis, Live Price).
- **11:27**: User reported "Current Price Tooltip shows Peak data".
- **11:30**: **Critical Visualization Fix**:
  - Found that `CustomTooltip` logic was favoring "Event" data over "Current" data if the `label` was missing.
  - Found that invisible scatter points (`hoverTargets`) were not explicitly mapped to Time Axis coordinates, potentially causing "ghost" hover zones.
  - **Action**:
    1.  Updated `CustomTooltip` to prioritize `isCurrent` flag.
    2.  Added `x`, `y` coordinates explicitly to **BOTH** `currentPoint` and `hoverTargets` scatter datasets.
    3.  Added `label: 'Current Price'` to `currentPoint`.
- **Result**: The Red Dot will now exclusively trigger "Current Price" in the tooltip, and invisible hover targets will be strictly bound to their correct historical dates, eliminating ghost overlays.
