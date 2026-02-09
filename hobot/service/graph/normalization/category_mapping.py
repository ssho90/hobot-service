"""
Phase B-3: Category Mapping
TradingEconomics 카테고리 → 내부 taxonomy 매핑
"""

from typing import Optional, Dict, List

# TradingEconomics 카테고리 → 내부 MacroTheme 매핑
CATEGORY_TO_THEME: Dict[str, str] = {
    # Interest Rates & Monetary Policy → rates
    "interest rate": "rates",
    "interest rates": "rates",
    "central bank": "rates",
    "monetary policy": "rates",
    "fed": "rates",
    "federal reserve": "rates",
    "ecb": "rates",
    "boj": "rates",
    "bank of england": "rates",
    "pboc": "rates",
    "treasury": "rates",
    "bond": "rates",
    "bonds": "rates",
    "yield": "rates",
    "yields": "rates",
    
    # Inflation → inflation
    "inflation": "inflation",
    "cpi": "inflation",
    "consumer price": "inflation",
    "ppi": "inflation",
    "producer price": "inflation",
    "pce": "inflation",
    "core inflation": "inflation",
    "deflation": "inflation",
    "price index": "inflation",
    
    # Growth & GDP → growth
    "gdp": "growth",
    "growth": "growth",
    "economic growth": "growth",
    "recession": "growth",
    "expansion": "growth",
    "manufacturing": "growth",
    "pmi": "growth",
    "industrial production": "growth",
    "retail sales": "growth",
    "consumer spending": "growth",
    "leading indicators": "growth",
    "business confidence": "growth",
    
    # Labor Market → labor
    "employment": "labor",
    "unemployment": "labor",
    "jobs": "labor",
    "labor": "labor",
    "labour": "labor",
    "payrolls": "labor",
    "nonfarm": "labor",
    "wage": "labor",
    "wages": "labor",
    "jobless claims": "labor",
    "hiring": "labor",
    
    # Liquidity → liquidity
    "liquidity": "liquidity",
    "fed balance sheet": "liquidity",
    "quantitative easing": "liquidity",
    "qe": "liquidity",
    "qt": "liquidity",
    "quantitative tightening": "liquidity",
    "repo": "liquidity",
    "reverse repo": "liquidity",
    "tga": "liquidity",
    "treasury general account": "liquidity",
    "money supply": "liquidity",
    "m2": "liquidity",
    
    # Risk & Volatility → risk
    "risk": "risk",
    "volatility": "risk",
    "vix": "risk",
    "credit spread": "risk",
    "high yield": "risk",
    "junk bonds": "risk",
    "stress": "risk",
    "financial stress": "risk",
    "credit": "risk",
    "default": "risk",
    "spreads": "risk",
}

# 내부 Theme 정보
THEME_INFO: Dict[str, Dict] = {
    "rates": {
        "theme_id": "rates",
        "name": "Interest Rates & Bonds",
        "description": "금리, 채권, 통화정책 관련"
    },
    "inflation": {
        "theme_id": "inflation",
        "name": "Inflation & Prices",
        "description": "물가, 인플레이션 관련"
    },
    "growth": {
        "theme_id": "growth",
        "name": "Economic Growth",
        "description": "GDP, 경기, 성장 관련"
    },
    "labor": {
        "theme_id": "labor",
        "name": "Labor Market",
        "description": "고용, 실업, 임금 관련"
    },
    "liquidity": {
        "theme_id": "liquidity",
        "name": "Liquidity & Money Supply",
        "description": "유동성, 통화공급 관련"
    },
    "risk": {
        "theme_id": "risk",
        "name": "Risk & Volatility",
        "description": "리스크, 변동성 관련"
    },
}

# 역매핑: Theme → 관련 키워드들
THEME_KEYWORDS: Dict[str, List[str]] = {
    theme_id: [k for k, v in CATEGORY_TO_THEME.items() if v == theme_id]
    for theme_id in THEME_INFO.keys()
}


def normalize_category(raw_category: str) -> Optional[str]:
    """
    원문 카테고리를 내부 MacroTheme ID로 변환
    
    Args:
        raw_category: 원문 카테고리 (예: "Interest Rate", "GDP", "Inflation")
    
    Returns:
        내부 theme_id 또는 None
    """
    if not raw_category:
        return None
    
    normalized = raw_category.lower().strip()
    
    # 직접 매핑 확인
    if normalized in CATEGORY_TO_THEME:
        return CATEGORY_TO_THEME[normalized]
    
    # 부분 문자열 매칭
    for key, theme_id in CATEGORY_TO_THEME.items():
        if key in normalized or normalized in key:
            return theme_id
    
    return None


def get_theme_info(theme_id: str) -> Optional[Dict]:
    """
    Theme ID로 상세 정보 조회
    """
    return THEME_INFO.get(theme_id)


def get_related_themes(text: str) -> List[str]:
    """
    텍스트에서 관련된 모든 Theme 추출
    
    Args:
        text: 분석할 텍스트
    
    Returns:
        관련된 theme_id 리스트 (중복 제거)
    """
    if not text:
        return []
    
    text_lower = text.lower()
    themes = set()
    
    for keyword, theme_id in CATEGORY_TO_THEME.items():
        if keyword in text_lower:
            themes.add(theme_id)
    
    return list(themes)


def add_category_mapping(raw_category: str, theme_id: str):
    """
    새로운 카테고리 매핑 추가 (런타임 확장)
    """
    if theme_id not in THEME_INFO:
        raise ValueError(f"Unknown theme_id: {theme_id}")
    CATEGORY_TO_THEME[raw_category.lower().strip()] = theme_id
