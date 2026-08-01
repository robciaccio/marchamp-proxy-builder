"""T031 — image validation and fit modes (FR-009b, FR-009b1, FR-009b2, FR-010, FR-014)."""

from __future__ import annotations

import pytest

from marchamp.render.images import (
    FitMode,
    ImageTooSmall,
    fit_rect,
    min_source_pixels,
    validate_source,
)
from tests.conftest import make_card_image

SLOT_W, SLOT_H = 63.5, 88.9
SRC_W, SRC_H = 1446, 2079  # ratio 1.4378, like the real scans


def test_required_source_pixels_for_300_dpi():
    # FR-010: 63.5 x 88.9 mm at 300 DPI is 750 x 1050 px.
    assert min_source_pixels(SLOT_W, SLOT_H, dpi=300) == (750, 1050)


def test_crop_fills_the_slot_exactly():
    r = fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.CROP)
    assert r.draw_w_mm == pytest.approx(SLOT_W, abs=0.01)
    assert r.draw_h_mm == pytest.approx(SLOT_H, abs=0.01)


def test_crop_trims_symmetrically_top_and_bottom():
    # FR-009b: half the overflow from each edge, never all from one side.
    r = fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.CROP)
    assert r.src_crop_top_px == pytest.approx(r.src_crop_bottom_px, abs=1)
    assert r.src_crop_top_px > 0


def test_fit_preserves_ratio_and_never_exceeds_the_slot():
    r = fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.FIT)
    assert r.draw_w_mm <= SLOT_W + 1e-9
    assert r.draw_h_mm <= SLOT_H + 1e-9
    assert r.draw_w_mm / r.draw_h_mm == pytest.approx(SRC_W / SRC_H, rel=1e-6)
    # The spec's worked figure for these scans.
    assert r.draw_w_mm == pytest.approx(61.8, abs=0.2)
    assert r.draw_h_mm == pytest.approx(88.9, abs=0.01)


def test_fit_crops_nothing():
    r = fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.FIT)
    assert r.src_crop_top_px == 0 and r.src_crop_bottom_px == 0


def test_stretch_fills_exactly_and_distorts():
    r = fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.STRETCH)
    assert r.draw_w_mm == pytest.approx(SLOT_W, abs=0.01)
    assert r.draw_h_mm == pytest.approx(SLOT_H, abs=0.01)
    assert r.src_crop_top_px == 0
    assert r.distorts is True


def test_only_stretch_distorts():
    # FR-014 — distortion nowhere else, ever.
    assert fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.CROP).distorts is False
    assert fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.FIT).distorts is False


def test_each_card_is_fitted_on_its_own_measurements():
    # FR-009b2 — real scans vary from one another, so no deck-wide ratio is assumed.
    a = fit_rect(1446, 2079, SLOT_W, SLOT_H, FitMode.FIT)
    b = fit_rect(1443, 2085, SLOT_W, SLOT_H, FitMode.FIT)
    assert a.draw_w_mm != pytest.approx(b.draw_w_mm, abs=1e-6)


def test_dpi_measured_over_the_printed_region_for_crop():
    # Cropped pixels do not contribute to what is printed.
    r = fit_rect(SRC_W, SRC_H, SLOT_W, SLOT_H, FitMode.CROP)
    used_h = SRC_H - r.src_crop_top_px - r.src_crop_bottom_px
    assert r.effective_dpi_y == pytest.approx(used_h / (SLOT_H / 25.4), rel=1e-6)


def test_source_below_300_dpi_is_rejected(tmp_path):
    small = make_card_image(tmp_path / "small.tiff", "S", width=400, height=575)
    with pytest.raises(ImageTooSmall):
        validate_source(small, SLOT_W, SLOT_H, FitMode.CROP)


def test_adequate_source_passes(tmp_path):
    ok = make_card_image(tmp_path / "ok.tiff", "OK")
    assert validate_source(ok, SLOT_W, SLOT_H, FitMode.CROP).width_px == SRC_W


def test_pixel_ceiling_is_set_not_disabled():
    # The common workaround (MAX_IMAGE_PIXELS = None) removes exactly the
    # decompression-bomb protection the constitution asks for.
    from PIL import Image

    import marchamp.render.images  # noqa: F401  (import applies the ceiling)

    assert Image.MAX_IMAGE_PIXELS is not None
    assert Image.MAX_IMAGE_PIXELS <= 80_000_000
