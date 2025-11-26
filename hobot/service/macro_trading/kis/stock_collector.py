"""
KIS API를 사용하여 종목명-티커 매핑 데이터 수집 모듈
"""
import logging
import time
from datetime import date
from typing import List, Dict, Optional
from service.macro_trading.kis.kis_api import KISAPI
from service.macro_trading.kis.config import APP_KEY, APP_SECRET, ACCOUNT_NO
from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


def collect_stock_tickers_from_balance():
    """
    잔고 조회를 통해 보유 종목의 티커와 종목명을 수집
    
    Returns:
        int: 수집된 종목 수
    """
    try:
        api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
        balance_data = api.get_balance()
        
        if not balance_data or balance_data.get('rt_cd') != '0':
            logger.warning("잔고 조회 실패로 종목 정보를 수집할 수 없습니다.")
            return 0
        
        output1 = balance_data.get('output1', [])  # 주식 잔고
        
        stocks = []
        for item in output1:
            ticker = item.get('pdno', '').strip()
            stock_name = item.get('prdt_name', '').strip()
            
            if ticker and stock_name:
                stocks.append({
                    'ticker': ticker,
                    'stock_name': stock_name,
                    'market_type': 'J'  # 주식 시장
                })
        
        # DB에 저장
        saved_count = save_stock_tickers_to_db(stocks)
        
        logger.info(f"잔고에서 {len(stocks)}개 종목 수집, {saved_count}개 저장 완료")
        return saved_count
        
    except Exception as e:
        logger.error(f"종목 정보 수집 중 오류: {e}", exc_info=True)
        return 0


def collect_all_stock_tickers():
    """
    모든 종목 정보 수집 (현재는 잔고 조회 방식 사용)
    
    향후 KIS API의 종목 마스터 API가 있다면 사용
    
    Returns:
        int: 수집된 종목 수
    """
    try:
        logger.info("=" * 60)
        logger.info("종목명-티커 매핑 데이터 수집 시작")
        logger.info("=" * 60)
        
        # 현재는 잔고 조회를 통해 수집
        # 향후 전체 종목 마스터 데이터 수집 API 사용 가능
        saved_count = collect_stock_tickers_from_balance()
        
        logger.info("=" * 60)
        logger.info(f"종목명-티커 매핑 데이터 수집 완료: {saved_count}개")
        logger.info("=" * 60)
        
        return saved_count
        
    except Exception as e:
        logger.error(f"종목 정보 수집 중 오류: {e}", exc_info=True)
        return 0


def save_stock_tickers_to_db(stocks: List[Dict]):
    """
    종목 정보를 DB에 저장
    
    Args:
        stocks: 종목 리스트 [{"ticker": "005930", "stock_name": "삼성전자", "market_type": "J"}, ...]
        
    Returns:
        int: 저장된 종목 수
    """
    try:
        today = date.today()
        saved_count = 0
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for stock in stocks:
                ticker = stock.get('ticker', '').strip()
                stock_name = stock.get('stock_name', '').strip()
                market_type = stock.get('market_type', 'J')
                
                if not ticker or not stock_name:
                    continue
                
                try:
                    # INSERT 또는 UPDATE (티커가 같으면 업데이트)
                    cursor.execute("""
                        INSERT INTO stock_tickers 
                        (ticker, stock_name, market_type, is_active, last_updated)
                        VALUES (%s, %s, %s, TRUE, %s)
                        ON DUPLICATE KEY UPDATE
                            stock_name = VALUES(stock_name),
                            market_type = VALUES(market_type),
                            is_active = TRUE,
                            last_updated = VALUES(last_updated),
                            updated_at = CURRENT_TIMESTAMP
                    """, (ticker, stock_name, market_type, today))
                    
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"종목 저장 실패 (ticker: {ticker}): {e}")
                    continue
            
            conn.commit()
        
        return saved_count
        
    except Exception as e:
        logger.error(f"종목 정보 DB 저장 중 오류: {e}", exc_info=True)
        return 0


def search_stock_tickers(keyword: str, limit: int = 20) -> List[Dict]:
    """
    종목명으로 티커 검색
    
    Args:
        keyword: 검색 키워드 (종목명 일부)
        limit: 최대 검색 결과 수
        
    Returns:
        List[Dict]: 검색 결과 [{"ticker": "005930", "stock_name": "삼성전자"}, ...]
    """
    try:
        if not keyword or len(keyword.strip()) < 1:
            return []
        
        keyword = f"%{keyword.strip()}%"
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticker, stock_name, market_type
                FROM stock_tickers
                WHERE is_active = TRUE
                AND stock_name LIKE %s
                ORDER BY stock_name
                LIMIT %s
            """, (keyword, limit))
            
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    'ticker': row['ticker'],
                    'stock_name': row['stock_name'],
                    'market_type': row.get('market_type', 'J')
                })
            
            return results
            
    except Exception as e:
        logger.error(f"종목 검색 중 오류: {e}", exc_info=True)
        return []

