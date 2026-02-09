"""
Macro Knowledge Graph (MKG) - Seed Data Loader
Phase A: 초기 스키마 및 Seed 데이터 적재
"""
import os
import logging
from pathlib import Path
from .neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)

# 기본 Cypher 파일 경로
CYPHER_DIR = Path(__file__).parent.parent.parent.parent / "work-planning" / "graph-db-analysis" / "2026-02-04_2303" / "cypher"


def seed_constraints():
    """A-1: 제약조건 및 인덱스 생성"""
    client = get_neo4j_client()
    cypher_file = CYPHER_DIR / "00_constraints.cypher"
    
    logger.info(f"[Seed] Loading constraints from {cypher_file}")
    results = client.run_cypher_file(str(cypher_file))
    logger.info(f"[Seed] Constraints loaded: {len(results)} queries executed")
    return results


def seed_themes():
    """A-2: MacroTheme Seed 적재"""
    client = get_neo4j_client()
    cypher_file = CYPHER_DIR / "01_seed_themes.cypher"
    
    logger.info(f"[Seed] Loading themes from {cypher_file}")
    results = client.run_cypher_file(str(cypher_file))
    logger.info(f"[Seed] Themes loaded: {len(results)} queries executed")
    return results


def seed_indicators():
    """A-3: EconomicIndicator Seed 적재 + Theme 연결"""
    client = get_neo4j_client()
    cypher_file = CYPHER_DIR / "02_seed_indicators.cypher"
    
    logger.info(f"[Seed] Loading indicators from {cypher_file}")
    results = client.run_cypher_file(str(cypher_file))
    logger.info(f"[Seed] Indicators loaded: {len(results)} queries executed")
    return results


def seed_entities():
    """A-4: Entity/EntityAlias Seed 적재"""
    client = get_neo4j_client()
    cypher_file = CYPHER_DIR / "03_seed_entities.cypher"
    
    logger.info(f"[Seed] Loading entities from {cypher_file}")
    results = client.run_cypher_file(str(cypher_file))
    logger.info(f"[Seed] Entities loaded: {len(results)} queries executed")
    return results


def verify_seed():
    """Seed 적재 검증"""
    client = get_neo4j_client()
    
    # 노드 카운트
    count_query = """
    MATCH (t:MacroTheme) RETURN 'MacroTheme' AS label, count(t) AS count
    UNION ALL
    MATCH (i:EconomicIndicator) RETURN 'EconomicIndicator' AS label, count(i) AS count
    UNION ALL
    MATCH (e:Entity) RETURN 'Entity' AS label, count(e) AS count
    UNION ALL
    MATCH (a:EntityAlias) RETURN 'EntityAlias' AS label, count(a) AS count
    """
    
    counts = client.run_read(count_query)
    logger.info("[Seed] Node counts:")
    for row in counts:
        logger.info(f"  - {row['label']}: {row['count']}")
    
    # 관계 카운트
    rel_query = """
    MATCH ()-[r:BELONGS_TO]->() RETURN 'BELONGS_TO' AS rel, count(r) AS count
    UNION ALL
    MATCH ()-[r:HAS_ALIAS]->() RETURN 'HAS_ALIAS' AS rel, count(r) AS count
    """
    
    rels = client.run_read(rel_query)
    logger.info("[Seed] Relationship counts:")
    for row in rels:
        logger.info(f"  - {row['rel']}: {row['count']}")
    
    return {"nodes": counts, "relationships": rels}


def run_all_seeds():
    """모든 Seed 적재 실행"""
    logger.info("=" * 60)
    logger.info("[Seed] Starting Macro Knowledge Graph Seed Process")
    logger.info("=" * 60)
    
    results = {}
    
    # A-1: Constraints
    logger.info("\n[A-1] Creating constraints and indexes...")
    results["constraints"] = seed_constraints()
    
    # A-2: Themes
    logger.info("\n[A-2] Seeding MacroTheme nodes...")
    results["themes"] = seed_themes()
    
    # A-3: Indicators
    logger.info("\n[A-3] Seeding EconomicIndicator nodes...")
    results["indicators"] = seed_indicators()
    
    # A-4: Entities
    logger.info("\n[A-4] Seeding Entity and EntityAlias nodes...")
    results["entities"] = seed_entities()
    
    # Verification
    logger.info("\n[Verify] Checking seed results...")
    results["verification"] = verify_seed()
    
    logger.info("\n" + "=" * 60)
    logger.info("[Seed] Seed process completed!")
    logger.info("=" * 60)
    
    return results


if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # .env 파일 로드
    from dotenv import load_dotenv
    load_dotenv()
    
    # Seed 실행
    run_all_seeds()
