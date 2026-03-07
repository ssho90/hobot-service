# Dashboard UI Refinement Plan

## Goal
Fix the issue where MP/Sub-MP info is not showing, and implement the requested "Show Description" button and "New" update indicator.

## Diagnosis
- The current implementation relies on `mp_id` being present in the `target_allocation` JSON of the `ai_strategy_decisions` table.
- If the latest decision record is old format, `mp_id` is missing, so no MP info is fetched.
- **Solution**: Check if `ai_strategy_decisions` table has `mp_id` column. If yes, use it. If no, we might need to rely on `ai_strategist.py` caching or fallback. (Note: `AIStrategyDecision` pydantic model has `mp_id`, likely it's saved in the DB columns too).

## Tasks
1. **Schema Verification**: Check `database_schema.sql` for `ai_strategy_decisions` columns.
2. **Backend Fix (`main.py`)**: 
    - In `get_rebalancing_status`, if `mp_id` is not in `target_allocation_raw`, try to fetch it from the database row (if column exists) or infer it.
    - Ensure `mp_info` is populated.
3. **Frontend Refinement (`TradingDashboard.tsx`)**:
    - Implement a "Details" button (toggle) to show/hide the Description/Timestamp block.
    - Ensure the "New" indicator (blue dot) is visible even when description is hidden (or on the button).
    - Verify `updated_at` logic.

## Workflow
- Create workflow log in `workflow/`
- Verify Schema
- Modify `main.py`
- Modify `TradingDashboard.tsx`
- Verify
