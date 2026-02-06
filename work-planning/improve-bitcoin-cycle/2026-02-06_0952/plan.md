# Fix Bitcoin Cycle Chart: UI Polish

## User Request
- "Current Price라는 텍스트 없애고 빨간 점만 남겨놔" (Remove 'Current Price' text, leave only red dot).
- The user observed that the Current Price dot had a text label rendered next to it on the chart.

## Diagnosis
- The `PulseDot` component (used for the Red Dot `Scatter`) renders a `<text>` element if the data point has a `label` property.
- I had added `label: 'Current Price'` to `currentPoint` in the previous step (to assist with Tooltip identification), unknowingly triggering the on-chart text rendering.

## Solution
- **Remove `label`**: Removed `label: 'Current Price'` from `currentPoint`.
- **Tooltip Continuity**: The `CustomTooltip` logic uses `isCurrent` (which is still true) to identify the point, so the Tooltip will *still* correctly display "Current Price" even without the `label` property.

## Plan
- [x] Remove `label` from `currentPoint` definition.

## Status
- **Complete**. The chart will now display a clean pulsating red dot without adjacent text, while the hover tooltip remains informative.
