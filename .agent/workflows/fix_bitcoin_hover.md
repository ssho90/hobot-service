# Improve Bitcoin Cycle Hover Reliability (Phase 2)

## User Feedback
- "여전히 마우스 올리면 빨간점 가격만 보이는데?" (Still only Red Dot works)
- Issue: Manual hit-testing logic (`scale.invert` + distance calc) was likely failing for Peak/Bottom points, possibly due to empty `hoverTargets` or coordinate mismatch.

## Diagnosis
- The manually calculated coordinates approach is fragile.
- Recharts provides `state.activePayload` which contains the exact data points currently under the cursor (handled by Recharts' own internal hit-testing).
- Since Red Dot works (it's a Scatter), and Peak/Bottoms are points on a Line (plus an invisible Scatter I added), Recharts *should* see them in `activePayload`.

## Solution
- Refactored `resolveHoverPoint` to use `state.activePayload`.
- Logic:
  1. Check if `activePayload` is present.
  2. Search `activePayload` for any item that has `isHoverTarget: true` (Peak/Bottom) or `isCurrent: true` (Red Dot).
  3. If found, use that data to render badges.
- This creates a much more native interaction where the badges appear exactly when Recharts considers the point "hovered" (snapped).

## Verification
- Code changed in `BitcoinCycleChart.tsx`.
- Behavior: Hovering exactly on (or near, depending on Recharts tooltip behavior) a Peak/Bottom should showing the badges.
