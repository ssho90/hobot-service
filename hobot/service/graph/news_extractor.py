"""
Phase B-6: News Extractor
LLM 기반 뉴스 추출기 - Structured Output 사용
"""

import os
import json
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from service.llm_monitoring import track_llm_call

from google import genai
from google.genai import types

from service.graph.schemas.extraction_schema import (
    ExtractionResult, Event, Fact, Claim, Evidence, Link,
    SentimentType, ConfidenceLevel, LinkType,
    ExtractionValidator, SCHEMA_VERSION
)
from service.graph.normalization.category_mapping import get_related_themes
from service.graph.nel.nel_pipeline import get_nel_pipeline, NELPipeline

logger = logging.getLogger(__name__)


# ============ LLM Response Schema (Simplified for structured output) ============

class LLMEvidence(BaseModel):
    """LLM이 추출하는 Evidence"""
    evidence_text: str = Field(..., description="Original text from the article supporting this information")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")


class LLMFact(BaseModel):
    """LLM이 추출하는 Fact"""
    fact_text: str = Field(..., description="Objective, verifiable statement from the article")
    fact_type: str = Field(default="other", description="Type: economic_event, policy_action, market_data, statement, other")
    entities_mentioned: List[str] = Field(default_factory=list, description="Entities mentioned in this fact")
    evidence: LLMEvidence = Field(..., description="Supporting evidence from the text")


class LLMClaim(BaseModel):
    """LLM이 추출하는 Claim"""
    claim_text: str = Field(..., description="Opinion, prediction, or judgment from the article")
    claim_type: str = Field(default="other", description="Type: prediction, opinion, analysis, recommendation, other")
    author: Optional[str] = Field(None, description="Who made this claim")
    sentiment: str = Field(default="neutral", description="Sentiment: positive, negative, neutral")
    evidence: LLMEvidence = Field(..., description="Supporting evidence from the text")


class LLMEvent(BaseModel):
    """LLM이 추출하는 Event"""
    event_name: str = Field(..., description="Name of the event")
    event_type: str = Field(default="other", description="Type: policy, economic_release, market_event, geopolitical, corporate, other")
    description: Optional[str] = Field(None, description="Brief description of the event")
    impact_level: str = Field(default="medium", description="Impact level: high, medium, low")


class LLMLink(BaseModel):
    """LLM이 추출하는 Link/Relationship"""
    source: str = Field(..., description="Source entity or event name")
    target: str = Field(..., description="Target entity, theme, or indicator")
    relationship: str = Field(..., description="Relationship type: AFFECTS, CAUSES, CORRELATES, MENTIONS")
    evidence: LLMEvidence = Field(..., description="Evidence supporting this relationship")


class LLMExtractionResponse(BaseModel):
    """LLM의 전체 추출 응답"""
    events: List[LLMEvent] = Field(default_factory=list, description="Events mentioned in the article")
    facts: List[LLMFact] = Field(default_factory=list, description="Verifiable facts from the article")
    claims: List[LLMClaim] = Field(default_factory=list, description="Opinions and predictions from the article")
    links: List[LLMLink] = Field(default_factory=list, description="Relationships between entities/events and themes/indicators")


# ============ Extraction Prompt ============

EXTRACTION_PROMPT = """You are a financial news analyst. Extract structured information from the following news article.

<article>
{article_text}
</article>

<instructions>
1. Extract EVENTS: Notable economic or market events mentioned (e.g., FOMC meeting, CPI release, rate decision)
2. Extract FACTS: Objective, verifiable statements (e.g., "Fed raised rates by 25bps", "Unemployment fell to 3.7%")
3. Extract CLAIMS: Opinions, predictions, or judgments (e.g., "Analysts expect further hikes", "Market shows signs of weakness")
4. Extract LINKS: Relationships between entities/events and economic themes/indicators

IMPORTANT RULES:
- Every FACT and CLAIM must have EVIDENCE (direct quote from the article)
- Every LINK relationship must have EVIDENCE
- Focus on macroeconomic themes: rates, inflation, growth, labor, liquidity, risk
- Be specific and cite the original text

Valid relationship types: AFFECTS, CAUSES, CORRELATES, MENTIONS
Valid themes: rates, inflation, growth, labor, liquidity, risk
</instructions>

Extract the information in the specified JSON format.
"""


class NewsExtractor:
    """
    LLM 기반 뉴스 추출기
    """
    ALLOWED_MODELS = {"gemini-3-flash-preview", "gemini-3-pro-preview"}
    DEFAULT_MODEL = "gemini-3-flash-preview"

    VALID_EVENT_TYPES = {"policy", "economic_release", "market_event", "geopolitical", "corporate", "other"}
    EVENT_TYPE_ALIASES = {
        "economic_data": "economic_release",
        "data_release": "economic_release",
        "macro_event": "economic_release",
        "policy_action": "policy",
        "market": "market_event",
    }
    VALID_IMPACT_LEVELS = {"high", "medium", "low"}
    IMPACT_LEVEL_ALIASES = {
        "critical": "high",
        "severe": "high",
        "moderate": "medium",
        "normal": "medium",
        "minor": "low",
    }
    VALID_FACT_TYPES = {
        "economic_event",
        "economic_release",
        "policy_action",
        "market_data",
        "statement",
        "data_release",
        "other",
    }
    FACT_TYPE_ALIASES = {
        "economic_data": "data_release",
        "data": "data_release",
        "release": "data_release",
        "economic_release_data": "economic_release",
        "policy": "policy_action",
        "market": "market_data",
        "corporate": "other",
    }
    VALID_CLAIM_TYPES = {
        "prediction",
        "opinion",
        "analysis",
        "recommendation",
        "expectation",
        "statement",
        "forecast",
        "other",
    }
    CLAIM_TYPE_ALIASES = {
        "expect": "expectation",
        "expectations": "expectation",
        "view": "opinion",
        "market_view": "opinion",
        "judgment": "analysis",
        "commentary": "analysis",
        "comment": "statement",
    }
    SENTIMENT_ALIASES = {
        "bullish": "positive",
        "constructive": "positive",
        "bearish": "negative",
        "cautious": "negative",
        "mixed": "neutral",
    }
    CONFIDENCE_ALIASES = {
        "strong": "high",
        "very_high": "high",
        "certain": "high",
        "moderate": "medium",
        "normal": "medium",
        "weak": "low",
        "uncertain": "low",
    }
    LINK_TYPE_ALIASES = {
        "AFFECT": "AFFECTS",
        "CAUSE": "CAUSES",
        "CORRELATE": "CORRELATES",
        "CORRELATED": "CORRELATES",
        "CORRELATED_WITH": "CORRELATES",
        "MENTION": "MENTIONS",
    }
    
    def __init__(
        self,
        model_name: str = "gemini-3-flash-preview",
        extractor_version: str = "1.0",
        cache_enabled: bool = True
    ):
        self.model_name = self._resolve_model_name(model_name)
        self.extractor_version = extractor_version
        self.cache_enabled = cache_enabled
        self.cache_dir = os.path.join(os.path.dirname(__file__), "..", "cache", "extractions")
        
        # NEL Pipeline
        self.nel_pipeline = get_nel_pipeline()
        
        # Gemini Client
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None
            logger.warning("No Gemini API key found. Extraction will fail.")
        
        # 캐시 디렉토리 생성
        os.makedirs(self.cache_dir, exist_ok=True)

    def _resolve_model_name(self, requested_model: Optional[str]) -> str:
        model_name = (requested_model or "").strip()
        if model_name in self.ALLOWED_MODELS:
            return model_name
        logger.warning(
            "Unsupported extraction model '%s'. Fallback to '%s'.",
            requested_model,
            self.DEFAULT_MODEL,
        )
        return self.DEFAULT_MODEL
    
    def _get_cache_key(self, doc_id: str) -> str:
        """캐시 키 생성: doc_id:extractor_version:model"""
        content = f"{doc_id}:{self.extractor_version}:{self.model_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def _get_cached(self, doc_id: str) -> Optional[ExtractionResult]:
        """캐시에서 결과 조회"""
        if not self.cache_enabled:
            return None
        
        cache_key = self._get_cache_key(doc_id)
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    return ExtractionResult.model_validate(data)
            except Exception as e:
                logger.warning(f"Cache read error for {doc_id}: {e}")
        
        return None
    
    def _save_cache(self, doc_id: str, result: ExtractionResult):
        """결과를 캐시에 저장"""
        if not self.cache_enabled:
            return
        
        cache_key = self._get_cache_key(doc_id)
        cache_path = os.path.join(self.cache_dir, f"{cache_key}.json")
        
        try:
            with open(cache_path, 'w') as f:
                json.dump(result.model_dump(mode='json'), f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Cache write error for {doc_id}: {e}")

    def _normalize_choice(
        self,
        raw_value: Optional[str],
        valid_values: set[str],
        aliases: Optional[Dict[str, str]] = None,
        default: str = "other",
    ) -> str:
        if raw_value is None:
            return default
        normalized = str(raw_value).strip().lower()
        if not normalized:
            return default
        normalized = normalized.replace("-", "_").replace(" ", "_")
        if aliases and normalized in aliases:
            normalized = aliases[normalized]
        return normalized if normalized in valid_values else default

    def _normalize_confidence(self, raw_value: Optional[str]) -> ConfidenceLevel:
        value = self._normalize_choice(
            raw_value,
            valid_values={item.value for item in ConfidenceLevel},
            aliases=self.CONFIDENCE_ALIASES,
            default=ConfidenceLevel.MEDIUM.value,
        )
        return ConfidenceLevel(value)

    def _normalize_sentiment(self, raw_value: Optional[str]) -> SentimentType:
        value = self._normalize_choice(
            raw_value,
            valid_values={item.value for item in SentimentType},
            aliases=self.SENTIMENT_ALIASES,
            default=SentimentType.NEUTRAL.value,
        )
        return SentimentType(value)

    def _normalize_link_type(self, raw_value: Optional[str]) -> LinkType:
        if raw_value is None:
            return LinkType.MENTIONS
        normalized = str(raw_value).strip().upper().replace("-", "_").replace(" ", "_")
        normalized = self.LINK_TYPE_ALIASES.get(normalized, normalized)
        try:
            return LinkType(normalized)
        except ValueError:
            return LinkType.MENTIONS

    def _normalize_evidence_text(self, raw_text: Optional[str], fallback_text: Optional[str]) -> str:
        text = (raw_text or "").strip()
        if len(text) >= 10:
            return text
        fallback = (fallback_text or "").strip()
        if len(fallback) >= 10:
            return fallback
        merged = (text or fallback or "No evidence provided").strip()
        if len(merged) < 10:
            merged = f"{merged} (n/a)"
        if len(merged) < 10:
            merged = merged.ljust(10, ".")
        return merged
    
    def _convert_llm_response(self, doc_id: str, llm_response: LLMExtractionResponse, article_text: str) -> ExtractionResult:
        """LLM 응답을 ExtractionResult로 변환"""
        
        # Events 변환
        events = []
        for llm_event in llm_response.events:
            event = Event(
                event_name=llm_event.event_name,
                event_type=self._normalize_choice(
                    llm_event.event_type,
                    valid_values=self.VALID_EVENT_TYPES,
                    aliases=self.EVENT_TYPE_ALIASES,
                    default="other",
                ),  # type: ignore
                description=llm_event.description,
                impact_level=self._normalize_choice(
                    llm_event.impact_level,
                    valid_values=self.VALID_IMPACT_LEVELS,
                    aliases=self.IMPACT_LEVEL_ALIASES,
                    default="medium",
                ),  # type: ignore
                related_themes=get_related_themes(llm_event.event_name + " " + (llm_event.description or ""))
            )
            events.append(event)
        
        # Facts 변환
        facts = []
        for llm_fact in llm_response.facts:
            evidence = Evidence(
                evidence_text=self._normalize_evidence_text(
                    llm_fact.evidence.evidence_text,
                    llm_fact.fact_text or article_text,
                ),
                confidence=self._normalize_confidence(llm_fact.evidence.confidence),
            )
            fact = Fact(
                fact_text=llm_fact.fact_text,
                fact_type=self._normalize_choice(
                    llm_fact.fact_type,
                    valid_values=self.VALID_FACT_TYPES,
                    aliases=self.FACT_TYPE_ALIASES,
                    default="other",
                ),  # type: ignore
                entities_mentioned=llm_fact.entities_mentioned,
                evidences=[evidence]
            )
            facts.append(fact)
        
        # Claims 변환
        claims = []
        for llm_claim in llm_response.claims:
            evidence = Evidence(
                evidence_text=self._normalize_evidence_text(
                    llm_claim.evidence.evidence_text,
                    llm_claim.claim_text or article_text,
                ),
                confidence=self._normalize_confidence(llm_claim.evidence.confidence),
            )
            claim = Claim(
                claim_text=llm_claim.claim_text,
                claim_type=self._normalize_choice(
                    llm_claim.claim_type,
                    valid_values=self.VALID_CLAIM_TYPES,
                    aliases=self.CLAIM_TYPE_ALIASES,
                    default="other",
                ),  # type: ignore
                author=llm_claim.author,
                sentiment=self._normalize_sentiment(llm_claim.sentiment),
                evidences=[evidence]
            )
            claims.append(claim)
        
        # Links 변환
        links = []
        for llm_link in llm_response.links:
            evidence = Evidence(
                evidence_text=self._normalize_evidence_text(
                    llm_link.evidence.evidence_text,
                    article_text,
                ),
                confidence=self._normalize_confidence(llm_link.evidence.confidence),
            )
            
            # relationship 타입 변환
            link_type = self._normalize_link_type(llm_link.relationship)
            
            link = Link(
                source_type="Event",  # 기본값, 실제로는 더 정교한 분류 필요
                source_ref=llm_link.source,
                target_type="Theme",  # 기본값
                target_ref=llm_link.target,
                link_type=link_type,
                evidence=evidence
            )
            links.append(link)
        
        # ExtractionResult 생성
        result = ExtractionResult(
            doc_id=doc_id,
            extractor_version=self.extractor_version,
            model_name=self.model_name,
            events=events,
            facts=facts,
            claims=claims,
            links=links
        )
        
        # Evidence ID 생성
        result.generate_all_evidence_ids()
        
        return result
    
    async def extract_async(self, doc_id: str, article_text: str, title: str = "") -> ExtractionResult:
        """비동기 추출"""
        import asyncio
        return await asyncio.to_thread(self.extract, doc_id, article_text, title)
    
    def extract(self, doc_id: str, article_text: str, title: str = "") -> ExtractionResult:
        """
        뉴스 기사에서 구조화된 정보 추출
        
        Args:
            doc_id: Document ID
            article_text: 기사 본문
            title: 기사 제목 (선택)
        
        Returns:
            ExtractionResult
        """
        start_time = datetime.now()
        
        # 캐시 확인
        cached = self._get_cached(doc_id)
        if cached:
            logger.info(f"[NewsExtractor] Cache hit for {doc_id}")
            return cached
        
        if not self.client:
            raise RuntimeError("Gemini client not initialized. Check API key.")
        
        # 프롬프트 생성
        full_text = f"{title}\n\n{article_text}" if title else article_text
        prompt_text = EXTRACTION_PROMPT.replace("{article_text}", full_text)
    
        try:
            response = None
            # LLM 호출 및 모니터링 (시스템 계정 사용)
            with track_llm_call(
                model_name=self.model_name,
                provider="Google",
                service_name="news_extraction",
                request_prompt=prompt_text[:2000] + "...",  # 너무 길 수 있으므로 로깅용으론 축약 (DB엔 전체 저장될지 확인 필요)
                user_id="system"
            ) as tracker:
                # 원본 프롬프트 전체 저장 (track_llm_call 내부에서 DB 저장 시 잘림 처리됨)
                tracker.set_request_prompt(prompt_text)
                
                # Structured Output으로 LLM 호출
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=LLMExtractionResponse,
                        temperature=0.2,  # 낮은 temperature로 일관성 확보
                    )
                )
                # 응답 설정 (토큰 사용량 자동 추출)
                tracker.set_response(response)
            
            # 응답 파싱
            if response and response.text:
                llm_response = response.parsed
                if not llm_response:
                     # parsed가 없으면 직접 파싱 시도
                     llm_response = LLMExtractionResponse.model_validate_json(response.text)
            else:
                raise ValueError("Empty response from LLM")
            
            # ExtractionResult로 변환
            result = self._convert_llm_response(doc_id, llm_response, article_text)
            
            # 처리 시간 기록
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            result.processing_time_ms = processing_time
            
            # 검증
            is_valid, errors = ExtractionValidator.validate(result)
            if not is_valid:
                result.error_messages.extend(errors)
                logger.warning(f"[NewsExtractor] Validation warnings for {doc_id}: {errors}")
            
            # 캐시 저장
            self._save_cache(doc_id, result)
            
            logger.info(f"[NewsExtractor] Extracted from {doc_id}: "
                       f"{len(result.events)} events, {len(result.facts)} facts, "
                       f"{len(result.claims)} claims, {len(result.links)} links "
                       f"in {processing_time}ms")
            
            return result
            
        except Exception as e:
            logger.error(f"[NewsExtractor] Extraction failed for {doc_id}: {e}")
            # 실패 시 빈 결과 반환 (with error)
            return ExtractionResult(
                doc_id=doc_id,
                extractor_version=self.extractor_version,
                model_name=self.model_name,
                error_messages=[str(e)],
                processing_time_ms=int((datetime.now() - start_time).total_seconds() * 1000)
            )


# Global instance
_extractor = None

def get_news_extractor() -> NewsExtractor:
    """싱글톤 NewsExtractor 인스턴스 반환"""
    global _extractor
    if _extractor is None:
        _extractor = NewsExtractor()
    return _extractor
