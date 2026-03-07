# Fix Sub-MP Details Chart Visualization

## User Request
- "왜 채권 보면 서로 이름이 다른걸까? 같은 종목이거든"
- Issue:
  - Target: TIGER CD금리투자KIS
  - Actual: TIGER CD금리투자KIS(합성)
  - User treats them as SAME, but system treats them as different, causing visual separation and color mismatches.

## Analysis
- **Root Cause**: Exact string matching fails due to suffixes like `(합성)`.
- **Solution**:
  - Normalize names by removing `(합성)` for comparison.
  - Use normalized name for:
    - Sorting (Order)
    - Coloring (Consistency)
    - Display Label (Visual Uniformity)

## Plan
1.  **Analyze `TradingDashboard.tsx`**: Locate the map loop.
2.  **Define `normalizeName`**: Regex replace `/\(합성\)/g`.
3.  **Apply Logic**:
    - `allNames = set(items.map(normalizeName))`
    - `getColor(normalizeName(item.name))`
    - `StackedBar label = normalizeName(item.name)`
4.  **Fix Syntax**: Clean up any residual syntax errors from previous rough edits.

## Status
- [x] Analyze Code
- [x] Implement normalization logic (+ display fix)
- [x] Fix Syntax Errors (Extra `}`)
- [x] Verify Structure (Code clean)
