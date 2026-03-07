# Extraction Cache Migration to DB

## 1. Problem
- `NewsExtractor` saves intermediate extraction results as JSON files in `hobot/service/cache/extractions`.
- This causes a large number of files to accumulate, which is difficult to manage.

## 2. Solution
- Move the caching mechanism from the file system to the MySQL database.
- Create a new table `extraction_cache`.
- Update `NewsExtractor` to use this table.

## 3. Implementation Steps
1.  **Database Schema**: Add `extraction_cache` table to `hobot/service/database/db.py`.
    - Columns: `cache_key` (PK), `doc_id`, `data` (JSON), `created_at`, `updated_at`.
2.  **Code Update**: Modify `hobot/service/graph/news_extractor.py`.
    - Remove file operations.
    - Implement `_get_cached` and `_save_cache` using SQL queries.
3.  **Migration (Optional)**: One-time script to load existing JSON files into the DB.

## 4. Verification
- Verify that new extractions are saved to the DB.
- Verify that cached results are retrieved correctly.
