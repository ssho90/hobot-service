"""
TradingEconomics 스트림 뉴스 수집 모듈
2시간 이내의 경제 뉴스를 수집하여 economic_news 테이블에 저장
"""
import os
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# Selenium (선택적, JavaScript 렌더링이 필요한 경우)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from service.database.db import get_db_connection

logger = logging.getLogger(__name__)


class NewsCollectorError(Exception):
    """뉴스 수집 관련 오류"""
    pass


class NewsCollector:
    """TradingEconomics 스트림 뉴스 수집 클래스"""
    
    BASE_URL = "https://tradingeconomics.com"
    STREAM_URL = "https://tradingeconomics.com/stream"
    
    def __init__(self):
        """초기화"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.timeout = 30
    
    def fetch_stream_page(self, use_selenium: bool = False) -> Optional[str]:
        """
        TradingEconomics 스트림 페이지 HTML 가져오기
        
        Args:
            use_selenium: Selenium을 사용하여 JavaScript 렌더링된 HTML 가져오기
        
        Returns:
            HTML 문자열 또는 None (실패 시)
        """
        if use_selenium and SELENIUM_AVAILABLE:
            return self._fetch_with_selenium()
        else:
            return self._fetch_with_requests()
    
    def _fetch_with_requests(self) -> Optional[str]:
        """requests를 사용하여 HTML 가져오기"""
        try:
            logger.info(f"TradingEconomics 스트림 페이지 요청: {self.STREAM_URL}")
            response = self.session.get(self.STREAM_URL, timeout=self.timeout)
            response.raise_for_status()
            logger.info(f"페이지 응답 성공 (상태 코드: {response.status_code})")
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"페이지 요청 실패: {e}")
            raise NewsCollectorError(f"페이지 요청 실패: {e}")
    
    def _fetch_with_selenium(self) -> Optional[str]:
        """Selenium을 사용하여 JavaScript 렌더링된 HTML 가져오기"""
        if not SELENIUM_AVAILABLE:
            logger.warning("Selenium이 설치되지 않았습니다. pip install selenium으로 설치하세요.")
            return None
        
        driver = None
        try:
            logger.info("Selenium을 사용하여 페이지 로드 중...")
            
            # Chrome 옵션 설정
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 헤드리스 모드
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(self.STREAM_URL)
            
            # stream div가 로드될 때까지 대기 (최대 30초)
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.ID, "stream"))
                )
                # 추가로 뉴스 항목이 로드될 때까지 대기
                WebDriverWait(driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "li.te-stream-item")) > 0
                )
                logger.info("뉴스 항목 로드 완료")
            except TimeoutException:
                logger.warning("뉴스 항목 로드 타임아웃 (일부만 로드되었을 수 있음)")
            
            html = driver.page_source
            logger.info(f"Selenium으로 HTML 가져오기 성공 (길이: {len(html)} bytes)")
            return html
            
        except Exception as e:
            logger.error(f"Selenium으로 페이지 가져오기 실패: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def parse_news_items(self, html: str) -> List[Dict]:
        """
        HTML에서 뉴스 항목 파싱
        
        Args:
            html: HTML 문자열
            
        Returns:
            뉴스 항목 리스트 (각 항목은 dict)
        """
        soup = BeautifulSoup(html, 'html.parser')
        news_items = []
        
        # 방법 1: div#stream 안에서 찾기
        stream_div = soup.find('div', id='stream')
        if stream_div:
            logger.debug("div#stream을 찾았습니다.")
            # stream div 안에서 li 요소 찾기
            stream_items = stream_div.find_all('li', class_=re.compile(r'te-stream-item', re.I))
            logger.debug(f"div#stream 안에서 {len(stream_items)}개의 li 요소를 찾았습니다.")
        else:
            logger.warning("div#stream을 찾을 수 없습니다.")
            stream_items = []
        
        # 방법 2: stream div가 없거나 결과가 없으면 전체 문서에서 찾기
        if not stream_items:
            logger.debug("전체 문서에서 te-stream-item 클래스를 가진 요소를 찾습니다.")
            stream_items = soup.find_all('li', class_=re.compile(r'te-stream-item', re.I))
            logger.debug(f"전체 문서에서 {len(stream_items)}개의 li 요소를 찾았습니다.")
        
        # 방법 3: 클래스 이름을 정확히 매칭
        if not stream_items:
            logger.debug("정확한 클래스 이름으로 찾습니다.")
            stream_items = soup.find_all('li', class_=lambda x: x and 'te-stream-item' in ' '.join(x))
            logger.debug(f"정확한 클래스 매칭으로 {len(stream_items)}개의 li 요소를 찾았습니다.")
        
        # 방법 4: list-group-item과 함께 찾기
        if not stream_items:
            logger.debug("list-group-item 클래스를 가진 li 요소를 찾습니다.")
            stream_items = soup.find_all('li', class_=lambda x: x and 'list-group-item' in ' '.join(x))
            logger.debug(f"list-group-item으로 {len(stream_items)}개의 li 요소를 찾았습니다.")
        
        logger.info(f"파싱된 뉴스 항목 수: {len(stream_items)}")
        
        # 디버깅: 첫 번째 항목의 HTML 구조 확인
        if stream_items and len(stream_items) > 0:
            first_item = stream_items[0]
            logger.debug(f"첫 번째 항목 클래스: {first_item.get('class', [])}")
            logger.debug(f"첫 번째 항목 HTML (처음 500자): {str(first_item)[:500]}")
        
        for item in stream_items:
            try:
                news_item = self._extract_news_item(item)
                if news_item:
                    news_items.append(news_item)
                else:
                    logger.debug(f"뉴스 항목 추출 실패 (제목을 찾을 수 없음)")
            except Exception as e:
                logger.warning(f"뉴스 항목 파싱 실패: {e}")
                continue
        
        return news_items
    
    def _extract_news_item(self, element) -> Optional[Dict]:
        """
        개별 뉴스 항목에서 정보 추출
        
        실제 HTML 구조:
        - 제목: <a class="te-stream-title-2" href="..."><b>제목</b></a>
        - 국가: <a class="badge small te-stream-country" href="...">United States</a>
        - 카테고리: <a class="badge small te-stream-category" href="...">Stock Market</a>
        - 본문: <span class="te-stream-item-description">...</span>
        - 날짜: <small class="te-stream-item-date">14 hours ago</small>
        
        Args:
            element: BeautifulSoup 요소
            
        Returns:
            뉴스 정보 dict 또는 None
        """
        try:
            # 제목 추출: <a class="te-stream-title-2">
            title_elem = element.find('a', class_=re.compile(r'te-stream-title', re.I))
            if not title_elem:
                return None
            
            # <b> 태그 안의 텍스트 또는 직접 텍스트
            title_b = title_elem.find('b')
            if title_b:
                title = title_b.get_text(strip=True)
            else:
                title = title_elem.get_text(strip=True)
            
            if not title:
                return None
            
            # 링크 추출
            link = title_elem.get('href', '')
            if link and not link.startswith('http'):
                link = urljoin(self.BASE_URL, link)
            
            # 국가 추출: <a class="badge small te-stream-country">
            country_elem = element.find('a', class_=re.compile(r'te-stream-country', re.I))
            country = country_elem.get_text(strip=True) if country_elem else None
            
            # 카테고리 추출: <a class="badge small te-stream-category">
            category_elem = element.find('a', class_=re.compile(r'te-stream-category', re.I))
            category = category_elem.get_text(strip=True) if category_elem else None
            
            # 본문 추출: <span class="te-stream-item-description">
            description_elem = element.find('span', class_=re.compile(r'te-stream-item-description', re.I))
            description = description_elem.get_text(strip=True) if description_elem else None
            
            # 날짜 추출: <small class="te-stream-item-date">
            date_elem = element.find('small', class_=re.compile(r'te-stream-item-date', re.I))
            date_text = date_elem.get_text(strip=True) if date_elem else None
            
            # 날짜 파싱
            published_at = None
            if date_text:
                published_at = self._parse_date_text(date_text)
            
            return {
                'title': title,
                'link': link,
                'country': country,
                'category': category,
                'description': description,
                'published_at': published_at,
                'date_text': date_text  # 디버깅용
            }
        except Exception as e:
            logger.debug(f"뉴스 항목 추출 중 오류: {e}")
            return None
    
    def _parse_date_text(self, date_text: str) -> Optional[datetime]:
        """
        날짜 텍스트를 datetime 객체로 변환
        
        Args:
            date_text: 날짜 문자열 (예: "2 hours ago", "14 hours ago")
            
        Returns:
            datetime 객체 또는 None
        """
        if not date_text:
            return None
        
        date_text = date_text.strip().lower()
        now = datetime.now()
        
        # "X hours ago" 형식
        hours_match = re.search(r'(\d+)\s*hours?\s*ago', date_text)
        if hours_match:
            hours = int(hours_match.group(1))
            return now - timedelta(hours=hours)
        
        # "X minutes ago" 형식
        minutes_match = re.search(r'(\d+)\s*minutes?\s*ago', date_text)
        if minutes_match:
            minutes = int(minutes_match.group(1))
            return now - timedelta(minutes=minutes)
        
        # "X days ago" 형식
        days_match = re.search(r'(\d+)\s*days?\s*ago', date_text)
        if days_match:
            days = int(days_match.group(1))
            return now - timedelta(days=days)
        
        # 표준 날짜 형식 시도
        date_formats = [
            '%b %d, %Y %I:%M %p',  # "Dec 19, 2024 10:30 AM"
            '%B %d, %Y %I:%M %p',  # "December 19, 2024 10:30 AM"
            '%Y-%m-%d %H:%M:%S',   # "2024-12-19 10:30:00"
            '%Y-%m-%d',            # "2024-12-19"
            '%b %d, %Y',           # "Dec 19, 2024"
            '%B %d, %Y',           # "December 19, 2024"
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_text, fmt)
            except:
                continue
        
        return None
    
    def filter_recent_news(self, news_items: List[Dict], hours: int = 2) -> List[Dict]:
        """
        2시간 이내의 뉴스만 필터링
        
        Args:
            news_items: 뉴스 항목 리스트
            hours: 필터링할 시간 범위 (기본값: 2시간)
            
        Returns:
            필터링된 뉴스 항목 리스트
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered = []
        
        for item in news_items:
            published_at = item.get('published_at')
            if published_at and published_at >= cutoff_time:
                filtered.append(item)
            elif not published_at:
                # 날짜가 없는 경우 제외
                logger.debug(f"날짜 정보가 없는 뉴스 제외: {item.get('title', 'Unknown')}")
                continue
        
        logger.info(f"{hours}시간 이내 뉴스: {len(filtered)}개")
        return filtered
    
    def check_news_exists(self, title: str, link: Optional[str] = None) -> bool:
        """
        뉴스가 이미 DB에 존재하는지 확인
        
        Args:
            title: 뉴스 제목
            link: 뉴스 링크 (선택적)
            
        Returns:
            존재 여부
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                if link:
                    # 제목과 링크로 중복 확인
                    cursor.execute("""
                        SELECT COUNT(*) FROM economic_news
                        WHERE title = %s AND link = %s
                    """, (title, link))
                else:
                    # 제목만으로 중복 확인
                    cursor.execute("""
                        SELECT COUNT(*) FROM economic_news
                        WHERE title = %s
                    """, (title,))
                
                result = cursor.fetchone()
                return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"중복 확인 실패: {e}")
            return False
    
    def save_to_db(self, news_items: List[Dict]) -> Tuple[int, int]:
        """
        뉴스를 DB에 저장
        
        Args:
            news_items: 뉴스 항목 리스트
            
        Returns:
            (저장된 개수, 건너뛴 개수) 튜플
        """
        saved_count = 0
        skipped_count = 0
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for item in news_items:
                    title = item.get('title')
                    if not title:
                        skipped_count += 1
                        continue
                    
                    link = item.get('link')
                    
                    # 중복 확인
                    if self.check_news_exists(title, link):
                        skipped_count += 1
                        logger.debug(f"중복 뉴스 건너뜀: {title[:50]}...")
                        continue
                    
                    try:
                        cursor.execute("""
                            INSERT INTO economic_news
                            (title, link, country, category, description, published_at, source)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            title,
                            link,
                            item.get('country'),
                            item.get('category'),
                            item.get('description'),
                            item.get('published_at'),
                            'TradingEconomics Stream'
                        ))
                        saved_count += 1
                        logger.debug(f"뉴스 저장: {title[:50]}...")
                    except Exception as e:
                        logger.warning(f"뉴스 저장 실패 ({title[:50]}...): {e}")
                        skipped_count += 1
                        continue
                
                conn.commit()
                logger.info(f"뉴스 저장 완료: {saved_count}개 저장, {skipped_count}개 건너뜀")
                return saved_count, skipped_count
                
        except Exception as e:
            logger.error(f"DB 저장 중 오류: {e}")
            raise NewsCollectorError(f"DB 저장 실패: {e}")
    
    def collect_recent_news(self, hours: int = 2, use_selenium: bool = False) -> Tuple[int, int]:
        """
        최근 뉴스 수집 및 저장 (메인 메서드)
        
        Args:
            hours: 수집할 시간 범위 (기본값: 2시간)
            use_selenium: Selenium 사용 여부 (JavaScript 렌더링 필요 시)
            
        Returns:
            (저장된 개수, 건너뛴 개수) 튜플
        """
        try:
            # 1. 페이지 가져오기
            html = self.fetch_stream_page(use_selenium=use_selenium)
            if not html:
                raise NewsCollectorError("페이지를 가져올 수 없습니다")
            
            # 2. 뉴스 파싱
            news_items = self.parse_news_items(html)
            if not news_items:
                logger.warning("파싱된 뉴스가 없습니다")
                return 0, 0
            
            # 3. 최근 뉴스 필터링 (2시간 이내)
            recent_news = self.filter_recent_news(news_items, hours=hours)
            if not recent_news:
                logger.info(f"{hours}시간 이내의 뉴스가 없습니다")
                return 0, 0
            
            # 4. DB에 저장
            saved, skipped = self.save_to_db(recent_news)
            
            return saved, skipped
            
        except Exception as e:
            logger.error(f"뉴스 수집 실패: {e}")
            raise


def get_news_collector() -> NewsCollector:
    """
    NewsCollector 인스턴스 생성 (싱글톤 패턴)
    
    Returns:
        NewsCollector 인스턴스
    """
    return NewsCollector()


if __name__ == "__main__":
    # 테스트 실행
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    collector = get_news_collector()
    try:
        saved, skipped = collector.collect_recent_news(hours=2)
        print(f"\n✅ 뉴스 수집 완료: {saved}개 저장, {skipped}개 건너뜀")
    except Exception as e:
        print(f"\n❌ 뉴스 수집 실패: {e}")
        import traceback
        traceback.print_exc()
