"""context_layer/sources — Vault scanning and source cache (A4)."""

from .vault_scanner import scan_vault, scan_bibtex_files
from .source_cache import (
    load_cache,
    save_cache,
    update_cache,
    get_source_paths,
    cache_stats,
)

__all__ = [
    "scan_vault",
    "scan_bibtex_files",
    "load_cache",
    "save_cache",
    "update_cache",
    "get_source_paths",
    "cache_stats",
]
