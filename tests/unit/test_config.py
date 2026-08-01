"""T008 — settings resolution (FR-005c3, FR-019b, FR-0A4)."""

from __future__ import annotations

import pytest

from marchamp.config import ConfigProblem, Settings


def test_unset_paths_are_distinguishable_from_wrong_paths(tmp_path):
    unset = Settings(image_dir=None, catalog_path=None).problems()
    assert [p.kind for p in unset] == ["image_dir_unset", "catalog_unset"]

    missing = Settings(image_dir=tmp_path / "nope", catalog_path=tmp_path / "nope.json").problems()
    assert [p.kind for p in missing] == ["image_dir_missing", "catalog_missing"]


def test_problem_text_says_what_to_do(tmp_path):
    (problem,) = Settings(image_dir=None, catalog_path=tmp_path / "c.json").problems()[:1]
    assert isinstance(problem, ConfigProblem)
    assert problem.detail  # actionable text, not just a code
    assert "MARCHAMP_IMAGE_DIR" in problem.detail


def test_valid_settings_have_no_problems(image_dir, catalog_path):
    assert Settings(image_dir=image_dir, catalog_path=catalog_path).problems() == []


def test_limits_are_named_constants_not_scattered_literals():
    s = Settings(image_dir=None, catalog_path=None)
    assert s.limits.max_faces_per_generation == 200
    assert s.limits.generation_wall_clock_s == 120
    assert s.limits.decode_wall_clock_s == 10
    assert s.limits.decode_memory_bytes == 512 * 1024 * 1024
    assert s.limits.max_source_pixels == 80_000_000


def test_binds_loopback_by_default():
    assert Settings(image_dir=None, catalog_path=None).host == "127.0.0.1"


@pytest.mark.parametrize("bad_host", ["0.0.0.0", "::", "192.168.1.5"])
def test_non_loopback_host_is_rejected(bad_host):
    # FR-0A2: privacy must not depend on a firewall.
    with pytest.raises(ValueError):
        Settings(image_dir=None, catalog_path=None, host=bad_host)
