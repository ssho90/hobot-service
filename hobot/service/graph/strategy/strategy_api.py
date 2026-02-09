"""
Phase E-5: Strategy Decision API
전략결정 및 Macro Graph 근거 조회 API
"""

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from service.graph.neo4j_client import get_neo4j_client
from service.graph.strategy.decision_mirror import (
    mirror_latest_strategy_decision,
    mirror_strategy_decisions_backfill,
)
from service.graph.strategy.graph_context_provider import build_strategy_graph_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])


# ============================================================================
# Request/Response Models
# ============================================================================


class StrategyDecisionSummary(BaseModel):
    """전략 결정 요약"""
    decision_id: str
    decision_date: str
    mp_id: str
    target_allocation: Dict[str, Any] = Field(default_factory=dict)
    sub_mp: Dict[str, Any] = Field(default_factory=dict)
    analysis_summary: Optional[str] = None
    reasoning: Optional[str] = None


class StrategyDecisionListResponse(BaseModel):
    """전략 결정 목록 응답"""
    decisions: List[StrategyDecisionSummary]
    total: int
    message: str


class StrategyDecisionDetailResponse(BaseModel):
    """전략 결정 상세 응답"""
    decision: StrategyDecisionSummary
    related_events: List[Dict[str, Any]] = Field(default_factory=list)
    related_evidences: List[Dict[str, Any]] = Field(default_factory=list)
    related_macro_state: Optional[Dict[str, Any]] = None


class StrategyMirrorRequest(BaseModel):
    """미러링 요청"""
    days: int = Field(default=30, ge=1, le=365)


class StrategyMirrorResponse(BaseModel):
    """미러링 응답"""
    success: bool
    count: int
    errors: int = 0
    message: str


class StrategyContextRequest(BaseModel):
    """그래프 컨텍스트 요청"""
    as_of_date: Optional[date] = None
    time_range_days: int = Field(default=7, ge=1, le=90)
    max_events: int = Field(default=5, ge=1, le=20)
    max_stories: int = Field(default=3, ge=1, le=10)
    max_evidences: int = Field(default=5, ge=1, le=20)


class StrategyContextResponse(BaseModel):
    """그래프 컨텍스트 응답"""
    context_text: str
    context_length: int
    as_of_date: str
    time_range_days: int


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/decisions", response_model=StrategyDecisionListResponse)
async def list_strategy_decisions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    mp_id: Optional[str] = Query(default=None, description="MP ID 필터"),
    start_date: Optional[date] = Query(default=None, description="시작 날짜"),
    end_date: Optional[date] = Query(default=None, description="종료 날짜"),
):
    """
    Macro Graph에서 전략 결정 목록 조회
    """
    try:
        client = get_neo4j_client()
        
        # 동적 쿼리 생성
        where_clauses = []
        params = {"limit": limit, "offset": offset}
        
        if mp_id:
            where_clauses.append("sd.mp_id = $mp_id")
            params["mp_id"] = mp_id
        if start_date:
            where_clauses.append("sd.decision_date >= date($start_date)")
            params["start_date"] = start_date.isoformat()
        if end_date:
            where_clauses.append("sd.decision_date <= date($end_date)")
            params["end_date"] = end_date.isoformat()
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "true"
        
        query = f"""
        // phase_e_list_strategy_decisions
        MATCH (sd:StrategyDecision)
        WHERE {where_clause}
        WITH sd ORDER BY sd.decision_date DESC
        SKIP $offset LIMIT $limit
        RETURN sd.decision_id AS decision_id,
               toString(sd.decision_date) AS decision_date,
               sd.mp_id AS mp_id,
               sd.target_allocation AS target_allocation,
               sd.sub_mp AS sub_mp,
               sd.analysis_summary AS analysis_summary,
               sd.reasoning AS reasoning
        """
        
        rows = client.run_read(query, params)
        
        decisions = []
        for row in rows:
            decisions.append(StrategyDecisionSummary(
                decision_id=row.get("decision_id", ""),
                decision_date=row.get("decision_date", ""),
                mp_id=row.get("mp_id", ""),
                target_allocation=_parse_json_str(row.get("target_allocation", "{}")),
                sub_mp=_parse_json_str(row.get("sub_mp", "{}")),
                analysis_summary=row.get("analysis_summary"),
                reasoning=row.get("reasoning"),
            ))
        
        # 전체 수 조회
        count_query = f"""
        MATCH (sd:StrategyDecision) WHERE {where_clause}
        RETURN count(sd) AS total
        """
        count_result = client.run_read(count_query, params)
        total = count_result[0]["total"] if count_result else 0
        
        return StrategyDecisionListResponse(
            decisions=decisions,
            total=total,
            message=f"Found {len(decisions)} decisions (total: {total})"
        )
        
    except Exception as e:
        logger.error(f"전략 결정 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


@router.get("/decisions/{decision_id}", response_model=StrategyDecisionDetailResponse)
async def get_strategy_decision_detail(decision_id: str):
    """
    특정 전략 결정 상세 조회 (관련 이벤트/Evidence 포함)
    """
    try:
        client = get_neo4j_client()
        
        # 전략 결정 조회
        query = """
        // phase_e_get_strategy_decision_detail
        MATCH (sd:StrategyDecision {decision_id: $decision_id})
        OPTIONAL MATCH (sd)-[:BASED_ON]->(ms:MacroState)
        RETURN sd.decision_id AS decision_id,
               toString(sd.decision_date) AS decision_date,
               sd.mp_id AS mp_id,
               sd.target_allocation AS target_allocation,
               sd.sub_mp AS sub_mp,
               sd.analysis_summary AS analysis_summary,
               sd.reasoning AS reasoning,
               ms.state_id AS macro_state_id,
               ms.summary AS macro_state_summary
        """
        
        rows = client.run_read(query, {"decision_id": decision_id})
        
        if not rows:
            raise HTTPException(status_code=404, detail=f"Decision not found: {decision_id}")
        
        row = rows[0]
        decision = StrategyDecisionSummary(
            decision_id=row.get("decision_id", ""),
            decision_date=row.get("decision_date", ""),
            mp_id=row.get("mp_id", ""),
            target_allocation=_parse_json_str(row.get("target_allocation", "{}")),
            sub_mp=_parse_json_str(row.get("sub_mp", "{}")),
            analysis_summary=row.get("analysis_summary"),
            reasoning=row.get("reasoning"),
        )
        
        macro_state = None
        if row.get("macro_state_id"):
            macro_state = {
                "state_id": row.get("macro_state_id"),
                "summary": row.get("macro_state_summary"),
            }
        
        # 관련 이벤트 조회 (해당 날짜의 이벤트)
        decision_date = row.get("decision_date", "")
        related_events = []
        if decision_date:
            event_query = """
            MATCH (e:Event)
            WHERE date(e.event_time) = date($decision_date)
            RETURN e.event_id AS event_id,
                   e.summary AS summary,
                   toString(e.event_time) AS event_time
            LIMIT 5
            """
            event_rows = client.run_read(event_query, {"decision_date": decision_date})
            related_events = [dict(r) for r in event_rows]
        
        # 관련 Evidence 조회 (해당 날짜의 Evidence)
        related_evidences = []
        if decision_date:
            evidence_query = """
            MATCH (ev:Evidence)<-[:HAS_EVIDENCE]-(d:Document)
            WHERE date(d.published_at) = date($decision_date)
            RETURN ev.evidence_id AS evidence_id,
                   ev.text AS text,
                   d.title AS doc_title,
                   coalesce(d.url, d.link) AS doc_url
            LIMIT 5
            """
            evidence_rows = client.run_read(evidence_query, {"decision_date": decision_date})
            related_evidences = [dict(r) for r in evidence_rows]
        
        return StrategyDecisionDetailResponse(
            decision=decision,
            related_events=related_events,
            related_evidences=related_evidences,
            related_macro_state=macro_state,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"전략 결정 상세 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"조회 실패: {str(e)}")


@router.post("/mirror", response_model=StrategyMirrorResponse)
async def mirror_strategy_decisions(request: StrategyMirrorRequest):
    """
    MySQL ai_strategy_decisions → Macro Graph 미러링 (백필)
    """
    try:
        result = mirror_strategy_decisions_backfill(days=request.days)
        return StrategyMirrorResponse(
            success=result.get("success", False),
            count=result.get("count", 0),
            errors=result.get("errors", 0),
            message=result.get("message", ""),
        )
    except Exception as e:
        logger.error(f"미러링 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"미러링 실패: {str(e)}")


@router.post("/mirror/latest", response_model=StrategyMirrorResponse)
async def mirror_latest_decision():
    """
    최신 MySQL 전략 결정을 Macro Graph에 미러링
    """
    try:
        result = mirror_latest_strategy_decision()
        if result:
            return StrategyMirrorResponse(
                success=True,
                count=1,
                message=f"Mirrored: {result.get('decision_id', 'unknown')}"
            )
        else:
            return StrategyMirrorResponse(
                success=True,
                count=0,
                message="No decisions to mirror"
            )
    except Exception as e:
        logger.error(f"최신 미러링 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"미러링 실패: {str(e)}")


@router.post("/context", response_model=StrategyContextResponse)
async def get_strategy_graph_context(request: StrategyContextRequest):
    """
    AI 전략가 프롬프트용 그래프 컨텍스트 생성
    """
    try:
        as_of = request.as_of_date or date.today()
        context_text = build_strategy_graph_context(
            as_of_date=as_of,
            time_range_days=request.time_range_days,
            max_events=request.max_events,
            max_stories=request.max_stories,
            max_evidences=request.max_evidences,
        )
        
        return StrategyContextResponse(
            context_text=context_text,
            context_length=len(context_text),
            as_of_date=as_of.isoformat(),
            time_range_days=request.time_range_days,
        )
    except Exception as e:
        logger.error(f"컨텍스트 생성 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"컨텍스트 생성 실패: {str(e)}")


@router.get("/stats")
async def get_strategy_stats():
    """
    전략 결정 통계 조회
    """
    try:
        client = get_neo4j_client()
        
        query = """
        // phase_e_strategy_stats
        MATCH (sd:StrategyDecision)
        WITH count(sd) AS total_decisions,
             collect(DISTINCT sd.mp_id) AS mp_ids
        MATCH (sd2:StrategyDecision)
        WITH total_decisions, mp_ids,
             min(sd2.decision_date) AS earliest_date,
             max(sd2.decision_date) AS latest_date
        UNWIND mp_ids AS mp_id
        OPTIONAL MATCH (sd3:StrategyDecision {mp_id: mp_id})
        WITH total_decisions, earliest_date, latest_date, mp_id, count(sd3) AS mp_count
        RETURN total_decisions, 
               toString(earliest_date) AS earliest_date, 
               toString(latest_date) AS latest_date,
               collect({mp_id: mp_id, count: mp_count}) AS mp_distribution
        """
        
        rows = client.run_read(query, {})
        
        if not rows:
            return {
                "total_decisions": 0,
                "earliest_date": None,
                "latest_date": None,
                "mp_distribution": [],
            }
        
        row = rows[0]
        return {
            "total_decisions": row.get("total_decisions", 0),
            "earliest_date": row.get("earliest_date"),
            "latest_date": row.get("latest_date"),
            "mp_distribution": row.get("mp_distribution", []),
        }
        
    except Exception as e:
        logger.error(f"통계 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")


# ============================================================================
# Helper Functions
# ============================================================================


def _parse_json_str(value) -> Dict[str, Any]:
    """JSON 문자열 파싱"""
    import json
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    elif isinstance(value, dict):
        return value
    return {}
