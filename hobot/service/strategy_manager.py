import os
import json
import logging

# 전략 파일 경로
STRATEGY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'service', 'CurrentStrategy.json')

def read_strategy(platform='upbit'):
    """플랫폼별 현재 전략을 읽어옵니다."""
    try:
        if not os.path.exists(STRATEGY_FILE_PATH):
            # 파일이 없으면 기본값으로 생성
            default_strategies = {
                'upbit': 'STRATEGY_NULL',
                'binance': 'STRATEGY_NULL',
                'kis': 'STRATEGY_NULL'
            }
            write_strategies(default_strategies)
            return default_strategies.get(platform, 'STRATEGY_NULL')
        
        with open(STRATEGY_FILE_PATH, 'r', encoding='utf-8') as f:
            strategies = json.load(f)
            return strategies.get(platform, 'STRATEGY_NULL')
    except json.JSONDecodeError:
        logging.error("Invalid JSON in strategy file, resetting to defaults")
        default_strategies = {
            'upbit': 'STRATEGY_NULL',
            'binance': 'STRATEGY_NULL',
            'kis': 'STRATEGY_NULL'
        }
        write_strategies(default_strategies)
        return default_strategies.get(platform, 'STRATEGY_NULL')
    except Exception as e:
        logging.error(f"Error reading strategy: {e}")
        return 'STRATEGY_NULL'

def write_strategy(platform, strategy):
    """플랫폼별 전략을 업데이트합니다."""
    try:
        # 기존 전략 읽기
        if os.path.exists(STRATEGY_FILE_PATH):
            with open(STRATEGY_FILE_PATH, 'r', encoding='utf-8') as f:
                strategies = json.load(f)
        else:
            strategies = {
                'upbit': 'STRATEGY_NULL',
                'binance': 'STRATEGY_NULL',
                'kis': 'STRATEGY_NULL'
            }
        
        # 특정 플랫폼의 전략만 업데이트
        strategies[platform] = strategy
        
        # 파일에 저장
        with open(STRATEGY_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(strategies, f, indent=2, ensure_ascii=False)
        
        logging.info(f"Strategy updated: {platform} = {strategy}")
        return strategies
    except Exception as e:
        logging.error(f"Error writing strategy: {e}")
        raise

def write_strategies(strategies_dict):
    """모든 플랫폼의 전략을 한번에 업데이트합니다."""
    try:
        with open(STRATEGY_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(strategies_dict, f, indent=2, ensure_ascii=False)
        logging.info(f"All strategies updated: {strategies_dict}")
    except Exception as e:
        logging.error(f"Error writing strategies: {e}")
        raise

def get_all_strategies():
    """모든 플랫폼의 전략을 반환합니다."""
    try:
        if not os.path.exists(STRATEGY_FILE_PATH):
            default_strategies = {
                'upbit': 'STRATEGY_NULL',
                'binance': 'STRATEGY_NULL',
                'kis': 'STRATEGY_NULL'
            }
            write_strategies(default_strategies)
            return default_strategies
        
        with open(STRATEGY_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logging.error("Invalid JSON in strategy file, resetting to defaults")
        default_strategies = {
            'upbit': 'STRATEGY_NULL',
            'binance': 'STRATEGY_NULL',
            'kis': 'STRATEGY_NULL'
        }
        write_strategies(default_strategies)
        return default_strategies
    except Exception as e:
        logging.error(f"Error reading all strategies: {e}")
        return {
            'upbit': 'STRATEGY_NULL',
            'binance': 'STRATEGY_NULL',
            'kis': 'STRATEGY_NULL'
        }


