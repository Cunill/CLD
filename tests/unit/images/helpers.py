"""Helpers shared by the B4 image tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from passimaker.images.decode import read_header
from passimaker.model.types import Photo, Rotation


def photo_for(path: Path, rotation: Rotation = Rotation.R0, photo_id: str | None = None) -> Photo:
    """A Photo for a real file, with the oriented (and rotated) size the importer would give."""
    try:
        width, height = read_header(path).oriented_size
    except Exception:
        width, height = 100, 100
    if rotation in (Rotation.R90, Rotation.R270):
        width, height = height, width
    return Photo(photo_id or path.name, path, None, width, height, rotation=rotation)


def mean_abs_diff(a: NDArray[np.uint8], b: NDArray[np.uint8]) -> float:
    assert a.shape == b.shape, (a.shape, b.shape)
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))


def dihedral(image: NDArray[np.uint8]) -> list[NDArray[np.uint8]]:
    """The 8 rotations and mirror images of `image`; index 0 is the image itself."""
    out: list[NDArray[np.uint8]] = []
    for flipped in (image, image[:, ::-1]):
        for k in range(4):
            out.append(np.ascontiguousarray(np.rot90(flipped, k)))
    return out
