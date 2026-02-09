"""
Phase E-2: Graph Context Provider for Strategy Prompts
전략 결정(MP/Sub-MP) 프롬프트에 주입할 Macro Graph 컨텍스트를 생성합니다.
"""

import logging
from datetime import date, timedelta
from typing import Optional, Dict, Any, List

from service.graph.neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class StrategyGraphContextProvider:
    """
    전략 분석용 그래프 컨텍스트 제공자
    
    ai_strategist의 MP/Sub-MP 프롬프트에 Macro Graph의 근거(Evidence, Event, Story 등)를
    주입하여 근거 기반 전략 결정을 지원합니다.
    """

    def __init__(self):
        self.neo4j_client = None

    def _get_client(self):
        """Neo4j 클라이언트 lazy 초기화"""
        if self.neo4j_client is None:
            try:
                self.neo4j_client = get_neo4j_client()
            except Exception as e:
                logger.warning(f"[StrategyGraphContext] Neo4j 클라이언트 초기화 실패: {e}")
                self.neo4j_client = None
        return self.neo4j_client

    def build_strategy_context(
        self,
        as_of_date: Optional[date] = None,
        time_range_days: int = 7,
        country: Optional[str] = None,
        theme_ids: Optional[List[str]] = None,
        max_events: int = 5,
        max_stories: int = 3,
        max_evidences: int = 5,
    ) -> str:
        """
        전략 프롬프트에 주입할 그래프 컨텍스트 블록 생성
        
        Args:
            as_of_date: 기준 날짜 (기본: 오늘)
            time_range_days: 조회 기간 (일)
            country: 국가 필터 (예: "US", "KR")
            theme_ids: 관심 테마 ID 리스트 (예: ["inflation", "growth"])
            max_events: 최대 이벤트 수
            max_stories: 최대 스토리 수
            max_evidences: 최대 Evidence 수
            
        Returns:
            LLM 프롬프트에 삽입할 컨텍스트 문자열 (비어있을 수 있음)
        """
        try:
            client = self._get_client()
            if client is None:
                logger.info("[StrategyGraphContext] Neo4j 연결 불가, 빈 컨텍스트 반환")
                return ""

            as_of_date = as_of_date or date.today()
            start_date = as_of_date - timedelta(days=time_range_days)

            # 1. 최근 주요 이벤트 조회
            events = self._fetch_recent_events(
                client, start_date, as_of_date, country, max_events
            )

            # 2. 최근 스토리 조회
            stories = self._fetch_recent_stories(
                client, start_date, as_of_date, max_stories
            )

            # 3. 핵심 Evidence 조회 (테마 관련)
            evidences = self._fetch_relevant_evidences(
                client, start_date, as_of_date, theme_ids, max_evidences
            )

            # 4. 컨텍스트 블록 조립
            context_block = self._assemble_context_block(
                events, stories, evidences, as_of_date, time_range_days
            )

            if context_block.strip():
                logger.info(
                    f"[StrategyGraphContext] 컨텍스트 생성 완료: "
                    f"events={len(events)}, stories={len(stories)}, evidences={len(evidences)}"
                )
            else:
                logger.info("[StrategyGraphContext] 그래프에 관련 데이터 없음, 빈 컨텍스트")

            return context_block

        except Exception as e:
            logger.warning(f"[StrategyGraphContext] 컨텍스트 생성 실패, 빈 문자열 반환: {e}")
            return ""

    def _fetch_recent_events(
        self,
        client,
        start_date: date,
        end_date: date,
        country: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """최근 주요 이벤트 조회"""
        try:
            query = """
            // phase_e_strategy_recent_events
            MATCH (e:Event)
            WHERE e.event_time IS NOT NULL
              AND date(e.event_time) >= date($start_date)
              AND date(e.event_time) <= date($end_date)
              AND ($country IS NULL OR e.country = $country)
            OPTIONAL MATCH (e)<-[:MENTIONS]-(d:Document)
            WITH e, count(DISTINCT d) AS doc_count
            ORDER BY doc_count DESC, e.event_time DESC
            LIMIT $limit
            RETURN e.event_id AS event_id,
                   e.summary AS summary,
                   e.event_type AS event_type,
                   e.country AS country,
                   e.event_time AS event_time,
                   doc_count
            """
            rows = client.run_read(query, {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "country": country,
                "limit": limit,
            })
            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"[StrategyGraphContext] 이벤트 조회 실패: {e}")
            return []

    def _fetch_recent_stories(
        self,
        client,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """최근 스토리 조회"""
        try:
            query = """
            // phase_e_strategy_recent_stories
            MATCH (s:Story)
            WHERE s.story_date IS NOT NULL
              AND date(s.story_date) >= date($start_date)
              AND date(s.story_date) <= date($end_date)
            OPTIONAL MATCH (s)-[:AGGREGATES]->(d:Document)
            WITH s, count(DISTINCT d) AS doc_count
            ORDER BY doc_count DESC, s.story_date DESC
            LIMIT $limit
            RETURN s.story_id AS story_id,
                   s.title AS title,
                   s.summary AS summary,
                   s.story_date AS story_date,
                   doc_count
            """
            rows = client.run_read(query, {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "limit": limit,
            })
            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"[StrategyGraphContext] 스토리 조회 실패: {e}")
            return []

    def _fetch_relevant_evidences(
        self,
        client,
        start_date: date,
        end_date: date,
        theme_ids: Optional[List[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """관련 Evidence 조회 (테마 필터 적용)"""
        try:
            # 테마 필터가 있으면 해당 테마와 연결된 Evidence 우선
            if theme_ids:
                query = """
                // phase_e_strategy_themed_evidences
                MATCH (ev:Evidence)-[:SUPPORTS]->(target)
                WHERE (target:MacroTheme AND target.theme_id IN $theme_ids)
                   OR (target:Event)-[:ABOUT_THEME]->(:MacroTheme {theme_id: $theme_ids[0]})
                MATCH (ev)<-[:HAS_EVIDENCE]-(d:Document)
                WHERE d.published_at IS NOT NULL
                  AND date(d.published_at) >= date($start_date)
                  AND date(d.published_at) <= date($end_date)
                RETURN ev.evidence_id AS evidence_id,
                       ev.text AS text,
                       d.doc_id AS doc_id,
                       d.title AS doc_title,
                       coalesce(d.url, d.link) AS doc_url,
                       d.published_at AS published_at
                ORDER BY d.published_at DESC
                LIMIT $limit
                """
                rows = client.run_read(query, {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "theme_ids": theme_ids,
                    "limit": limit,
                })
            else:
                # 테마 필터 없으면 최근 Evidence 조회
                query = """
                // phase_e_strategy_recent_evidences
                MATCH (ev:Evidence)<-[:HAS_EVIDENCE]-(d:Document)
                WHERE d.published_at IS NOT NULL
                  AND date(d.published_at) >= date($start_date)
                  AND date(d.published_at) <= date($end_date)
                RETURN ev.evidence_id AS evidence_id,
                       ev.text AS text,
                       d.doc_id AS doc_id,
                       d.title AS doc_title,
                       coalesce(d.url, d.link) AS doc_url,
                       d.published_at AS published_at
                ORDER BY d.published_at DESC
                LIMIT $limit
                """
                rows = client.run_read(query, {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "limit": limit,
                })

            return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"[StrategyGraphContext] Evidence 조회 실패: {e}")
            return []

    def _assemble_context_block(
        self,
        events: List[Dict],
        stories: List[Dict],
        evidences: List[Dict],
        as_of_date: date,
        time_range_days: int,
    ) -> str:
        """컨텍스트 블록 조립"""
        if not events and not stories and not evidences:
            return ""

        lines = []
        lines.append(f"\n=== Macro Graph 근거 (최근 {time_range_days}일, {as_of_date} 기준) ===\n")

        # 이벤트 섹션
        if events:
            lines.append("### 주요 이벤트:")
            for i, evt in enumerate(events, 1):
                summary = evt.get("summary") or evt.get("event_id", "N/A")
                event_type = evt.get("event_type", "")
                country = evt.get("country", "")
                event_time = evt.get("event_time", "")
                
                # event_time 포맷팅
                if hasattr(event_time, 'strftime'):
                    event_time = event_time.strftime("%Y-%m-%d")
                elif event_time:
                    event_time = str(event_time)[:10]
                
                lines.append(f"  {i}. [{event_type}] {summary} ({country}, {event_time})")
            lines.append("")

        # 스토리 섹션
        if stories:
            lines.append("### 주요 스토리:")
            for i, story in enumerate(stories, 1):
                title = story.get("title") or story.get("story_id", "N/A")
                summary = story.get("summary", "")
                story_date = story.get("story_date", "")
                
                if hasattr(story_date, 'strftime'):
                    story_date = story_date.strftime("%Y-%m-%d")
                elif story_date:
                    story_date = str(story_date)[:10]
                
                lines.append(f"  {i}. {title} ({story_date})")
                if summary:
                    lines.append(f"     → {summary[:100]}...")
            lines.append("")

        # Evidence 섹션
        if evidences:
            lines.append("### 핵심 근거 (Evidence):")
            for i, ev in enumerate(evidences, 1):
                text = ev.get("text", "")[:150]
                doc_title = ev.get("doc_title", "")
                doc_url = ev.get("doc_url", "")
                
                lines.append(f"  {i}. \"{text}...\"")
                if doc_title:
                    lines.append(f"     출처: {doc_title}")
                if doc_url:
                    lines.append(f"     URL: {doc_url}")
            lines.append("")

        lines.append("=== (Graph 근거 끝) ===\n")

        return "\n".join(lines)


# 싱글톤 인스턴스
_strategy_graph_context_provider = None


def get_strategy_graph_context_provider() -> StrategyGraphContextProvider:
    """StrategyGraphContextProvider 싱글톤 인스턴스 반환"""
    global _strategy_graph_context_provider
    if _strategy_graph_context_provider is None:
        _strategy_graph_context_provider = StrategyGraphContextProvider()
    return _strategy_graph_context_provider


def build_strategy_graph_context(
    as_of_date: Optional[date] = None,
    time_range_days: int = 7,
    country: Optional[str] = None,
    theme_ids: Optional[List[str]] = None,
    max_events: int = 5,
    max_stories: int = 3,
    max_evidences: int = 5,
) -> str:
    """
    전략 프롬프트용 그래프 컨텍스트 생성 (편의 함수)
    
    그래프가 비어있거나 Neo4j 장애 시 빈 문자열 반환 (기존 전략 로직 폴백)
    """
    provider = get_strategy_graph_context_provider()
    return provider.build_strategy_context(
        as_of_date=as_of_date,
        time_range_days=time_range_days,
        country=country,
        theme_ids=theme_ids,
        max_events=max_events,
        max_stories=max_stories,
        max_evidences=max_evidences,
    )
