from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

REGION_ALL_TOKENS: Set[str] = {
    "전체",
    "전국",
    "전국전체",
    "전체지역",
    "all",
}

REAL_ESTATE_CONTEXT_KEYWORDS: Tuple[str, ...] = (
    "부동산",
    "아파트",
    "오피스텔",
    "연립",
    "다세대",
    "단독",
    "전세",
    "월세",
    "매매",
    "거래",
    "주택",
    "집값",
    "housing",
    "realestate",
    "real estate",
)

SIDO_PREFIX_BY_NAME: Dict[str, str] = {
    "서울": "11",
    "서울시": "11",
    "부산": "26",
    "부산시": "26",
    "대구": "27",
    "대구시": "27",
    "인천": "28",
    "인천시": "28",
    "광주": "29",
    "광주시": "29",
    "대전": "30",
    "대전시": "30",
    "울산": "31",
    "울산시": "31",
    "세종": "36",
    "세종시": "36",
    "경기": "41",
    "경기도": "41",
    "강원": "42",
    "강원도": "42",
    "충북": "43",
    "충청북도": "43",
    "충남": "44",
    "충청남도": "44",
    "전북": "45",
    "전라북도": "45",
    "전남": "46",
    "전라남도": "46",
    "경북": "47",
    "경상북도": "47",
    "경남": "48",
    "경상남도": "48",
    "제주": "50",
    "제주도": "50",
    "seoul": "11",
    "busan": "26",
    "daegu": "27",
    "incheon": "28",
    "gwangju": "29",
    "daejeon": "30",
    "ulsan": "31",
    "sejong": "36",
    "gyeonggi": "41",
    "gangwon": "42",
    "chungbuk": "43",
    "chungnam": "44",
    "jeonbuk": "45",
    "jeonnam": "46",
    "gyeongbuk": "47",
    "gyeongnam": "48",
    "jeju": "50",
}

LAWD_NAME_BY_CODE: Dict[str, str] = {
    "11110": "서울 종로구",
    "11140": "서울 중구",
    "11170": "서울 용산구",
    "11200": "서울 성동구",
    "11215": "서울 광진구",
    "11230": "서울 동대문구",
    "11260": "서울 중랑구",
    "11290": "서울 성북구",
    "11305": "서울 강북구",
    "11320": "서울 도봉구",
    "11350": "서울 노원구",
    "11380": "서울 은평구",
    "11410": "서울 서대문구",
    "11440": "서울 마포구",
    "11470": "서울 양천구",
    "11500": "서울 강서구",
    "11530": "서울 구로구",
    "11545": "서울 금천구",
    "11560": "서울 영등포구",
    "11590": "서울 동작구",
    "11620": "서울 관악구",
    "11650": "서울 서초구",
    "11680": "서울 강남구",
    "11710": "서울 송파구",
    "11740": "서울 강동구",
    "41111": "경기 수원시 장안구",
    "41113": "경기 수원시 권선구",
    "41115": "경기 수원시 팔달구",
    "41117": "경기 수원시 영통구",
    "41131": "경기 성남시 수정구",
    "41133": "경기 성남시 중원구",
    "41135": "경기 성남시 분당구",
    "41150": "경기 의정부시",
    "41171": "경기 안양시 만안구",
    "41173": "경기 안양시 동안구",
    "41190": "경기 부천시",
    "41210": "경기 광명시",
    "41220": "경기 평택시",
    "41250": "경기 동두천시",
    "41271": "경기 안산시 상록구",
    "41273": "경기 안산시 단원구",
    "41281": "경기 고양시 덕양구",
    "41285": "경기 고양시 일산동구",
    "41287": "경기 고양시 일산서구",
    "41290": "경기 과천시",
    "41310": "경기 구리시",
    "41360": "경기 남양주시",
    "41370": "경기 오산시",
    "41390": "경기 시흥시",
    "41410": "경기 군포시",
    "41430": "경기 의왕시",
    "41450": "경기 하남시",
    "41460": "경기 용인시 처인구",
    "41463": "경기 용인시 기흥구",
    "41465": "경기 용인시 수지구",
    "41480": "경기 파주시",
    "41500": "경기 이천시",
    "41550": "경기 안성시",
    "41570": "경기 김포시",
    "41590": "경기 화성시",
    "41610": "경기 광주시",
    "41630": "경기 양주시",
    "41650": "경기 포천시",
    "41670": "경기 여주시",
    "41800": "경기 연천군",
    "41820": "경기 가평군",
    "41830": "경기 양평군",
    "26110": "부산 중구",
    "26140": "부산 서구",
    "26170": "부산 동구",
    "26200": "부산 영도구",
    "26230": "부산 부산진구",
    "26260": "부산 동래구",
    "26290": "부산 남구",
    "26320": "부산 북구",
    "26350": "부산 해운대구",
    "26380": "부산 사하구",
    "26410": "부산 금정구",
    "26440": "부산 강서구",
    "26470": "부산 연제구",
    "26500": "부산 수영구",
    "26530": "부산 사상구",
    "26710": "부산 기장군",
    "27110": "대구 중구",
    "27140": "대구 동구",
    "27170": "대구 서구",
    "27200": "대구 남구",
    "27230": "대구 북구",
    "27260": "대구 수성구",
    "27290": "대구 달서구",
    "27710": "대구 달성군",
    "27720": "대구 군위군",
    "28110": "인천 중구",
    "28140": "인천 동구",
    "28177": "인천 미추홀구",
    "28185": "인천 연수구",
    "28200": "인천 남동구",
    "28237": "인천 부평구",
    "28245": "인천 계양구",
    "28260": "인천 서구",
    "28710": "인천 강화군",
    "28720": "인천 옹진군",
    "29110": "광주 동구",
    "29140": "광주 서구",
    "29155": "광주 남구",
    "29170": "광주 북구",
    "29200": "광주 광산구",
    "30110": "대전 동구",
    "30140": "대전 중구",
    "30170": "대전 서구",
    "30200": "대전 유성구",
    "30230": "대전 대덕구",
    "31110": "울산 중구",
    "31140": "울산 남구",
    "31170": "울산 동구",
    "31200": "울산 북구",
    "31710": "울산 울주군",
    "36110": "세종",
    "42110": "강원 춘천시",
    "42130": "강원 원주시",
    "42150": "강원 강릉시",
    "43111": "충북 청주시 상당구",
    "43112": "충북 청주시 서원구",
    "43113": "충북 청주시 흥덕구",
    "43114": "충북 청주시 청원구",
    "44131": "충남 천안시 동남구",
    "44133": "충남 천안시 서북구",
    "44200": "충남 아산시",
    "45111": "전북 전주시 완산구",
    "45113": "전북 전주시 덕진구",
    "45140": "전북 익산시",
    "46110": "전남 목포시",
    "46130": "전남 여수시",
    "46150": "전남 순천시",
    "47111": "경북 포항시 남구",
    "47113": "경북 포항시 북구",
    "47130": "경북 경주시",
    "47190": "경북 구미시",
    "47210": "경북 영주시",
    "47290": "경북 김천시",
    "48121": "경남 창원시 의창구",
    "48123": "경남 창원시 성산구",
    "48125": "경남 창원시 마산합포구",
    "48127": "경남 창원시 마산회원구",
    "48129": "경남 창원시 진해구",
    "48170": "경남 진주시",
    "48250": "경남 김해시",
    "50110": "제주 제주시",
    "50130": "제주 서귀포시",
}

_REGION_TOKEN_NORMALIZER = re.compile(r"\s+")
_REGION_TEXT_SPLITTER = re.compile(r"[,\n\t]+")
_REGION_WORD_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")
_REGION_SUFFIX_PATTERN = re.compile(r"(특별시|광역시|특별자치시|특별자치도|도|시|구|군)$")
_REGION_CONNECTOR_PATTERN = re.compile(r"(vs|VS|versus|그리고|및|와|과|대비|비교)")


def _normalize_region_token(value: str) -> str:
    return _REGION_TOKEN_NORMALIZER.sub("", (value or "").strip()).lower()


def _strip_all_suffix(normalized_token: str) -> str:
    out = normalized_token
    if out.endswith("전체"):
        out = out[: -len("전체")]
    if out.endswith("all"):
        out = out[: -len("all")]
    return out


def _strip_region_suffix(token: str) -> str:
    stripped = _REGION_SUFFIX_PATTERN.sub("", token or "")
    return stripped if len(stripped) >= 2 else token


ALL_LAWD_CODES: List[str] = sorted(LAWD_NAME_BY_CODE.keys())

SIDO_PREFIX_BY_TOKEN: Dict[str, str] = {
    _normalize_region_token(name): prefix for name, prefix in SIDO_PREFIX_BY_NAME.items()
}


def _register_alias(alias_to_codes: Dict[str, Set[str]], alias: str, code: str) -> None:
    normalized = _normalize_region_token(alias)
    if len(normalized) < 2:
        return
    alias_to_codes.setdefault(normalized, set()).add(code)


REGION_ALIAS_TO_CODES: Dict[str, Set[str]] = {}
for _code, _name in LAWD_NAME_BY_CODE.items():
    _register_alias(REGION_ALIAS_TO_CODES, _name, _code)

    _parts = _name.split()
    if len(_parts) >= 2:
        _sido = _parts[0]
        _district_parts = _parts[1:]
        _district = " ".join(_district_parts)
        _register_alias(REGION_ALIAS_TO_CODES, _district, _code)
        _register_alias(REGION_ALIAS_TO_CODES, _strip_region_suffix(_district), _code)
        for _part in _district_parts:
            _register_alias(REGION_ALIAS_TO_CODES, _part, _code)
            _register_alias(REGION_ALIAS_TO_CODES, _strip_region_suffix(_part), _code)

        _city = _district_parts[0]
        _register_alias(REGION_ALIAS_TO_CODES, _city, _code)
        _register_alias(REGION_ALIAS_TO_CODES, _strip_region_suffix(_city), _code)

    for _sido_name, _prefix in SIDO_PREFIX_BY_NAME.items():
        if _code.startswith(_prefix):
            _register_alias(REGION_ALIAS_TO_CODES, _sido_name, _code)

REGION_ALIASES_SORTED: List[str] = sorted(
    REGION_ALIAS_TO_CODES.keys(),
    key=lambda token: (-len(token), token),
)


def contains_real_estate_context(question: str) -> bool:
    lowered = _normalize_region_token(question)
    return any(keyword in lowered for keyword in REAL_ESTATE_CONTEXT_KEYWORDS)


def resolve_region_token_to_lawd_codes(token: str) -> List[str]:
    raw = (token or "").strip()
    normalized = _normalize_region_token(raw)
    if not normalized:
        return []

    if normalized in REGION_ALL_TOKENS:
        return list(ALL_LAWD_CODES)

    if re.fullmatch(r"\d{10}", raw):
        code = raw[:5]
        return [code] if code.isdigit() else []

    if re.fullmatch(r"\d{5}", raw):
        return [raw]

    direct_codes = REGION_ALIAS_TO_CODES.get(normalized)
    if direct_codes:
        return sorted(direct_codes)

    no_all_suffix = _strip_all_suffix(normalized)
    prefix = SIDO_PREFIX_BY_TOKEN.get(normalized) or SIDO_PREFIX_BY_TOKEN.get(no_all_suffix)
    if prefix:
        return [code for code in ALL_LAWD_CODES if code.startswith(prefix)]

    if len(normalized) >= 2:
        fuzzy: Set[str] = set()
        for alias, codes in REGION_ALIAS_TO_CODES.items():
            if len(alias) < 3:
                continue
            if normalized in alias:
                fuzzy.update(codes)
        if fuzzy:
            return sorted(fuzzy)

    return []


def parse_region_input_to_lawd_codes(raw_input: str) -> Tuple[List[str], List[str], int]:
    if not (raw_input or "").strip():
        return [], [], 0

    codes: Set[str] = set()
    unknown_tokens: List[str] = []
    matched_group_count = 0

    tokens = [
        token.strip()
        for token in _REGION_TEXT_SPLITTER.split(raw_input)
        if token and token.strip()
    ]

    for token in tokens:
        resolved_codes = resolve_region_token_to_lawd_codes(token)
        if resolved_codes:
            codes.update(resolved_codes)
            matched_group_count += 1
        else:
            unknown_tokens.append(token)

    return sorted(codes), unknown_tokens, matched_group_count


def extract_region_codes_from_question(question: str) -> Tuple[List[str], int]:
    text = (question or "").strip()
    if not text or not contains_real_estate_context(text):
        return [], 0

    codes: Set[str] = set()
    matched_group_count = 0

    # 숫자 코드(5자리/10자리) 우선 수집
    for token in re.findall(r"\b\d{5,10}\b", text):
        resolved_codes = resolve_region_token_to_lawd_codes(token)
        if resolved_codes:
            codes.update(resolved_codes)
            matched_group_count += 1

    segmented_text = _REGION_CONNECTOR_PATTERN.sub(" ", text)
    words = _REGION_WORD_PATTERN.findall(segmented_text)
    if not words:
        return sorted(codes), matched_group_count

    occupied = [False] * len(words)
    max_phrase_size = min(3, len(words))

    for phrase_size in range(max_phrase_size, 0, -1):
        for start_idx in range(0, len(words) - phrase_size + 1):
            end_idx = start_idx + phrase_size
            if any(occupied[start_idx:end_idx]):
                continue

            phrase = " ".join(words[start_idx:end_idx])
            resolved_codes = resolve_region_token_to_lawd_codes(phrase)
            if not resolved_codes:
                continue

            codes.update(resolved_codes)
            matched_group_count += 1
            for idx in range(start_idx, end_idx):
                occupied[idx] = True

    return sorted(codes), matched_group_count


def format_lawd_codes_csv(codes: List[str]) -> Optional[str]:
    if not codes:
        return None
    return ",".join(sorted({code for code in codes if re.fullmatch(r"\d{5}", str(code))})) or None
