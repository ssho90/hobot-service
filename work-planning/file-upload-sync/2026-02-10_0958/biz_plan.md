# File Upload Sync Improvement Plan

## 1. Goal
- Enable other users to view content (text/images) pasted in the file upload screen immediately.
- Currently, pasted content is only visible locally (likely using `URL.createObjectURL` or base64 without server upload).

## 2. Analysis
- **Current State**: Identify the component handling paste events. Check how the preview is generated.
- **Problem**: The preview is local-only.
- **Solution**:
    - When content is pasted, upload it to the server immediately.
    - initial implementation will likely return a server URL.
    - Use this URL for the preview instead of the local blob/base64.
    - Broadcast/save this state so other users can see it (if real-time) or just ensure it's saved when the user submits, but the request says "immediately visible".

## 3. Implementation Steps
1.  **Locate Code**: Find the file upload/paste component in `hobot-ui-v2`.
2.  **Analyze Logic**: Understand `onPaste` handler and state management.
3.  **Backend Check**: Verify if there's an API to upload files/images.
4.  **Frontend Modification**:
    - Modify `onPaste` to trigger an upload.
    - Replace local preview with server URL.
    - Ensure the form data includes the server path/URL.

## 4. Verification
- Verify that pasted images are uploaded.
- Verify that the image URL is accessible.
