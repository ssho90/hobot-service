import logging
from datetime import datetime
from service.database.db import get_db_connection

def read_strategy(platform='upbit'):
    """플랫폼별 현재 전략을 읽어옵니다."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT strategy FROM strategies WHERE platform = %s", (platform,))
            row = cursor.fetchone()
            
            if row:
                return row['strategy']
            else:
                # 기본값으로 생성
                default_strategy = 'STRATEGY_NULL'
                write_strategy(platform, default_strategy)
                return default_strategy
    except Exception as e:
        logging.error(f"Error reading strategy: {e}")
        return 'STRATEGY_NULL'

def write_strategy(platform, strategy):
    """플랫폼별 전략을 업데이트합니다."""
    try:
        now = datetime.now()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO strategies (platform, strategy, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE strategy = %s, updated_at = %s
            """, (platform, strategy, now, strategy, now))
            conn.commit()
        
        logging.info(f"Strategy updated: {platform} = {strategy}")
        return get_all_strategies()
    except Exception as e:
        logging.error(f"Error writing strategy: {e}")
        raise

def write_strategies(strategies_dict):
    """모든 플랫폼의 전략을 한번에 업데이트합니다."""
    try:
        now = datetime.now()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            for platform, strategy in strategies_dict.items():
                cursor.execute("""
                    INSERT INTO strategies (platform, strategy, updated_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE strategy = %s, updated_at = %s
                """, (platform, strategy, now, strategy, now))
            conn.commit()
        logging.info(f"All strategies updated: {strategies_dict}")
    except Exception as e:
        logging.error(f"Error writing strategies: {e}")
        raise

def get_all_strategies():
    """모든 플랫폼의 전략을 반환합니다."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT platform, strategy FROM strategies")
            rows = cursor.fetchall()
            
            strategies = {row['platform']: row['strategy'] for row in rows}
            
            # 기본 플랫폼이 없으면 기본값으로 생성
            default_platforms = ['upbit', 'binance', 'kis']
            for platform in default_platforms:
                if platform not in strategies:
                    strategies[platform] = 'STRATEGY_NULL'
                    write_strategy(platform, 'STRATEGY_NULL')
            
            return strategies
    except Exception as e:
        logging.error(f"Error reading all strategies: {e}")
        return {
            'upbit': 'STRATEGY_NULL',
            'binance': 'STRATEGY_NULL',
            'kis': 'STRATEGY_NULL'
        }


