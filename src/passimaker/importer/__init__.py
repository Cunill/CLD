"""M2 · Photo import and metadata (block B4).

Public API: import_paths and sort_candidates, with the data types of docs/CONTRACTES.md §2.
Only file headers are read here; pixels are decoded by passimaker.images.
"""

from passimaker.importer.order import DATE_ORDER_MIN_FRACTION, sort_candidates
from passimaker.importer.scan import import_paths, path_key
from passimaker.importer.types import (
    RAW_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    FailedFile,
    ImportFailure,
    ImportResult,
    PhotoCandidate,
)

__all__ = [
    "DATE_ORDER_MIN_FRACTION",
    "RAW_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "FailedFile",
    "ImportFailure",
    "ImportResult",
    "PhotoCandidate",
    "import_paths",
    "path_key",
    "sort_candidates",
]
