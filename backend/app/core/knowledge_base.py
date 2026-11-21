"""
Centralized, High-Performance Cached Knowledge Base for Cutoffs and Rules.
Eliminates disk I/O bottlenecks under high-concurrency exam-day load.
Uses LRU caching in memory for sub-microsecond access.
"""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@lru_cache(maxsize=16)
def load_cached_json(filename: str) -> Any:
    """
    Loads JSON from disk and caches in memory.
    Subsequent calls execute in sub-microseconds without filesystem locks.
    """
    p = DATA_DIR / filename
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_coap_cutoffs() -> List[Dict]:
    return load_cached_json("cutoffs_coap.json")


def get_ccmt_cutoffs() -> List[Dict]:
    return load_cached_json("cutoffs_ccmt.json")


def get_psu_cutoffs() -> List[Dict]:
    return load_cached_json("cutoffs_psu.json")


def get_branch_matrix() -> Dict[str, List[str]]:
    data = load_cached_json("branch_matrix.json")
    return data if isinstance(data, dict) else {}


def invalidate_knowledge_base_cache():
    """Forces cache clearing if admin updates cutoff files dynamically."""
    load_cached_json.cache_clear()
