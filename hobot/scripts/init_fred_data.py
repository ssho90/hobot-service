
import logging
import time
from datetime import date
import argparse
import sys
import os

# 프로젝트 루트 경로를 PYTHONPATH에 추가하여 모듈 import 가능하게 함
current_dir = os.path.dirname(os.path.abspath(__file__))
hobot_root = os.path.dirname(current_dir) # .../hobot
sys.path.append(hobot_root)

from service.macro_trading.collectors.fred_collector import FREDCollector, FRED_INDICATORS

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def init_fred_data(days=365*3):
    """
    FRED 데이터를 초기화합니다.
    
    Args:
        days: 수집할 기간 (일 단위, 기본값: 3년)
    """
    try:
        collector = FREDCollector()
        
        logger.info(f"FRED 데이터 초기화 시작 (수집 기간: 최근 {days}일)")
        
        # 수집할 신규 지표 목록 (ISM -> Philly Fed 교체)
        target_indicators = [
            "GACDFSA066MSFRBPHI", "NOCDFSA066MSFRBPHI", "GAFDFSA066MSFRBPHI", 
            "GDPNOW", "PCEPILFE", "T10YIE", "VIXCLS", "STLFSI4"
        ]
        
        # 기존 주요 지표들도 함께 업데이트
        target_indicators.extend([
            "DGS10", "DGS2", "FEDFUNDS", "CPIAUCSL", "PCEPI", "GDP", "UNRATE", "PAYEMS",
            "WALCL", "WTREGEN", "RRPONTSYD", "BAMLH0A0HYM2", "DFII10"
        ])
        
        # 중복 제거
        target_indicators = list(set(target_indicators))
        
        for indicator in target_indicators:
            if indicator not in FRED_INDICATORS:
                logger.warning(f"지표 {indicator}는 FRED_INDICATORS에 정의되지 않았습니다. 건너뜁니다.")
                continue
                
            logger.info(f"지표 수집 중: {indicator} ({FRED_INDICATORS[indicator]['name']})")
            try:
                # 데이터 수집 및 저장
                data = collector.fetch_indicator(indicator, use_rate_limit=True)
                
                if not data.empty:
                    # DGS10, DGS2는 보간 적용
                    fill_missing = indicator in ["DGS10", "DGS2"]
                    
                    saved_count = collector.save_to_db(
                        indicator,
                        data,
                        fill_missing=fill_missing
                    )
                    logger.info(f"  -> 저장됨: {saved_count}건")
                else:
                    logger.warning(f"  -> 데이터 없음")
                
                # Rate Limit 고려한 딜레이
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"  -> 실패: {e}")
                
        logger.info("FRED 데이터 초기화 완료")
        
    except Exception as e:
        logger.error(f"초기화 중 오류 발생: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FRED 데이터 초기 적재 스크립트")
    parser.add_argument("--days", type=int, default=365*3, help="수집할 기간 (일 단위)")
    args = parser.parse_args()
    
    init_fred_data(args.days)
