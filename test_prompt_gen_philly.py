
import logging
import sys
import os
from pprint import pprint

# 프로젝트 루트 경로 설정 (hobot 패키지를 찾을 수 있도록)
current_dir = os.path.dirname(os.path.abspath(__file__))
hobot_src_path = os.path.join(current_dir, "hobot")
if os.path.isdir(hobot_src_path):
    sys.path.append(hobot_src_path)
else:
    sys.path.append(current_dir)

from dotenv import load_dotenv
load_dotenv()  # .env 파일 로드 (FRED_API_KEY 등)

try:
    from service.macro_trading.ai_strategist import create_mp_analysis_prompt, collect_fred_signals
    from service.macro_trading.signals.quant_signals import QuantSignalCalculator
    from service.macro_trading.collectors.fred_collector import get_fred_collector
except ImportError as e:
    print(f"Import Error: {e}")
    sys.path.append(os.path.join(current_dir, "..", "hobot"))
    from service.macro_trading.ai_strategist import create_mp_analysis_prompt, collect_fred_signals
    from service.macro_trading.signals.quant_signals import QuantSignalCalculator
    from service.macro_trading.collectors.fred_collector import get_fred_collector

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_prompt_generation_real_data():
    print("\n" + "="*50)
    print("AI Strategist Prompt Generation Test (REAL DATA)")
    print("="*50 + "\n")
    
    try:
        # 1. FRED Collector & Calculator 초기화
        print("[*] Initializing QuantSignalCalculator...")
        calculator = QuantSignalCalculator()
        
        # 2. 실제 데이터 수집 (collect_fred_signals 함수 내부 로직 재현 또는 직접 호출)
        # ai_strategist.collect_fred_signals() 함수가 이미 우리가 원하는 구조를 반환하도록 수정되었음
        # 단, 내부적으로 DB 등 연결이 필요함
        
        print("[*] Collecting FRED signals and Dashboard data...")
        # collect_fred_signals는 내부적으로 calculator를 새로 생성하지만, 
        # 여기서는 테스트 목적상 명시적으로 호출 과정을 보여주거나 그냥 함수를 쓴다.
        # ai_strategist.py의 collect_fred_signals를 직접 호출해보자.
        
        fred_signals = collect_fred_signals()
        
        if not fred_signals:
            print("\n❌ Failed to collect FRED signals. Check DB connection and API Key.")
            return

        dashboard_data = fred_signals.get('dashboard_data', {})
        print(f"[*] Dashboard Data Keys: {list(dashboard_data.keys())}")
        
        # 간단히 데이터 일부 출력 확인
        if 'growth' in dashboard_data:
            print(f"[*] Philly Current: {dashboard_data['growth'].get('philly_current')}")
            print(f"[*] Philly New Orders: {dashboard_data['growth'].get('philly_new_orders')}")
        
        # 3. 프롬프트 생성
        print("[*] Generating Prompt...")
        news = {} # 뉴스는 빈 딕셔너리로 처리
        prompt = create_mp_analysis_prompt(fred_signals, news)
        
        print("\nGenerated Prompt Result:")
        print("-" * 30)
        print(prompt)
        print("-" * 30)
        
        # 4. 검증
        print("\n[Verifying Content]")
        
        # Philly Fed 데이터 확인
        if "Philly Fed 제조업 지수" in prompt:
            print("✅ Philly Fed Current Activity Indicator found in prompt.")
        else:
            print("❌ Missing Philly Fed Current Activity Indicator.")
            
        # 값 확인 (N/A가 아닌지)
        if "N/A" in prompt:
            print("⚠️ Note: Some values are 'N/A'. This might be expected if DB is empty.")
        else:
            print("✅ All values seem to be populated (No 'N/A' found).")

    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_prompt_generation_real_data()
