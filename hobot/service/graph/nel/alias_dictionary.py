"""
Phase B-5: Alias Dictionary
Entity의 다양한 표기법을 canonical_id로 매핑하는 사전
"""

from typing import Optional, Dict, List, Tuple
import re

# Alias → canonical Entity 매핑
# Key: 다양한 alias/표기법, Value: (entity_type, canonical_id, canonical_name)
ALIAS_DICTIONARY: Dict[str, Tuple[str, str, str]] = {
    # ============ Central Banks ============
    # Federal Reserve
    "federal reserve": ("Institution", "ENT_FED", "Federal Reserve"),
    "fed": ("Institution", "ENT_FED", "Federal Reserve"),
    "the fed": ("Institution", "ENT_FED", "Federal Reserve"),
    "federal reserve board": ("Institution", "ENT_FED", "Federal Reserve"),
    "fomc": ("Institution", "ENT_FOMC", "Federal Open Market Committee"),
    "federal open market committee": ("Institution", "ENT_FOMC", "Federal Open Market Committee"),
    
    # ECB
    "ecb": ("Institution", "ENT_ECB", "European Central Bank"),
    "european central bank": ("Institution", "ENT_ECB", "European Central Bank"),
    
    # BOJ
    "boj": ("Institution", "ENT_BOJ", "Bank of Japan"),
    "bank of japan": ("Institution", "ENT_BOJ", "Bank of Japan"),
    
    # BOE
    "boe": ("Institution", "ENT_BOE", "Bank of England"),
    "bank of england": ("Institution", "ENT_BOE", "Bank of England"),
    
    # PBOC
    "pboc": ("Institution", "ENT_PBOC", "People's Bank of China"),
    "people's bank of china": ("Institution", "ENT_PBOC", "People's Bank of China"),
    
    # ============ Key Figures ============
    # Jerome Powell
    "jerome powell": ("Person", "ENT_POWELL", "Jerome Powell"),
    "powell": ("Person", "ENT_POWELL", "Jerome Powell"),
    "jay powell": ("Person", "ENT_POWELL", "Jerome Powell"),
    "fed chair powell": ("Person", "ENT_POWELL", "Jerome Powell"),
    "chairman powell": ("Person", "ENT_POWELL", "Jerome Powell"),
    
    # Christine Lagarde
    "christine lagarde": ("Person", "ENT_LAGARDE", "Christine Lagarde"),
    "lagarde": ("Person", "ENT_LAGARDE", "Christine Lagarde"),
    
    # Kazuo Ueda
    "kazuo ueda": ("Person", "ENT_UEDA", "Kazuo Ueda"),
    "ueda": ("Person", "ENT_UEDA", "Kazuo Ueda"),
    
    # Janet Yellen
    "janet yellen": ("Person", "ENT_YELLEN", "Janet Yellen"),
    "yellen": ("Person", "ENT_YELLEN", "Janet Yellen"),
    "treasury secretary yellen": ("Person", "ENT_YELLEN", "Janet Yellen"),
    
    # ============ Government Agencies ============
    "u.s. treasury": ("Institution", "ENT_USTREAS", "U.S. Treasury"),
    "us treasury": ("Institution", "ENT_USTREAS", "U.S. Treasury"),
    "treasury department": ("Institution", "ENT_USTREAS", "U.S. Treasury"),
    
    "bureau of labor statistics": ("Institution", "ENT_BLS", "Bureau of Labor Statistics"),
    "bls": ("Institution", "ENT_BLS", "Bureau of Labor Statistics"),
    
    "bureau of economic analysis": ("Institution", "ENT_BEA", "Bureau of Economic Analysis"),
    "bea": ("Institution", "ENT_BEA", "Bureau of Economic Analysis"),
    
    # ============ Economic Indicators (as Concepts) ============
    "cpi": ("Concept", "IND_CPI", "Consumer Price Index"),
    "consumer price index": ("Concept", "IND_CPI", "Consumer Price Index"),
    
    "pce": ("Concept", "IND_PCE", "Personal Consumption Expenditures"),
    "core pce": ("Concept", "IND_PCEPILFE", "Core PCE"),
    
    "gdp": ("Concept", "IND_GDP", "Gross Domestic Product"),
    "gross domestic product": ("Concept", "IND_GDP", "Gross Domestic Product"),
    
    "nfp": ("Concept", "IND_PAYEMS", "Nonfarm Payrolls"),
    "nonfarm payrolls": ("Concept", "IND_PAYEMS", "Nonfarm Payrolls"),
    "non-farm payrolls": ("Concept", "IND_PAYEMS", "Nonfarm Payrolls"),
    
    "unemployment rate": ("Concept", "IND_UNRATE", "Unemployment Rate"),
    
    "vix": ("Concept", "IND_VIX", "VIX"),
    "volatility index": ("Concept", "IND_VIX", "VIX"),
    "fear index": ("Concept", "IND_VIX", "VIX"),
    
    # ============ Markets & Indices ============
    "s&p 500": ("Index", "IDX_SPX", "S&P 500"),
    "s&p500": ("Index", "IDX_SPX", "S&P 500"),
    "sp500": ("Index", "IDX_SPX", "S&P 500"),
    "spx": ("Index", "IDX_SPX", "S&P 500"),
    
    "dow jones": ("Index", "IDX_DJI", "Dow Jones Industrial Average"),
    "djia": ("Index", "IDX_DJI", "Dow Jones Industrial Average"),
    "the dow": ("Index", "IDX_DJI", "Dow Jones Industrial Average"),
    
    "nasdaq": ("Index", "IDX_IXIC", "NASDAQ Composite"),
    "nasdaq composite": ("Index", "IDX_IXIC", "NASDAQ Composite"),
    
    # ============ Commodities ============
    "wti": ("Commodity", "COM_WTI", "WTI Crude Oil"),
    "wti crude": ("Commodity", "COM_WTI", "WTI Crude Oil"),
    "crude oil": ("Commodity", "COM_WTI", "WTI Crude Oil"),
    
    "brent": ("Commodity", "COM_BRENT", "Brent Crude"),
    "brent crude": ("Commodity", "COM_BRENT", "Brent Crude"),
    
    "gold": ("Commodity", "COM_GOLD", "Gold"),
    "xau": ("Commodity", "COM_GOLD", "Gold"),
    
    # ============ Currencies ============
    "dollar": ("Currency", "CUR_USD", "US Dollar"),
    "usd": ("Currency", "CUR_USD", "US Dollar"),
    "u.s. dollar": ("Currency", "CUR_USD", "US Dollar"),
    
    "euro": ("Currency", "CUR_EUR", "Euro"),
    "eur": ("Currency", "CUR_EUR", "Euro"),
    
    "yen": ("Currency", "CUR_JPY", "Japanese Yen"),
    "jpy": ("Currency", "CUR_JPY", "Japanese Yen"),
}

# 역매핑: canonical_id → aliases
CANONICAL_TO_ALIASES: Dict[str, List[str]] = {}
for alias, (_, canonical_id, _) in ALIAS_DICTIONARY.items():
    if canonical_id not in CANONICAL_TO_ALIASES:
        CANONICAL_TO_ALIASES[canonical_id] = []
    CANONICAL_TO_ALIASES[canonical_id].append(alias)


class AliasLookup:
    """Alias 조회 및 매칭 클래스"""
    
    def __init__(self):
        self.dictionary = ALIAS_DICTIONARY.copy()
        self.unresolved_cache: Dict[str, int] = {}  # 미해결 alias 누적
    
    def lookup(self, mention: str) -> Optional[Tuple[str, str, str]]:
        """
        Mention을 canonical entity로 변환
        
        Args:
            mention: 텍스트에서 추출된 멘션
        
        Returns:
            (entity_type, canonical_id, canonical_name) 또는 None
        """
        if not mention:
            return None
        
        normalized = mention.lower().strip()
        
        # 직접 매칭
        if normalized in self.dictionary:
            return self.dictionary[normalized]
        
        # 정규화된 매칭 (특수문자 제거)
        cleaned = re.sub(r'[^\w\s]', '', normalized)
        if cleaned in self.dictionary:
            return self.dictionary[cleaned]
        
        # 부분 매칭 (한 단어가 다른 것에 포함된 경우)
        for alias, entity_info in self.dictionary.items():
            if alias in normalized or normalized in alias:
                return entity_info
        
        # 미해결 alias 기록
        self._record_unresolved(mention)
        return None
    
    def _record_unresolved(self, mention: str):
        """미해결 alias 누적 기록"""
        normalized = mention.lower().strip()
        self.unresolved_cache[normalized] = self.unresolved_cache.get(normalized, 0) + 1
    
    def add_alias(self, alias: str, entity_type: str, canonical_id: str, canonical_name: str):
        """새로운 alias 추가"""
        self.dictionary[alias.lower().strip()] = (entity_type, canonical_id, canonical_name)
    
    def get_unresolved_stats(self) -> Dict[str, int]:
        """미해결 alias 통계 반환 (빈도순 정렬)"""
        return dict(sorted(self.unresolved_cache.items(), key=lambda x: -x[1]))
    
    def export_unresolved_for_review(self, min_count: int = 3) -> List[str]:
        """
        자주 등장하는 미해결 alias 목록 (수동 매핑 추가용)
        """
        return [
            alias for alias, count in self.unresolved_cache.items()
            if count >= min_count
        ]


# Global instance
_alias_lookup = None

def get_alias_lookup() -> AliasLookup:
    """싱글톤 AliasLookup 인스턴스 반환"""
    global _alias_lookup
    if _alias_lookup is None:
        _alias_lookup = AliasLookup()
    return _alias_lookup
