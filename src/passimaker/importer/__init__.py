"""M2 · Photo import and metadata (block B4).

Public API: import_paths, sort_candidates and photo_from_candidate, with the data types of
docs/CONTRACTES.md §2.
Only file headers are read here; pixels are decoded by passimaker.images.
"""

from passimaker.importer.order import sort_candidates
from passimaker.importer.photo import photo_from_candidate
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
    "RAW_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "FailedFile",
    "ImportFailure",
    "ImportResult",
    "PhotoCandidate",
    "import_paths",
    "path_key",
    "photo_from_candidate",
    "sort_candidates",
]
