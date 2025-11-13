import os
import logging
from datetime import datetime

# 뉴스 파일 경로
# news_manager.py는 service/news/ 디렉토리에 있으므로, hobot/ 디렉토리로 가려면 두 단계 상위로 이동
NEWS_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'daily_news.txt')

# 모듈 로드 시 파일 경로 로깅
logging.info(f"News file path initialized: {NEWS_FILE_PATH}")
logging.info(f"News file exists: {os.path.exists(NEWS_FILE_PATH)}")

def get_today_date_str():
    """오늘 날짜를 YYYY-MM-DD 형식으로 반환"""
    return datetime.now().strftime("%Y-%m-%d")

def get_news_date_from_file():
    """뉴스 파일에서 날짜를 읽어옴"""
    logging.info(f"get_news_date_from_file: Checking file at {NEWS_FILE_PATH}")
    try:
        if not os.path.exists(NEWS_FILE_PATH):
            logging.info(f"get_news_date_from_file: File does not exist at {NEWS_FILE_PATH}")
            return None
        
        logging.info(f"get_news_date_from_file: File exists, reading first line...")
        with open(NEWS_FILE_PATH, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            logging.info(f"get_news_date_from_file: First line = '{first_line}'")
            # 날짜 형식: "=== 2024-01-01 ==="
            if first_line.startswith("===") and first_line.endswith("==="):
                date_str = first_line.replace("===", "").strip()
                logging.info(f"get_news_date_from_file: Extracted date = '{date_str}'")
                return date_str
        logging.info(f"get_news_date_from_file: First line does not match date format")
        return None
    except Exception as e:
        logging.error(f"get_news_date_from_file: Error reading news date from file: {type(e).__name__}: {str(e)}", exc_info=True)
        return None

def is_news_today():
    """오늘 날짜의 뉴스가 있는지 확인"""
    file_date = get_news_date_from_file()
    today_date = get_today_date_str()
    is_today = file_date == today_date
    logging.info(f"is_news_today: file_date={file_date}, today_date={today_date}, is_today={is_today}")
    return is_today

def save_news_to_file(news_content):
    """뉴스 내용을 파일에 저장"""
    logging.info(f"save_news_to_file: Starting to save news to {NEWS_FILE_PATH}")
    try:
        today_date = get_today_date_str()
        news_length = len(news_content) if news_content else 0
        logging.info(f"save_news_to_file: Date={today_date}, Content length={news_length} characters")
        
        with open(NEWS_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(f"=== {today_date} ===\n\n")
            f.write(news_content)
        
        # 저장 후 파일 크기 확인
        file_size = os.path.getsize(NEWS_FILE_PATH) if os.path.exists(NEWS_FILE_PATH) else 0
        logging.info(f"save_news_to_file: Successfully saved news to file. File size={file_size} bytes")
    except Exception as e:
        logging.error(f"save_news_to_file: Error saving news to file: {type(e).__name__}: {str(e)}", exc_info=True)
        raise

def get_news_from_file():
    """뉴스 파일에서 내용을 읽어옴"""
    logging.info(f"get_news_from_file: Checking file at {NEWS_FILE_PATH}")
    try:
        if not os.path.exists(NEWS_FILE_PATH):
            logging.info(f"get_news_from_file: File does not exist at {NEWS_FILE_PATH}")
            return None
        
        logging.info(f"get_news_from_file: File exists, reading content...")
        with open(NEWS_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
            content_length = len(content)
            logging.info(f"get_news_from_file: Read {content_length} characters from file")
            
            # 첫 번째 줄(날짜) 제거
            lines = content.split('\n')
            logging.info(f"get_news_from_file: File has {len(lines)} lines")
            if len(lines) > 1:
                news_content = '\n'.join(lines[2:])  # 날짜 줄과 빈 줄 제거
                news_length = len(news_content) if news_content else 0
                logging.info(f"get_news_from_file: Extracted news content length={news_length} characters")
                return news_content
        logging.info(f"get_news_from_file: File has insufficient lines (<=1)")
        return None
    except Exception as e:
        logging.error(f"get_news_from_file: Error reading news from file: {type(e).__name__}: {str(e)}", exc_info=True)
        return None

def update_news_with_tavily(compiled, force_update=False):
    """Tavily를 사용하여 뉴스를 수집하고 저장"""
    logging.info(f"update_news_with_tavily: Starting update (force_update={force_update})")
    try:
        # 강제 업데이트가 아니고 오늘 날짜의 뉴스가 이미 있으면 업데이트하지 않음
        if not force_update:
            logging.info("update_news_with_tavily: Checking if news for today already exists...")
            if is_news_today():
                logging.info("update_news_with_tavily: News for today already exists, skipping update")
                return {
                    "status": "already_exists",
                    "message": "News for today already exists"
                }
            else:
                logging.info("update_news_with_tavily: No news for today found, proceeding with update")
        else:
            logging.info("update_news_with_tavily: Force update requested, proceeding with update")
        
        # 뉴스 수집
        logging.info("update_news_with_tavily: Starting news collection with Tavily API...")
        logging.info("update_news_with_tavily: Initializing state and invoking compiled graph...")
        
        # State 초기화 - messages를 빈 리스트로 초기화
        initial_state = {"messages": []}
        
        try:
            logging.info("update_news_with_tavily: Calling compiled.invoke()...")
            final_state = compiled.invoke(initial_state)
            logging.info(f"update_news_with_tavily: Graph execution completed. Messages count: {len(final_state.get('messages', []))}")
            
            if not final_state.get('messages'):
                logging.error("update_news_with_tavily: No messages in final state")
                raise Exception("No messages returned from news collection")
            
            last_message = final_state['messages'][-1]
            logging.info(f"update_news_with_tavily: Last message type: {type(last_message).__name__}")
            
            if not hasattr(last_message, 'content'):
                logging.error(f"update_news_with_tavily: Last message has no content attribute. Message: {last_message}")
                raise Exception("Last message has no content")
            
            news_content = last_message.content
            news_length = len(news_content) if news_content else 0
            logging.info(f"update_news_with_tavily: Extracted news content, length={news_length} characters")
            
            if not news_content or news_length == 0:
                logging.error("update_news_with_tavily: News content is empty")
                raise Exception("News content is empty")
            
        except Exception as invoke_error:
            logging.error(f"update_news_with_tavily: Error during graph invocation: {type(invoke_error).__name__}: {str(invoke_error)}", exc_info=True)
            raise
        
        # 파일에 저장
        logging.info("update_news_with_tavily: Saving news to file...")
        save_news_to_file(news_content)
        
        logging.info("update_news_with_tavily: News update completed successfully")
        return {
            "status": "success",
            "message": "News updated successfully"
        }
    except Exception as e:
        logging.error(f"update_news_with_tavily: Error updating daily news: {type(e).__name__}: {str(e)}", exc_info=True)
        raise

def get_news_with_date():
    """뉴스와 날짜 정보를 함께 반환"""
    logging.info("get_news_with_date: Starting to get news with date")
    file_date = get_news_date_from_file()
    today_date = get_today_date_str()
    news_content = get_news_from_file()
    
    result = {
        "news": news_content,
        "date": file_date,
        "is_today": file_date == today_date if file_date else False
    }
    
    logging.info(f"get_news_with_date: Result - news exists={news_content is not None}, date={file_date}, is_today={result['is_today']}")
    return result

