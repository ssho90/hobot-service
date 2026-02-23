import json
from typing import Dict, Any, List

def _normalize_agent_execution_payload(raw_json: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    summary = str(raw_json.get("analytical_summary") or raw_json.get("summary") or "").strip()
    key_drivers_raw = raw_json.get("key_drivers") or raw_json.get("key_points")
    primary_trend = str(raw_json.get("primary_trend") or "NEUTRAL").upper()
    domain_source = str(raw_json.get("domain_source") or "GENERAL").upper()
    
    confidence_score_raw = raw_json.get("confidence_score")
    confidence_score = 0.5
    try:
        if confidence_score_raw is not None:
            confidence_score = float(confidence_score_raw)
            confidence_score = max(0.0, min(1.0, confidence_score))
    except Exception:
        pass

    key_drivers: List[str] = []
    if isinstance(key_drivers_raw, list):
        for item in key_drivers_raw[:4]:
            text = str(item or "").strip()
            if text:
                key_drivers.append(text)

    metrics_raw = raw_json.get("quantitative_metrics")
    quantitative_metrics: Dict[str, str] = {}
    if isinstance(metrics_raw, dict):
        for k, v in metrics_raw.items():
            if str(k).strip():
                quantitative_metrics[str(k).strip()] = str(v).strip()

    if not summary:
        summary = str(raw_text or "").strip()
    if not summary:
        summary = "도메인 분석 결과를 생성하지 못했습니다."

    if primary_trend not in {"BULL", "BEAR", "NEUTRAL"}:
        primary_trend = "NEUTRAL"

    return {
        "domain_source": domain_source,
        "primary_trend": primary_trend,
        "confidence_score": confidence_score,
        "key_drivers": key_drivers,
        "quantitative_metrics": quantitative_metrics,
        "analytical_summary": summary,
    }

# 1. 정상 파싱 테스트
mock_valid_json = {
    "domain_source": "EQUITY",
    "confidence_score": 0.85,
    "primary_trend": "BULL",
    "quantitative_metrics": {
        "MA60_diff": "+4%",
        "earnings_surprise": "Beat"
    },
    "key_drivers": ["실적 서프라이즈로 인한 투자심리 개선", "단기 저점 지지선 돌파"],
    "analytical_summary": "현재 주식 시장의 단기 모멘텀은 매우 강한 상태로 평가됩니다."
}
print("--- [1] VALID PARSING ---")
parsed1 = _normalize_agent_execution_payload(mock_valid_json, "")
print(json.dumps(parsed1, ensure_ascii=False, indent=2))


# 2. 에러 발동시(Fallback) 테스트 (빈 데이터)
print("\n--- [2] FALLBACK PARSING ---")
agent_name = "real_estate_agent"
empty_payload = _normalize_agent_execution_payload({}, "")
empty_payload["domain_source"] = agent_name.replace('_agent', '').upper()
empty_payload["primary_trend"] = "NEUTRAL"
empty_payload["analytical_summary"] = "현재 데이터를 분석할 수 없습니다. (LLM 에러/지연)"
empty_payload["key_drivers"] = ["에이전트 응답 지연/스키마 불일치 오류"]

print(json.dumps(empty_payload, ensure_ascii=False, indent=2))
