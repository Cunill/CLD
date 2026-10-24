"""From a photo candidate to a new photo of the project (shared by the interface and the command line)."""

from __future__ import annotations

from passimaker.importer.types import PhotoCandidate
from passimaker.model import OutputFormat, Photo


def photo_from_candidate(candidate: PhotoCandidate, photo_id: str, output_format: OutputFormat) -> Photo:
    """A new photo with the default settings; its motion is drawn by the controller."""
    return Photo(
        id=photo_id,
        path=candidate.path,
        relative_path=None,
        width=candidate.width,
        height=candidate.height,
        exif_orientation=candidate.exif_orientation,
        capture_time=candidate.capture_time,
        # §1.1: short side under half the video's (540 px in 1080p) -> "low resolution" icon.
        low_resolution=2 * min(candidate.width, candidate.height) < min(output_format.size),
    )
