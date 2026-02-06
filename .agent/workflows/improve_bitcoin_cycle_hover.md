# Improve Bitcoin Cycle Chart Hover Interaction

## Problem
The user requested better visibility of x/y values when hovering over "Peak" or "Bottom" points.
Current implementation:
- Had strict hover detection (threshold 0.6) making it hard to trigger.
- Used simple gray text labels which were visually weak.

## Solution
Modified `BitcoinCycleChart.tsx` to:
1.  **Relax Hover Threshold**: Increased `bestScore` threshold from 0.6 to 2.0, making it much easier to "snap" to Peak/Bottom points.
2.  **Custom Axis Badges**: Implemented `CustomXReferenceLabel` and `CustomYReferenceLabel` components.
    - Renders a pill-shaped background (`rect`) with white text.
    - Positioned along the axes (X: below chart, Y: left of chart) to mimic active axis ticks.

## Verification
- Code updated in `BitcoinCycleChart.tsx`.
- Removed invalid `isFront` prop that caused TypeScript errors.
- Visual result should be: Hovering near a peak/bottom shows a horizontal and vertical dashed line with dark badges on the axes displaying the exact Date and Price.
