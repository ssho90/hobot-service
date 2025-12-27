"""
사용자별 KIS API 인증 정보 조회 모듈
"""
from typing import Optional, Dict
from service.database.db import get_db_connection
from service.utils.encryption import decrypt_data
import logging


def get_user_kis_credentials(user_id: str) -> Optional[Dict[str, str]]:
    """
    사용자별 KIS API 인증 정보 조회 및 복호화
    
    Args:
        user_id: 사용자 ID
        
    Returns:
        {
            'kis_id': str,
            'account_no': str,
            'app_key': str,
            'app_secret': str
        } 또는 None (인증 정보가 없는 경우)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT kis_id, account_no, app_key_encrypted, app_secret_encrypted, is_simulation
                FROM user_kis_credentials
                WHERE user_id = %s
            """, (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # 복호화
            try:
                app_key = decrypt_data(row["app_key_encrypted"])
                app_secret = decrypt_data(row["app_secret_encrypted"])
            except Exception as e:
                logging.error(f"Error decrypting credentials for user {user_id}: {e}")
                return None
            
            return {
                'kis_id': row["kis_id"],
                'account_no': row["account_no"],
                'app_key': app_key,
                'app_secret': app_secret,
                'is_simulation': bool(row["is_simulation"])
            }
    except Exception as e:
        logging.error(f"Error getting KIS credentials for user {user_id}: {e}")
        return None

