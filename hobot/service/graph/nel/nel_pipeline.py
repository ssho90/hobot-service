"""
Phase B-5: NEL (Named Entity Linking) Pipeline
텍스트에서 Entity mention을 추출하고 canonical ID로 연결하는 파이프라인
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from hashlib import sha256

from .alias_dictionary import get_alias_lookup, AliasLookup

logger = logging.getLogger(__name__)


@dataclass
class EntityMention:
    """텍스트에서 발견된 Entity 멘션"""
    text: str                    # 원문 텍스트
    start_pos: int              # 시작 위치
    end_pos: int                # 끝 위치
    entity_type: Optional[str] = None    # 추론된 엔티티 타입
    canonical_id: Optional[str] = None   # 연결된 canonical ID
    canonical_name: Optional[str] = None # canonical 이름
    confidence: float = 0.0              # 연결 신뢰도


@dataclass
class NELResult:
    """NEL 파이프라인 결과"""
    mentions: List[EntityMention]
    resolved_count: int
    unresolved_count: int
    resolution_rate: float


class NELPipeline:
    """
    Named Entity Linking 파이프라인
    
    Step 1: Mention 추출 (룰 기반 + LLM 출력)
    Step 2: 후보 생성 (Alias Dictionary)
    Step 3: 연결 판별 (스코어링 + 임계치)
    Step 4: canonical_id로 MERGE
    """
    
    # 일반적인 Entity 패턴 (대문자로 시작하는 단어 시퀀스)
    ENTITY_PATTERNS = [
        # Institutions (대문자 약어)
        r'\b(FED|FOMC|ECB|BOJ|BOE|PBOC|IMF|BIS|BLS|BEA)\b',
        # Names (First Last 패턴)
        r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b',
        # Proper nouns with "the" (예: the Fed, the Treasury)
        r'\b[Tt]he ([A-Z][a-zA-Z]+)\b',
        # Economic indicators (대문자)
        r'\b(CPI|PPI|PCE|GDP|NFP|VIX|PMI)\b',
        # Markets/Indices
        r'\b(S&P 500|S&P500|NASDAQ|Dow Jones|DJIA)\b',
    ]
    
    def __init__(self, alias_lookup: Optional[AliasLookup] = None, min_confidence: float = 0.5):
        self.alias_lookup = alias_lookup or get_alias_lookup()
        self.min_confidence = min_confidence
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.ENTITY_PATTERNS]
    
    def extract_mentions(self, text: str) -> List[EntityMention]:
        """
        Step 1: 텍스트에서 Entity mention 추출
        """
        mentions = []
        seen_positions = set()
        
        for pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                # 그룹이 있으면 그룹 사용, 없으면 전체 매치
                if match.groups():
                    mention_text = match.group(1)
                    start = match.start(1)
                    end = match.end(1)
                else:
                    mention_text = match.group(0)
                    start = match.start(0)
                    end = match.end(0)
                
                # 중복 위치 스킵
                pos_key = (start, end)
                if pos_key in seen_positions:
                    continue
                seen_positions.add(pos_key)
                
                mentions.append(EntityMention(
                    text=mention_text,
                    start_pos=start,
                    end_pos=end
                ))
        
        # 위치순 정렬
        mentions.sort(key=lambda m: m.start_pos)
        return mentions
    
    def generate_candidates(self, mention: EntityMention) -> List[Tuple[str, str, str, float]]:
        """
        Step 2: 멘션에 대한 후보 entity 생성
        Returns: List of (entity_type, canonical_id, canonical_name, score)
        """
        result = self.alias_lookup.lookup(mention.text)
        
        if result:
            entity_type, canonical_id, canonical_name = result
            # 직접 매칭은 높은 점수
            return [(entity_type, canonical_id, canonical_name, 0.9)]
        
        # 후보 없음
        return []
    
    def resolve_mention(self, mention: EntityMention) -> EntityMention:
        """
        Step 3: 멘션을 canonical entity로 연결
        """
        candidates = self.generate_candidates(mention)
        
        if candidates:
            # 가장 높은 점수의 후보 선택
            best_candidate = max(candidates, key=lambda c: c[3])
            entity_type, canonical_id, canonical_name, score = best_candidate
            
            if score >= self.min_confidence:
                mention.entity_type = entity_type
                mention.canonical_id = canonical_id
                mention.canonical_name = canonical_name
                mention.confidence = score
        
        return mention
    
    def process(self, text: str) -> NELResult:
        """
        전체 NEL 파이프라인 실행
        
        Args:
            text: 처리할 텍스트
        
        Returns:
            NELResult with resolved mentions
        """
        # Step 1: Mention 추출
        mentions = self.extract_mentions(text)
        
        # Step 2-3: 각 멘션 해결
        for mention in mentions:
            self.resolve_mention(mention)
        
        # 통계 계산
        resolved = [m for m in mentions if m.canonical_id]
        unresolved = [m for m in mentions if not m.canonical_id]
        
        resolution_rate = len(resolved) / len(mentions) if mentions else 1.0
        
        return NELResult(
            mentions=mentions,
            resolved_count=len(resolved),
            unresolved_count=len(unresolved),
            resolution_rate=resolution_rate
        )
    
    def process_with_llm_mentions(self, text: str, llm_entities: List[str]) -> NELResult:
        """
        LLM이 추출한 entity 목록을 함께 처리
        
        Args:
            text: 원문 텍스트
            llm_entities: LLM이 추출한 entity 이름 목록
        
        Returns:
            NELResult
        """
        # 룰 기반 추출
        mentions = self.extract_mentions(text)
        
        # LLM 엔티티 추가 (텍스트에서 위치 찾기)
        for entity_name in llm_entities:
            # 이미 추출된 것인지 확인
            already_extracted = any(
                m.text.lower() == entity_name.lower() 
                for m in mentions
            )
            if already_extracted:
                continue
            
            # 텍스트에서 위치 찾기
            pattern = re.escape(entity_name)
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                mentions.append(EntityMention(
                    text=entity_name,
                    start_pos=match.start(),
                    end_pos=match.end()
                ))
        
        # 위치순 정렬 및 해결
        mentions.sort(key=lambda m: m.start_pos)
        for mention in mentions:
            self.resolve_mention(mention)
        
        resolved = [m for m in mentions if m.canonical_id]
        unresolved = [m for m in mentions if not m.canonical_id]
        
        return NELResult(
            mentions=mentions,
            resolved_count=len(resolved),
            unresolved_count=len(unresolved),
            resolution_rate=len(resolved) / len(mentions) if mentions else 1.0
        )
    
    def generate_entity_id(self, mention: EntityMention, source: str = "unknown") -> str:
        """
        미해결 entity에 대해 새로운 ID 생성
        Format: NEW_{hash(source:text)[:12]}
        """
        content = f"{source}:{mention.text.lower()}"
        return f"NEW_{sha256(content.encode()).hexdigest()[:12]}"


# Global instance
_nel_pipeline = None

def get_nel_pipeline() -> NELPipeline:
    """싱글톤 NEL Pipeline 인스턴스 반환"""
    global _nel_pipeline
    if _nel_pipeline is None:
        _nel_pipeline = NELPipeline()
    return _nel_pipeline
