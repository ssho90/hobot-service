# Fix Frontend Build Errors

## User Request
- Fix TypeScript errors reported in `frontend-build.log`.

## Diagnosed & Fixed Issues
1.  **MacroIndicators.tsx**:
    - Removed unused imports: `Briefcase`, `BarChart3`, `TrendingUp`, `Activity`.
    - Removed unused variable `icon`.
    - Removed duplicate `frequency` prop in JSX.
2.  **ChartCard.tsx**:
    - Removed unused `icon` prop (from interface and destructuring).
    - Fixed `formatter` type to accept `number | undefined`.
3.  **ExpandedChartModal.tsx**:
    - Removed unused imports: `Activity`, `TrendingUp`, `BarChart3`.
    - Fixed `formatter` type to accept `number | undefined`.

## Status
- **Complete**. All reported errors have been addressed. The build should now pass without unused variable warnings or Type mismatch errors in Recharts.
