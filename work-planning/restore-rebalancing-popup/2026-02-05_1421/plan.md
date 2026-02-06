# Plan: Restore Rebalancing Test Popup

## Objective
Restore the functionality where clicking the "Rebalancing Test" button in the Trading Dashboard opens a popup allowing the user to choose between testing "Step 3 & 4" (Planning) or "Step 5" (Execution).

## Current State
- `TradingDashboard.tsx` has a "Rebalancing Test" button but it currently does nothing or has lost its previous binding.
- Backend API `/api/macro-trading/rebalance/test` exists and supports `max_phase` parameter.

## Tasks
1.  [x] Create `RebalancingTestModal.tsx` component.
    -   Modal UI with backdrop.
    -   Two major buttons: "Step 3 & 4" (max_phase=4) and "Step 5" (max_phase=5).
    -   API integration to call `/api/macro-trading/rebalance/test`.
    -   Display execution results (JSON or formatted text).
2.  [x] Integrate into `TradingDashboard.tsx`.
    -   Add state `isTestModalOpen`.
    -   Add `RebalancingTestModal` to the render tree.
    -   Connect the "Rebalancing Test" button to set the state to true.

## Technical Details
- **API Endpoint:** `POST /api/macro-trading/rebalance/test`
- **Body:** `{ "max_phase": int }`
- **Components:**
    -   `src/components/RebalancingTestModal.tsx` (New)
    -   `src/components/TradingDashboard.tsx` (Modified)
