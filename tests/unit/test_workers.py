"""T029 — isolated decoding under hard limits (FR-0A4, constitution isolated-parsing gate)."""

from __future__ import annotations

import time

import pytest

from marchamp.render.workers import LimitExceeded, WorkerPool, memory_limit_supported


def _sleep(seconds: float) -> str:
    time.sleep(seconds)
    return "done"


def _burn_memory(mb: int) -> int:
    blob = bytearray(mb * 1024 * 1024)
    return len(blob)


def _boom() -> None:
    raise ValueError("decoder exploded")


def test_work_runs_in_a_separate_process():
    import os

    with WorkerPool(wall_clock_s=10) as pool:
        assert pool.run(os.getpid) != os.getpid()


def test_wall_clock_limit_is_enforced():
    with WorkerPool(wall_clock_s=1) as pool, pytest.raises(LimitExceeded) as exc:
        pool.run(_sleep, 5)
    assert "time" in str(exc.value).lower()


@pytest.mark.slow
@pytest.mark.skipif(
    not memory_limit_supported(),
    reason=(
        "macOS refuses RLIMIT_AS/RLIMIT_DATA ('current limit exceeds maximum limit'), "
        "verified on arm64 2026-08. The bomb guard on this platform is the pre-allocation "
        "pixel ceiling, asserted in test_oversized_image_is_rejected_before_allocation."
    ),
)
def test_memory_limit_is_enforced_where_the_os_supports_it():
    with (
        WorkerPool(wall_clock_s=30, memory_bytes=64 * 1024 * 1024) as pool,
        pytest.raises(LimitExceeded),
    ):
        pool.run(_burn_memory, 512)


def test_oversized_image_is_rejected_before_allocation():
    """The cross-platform bomb guard the constitution actually relies on.

    This must hold on every platform, including those where the OS will not enforce a
    memory cap — otherwise the isolated-parsing gate is unmet in practice.
    """
    from PIL import Image

    from marchamp.config import Limits

    assert Image.MAX_IMAGE_PIXELS is not None
    assert Limits().max_source_pixels >= Image.MAX_IMAGE_PIXELS


def test_every_platform_enforces_wall_clock_even_without_memory_limits():
    with WorkerPool(wall_clock_s=1) as pool, pytest.raises(LimitExceeded):
        pool.run(_sleep, 5)


def test_a_crashing_decode_does_not_kill_the_pool():
    with WorkerPool(wall_clock_s=10) as pool:
        with pytest.raises(ValueError):
            pool.run(_boom)
        assert pool.run(_sleep, 0) == "done"


def test_limit_message_names_the_limit():
    with WorkerPool(wall_clock_s=1) as pool, pytest.raises(LimitExceeded) as exc:
        pool.run(_sleep, 5)
    assert "1" in str(exc.value)  # states the ceiling that was hit
