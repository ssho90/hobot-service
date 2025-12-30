from typing import Dict, Any
from service.database.db import get_db_connection
import logging

logger = logging.getLogger(__name__)

def get_rebalancing_config() -> Dict[str, float]:
    """
    DB에서 리밸런싱 설정(임계값 등)을 조회
    
    Returns:
        Dict: {"mp": 3.0, "sub_mp": 5.0, "is_active": True}
    """
    default_config = {
        "mp": 3.0, 
        "sub_mp": 5.0,
        "is_active": True
    }
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 가장 최근에 업데이트된 활성화 설정 조회? 
            # 아니면 단일 행으로 관리? 보통 config 테이블은 단일 행 또는 키-값 구조.
            # 스키마(rebalancing_config)를 보면 id가 있고 다중 행 가능 구조지만,
            # 여기서는 편의상 하나만 있거나 제일 최근 것을 가져온다고 가정.
            # 하지만 스키마 정의상 'id'가 hash 기반이고, 보통 관리자 화면에서 하나만 수정한다면
            # LIMIT 1로 가져오는게 안전.
            
            cursor.execute("""
                SELECT mp_threshold_percent, sub_mp_threshold_percent, is_active
                FROM rebalancing_config
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            
            if row:
                return {
                    "mp": float(row.get('mp_threshold_percent', 3.0)),
                    "sub_mp": float(row.get('sub_mp_threshold_percent', 5.0)),
                    "is_active": bool(row.get('is_active', True))
                }
            else:
                logger.info("No rebalancing config found in DB, using defaults.")
                return default_config
                
    except Exception as e:
        logger.error(f"Error fetching rebalancing config: {e}")
        return default_config
