# Plan: FRED Indicator Popup Implementation

## 1. Overview
The goal is to add a popup in the Macro Dashboard (Home screen) that displays a list of FRED indicators currently being collected.
The popup should include:
- FRED Ticker Name (Series ID)
- Collection Interval (Frequency)
- Latest Collection Date (from DB)
- Ticker Description

## 2. Analysis
### Frontend
- Needs a new button on the Macro Dashboard.
- Needs a new Modal/Popup component to display the list.
- Calls a backend API to fetch indicator status.

### Backend
- Needs a new API endpoint (e.g., `GET /api/v1/macro/fred/indicators/status`)
- This API should:
    - List all monitored FRED tickers.
    - Query the database to find the latest date for each ticker.
    - Return a list including Ticker, Frequency, Last Updated, Description.

## 3. Implementation Steps
### Step 1: Codebase Exploration
- Identify Frontend Dashboard component.
- Identify Backend FRED configuration and data storage tables.

### Step 2: Backend Implementation
- Create a service method to gather indicator metadata and last updated dates.
- Create an API endpoint in `hobot/main.py` or a dedicated router.

### Step 3: Frontend Implementation
- Create `FredIndicatorStatusModal.tsx`.
- Add "FRED Indicators" button to the Dashboard.
- Connect the button to the modal and fetch data from the API.

## 4. Verification
- Verify the button appears on the Dashboard.
- Verify the popup opens and displays correct data.
