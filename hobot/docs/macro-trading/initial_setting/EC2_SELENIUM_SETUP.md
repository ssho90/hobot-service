# EC2에서 Selenium 설정 가이드

EC2 서버에서 TradingEconomics 뉴스 수집을 위한 Selenium 설정 방법입니다.

## 문제

EC2에서 Selenium을 사용할 때 다음과 같은 오류가 발생할 수 있습니다:
```
Message: Service chromedriver unexpectedly exited. Status code was: 127
```

이는 Chrome 브라우저나 ChromeDriver가 제대로 설치되지 않았을 때 발생합니다.

## 해결 방법

### 1. Chrome 브라우저 설치 (Amazon Linux 2)

```bash
# Chrome 저장소 추가
sudo yum install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm

# 또는 wget 사용
wget https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
sudo yum localinstall -y google-chrome-stable_current_x86_64.rpm
```

### 2. Chrome 브라우저 설치 (Ubuntu/Debian)

```bash
# Chrome 저장소 추가
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list

# Chrome 설치
sudo apt-get update
sudo apt-get install -y google-chrome-stable
```

### 3. 필요한 시스템 라이브러리 설치

```bash
# Amazon Linux 2
sudo yum install -y \
    gtk3 \
    libXScrnSaver \
    alsa-lib \
    xorg-x11-server-Xvfb

# Ubuntu/Debian
sudo apt-get install -y \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    xvfb
```

### 4. Python 패키지 설치

```bash
pip install selenium webdriver-manager
```

`webdriver-manager`는 ChromeDriver를 자동으로 다운로드하고 관리합니다.

### 5. Chrome 버전 확인

```bash
google-chrome --version
```

## 대안: requests로 폴백

Selenium이 실패하면 자동으로 `requests`로 폴백합니다. 하지만 JavaScript로 동적 로드되는 페이지는 제대로 파싱되지 않을 수 있습니다.

Selenium을 사용하지 않으려면:
```bash
python -m service.macro_trading.scripts.initial_data_load --skip-fred --no-selenium
```

## 테스트

설치 후 테스트:
```bash
python -m service.macro_trading.tests.test_news_collector_no_db
```

## 참고

- Chrome은 헤드리스 모드로 실행되므로 디스플레이가 필요 없습니다.
- `webdriver-manager`는 ChromeDriver를 자동으로 다운로드하므로 별도 설치가 필요 없습니다.
- 메모리 사용량이 많으므로 EC2 인스턴스의 메모리가 충분한지 확인하세요 (최소 2GB 권장).

