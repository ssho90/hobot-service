import os
import sys
import json
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.database.db import get_db_connection, ensure_database_initialized
from service.graph.news_extractor import get_news_extractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_cache_files_to_db():
    extractor = get_news_extractor()
    cache_dir = extractor.cache_dir
    
    if not os.path.exists(cache_dir):
        logger.info(f"Cache directory {cache_dir} does not exist.")
        return

    files = [f for f in os.listdir(cache_dir) if f.endswith('.json')]
    logger.info(f"Found {len(files)} cache files in {cache_dir}")

    success_count = 0
    fail_count = 0
    
    # DB 초기화 확인
    try:
        ensure_database_initialized()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return

    for filename in files:
        file_path = os.path.join(cache_dir, filename)
        cache_key = filename.replace('.json', '')
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            doc_id = data.get('doc_id')
            if not doc_id:
                logger.warning(f"Skipping {filename}: No doc_id found in JSON")
                continue
                
            # DB 저장
            extractor._save_to_db(cache_key, doc_id, data)
            success_count += 1
            
            # 선택적: 파일 삭제
            # os.remove(file_path)
            
        except Exception as e:
            logger.error(f"Failed to migrate {filename}: {e}")
            fail_count += 1
            
    logger.info(f"Migration completed. Success: {success_count}, Failed: {fail_count}")

if __name__ == "__main__":
    migrate_cache_files_to_db()
