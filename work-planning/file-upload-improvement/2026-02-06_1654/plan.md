# File Upload & Management Screen Improvement

## User Requirements
1.  **Paste Functionality Improvement**: Change the behavior of the "Upload Pasted Content" button. Instead of saving the pasted text/image as a file to the server, display it prominently on the screen (showing only the most recent content).
2.  **Drag and Drop Improvement**: Enable multiple file upload support for drag-and-drop and file selection.

## Implementation Plan

### 1. Multi-File Upload Support
*   **Target File**: `src/components/admin/AdminFileUpload.tsx`
*   **Changes**:
    *   Add `multiple` attribute to the hidden file input.
    *   Update `handleFileChange`: Iterate over `e.target.files` and proceed with upload for each.
    *   Update `handleDrop`: Iterate over `e.dataTransfer.files` and proceed with upload for each.
    *   Refine `handleUpload` usage:
        *   Currently `handleUpload` is async and updates state.
        *   Will use a loop to process files. Ideally sequential to avoid overwhelming the server or UI state, though parallel is also possible. Given the UI simple state (`uploadMessage`), sequential might be cleaner for feedback messages, or just fire all and show "Uploading...".
        *   I will implement a simple loop.

### 2. Paste Content Display (Preview Mode)
*   **Target File**: `src/components/admin/AdminFileUpload.tsx`
*   **Changes**:
    *   Add state `viewContent` to store the content to be displayed `{ type: 'text' | 'image', content: string, timestamp: string }`.
    *   Modify `handleContentUpload` (rename to `handleShowContent` or similar):
        *   Remove the logic that calls `handleUpload` (the server upload).
        *   Instead, update `viewContent` state with the current input/pasted file.
        *   If it's an image, create an object URL.
    *   Add a Display Section:
        *   Where: Below the Paste Area (Left Column).
        *   What: Shows the Text or Image stored in `viewContent`.
        *   Style: A clean box showing the content.

### 3. Cleanup
*   Ensure object URLs are revoked when no longer needed to prevent memory leaks.
