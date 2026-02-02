import sys
import os
from dotenv import load_dotenv
import pymysql

# Add parent directory to path to allow importing service modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv(override=True)

from service.database.db import get_db_connection

def apply_migration():
    print("Starting migration...")
    
    queries = [
        # Check if column exists before adding to avoid error on re-run
        """
        SELECT count(*) as cnt 
        FROM information_schema.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE() 
        AND TABLE_NAME = 'account_snapshots' 
        AND COLUMN_NAME = 'user_id'
        """,
        
        # Add column if not exists
        """
        SET @exist := (SELECT count(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'account_snapshots' AND COLUMN_NAME = 'user_id');
        SET @sql := IF(@exist = 0, 'ALTER TABLE account_snapshots ADD COLUMN user_id VARCHAR(50) NOT NULL DEFAULT "ssho" AFTER id', 'SELECT "Column user_id already exists"');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        """,
        
        # Update existing records
        "UPDATE account_snapshots SET user_id = 'ssho' WHERE user_id IS NULL",
        
        # Drop old index if exists
        """
        SET @exist := (SELECT count(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'account_snapshots' AND INDEX_NAME = 'unique_date');
        SET @sql := IF(@exist > 0, 'ALTER TABLE account_snapshots DROP INDEX unique_date', 'SELECT "Index unique_date does not exist"');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        """,
        
        # Add new unique key if not exists
        """
        SET @exist := (SELECT count(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'account_snapshots' AND INDEX_NAME = 'unique_user_date');
        SET @sql := IF(@exist = 0, 'ALTER TABLE account_snapshots ADD UNIQUE KEY unique_user_date (user_id, snapshot_date)', 'SELECT "Index unique_user_date already exists"');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        """,
        
        # Add new normal index if not exists
        """
        SET @exist := (SELECT count(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'account_snapshots' AND INDEX_NAME = 'idx_user_date');
        SET @sql := IF(@exist = 0, 'ALTER TABLE account_snapshots ADD INDEX idx_user_date (user_id, snapshot_date)', 'SELECT "Index idx_user_date already exists"');
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
        """
    ]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for query in queries:
                # Skip the check query, it's just for logic flow but actually using PREPARE statements is safer for idempotency
                # But PyMySQL doesn't support multiple statements well in one execute unless configured.
                # Simplified approach: Try/Except for DDLs or use procedure-like blocks.
                # Since we want to be safe, let's just try running DDLs and catch errors if they exist, 
                # OR better, run them one by one.
                pass
            
            # Let's run simpler direct DDLs and catch operational errors if they fail (e.g. duplicate column)
            # 1. Add Column
            try:
                print("1. Adding user_id column...")
                cursor.execute("ALTER TABLE account_snapshots ADD COLUMN user_id VARCHAR(50) NOT NULL DEFAULT 'ssho' AFTER id")
                print("   -> Done.")
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1060: # Duplicate column name
                    print("   -> Column user_id already exists. Skipping.")
                else:
                    raise e
            
            # 2. Update Data
            print("2. Updating user_id data...")
            cursor.execute("UPDATE account_snapshots SET user_id = 'ssho' WHERE user_id IS NULL")
            print("   -> Done.")
            
            # 3. Drop old index
            try:
                print("3. Dropping unique_date index...")
                cursor.execute("ALTER TABLE account_snapshots DROP INDEX unique_date")
                print("   -> Done.")
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1091: # Can't DROP 'unique_date'; check that column/key exists
                    print("   -> Index unique_date does not exist. Skipping.")
                else:
                    # In some mysql versions/setups, checking existence is better.
                    print(f"   -> Warning: {e}")

            # 4. Add new unique key
            try:
                print("4. Adding unique_user_date index...")
                cursor.execute("ALTER TABLE account_snapshots ADD UNIQUE KEY unique_user_date (user_id, snapshot_date)")
                print("   -> Done.")
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1061: # Duplicate key name
                    print("   -> Index unique_user_date already exists. Skipping.")
                else:
                    raise e

            # 5. Add new index
            try:
                print("5. Adding idx_user_date index...")
                cursor.execute("ALTER TABLE account_snapshots ADD INDEX idx_user_date (user_id, snapshot_date)")
                print("   -> Done.")
            except pymysql.err.OperationalError as e:
                if e.args[0] == 1061: # Duplicate key name
                    print("   -> Index idx_user_date already exists. Skipping.")
                else:
                    raise e

            conn.commit()
            print("Migration completed successfully.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    apply_migration()
