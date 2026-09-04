"""Test-only PaperLab catalog and invocation guard fixture exports."""

from .fake_catalog import (
    BROAD_READONLY_EXTRA_NAMES,
    DEFAULT_BROAD_CATALOG,
    FOREIGN_NAMES,
    HIDDEN_OR_AUTHORITY_NAMES,
    MAX_CATALOG_ENTRIES,
    PAPERLAB_RAW_OPERATIONS,
    PUBLIC_OPERATIONS,
    WRITE_NAMES,
    CatalogSnapshot,
    FakeCatalogGuard,
    InvocationResult,
)

__all__ = [
    "BROAD_READONLY_EXTRA_NAMES",
    "DEFAULT_BROAD_CATALOG",
    "FOREIGN_NAMES",
    "HIDDEN_OR_AUTHORITY_NAMES",
    "MAX_CATALOG_ENTRIES",
    "PAPERLAB_RAW_OPERATIONS",
    "PUBLIC_OPERATIONS",
    "WRITE_NAMES",
    "CatalogSnapshot",
    "FakeCatalogGuard",
    "InvocationResult",
]
