# Implement Code Review Improvements

## Goal
Implement key recommendations from the code review to improve performance, maintainability, and code quality of `hobot-ui-v2`.

## Proposed Changes

### 1. Code Splitting (Critical)
- **File:** `src/App.tsx`
- **Change:**
    - Convert static imports of page components (`Admin*`, `TradingDashboard`, `RegisterPage`) to `React.lazy()` imports.
    - Wrap usage in `Suspense` with a fallbak loader.
- **Benefit:** Reduces initial bundle size.

### 2. Utility Refactoring (Medium)
- **New File:** `src/utils/formatters.ts`
- **Change:**
    - Extract `formatCurrency`, `formatPercent`, `safeNumber`, `getTimeAgo` from `TradingDashboard.tsx` and `Dashboard`.
    - Update components to import these functions.
- **Benefit:** Reduces component complexity and memory usage (no re-creation on render).

### 3. Data Fetching Optimization (Medium-High)
- **New File:** `src/hooks/useMacroData.ts`
- **Change:**
    - Create custom hooks (`useOverview`, `useBalance`, `useRebalancing`) using standard `fetch` or a lightweight wrapper.
    - (Optional) Introduce `SWR` if approved, otherwise structure hooks to be SWR-ready.
- **Target:** `TradingDashboard.tsx`, `AIMacroReport.tsx`.

## Verification Plan
1.  **Build Verification:** Run `npm run build` to ensure code splitting works and no chunks are broken.
2.  **Runtime Check:** Verify page loads (especially Admin/Trading tabs) work correctly with Suspense loading states.
3.  **Refactoring Check:** Ensure formatted numbers/dates appear exactly as before.
