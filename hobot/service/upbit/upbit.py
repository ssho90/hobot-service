from dotenv import load_dotenv
import os
import pyupbit
import pandas as pd
from service.upbit.upbit_utils import calculate_rsi, write_current_strategy, get_balance_info, current_time, read_current_strategy, get_buy_info, get_sell_info, calculate_atr
from service.slack_bot import post_message
import traceback

load_dotenv(override = True)

api_key = os.environ["UP_ACCESS_KEY"]
api_secret = os.environ["UP_SECRET_KEY"]

target_ticker = "KRW-BTC"
interval = "D"

# ===============================================
# Helper Functions
# ===============================================
def fetch_candle_data(ticker, interval, count):
    """Fetches OHLCV data from Upbit."""
    try:
        df = pyupbit.get_ohlcv(ticker, interval=interval, count=count)
        if df is None or df.empty:
            raise ValueError(f"Could not fetch candle data for {ticker} with interval {interval} and count {count}")
        return df
    except Exception as e:
        print(f"Error fetching candle data: {e}")
        return None

def calculate_moving_averages(close, spans=[7, 20, 99, 180]):
    """Calculates exponential moving averages."""
    ma = {}
    for span in spans:
        ma[span] = close.ewm(span=span, adjust=False).mean().iloc[-2]
    return ma


# ===============================================
# strategy1 : EMA 정배열
# 조건 : 
# ===============================================
def strategy_ema(current_strategy):
    import pyupbit
    from service.upbit.upbit_utils import write_current_strategy

    df = fetch_candle_data(target_ticker, interval, 200)

    close = df["close"]

    ma = calculate_moving_averages(close, spans=[7, 20, 99, 180])

    print(f'MA(7 20 99 180): {ma[7]} / {ma[20]} / {ma[99]} / {ma[180]}')

    ema1 = ma[7]
    ema2 = ma[20]
    ema3 = ma[99]
    ema4 = ma[180]

    buy_condition_ema = ema1 > ema2 > ema3 > ema4

    ema_almost_crossunder = abs(ema1 - ema2) * 100 / ema1 < 0.5 # 0.5% 이내)

    sell_condition = not (buy_condition_ema)

    if current_strategy == "STRATEGY_NULL":
        if buy_condition_ema and not ema_almost_crossunder:
            return "buyCondition_ema"    
        else:
            return "noCondition_ema"
    else:
        if sell_condition:
            return "sellCondition_ema"
        if ema_almost_crossunder:
            return "sellCondition_ema"
        else:
            return "noCondition_ema"

# ===============================================
# strategy1-2 : EMA 정배열 (ema3, ema4 > ema1, ema2 에서 작동)
# 조건 : 
# ===============================================
def strategy_ema2(current_strategy):

    df = fetch_candle_data(target_ticker, interval, 250)

    close = df["close"]

    atr_df = calculate_atr(df, period=20)

    print(atr_df[-1]) # 이게 하루전 atr임. atr은 오늘 봉이 끝나야 계산됨.

    ma = calculate_moving_averages(close, spans=[7, 20, 99, 180])

    ema1 = ma[7]
    ema2 = ma[20]
    ema3 = ma[99]
    ema4 = ma[180]
    
    ema1_2b = close.ewm(span=7, adjust=False).mean().iloc[-3]
    ema2_2b = close.ewm(span=20, adjust=False).mean().iloc[-3]
    ema3_2b = close.ewm(span=99, adjust=False).mean().iloc[-3]

    print(f'EMA_2b(7 20 99): {ema1_2b} / {ema2_2b} / {ema3_2b}')

    # Bollinger Bands (K=1)
    df['middle'] = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(20).std(ddof=0)
    df['upper'] = df['middle'] + 1 * std
    df['lower'] = df['middle'] - 1 * std

    df[['upper', 'middle', 'lower']].tail(n=10)

    # Bollinger Bands (K=2)
    df['middle_k2'] = df['close'].rolling(window=20).mean()
    std_k2 = df['close'].rolling(20).std(ddof=0)
    df['upper_k2'] = df['middle_k2'] + 2 * std_k2
    df['lower_k2'] = df['middle_k2'] - 2 * std_k2

    bb_low1 = df.iloc[-2]['lower']
    bb_low1_k2 = df.iloc[-2]['lower_k2']
    bb_low2_k2 = df.iloc[-3]['lower_k2']
    
    close_1b = df.iloc[-2]["close"]
    close_2b = df.iloc[-3]["close"]

    df[['upper_k2', 'middle_k2', 'lower_k2']].tail(n=10)


    sell_condition_each1 = close_1b < bb_low1_k2 and close_2b > bb_low2_k2 # ta.crossunder(close,bb_low1_k2)
    sell_condition_each2 = ema1 < ema2 and ema1_2b > ema2_2b # ta.crossunder(ema1,ema2)
    sell_condition_each3 = close_1b > ema3 and close_2b < ema3_2b # ta.crossover(close,ema3)

    long_condition_each1 = ema1 > ema2 and ema1_2b < ema2_2b # ta.crossover(ema1,ema2)
    long_condition_each2 = ema4 > ema3 and ema3 > ema2
    
    buy_condition = long_condition_each1 and long_condition_each2
    sell_condition = sell_condition_each1 or sell_condition_each2 or sell_condition_each3

    if current_strategy == "STRATEGY_NULL":
        if buy_condition:
            return "buyCondition_ema2"    
        else:
            return "noCondition_ema2"
    else:
        if sell_condition:
            return "sellCondition_ema2"
        else:
            return "noCondition_ema2"
    

# ===============================================
# strategy2 : BBRSI STRATEGY
# 직전 종가가 ema1 위에 있으면 -> BBRSI_STRATEGY_OVER
# 직전 종가가 ema1 아래에 있으면 -> BBRSI_STRATEGY_UNDER
# -----------------------------------------------
# 매수조건 (AND)
# 1) rsi의 2이평 > 4이평
# 1-2) RSI 1,2,4 이평끼리 서로 간격이 좁을 때 (rsi_threshold default 1.8%)
# 2) 2봉 전 or 3봉 전의 rsi의 1, 2, 4 이평이 역배열 상태였었는가?
# 3) 직전 4개봉 저가가 BB 하단에 위치
# -----------------------------------------------
# 매도조건 - OVER 일때 (OR)
# 1) 직전 종가가 bbLower(k=2) 하단에 위치
# 2) 직전 종가가 bbUpper(k=1) Crossover
# 3) StopLoss 매도조건: 직전봉 종가 * 0.88 > 현재가
# -----------------------------------------------
# 매도조건 - UNDER 일때 (OR)
# 1) 직전 종가가 bbLower(k=2) 하단에 위치
# 2) 직전 종가가 7일 이평 Crossover
# 3) StopLoss 매도조건: 직전봉 저가 - atr*1 > 현재가
# 4) limit 매도조건: 직전봉 고가 + atr*4 < 현재가
# ===============================================
def strategy_bbrsi(current_strategy):
    df = fetch_candle_data(target_ticker, interval, 250)

    close = df["close"]

    #rsi
    rsi = calculate_rsi(df)
    rsi_ma1 = calculate_rsi(df).iloc[-2]
    rsi_ma2 = rsi.ewm(span=2, adjust=False).mean().iloc[-2]
    rsi_ma4 = rsi.ewm(span=4, adjust=False).mean().iloc[-2]

    rsi_ma1_2before = calculate_rsi(df).iloc[-3]
    rsi_ma2_2before = rsi.ewm(span=2, adjust=False).mean().iloc[-3]
    rsi_ma4_2before = rsi.ewm(span=4, adjust=False).mean().iloc[-3]

    rsi_ma1_3before = calculate_rsi(df).iloc[-4]
    rsi_ma2_3before = rsi.ewm(span=2, adjust=False).mean().iloc[-4]
    rsi_ma4_3before = rsi.ewm(span=4, adjust=False).mean().iloc[-4]

    # 이평
    ma7 = close.ewm(span=7, adjust=False).mean().iloc[-2]
    ma7_2before = close.ewm(span=7, adjust=False).mean().iloc[-3]


    # 볼밴
    pd.set_option('display.float_format', lambda x: '%.2f' % x)

    # Bollinger Bands (K=1)
    df['middle'] = df['close'].rolling(window=20).mean()
    std = df['close'].rolling(20).std(ddof=0)
    df['upper'] = df['middle'] + 1 * std
    df['lower'] = df['middle'] - 1 * std

    df[['upper', 'middle', 'lower']].tail(n=10)

    # Bollinger Bands (K=2)
    df['middle_k2'] = df['close'].rolling(window=20).mean()
    std_k2 = df['close'].rolling(20).std(ddof=0)
    df['upper_k2'] = df['middle_k2'] + 2 * std_k2
    df['lower_k2'] = df['middle_k2'] - 2 * std_k2

    df[['upper_k2', 'middle_k2', 'lower_k2']].tail(n=10)

    

    # 볼린저밴드 직전 하단
    bb_low1 = df.iloc[-2]['lower']
    bb_low2 = df.iloc[-3]['lower']
    bb_low3 = df.iloc[-4]['lower']
    bb_low4 = df.iloc[-5]['lower']

    bb_low1_k2 = df.iloc[-2]['lower_k2']

    bb_upper1 = df.iloc[-2]['upper']
    bb_upper2 = df.iloc[-3]['upper']

    close_curr = df.iloc[-1]["close"]
    close1 = df.iloc[-2]["close"]
    close2 = df.iloc[-3]["close"]
    close3 = df.iloc[-4]["close"]
    close4 = df.iloc[-5]["close"]

    high1 = df.iloc[-2]["high"]

    low1 = df.iloc[-2]["low"]
    low2 = df.iloc[-3]["low"]
    low3 = df.iloc[-4]["low"]
    low4 = df.iloc[-5]["low"]

    bbrsi_dict = {"ma7": ma7, "rsi":rsi_ma1, "rsi_ma2":rsi_ma2, "rsi_ma4":rsi_ma4, "bb_low1":bb_low1, "bb_low2":bb_low2, "bb_low3":bb_low3, "bb_low4":bb_low4, "bb_low1_k2": bb_low1_k2,"close":close_curr, "close1":close1, "close2":close2, "close3":close3, "close4":close4, "low1":low1, "low2":low2, "low3":low3, "low4":low4}
    print("bbrsi_dict =============")
    print(bbrsi_dict)

    atr_df = calculate_atr(df, period=20, atr_type="rma")
    atr1 = atr_df.iloc[-1]
    print("atr1 - bbrsi_under=============")
    print(atr1)

    # -----------------------------------------------
    # 매수조건 Setting
    # -----------------------------------------------
    # 매수조건1) rsi의 2이평 > 4이평
    condition1 = close1 > ma7

    # 매수조건 1-2) RSI 1,2,4 이평끼리 서로 간격이 좁을 때 (rsi_threshold default 1.8%)
    rsi_threshold = 1.8
    condition1_2 = abs(rsi_ma1 - rsi_ma2) * 100 / rsi_ma1 < rsi_threshold or abs(rsi_ma1 - rsi_ma2) * 100 / rsi_ma2 < rsi_threshold or abs(rsi_ma2 - rsi_ma4) * 100 / rsi_ma4 < rsi_threshold

    # 매수조건2) 2봉 전 or 3봉 전의 rsi의 1, 2, 4 이평이 역배열 상태였었는가?
    c1 = rsi_ma1_2before < rsi_ma2_2before and rsi_ma2_2before < rsi_ma4_2before
    c2 = rsi_ma1_3before < rsi_ma2_3before and rsi_ma2_3before < rsi_ma4_3before
    condition2 = c1 or c2

    # 매수조건3) 직전 4개봉 저가가 BB 하단에 위치
    condition3 = bb_low1 > low1 or bb_low2 > low2 or bb_low3 > low3 or bb_low4 > low4

    # -----------------------------------------------
    # 매도조건 Setting
    # -----------------------------------------------
    # 공통 매도조건1) 직전 종가가 bbLower(k=2) 하단에 위치
    sell_condition1 = low1 < bb_low1_k2

    # OVER 매도조건2) 직전 종가가 bbUpper(k=1) Crossover
    sell_condition1_over =  bb_upper1 < close1 and bb_upper2 > close2 # ta.crossover(close,ma7)

    # OVER 매도조건3) StopLoss 매도조건: 직전봉 저가 - atr*1 > 현재가
    stop_condition_under = (low1 - atr1) > close_curr
    
    # OVER 매도조건4) limit 매도조건: 직전봉 고가 + atr*4 < 현재가
    limit_condition_under = (high1 + atr1 * 4) < close_curr

    # UNDER 매도조건2) 직전 종가가 7일 이평 Crossover
    sell_condition1_under = ma7 < close1 and ma7_2before > close2 # ta.crossover(close,ma7)

    # UNDER 매도조건3) StopLoss 매도조건: 직전봉 종가 * 0.88 > 현재가
    stop_condition_over = (close1 * 0.88) > close_curr


    sellCondition_bbrsi_over = sell_condition1_over or sell_condition1 or stop_condition_under or limit_condition_under
    sellCondition_bbrsi_under = sell_condition1_under or sell_condition1 or stop_condition_over

    #bbrsi_over or bbrsi_under 판단
    is_over = close1 > ma7

    result = None

    if current_strategy == "STRATEGY_NULL":
        if is_over: #over 상태일 때
            buyCondition_bbrsi = (condition1 or condition1_2) and condition2 and condition3
            
            if buyCondition_bbrsi and not(sellCondition_bbrsi_over): #sell condition False일 때 buy 하도록:
                result = "buyCondition_bbrsi_over"

        else: #under 상태일 때
            buyCondition_bbrsi = (condition1 or condition1_2) and condition2 and condition3

            if buyCondition_bbrsi and not(sellCondition_bbrsi_under): #sell condition False일 때 buy 하도록:
                result = "buyCondition_bbrsi_under"
     
    elif current_strategy == "STRATEGY_BBRSI_OVER":
        if sellCondition_bbrsi_over:
            result = "sellCondition_bbrsi_over"

    elif current_strategy == "STRATEGY_BBRSI_UNDER":
        if sellCondition_bbrsi_under:
            result = "sellCondition_bbrsi_under"

    return "noCondition_bbrsi" if result == None else result

# ================================================
# Entry Position
# ================================================
def entry_position(balance_krw, upbit, strategy):
 
    try:
        df = fetch_candle_data(target_ticker, interval, 3)

        current_price = df.iloc[-1]["close"]
        print(f"현재가: {current_price}")

        print(f"*(매수중) 보유현금 : {balance_krw}")

        # 현재 갖고 있는 현금
        print("*(매수중) 보유현금 : "+ str(balance_krw))

        # 시장가에 매수 실행
        res = upbit.buy_market_order(target_ticker, balance_krw - 7000)
        if 'error' in res:
            print(res)
            return {"status": "error", "message": f"매수 주문 실패: {res}"}
        print(res)
        buy_amount = res['price'] # 체결된 매수 금액 총량
        write_current_strategy(strategy)

        post_message(get_buy_info(strategy, buy_amount, current_price))

        return {"status": "success", "message": "매수 주문 성공", "result": res}
    except Exception as e:
        print(f"Error during entry: {e}")
        return {"status": "error", "message": f"매수 중 오류 발생: {e}"}
    
# ================================================
# Close Position
# ================================================
def close_position(bal_btc, upbit, strategy):
    try:
        print(f"**매도 btc 수량: {bal_btc}")

        res = upbit.sell_market_order(target_ticker, bal_btc)
        if 'error' in res:
            print(res)
            return {"status": "error", "message": f"매도 주문 실패: {res}"}

        print(res)
        write_current_strategy("STRATEGY_NULL")
        post_message(get_sell_info(strategy))
        return {"status": "success", "message": "매도 주문 성공", "result": res}

    except Exception as e:
        print(f"Error during close: {e}")
        return {"status": "error", "message": f"매도 중 오류 발생: {e}"}

# ================================================
# Control Tower
# ================================================
def control_tower():
    try:
        upbit = pyupbit.Upbit(api_key, api_secret)	

        df = fetch_candle_data(target_ticker, interval, 3)
        if df is None:
            return {"status": "error", "message": "Failed to fetch candle data"}

        current_price = df.iloc[-1]["close"]

        # ===============================================
        # 서버 기동 후 현재 계좌 상태 Slack Alarm
        # ===============================================
        bal_info, bal_krw, bal_btc = get_balance_info(upbit, "BTC", current_price)

        post_message(bal_info, channel="#upbit-balance")

        #현재 매매 상태 체크
        current_strategy = read_current_strategy()

        # ===============================================
        # No Position
        # ===============================================
        if current_strategy == "STRATEGY_NULL":
            if strategy_ema(current_strategy) == "buyCondition_ema": 
                print("EMA 매수 실행")
                entry_result = entry_position(bal_krw, upbit, "STRATEGY_EMA")

                return {"status": "success", "message": "EMA entry success", "strategy": "STRATEGY_EMA", "system_message": entry_result}
            
            elif strategy_ema2(current_strategy) == "buyCondition_ema2":
                print("EMA2 매수 실행")
                entry_result = entry_position(bal_krw, upbit, "STRATEGY_EMA2")

                return {"status": "success", "message": "EMA2 entry success", "strategy": "STRATEGY_EMA2", "system_message": entry_result}

            elif strategy_bbrsi(current_strategy) == "buyCondition_bbrsi_over": 
                print("BBRSI_OVER 매수 실행")
                entry_result = entry_position(bal_krw, upbit, "STRATEGY_BBRSI_OVER")

                return {"status": "success", "message": "BBRSI_OVER entry success", "strategy": "STRATEGY_BBRSI_OVER", "system_message": entry_result}

            elif strategy_bbrsi(current_strategy) == "buyCondition_bbrsi_under": 
                print("BBRSI_UNDER 매수 실행")
                entry_result = entry_position(bal_krw, upbit, "STRATEGY_BBRSI_UNDER")

                return {"status": "success", "message": "BBRSI_UNDER entry success", "strategy": "STRATEGY_BBRSI_UNDER", "system_message": entry_result}

        elif current_strategy == "STRATEGY_EMA" and strategy_ema(current_strategy) == "sellCondition_ema":
            print("STRATEGY_EMA 매도 실행")
            close_result = close_position(bal_btc, upbit, "STRATEGY_EMA")

            return {"status": "success", "message": "EMA close success", "strategy": "STRATEGY_EMA", "system_message": close_result}

        elif current_strategy == "STRATEGY_EMA2" and strategy_ema2(current_strategy) == "sellCondition_ema2":
            print("STRATEGY_EMA2 매도 실행")
            close_result = close_position(bal_btc, upbit, "STRATEGY_EMA2")

            return {"status": "success", "message": "EMA2 close success", "strategy": "STRATEGY_EMA2", "system_message": close_result}

        elif current_strategy == "STRATEGY_BBRSI_OVER" and strategy_bbrsi(current_strategy) == "sellCondition_bbrsi_over":
            print("STRATEGY_BBRSI_OVER 매도 실행")
            close_result = close_position(bal_btc, upbit, "STRATEGY_BBRSI_OVER")

            return {"status": "success", "message": "BBRSI_OVER close success", "strategy": "STRATEGY_BBRSI_OVER", "system_message": close_result}

        elif current_strategy == "STRATEGY_BBRSI_UNDER" and strategy_bbrsi(current_strategy) == "sellCondition_bbrsi_under":
            print("STRATEGY_BBRSI_UNDER 매도 실행")
            close_result = close_position(bal_btc, upbit, "STRATEGY_BBRSI_UNDER")

            return {"status": "success", "message": "BBRSI_UNDER close success", "strategy": "STRATEGY_BBRSI_UNDER", "system_message": close_result}

        return {"status": "success", "message": "No action taken", "strategy": current_strategy}
    
    except Exception as e:
        trace = traceback.format_exc()
        return {"status": "error", "message": str(e), "trace": trace}
    

def health_check():
    try:
        upbit = pyupbit.Upbit(api_key, api_secret)	

        df = fetch_candle_data(target_ticker, interval, 3)
        if df is None:
            return {"status": "error", "message": "Failed to fetch candle data"}

        current_price = df.iloc[-1]["close"]

        # ===============================================
        # 서버 기동 후 현재 계좌 상태 Slack Alarm
        # ===============================================
        try:
            bal_info, bal_krw, bal_btc = get_balance_info(upbit, "BTC", current_price)
            if isinstance(bal_info, str) and "오류" in bal_info:
                # API 오류가 있는 경우에도 헬스체크는 성공으로 처리
                print(f"Balance info warning: {bal_info}")
                return {"status": "success", "message": "Health check success (with balance API warning)"}
            else:
                post_message(bal_info)
                return {"status": "success", "message": "Health check success"}
        except Exception as balance_error:
            print(f"Balance check error: {balance_error}")
            # 잔고 조회 실패해도 헬스체크는 성공으로 처리
            return {"status": "success", "message": "Health check success (balance check failed)"}

        trace = traceback.format_exc()
        return {"status": "error", "message": str(e), "trace": trace}

def analyze_market_condition():
    """
    현재 차트 데이터와 전략을 기반으로 매매 로직을 시뮬레이션하여 상태를 반환합니다.
    매매는 실행하지 않으며, 판단 결과 문자열만 반환합니다.
    """
    try:
        # 현재 매매 상태 체크 (DB)
        current_strategy = read_current_strategy()
        
        # 1. No Position 상태일 때 (매수 조건 점검)
        if current_strategy == "STRATEGY_NULL":
            # EMA
            if strategy_ema(current_strategy) == "buyCondition_ema":
                return "Buy Signal Detected: STRATEGY_EMA"
            
            # EMA2
            elif strategy_ema2(current_strategy) == "buyCondition_ema2":
                return "Buy Signal Detected: STRATEGY_EMA2"

            # BBRSI
            bbrsi_result = strategy_bbrsi(current_strategy)
            if bbrsi_result == "buyCondition_bbrsi_over":
                 return "Buy Signal Detected: STRATEGY_BBRSI_OVER"
            elif bbrsi_result == "buyCondition_bbrsi_under":
                 return "Buy Signal Detected: STRATEGY_BBRSI_UNDER"
            
            return "No Buy Signal (Monitoring...)"

        # 2. Position 보유 중일 때 (매도 조건 점검)
        elif current_strategy == "STRATEGY_EMA":
            if strategy_ema(current_strategy) == "sellCondition_ema":
                return "Sell Signal Detected (Exit STRATEGY_EMA)"
            return "Holding STRATEGY_EMA (No Sell Signal)"

        elif current_strategy == "STRATEGY_EMA2":
             if strategy_ema2(current_strategy) == "sellCondition_ema2":
                return "Sell Signal Detected (Exit STRATEGY_EMA2)"
             return "Holding STRATEGY_EMA2 (No Sell Signal)"

        elif current_strategy == "STRATEGY_BBRSI_OVER":
            if strategy_bbrsi(current_strategy) == "sellCondition_bbrsi_over":
                return "Sell Signal Detected (Exit STRATEGY_BBRSI_OVER)"
            return "Holding STRATEGY_BBRSI_OVER (No Sell Signal)"

        elif current_strategy == "STRATEGY_BBRSI_UNDER":
            if strategy_bbrsi(current_strategy) == "sellCondition_bbrsi_under":
                return "Sell Signal Detected (Exit STRATEGY_BBRSI_UNDER)"
            return "Holding STRATEGY_BBRSI_UNDER (No Sell Signal)"
            
        return f"Unknown Strategy State: {current_strategy}"

    except Exception as e:
        trace = traceback.format_exc()
        return f"Analysis Error: {str(e)}"
    