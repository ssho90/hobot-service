import requests
from bs4 import BeautifulSoup

# List of URLs to crawl
urls = [
    'https://edition.cnn.com/',
    # 'https://edition.cnn.com/politics',
    # 'https://edition.cnn.com/world',
    # 'https://edition.cnn.com/business',
    # 'https://edition.cnn.com/business/investing',
    # #'https://www.reuters.com/technology/',
    # 'https://edition.cnn.com/business/tech',
    # 'https://edition.cnn.com/business/media',
    # 'https://edition.cnn.com/world/asia',
    # 'https://edition.cnn.com/world/europe',
    # 'https://edition.cnn.com/world/china'
]

# Function to crawl and extract the desired text
def crawl_and_extract(url):
    try:
        # Send a request to the URL
        response = requests.get(url, verify=False)
        # Raise an exception if the request was unsuccessful
        response.raise_for_status()

        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all span elements with the specified class
        headlines = soup.find_all('span', class_='container__headline-text', attrs={"data-editable": "headline"})

        extracted_texts = []
        for headline in headlines[:50]:
            extracted_texts.append(headline.get_text())

        return extracted_texts

    except requests.RequestException as e:
        print(f'An error occurred while processing {url}: {e}')
        return []

def get_daily_news():
    # Iterate over each URL and extract the information
    news_list = []
    for url in urls:
        extracted_texts = crawl_and_extract(url)
        
        #print(f'\nExtracted texts from {url}:')

        for text in extracted_texts:
            news_list.append(text)

    news_string = ', ** '.join(news_list)

    return news_string

