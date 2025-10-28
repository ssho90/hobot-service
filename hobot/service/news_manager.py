import os
import logging
from datetime import datetime

# 뉴스 파일 경로
NEWS_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'daily_news.txt')

def get_today_date_str():
    """오늘 날짜를 YYYY-MM-DD 형식으로 반환"""
    return datetime.now().strftime("%Y-%m-%d")

def get_news_date_from_file():
    """뉴스 파일에서 날짜를 읽어옴"""
    try:
        if not os.path.exists(NEWS_FILE_PATH):
            return None
        
        with open(NEWS_FILE_PATH, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            # 날짜 형식: "=== 2024-01-01 ==="
            if first_line.startswith("===") and first_line.endswith("==="):
                date_str = first_line.replace("===", "").strip()
                return date_str
        return None
    except Exception as e:
        logging.error(f"Error reading news date from file: {e}")
        return None

def is_news_today():
    """오늘 날짜의 뉴스가 있는지 확인"""
    file_date = get_news_date_from_file()
    today_date = get_today_date_str()
    return file_date == today_date

def save_news_to_file(news_content):
    """뉴스 내용을 파일에 저장"""
    try:
        today_date = get_today_date_str()
        with open(NEWS_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(f"=== {today_date} ===\n\n")
            f.write(news_content)
        logging.info(f"News saved to file for date: {today_date}")
    except Exception as e:
        logging.error(f"Error saving news to file: {e}")
        raise

def get_news_from_file():
    """뉴스 파일에서 내용을 읽어옴"""
    try:
        if not os.path.exists(NEWS_FILE_PATH):
            return None
        
        with open(NEWS_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
            # 첫 번째 줄(날짜) 제거
            lines = content.split('\n')
            if len(lines) > 1:
                return '\n'.join(lines[2:])  # 날짜 줄과 빈 줄 제거
        return None
    except Exception as e:
        logging.error(f"Error reading news from file: {e}")
        return None

def update_news_with_tavily(compiled):
    """Tavily를 사용하여 뉴스를 수집하고 저장"""
    try:
        # 오늘 날짜의 뉴스가 이미 있으면 업데이트하지 않음
        if is_news_today():
            logging.info("News for today already exists, skipping update")
            return {
                "status": "already_exists",
                "message": "News for today already exists"
            }
        
        # 뉴스 수집
        logging.info("Starting news collection with Tavily API...")
        # State 초기화 - messages를 빈 리스트로 초기화
        initial_state = {"messages": []}
        final_state = compiled.invoke(initial_state)
        last_message = final_state['messages'][-1]
        news_content = last_message.content
        
        # 파일에 저장
        save_news_to_file(news_content)
        
        logging.info("News update completed successfully")
        return {
            "status": "success",
            "message": "News updated successfully"
        }
    except Exception as e:
        logging.error(f"Error updating daily news: {e}")
        raise

def get_news_with_date():
    """뉴스와 날짜 정보를 함께 반환"""
    file_date = get_news_date_from_file()
    today_date = get_today_date_str()
    news_content = get_news_from_file()
    
    return {
        "news": news_content,
        "date": file_date,
        "is_today": file_date == today_date if file_date else False
    }

