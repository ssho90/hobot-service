"""
Phase D-5: GraphRAG monitoring metrics.
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, Optional, Sequence

from fastapi import APIRouter, HTTPException, Query

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph/rag", tags=["graph-rag"])


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


class GraphRagApiCallLogger:
    """GraphRAG API 호출 로그를 Graph DB에 저장한다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _hash_text(value: Optional[str]) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:20]

    def log_call(
        self,
        *,
        question: str,
        time_range: str,
        country: Optional[str],
        country_code: Optional[str] = None,
        as_of_date: date,
        model: str,
        status: str,
        duration_ms: int,
        error_message: Optional[str] = None,
        evidence_count: int = 0,
        node_count: int = 0,
        link_count: int = 0,
        response_text: Optional[str] = None,
        analysis_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        call_id = f"grc_{uuid.uuid4().hex[:16]}"
        question_hash = self._hash_text(question)
        response_hash = self._hash_text(response_text)

        result = self.neo4j_client.run_write(
            """
            // phase_d5_log_graphrag_call
            CREATE (c:GraphRagApiCall {
              call_id: $call_id,
              question: $question,
              question_hash: $question_hash,
              response_hash: $response_hash,
              time_range: $time_range,
              country: $country,
              country_code: $country_code,
              as_of_date: date($as_of_date),
              model: $model,
              status: $status,
              duration_ms: $duration_ms,
              error_message: $error_message,
              evidence_count: $evidence_count,
              node_count: $node_count,
              link_count: $link_count,
              analysis_run_id: $analysis_run_id,
              created_at: datetime()
            })
            """,
            {
                "call_id": call_id,
                "question": question,
                "question_hash": question_hash,
                "response_hash": response_hash,
                "time_range": time_range,
                "country": country,
                "country_code": country_code,
                "as_of_date": as_of_date.isoformat(),
                "model": model,
                "status": status,
                "duration_ms": int(duration_ms),
                "error_message": error_message,
                "evidence_count": int(evidence_count),
                "node_count": int(node_count),
                "link_count": int(link_count),
                "analysis_run_id": analysis_run_id,
            },
        )

        logger.info(
            "[GraphRagApiCallLogger] call_id=%s status=%s duration_ms=%s model=%s",
            call_id,
            status,
            duration_ms,
            model,
        )

        return {
            "call_id": call_id,
            "status": status,
            "write_result": result,
        }


class GraphRagMonitoringMetrics:
    """GraphRAG 운영/품질 지표를 집계한다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _since_iso(days: int) -> str:
        since = datetime.now(UTC) - timedelta(days=days)
        return since.isoformat()

    def quality_metrics(self, days: int = 7) -> Dict[str, Any]:
        row = self.neo4j_client.run_read(
            """
            // phase_d5_quality_metrics
            MATCH (c:GraphRagApiCall)
            WHERE c.created_at >= datetime($since_iso)
            WITH count(c) AS total_calls,
                 count(CASE WHEN c.status = 'success' THEN 1 END) AS success_calls,
                 count(CASE WHEN c.status = 'error' THEN 1 END) AS error_calls,
                 count(CASE WHEN c.status = 'success' AND coalesce(c.evidence_count, 0) > 0 THEN 1 END) AS cited_calls
            RETURN total_calls, success_calls, error_calls, cited_calls,
                   CASE WHEN success_calls = 0 THEN 0.0 ELSE toFloat(cited_calls) / success_calls * 100 END AS evidence_link_rate_pct,
                   CASE WHEN total_calls = 0 THEN 0.0 ELSE toFloat(error_calls) / total_calls * 100 END AS api_error_rate_pct
            """,
            {"since_iso": self._since_iso(days)},
        )
        return row[0] if row else {
            "total_calls": 0,
            "success_calls": 0,
            "error_calls": 0,
            "cited_calls": 0,
            "evidence_link_rate_pct": 0.0,
            "api_error_rate_pct": 0.0,
        }

    def reproducibility_metrics(self, days: int = 7) -> Dict[str, Any]:
        row = self.neo4j_client.run_read(
            """
            // phase_d5_reproducibility_metrics
            MATCH (c:GraphRagApiCall)
            WHERE c.created_at >= datetime($since_iso)
              AND c.status = 'success'
              AND c.question_hash IS NOT NULL
              AND c.response_hash IS NOT NULL
            WITH c.question_hash AS question_hash,
                 c.time_range AS time_range,
                 coalesce(c.country, '') AS country,
                 toString(c.as_of_date) AS as_of_date,
                 c.response_hash AS response_hash
            WITH question_hash, time_range, country, as_of_date, response_hash, count(*) AS cnt
            ORDER BY question_hash, time_range, country, as_of_date, cnt DESC
            WITH question_hash, time_range, country, as_of_date,
                 collect(cnt) AS counts,
                 reduce(total = 0, x IN collect(cnt) | total + x) AS total_runs
            WHERE total_runs >= 2
            WITH count(*) AS groups,
                 sum(total_runs) AS repeated_runs,
                 sum(head(counts)) AS stable_runs
            RETURN groups,
                   repeated_runs,
                   stable_runs,
                   CASE WHEN repeated_runs = 0 THEN 0.0 ELSE toFloat(stable_runs) / repeated_runs * 100 END AS reproducibility_pct
            """,
            {"since_iso": self._since_iso(days)},
        )
        return row[0] if row else {
            "groups": 0,
            "repeated_runs": 0,
            "stable_runs": 0,
            "reproducibility_pct": 0.0,
        }

    def consistency_metrics(self, days: int = 7) -> Dict[str, Any]:
        row = self.neo4j_client.run_read(
            """
            // phase_d5_consistency_metrics
            MATCH (c:GraphRagApiCall)
            WHERE c.created_at >= datetime($since_iso)
              AND c.status = 'success'
              AND c.question_hash IS NOT NULL
              AND c.response_hash IS NOT NULL
            WITH c.question_hash AS question_hash, c.response_hash AS response_hash
            WITH question_hash, response_hash, count(*) AS cnt
            ORDER BY question_hash, cnt DESC
            WITH question_hash,
                 collect(cnt) AS counts,
                 reduce(total = 0, x IN collect(cnt) | total + x) AS total_runs
            WHERE total_runs >= 2
            WITH count(*) AS repeated_questions,
                 sum(total_runs) AS repeated_runs,
                 sum(head(counts)) AS dominant_runs
            RETURN repeated_questions,
                   repeated_runs,
                   dominant_runs,
                   CASE WHEN repeated_runs = 0 THEN 0.0 ELSE toFloat(dominant_runs) / repeated_runs * 100 END AS consistency_pct
            """,
            {"since_iso": self._since_iso(days)},
        )
        return row[0] if row else {
            "repeated_questions": 0,
            "repeated_runs": 0,
            "dominant_runs": 0,
            "consistency_pct": 0.0,
        }

    def performance_metrics(self, days: int = 7) -> Dict[str, Any]:
        row = self.neo4j_client.run_read(
            """
            // phase_d5_performance_metrics
            MATCH (c:GraphRagApiCall)
            WHERE c.created_at >= datetime($since_iso)
            RETURN avg(c.duration_ms) AS avg_duration_ms,
                   percentileCont(c.duration_ms, 0.5) AS p50_duration_ms,
                   percentileCont(c.duration_ms, 0.95) AS p95_duration_ms,
                   max(c.duration_ms) AS max_duration_ms,
                   avg(c.node_count) AS avg_node_count,
                   percentileCont(c.node_count, 0.95) AS p95_node_count,
                   avg(c.link_count) AS avg_link_count,
                   percentileCont(c.link_count, 0.95) AS p95_link_count
            """,
            {"since_iso": self._since_iso(days)},
        )
        base = row[0] if row else {}
        return {
            "avg_duration_ms": _safe_float(base.get("avg_duration_ms")),
            "p50_duration_ms": _safe_float(base.get("p50_duration_ms")),
            "p95_duration_ms": _safe_float(base.get("p95_duration_ms")),
            "max_duration_ms": _safe_float(base.get("max_duration_ms")),
            "avg_node_count": _safe_float(base.get("avg_node_count")),
            "p95_node_count": _safe_float(base.get("p95_node_count")),
            "avg_link_count": _safe_float(base.get("avg_link_count")),
            "p95_link_count": _safe_float(base.get("p95_link_count")),
        }

    def scope_violation_metrics(
        self,
        days: int = 7,
        allowed_country_codes: Sequence[str] = ("US", "KR"),
    ) -> Dict[str, Any]:
        allowed_codes = sorted(
            {str(code or "").strip().upper() for code in allowed_country_codes if str(code or "").strip()}
        )
        row = self.neo4j_client.run_read(
            """
            // phase_d5_scope_violation_metrics
            MATCH (c:GraphRagApiCall)
            WHERE c.created_at >= datetime($since_iso)
            WITH c,
                 trim(toUpper(coalesce(toString(c.country_code), ""))) AS code
            WITH count(c) AS total_calls,
                 count(CASE WHEN code = "" THEN 1 END) AS missing_country_code_calls,
                 count(CASE WHEN code <> "" AND NOT code IN $allowed_country_codes THEN 1 END) AS out_of_scope_calls
            RETURN total_calls,
                   missing_country_code_calls,
                   out_of_scope_calls,
                   CASE WHEN total_calls = 0 THEN 0.0 ELSE toFloat(out_of_scope_calls) / total_calls * 100 END AS out_of_scope_rate_pct
            """,
            {
                "since_iso": self._since_iso(days),
                "allowed_country_codes": allowed_codes,
            },
        )
        base = row[0] if row else {}
        return {
            "allowed_country_codes": allowed_codes,
            "total_calls": _safe_int(base.get("total_calls")),
            "missing_country_code_calls": _safe_int(base.get("missing_country_code_calls")),
            "out_of_scope_calls": _safe_int(base.get("out_of_scope_calls")),
            "out_of_scope_rate_pct": _safe_float(base.get("out_of_scope_rate_pct")),
        }

    def persist_weekly_quality_snapshot(
        self,
        days: int = 7,
        snapshot_date: Optional[date] = None,
        allowed_country_codes: Sequence[str] = ("US", "KR"),
    ) -> Dict[str, Any]:
        summary = self.collect_summary(days=days, allowed_country_codes=allowed_country_codes)
        target_date = snapshot_date or date.today()
        scope_codes = summary.get("scope", {}).get("allowed_country_codes", [])

        write_result = self.neo4j_client.run_write(
            """
            // phase_d5_quality_snapshot
            MERGE (s:GraphRagQualitySnapshot {snapshot_date: date($snapshot_date), window_days: $window_days})
            SET s.scope_key = $scope_key,
                s.allowed_country_codes = $allowed_country_codes,
                s.total_calls = $total_calls,
                s.success_calls = $success_calls,
                s.error_calls = $error_calls,
                s.evidence_link_rate_pct = $evidence_link_rate_pct,
                s.api_error_rate_pct = $api_error_rate_pct,
                s.out_of_scope_calls = $out_of_scope_calls,
                s.out_of_scope_rate_pct = $out_of_scope_rate_pct,
                s.summary_json = $summary_json,
                s.updated_at = datetime()
            """,
            {
                "snapshot_date": target_date.isoformat(),
                "window_days": int(summary.get("window_days", days)),
                "scope_key": "|".join(scope_codes),
                "allowed_country_codes": scope_codes,
                "total_calls": int(summary.get("quality", {}).get("total_calls", 0)),
                "success_calls": int(summary.get("quality", {}).get("success_calls", 0)),
                "error_calls": int(summary.get("quality", {}).get("error_calls", 0)),
                "evidence_link_rate_pct": float(summary.get("quality", {}).get("evidence_link_rate_pct", 0.0)),
                "api_error_rate_pct": float(summary.get("quality", {}).get("api_error_rate_pct", 0.0)),
                "out_of_scope_calls": int(summary.get("scope", {}).get("out_of_scope_calls", 0)),
                "out_of_scope_rate_pct": float(summary.get("scope", {}).get("out_of_scope_rate_pct", 0.0)),
                "summary_json": json.dumps(summary, ensure_ascii=False),
            },
        )
        return {
            "snapshot_date": target_date.isoformat(),
            "window_days": int(summary.get("window_days", days)),
            "summary": summary,
            "write_result": write_result,
        }

    def collect_summary(
        self,
        days: int = 7,
        allowed_country_codes: Sequence[str] = ("US", "KR"),
    ) -> Dict[str, Any]:
        quality = self.quality_metrics(days=days)
        reproducibility = self.reproducibility_metrics(days=days)
        consistency = self.consistency_metrics(days=days)
        performance = self.performance_metrics(days=days)
        scope = self.scope_violation_metrics(days=days, allowed_country_codes=allowed_country_codes)

        return {
            "window_days": days,
            "quality": {
                "total_calls": _safe_int(quality.get("total_calls")),
                "success_calls": _safe_int(quality.get("success_calls")),
                "error_calls": _safe_int(quality.get("error_calls")),
                "evidence_link_rate_pct": _safe_float(quality.get("evidence_link_rate_pct")),
                "api_error_rate_pct": _safe_float(quality.get("api_error_rate_pct")),
            },
            "reproducibility": {
                "groups": _safe_int(reproducibility.get("groups")),
                "repeated_runs": _safe_int(reproducibility.get("repeated_runs")),
                "stable_runs": _safe_int(reproducibility.get("stable_runs")),
                "reproducibility_pct": _safe_float(reproducibility.get("reproducibility_pct")),
            },
            "consistency": {
                "repeated_questions": _safe_int(consistency.get("repeated_questions")),
                "repeated_runs": _safe_int(consistency.get("repeated_runs")),
                "dominant_runs": _safe_int(consistency.get("dominant_runs")),
                "consistency_pct": _safe_float(consistency.get("consistency_pct")),
            },
            "performance": performance,
            "scope": scope,
        }


@router.get("/metrics")
def graph_rag_metrics(days: int = Query(7, ge=1, le=90)):
    try:
        collector = GraphRagMonitoringMetrics()
        return {
            "status": "success",
            "data": collector.collect_summary(days=days),
        }
    except Exception as error:
        logger.error("[GraphRAGMetrics] failed: %s", error, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to collect GraphRAG metrics") from error
