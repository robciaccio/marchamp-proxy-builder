"""T008, T010 — settings resolution (FR-005, FR-005c3, FR-019b, FR-0A4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from marchamp.config import (
    ConfigProblem,
    Settings,
    StateDirectoryInsideLibrary,
    default_state_dir,
    settings_from_env,
)


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


# ------------------------------------------------------- T010: feature 002 configuration


def test_state_dir_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("MARCHAMP_STATE_DIR", str(tmp_path / "elsewhere"))
    assert settings_from_env().state_dir == tmp_path / "elsewhere"


def test_state_dir_defaults_to_the_platform_data_directory(monkeypatch):
    # Resolved from an explicit platform and environment rather than the running one, so
    # the Linux branch is covered on a Mac and the reverse.
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    home = Path("/home/someone")
    darwin = default_state_dir("darwin", {"HOME": str(home)})
    assert darwin == home / "Library" / "Application Support" / "marchamp"

    linux = default_state_dir("linux", {"HOME": str(home)})
    assert linux == home / ".local" / "share" / "marchamp"

    xdg = default_state_dir("linux", {"HOME": str(home), "XDG_DATA_HOME": "/data"})
    assert xdg == Path("/data") / "marchamp"


def test_state_dir_inside_a_library_root_is_refused(tmp_path):
    """The library is a synced Drive folder (data-model.md § Configuration).

    Writing run state into it would break FR-001's read-only guarantee and hand the user's
    PDFs to a sync client, which is a data-loss bug rather than an untidy layout.
    """
    library = tmp_path / "Drive" / "Marvel Scans"
    library.mkdir(parents=True)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=library / "marchamp-state")
    with pytest.raises(StateDirectoryInsideLibrary) as exc:
        settings.check_state_dir(library)
    assert "marchamp-state" in str(exc.value) or "state" in str(exc.value)


def test_state_dir_equal_to_the_library_root_is_refused(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    settings = Settings(image_dir=None, catalog_path=None, state_dir=library)
    with pytest.raises(StateDirectoryInsideLibrary):
        settings.check_state_dir(library)


def test_state_dir_beside_a_library_root_is_allowed(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    settings.check_state_dir(library)  # does not raise


def test_a_library_root_inside_the_state_dir_is_also_refused(tmp_path):
    """The containment is symmetric, and the reverse nesting is the easier mistake.

    Pointing MARCHAMP_STATE_DIR at a parent of the library makes the library a subtree of
    app-owned storage, so the orphan sweep would be walking the user's scans.
    """
    state = tmp_path / "state"
    library = state / "scans"
    library.mkdir(parents=True)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=state)
    with pytest.raises(StateDirectoryInsideLibrary):
        settings.check_state_dir(library)


def test_upstream_is_one_host_with_explicit_timeouts_and_pacing():
    up = Settings(image_dir=None, catalog_path=None).upstream
    # The whole allowlist (FR-003, research R2).
    assert up.host == "marvelcdb.com"
    # FR-041: attributable and contactable, not merely unblocked.
    assert "marchamp" in up.user_agent.lower() and "http" in up.user_agent.lower()
    # FR-042, FR-043. MarvelCDB publishes no rate limit; its absence is not permission.
    assert up.max_retries == 2
    assert up.min_request_interval_s >= 1.0
    assert up.connect_timeout_s > 0 and up.read_timeout_s > 0


def test_new_ceilings_are_named_constants():
    limits = Settings(image_dir=None, catalog_path=None).limits
    # An upload is an untrusted binary bounded before Pillow sees it (FR-028, research R9).
    assert limits.upload_bytes == 64 * 1024 * 1024
    # Bounds one os.walk against a mistakenly named root such as "/" (research R13).
    assert limits.library_scan_files == 50_000


def test_002_settings_do_not_become_startup_requirements(monkeypatch):
    """FR-005 and SC-003a: assembly needs no environment variable at all."""
    for var in ("MARCHAMP_IMAGE_DIR", "MARCHAMP_CATALOG", "MARCHAMP_STATE_DIR"):
        monkeypatch.delenv(var, raising=False)
    settings = settings_from_env()
    assert settings.state_dir is not None
    # 001's two remain reportable problems, and remain only that.
    assert {p.kind for p in settings.problems()} == {"image_dir_unset", "catalog_unset"}
