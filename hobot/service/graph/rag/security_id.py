"""Security identifier normalization helpers for equity queries."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

_SECURITY_ID_PATTERN = re.compile(r"^([A-Za-z]{2}):([A-Za-z0-9.\-]+)$")
_US_NATIVE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")

_COUNTRY_ALIASES = {
    "KR": "KR",
    "KOR": "KR",
    "KOREA": "KR",
    "SOUTHKOREA": "KR",
    "한국": "KR",
    "대한민국": "KR",
    "US": "US",
    "USA": "US",
    "UNITEDSTATES": "US",
    "미국": "US",
}


def normalize_country_code(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    compact = re.sub(r"[^0-9A-Za-z가-힣]+", "", text).upper()
    return _COUNTRY_ALIASES.get(compact)


def normalize_native_code(country_code: str, native_code: Any) -> Optional[str]:
    country = normalize_country_code(country_code)
    text = str(native_code or "").strip()
    if not country or not text:
        return None

    if country == "KR":
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits or len(digits) > 6:
            return None
        return digits.zfill(6)

    upper_text = text.upper().replace(" ", "")
    if country == "US":
        return upper_text if _US_NATIVE_PATTERN.fullmatch(upper_text) else None

    return upper_text or None


def parse_security_id(value: Any) -> Tuple[Optional[str], Optional[str]]:
    text = str(value or "").strip()
    if not text:
        return None, None
    matched = _SECURITY_ID_PATTERN.fullmatch(text)
    if not matched:
        return None, None
    raw_country, raw_native = matched.group(1), matched.group(2)
    country = normalize_country_code(raw_country)
    native = normalize_native_code(country or raw_country, raw_native)
    if not country or not native:
        return None, None
    return country, native


def to_security_id(country_code: Any, native_code: Any) -> Optional[str]:
    country = normalize_country_code(country_code)
    native = normalize_native_code(country or "", native_code)
    if not country or not native:
        return None
    return f"{country}:{native}"


def infer_country_for_symbol(
    symbol: Any,
    *,
    requested_country_code: Any = None,
    selected_type: Any = None,
) -> Optional[str]:
    token = str(symbol or "").strip()
    if not token:
        return normalize_country_code(requested_country_code)

    parsed_country, _ = parse_security_id(token)
    if parsed_country:
        return parsed_country

    digits = "".join(ch for ch in token if ch.isdigit())
    if digits and len(digits) <= 6 and digits == token:
        return "KR"

    upper_token = token.upper().replace(" ", "")
    if _US_NATIVE_PATTERN.fullmatch(upper_token):
        return "US"

    if str(selected_type or "").strip().lower() == "us_single_stock":
        return "US"

    return normalize_country_code(requested_country_code)


def build_equity_focus_identifiers(route_decision: Dict[str, Any], request: Any) -> Dict[str, Optional[str]]:
    matched_symbols = route_decision.get("matched_symbols")
    focus_symbol = None
    if isinstance(matched_symbols, list):
        for item in matched_symbols:
            candidate = str(item or "").strip()
            if candidate:
                focus_symbol = candidate
                break

    if not focus_symbol:
        return {
            "focus_symbol": None,
            "country_code": None,
            "native_code": None,
            "security_id": None,
        }

    parsed_country, parsed_native = parse_security_id(focus_symbol)
    if parsed_country and parsed_native:
        return {
            "focus_symbol": parsed_native,
            "country_code": parsed_country,
            "native_code": parsed_native,
            "security_id": f"{parsed_country}:{parsed_native}",
        }

    requested_country_code = (
        getattr(request, "country_code", None)
        or route_decision.get("resolved_country_code")
        or route_decision.get("country_code")
    )
    selected_type = route_decision.get("selected_type")
    country = infer_country_for_symbol(
        focus_symbol,
        requested_country_code=requested_country_code,
        selected_type=selected_type,
    )
    native = normalize_native_code(country or "", focus_symbol)
    security_id = to_security_id(country, native) if country and native else None
    normalized_focus_symbol = native if native else focus_symbol.upper().replace(" ", "")
    return {
        "focus_symbol": normalized_focus_symbol or None,
        "country_code": country,
        "native_code": native,
        "security_id": security_id,
    }


__all__ = [
    "build_equity_focus_identifiers",
    "infer_country_for_symbol",
    "normalize_country_code",
    "normalize_native_code",
    "parse_security_id",
    "to_security_id",
]
