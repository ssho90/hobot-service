
import logging
import sys
import os

# Set up path
sys.path.append("/Users/ssho/project/hobot-service/hobot")

from service.macro_trading.ai_strategist import create_mp_analysis_prompt

# Mock data for testing since DB might be empty or restricted
mock_dashboard_data = {
    "growth": {
        "philly_current": {"value": 12.5, "status": "확장"},
        "philly_new_orders": 8.4,
        "philly_future": 25.0,
        "gdp_now": 2.5,
        "unemployment": {"current": 4.1, "past_3m": 3.7, "diff_trend": "상승", "sams_rule": "경고등 꺼짐"},
        "nfp": {"value": 150}
    },
    "inflation": {
        "core_pce_yoy": {"value": 2.8, "target_gap": "큼"},
        "cpi_yoy": {"value": 3.1, "trend": "횡보중"},
        "expected_inflation": 2.3
    },
    "liquidity": {
        "yield_curve": {"value_bp": -30, "status": "Bear Flattening"},
        "soma": {"value": 7500, "qt_speed": "느림"},
        "net_liquidity": {"value": 6200, "status": "SOMA 감소에도 불구하고 유동성 증가 중"},
        "hy_spread": {"value": 3.2, "evaluation": "Greed - 시장이 위험을 무시 중"}
    },
    "sentiment": {
        "vix": 13.5,
        "move": {"value": 110, "status": "불안"},
        "cnn_index": {"value": 75, "status": "Extreme Greed"}
    }
}

fred_signals = {"dashboard_data": mock_dashboard_data}
news = {}

try:
    print("=== Generating Prompt with Mock Data ===")
    prompt = create_mp_analysis_prompt(fred_signals, news)
    print(prompt)
except Exception as e:
    print(f"Error: {e}")
