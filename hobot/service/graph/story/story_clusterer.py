"""
Phase C-4: Rule-based Story 클러스터링.
"""

import hashlib
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class StoryClusterer:
    """테마 + 시간 버킷 기준으로 Story 노드를 생성한다."""

    METHOD_NAME = "theme_time_bucket"

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _normalize_date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.fromisoformat(str(value)).date()

    def _fetch_documents(
        self,
        window_days: int,
        as_of_date: Optional[date],
    ) -> List[Dict[str, Any]]:
        end_date = as_of_date or date.today()
        start_date = end_date - timedelta(days=window_days)

        query = """
        MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)
        WHERE d.published_at IS NOT NULL
          AND d.published_at >= datetime($start_iso)
          AND d.published_at <= datetime($end_iso)
        RETURN d.doc_id AS doc_id,
               d.title AS title,
               d.published_at AS published_at,
               t.theme_id AS theme_id
        ORDER BY d.published_at DESC
        """

        return self.neo4j_client.run_read(
            query,
            {
                "start_iso": f"{start_date.isoformat()}T00:00:00",
                "end_iso": f"{end_date.isoformat()}T23:59:59",
            },
        )

    def _build_clusters(
        self,
        rows: List[Dict[str, Any]],
        bucket_days: int,
        min_docs_per_story: int,
    ) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            published_date = self._normalize_date(row["published_at"])
            bucket_start = published_date - timedelta(days=(published_date.toordinal() % bucket_days))
            bucket_key = f"{row['theme_id']}:{bucket_start.isoformat()}"

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    "theme_id": row["theme_id"],
                    "bucket_start": bucket_start,
                    "titles": [],
                    "doc_ids": [],
                }
            buckets[bucket_key]["titles"].append(row.get("title") or "")
            buckets[bucket_key]["doc_ids"].append(row["doc_id"])

        stories: List[Dict[str, Any]] = []
        for bucket in buckets.values():
            if len(bucket["doc_ids"]) < min_docs_per_story:
                continue

            fingerprint = f"{bucket['theme_id']}:{bucket['bucket_start'].isoformat()}"
            story_id = f"story_{hashlib.sha1(fingerprint.encode()).hexdigest()[:16]}"
            title_seed = next((title for title in bucket["titles"] if title), f"{bucket['theme_id']} narrative")
            story_title = f"{bucket['theme_id'].upper()} | {title_seed[:64]}"

            stories.append(
                {
                    "story_id": story_id,
                    "title": story_title,
                    "theme_id": bucket["theme_id"],
                    "story_date": bucket["bucket_start"].isoformat(),
                    "doc_ids": sorted(set(bucket["doc_ids"])),
                }
            )

        return stories

    def cluster_recent_documents(
        self,
        window_days: int = 7,
        bucket_days: int = 3,
        min_docs_per_story: int = 3,
        min_story_count: int = 10,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        effective_window_days = window_days
        effective_bucket_days = bucket_days
        rows = self._fetch_documents(window_days=effective_window_days, as_of_date=as_of_date)
        stories = self._build_clusters(rows=rows, bucket_days=effective_bucket_days, min_docs_per_story=min_docs_per_story)

        if len(stories) < min_story_count:
            adaptive_configs = [
                (max(window_days, 14), 2),
                (max(window_days, 21), 1),
            ]
            for candidate_window, candidate_bucket in adaptive_configs:
                candidate_rows = self._fetch_documents(window_days=candidate_window, as_of_date=as_of_date)
                candidate_stories = self._build_clusters(
                    rows=candidate_rows,
                    bucket_days=candidate_bucket,
                    min_docs_per_story=min_docs_per_story,
                )
                if len(candidate_stories) > len(stories):
                    effective_window_days = candidate_window
                    effective_bucket_days = candidate_bucket
                    rows = candidate_rows
                    stories = candidate_stories
                if len(stories) >= min_story_count:
                    break

        if not stories:
            return {
                "window_days": effective_window_days,
                "bucket_days": effective_bucket_days,
                "source_documents": len(rows),
                "stories_created": 0,
            }

        clear_query = """
        MATCH (s:Story)
        WHERE s.method = $method
          AND s.window_days = $window_days
        DETACH DELETE s
        """
        create_query = """
        UNWIND $stories AS story
        MERGE (s:Story {story_id: story.story_id})
        SET s.title = story.title,
            s.method = $method,
            s.window_days = $window_days,
            s.story_date = date(story.story_date),
            s.created_at = datetime(),
            s.updated_at = datetime()
        WITH s, story
        MATCH (t:MacroTheme {theme_id: story.theme_id})
        MERGE (s)-[:ABOUT_THEME]->(t)
        WITH s, story
        UNWIND story.doc_ids AS doc_id
        MATCH (d:Document {doc_id: doc_id})
        MERGE (s)-[:CONTAINS]->(d)
        """

        self.neo4j_client.run_write(
            clear_query,
            {"method": self.METHOD_NAME, "window_days": effective_window_days},
        )
        create_result = self.neo4j_client.run_write(
            create_query,
            {
                "stories": stories,
                "method": self.METHOD_NAME,
                "window_days": effective_window_days,
            },
        )

        logger.info(
            "[StoryCluster] stories=%s docs=%s window=%s bucket=%s",
            len(stories),
            len(rows),
            effective_window_days,
            effective_bucket_days,
        )

        return {
            "window_days": effective_window_days,
            "bucket_days": effective_bucket_days,
            "source_documents": len(rows),
            "stories_created": len(stories),
            "create_result": create_result,
            "sample": stories[:5],
        }
