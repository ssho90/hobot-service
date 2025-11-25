# service/macro_trading/kis/kis_utils.py
import pandas as pd
import numpy as np
import os

# ================
# current state Read/Write
# 현재 매수한 거래가 어떤 전략인지
# ================
def write_current_strategy(text):
    # 프로젝트 루트 기준으로 경로 설정
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    strategy_file = os.path.join(base_path, 'service', 'CurrentStrategy_kis.txt')
    with open(strategy_file, 'w') as file:
        file.write(text)

    current_strategy = read_current_strategy()
    return "[System] Current Strategy : " + current_strategy

def read_current_strategy():
    # 프로젝트 루트 기준으로 경로 설정
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    strategy_file = os.path.join(base_path, 'service', 'CurrentStrategy_kis.txt')
    try:
        with open(strategy_file, 'r') as file:
            condition = file.read()
        if not condition:
            return "STRATEGY_NULL"
        return condition
    except FileNotFoundError:
        write_current_strategy("STRATEGY_NULL")
        return "STRATEGY_NULL"

# ===============================================
# 보조지표 계산 함수들 (기존 코드와 동일)
# ===============================================
def calculate_rsi(df):
    period = 14
    delta = df['close'].diff()
    delta = delta[1:]
    gain = delta.clip(lower=0)
    loss = delta.clip(upper=0).abs()
    avg_gain = gain.ewm(alpha=1 / period).mean()
    avg_loss = loss.ewm(alpha=1 / period).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi

def calculate_true_range(df):
    df['high_low'] = df['high'] - df['low']
    df['high_prev_close'] = abs(df['high'] - df['close'].shift(1))
    df['low_prev_close'] = abs(df['low'] - df['close'].shift(1))
    df['True_Range'] = df[['high_low', 'high_prev_close', 'low_prev_close']].max(axis=1)
    return df

def calculate_atr(df, period=14, atr_type='rma'):
    df = calculate_true_range(df)
    if atr_type == 'rma':
        df['ATR'] = df['True_Range'].ewm(alpha=1/period, adjust=False).mean()
    elif atr_type == 'sma':
        df['ATR'] = df['True_Range'].rolling(window=period).mean()
    # ... (other atr types if needed)
    return df['ATR']

def current_time(type="time"):
    import datetime
    import pytz

    date = datetime.datetime.now(pytz.timezone('Asia/Seoul'))
    dict_yoil = {0:'(월)', 1:'(화)', 2:'(수)', 3:'(목)', 4:'(금)', 5:'(토)', 6:'(일)'}
    yoil = dict_yoil[date.weekday()]

    if type == "day":
        return date.strftime("%Y.%m.%d") + " " + yoil
    else:
        return date.strftime("%Y-%m-%d") + " " + yoil + " " + date.strftime("%H:%M:%S")

# ===============================================
# 메시지 포맷팅 함수들 (주식 시장 용어로 수정)
# ===============================================
def get_balance_info(balance_data, ticker_name, current_price):
    if not balance_data:
        return "잔고 조회에 실패했습니다.", 0, 0

    output1 = balance_data.get('output1', []) # 주식 잔고
    output2 = balance_data.get('output2', []) # 계좌 총 평가

    total_eval_amt = int(output2[0]['tot_evlu_amt']) if output2 else 0
    cash_balance = int(output2[0]['dnca_tot_amt']) if output2 else 0
    
    stock_str = "보유 주식 없음"
    stock_quantity = 0

    if output1:
        for item in output1:
            if item['pdno'] == ticker_name: # 종목코드가 아닌 종목명으로 비교 (API 응답 기준)
                stock_quantity = int(item['hldg_qty'])
                avg_buy_price = int(item['pchs_avg_prc'])
                eval_amt = int(item['evlu_amt'])
                eval_profit_loss = int(item['evlu_pfls_amt'])
                eval_profit_loss_rate = float(item['evlu_pfls_rt'])
                
                stock_str = f"""
<< {item['prdt_name']} >>
- 보유수량: {format(stock_quantity, ",")} 주
- 평가금액: {format(eval_amt, ",")} 원
- 평가손익: {format(eval_profit_loss, ",")} 원 ({eval_profit_loss_rate}%)
- 현재금액: {format(current_price, ",")} 원
- 매수평균가: {format(avg_buy_price, ",")} 원
                """
                break
    
    header = f"""
--------------------------------------
      [KIS Auto Trading]
--------------------------------------
- 일시: {current_time()}
- 총 보유자산: {format(total_eval_amt, ",")} 원
    """

    cash_str = f"""
<< 예수금 >>
- 보유현금: {format(cash_balance, ",")} 원
    """

    result = header + cash_str + stock_str
    return result, cash_balance, stock_quantity


def get_buy_info(strategy, quantity, price, ticker_name):
    return f"""
------------------------
  [매수 체결]
------------------------
- 일자: {current_time()}
- 종목: {ticker_name}
- 매매전략: {strategy}
- 체결수량: {format(quantity, ",")} 주
- 체결단가: {format(price, ",")} 원
    """

def get_sell_info(strategy, quantity, price, ticker_name):
    return f"""
------------------------
  [매도 체결]
------------------------
- 일자: {current_time()}
- 종목: {ticker_name}
- 매매전략: {strategy}
- 체결수량: {format(quantity, ",")} 주
- 체결단가: {format(price, ",")} 원
    """

