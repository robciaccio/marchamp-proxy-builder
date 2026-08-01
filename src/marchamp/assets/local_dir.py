"""Local directory asset store — the only implementation today (FR-019, FR-019c, FR-019d)."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

from marchamp.assets.store import AssetInfo, AssetMissing, AssetUnreadable


class LocalDirectoryStore:
    """Reads card images from a directory the user configures.

    Holds no credentials and makes no network call. Never writes: the image directory is
    read-only source material (FR-019c).
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    def _resolve(self, ref: str) -> Path:
        """Contain every ref inside the configured directory.

        The catalog is authored data, but it is still data — an absolute path or a `..`
        escape in it must not reach outside the folder the user pointed us at.
        """
        if Path(ref).is_absolute():
            raise ValueError(f"asset ref must be relative, got {ref!r}")
        candidate = (self._root / ref).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError(f"asset ref escapes the configured directory: {ref!r}")
        return candidate

    def exists(self, ref: str) -> bool:
        try:
            return self._resolve(ref).is_file()
        except ValueError:
            return False

    def open(self, ref: str) -> BinaryIO:
        p = self._resolve(ref)
        if not p.is_file():
            raise AssetMissing(ref)
        try:
            return p.open("rb")
        except OSError as exc:  # locked, permissions, still syncing
            raise AssetUnreadable(f"{ref}: {exc.strerror or exc}") from exc

    def describe(self, ref: str) -> AssetInfo:
        p = self._resolve(ref)
        if not p.is_file():
            raise AssetMissing(ref)
        try:
            with Image.open(p) as img:
                # Identified by content, never by extension or declared type (FR-019d).
                fmt = img.format or "UNKNOWN"
                w, h = img.size
        except (UnidentifiedImageError, OSError) as exc:
            raise AssetUnreadable(f"{ref}: {exc}") from exc
        return AssetInfo(
            ref=ref, byte_size=p.stat().st_size, detected_format=fmt, width_px=w, height_px=h
        )
