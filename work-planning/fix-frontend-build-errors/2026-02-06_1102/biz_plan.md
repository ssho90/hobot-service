# Fix Frontend Build Errors (Round 2)

## User Request
- Fix TypeScript errors in `FredIndicatorStatusModal.tsx`:
  - `Property 'icon' does not exist on type...`

## Diagnosis
- Previous fix for `MacroIndicators.tsx` removed `icon` from `ChartCard` props definition and usage.
- `FredIndicatorStatusModal.tsx` also uses `ChartCard` and was still passing `icon`.
- Additionally, a previous attempt to fix `FredIndicatorStatusModal.tsx` broke the JSX syntax by accidentally removing the component tag.

## Solution
- **Repair**: Restored correct `ChartCard` usage in `FredIndicatorStatusModal.tsx`.
- **Align Props**: Removed `icon` prop passing to match `ChartCard` interface.
- **Cleanup**: Removed unused `Activity` import.

## Status
- **Complete**. `ChartCard` usage is now consistent across all components, and syntax errors are resolved.
