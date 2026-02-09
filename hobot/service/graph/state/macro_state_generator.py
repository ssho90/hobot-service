"""
Phase D-4: MacroState / AnalysisRun persistence helpers.
"""

import json
import logging
import uuid
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class MacroStateGenerator:
    """MacroState(date) 노드를 생성하고 신호/테마 관계를 적재한다."""

    SIGNAL_FEATURE_ORDER = ["pct_change_1d", "delta_1d"]

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    def _collect_dominant_themes(
        self,
        as_of_date: date,
        window_days: int,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        start_date = as_of_date - timedelta(days=window_days)
        rows = self.neo4j_client.run_read(
            """
            MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)
            WHERE d.published_at IS NOT NULL
              AND d.published_at >= datetime($start_iso)
              AND d.published_at <= datetime($end_iso)
            RETURN t.theme_id AS theme_id,
                   coalesce(t.name, t.theme_id) AS theme_name,
                   count(*) AS doc_count
            ORDER BY doc_count DESC, theme_id
            LIMIT $top_k
            """,
            {
                "start_iso": f"{start_date.isoformat()}T00:00:00",
                "end_iso": f"{as_of_date.isoformat()}T23:59:59",
                "top_k": top_k,
            },
        )
        enriched: List[Dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            enriched.append(
                {
                    "theme_id": row.get("theme_id"),
                    "theme_name": row.get("theme_name"),
                    "doc_count": int(row.get("doc_count") or 0),
                    "rank": index,
                }
            )
        return enriched

    def _collect_top_signals(
        self,
        as_of_date: date,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        rows = self.neo4j_client.run_read(
            """
            MATCH (i:EconomicIndicator)
            CALL {
              WITH i
              MATCH (i)-[:HAS_OBSERVATION]->(:IndicatorObservation)-[:HAS_FEATURE]->(f:DerivedFeature)
              WHERE f.obs_date <= date($as_of_date)
                AND f.feature_name IN $feature_names
              RETURN f
              ORDER BY f.obs_date DESC,
                       CASE f.feature_name
                         WHEN "pct_change_1d" THEN 0
                         ELSE 1
                       END
              LIMIT 1
            }
            RETURN i.indicator_code AS indicator_code,
                   f.feature_name AS feature_name,
                   f.value AS value,
                   f.obs_date AS obs_date
            ORDER BY abs(f.value) DESC, i.indicator_code
            LIMIT $top_k
            """,
            {
                "as_of_date": as_of_date.isoformat(),
                "feature_names": self.SIGNAL_FEATURE_ORDER,
                "top_k": top_k,
            },
        )
        signals: List[Dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            value = float(row.get("value") or 0.0)
            signals.append(
                {
                    "indicator_code": row.get("indicator_code"),
                    "feature_name": row.get("feature_name"),
                    "value": value,
                    "score": round(abs(value), 6),
                    "obs_date": str(row.get("obs_date")),
                    "rank": index,
                }
            )
        return signals

    @staticmethod
    def _build_summary(
        as_of_date: date,
        themes: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
    ) -> str:
        theme_text = ", ".join(
            f"{item['theme_name']}({item['doc_count']})"
            for item in themes[:3]
            if item.get("theme_name")
        )
        signal_text = ", ".join(
            f"{item['indicator_code']}:{item['feature_name']}={item['value']:.4f}"
            for item in signals[:3]
            if item.get("indicator_code")
        )
        if not theme_text:
            theme_text = "dominant theme unavailable"
        if not signal_text:
            signal_text = "signal unavailable"
        return (
            f"{as_of_date.isoformat()} MacroState | "
            f"Dominant themes: {theme_text} | "
            f"Top signals: {signal_text}"
        )

    def generate_macro_state(
        self,
        as_of_date: Optional[date] = None,
        theme_window_days: int = 14,
        top_themes: int = 3,
        top_signals: int = 8,
    ) -> Dict[str, Any]:
        as_of_value = as_of_date or date.today()
        themes = self._collect_dominant_themes(
            as_of_date=as_of_value,
            window_days=theme_window_days,
            top_k=top_themes,
        )
        signals = self._collect_top_signals(
            as_of_date=as_of_value,
            top_k=top_signals,
        )
        summary = self._build_summary(
            as_of_date=as_of_value,
            themes=themes,
            signals=signals,
        )

        upsert_state_result = self.neo4j_client.run_write(
            """
            MERGE (ms:MacroState {date: date($as_of_date)})
            SET ms.summary = $summary,
                ms.theme_window_days = $theme_window_days,
                ms.top_theme_count = $top_theme_count,
                ms.top_signal_count = $top_signal_count,
                ms.updated_at = datetime()
            """,
            {
                "as_of_date": as_of_value.isoformat(),
                "summary": summary,
                "theme_window_days": theme_window_days,
                "top_theme_count": len(themes),
                "top_signal_count": len(signals),
            },
        )

        clear_theme_result = self.neo4j_client.run_write(
            """
            MATCH (ms:MacroState {date: date($as_of_date)})-[r:DOMINANT_THEME]->(:MacroTheme)
            DELETE r
            """,
            {"as_of_date": as_of_value.isoformat()},
        )

        clear_signal_result = self.neo4j_client.run_write(
            """
            MATCH (ms:MacroState {date: date($as_of_date)})-[r:HAS_SIGNAL]->(:DerivedFeature)
            DELETE r
            """,
            {"as_of_date": as_of_value.isoformat()},
        )

        theme_link_result = {"relationships_created": 0, "properties_set": 0}
        if themes:
            theme_link_result = self.neo4j_client.run_write(
                """
                MATCH (ms:MacroState {date: date($as_of_date)})
                UNWIND $themes AS theme
                MATCH (t:MacroTheme {theme_id: theme.theme_id})
                MERGE (ms)-[r:DOMINANT_THEME]->(t)
                SET r.rank = theme.rank,
                    r.doc_count = theme.doc_count,
                    r.window_days = $theme_window_days,
                    r.as_of = date($as_of_date),
                    r.updated_at = datetime()
                """,
                {
                    "as_of_date": as_of_value.isoformat(),
                    "theme_window_days": theme_window_days,
                    "themes": themes,
                },
            )

        signal_link_result = {"relationships_created": 0, "properties_set": 0}
        if signals:
            signal_link_result = self.neo4j_client.run_write(
                """
                MATCH (ms:MacroState {date: date($as_of_date)})
                UNWIND $signals AS signal
                MATCH (f:DerivedFeature {
                  indicator_code: signal.indicator_code,
                  feature_name: signal.feature_name,
                  obs_date: date(signal.obs_date)
                })
                MERGE (ms)-[r:HAS_SIGNAL]->(f)
                SET r.rank = signal.rank,
                    r.score = signal.score,
                    r.value = signal.value,
                    r.as_of = date($as_of_date),
                    r.updated_at = datetime()
                """,
                {
                    "as_of_date": as_of_value.isoformat(),
                    "signals": signals,
                },
            )

        logger.info(
            "[MacroStateGenerator] as_of=%s themes=%s signals=%s",
            as_of_value.isoformat(),
            len(themes),
            len(signals),
        )

        return {
            "as_of": as_of_value.isoformat(),
            "summary": summary,
            "themes": themes,
            "signals": signals,
            "write_result": {
                "upsert_state": upsert_state_result,
                "clear_theme_links": clear_theme_result,
                "clear_signal_links": clear_signal_result,
                "theme_links": theme_link_result,
                "signal_links": signal_link_result,
            },
        }


class AnalysisRunWriter:
    """GraphRAG 질의 결과를 AnalysisRun 노드로 저장한다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _split_node_ids(node_ids: Iterable[str]) -> Dict[str, List[str]]:
        buckets = {
            "event_ids": [],
            "indicator_codes": [],
            "theme_ids": [],
            "story_ids": [],
            "doc_ids": [],
        }
        seen = {key: set() for key in buckets}

        for node_id in node_ids:
            raw = str(node_id or "").strip()
            if ":" not in raw:
                continue
            prefix, value = raw.split(":", 1)
            if not value:
                continue
            if prefix == "event":
                bucket_key = "event_ids"
            elif prefix == "indicator":
                bucket_key = "indicator_codes"
            elif prefix == "theme":
                bucket_key = "theme_ids"
            elif prefix == "story":
                bucket_key = "story_ids"
            elif prefix == "document":
                bucket_key = "doc_ids"
            else:
                continue

            if value in seen[bucket_key]:
                continue
            seen[bucket_key].add(value)
            buckets[bucket_key].append(value)

        return buckets

    def _link_used_nodes(
        self,
        run_id: str,
        values: List[str],
        label: str,
        property_key: str,
    ) -> Dict[str, Any]:
        if not values:
            return {"relationships_created": 0, "properties_set": 0}
        return self.neo4j_client.run_write(
            f"""
            MATCH (ar:AnalysisRun {{run_id: $run_id}})
            UNWIND $values AS value
            MATCH (n:{label} {{{property_key}: value}})
            MERGE (ar)-[:USED_NODE]->(n)
            """,
            {
                "run_id": run_id,
                "values": values,
            },
        )

    def persist_run(
        self,
        question: str,
        response_text: str,
        model: str,
        as_of_date: date,
        citations: Optional[List[Any]] = None,
        impact_pathways: Optional[List[Any]] = None,
        duration_ms: Optional[int] = None,
        run_metadata: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        actual_run_id = run_id or f"ar_{uuid.uuid4().hex[:16]}"
        evidence_ids: List[str] = []
        node_ids: List[str] = []

        for citation in citations or []:
            evidence_id = getattr(citation, "evidence_id", None)
            if evidence_id is None and isinstance(citation, dict):
                evidence_id = citation.get("evidence_id")
            if evidence_id:
                evidence_ids.append(str(evidence_id))

            source_node_ids = getattr(citation, "node_ids", None)
            if source_node_ids is None and isinstance(citation, dict):
                source_node_ids = citation.get("node_ids")
            if isinstance(source_node_ids, list):
                node_ids.extend(str(node_id) for node_id in source_node_ids if node_id)

        for pathway in impact_pathways or []:
            event_id = getattr(pathway, "event_id", None)
            theme_id = getattr(pathway, "theme_id", None)
            indicator_code = getattr(pathway, "indicator_code", None)

            if event_id is None and isinstance(pathway, dict):
                event_id = pathway.get("event_id")
            if theme_id is None and isinstance(pathway, dict):
                theme_id = pathway.get("theme_id")
            if indicator_code is None and isinstance(pathway, dict):
                indicator_code = pathway.get("indicator_code")

            if event_id:
                node_ids.append(f"event:{event_id}")
            if theme_id:
                node_ids.append(f"theme:{theme_id}")
            if indicator_code:
                node_ids.append(f"indicator:{indicator_code}")

        split_nodes = self._split_node_ids(node_ids)
        unique_evidence_ids = sorted(set(evidence_ids))

        create_result = self.neo4j_client.run_write(
            """
            CREATE (ar:AnalysisRun {
              run_id: $run_id,
              question: $question,
              response: $response,
              model: $model,
              duration_ms: $duration_ms,
              as_of_date: date($as_of_date),
              metadata_json: $metadata_json,
              created_at: datetime()
            })
            """,
            {
                "run_id": actual_run_id,
                "question": question,
                "response": response_text,
                "model": model,
                "duration_ms": int(duration_ms or 0),
                "as_of_date": as_of_date.isoformat(),
                "metadata_json": json.dumps(run_metadata or {}, ensure_ascii=False),
            },
        )

        evidence_result = {"relationships_created": 0, "properties_set": 0}
        if unique_evidence_ids:
            evidence_result = self.neo4j_client.run_write(
                """
                MATCH (ar:AnalysisRun {run_id: $run_id})
                UNWIND $evidence_ids AS evidence_id
                MATCH (e:Evidence {evidence_id: evidence_id})
                MERGE (ar)-[:USED_EVIDENCE]->(e)
                """,
                {
                    "run_id": actual_run_id,
                    "evidence_ids": unique_evidence_ids,
                },
            )

        node_results = {
            "events": self._link_used_nodes(
                run_id=actual_run_id,
                values=split_nodes["event_ids"],
                label="Event",
                property_key="event_id",
            ),
            "indicators": self._link_used_nodes(
                run_id=actual_run_id,
                values=split_nodes["indicator_codes"],
                label="EconomicIndicator",
                property_key="indicator_code",
            ),
            "themes": self._link_used_nodes(
                run_id=actual_run_id,
                values=split_nodes["theme_ids"],
                label="MacroTheme",
                property_key="theme_id",
            ),
            "stories": self._link_used_nodes(
                run_id=actual_run_id,
                values=split_nodes["story_ids"],
                label="Story",
                property_key="story_id",
            ),
            "documents": self._link_used_nodes(
                run_id=actual_run_id,
                values=split_nodes["doc_ids"],
                label="Document",
                property_key="doc_id",
            ),
        }

        logger.info(
            "[AnalysisRunWriter] run_id=%s evidences=%s nodes=%s",
            actual_run_id,
            len(unique_evidence_ids),
            sum(len(values) for values in split_nodes.values()),
        )

        return {
            "run_id": actual_run_id,
            "as_of": as_of_date.isoformat(),
            "counts": {
                "evidences": len(unique_evidence_ids),
                "events": len(split_nodes["event_ids"]),
                "indicators": len(split_nodes["indicator_codes"]),
                "themes": len(split_nodes["theme_ids"]),
                "stories": len(split_nodes["story_ids"]),
                "documents": len(split_nodes["doc_ids"]),
            },
            "write_result": {
                "create_run": create_result,
                "evidence_links": evidence_result,
                "node_links": node_results,
            },
        }


def generate_macro_state(as_of_date: Optional[date] = None) -> Dict[str, Any]:
    generator = MacroStateGenerator()
    return generator.generate_macro_state(as_of_date=as_of_date)

