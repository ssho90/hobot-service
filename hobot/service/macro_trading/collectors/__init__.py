"""
데이터 수집 모듈
"""
from service.macro_trading.collectors.fred_collector import (
    FREDCollector,
    get_fred_collector,
    FRED_INDICATORS
)
from service.macro_trading.collectors.news_collector import (
    NewsCollector,
    get_news_collector,
    NewsCollectorError
)

__all__ = [
    'FREDCollector',
    'get_fred_collector',
    'FRED_INDICATORS',
    'NewsCollector',
    'get_news_collector',
    'NewsCollectorError'
]

