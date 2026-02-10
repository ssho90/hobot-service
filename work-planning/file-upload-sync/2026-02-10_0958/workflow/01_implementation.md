# File Upload Sync Implementation

## 1. Analysis
- Identified that `AdminFileUpload.tsx` uses `URL.createObjectURL` for local preview, which is session-bound.
- To share the preview, we need to upload the file to the server and share the new URL.

## 2. Backend Changes (`hobot/main.py`)
- Created `SharedViewRequest` Pydantic model.
- Added `shared_view_state` global variable (in-memory).
- Added endpoints:
    - `GET /api/admin/shared-view`: Retrieve current shared content.
    - `POST /api/admin/shared-view`: Update shared content.

## 3. Frontend Changes (`AdminFileUpload.tsx`)
- Modified `handleUpload` to return uploaded file data (ID/URL).
- Added `fetchSharedView` function to poll the shared state via `/api/admin/shared-view`.
- Added `useEffect` with interval (2s) to keep the view synced.
- Updated `handleDisplayContent`:
    - For images: Upload file -> Get URL -> Post to `/api/admin/shared-view`.
    - For text: Post directly to `/api/admin/shared-view`.

## 4. Result
- Users can now paste an image/text, click "Display", and it will be visible to all users currently viewing the page (synced every 2 seconds).
