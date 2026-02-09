"""NEL (Named Entity Linking) Package"""
from .alias_dictionary import get_alias_lookup, AliasLookup, ALIAS_DICTIONARY
from .nel_pipeline import get_nel_pipeline, NELPipeline, EntityMention, NELResult

__all__ = [
    "get_alias_lookup",
    "AliasLookup",
    "ALIAS_DICTIONARY",
    "get_nel_pipeline",
    "NELPipeline",
    "EntityMention",
    "NELResult",
]
