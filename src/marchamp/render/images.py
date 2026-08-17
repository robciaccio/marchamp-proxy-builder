"""Image validation and fit-mode geometry (FR-009b, FR-009b2, FR-010, FR-014, FR-015a)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from PIL import Image, UnidentifiedImageError

from marchamp.assets.store import AssetError, Store
from marchamp.config import Limits

# Set deliberately rather than disabled. The common workaround (MAX_IMAGE_PIXELS = None)
# removes exactly the decompression-bomb protection the constitution asks for.
Image.MAX_IMAGE_PIXELS = Limits().max_source_pixels

# Pinned so a library default change cannot silently alter output bytes (FR-015a).
RESAMPLE_FILTER = Image.Resampling.LANCZOS

MM_PER_INCH = 25.4
MIN_DPI = 300


class FitMode(StrEnum):
    CROP = "CROP"
    FIT = "FIT"
    STRETCH = "STRETCH"


class ImageTooSmall(Exception):
    """Below the resolution FR-010 requires at final print size."""


class ImageUnreadable(Exception):
    """Present but not decodable."""


@dataclass(frozen=True)
class SourceInfo:
    #: The opaque asset ref, not a path. Feature 002 reads faces from two roots and a
    #: finished run must render with the library unmounted (SC-006h), so nothing downstream
    #: may assume a source image has a location on this filesystem.
    ref: str
    width_px: int
    height_px: int


@dataclass(frozen=True)
class FitRect:
    """How one source image maps into one slot."""

    draw_w_mm: float
    draw_h_mm: float
    offset_x_mm: float
    offset_y_mm: float
    src_crop_top_px: float
    src_crop_bottom_px: float
    src_crop_left_px: float
    src_crop_right_px: float
    effective_dpi_x: float
    effective_dpi_y: float
    distorts: bool


def min_source_pixels(slot_w_mm: float, slot_h_mm: float, dpi: int = MIN_DPI) -> tuple[int, int]:
    return (
        round(slot_w_mm / MM_PER_INCH * dpi),
        round(slot_h_mm / MM_PER_INCH * dpi),
    )


def fit_rect(src_w: int, src_h: int, slot_w_mm: float, slot_h_mm: float, mode: FitMode) -> FitRect:
    """Map a source image into a slot under the selected fit mode.

    Each card is fitted on its own measurements (FR-009b2); no deck-wide ratio is assumed,
    because the real scans vary slightly from one another.
    """
    target_ratio = slot_w_mm / slot_h_mm
    src_ratio = src_w / src_h
    crop_t = crop_b = crop_l = crop_r = 0.0
    distorts = False

    if mode is FitMode.STRETCH:
        draw_w, draw_h = slot_w_mm, slot_h_mm
        distorts = True
        used_w, used_h = src_w, src_h
    elif mode is FitMode.FIT:
        scale = min(slot_w_mm / src_w, slot_h_mm / src_h)
        draw_w, draw_h = src_w * scale, src_h * scale
        used_w, used_h = src_w, src_h
    else:  # CROP — fill the slot, trimming the overflowing edges symmetrically
        draw_w, draw_h = slot_w_mm, slot_h_mm
        if src_ratio > target_ratio:
            # Source is proportionally wider: trim the sides.
            keep_w = src_h * target_ratio
            crop_l = crop_r = (src_w - keep_w) / 2
            used_w, used_h = keep_w, src_h
        else:
            # Source is proportionally taller — the real scans' case: trim top and bottom.
            keep_h = src_w / target_ratio
            crop_t = crop_b = (src_h - keep_h) / 2
            used_w, used_h = src_w, keep_h

    return FitRect(
        draw_w_mm=draw_w,
        draw_h_mm=draw_h,
        offset_x_mm=(slot_w_mm - draw_w) / 2,
        offset_y_mm=(slot_h_mm - draw_h) / 2,
        src_crop_top_px=crop_t,
        src_crop_bottom_px=crop_b,
        src_crop_left_px=crop_l,
        src_crop_right_px=crop_r,
        # Measured over the region actually printed: cropped pixels do not contribute.
        effective_dpi_x=used_w / (draw_w / MM_PER_INCH),
        effective_dpi_y=used_h / (draw_h / MM_PER_INCH),
        distorts=distorts,
    )


def validate_source(
    store: Store, ref: str, slot_w_mm: float, slot_h_mm: float, mode: FitMode, dpi: int = MIN_DPI
) -> SourceInfo:
    """Reject anything that cannot print at the required resolution (FR-010, FR-020).

    Reads through the adapter rather than joining a directory and a ref (FR-004, research
    R8). That is what lets an uploaded file (FR-026e), which lives in the run's own
    directory rather than in the named library, be validated by exactly this code — FR-028's
    "manual choice bypasses discovery, never validation", satisfied by calling what already
    existed rather than by writing a second check.
    """
    try:
        with store.open(ref) as handle, Image.open(handle) as img:
            w, h = img.size
    except (UnidentifiedImageError, OSError, AssetError) as exc:
        raise ImageUnreadable(str(exc)) from exc

    rect = fit_rect(w, h, slot_w_mm, slot_h_mm, mode)
    if math.floor(min(rect.effective_dpi_x, rect.effective_dpi_y)) < dpi:
        need_w, need_h = min_source_pixels(slot_w_mm, slot_h_mm, dpi)
        raise ImageTooSmall(
            f"{w}x{h}px gives {rect.effective_dpi_x:.0f}x{rect.effective_dpi_y:.0f} DPI at "
            f"final size; at least {need_w}x{need_h}px is required for {dpi} DPI"
        )
    return SourceInfo(ref=ref, width_px=w, height_px=h)
