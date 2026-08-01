"""Isolated decoding with hard limits (FR-0A4).

Image decoders are the most vulnerability-dense dependency this project takes on, and the
TIFFs are third-party files rather than the user's own work. Decoding inline would mean a
malformed image can take down the application and a decompression bomb can exhaust the
machine, with no memory ceiling available in-process.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import multiprocessing as mp
import resource
import sys
from collections.abc import Callable
from typing import Any

from marchamp.config import Limits


class LimitExceeded(Exception):
    """A generation hit one of the FR-0A4 ceilings."""


def memory_limit_supported() -> bool:
    """Whether this platform actually enforces an address-space cap.

    Measured, not assumed: on macOS (verified on arm64, 2026-08) both RLIMIT_AS and
    RLIMIT_DATA are refused with "current limit exceeds maximum limit", so a child can
    allocate freely no matter what we ask for. Linux enforces both.

    This matters because the constitution requires hard memory limits on parsing. Where the
    OS will not provide one, the guard is the pixel ceiling in render.images, which rejects
    a decompression bomb *before* allocation rather than after — see MEMORY_GUARD_NOTE.
    """
    return sys.platform.startswith("linux")


MEMORY_GUARD_NOTE = (
    "On platforms without an enforceable address-space limit, protection against oversized "
    "images comes from the pixel ceiling applied at decode time (render.images), which "
    "rejects the image before memory is allocated, plus the wall-clock timeout."
)


def _apply_rlimits(memory_bytes: int | None, cpu_seconds: int | None) -> None:
    """Runs in the child, before any work."""
    if memory_bytes:
        for which in ("RLIMIT_AS", "RLIMIT_DATA"):
            limit = getattr(resource, which, None)
            if limit is not None:
                # Expected to fail on macOS. Deliberately not fatal: the wall-clock timeout
                # and the pre-allocation pixel ceiling still apply. See MEMORY_GUARD_NOTE.
                with contextlib.suppress(ValueError, OSError):
                    resource.setrlimit(limit, (memory_bytes, memory_bytes))
    if cpu_seconds:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


class WorkerPool:
    """Runs decode and render work in a separate, resource-capped process."""

    def __init__(
        self,
        wall_clock_s: int | None = None,
        memory_bytes: int | None = None,
        cpu_seconds: int | None = None,
        max_workers: int = 1,
    ) -> None:
        limits = Limits()
        self._wall_clock_s = (
            wall_clock_s if wall_clock_s is not None else limits.decode_wall_clock_s
        )
        self._memory_bytes = (
            memory_bytes if memory_bytes is not None else limits.decode_memory_bytes
        )
        self._cpu_seconds = cpu_seconds if cpu_seconds is not None else limits.decode_wall_clock_s
        self._max_workers = max_workers
        self._pool: concurrent.futures.ProcessPoolExecutor | None = None

    def __enter__(self) -> WorkerPool:
        ctx = mp.get_context("spawn")  # never fork: inherited state makes runs non-deterministic
        self._pool = concurrent.futures.ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=ctx,
            initializer=_apply_rlimits,
            initargs=(self._memory_bytes, self._cpu_seconds),
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None

    def run(self, fn: Callable[..., Any], *args: Any) -> Any:
        if self._pool is None:
            raise RuntimeError("WorkerPool must be used as a context manager")
        future = self._pool.submit(fn, *args)
        try:
            return future.result(timeout=self._wall_clock_s)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise LimitExceeded(
                f"exceeded the {self._wall_clock_s}s wall-clock time limit"
            ) from exc
        except MemoryError as exc:
            raise LimitExceeded(
                f"exceeded the {self._memory_bytes // (1024 * 1024)}MB memory limit"
            ) from exc
        except concurrent.futures.process.BrokenProcessPool as exc:
            # A child killed by the kernel for overrunning a resource limit surfaces here.
            self.__exit__()
            self.__enter__()
            raise LimitExceeded(
                f"worker died, most likely exceeding the "
                f"{self._memory_bytes // (1024 * 1024)}MB memory limit"
            ) from exc


if sys.platform == "win32":  # pragma: no cover - unsupported target
    raise ImportError("resource limits are POSIX-only; this application targets macOS and Linux")
