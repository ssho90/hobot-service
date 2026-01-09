
import logging
import sys
import os

# 프로젝트 루트 경로 설정 (hobot 패키지를 찾을 수 있도록)
current_dir = os.path.dirname(os.path.abspath(__file__))
# hobot 폴더가 있는 경로를 sys.path에 추가 (hobot-service/hobot)
# 구조상 hobot-service 가 루트고 그 안에 hobot 폴더가 소스 루트라면:
hobot_src_path = os.path.join(current_dir, "hobot")
if os.path.isdir(hobot_src_path):
    sys.path.append(hobot_src_path)
else:
    # 만약 현재 위치가 이미 hobot 폴더 상위라면
    sys.path.append(current_dir)

try:
    from service.macro_trading.ai_strategist import create_mp_analysis_prompt
except ImportError:
    # 혹시 경로가 맞지 않을 경우를 대비해 상위 경로도 추가 시도
    sys.path.append(os.path.join(current_dir, "..", "hobot"))
    from service.macro_trading.ai_strategist import create_mp_analysis_prompt

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_prompt_generation():
    # Mock Dashboard Data 생성 (Philly Fed 지표 포함)
    mock_dashboard_data = {
        "growth": {
            "philly_current": {
                "value": 12.5, 
                "status": "확장" # 양수면 확장
            },
            "philly_new_orders": 8.4,
            "philly_future": 25.0,
            
            "gdp_now": 2.8,
            
            "unemployment": {
                "current": 4.1, 
                "past_3m": 3.7, 
                "diff_trend": "상승", 
                "sams_rule": "경고등 꺼짐"
            },
            
            "nfp": {
                "value": 175,
                "consensus": 160, # 참고용
                "surprise": "상회" # 참고용
            }
        },
        "inflation": {
            "core_pce_yoy": {
                "value": 2.8, 
                "target_gap": "큼"
            },
            "cpi_yoy": {
                "value": 3.1, 
                "trend": "횡보중"
            },
            "expected_inflation": 2.3
        },
        "liquidity": {
            "yield_curve": {
                "value_bp": -30, 
                "status": "Bear Flattening - 인플레 우려 지속"
            },
            "soma": {
                "value": 7250, 
                "qt_speed": "느림"
            },
            "net_liquidity": {
                "value": 6150, 
                "status": "SOMA 감소에도 불구하고 유동성 증가 중"
            },
            "hy_spread": {
                "value": 3.45, 
                "evaluation": "Greed - 시장이 위험을 무시 중"
            }
        },
        "sentiment": {
            "vix": 13.5,
            "move": {
                "value": 110, 
                "status": "불안"
            },
            "cnn_index": {
                "value": 75, 
                "status": "Extreme Greed"
            }
        }
    }

    # FRED Signals 구조에 포함
    fred_signals = {
        "dashboard_data": mock_dashboard_data,
        # 기존 시그널 데이터 (요약 텍스트 생성을 위해 필요할 수 있음)
        "yield_curve_spread_trend": {"regime_kr": "Bear Flattening", "spread": -0.30, "yield_regime_kr": "금리 상승"},
        "real_interest_rate": 2.1,
        "taylor_rule_signal": 1.5,
        "net_liquidity": {"ma_trend": 1},
        "high_yield_spread": {"spread": 3.45, "signal_name": "Greed"}
    }
    
    # News 데이터 (비어있음)
    news = {}

    print("\n" + "="*50)
    print("AI Strategist Prompt Generation Test")
    print("="*50 + "\n")
    
    try:
        # 프롬프트 생성 함수 호출
        prompt = create_mp_analysis_prompt(fred_signals, news)
        
        print("Generated Prompt Result:")
        print("-" * 30)
        print(prompt)
        print("-" * 30)
        
        # 검증
        if "Philly Fed 제조업 지수" in prompt and "12.5" in prompt:
            print("\n✅ Philly Fed Current Activity Indicator found.")
        else:
            print("\n❌ Missing Philly Fed Current Activity Indicator.")
            
        if "Philly Fed 신규 주문" in prompt and "8.4" in prompt:
            print("✅ Philly Fed New Orders Indicator found.")
        else:
            print("❌ Missing Philly Fed New Orders Indicator.")

        if "ISM 제조업 PMI" not in prompt:
             print("✅ ISM PMI correctly removed.")
        else:
             print("❌ ISM PMI still present (Should be removed).")

    except Exception as e:
        print(f"\n❌ Error during prompt generation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_prompt_generation()
