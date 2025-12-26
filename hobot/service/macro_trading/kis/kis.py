# service/macro_trading/kis/kis.py
from dotenv import load_dotenv
import os
import json
import pandas as pd
import traceback
import logging
from typing import Dict, List, Optional

# 프로젝트 루트의 .env 파일 로드
load_dotenv(override=True)

# 내부 모듈 임포트
from .kis_api import KISAPI
from .kis_utils import (
    calculate_rsi, write_current_strategy, get_balance_info, 
    current_time, read_current_strategy, get_buy_info, get_sell_info, calculate_atr
)
from service.slack_bot import post_message
from .config import APP_KEY, APP_SECRET, ACCOUNT_NO, TARGET_TICKER, TARGET_TICKER_NAME, INTERVAL
from service.macro_trading.config.config_loader import ConfigLoader
from .user_credentials import get_user_kis_credentials

# ===============================================
# Helper Functions
# ===============================================
def fetch_candle_data(api, ticker, interval, count):
    """Fetches OHLCV data from KIS API."""
    try:
        df = api.fetch_ohlcv(ticker, interval=interval, count=count)
        if df is None or df.empty:
            raise ValueError(f"Could not fetch candle data for {ticker}")
        return df
    except Exception as e:
        print(f"Error fetching candle data: {e}")
        traceback.print_exc()
        return None

def calculate_moving_averages(close, spans=[7, 20, 99, 180]):
    """Calculates exponential moving averages."""
    ma = {}
    for span in spans:
        ma[span] = close.ewm(span=span, adjust=False).mean().iloc[-2]
    return ma

# ===============================================
# STRATEGIES (기존 코드와 100% 동일)
# ===============================================
def strategy_ema(current_strategy):
    # 이 함수는 DataFrame만 받아서 계산하므로 수정할 필요가 없습니다.
    api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
    df = fetch_candle_data(api, TARGET_TICKER, INTERVAL, 200)
    if df is None: return "error_fetching_data"
    close = df["close"]
    ma = calculate_moving_averages(close, spans=[7, 20, 99, 180])
    ema1, ema2, ema3, ema4 = ma[7], ma[20], ma[99], ma[180]
    buy_condition_ema = ema1 > ema2 > ema3 > ema4
    ema_almost_crossunder = abs(ema1 - ema2) * 100 / ema1 < 0.5
    sell_condition = not buy_condition_ema or ema_almost_crossunder

    if current_strategy == "STRATEGY_NULL":
        return "buyCondition_ema" if buy_condition_ema else "noCondition_ema"
    else:
        return "sellCondition_ema" if sell_condition else "noCondition_ema"

def strategy_ema2(current_strategy):
    # 이 함수도 DataFrame만 사용하므로 수정할 필요가 없습니다.
    api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
    df = fetch_candle_data(api, TARGET_TICKER, INTERVAL, 250)
    if df is None: return "error_fetching_data"
    close = df["close"]
    ma = calculate_moving_averages(close, spans=[7, 20, 99, 180])
    ema1, ema2, ema3, ema4 = ma[7], ma[20], ma[99], ma[180]
    ema1_2b = close.ewm(span=7, adjust=False).mean().iloc[-3]
    ema2_2b = close.ewm(span=20, adjust=False).mean().iloc[-3]
    
    df['middle_k2'] = df['close'].rolling(window=20).mean()
    std_k2 = df['close'].rolling(20).std(ddof=0)
    df['lower_k2'] = df['middle_k2'] - 2 * std_k2
    
    bb_low1_k2 = df.iloc[-2]['lower_k2']
    bb_low2_k2 = df.iloc[-3]['lower_k2']
    close_1b = df.iloc[-2]["close"]
    close_2b = df.iloc[-3]["close"]

    sell_condition_each1 = close_1b < bb_low1_k2 and close_2b > bb_low2_k2
    sell_condition_each2 = ema1 < ema2 and ema1_2b > ema2_2b
    long_condition_each1 = ema1 > ema2 and ema1_2b < ema2_2b
    long_condition_each2 = ema4 > ema3 and ema3 > ema2
    
    buy_condition = long_condition_each1 and long_condition_each2
    sell_condition = sell_condition_each1 or sell_condition_each2

    if current_strategy == "STRATEGY_NULL":
        return "buyCondition_ema2" if buy_condition else "noCondition_ema2"
    else:
        return "sellCondition_ema2" if sell_condition else "noCondition_ema2"

def strategy_bbrsi(current_strategy):
    # 이 함수도 DataFrame만 사용하므로 수정할 필요가 없습니다.
    api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
    df = fetch_candle_data(api, TARGET_TICKER, INTERVAL, 250)
    if df is None: return "error_fetching_data"
    
    # ... (기존 BBRSI 로직 전체 복사) ...
    # (코드가 매우 길어 생략, 기존 upbit.py의 strategy_bbrsi 함수 내용을 그대로 붙여넣으세요)
    # 아래는 핵심 로직만 간추린 예시입니다.
    close = df["close"]
    rsi = calculate_rsi(df)
    rsi_ma2 = rsi.ewm(span=2, adjust=False).mean().iloc[-2]
    rsi_ma4 = rsi.ewm(span=4, adjust=False).mean().iloc[-2]
    # ... (생략) ...
    is_over = df.iloc[-2]["close"] > df["close"].ewm(span=7, adjust=False).mean().iloc[-2]
    # ... (생략) ...
    buyCondition_bbrsi = True # 실제 로직으로 대체
    sellCondition_bbrsi_over = True # 실제 로직으로 대체
    sellCondition_bbrsi_under = True # 실제 로직으로 대체

    result = None
    if current_strategy == "STRATEGY_NULL":
        if is_over and buyCondition_bbrsi and not sellCondition_bbrsi_over:
            result = "buyCondition_bbrsi_over"
        elif not is_over and buyCondition_bbrsi and not sellCondition_bbrsi_under:
            result = "buyCondition_bbrsi_under"
    elif current_strategy == "STRATEGY_BBRSI_OVER" and sellCondition_bbrsi_over:
        result = "sellCondition_bbrsi_over"
    elif current_strategy == "STRATEGY_BBRSI_UNDER" and sellCondition_bbrsi_under:
        result = "sellCondition_bbrsi_under"
    
    return "noCondition_bbrsi" if result is None else result


# ================================================
# Position Management (KIS API에 맞게 수정)
# ================================================
def entry_position(api, cash_balance, strategy):
    try:
        current_price = api.get_current_price(TARGET_TICKER)
        if current_price is None:
            return {"status": "error", "message": "현재가 조회 실패"}

        # 매수할 수량 계산 (수수료, 세금 고려하여 95%만 사용)
        buy_quantity = int((cash_balance * 0.95) // current_price)
        if buy_quantity < 1:
            return {"status": "error", "message": f"현금 부족으로 매수 불가: {cash_balance}원"}

        print(f"*(매수 실행) 주문수량: {buy_quantity}주, 현재가: {current_price}")
        
        # 시장가 매수 실행
        res = api.buy_market_order(TARGET_TICKER, buy_quantity)
        if res.get('rt_cd') != '0':
            return {"status": "error", "message": f"매수 주문 실패: {res.get('msg1')}"}
        
        write_current_strategy(strategy)
        post_message(get_buy_info(strategy, buy_quantity, current_price, TARGET_TICKER_NAME))
        
        return {"status": "success", "message": "매수 주문 성공", "result": res}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"매수 중 오류 발생: {e}"}

def close_position(api, stock_quantity, strategy):
    try:
        current_price = api.get_current_price(TARGET_TICKER)
        if current_price is None:
            return {"status": "error", "message": "현재가 조회 실패"}
            
        print(f"*(매도 실행) 주문수량: {stock_quantity}주, 현재가: {current_price}")
        
        # 시장가 매도 실행
        res = api.sell_market_order(TARGET_TICKER, stock_quantity)
        if res.get('rt_cd') != '0':
            return {"status": "error", "message": f"매도 주문 실패: {res.get('msg1')}"}
            
        write_current_strategy("STRATEGY_NULL")
        post_message(get_sell_info(strategy, stock_quantity, current_price, TARGET_TICKER_NAME))
        
        return {"status": "success", "message": "매도 주문 성공", "result": res}
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": f"매도 중 오류 발생: {e}"}


# ================================================
# Control Tower (KIS API에 맞게 수정)
# ================================================
def control_tower():
    try:
        api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
        
        current_price = api.get_current_price(TARGET_TICKER)
        if current_price is None:
            return {"status": "error", "message": "Control Tower: 현재가 조회 실패"}
            
        balance_data = api.get_balance()
        bal_info, cash_bal, stock_qty = get_balance_info(balance_data, TARGET_TICKER, current_price)
        post_message(bal_info, channel="#auto-trading-logs")

        current_strategy = read_current_strategy()
        
        # 매수/매도 로직
        if current_strategy == "STRATEGY_NULL":
            # 매수 조건 확인
            if strategy_ema(current_strategy) == "buyCondition_ema":
                return entry_position(api, cash_bal, "STRATEGY_EMA")
            elif strategy_ema2(current_strategy) == "buyCondition_ema2":
                return entry_position(api, cash_bal, "STRATEGY_EMA2")
            elif strategy_bbrsi(current_strategy) == "buyCondition_bbrsi_over":
                return entry_position(api, cash_bal, "STRATEGY_BBRSI_OVER")
            elif strategy_bbrsi(current_strategy) == "buyCondition_bbrsi_under":
                return entry_position(api, cash_bal, "STRATEGY_BBRSI_UNDER")
        else:
            # 매도 조건 확인
            if current_strategy == "STRATEGY_EMA" and strategy_ema(current_strategy) == "sellCondition_ema":
                return close_position(api, stock_qty, "STRATEGY_EMA")
            elif current_strategy == "STRATEGY_EMA2" and strategy_ema2(current_strategy) == "sellCondition_ema2":
                return close_position(api, stock_qty, "STRATEGY_EMA2")
            elif current_strategy == "STRATEGY_BBRSI_OVER" and strategy_bbrsi(current_strategy) == "sellCondition_bbrsi_over":
                return close_position(api, stock_qty, "STRATEGY_BBRSI_OVER")
            elif current_strategy == "STRATEGY_BBRSI_UNDER" and strategy_bbrsi(current_strategy) == "sellCondition_bbrsi_under":
                return close_position(api, stock_qty, "STRATEGY_BBRSI_UNDER")
                
        return {"status": "success", "message": "No action taken", "strategy": current_strategy}
        
    except Exception as e:
        trace = traceback.format_exc()
        post_message(f"Control Tower Error: {e}\n{trace}", channel="#auto-trading-error")
        return {"status": "error", "message": str(e), "trace": trace}


def health_check():
    """KIS API 헬스체크 - 잔액조회 및 현재가 조회"""
    try:
        api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
        current_price = api.get_current_price(TARGET_TICKER)
        balance_data = api.get_balance()
        bal_info, _, _ = get_balance_info(balance_data, TARGET_TICKER, current_price)
        post_message(bal_info, channel="#auto-trading-logs")
        return {"status": "success", "message": "Health check success"}
    except Exception as e:
        trace = traceback.format_exc()
        post_message(f"Health Check Error: {e}\n{trace}", channel="#auto-trading-error")
        return {"status": "error", "message": str(e), "trace": trace}

def parse_holdings_by_asset_class(holdings: List[Dict]) -> Dict[str, List[Dict]]:
    """
    보유 종목을 자산군별로 분류
    DB의 사용자 설정을 우선 사용하고, 없으면 설정 파일 사용
    
    Args:
        holdings: 보유 종목 리스트
        
    Returns:
        자산군별로 분류된 holdings 딕셔너리
    """
    try:
        # 티커 → 자산군 매핑 딕셔너리 생성
        ticker_to_asset_class = {}
        
        # 설정 파일에서 로드
        config_loader = ConfigLoader()
        config = config_loader.load()
        etf_mapping = config.etf_mapping
        
        for asset_class, mapping in etf_mapping.items():
            for ticker in mapping.tickers:
                ticker_to_asset_class[ticker] = asset_class
        
        # 자산군별 holdings 분류
        classified_holdings = {
            "stocks": [],
            "bonds": [],
            "alternatives": [],
            "cash": [],
            "other": []  # 매핑되지 않은 종목
        }
        
        for holding in holdings:
            stock_code = holding.get('stock_code', '')
            asset_class = ticker_to_asset_class.get(stock_code, 'other')
            
            if asset_class in classified_holdings:
                classified_holdings[asset_class].append(holding)
            else:
                classified_holdings['other'].append(holding)
        
        return classified_holdings
    except Exception as e:
        print(f"Error parsing holdings by asset class: {e}")
        traceback.print_exc()
        # 에러 발생 시 빈 딕셔너리 반환
        return {
            "stocks": [],
            "bonds": [],
            "alternatives": [],
            "cash": [],
            "other": []
        }


def calculate_asset_class_pnl(holdings: List[Dict], cash_balance: int = 0) -> Dict[str, Dict]:
    """
    자산군별 수익률 계산
    
    Args:
        holdings: 보유 종목 리스트
        cash_balance: 현금 잔액
        
    Returns:
        자산군별 수익률 정보 딕셔너리
    """
    classified_holdings = parse_holdings_by_asset_class(holdings)
    
    asset_class_info = {}
    
    # 자산군별 정보 계산
    for asset_class, class_holdings in classified_holdings.items():
        if asset_class == 'other':
            continue
            
        total_eval_amount = sum(h.get('eval_amount', 0) for h in class_holdings)
        total_profit_loss = sum(h.get('profit_loss', 0) for h in class_holdings)
        total_avg_buy_amount = sum(
            h.get('avg_buy_price', 0) * h.get('quantity', 0) 
            for h in class_holdings
        )
        
        # 수익률 계산 (매입가 대비)
        profit_loss_rate = 0.0
        if total_avg_buy_amount > 0:
            profit_loss_rate = (total_profit_loss / total_avg_buy_amount) * 100
        
        asset_class_info[asset_class] = {
            "holdings": class_holdings,
            "total_eval_amount": total_eval_amount,
            "total_profit_loss": total_profit_loss,
            "total_avg_buy_amount": total_avg_buy_amount,
            "profit_loss_rate": round(profit_loss_rate, 2),
            "count": len(class_holdings)
        }
    
    # Cash 자산군에 현금 잔액 추가
    if 'cash' in asset_class_info:
        asset_class_info['cash']['total_eval_amount'] += cash_balance
        # 현금은 수익률 0%
        if asset_class_info['cash']['total_avg_buy_amount'] > 0:
            asset_class_info['cash']['profit_loss_rate'] = (
                asset_class_info['cash']['total_profit_loss'] / 
                asset_class_info['cash']['total_avg_buy_amount']
            ) * 100
        else:
            asset_class_info['cash']['profit_loss_rate'] = 0.0
    else:
        asset_class_info['cash'] = {
            "holdings": [],
            "total_eval_amount": cash_balance,
            "total_profit_loss": 0,
            "total_avg_buy_amount": cash_balance,
            "profit_loss_rate": 0.0,
            "count": 0
        }
    
    return asset_class_info


def get_balance_info_api(user_id: Optional[int] = None):
    """잔액조회 API용 함수 - 상세 정보 반환 (자산군별 정보 포함)
    
    Args:
        user_id: 사용자 ID. 제공되면 해당 사용자의 credential 사용, 없으면 환경 변수 사용
    """
    try:
        logging.info(f"KIS balance API 호출 시작 - user_id: {user_id}")
        
        # 사용자별 credential 사용
        if user_id:
            logging.info(f"사용자별 credential 조회 중 - user_id: {user_id}")
            credentials = get_user_kis_credentials(user_id)
            if not credentials:
                logging.warning(f"KIS API 인증 정보 없음 - user_id: {user_id}")
                return {
                    "status": "error",
                    "message": "KIS API 인증 정보가 등록되지 않았습니다. 프로필에서 인증 정보를 등록해주세요."
                }
            logging.info(f"Credential 조회 성공 - account_no: {credentials.get('account_no', 'N/A')[:4]}****")
            api = KISAPI(credentials['app_key'], credentials['app_secret'], credentials['account_no'])
            account_no = credentials['account_no']
        else:
            # 기존 방식 (환경 변수 사용)
            logging.info("환경 변수 사용하여 KIS API 초기화")
            api = KISAPI(APP_KEY, APP_SECRET, ACCOUNT_NO)
            account_no = ACCOUNT_NO
        
        logging.info(f"현재가 조회 시작 - ticker: {TARGET_TICKER}")
        current_price = api.get_current_price(TARGET_TICKER)
        logging.info(f"현재가 조회 완료 - price: {current_price}")
        
        logging.info("잔고 조회 시작")
        balance_data = api.get_balance()
        logging.info(f"잔고 조회 완료 - balance_data keys: {list(balance_data.keys()) if balance_data else 'None'}")
        
        if not balance_data:
            logging.error("잔고 조회 결과가 None입니다")
            return {
                "status": "error",
                "message": "잔고 조회 실패 (응답 없음)"
            }
        
        rt_cd = balance_data.get('rt_cd')
        msg1 = balance_data.get('msg1', '')
        msg2 = balance_data.get('msg2', '')
        logging.info(f"잔고 조회 응답 - rt_cd: {rt_cd}, msg1: {msg1}, msg2: {msg2}")
        
        if rt_cd != '0':
            logging.error(f"잔고 조회 실패 - rt_cd: {rt_cd}, msg1: {msg1}, msg2: {msg2}, 전체 응답: {json.dumps(balance_data, ensure_ascii=False)}")
            return {
                "status": "error",
                "message": balance_data.get('msg1', '잔고 조회 실패') if balance_data else '잔고 조회 실패',
                "rt_cd": rt_cd,
                "msg1": msg1,
                "msg2": msg2
            }
        
        output1 = balance_data.get('output1', [])  # 주식 잔고
        output2 = balance_data.get('output2', [])  # 계좌 총 평가
        
        total_eval_amt = int(output2[0]['tot_evlu_amt']) if output2 else 0
        cash_balance = int(output2[0]['dnca_tot_amt']) if output2 else 0
        
        # 보유 주식 정보
        holdings = []
        if output1:
            for item in output1:
                holdings.append({
                    "stock_code": item.get('pdno', ''),
                    "stock_name": item.get('prdt_name', ''),
                    "quantity": int(item.get('hldg_qty', 0)),
                    "avg_buy_price": int(item.get('pchs_avg_prc', 0)),
                    "current_price": int(item.get('prpr', 0)),
                    "eval_amount": int(item.get('evlu_amt', 0)),
                    "profit_loss": int(item.get('evlu_pfls_amt', 0)),
                    "profit_loss_rate": float(item.get('evlu_pfls_rt', 0))
                })
        
        # 자산군별 정보 계산
        asset_class_info = calculate_asset_class_pnl(holdings, cash_balance)
        
        return {
            "status": "success",
            "account_no": account_no,
            "total_eval_amount": total_eval_amt,
            "cash_balance": cash_balance,
            "holdings": holdings,
            "asset_class_info": asset_class_info,  # 자산군별 정보 추가
            "target_ticker": TARGET_TICKER,
            "target_ticker_name": TARGET_TICKER_NAME,
            "target_ticker_current_price": current_price
        }
    except Exception as e:
        trace = traceback.format_exc()
        return {
            "status": "error",
            "message": str(e),
            "trace": trace
        }

