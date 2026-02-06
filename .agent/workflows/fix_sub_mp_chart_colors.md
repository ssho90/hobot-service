# Sub-MP Details Chart Visualization Fix

## Problem
The user reported that the bar charts for "Sub-MP Details" (specifically Stocks and Alternatives) looked different between Target and Actual even when the internal balance was identical.

## Diagnosis
- The `StackedBar` component was assigning colors based on the index of the item (`COLORS[i % COLORS.length]`).
- If the order of items in `target` and `actual` arrays differed (even if the set of items was the same), the colors would be mismatched.
- For example, Item A might be Blue in Target (index 0) but Green in Actual (index 1), leading to a confusing visual representation where identical compositions looked different.

## Solution
- Modified `TradingDashboard.tsx` to implement consistent color assignment.
- Within each Sub-MP section loop:
  1. Collected all unique asset names from both `target` and `actual` lists.
  2. Sorted the names to ensure deterministic order.
  3. Created a `getColor(name)` helper that assigns colors based on the name's index in the sorted list.
  4. Updated `StackedBar` props to use this consistent color for both Target and Actual charts.

## Verification
- Code changes applied to `TradingDashboard.tsx`.
- Now, the same asset (by name) will always have the same color in both Target and Actual charts within a section.
