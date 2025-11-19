"""
데이터 수집 모듈
"""
from service.macro_trading.collectors.fred_collector import (
    FREDCollector,
    get_fred_collector,
    FRED_INDICATORS
)

__all__ = [
    'FREDCollector',
    'get_fred_collector',
    'FRED_INDICATORS'
]

