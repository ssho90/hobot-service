"""
TradingEconomics 뉴스 수집 테스트 스크립트 (DB 없이 실행)
"""
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NewsCollectorTester:
    """DB 없이 뉴스 수집 테스트 클래스"""
    
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
        """TradingEconomics 스트림 페이지 HTML 가져오기"""
        if use_selenium:
            return self._fetch_with_selenium()
        else:
            return self._fetch_with_requests()
    
    def _fetch_with_requests(self) -> Optional[str]:
        """requests를 사용하여 HTML 가져오기"""
        try:
            logger.info(f"페이지 요청: {self.STREAM_URL}")
            response = self.session.get(self.STREAM_URL, timeout=self.timeout)
            response.raise_for_status()
            logger.info(f"응답 성공 (상태 코드: {response.status_code})")
            html = response.text
            
            # 디버깅: HTML을 파일로 저장 (선택적)
            save_html = input("\nHTML을 파일로 저장하시겠습니까? (y/n): ").lower() == 'y'
            if save_html:
                html_file = "tradingeconomics_stream.html"
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"✅ HTML이 {html_file}에 저장되었습니다.")
                print(f"   파일 크기: {len(html)} bytes")
                print(f"   'stream' 문자열 포함 여부: {'stream' in html}")
                print(f"   'te-stream-item' 문자열 포함 여부: {'te-stream-item' in html}")
            
            return html
        except requests.exceptions.RequestException as e:
            logger.error(f"페이지 요청 실패: {e}")
            return None
    
    def _fetch_with_selenium(self) -> Optional[str]:
        """Selenium을 사용하여 JavaScript 렌더링된 HTML 가져오기"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException
        except ImportError:
            print("❌ Selenium이 설치되지 않았습니다.")
            print("   설치: pip install selenium")
            print("   ChromeDriver도 필요합니다: https://chromedriver.chromium.org/")
            return None
        
        driver = None
        try:
            print("🌐 Selenium을 사용하여 페이지 로드 중...")
            
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
                print("✅ stream div 로드 완료")
                
                # 추가로 뉴스 항목이 로드될 때까지 대기
                WebDriverWait(driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "li.te-stream-item")) > 0
                )
                print(f"✅ 뉴스 항목 로드 완료 ({len(driver.find_elements(By.CSS_SELECTOR, 'li.te-stream-item'))}개)")
            except TimeoutException:
                print("⚠️  뉴스 항목 로드 타임아웃 (일부만 로드되었을 수 있음)")
            
            html = driver.page_source
            
            # 디버깅: HTML을 파일로 저장
            save_html = input("\nHTML을 파일로 저장하시겠습니까? (y/n): ").lower() == 'y'
            if save_html:
                html_file = "tradingeconomics_stream_selenium.html"
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"✅ HTML이 {html_file}에 저장되었습니다.")
                print(f"   파일 크기: {len(html)} bytes")
            
            return html
            
        except Exception as e:
            print(f"❌ Selenium 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if driver:
                driver.quit()
    
    def parse_news_items(self, html: str) -> List[Dict]:
        """HTML에서 뉴스 항목 파싱"""
        soup = BeautifulSoup(html, 'html.parser')
        news_items = []
        
        # 방법 1: div#stream 안에서 찾기
        stream_div = soup.find('div', id='stream')
        if stream_div:
            print("✅ div#stream을 찾았습니다.")
            # stream div 안에서 li 요소 찾기
            stream_items = stream_div.find_all('li', class_=re.compile(r'te-stream-item', re.I))
            print(f"   div#stream 안에서 {len(stream_items)}개의 li 요소를 찾았습니다.")
        else:
            print("⚠️  div#stream을 찾을 수 없습니다.")
            stream_items = []
        
        # 방법 2: stream div가 없거나 결과가 없으면 전체 문서에서 찾기
        if not stream_items:
            print("전체 문서에서 te-stream-item 클래스를 가진 요소를 찾습니다.")
            stream_items = soup.find_all('li', class_=re.compile(r'te-stream-item', re.I))
            print(f"   전체 문서에서 {len(stream_items)}개의 li 요소를 찾았습니다.")
        
        # 방법 3: 클래스 이름을 정확히 매칭
        if not stream_items:
            print("정확한 클래스 이름으로 찾습니다.")
            stream_items = soup.find_all('li', class_=lambda x: x and 'te-stream-item' in ' '.join(x))
            print(f"   정확한 클래스 매칭으로 {len(stream_items)}개의 li 요소를 찾았습니다.")
        
        # 방법 4: list-group-item과 함께 찾기
        if not stream_items:
            print("list-group-item 클래스를 가진 li 요소를 찾습니다.")
            stream_items = soup.find_all('li', class_=lambda x: x and 'list-group-item' in ' '.join(x))
            print(f"   list-group-item으로 {len(stream_items)}개의 li 요소를 찾았습니다.")
        
        logger.info(f"파싱된 뉴스 항목 수: {len(stream_items)}")
        
        # 디버깅: 첫 번째 항목의 HTML 구조 확인
        if stream_items and len(stream_items) > 0:
            first_item = stream_items[0]
            print(f"\n🔍 첫 번째 항목 분석:")
            print(f"   클래스: {first_item.get('class', [])}")
            print(f"   ID: {first_item.get('id', 'N/A')}")
            print(f"   HTML (처음 500자):\n{str(first_item)[:500]}\n")
        else:
            print("\n⚠️  뉴스 항목을 찾을 수 없습니다. HTML 구조를 확인합니다...")
            # stream div가 있는지 확인
            if stream_div:
                print(f"   stream div의 자식 요소 수: {len(list(stream_div.children))}")
                print(f"   stream div의 직접 자식 li 수: {len(stream_div.find_all('li', recursive=False))}")
                print(f"   stream div의 모든 li 수: {len(stream_div.find_all('li'))}")
        
        for item in stream_items:
            try:
                news_item = self._extract_news_item(item)
                if news_item:
                    news_items.append(news_item)
                else:
                    print(f"   ⚠️  뉴스 항목 추출 실패 (제목을 찾을 수 없음)")
            except Exception as e:
                logger.warning(f"뉴스 항목 파싱 실패: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return news_items
    
    def _extract_news_item(self, element) -> Optional[Dict]:
        """개별 뉴스 항목에서 정보 추출"""
        try:
            # 제목 추출: <a class="te-stream-title-2">
            title_elem = element.find('a', class_=re.compile(r'te-stream-title', re.I))
            if not title_elem:
                # 디버깅: 왜 제목을 찾지 못했는지 확인
                all_links = element.find_all('a')
                print(f"   ⚠️  제목 링크를 찾을 수 없음. 전체 링크 수: {len(all_links)}")
                if all_links:
                    print(f"   첫 번째 링크 클래스: {all_links[0].get('class', [])}")
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
                'date_text': date_text
            }
        except Exception as e:
            logger.debug(f"뉴스 항목 추출 중 오류: {e}")
            return None
    
    def _parse_date_text(self, date_text: str) -> Optional[datetime]:
        """날짜 텍스트를 datetime 객체로 변환"""
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
        
        return None
    
    def filter_recent_news(self, news_items: List[Dict], hours: int = 2) -> List[Dict]:
        """2시간 이내의 뉴스만 필터링"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered = []
        
        for item in news_items:
            published_at = item.get('published_at')
            if published_at and published_at >= cutoff_time:
                filtered.append(item)
            elif not published_at:
                logger.debug(f"날짜 정보가 없는 뉴스 제외: {item.get('title', 'Unknown')}")
                continue
        
        logger.info(f"{hours}시간 이내 뉴스: {len(filtered)}개")
        return filtered
    
    def print_news_item(self, item: Dict, index: int):
        """뉴스 항목을 보기 좋게 출력"""
        print("\n" + "=" * 80)
        print(f"[{index}] {item.get('title', 'No Title')}")
        print("-" * 80)
        
        if item.get('country'):
            print(f"국가: {item['country']}")
        if item.get('category'):
            print(f"카테고리: {item['category']}")
        if item.get('date_text'):
            print(f"발행 시간: {item['date_text']} ({item.get('published_at')})")
        if item.get('link'):
            print(f"링크: {item['link']}")
        if item.get('description'):
            desc = item['description']
            if len(desc) > 200:
                desc = desc[:200] + "..."
            print(f"본문: {desc}")
    
    def test_collect_news(self, hours: int = 2, use_selenium: bool = False):
        """뉴스 수집 테스트 실행"""
        print("\n" + "=" * 80)
        print("TradingEconomics 뉴스 수집 테스트 시작")
        print("=" * 80)
        
        # 1. 페이지 가져오기
        html = self.fetch_stream_page(use_selenium=use_selenium)
        if not html:
            print("❌ 페이지를 가져올 수 없습니다.")
            return
        
        # HTML 기본 정보 출력
        print(f"\n📄 HTML 정보:")
        print(f"   전체 길이: {len(html)} bytes")
        print(f"   'stream' 포함: {'stream' in html}")
        print(f"   'te-stream-item' 포함: {'te-stream-item' in html}")
        print(f"   'list-group-item' 포함: {'list-group-item' in html}")
        
        # 2. 뉴스 파싱
        print("\n[1단계] 뉴스 파싱 중...")
        news_items = self.parse_news_items(html)
        print(f"✅ 총 {len(news_items)}개의 뉴스 항목을 파싱했습니다.")
        
        if not news_items:
            print("❌ 파싱된 뉴스가 없습니다.")
            return
        
        # 3. 최근 뉴스 필터링
        print(f"\n[2단계] {hours}시간 이내 뉴스 필터링 중...")
        recent_news = self.filter_recent_news(news_items, hours=hours)
        print(f"✅ {hours}시간 이내 뉴스: {len(recent_news)}개")
        
        # 4. 결과 출력
        print("\n[3단계] 수집된 뉴스 목록:")
        print("=" * 80)
        
        if recent_news:
            for idx, item in enumerate(recent_news, 1):
                self.print_news_item(item, idx)
        else:
            print(f"❌ {hours}시간 이내의 뉴스가 없습니다.")
        
        # 5. 통계 출력
        print("\n" + "=" * 80)
        print("수집 통계:")
        print(f"  - 전체 파싱된 뉴스: {len(news_items)}개")
        print(f"  - {hours}시간 이내 뉴스: {len(recent_news)}개")
        
        # 국가별 통계
        countries = {}
        for item in recent_news:
            country = item.get('country', 'Unknown')
            countries[country] = countries.get(country, 0) + 1
        
        if countries:
            print("\n국가별 뉴스 수:")
            for country, count in sorted(countries.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {country}: {count}개")
        
        # 카테고리별 통계
        categories = {}
        for item in recent_news:
            category = item.get('category', 'Unknown')
            categories[category] = categories.get(category, 0) + 1
        
        if categories:
            print("\n카테고리별 뉴스 수:")
            for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {category}: {count}개")
        
        print("=" * 80)
        print("\n✅ 테스트 완료!")


def main():
    """메인 함수"""
    tester = NewsCollectorTester()
    
    # Selenium 사용 여부 확인
    print("\n" + "=" * 80)
    use_selenium = input("Selenium을 사용하시겠습니까? (JavaScript 렌더링 필요, y/n): ").lower() == 'y'
    
    # 2시간 이내 뉴스 수집 테스트
    tester.test_collect_news(hours=2, use_selenium=use_selenium)
    
    # 추가 옵션: 전체 뉴스 확인 (필터링 없이)
    print("\n" + "=" * 80)
    response = input("전체 뉴스 목록도 확인하시겠습니까? (y/n): ")
    if response.lower() == 'y':
        html = tester.fetch_stream_page()
        if html:
            news_items = tester.parse_news_items(html)
            print(f"\n전체 뉴스: {len(news_items)}개")
            for idx, item in enumerate(news_items[:10], 1):  # 최대 10개만 출력
                tester.print_news_item(item, idx)
            if len(news_items) > 10:
                print(f"\n... 외 {len(news_items) - 10}개 더 있음")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n테스트가 중단되었습니다.")
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

