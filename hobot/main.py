from dotenv import load_dotenv
import os

load_dotenv(override=True)

from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
import logging
from service.slack_bot import post_message
from app import daily_news_summary
from service.daily_news_agent import compiled
from service import news_manager

app = FastAPI(title="Hobot API", version="1.0.0")

# API 라우터 생성
api_router = APIRouter(prefix="/api")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log.txt')
logging.basicConfig(filename=log_file_path, level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Pydantic 모델
class StrategyRequest(BaseModel):
    strategy: str

# 기본 페이지 (루트)
@app.get("/", response_class=HTMLResponse)
async def hello_world():
    return "<p>Hello, World!</p>"

# API 엔드포인트들을 /api 라우터에 추가
@api_router.get("/health")
async def health_check():
    from service.upbit.upbit import health_check
    res = health_check()
    return res

@api_router.get("/news-sentiment")
async def daily_news(query: str = Query(default="오늘의 뉴스 중 중요한 뉴스들을 알려줘. 경제 > 정치 > 과학(기술) > 사회 > 기타 순서로 중요도를 판단하면 돼")):
    """기존 뉴스 시감 분석 (슬랙 전송용)"""
    news = daily_news_summary(query)
    res = post_message(news)
    return res

@api_router.get("/news")
async def get_daily_news():
    """뉴스 파일에서 뉴스를 읽어옵니다. (브라우저용)"""
    try:
        result = news_manager.get_news_with_date()
        
        if result["news"]:
            return result
        else:
            raise HTTPException(status_code=404, detail="No news available")
    except Exception as e:
        logging.error(f"Error getting daily news: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/news-update")
async def update_daily_news():
    """뉴스를 새로 수집하고 저장합니다. (스케줄러용 - Tavily API 호출)"""
    try:
        return news_manager.update_news_with_tavily(compiled)
    except Exception as e:
        logging.error(f"Error updating daily news: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/upbit/trading")
async def upbit_trading():
    import time
    from service.upbit import upbit
    
    res = upbit.control_tower()
    post_message(f"upbit_trading result: {res}", channel="#auto-trading-logs")
    logging.info(f"upbit_trading result: {res}")
    return res

@api_router.get("/kis/healthcheck")
async def kis_health_check():
    from service.kis import connection_test
    
    res = connection_test.run_connection_test()
    logging.info(f"kis health check result: {res}")
    return res

@api_router.get("/upbit/test2")
async def upbit_bbrsi_test2():
    from service.upbit import upbit
    from service.upbit.upbit_utils import read_current_strategy
    
    current_st = read_current_strategy()
    res = upbit.strategy_ema("STRATEGY_NULL")
    logging.info(f"upbit_trading result: {res}")
    return {"res": res}

@api_router.get("/current-strategy", response_class=PlainTextResponse)
async def get_current_strategy():
    strategy_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'service', 'CurrentStrategy.txt')
    
    try:
        with open(strategy_file_path, 'r', encoding='utf-8') as f:
            strategy = f.read().strip()
        return strategy
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Strategy file not found")
    except Exception as e:
        logging.error(f"Error reading current strategy: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@api_router.post("/current-strategy")
async def update_current_strategy(request: StrategyRequest):
    strategy_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'service', 'CurrentStrategy.txt')
    
    try:
        with open(strategy_file_path, 'w', encoding='utf-8') as f:
            f.write(request.strategy)
        
        logging.info(f"Current strategy updated to: {request.strategy}")
        return {"status": "success", "strategy": request.strategy}
    except Exception as e:
        logging.error(f"Error updating current strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API 라우터를 앱에 포함
app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8991)