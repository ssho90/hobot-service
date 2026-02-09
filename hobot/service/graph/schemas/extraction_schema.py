"""
Phase B-1: LLM Extraction JSON Schema
뉴스에서 추출되는 Event, Fact, Claim, Evidence, Link의 Pydantic 모델
"""

from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

# Schema Version (변경 시 버전 업)
SCHEMA_VERSION = "1.0"


class SentimentType(str, Enum):
    """감정 분류"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ConfidenceLevel(str, Enum):
    """신뢰도 레벨"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LinkType(str, Enum):
    """관계 타입"""
    AFFECTS = "AFFECTS"
    CAUSES = "CAUSES"
    CORRELATES = "CORRELATES"
    MENTIONS = "MENTIONS"


# ============ Core Extraction Models ============

class Evidence(BaseModel):
    """
    증거 노드: Fact/Claim을 뒷받침하는 원문 인용
    (Document)-[:HAS_EVIDENCE]->(Evidence)
    (Evidence)-[:SUPPORTS]->(Claim|Fact)
    """
    evidence_text: str = Field(..., min_length=10, description="원문에서 발췌한 증거 텍스트")
    source_sentence: Optional[str] = Field(None, description="증거가 포함된 전체 문장")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM, description="증거 신뢰도")
    language: str = Field(default="en", description="증거 언어코드 (ISO 639-1)")
    
    # Deterministic ID 생성용
    _evidence_id: Optional[str] = None
    
    def generate_evidence_id(self, doc_id: str) -> str:
        """Deterministic Evidence ID 생성: hash(doc_id + evidence_text + lang)"""
        content = f"{doc_id}:{self.evidence_text}:{self.language}"
        self._evidence_id = f"EV_{sha256(content.encode()).hexdigest()[:16]}"
        return self._evidence_id
    
    @property
    def evidence_id(self) -> Optional[str]:
        return self._evidence_id


class Fact(BaseModel):
    """
    사실 노드: 객관적으로 검증 가능한 정보
    예: "Fed raised rates by 25bps"
    """
    fact_text: str = Field(..., min_length=5, description="사실 내용")
    fact_type: Literal["economic_event", "economic_release", "policy_action", "market_data", "statement", "data_release", "other"] = Field(
        default="other", description="사실 유형"
    )
    entities_mentioned: List[str] = Field(default_factory=list, description="언급된 엔티티명")
    date_mentioned: Optional[date] = Field(None, description="사실에서 언급된 날짜")
    evidences: List[Evidence] = Field(default_factory=list, description="뒷받침하는 증거들")
    
    @field_validator('evidences', mode='after')
    @classmethod
    def validate_evidences(cls, v: List[Evidence]) -> List[Evidence]:
        """최소 1개 이상의 Evidence 필요"""
        if not v:
            raise ValueError("Fact must have at least one Evidence")
        return v


class Claim(BaseModel):
    """
    주장 노드: 의견/예측/판단
    예: "Analysts expect further rate hikes"
    """
    claim_text: str = Field(..., min_length=5, description="주장 내용")
    claim_type: Literal["prediction", "opinion", "analysis", "recommendation", "expectation", "statement", "forecast", "other"] = Field(
        default="other", description="주장 유형"
    )
    author: Optional[str] = Field(None, description="주장의 출처/저자")
    sentiment: SentimentType = Field(default=SentimentType.NEUTRAL, description="주장의 감정")
    evidences: List[Evidence] = Field(default_factory=list, description="뒷받침하는 증거들")
    
    @field_validator('evidences', mode='after')
    @classmethod
    def validate_evidences(cls, v: List[Evidence]) -> List[Evidence]:
        """최소 1개 이상의 Evidence 필요"""
        if not v:
            raise ValueError("Claim must have at least one Evidence")
        return v


class Event(BaseModel):
    """
    이벤트 노드: 시장에 영향을 미치는 사건
    예: FOMC Meeting, CPI Release, Earnings Report
    """
    event_name: str = Field(..., min_length=3, description="이벤트명")
    event_type: Literal["policy", "economic_release", "market_event", "geopolitical", "corporate", "other"] = Field(
        default="other", description="이벤트 유형"
    )
    event_date: Optional[date] = Field(None, description="이벤트 날짜")
    description: Optional[str] = Field(None, description="이벤트 설명")
    impact_level: Literal["high", "medium", "low"] = Field(default="medium", description="영향도")
    related_themes: List[str] = Field(default_factory=list, description="관련 MacroTheme IDs")
    related_indicators: List[str] = Field(default_factory=list, description="관련 Indicator Codes")


class Link(BaseModel):
    """
    관계 링크: 엔티티/이벤트 간 관계
    반드시 Evidence가 있어야 AFFECTS/CAUSES 관계 생성 가능
    """
    source_type: Literal["Event", "Fact", "Claim", "Entity", "Indicator"] = Field(..., description="소스 타입")
    source_ref: str = Field(..., description="소스 참조 (이름 또는 ID)")
    target_type: Literal["Theme", "Indicator", "Entity", "Event"] = Field(..., description="타겟 타입")
    target_ref: str = Field(..., description="타겟 참조")
    link_type: LinkType = Field(..., description="관계 타입")
    strength: float = Field(default=0.5, ge=0.0, le=1.0, description="관계 강도 (0-1)")
    evidence: Optional[Evidence] = Field(None, description="관계를 뒷받침하는 증거")
    
    @model_validator(mode='after')
    def validate_evidence_for_causal_links(self):
        """AFFECTS/CAUSES 관계는 반드시 Evidence 필요"""
        if self.link_type in [LinkType.AFFECTS, LinkType.CAUSES]:
            if not self.evidence:
                raise ValueError(f"{self.link_type} relationship requires Evidence")
        return self


# ============ Full Extraction Result ============

class ExtractionResult(BaseModel):
    """
    전체 추출 결과: 하나의 Document에서 추출된 모든 정보
    """
    schema_version: str = Field(default=SCHEMA_VERSION, description="스키마 버전")
    doc_id: str = Field(..., description="원본 Document ID")
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="추출 시점")
    extractor_version: str = Field(default="1.0", description="추출기 버전")
    model_name: str = Field(default="gemini-3-flash-preview", description="사용된 LLM 모델")
    
    # 추출된 엔티티들
    events: List[Event] = Field(default_factory=list, description="추출된 이벤트들")
    facts: List[Fact] = Field(default_factory=list, description="추출된 사실들")
    claims: List[Claim] = Field(default_factory=list, description="추출된 주장들")
    links: List[Link] = Field(default_factory=list, description="추출된 관계들")
    
    # 추출 메타데이터
    extraction_confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="전체 추출 신뢰도")
    processing_time_ms: Optional[int] = Field(None, description="처리 시간 (ms)")
    error_messages: List[str] = Field(default_factory=list, description="추출 중 발생한 경고/에러")
    
    def generate_all_evidence_ids(self):
        """모든 Evidence에 대해 ID 생성"""
        for fact in self.facts:
            for evidence in fact.evidences:
                evidence.generate_evidence_id(self.doc_id)
        for claim in self.claims:
            for evidence in claim.evidences:
                evidence.generate_evidence_id(self.doc_id)
        for link in self.links:
            if link.evidence:
                link.evidence.generate_evidence_id(self.doc_id)
    
    def get_all_evidences(self) -> List[Evidence]:
        """모든 Evidence 수집"""
        evidences = []
        for fact in self.facts:
            evidences.extend(fact.evidences)
        for claim in self.claims:
            evidences.extend(claim.evidences)
        for link in self.links:
            if link.evidence:
                evidences.append(link.evidence)
        return evidences
    
    def validate_evidence_coverage(self) -> dict:
        """Evidence 커버리지 검증"""
        facts_with_evidence = sum(1 for f in self.facts if f.evidences)
        claims_with_evidence = sum(1 for c in self.claims if c.evidences)
        causal_links = [l for l in self.links if l.link_type in [LinkType.AFFECTS, LinkType.CAUSES]]
        causal_with_evidence = sum(1 for l in causal_links if l.evidence)
        
        return {
            "facts_total": len(self.facts),
            "facts_with_evidence": facts_with_evidence,
            "claims_total": len(self.claims),
            "claims_with_evidence": claims_with_evidence,
            "causal_links_total": len(causal_links),
            "causal_links_with_evidence": causal_with_evidence,
            "evidence_coverage_rate": (
                (facts_with_evidence + claims_with_evidence + causal_with_evidence) /
                max(len(self.facts) + len(self.claims) + len(causal_links), 1)
            )
        }


# ============ Validation Helper ============

class ExtractionValidator:
    """추출 결과 검증기"""
    
    @staticmethod
    def validate(result: ExtractionResult) -> tuple[bool, List[str]]:
        """
        추출 결과 검증
        Returns: (is_valid, error_messages)
        """
        errors = []
        
        # 1. Evidence 커버리지 검증
        coverage = result.validate_evidence_coverage()
        if coverage["evidence_coverage_rate"] < 0.8:
            errors.append(f"Evidence coverage too low: {coverage['evidence_coverage_rate']:.2%}")
        
        # 2. 최소 추출 확인
        if not result.events and not result.facts and not result.claims:
            errors.append("No meaningful content extracted")
        
        # 3. Link 검증 (AFFECTS/CAUSES는 Evidence 필수 - 이미 Pydantic에서 검증됨)
        
        # 4. Schema version 확인
        if result.schema_version != SCHEMA_VERSION:
            errors.append(f"Schema version mismatch: expected {SCHEMA_VERSION}, got {result.schema_version}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_and_raise(result: ExtractionResult):
        """검증 실패 시 예외 발생"""
        is_valid, errors = ExtractionValidator.validate(result)
        if not is_valid:
            raise ValueError(f"Extraction validation failed: {'; '.join(errors)}")
