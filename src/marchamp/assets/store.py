"""Asset store protocol — the seam Principle III requires.

Callers know only opaque refs. Whether a ref is a relative path today or an object key
later is the adapter's business alone, so moving to object storage never touches assembly
logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable


class AssetError(Exception):
    """Base for asset access problems."""


class AssetMissing(AssetError):
    """No such asset."""


class AssetUnreadable(AssetError):
    """Present but not usable right now — locked, truncated, or not yet synced."""


@dataclass(frozen=True)
class AssetInfo:
    ref: str
    byte_size: int
    detected_format: str
    width_px: int
    height_px: int


@runtime_checkable
class Store(Protocol):
    def exists(self, ref: str) -> bool: ...

    def open(self, ref: str) -> BinaryIO: ...

    def describe(self, ref: str) -> AssetInfo: ...
