# Dashboard Enhancement Plan: MP/Sub-MP Info & Alerts

## Goal
Add functionality to the `TradingDashboard` to:
1. View descriptions for Model Portfolios (MP) and Sub-Model Portfolios (Sub-MP).
2. Display the last updated date for MPs and Sub-MPs.
3. Show an alert indicator if the update occurred within the last 24 hours.

## Database Schema Analysis
- Verify table names: `model_portfolios`, `sub_portfolio_models`.
- Verify columns: `description`, `updated_at`.

## Backend Modifications (`hobot-service`)
- Target Service: `portfolio_service.py` (or equivalent).
- API Endpoint: `GET /api/dashboard/portfolio-info` (New) or update existing.
    - Should return list of MPs and Sub-MPs with `name`, `description`, `updated_at`.
    - Only active portfolios? Or all? -> Probably active ones for the dashboard context.

## Frontend Modifications (`hobot-ui-v2`)
- Component: `TradingDashboard.tsx`
- Features:
    - Fetch new portfolio info data.
    - "Portfolio Info" button (opens Modal or expanded section).
    - Helper function to check if `updated_at` is within 24 hours.
    - UI for "Last Updated" and Alert Icon (e.g., Red dot or "New" badge).

## Verification Plan
1. Check backend API returns correct data.
2. Verify Dashboard displays description button.
3. Verify Dashboard displays updated dates.
4. Verify Alert appears only for recent updates (can manually update DB to test).
