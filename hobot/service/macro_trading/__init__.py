"""
거시경제 기반 자동매매 Agent 모듈
"""
# Config 모듈
from service.macro_trading.config import (
    get_config,
    reload_config,
    get_config_loader,
    MacroTradingConfig
)

# Data Collectors 모듈
from service.macro_trading.collectors import (
    FREDCollector,
    get_fred_collector,
    FRED_INDICATORS
)

# Signals 모듈
from service.macro_trading.signals import (
    QuantSignalCalculator
)

__all__ = [
    # Config
    'get_config',
    'reload_config',
    'get_config_loader',
    'MacroTradingConfig',
    # FRED
    'FREDCollector',
    'get_fred_collector',
    'FRED_INDICATORS',
    # Quant Signals
    'QuantSignalCalculator'
]

