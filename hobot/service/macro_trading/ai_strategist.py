"""
AI 전략가 모듈
정량 시그널과 정성 뉴스를 종합하여 포트폴리오 목표 비중을 결정
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


def collect_economic_news(hours: int = 24) -> List[Dict]:
    """
    최근 N시간 내의 경제 뉴스를 수집하여 반환
    
    Args:
        hours: 조회할 시간 범위 (기본값: 24시간)
    
    Returns:
        뉴스 리스트 (딕셔너리 형태)
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with get_db_connection() as conn:
            # get_db_connection()이 이미 DictCursor를 사용하므로
            # cursor()만 호출하면 됨 (dictionary=True 불필요)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    id,
                    title,
                    title_ko,
                    link,
                    country,
                    country_ko,
                    category,
                    category_ko,
                    description,
                    description_ko,
                    published_at,
                    collected_at,
                    source
                FROM economic_news
                WHERE published_at >= %s
                ORDER BY published_at DESC
            """, (cutoff_time,))
            
            rows = cursor.fetchall()
            
            # DictCursor를 사용하므로 이미 딕셔너리 형태로 반환됨
            news_list = []
            for row in rows:
                news_item = {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "title_ko": row.get("title_ko"),
                    "link": row.get("link"),
                    "country": row.get("country"),
                    "country_ko": row.get("country_ko"),
                    "category": row.get("category"),
                    "category_ko": row.get("category_ko"),
                    "description": row.get("description"),
                    "description_ko": row.get("description_ko"),
                    "published_at": row.get("published_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("published_at") else None,
                    "collected_at": row.get("collected_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("collected_at") else None,
                    "source": row.get("source")
                }
                news_list.append(news_item)
            
            logger.info(f"경제 뉴스 {len(news_list)}개 수집 완료")
            return news_list
            
    except Exception as e:
        logger.error(f"경제 뉴스 수집 실패: {e}", exc_info=True)
        raise

