"""
Macro Knowledge Graph (MKG) - News Loader
Phase A-8: MySQL economic_news → Neo4j Document upsert + 기본 링크
"""
import logging
import hashlib
import time
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
from .neo4j_client import get_neo4j_client
from .normalization.category_mapping import get_related_themes, normalize_category
from .normalization.country_mapping import normalize_country
from .nel.nel_pipeline import get_nel_pipeline

logger = logging.getLogger(__name__)


class NewsLoader:
    """MySQL economic_news → Neo4j Document 동기화 및 기본 링크"""
    
    # Category → MacroTheme 매핑
    THEME_MAPPING = {
        'Interest Rate': 'rates',
        'Fed Interest Rate': 'rates',
        'Treasury Bond': 'rates',
        'Government Bond': 'rates',
        'Inflation Rate': 'inflation',
        'CPI': 'inflation',
        'PPI': 'inflation',
        'Consumer Price': 'inflation',
        'GDP': 'growth',
        'PMI': 'growth',
        'Industrial Production': 'growth',
        'Economic Growth': 'growth',
        'Unemployment': 'labor',
        'Employment': 'labor',
        'Nonfarm Payrolls': 'labor',
        'Jobs': 'labor',
        'Fed Balance Sheet': 'liquidity',
        'Money Supply': 'liquidity',
        'Liquidity': 'liquidity',
        'Credit Spreads': 'risk',
        'Risk': 'risk',
        'VIX': 'risk',
        'Financial Stress': 'risk',
    }
    
    # Entity Alias 사전 (간단한 substring 매칭용)
    ENTITY_ALIASES = {
        'Fed': 'ORG_FED',
        'Federal Reserve': 'ORG_FED',
        'FOMC': 'ORG_FED',
        '연준': 'ORG_FED',
        'ECB': 'ORG_ECB',
        'BOJ': 'ORG_BOJ',
        'Powell': 'PERSON_POWELL',
        '파월': 'PERSON_POWELL',
        'Yellen': 'PERSON_YELLEN',
        '옐런': 'PERSON_YELLEN',
        'Treasury': 'ORG_TREASURY',
    }

    THEME_DEFAULT_POLARITY = {
        "rates": "negative",
        "inflation": "negative",
        "growth": "positive",
        "labor": "positive",
        "liquidity": "positive",
        "risk": "negative",
    }

    EVIDENCE_CONFIDENCE_SCORE = {
        "high": 0.85,
        "medium": 0.60,
        "low": 0.35,
    }
    
    def __init__(self):
        self.neo4j_client = get_neo4j_client()
        self.nel_pipeline = get_nel_pipeline()
    
    def _get_mysql_connection(self):
        """MySQL 연결 반환"""
        from service.database.db import get_db_connection
        return get_db_connection()
    
    def _generate_doc_id(self, source: str, news_id: Any) -> str:
        """Document ID 생성 (deterministic)"""
        return f"{source}:{news_id}"
    
    def fetch_news_from_mysql(
        self,
        limit: int = 100,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """MySQL economic_news에서 뉴스 조회"""
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        with self._get_mysql_connection() as conn:
            cursor = conn.cursor()
            
            query = """
                SELECT id, title, link, country, category, description,
                       published_at, source, created_at,
                       title_ko, description_ko, country_ko, category_ko
                FROM economic_news
                WHERE DATE(published_at) >= %s AND DATE(published_at) <= %s
                ORDER BY published_at DESC
                LIMIT %s
            """
            
            cursor.execute(query, (start_date, end_date, limit))
            results = cursor.fetchall()
            
            news_list = []
            for row in results:
                doc_id = self._generate_doc_id("te", row['id'])  # te = TradingEconomics
                
                # 텍스트 생성 (title + description 조합)
                text = f"{row.get('title') or ''} {row.get('description') or ''}".strip()
                
                news_list.append({
                    'doc_id': doc_id,
                    'source': row.get('source') or 'TradingEconomics',
                    'country': row.get('country'),
                    'country_code': normalize_country(row.get('country') or ""),
                    'category': row.get('category'),
                    'category_id': normalize_category(row.get('category') or ""),
                    'title': row.get('title'),
                    'title_ko': row.get('title_ko'),
                    'description': row.get('description'),
                    'description_ko': row.get('description_ko'),
                    'text': text,
                    'link': row.get('link'),
                    'published_at': row['published_at'].isoformat() if row.get('published_at') else None,
                })
            
            logger.info(f"[NewsLoader] Fetched {len(news_list)} news from MySQL")
            return news_list
    
    def upsert_documents(self, news_list: List[Dict[str, Any]], batch_size: int = 100) -> Dict[str, int]:
        """Neo4j에 Document 노드 MERGE"""
        if not news_list:
            return {"nodes_created": 0}
        
        total_created = 0
        total_props_set = 0
        total_docs = len(news_list)
        start_time = time.monotonic()
        logger.info(
            "[NewsLoader][DocumentUpsert] start total_docs=%s batch_size=%s",
            total_docs,
            batch_size,
        )
        
        for i in range(0, len(news_list), batch_size):
            batch = news_list[i:i+batch_size]
            
            query = """
            UNWIND $news AS n
            MERGE (d:Document {doc_id: n.doc_id})
            SET d.source = n.source,
                d.country = n.country,
                d.country_code = n.country_code,
                d.category = n.category,
                d.category_id = n.category_id,
                d.title = n.title,
                d.title_ko = n.title_ko,
                d.description = n.description,
                d.description_ko = n.description_ko,
                d.text = n.text,
                d.link = n.link,
                d.published_at = CASE WHEN n.published_at IS NOT NULL 
                                      THEN datetime(n.published_at) 
                                      ELSE null END,
                d.updated_at = datetime()
            """
            
            result = self.neo4j_client.run_write(query, {"news": batch})
            total_created += result.get("nodes_created", 0)
            total_props_set += result.get("properties_set", 0)
            
            logger.info(f"[NewsLoader] Document batch {i//batch_size + 1}: {result}")
            processed_docs = min(i + len(batch), total_docs)
            self._log_progress(
                stage="DocumentUpsert",
                processed=processed_docs,
                total=total_docs,
                started_at=start_time,
                extra=f"nodes_created={total_created} properties_set={total_props_set}",
            )
        
        return {"nodes_created": total_created, "properties_set": total_props_set}
    
    def link_to_themes(self, news_list: List[Dict[str, Any]]) -> Dict[str, int]:
        """Category 기반 MacroTheme 연결 (ABOUT_THEME)"""
        links_created = 0
        total_docs = len(news_list)
        start_time = time.monotonic()
        logger.info("[NewsLoader][ThemeLink] start total_docs=%s", total_docs)
        
        for index, news in enumerate(news_list, start=1):
            category = news.get('category')
            if not category:
                if index % 200 == 0 or index == total_docs:
                    self._log_progress(
                        stage="ThemeLink",
                        processed=index,
                        total=total_docs,
                        started_at=start_time,
                        extra=f"links_created={links_created}",
                    )
                continue
            
            # 가장 적합한 theme 찾기
            theme_id = None
            for key, tid in self.THEME_MAPPING.items():
                if key.lower() in category.lower():
                    theme_id = tid
                    break
            
            if theme_id:
                query = """
                MATCH (d:Document {doc_id: $doc_id})
                MATCH (t:MacroTheme {theme_id: $theme_id})
                MERGE (d)-[r:ABOUT_THEME]->(t)
                RETURN count(r) AS created
                """
                result = self.neo4j_client.run_write(query, {
                    "doc_id": news['doc_id'],
                    "theme_id": theme_id
                })
                links_created += result.get("relationships_created", 0)
            if index % 200 == 0 or index == total_docs:
                self._log_progress(
                    stage="ThemeLink",
                    processed=index,
                    total=total_docs,
                    started_at=start_time,
                    extra=f"links_created={links_created}",
                )
        
        logger.info(f"[NewsLoader] Theme links created: {links_created}")
        return {"links_created": links_created}
    
    def link_to_entities(self, news_list: List[Dict[str, Any]]) -> Dict[str, int]:
        """Alias substring 매칭으로 Entity 연결 (MENTIONS)"""
        links_created = 0
        total_docs = len(news_list)
        start_time = time.monotonic()
        logger.info("[NewsLoader][EntityLink] start total_docs=%s", total_docs)
        
        for index, news in enumerate(news_list, start=1):
            text = news.get('text', '') or ''
            description = news.get('description', '') or ''
            combined_text = f"{text} {description}"
            
            mentioned_entities = set()
            for alias, entity_id in self.ENTITY_ALIASES.items():
                if alias in combined_text:
                    mentioned_entities.add(entity_id)
            
            for entity_id in mentioned_entities:
                query = """
                MATCH (d:Document {doc_id: $doc_id})
                MATCH (e:Entity {canonical_id: $entity_id})
                MERGE (d)-[r:MENTIONS]->(e)
                RETURN count(r) AS created
                """
                result = self.neo4j_client.run_write(query, {
                    "doc_id": news['doc_id'],
                    "entity_id": entity_id
                })
                links_created += result.get("relationships_created", 0)
            if index % 200 == 0 or index == total_docs:
                self._log_progress(
                    stage="EntityLink",
                    processed=index,
                    total=total_docs,
                    started_at=start_time,
                    extra=f"links_created={links_created}",
                )
        
        logger.info(f"[NewsLoader] Entity links created: {links_created}")
        return {"links_created": links_created}

    def _to_iso_datetime(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(microsecond=0).isoformat()
        if isinstance(value, date):
            return f"{value.isoformat()}T00:00:00"
        text = str(value).strip()
        if not text:
            return None
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        if "T" not in text:
            text = f"{text}T00:00:00"
        return text

    def _confidence_score(self, raw_confidence: Any, default: float = 0.60) -> float:
        if raw_confidence is None:
            return default
        key = str(raw_confidence).strip().lower()
        return float(self.EVIDENCE_CONFIDENCE_SCORE.get(key, default))

    def _resolve_theme_id(self, raw_value: str) -> Optional[str]:
        if not raw_value:
            return None
        normalized = raw_value.strip().lower()
        if normalized in self.THEME_DEFAULT_POLARITY:
            return normalized
        mapped = normalize_category(raw_value)
        if mapped:
            return mapped
        related = get_related_themes(raw_value)
        return related[0] if related else None

    def _merge_write_result(self, total: Dict[str, int], result: Dict[str, Any]):
        for key in (
            "nodes_created",
            "nodes_deleted",
            "relationships_created",
            "relationships_deleted",
            "properties_set",
            "constraints_added",
            "indexes_added",
        ):
            total[key] = total.get(key, 0) + int(result.get(key, 0) or 0)

    def _format_duration(self, seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        minutes, remain_seconds = divmod(total_seconds, 60)
        hours, remain_minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{remain_minutes:02d}:{remain_seconds:02d}"
        return f"{remain_minutes:02d}:{remain_seconds:02d}"

    def _log_progress(
        self,
        stage: str,
        processed: int,
        total: int,
        started_at: float,
        success: Optional[int] = None,
        failed: Optional[int] = None,
        skipped: Optional[int] = None,
        extra: Optional[str] = None,
    ):
        if total <= 0:
            return
        elapsed = max(time.monotonic() - started_at, 0.001)
        progress_pct = (processed / total) * 100
        speed = processed / elapsed
        eta_seconds = (total - processed) / speed if speed > 0 else 0.0

        status_parts = []
        if success is not None:
            status_parts.append(f"success={success}")
        if failed is not None:
            status_parts.append(f"failed={failed}")
        if skipped is not None:
            status_parts.append(f"skipped={skipped}")
        status_suffix = f", {' '.join(status_parts)}" if status_parts else ""
        extra_suffix = f", {extra}" if extra else ""

        logger.info(
            "[NewsLoader][%s] %s/%s (%.1f%%), elapsed=%s, eta=%s%s%s",
            stage,
            processed,
            total,
            progress_pct,
            self._format_duration(elapsed),
            self._format_duration(eta_seconds),
            status_suffix,
            extra_suffix,
        )

    def _mark_extraction_failure(self, doc_id: str, error_message: str):
        query = """
        MATCH (d:Document {doc_id: $doc_id})
        SET d.extraction_status = "failed",
            d.extraction_last_error = $error_message,
            d.extraction_updated_at = datetime()
        """
        self.neo4j_client.run_write(
            query,
            {
                "doc_id": doc_id,
                "error_message": error_message[:500],
            },
        )

    def fetch_extraction_candidates(
        self,
        limit: int = 200,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        retry_failed_after_minutes: int = 180,
    ) -> List[Dict[str, Any]]:
        """
        Neo4j Document 중 추출 대상(미처리 + 실패 재시도 가능) 후보를 조회한다.
        """
        params = {
            "limit": limit,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
            "retry_failed_after_minutes": max(0, int(retry_failed_after_minutes)),
        }
        query = """
        MATCH (d:Document)
        WHERE trim(coalesce(d.text, d.description, d.title, "")) <> ""
          AND (
            d.extraction_status IS NULL
            OR d.extraction_status = "pending"
            OR (
              d.extraction_status = "failed"
              AND (
                d.extraction_updated_at IS NULL
                OR d.extraction_updated_at <= datetime() - duration({minutes: $retry_failed_after_minutes})
              )
            )
          )
          AND (
            $start_date IS NULL
            OR (
              d.published_at IS NOT NULL
              AND date(d.published_at) >= date($start_date)
            )
          )
          AND (
            $end_date IS NULL
            OR (
              d.published_at IS NOT NULL
              AND date(d.published_at) <= date($end_date)
            )
          )
        RETURN d.doc_id AS doc_id,
               d.source AS source,
               d.country AS country,
               d.country_code AS country_code,
               d.category AS category,
               d.title AS title,
               d.description AS description,
               d.text AS text,
               toString(d.published_at) AS published_at
        ORDER BY coalesce(d.published_at, d.updated_at) DESC
        LIMIT $limit
        """
        rows = self.neo4j_client.run_read(query, params)
        return [dict(row) for row in rows]

    def sync_news_with_extraction_backlog(
        self,
        sync_limit: int = 2000,
        sync_days: int = 30,
        extraction_batch_size: int = 200,
        max_extraction_batches: int = 10,
        retry_failed_after_minutes: int = 180,
        extraction_progress_log_interval: int = 25,
    ) -> Dict[str, Any]:
        """
        1) MySQL -> Neo4j Document/기본 링크 동기화
        2) Neo4j의 미추출/재시도 대상 문서를 배치로 추출 적재
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=sync_days)
        logger.info(
            "[NewsLoader][Backlog] start sync_days=%s sync_limit=%s extraction_batch_size=%s max_batches=%s retry_failed_after_minutes=%s",
            sync_days,
            sync_limit,
            extraction_batch_size,
            max_extraction_batches,
            retry_failed_after_minutes,
        )

        sync_result = self.sync_news(
            limit=sync_limit,
            start_date=start_date,
            end_date=end_date,
            run_extraction=False,
        )

        extraction_summary: Dict[str, Any] = {
            "status": "success",
            "batches": 0,
            "processed_docs": 0,
            "success_docs": 0,
            "failed_docs": 0,
            "skipped_docs": 0,
            "failed_doc_ids": [],
            "write_result": {
                "nodes_created": 0,
                "nodes_deleted": 0,
                "relationships_created": 0,
                "relationships_deleted": 0,
                "properties_set": 0,
                "constraints_added": 0,
                "indexes_added": 0,
            },
            "stop_reason": "no_candidates",
        }

        batch_summaries: List[Dict[str, Any]] = []
        seen_failed_doc_ids = set()

        for batch_idx in range(max(1, max_extraction_batches)):
            candidates = self.fetch_extraction_candidates(
                limit=max(1, extraction_batch_size),
                start_date=start_date,
                end_date=end_date,
                retry_failed_after_minutes=retry_failed_after_minutes,
            )
            if not candidates:
                extraction_summary["stop_reason"] = "no_candidates"
                break

            extract_result = self.extract_and_persist(
                candidates,
                progress_log_interval=extraction_progress_log_interval,
            )

            extraction_summary["batches"] += 1
            extraction_summary["processed_docs"] += int(extract_result.get("processed_docs", 0) or 0)
            extraction_summary["success_docs"] += int(extract_result.get("success_docs", 0) or 0)
            extraction_summary["failed_docs"] += int(extract_result.get("failed_docs", 0) or 0)
            extraction_summary["skipped_docs"] += int(extract_result.get("skipped_docs", 0) or 0)

            batch_failed_doc_ids = extract_result.get("failed_doc_ids", []) or []
            for doc_id in batch_failed_doc_ids:
                if doc_id in seen_failed_doc_ids:
                    continue
                seen_failed_doc_ids.add(doc_id)
                extraction_summary["failed_doc_ids"].append(doc_id)

            write_result = extract_result.get("write_result") or {}
            for key in extraction_summary["write_result"].keys():
                extraction_summary["write_result"][key] += int(write_result.get(key, 0) or 0)

            batch_summaries.append(
                {
                    "batch_index": batch_idx + 1,
                    "requested_docs": len(candidates),
                    "status": extract_result.get("status"),
                    "processed_docs": int(extract_result.get("processed_docs", 0) or 0),
                    "success_docs": int(extract_result.get("success_docs", 0) or 0),
                    "failed_docs": int(extract_result.get("failed_docs", 0) or 0),
                }
            )

            status = extract_result.get("status")
            if status == "skipped":
                extraction_summary["status"] = "skipped"
                extraction_summary["stop_reason"] = str(extract_result.get("reason") or "skipped")
                break
            if status == "no_data":
                extraction_summary["stop_reason"] = "no_data"
                break

        extraction_summary["batch_summaries"] = batch_summaries

        logger.info(
            "[NewsLoader][Backlog] done synced_docs=%s batches=%s processed=%s success=%s failed=%s skipped=%s stop_reason=%s",
            sync_result.get("documents"),
            extraction_summary["batches"],
            extraction_summary["processed_docs"],
            extraction_summary["success_docs"],
            extraction_summary["failed_docs"],
            extraction_summary["skipped_docs"],
            extraction_summary["stop_reason"],
        )
        return {
            "status": "success",
            "sync_result": sync_result,
            "extraction": extraction_summary,
        }

    def extract_and_persist(
        self,
        news_list: List[Dict[str, Any]],
        max_docs: Optional[int] = None,
        default_horizon_days: int = 7,
        progress_log_interval: int = 25,
    ) -> Dict[str, Any]:
        """
        Phase B 정식 적재 경로.
        Document에서 LLM 추출을 수행하고 Event/Fact/Claim/Evidence/AFFECTS를 Neo4j에 저장한다.
        """
        if not news_list:
            return {
                "status": "no_data",
                "processed_docs": 0,
                "success_docs": 0,
                "failed_docs": 0,
            }

        from .news_extractor import get_news_extractor

        extractor = get_news_extractor()
        if not getattr(extractor, "client", None):
            logger.warning("[NewsLoader] Extraction skipped: Gemini client is not initialized.")
            return {
                "status": "skipped",
                "reason": "missing_gemini_api_key",
                "processed_docs": 0,
                "success_docs": 0,
                "failed_docs": 0,
            }

        target_news = news_list[:max_docs] if max_docs else news_list
        total_docs = len(target_news)
        step_interval = max(1, progress_log_interval)
        extraction_started_at = time.monotonic()
        logger.info(
            "[NewsLoader][Extraction] start total_docs=%s horizon_days=%s log_interval=%s",
            total_docs,
            default_horizon_days,
            step_interval,
        )
        total_write = {
            "nodes_created": 0,
            "nodes_deleted": 0,
            "relationships_created": 0,
            "relationships_deleted": 0,
            "properties_set": 0,
            "constraints_added": 0,
            "indexes_added": 0,
        }
        success_docs = 0
        failed_docs = 0
        skipped_docs = 0
        failed_doc_ids: List[str] = []

        for index, news in enumerate(target_news, start=1):
            doc_id = news["doc_id"]
            title = news.get("title") or ""
            article_text = news.get("text") or news.get("description") or title

            if not article_text:
                skipped_docs += 1
                if index % step_interval == 0 or index == total_docs:
                    self._log_progress(
                        stage="Extraction",
                        processed=index,
                        total=total_docs,
                        started_at=extraction_started_at,
                        success=success_docs,
                        failed=failed_docs,
                        skipped=skipped_docs,
                        extra=(
                            f"nodes_created={total_write['nodes_created']} "
                            f"rels_created={total_write['relationships_created']}"
                        ),
                    )
                continue

            try:
                extraction = extractor.extract(
                    doc_id=doc_id,
                    article_text=article_text,
                    title=title,
                )
            except Exception as exc:
                failed_docs += 1
                failed_doc_ids.append(doc_id)
                logger.warning("[NewsLoader] Extraction failed for %s: %s", doc_id, exc)
                self._mark_extraction_failure(doc_id, str(exc))
                if index % step_interval == 0 or index == total_docs:
                    self._log_progress(
                        stage="Extraction",
                        processed=index,
                        total=total_docs,
                        started_at=extraction_started_at,
                        success=success_docs,
                        failed=failed_docs,
                        skipped=skipped_docs,
                        extra=(
                            f"nodes_created={total_write['nodes_created']} "
                            f"rels_created={total_write['relationships_created']}"
                        ),
                    )
                continue

            event_rows: List[Dict[str, Any]] = []
            fact_rows: List[Dict[str, Any]] = []
            claim_rows: List[Dict[str, Any]] = []
            evidence_rows: Dict[str, Dict[str, Any]] = {}
            event_theme_rows: List[Dict[str, Any]] = []
            event_indicator_rows: List[Dict[str, Any]] = []
            theme_affects_rows: List[Dict[str, Any]] = []
            claim_about_rows: List[Dict[str, Any]] = []
            fact_evidence_rows: List[Dict[str, str]] = []
            claim_evidence_rows: List[Dict[str, str]] = []
            causes_rows: List[Dict[str, Any]] = []
            entity_rows: Dict[str, Dict[str, Any]] = {}
            entity_alias_rows: Dict[str, Dict[str, Any]] = {}

            event_name_to_id: Dict[str, str] = {}
            default_event_time = self._to_iso_datetime(news.get("published_at")) or self._to_iso_datetime(datetime.utcnow())
            document_country = (str(news.get("country") or "").strip() or None)
            document_country_code = (
                str(news.get("country_code") or "").strip().upper()
                or normalize_country(document_country or "")
            )

            def ensure_event(
                event_name: str,
                event_type: str = "other",
                summary: Optional[str] = None,
                event_time: Optional[str] = None,
                impact_level: str = "medium",
                event_country: Optional[str] = None,
                event_country_code: Optional[str] = None,
            ) -> str:
                normalized_name = event_name.strip()
                cache_key = normalized_name.lower()
                if cache_key in event_name_to_id:
                    return event_name_to_id[cache_key]
                resolved_country = (event_country or document_country or "").strip() or None
                resolved_country_code = (
                    (event_country_code or "").strip().upper()
                    or normalize_country(resolved_country or "")
                    or document_country_code
                )
                event_id = self._build_deterministic_id(
                    "EVT", f"{doc_id}:{normalized_name}"
                )
                event_name_to_id[cache_key] = event_id
                event_rows.append(
                    {
                        "event_id": event_id,
                        "event_name": normalized_name,
                        "event_type": event_type or "other",
                        "summary": (summary or normalized_name)[:300],
                        "event_time": event_time or default_event_time,
                        "country": resolved_country,
                        "country_code": resolved_country_code,
                        "impact_level": impact_level or "medium",
                    }
                )
                return event_id

            for event in extraction.events:
                event_time = self._to_iso_datetime(event.event_date) or default_event_time
                event_id = ensure_event(
                    event_name=event.event_name,
                    event_type=event.event_type,
                    summary=event.description or event.event_name,
                    event_time=event_time,
                    impact_level=event.impact_level,
                )

                for raw_theme in event.related_themes:
                    theme_id = self._resolve_theme_id(raw_theme)
                    if theme_id:
                        event_theme_rows.append({"event_id": event_id, "theme_id": theme_id})

                for raw_indicator in event.related_indicators:
                    indicator_code = (raw_indicator or "").strip().upper()
                    if not indicator_code:
                        continue
                    event_indicator_rows.append(
                        {
                            "event_id": event_id,
                            "indicator_code": indicator_code,
                            "polarity": "mixed",
                            "weight": 0.55,
                            "confidence": 0.55,
                            "horizon_days": default_horizon_days,
                            "source": "llm_extraction_event_indicator",
                        }
                    )

            def add_evidence(evidence_obj: Any, default_text: str) -> Optional[str]:
                if not evidence_obj:
                    return None
                evidence_text = (getattr(evidence_obj, "evidence_text", None) or default_text or "").strip()
                if not evidence_text:
                    return None
                evidence_id = getattr(evidence_obj, "evidence_id", None)
                if not evidence_id:
                    evidence_id = evidence_obj.generate_evidence_id(doc_id)
                evidence_rows[evidence_id] = {
                    "evidence_id": evidence_id,
                    "evidence_text": evidence_text[:1000],
                    "source_sentence": (getattr(evidence_obj, "source_sentence", None) or evidence_text)[:1000],
                    "language": (getattr(evidence_obj, "language", None) or "en"),
                    "confidence": self._confidence_score(getattr(evidence_obj, "confidence", None)),
                }
                return evidence_id

            for fact in extraction.facts:
                fact_id = self._build_deterministic_id("FACT", f"{doc_id}:{fact.fact_text}")
                fact_rows.append(
                    {
                        "fact_id": fact_id,
                        "fact_text": fact.fact_text[:1000],
                        "fact_type": fact.fact_type,
                        "date_mentioned": fact.date_mentioned.isoformat() if fact.date_mentioned else None,
                    }
                )
                for evidence in fact.evidences:
                    evidence_id = add_evidence(evidence, fact.fact_text)
                    if evidence_id:
                        fact_evidence_rows.append({"fact_id": fact_id, "evidence_id": evidence_id})

            for claim in extraction.claims:
                claim_id = self._build_deterministic_id("CLM", f"{doc_id}:{claim.claim_text}")
                claim_rows.append(
                    {
                        "claim_id": claim_id,
                        "claim_text": claim.claim_text[:1000],
                        "claim_type": claim.claim_type,
                        "author": claim.author,
                        "sentiment": claim.sentiment.value if hasattr(claim.sentiment, "value") else str(claim.sentiment),
                    }
                )
                for evidence in claim.evidences:
                    evidence_id = add_evidence(evidence, claim.claim_text)
                    if evidence_id:
                        claim_evidence_rows.append({"claim_id": claim_id, "evidence_id": evidence_id})

            for link in extraction.links:
                source_ref = (link.source_ref or "").strip()
                target_ref = (link.target_ref or "").strip()
                if not source_ref or not target_ref:
                    continue

                link_type = link.link_type.value if hasattr(link.link_type, "value") else str(link.link_type)
                source_event_id = ensure_event(source_ref)
                evidence_id = add_evidence(link.evidence, f"{source_ref} {link_type} {target_ref}")

                link_claim_id = self._build_deterministic_id(
                    "CLM",
                    f"{doc_id}:{source_ref}:{target_ref}:{link_type}",
                )
                claim_rows.append(
                    {
                        "claim_id": link_claim_id,
                        "claim_text": f"{source_ref} {link_type} {target_ref}"[:1000],
                        "claim_type": "analysis",
                        "author": "llm_link",
                        "sentiment": "neutral",
                    }
                )
                claim_about_rows.append({"claim_id": link_claim_id, "event_id": source_event_id})
                if evidence_id:
                    claim_evidence_rows.append({"claim_id": link_claim_id, "evidence_id": evidence_id})

                if link.target_type == "Theme":
                    theme_id = self._resolve_theme_id(target_ref)
                    if not theme_id:
                        continue
                    event_theme_rows.append({"event_id": source_event_id, "theme_id": theme_id})
                    if link_type == "AFFECTS":
                        theme_affects_rows.append(
                            {
                                "event_id": source_event_id,
                                "theme_id": theme_id,
                                "polarity": self.THEME_DEFAULT_POLARITY.get(theme_id, "mixed"),
                                "weight": float(max(link.strength, 0.30)),
                                "confidence": self._confidence_score(
                                    getattr(link.evidence, "confidence", None),
                                    default=float(max(link.strength, 0.45)),
                                ),
                                "horizon_days": default_horizon_days,
                                "source": "llm_extraction_link",
                            }
                        )
                elif link.target_type == "Indicator":
                    indicator_code = target_ref.upper()
                    event_indicator_rows.append(
                        {
                            "event_id": source_event_id,
                            "indicator_code": indicator_code,
                            "polarity": "mixed",
                            "weight": float(max(link.strength, 0.30)),
                            "confidence": self._confidence_score(
                                getattr(link.evidence, "confidence", None),
                                default=float(max(link.strength, 0.45)),
                            ),
                            "horizon_days": default_horizon_days,
                            "source": "llm_extraction_link",
                        }
                    )
                elif link.target_type == "Event" and link_type == "CAUSES":
                    target_event_id = ensure_event(target_ref)
                    causes_rows.append(
                        {
                            "src_event_id": source_event_id,
                            "dst_event_id": target_event_id,
                            "confidence": self._confidence_score(
                                getattr(link.evidence, "confidence", None),
                                default=float(max(link.strength, 0.40)),
                            ),
                        }
                    )

            combined_text = " ".join(
                part for part in (news.get("title"), news.get("description"), news.get("text")) if part
            )
            llm_entities = []
            for fact in extraction.facts:
                llm_entities.extend(fact.entities_mentioned)

            nel_result = self.nel_pipeline.process_with_llm_mentions(combined_text, llm_entities)
            for mention in nel_result.mentions:
                if not mention.canonical_id:
                    continue
                canonical_id = mention.canonical_id
                existing = entity_rows.get(canonical_id)
                if existing:
                    existing["confidence"] = max(existing["confidence"], mention.confidence)
                else:
                    entity_rows[canonical_id] = {
                        "canonical_id": canonical_id,
                        "name": mention.canonical_name or mention.text,
                        "entity_type": (mention.entity_type or "unknown").lower(),
                        "confidence": mention.confidence,
                    }
                alias_key = f"{canonical_id}:{mention.text.strip().lower()}"
                entity_alias_rows[alias_key] = {
                    "canonical_id": canonical_id,
                    "alias": mention.text[:150],
                    "lang": "en",
                }

            write_total = {
                "nodes_created": 0,
                "nodes_deleted": 0,
                "relationships_created": 0,
                "relationships_deleted": 0,
                "properties_set": 0,
                "constraints_added": 0,
                "indexes_added": 0,
            }

            metadata_query = """
            MATCH (d:Document {doc_id: $doc_id})
            SET d.extraction_status = "success",
                d.extraction_schema_version = $schema_version,
                d.extraction_version = $extractor_version,
                d.extraction_model = $model_name,
                d.extraction_confidence = $extraction_confidence,
                d.extraction_error_count = $error_count,
                d.extracted_at = datetime($extracted_at),
                d.extraction_updated_at = datetime()
            """
            metadata_result = self.neo4j_client.run_write(
                metadata_query,
                {
                    "doc_id": doc_id,
                    "schema_version": extraction.schema_version,
                    "extractor_version": extraction.extractor_version,
                    "model_name": extraction.model_name,
                    "extraction_confidence": extraction.extraction_confidence,
                    "error_count": len(extraction.error_messages),
                    "extracted_at": self._to_iso_datetime(extraction.extracted_at) or default_event_time,
                },
            )
            self._merge_write_result(write_total, metadata_result)

            if event_rows:
                event_query = """
                UNWIND $events AS row
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (ev:Event {event_id: row.event_id})
                SET ev.event_name = row.event_name,
                    ev.type = row.event_type,
                    ev.summary = row.summary,
                    ev.event_time = datetime(row.event_time),
                    ev.country = coalesce(row.country, ev.country, d.country),
                    ev.country_code = coalesce(row.country_code, ev.country_code, d.country_code),
                    ev.impact_level = row.impact_level,
                    ev.source = "llm_extraction",
                    ev.updated_at = datetime()
                MERGE (d)-[:MENTIONS]->(ev)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(event_query, {"doc_id": doc_id, "events": event_rows}),
                )

            if event_theme_rows:
                theme_query = """
                UNWIND $rows AS row
                MATCH (ev:Event {event_id: row.event_id})
                MATCH (t:MacroTheme {theme_id: row.theme_id})
                MERGE (ev)-[r:ABOUT_THEME]->(t)
                ON CREATE SET r.source = "llm_extraction", r.created_at = datetime()
                SET r.updated_at = datetime()
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(theme_query, {"rows": event_theme_rows}),
                )

            if event_indicator_rows:
                indicator_affect_query = """
                UNWIND $rows AS row
                MATCH (ev:Event {event_id: row.event_id})
                MATCH (i:EconomicIndicator {indicator_code: row.indicator_code})
                MERGE (ev)-[r:AFFECTS]->(i)
                ON CREATE SET r.polarity = row.polarity,
                              r.weight = row.weight,
                              r.confidence = row.confidence,
                              r.horizon_days = row.horizon_days,
                              r.source = row.source,
                              r.created_at = datetime()
                SET r.updated_at = datetime()
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(indicator_affect_query, {"rows": event_indicator_rows}),
                )

            if theme_affects_rows:
                theme_affect_query = """
                UNWIND $rows AS row
                MATCH (ev:Event {event_id: row.event_id})
                MATCH (t:MacroTheme {theme_id: row.theme_id})
                MATCH (i:EconomicIndicator)-[:BELONGS_TO]->(t)
                MERGE (ev)-[r:AFFECTS]->(i)
                ON CREATE SET r.polarity = row.polarity,
                              r.weight = row.weight,
                              r.confidence = row.confidence,
                              r.horizon_days = row.horizon_days,
                              r.source = row.source,
                              r.created_at = datetime()
                SET r.updated_at = datetime()
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(theme_affect_query, {"rows": theme_affects_rows}),
                )

            if causes_rows:
                causes_query = """
                UNWIND $rows AS row
                MATCH (src:Event {event_id: row.src_event_id})
                MATCH (dst:Event {event_id: row.dst_event_id})
                MERGE (src)-[r:CAUSES]->(dst)
                ON CREATE SET r.confidence = row.confidence,
                              r.source = "llm_extraction",
                              r.created_at = datetime()
                SET r.updated_at = datetime()
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(causes_query, {"rows": causes_rows}),
                )

            if fact_rows:
                fact_query = """
                UNWIND $facts AS row
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (f:Fact {fact_id: row.fact_id})
                SET f.text = row.fact_text,
                    f.fact_type = row.fact_type,
                    f.date_mentioned = CASE
                      WHEN row.date_mentioned IS NOT NULL THEN date(row.date_mentioned)
                      ELSE NULL
                    END,
                    f.source = "llm_extraction",
                    f.updated_at = datetime()
                MERGE (d)-[:MENTIONS]->(f)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(fact_query, {"doc_id": doc_id, "facts": fact_rows}),
                )

            if claim_rows:
                claim_query = """
                UNWIND $claims AS row
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (c:Claim {claim_id: row.claim_id})
                SET c.text = row.claim_text,
                    c.claim_type = row.claim_type,
                    c.author = row.author,
                    c.sentiment = row.sentiment,
                    c.source = "llm_extraction",
                    c.updated_at = datetime()
                MERGE (d)-[:MENTIONS]->(c)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(claim_query, {"doc_id": doc_id, "claims": claim_rows}),
                )

            if claim_about_rows:
                claim_about_query = """
                UNWIND $rows AS row
                MATCH (c:Claim {claim_id: row.claim_id})
                MATCH (ev:Event {event_id: row.event_id})
                MERGE (c)-[r:ABOUT]->(ev)
                ON CREATE SET r.source = "llm_extraction", r.created_at = datetime()
                SET r.updated_at = datetime()
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(claim_about_query, {"rows": claim_about_rows}),
                )

            if evidence_rows:
                evidence_query = """
                UNWIND $rows AS row
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (evi:Evidence {evidence_id: row.evidence_id})
                SET evi.text = row.evidence_text,
                    evi.source_sentence = row.source_sentence,
                    evi.lang = row.language,
                    evi.confidence = row.confidence,
                    evi.source = "llm_extraction",
                    evi.updated_at = datetime()
                MERGE (d)-[:HAS_EVIDENCE]->(evi)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(
                        evidence_query, {"doc_id": doc_id, "rows": list(evidence_rows.values())}
                    ),
                )

            if fact_evidence_rows:
                fact_support_query = """
                UNWIND $rows AS row
                MATCH (evi:Evidence {evidence_id: row.evidence_id})
                MATCH (f:Fact {fact_id: row.fact_id})
                MERGE (evi)-[:SUPPORTS]->(f)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(fact_support_query, {"rows": fact_evidence_rows}),
                )

            if claim_evidence_rows:
                claim_support_query = """
                UNWIND $rows AS row
                MATCH (evi:Evidence {evidence_id: row.evidence_id})
                MATCH (c:Claim {claim_id: row.claim_id})
                MERGE (evi)-[:SUPPORTS]->(c)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(claim_support_query, {"rows": claim_evidence_rows}),
                )

            if entity_rows:
                entity_query = """
                UNWIND $rows AS row
                MATCH (d:Document {doc_id: $doc_id})
                MERGE (e:Entity {canonical_id: row.canonical_id})
                SET e.name = coalesce(e.name, row.name),
                    e.entity_type = coalesce(e.entity_type, row.entity_type),
                    e.source = coalesce(e.source, "nel_pipeline"),
                    e.updated_at = datetime()
                MERGE (d)-[r:MENTIONS]->(e)
                ON CREATE SET r.confidence = row.confidence,
                              r.source = "nel_pipeline",
                              r.created_at = datetime()
                SET r.updated_at = datetime()
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(
                        entity_query,
                        {"doc_id": doc_id, "rows": list(entity_rows.values())},
                    ),
                )

            if entity_alias_rows:
                alias_query = """
                UNWIND $rows AS row
                MERGE (a:EntityAlias {
                    canonical_id: row.canonical_id,
                    alias: row.alias,
                    lang: row.lang
                })
                SET a.source = "nel_pipeline",
                    a.updated_at = datetime()
                WITH row, a
                MATCH (e:Entity {canonical_id: row.canonical_id})
                MERGE (e)-[:HAS_ALIAS]->(a)
                """
                self._merge_write_result(
                    write_total,
                    self.neo4j_client.run_write(alias_query, {"rows": list(entity_alias_rows.values())}),
                )

            self._merge_write_result(total_write, write_total)
            success_docs += 1
            if index % step_interval == 0 or index == total_docs:
                self._log_progress(
                    stage="Extraction",
                    processed=index,
                    total=total_docs,
                    started_at=extraction_started_at,
                    success=success_docs,
                    failed=failed_docs,
                    skipped=skipped_docs,
                    extra=(
                        f"nodes_created={total_write['nodes_created']} "
                        f"rels_created={total_write['relationships_created']}"
                    ),
                )

        logger.info(
            "[NewsLoader] Extraction persisted: processed=%s success=%s failed=%s skipped=%s",
            len(target_news),
            success_docs,
            failed_docs,
            skipped_docs,
        )
        return {
            "status": "success",
            "processed_docs": len(target_news),
            "success_docs": success_docs,
            "failed_docs": failed_docs,
            "skipped_docs": skipped_docs,
            "failed_doc_ids": failed_doc_ids,
            "write_result": total_write,
        }

    def backfill_extractions(
        self,
        limit: int = 500,
        days: int = 30,
        progress_log_interval: int = 25,
    ) -> Dict[str, Any]:
        """
        최근 N일 문서를 대상으로 LLM 추출을 재실행/재적재한다. (Phase B-6 Backfill)
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        news_list = self.fetch_news_from_mysql(
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        return self.extract_and_persist(
            news_list,
            progress_log_interval=progress_log_interval,
        )
    
    def sync_news(
        self,
        limit: int = 500,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        run_extraction: bool = False,
        extraction_limit: Optional[int] = None,
        extraction_progress_log_interval: int = 25,
    ) -> Dict[str, Any]:
        """뉴스 동기화 전체 파이프라인"""
        pipeline_started_at = time.monotonic()
        logger.info(
            "[NewsLoader] Starting news sync (limit=%s, run_extraction=%s, extraction_limit=%s)",
            limit,
            run_extraction,
            extraction_limit,
        )
        
        # 1. MySQL에서 뉴스 조회
        news_list = self.fetch_news_from_mysql(limit, start_date, end_date)
        
        if not news_list:
            return {"status": "no_data", "documents": 0}
        
        # 2. Document 노드 생성
        doc_result = self.upsert_documents(news_list)
        
        # 3. Theme 연결
        theme_result = self.link_to_themes(news_list)
        
        # 4. Entity 연결
        entity_result = self.link_to_entities(news_list)

        extraction_result = None
        if run_extraction:
            logger.info(
                "[NewsLoader] Extraction stage start (docs=%s, limit=%s)",
                len(news_list),
                extraction_limit,
            )
            extraction_result = self.extract_and_persist(
                news_list,
                max_docs=extraction_limit,
                progress_log_interval=extraction_progress_log_interval,
            )
        
        response = {
            "status": "success",
            "documents": len(news_list),
            "doc_result": doc_result,
            "theme_links": theme_result,
            "entity_links": entity_result
        }
        if extraction_result is not None:
            response["extraction"] = extraction_result
        logger.info(
            "[NewsLoader] Sync complete in %s (documents=%s)",
            self._format_duration(time.monotonic() - pipeline_started_at),
            len(news_list),
        )
        return response
    
    def verify_sync(self) -> Dict[str, Any]:
        """뉴스 동기화 검증"""
        queries = {
            "documents": "MATCH (d:Document) RETURN count(d) AS count",
            "about_theme": "MATCH ()-[r:ABOUT_THEME]->() RETURN count(r) AS count",
            "mentions": "MATCH ()-[r:MENTIONS]->() RETURN count(r) AS count",
            "theme_distribution": """
                MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)
                RETURN t.theme_id AS theme, count(d) AS count
                ORDER BY count DESC
            """,
            "entity_mentions": """
                MATCH (d:Document)-[:MENTIONS]->(e:Entity)
                RETURN e.name AS entity, count(d) AS count
                ORDER BY count DESC LIMIT 10
            """
        }
        
        results = {}
        for name, query in queries.items():
            results[name] = self.neo4j_client.run_read(query)
        
        logger.info("[NewsLoader] Verification:")
        logger.info(f"  Documents: {results['documents']}")
        logger.info(f"  ABOUT_THEME links: {results['about_theme']}")
        logger.info(f"  MENTIONS links: {results['mentions']}")
        
        return results

    def _build_deterministic_id(self, prefix: str, raw: str) -> str:
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}_{digest}"

    def backfill_events_and_affects(
        self,
        limit: int = 1000,
        horizon_days: int = 7,
        initial_weight: float = 0.5,
        initial_confidence: float = 0.35
    ) -> Dict[str, Any]:
        """
        Document-Theme 링크를 Event/AFFECTS 구조로 브릿징한다.
        LLM 추출 적재가 붙기 전까지 Phase C 계산의 최소 입력을 생성하기 위한 보조 경로.
        """
        fetch_query = """
        MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)
        WHERE d.published_at IS NOT NULL
        RETURN d.doc_id AS doc_id,
               d.title AS title,
               d.description AS description,
               d.text AS text,
               toString(d.published_at) AS published_at,
               t.theme_id AS theme_id
        ORDER BY d.published_at DESC
        LIMIT $limit
        """
        rows = self.neo4j_client.run_read(fetch_query, {"limit": limit})
        if not rows:
            return {"status": "no_data", "rows": 0}

        batch = []
        for row in rows:
            doc_id = row["doc_id"]
            theme_id = row["theme_id"]
            title = row.get("title") or ""
            description = row.get("description") or ""
            text = row.get("text") or ""
            published_at = row.get("published_at")
            evidence_text = (text or description or title or doc_id).strip()[:320]
            event_summary = (title or description or f"{theme_id} macro event").strip()[:180]

            event_id = self._build_deterministic_id("EVT", f"{doc_id}:{theme_id}")
            claim_id = self._build_deterministic_id("CLM", f"{doc_id}:{theme_id}:rule")
            evidence_id = self._build_deterministic_id("EVD", f"{doc_id}:{theme_id}:{evidence_text}")

            batch.append({
                "doc_id": doc_id,
                "theme_id": theme_id,
                "event_id": event_id,
                "claim_id": claim_id,
                "evidence_id": evidence_id,
                "event_summary": event_summary,
                "event_time": published_at,
                "claim_text": f"{theme_id} theme signal derived from document",
                "evidence_text": evidence_text,
                "polarity": self.THEME_DEFAULT_POLARITY.get(theme_id, "mixed"),
                "initial_weight": initial_weight,
                "initial_confidence": initial_confidence,
                "horizon_days": horizon_days,
            })

        upsert_query = """
        UNWIND $rows AS row
        MERGE (ev:Event {event_id: row.event_id})
        SET ev.type = "theme_signal",
            ev.summary = row.event_summary,
            ev.event_time = datetime(row.event_time),
            ev.source = "rule_based_theme_mapping",
            ev.updated_at = datetime()
        WITH row, ev
        MATCH (d:Document {doc_id: row.doc_id})
        MATCH (t:MacroTheme {theme_id: row.theme_id})
        MERGE (d)-[:MENTIONS]->(ev)
        MERGE (ev)-[:ABOUT_THEME]->(t)
        WITH row, ev, d, t
        MERGE (c:Claim {claim_id: row.claim_id})
        SET c.text = row.claim_text,
            c.polarity = row.polarity,
            c.confidence = row.initial_confidence,
            c.source = "rule_based_theme_mapping",
            c.updated_at = datetime()
        MERGE (c)-[:ABOUT]->(ev)
        MERGE (evi:Evidence {evidence_id: row.evidence_id})
        SET evi.text = row.evidence_text,
            evi.lang = "en",
            evi.source = "document_snippet",
            evi.updated_at = datetime()
        MERGE (d)-[:HAS_EVIDENCE]->(evi)
        MERGE (evi)-[:SUPPORTS]->(c)
        WITH row, ev, t
        MATCH (i:EconomicIndicator)-[:BELONGS_TO]->(t)
        MERGE (ev)-[r:AFFECTS]->(i)
        ON CREATE SET r.polarity = row.polarity,
                      r.weight = row.initial_weight,
                      r.confidence = row.initial_confidence,
                      r.horizon_days = row.horizon_days,
                      r.source = "rule_based_theme_mapping",
                      r.created_at = datetime()
        SET r.updated_at = datetime()
        """
        result = self.neo4j_client.run_write(upsert_query, {"rows": batch})
        logger.info("[NewsLoader] Backfilled Event/AFFECTS from %s docs: %s", len(batch), result)
        return {
            "status": "success",
            "rows": len(batch),
            "result": result
        }


def sync_news(
    limit: int = 500,
    days: int = 30,
    run_extraction: bool = False,
    extraction_limit: Optional[int] = None,
    extraction_progress_log_interval: int = 25,
) -> Dict[str, Any]:
    """뉴스 동기화 (편의 함수)"""
    loader = NewsLoader()
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    result = loader.sync_news(
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        run_extraction=run_extraction,
        extraction_limit=extraction_limit,
        extraction_progress_log_interval=extraction_progress_log_interval,
    )
    verification = loader.verify_sync()
    
    return {"sync_result": result, "verification": verification}


def sync_news_with_extraction(
    limit: int = 500,
    days: int = 30,
    extraction_progress_log_interval: int = 25,
) -> Dict[str, Any]:
    """
    Document 적재 + 기본 링크 + LLM 추출 결과(Event/Fact/Claim/Evidence/AFFECTS)까지 한 번에 수행.
    """
    return sync_news(
        limit=limit,
        days=days,
        run_extraction=True,
        extraction_progress_log_interval=extraction_progress_log_interval,
    )


def sync_news_with_extraction_backlog(
    sync_limit: int = 2000,
    sync_days: int = 30,
    extraction_batch_size: int = 200,
    max_extraction_batches: int = 10,
    retry_failed_after_minutes: int = 180,
    extraction_progress_log_interval: int = 25,
) -> Dict[str, Any]:
    """
    Document 동기화 후 미처리/실패 문서를 전량 배치로 추출 적재한다.
    """
    loader = NewsLoader()
    return loader.sync_news_with_extraction_backlog(
        sync_limit=sync_limit,
        sync_days=sync_days,
        extraction_batch_size=extraction_batch_size,
        max_extraction_batches=max_extraction_batches,
        retry_failed_after_minutes=retry_failed_after_minutes,
        extraction_progress_log_interval=extraction_progress_log_interval,
    )


def backfill_news_extractions(
    limit: int = 500,
    days: int = 30,
    progress_log_interval: int = 25,
) -> Dict[str, Any]:
    """최근 N일 문서를 대상으로 LLM 추출 재적재."""
    loader = NewsLoader()
    return loader.backfill_extractions(
        limit=limit,
        days=days,
        progress_log_interval=progress_log_interval,
    )


def backfill_events_and_affects(limit: int = 1000) -> Dict[str, Any]:
    """Document-Theme 기반 Event/AFFECTS 브릿지 적재 (편의 함수)"""
    loader = NewsLoader()
    return loader.backfill_events_and_affects(limit=limit)


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from dotenv import load_dotenv
    load_dotenv()
    
    result = sync_news(limit=500, days=30)
    print("\n=== SYNC RESULT ===")
    print(result)
