"""
Neo4j Client for Macro Knowledge Graph (MKG)
Phase A: 기본 연결 및 쿼리 실행
"""
import os
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j Macro Graph 연결 클라이언트"""
    
    _instance: Optional['Neo4jClient'] = None
    _driver: Optional[Driver] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._driver is None:
            self._connect()
    
    def _connect(self):
        """Neo4j Macro Graph에 연결"""
        uri = os.getenv("NEO4J_MACRO_URI")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "")
        
        if not uri:
            raise ValueError("NEO4J_MACRO_URI environment variable not set")
        
        logger.info(f"[Neo4jClient] Connecting to Macro Graph: {uri}")
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        
        # 연결 테스트
        self._driver.verify_connectivity()
        logger.info("[Neo4jClient] Connected successfully")
    
    @property
    def driver(self) -> Driver:
        if self._driver is None:
            self._connect()
        return self._driver
    
    def close(self):
        """연결 종료"""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("[Neo4jClient] Connection closed")
    
    @contextmanager
    def session(self):
        """세션 컨텍스트 매니저"""
        session = self.driver.session()
        try:
            yield session
        finally:
            session.close()
    
    def run_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Cypher 쿼리 실행 (읽기/쓰기 혼용)"""
        with self.session() as session:
            result = session.run(query, params or {})
            return [record.data() for record in result]
    
    def run_write(self, query: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """쓰기 트랜잭션으로 Cypher 쿼리 실행"""
        def _write_tx(tx, query, params):
            result = tx.run(query, params or {})
            summary = result.consume()
            return {
                "nodes_created": summary.counters.nodes_created,
                "nodes_deleted": summary.counters.nodes_deleted,
                "relationships_created": summary.counters.relationships_created,
                "relationships_deleted": summary.counters.relationships_deleted,
                "properties_set": summary.counters.properties_set,
                "constraints_added": summary.counters.constraints_added,
                "indexes_added": summary.counters.indexes_added,
            }
        
        with self.session() as session:
            return session.execute_write(_write_tx, query, params)
    
    def run_read(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """읽기 트랜잭션으로 Cypher 쿼리 실행"""
        def _read_tx(tx, query, params):
            result = tx.run(query, params or {})
            return [record.data() for record in result]
        
        with self.session() as session:
            return session.execute_read(_read_tx, query, params)
    
    def run_cypher_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Cypher 파일 실행 (;로 구분된 여러 쿼리 지원)"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 주석 제거 및 쿼리 분리
        queries = []
        current_query = []
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('//') or not stripped:
                continue
            current_query.append(line)
            if stripped.endswith(';'):
                query = '\n'.join(current_query)
                # 마지막 세미콜론 제거
                query = query.rstrip(';').strip()
                if query:
                    queries.append(query)
                current_query = []
        
        # 마지막 쿼리 (세미콜론 없이 끝난 경우)
        if current_query:
            query = '\n'.join(current_query).strip()
            if query:
                queries.append(query)
        
        results = []
        for i, query in enumerate(queries):
            logger.info(f"[Neo4jClient] Running query {i+1}/{len(queries)}")
            try:
                result = self.run_write(query)
                results.append({"query_index": i+1, "status": "success", **result})
                logger.info(f"  → {result}")
            except Exception as e:
                logger.error(f"  → Error: {e}")
                results.append({"query_index": i+1, "status": "error", "error": str(e)})
        
        return results


# 싱글톤 인스턴스 접근
def get_neo4j_client() -> Neo4jClient:
    return Neo4jClient()
