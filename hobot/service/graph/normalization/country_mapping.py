"""
Phase B-3: Country Mapping
원문 국가명 → ISO 3166-1 alpha-2 코드 매핑
"""

from typing import Optional, Dict

# ISO 3166-1 alpha-2 Country Code 매핑
# Key: 다양한 원문 표현, Value: ISO 코드
COUNTRY_MAPPING: Dict[str, str] = {
    # United States
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "u.s.": "US",
    "u.s": "US",
    "america": "US",
    "the us": "US",
    "the united states": "US",
    
    # China
    "china": "CN",
    "people's republic of china": "CN",
    "prc": "CN",
    "mainland china": "CN",
    
    # Japan
    "japan": "JP",
    "nippon": "JP",
    
    # European Union (유럽연합 전체)
    "european union": "EU",
    "eu": "EU",
    "eurozone": "EU",
    "euro area": "EU",
    "euro zone": "EU",
    
    # Germany
    "germany": "DE",
    "deutschland": "DE",
    
    # United Kingdom
    "united kingdom": "GB",
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "great britain": "GB",
    "england": "GB",
    
    # France
    "france": "FR",
    
    # Italy
    "italy": "IT",
    
    # Spain
    "spain": "ES",
    
    # Canada
    "canada": "CA",
    
    # Australia
    "australia": "AU",
    
    # South Korea
    "south korea": "KR",
    "korea": "KR",
    "republic of korea": "KR",
    
    # India
    "india": "IN",
    
    # Brazil
    "brazil": "BR",
    
    # Russia
    "russia": "RU",
    "russian federation": "RU",
    
    # Mexico
    "mexico": "MX",
    
    # Switzerland
    "switzerland": "CH",
    
    # Netherlands
    "netherlands": "NL",
    "holland": "NL",
    
    # Sweden
    "sweden": "SE",
    
    # Norway
    "norway": "NO",
    
    # New Zealand
    "new zealand": "NZ",
    
    # Singapore
    "singapore": "SG",
    
    # Hong Kong
    "hong kong": "HK",
    
    # Taiwan
    "taiwan": "TW",
    
    # Turkey
    "turkey": "TR",
    "türkiye": "TR",
    
    # Saudi Arabia
    "saudi arabia": "SA",
    
    # South Africa
    "south africa": "ZA",
    
    # Argentina
    "argentina": "AR",
    
    # Indonesia
    "indonesia": "ID",
    
    # Thailand
    "thailand": "TH",
    
    # Vietnam
    "vietnam": "VN",
    
    # Malaysia
    "malaysia": "MY",
    
    # Philippines
    "philippines": "PH",
    
    # Global/World (특수 케이스)
    "global": "GLOBAL",
    "world": "GLOBAL",
    "worldwide": "GLOBAL",
    "international": "GLOBAL",
}

# ISO 코드 → 국가명 (역매핑)
ISO_TO_NAME: Dict[str, str] = {
    "US": "United States",
    "CN": "China",
    "JP": "Japan",
    "EU": "European Union",
    "DE": "Germany",
    "GB": "United Kingdom",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "CA": "Canada",
    "AU": "Australia",
    "KR": "South Korea",
    "IN": "India",
    "BR": "Brazil",
    "RU": "Russia",
    "MX": "Mexico",
    "CH": "Switzerland",
    "NL": "Netherlands",
    "SE": "Sweden",
    "NO": "Norway",
    "NZ": "New Zealand",
    "SG": "Singapore",
    "HK": "Hong Kong",
    "TW": "Taiwan",
    "TR": "Turkey",
    "SA": "Saudi Arabia",
    "ZA": "South Africa",
    "AR": "Argentina",
    "ID": "Indonesia",
    "TH": "Thailand",
    "VN": "Vietnam",
    "MY": "Malaysia",
    "PH": "Philippines",
    "GLOBAL": "Global",
}


def normalize_country(raw_country: str) -> Optional[str]:
    """
    원문 국가명을 ISO 코드로 변환
    
    Args:
        raw_country: 원문 국가명 (예: "United States", "US", "America")
    
    Returns:
        ISO 3166-1 alpha-2 코드 또는 None
    """
    if not raw_country:
        return None
    
    normalized = raw_country.lower().strip()
    
    # 직접 매핑 확인
    if normalized in COUNTRY_MAPPING:
        return COUNTRY_MAPPING[normalized]
    
    # ISO 코드로 직접 입력된 경우
    upper = normalized.upper()
    if upper in ISO_TO_NAME:
        return upper
    
    # Fuzzy matching 시도 (부분 문자열)
    for key, value in COUNTRY_MAPPING.items():
        if key in normalized or normalized in key:
            return value
    
    return None


def get_country_name(iso_code: str) -> str:
    """
    ISO 코드를 국가명으로 변환
    """
    return ISO_TO_NAME.get(iso_code.upper(), iso_code)


def add_country_mapping(raw_country: str, iso_code: str):
    """
    새로운 국가 매핑 추가 (런타임 확장)
    """
    COUNTRY_MAPPING[raw_country.lower().strip()] = iso_code.upper()
