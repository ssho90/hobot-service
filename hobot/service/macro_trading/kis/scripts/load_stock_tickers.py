#!/usr/bin/env python3
"""
종목명-티커 초기 적재 스크립트

사용법:
    python load_stock_tickers.py [옵션]

옵션:
    --from-balance    : 잔고 조회를 통해 보유 종목만 수집 (기본값)
    --from-file FILE  : CSV 파일에서 종목 정보 읽기
    --manual          : 수동으로 종목 정보 입력
    --all             : 전체 종목 수집 시도 (KIS API 사용)
    --dry-run         : 실제 DB 저장 없이 테스트만 실행
"""
import sys
import os
import argparse
import csv
import logging
from datetime import date
from typing import List, Dict

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../'))

from dotenv import load_dotenv
load_dotenv(override=True)

from service.macro_trading.kis.kis_api import KISAPI
from service.macro_trading.kis.config import APP_KEY, APP_SECRET, ACCOUNT_NO
from service.macro_trading.kis.stock_collector import save_stock_tickers_to_db, search_stock_tickers
from service.database.db import get_db_connection

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_from_balance():
    """잔고 조회를 통해 보유 종목 정보 수집"""
    logger.info("=" * 60)
    logger.info("잔고 조회를 통한 종목 정보 수집 시작")
    logger.info("=" * 60)
    
    try:
        api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
        balance_data = api.get_balance()
        
        if not balance_data or balance_data.get('rt_cd') != '0':
            logger.error("잔고 조회 실패")
            return 0
        
        output1 = balance_data.get('output1', [])
        
        stocks = []
        for item in output1:
            ticker = item.get('pdno', '').strip()
            stock_name = item.get('prdt_name', '').strip()
            
            if ticker and stock_name:
                stocks.append({
                    'ticker': ticker,
                    'stock_name': stock_name,
                    'market_type': 'J'
                })
                logger.info(f"  - {stock_name} ({ticker})")
        
        logger.info(f"\n총 {len(stocks)}개 종목 수집 완료")
        return stocks
        
    except Exception as e:
        logger.error(f"잔고 조회 중 오류: {e}", exc_info=True)
        return []


def load_from_file(file_path: str) -> List[Dict]:
    """CSV 파일에서 종목 정보 읽기
    
    CSV 형식:
        ticker,stock_name,market_type
        005930,삼성전자,J
        360750,TIGER 미국 S&P500,J
    """
    logger.info("=" * 60)
    logger.info(f"CSV 파일에서 종목 정보 읽기: {file_path}")
    logger.info("=" * 60)
    
    if not os.path.exists(file_path):
        logger.error(f"파일을 찾을 수 없습니다: {file_path}")
        return []
    
    stocks = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ticker = row.get('ticker', '').strip()
                stock_name = row.get('stock_name', '').strip()
                market_type = row.get('market_type', 'J').strip()
                
                if ticker and stock_name:
                    stocks.append({
                        'ticker': ticker,
                        'stock_name': stock_name,
                        'market_type': market_type
                    })
                    logger.info(f"  - {stock_name} ({ticker})")
        
        logger.info(f"\n총 {len(stocks)}개 종목 읽기 완료")
        return stocks
        
    except Exception as e:
        logger.error(f"CSV 파일 읽기 중 오류: {e}", exc_info=True)
        return []


def load_manual():
    """수동으로 종목 정보 입력"""
    logger.info("=" * 60)
    logger.info("수동 종목 정보 입력")
    logger.info("=" * 60)
    logger.info("종목 정보를 입력하세요. (종료: 빈 줄 입력)")
    logger.info("형식: 티커,종목명,시장구분(선택, 기본값:J)")
    logger.info("예시: 005930,삼성전자,J")
    logger.info("-" * 60)
    
    stocks = []
    while True:
        try:
            line = input("> ").strip()
            if not line:
                break
            
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 2:
                logger.warning("형식이 올바르지 않습니다. 다시 입력하세요.")
                continue
            
            ticker = parts[0]
            stock_name = parts[1]
            market_type = parts[2] if len(parts) > 2 else 'J'
            
            stocks.append({
                'ticker': ticker,
                'stock_name': stock_name,
                'market_type': market_type
            })
            logger.info(f"  추가됨: {stock_name} ({ticker})")
            
        except KeyboardInterrupt:
            logger.info("\n입력 중단")
            break
        except Exception as e:
            logger.error(f"입력 처리 중 오류: {e}")
            continue
    
    logger.info(f"\n총 {len(stocks)}개 종목 입력 완료")
    return stocks


def load_common_stocks():
    """일반적인 ETF 및 주요 종목 목록 반환"""
    logger.info("=" * 60)
    logger.info("일반적인 ETF 및 주요 종목 목록 사용")
    logger.info("=" * 60)
    
    # 주요 ETF 및 종목 목록
    common_stocks = [
        # 주식 ETF
        {'ticker': '360750', 'stock_name': 'TIGER 미국 S&P500', 'market_type': 'J'},
        {'ticker': '133690', 'stock_name': 'TIGER 미국나스닥100', 'market_type': 'J'},
        {'ticker': '069500', 'stock_name': 'KODEX 200', 'market_type': 'J'},
        {'ticker': '114800', 'stock_name': 'KODEX 인버스', 'market_type': 'J'},
        {'ticker': '251350', 'stock_name': 'KODEX 코스닥150', 'market_type': 'J'},
        
        # 대체투자 ETF
        {'ticker': '132030', 'stock_name': 'KODEX 골드선물(H)', 'market_type': 'J'},
        {'ticker': '138230', 'stock_name': 'KODEX 미국달러선물', 'market_type': 'J'},
        {'ticker': '114800', 'stock_name': 'KODEX 인버스', 'market_type': 'J'},
        
        # 현금/채권 ETF
        {'ticker': '130730', 'stock_name': 'TIGER CD금리투자KIS', 'market_type': 'J'},
        {'ticker': '114260', 'stock_name': 'KODEX KOFR금리액티브', 'market_type': 'J'},
        {'ticker': '148070', 'stock_name': 'KODEX 국고채3년', 'market_type': 'J'},
        {'ticker': '114800', 'stock_name': 'KODEX 국고채10년', 'market_type': 'J'},
        
        # 주요 주식
        {'ticker': '005930', 'stock_name': '삼성전자', 'market_type': 'J'},
        {'ticker': '000660', 'stock_name': 'SK하이닉스', 'market_type': 'J'},
        {'ticker': '035420', 'stock_name': 'NAVER', 'market_type': 'J'},
        {'ticker': '035720', 'stock_name': '카카오', 'market_type': 'J'},
        {'ticker': '005380', 'stock_name': '현대차', 'market_type': 'J'},
        {'ticker': '051910', 'stock_name': 'LG화학', 'market_type': 'J'},
        {'ticker': '006400', 'stock_name': '삼성SDI', 'market_type': 'J'},
        {'ticker': '028260', 'stock_name': '삼성물산', 'market_type': 'J'},
        {'ticker': '207940', 'stock_name': '삼성바이오로직스', 'market_type': 'J'},
        {'ticker': '068270', 'stock_name': '셀트리온', 'market_type': 'J'},
    ]
    
    logger.info(f"총 {len(common_stocks)}개 일반 종목 목록 생성")
    for stock in common_stocks:
        logger.info(f"  - {stock['stock_name']} ({stock['ticker']})")
    
    return common_stocks


def save_to_db(stocks: List[Dict], dry_run: bool = False):
    """종목 정보를 DB에 저장"""
    if dry_run:
        logger.info("=" * 60)
        logger.info("[DRY RUN] 실제 DB 저장 없이 테스트만 실행")
        logger.info("=" * 60)
        for stock in stocks:
            logger.info(f"  저장 예정: {stock['stock_name']} ({stock['ticker']})")
        logger.info(f"\n총 {len(stocks)}개 종목 저장 예정")
        return len(stocks)
    
    logger.info("=" * 60)
    logger.info("DB 저장 시작")
    logger.info("=" * 60)
    
    saved_count = save_stock_tickers_to_db(stocks)
    
    logger.info("=" * 60)
    logger.info(f"DB 저장 완료: {saved_count}개 종목 저장됨")
    logger.info("=" * 60)
    
    return saved_count


def main():
    parser = argparse.ArgumentParser(
        description='종목명-티커 초기 적재 스크립트',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 잔고 조회를 통해 수집
  python load_stock_tickers.py --from-balance
  
  # CSV 파일에서 읽기
  python load_stock_tickers.py --from-file stocks.csv
  
  # 일반적인 종목 목록 사용
  python load_stock_tickers.py --common
  
  # 수동 입력
  python load_stock_tickers.py --manual
  
  # 테스트 실행 (DB 저장 안 함)
  python load_stock_tickers.py --common --dry-run
        """
    )
    
    parser.add_argument(
        '--from-balance',
        action='store_true',
        help='잔고 조회를 통해 보유 종목만 수집 (기본값)'
    )
    parser.add_argument(
        '--from-file',
        type=str,
        metavar='FILE',
        help='CSV 파일에서 종목 정보 읽기'
    )
    parser.add_argument(
        '--manual',
        action='store_true',
        help='수동으로 종목 정보 입력'
    )
    parser.add_argument(
        '--common',
        action='store_true',
        help='일반적인 ETF 및 주요 종목 목록 사용'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='실제 DB 저장 없이 테스트만 실행'
    )
    
    args = parser.parse_args()
    
    # 옵션이 없으면 기본값으로 잔고 조회
    if not any([args.from_balance, args.from_file, args.manual, args.common]):
        args.from_balance = True
    
    stocks = []
    
    try:
        if args.from_file:
            stocks = load_from_file(args.from_file)
        elif args.manual:
            stocks = load_manual()
        elif args.common:
            stocks = load_common_stocks()
        elif args.from_balance:
            stocks = load_from_balance()
        
        if not stocks:
            logger.warning("수집된 종목이 없습니다.")
            return
        
        # DB 저장
        saved_count = save_to_db(stocks, dry_run=args.dry_run)
        
        if not args.dry_run:
            logger.info("=" * 60)
            logger.info("초기 적재 완료!")
            logger.info(f"총 {saved_count}개 종목이 DB에 저장되었습니다.")
            logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("\n작업이 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

