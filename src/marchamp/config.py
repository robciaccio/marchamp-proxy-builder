"""Runtime configuration (FR-005, FR-005c3, FR-019b, FR-0A4)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class Limits:
    """FR-0A4 ceilings.

    Set against a contemporary consumer laptop: far above real decks (~41 cards, ~3 MP
    scans) and far below anything that would destabilise the machine. Expected to be tuned
    from observation rather than treated as sacred.
    """

    decode_wall_clock_s: int = 10
    decode_memory_bytes: int = 512 * 1024 * 1024
    max_source_pixels: int = 80_000_000
    max_faces_per_generation: int = 200
    generation_wall_clock_s: int = 120

    # Feature 002. An upload is an untrusted binary and is streamed to a temporary file
    # under this ceiling *before* decode, so a hostile file is bounded before Pillow sees
    # it (FR-028, research R9). A real 600-DPI card scan is 2-6 MB, so this is generous by
    # an order of magnitude and still far below anything that fills a disk.
    upload_bytes: int = 64 * 1024 * 1024
    # Bounds one `os.walk` against a mistakenly named root such as `/`. The real library
    # holds ~4,447 images, so this leaves an order of magnitude of headroom (research R13).
    library_scan_files: int = 50_000


@dataclass(frozen=True)
class UpstreamSettings:
    """The whole of the egress allowlist, and the conduct it is exercised with.

    Every field here answers a MUST: one host (FR-003), an attributable `User-Agent`
    (FR-041), explicit timeouts and bounded retries (FR-042), and pacing (FR-043).
    MarvelCDB publishes no rate limit, and its absence is not permission — the figures are
    self-imposed and stated here rather than left to inference. An assembly makes a handful
    of requests — seven for `cap`, measured — so a one-second floor costs nothing.
    """

    host: str = "marvelcdb.com"
    scheme: str = "https"
    user_agent: str = (
        "marchamp-proxy-builder/0.1 (+https://github.com/rsciaccio/marchamp-proxy-builder)"
    )
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 10.0
    max_retries: int = 2
    backoff_base_s: float = 1.0
    backoff_jitter_s: float = 0.25
    min_request_interval_s: float = 1.0
    #: `cache-control: max-age=600` was measured, but a response without one still needs a
    #: freshness window, and defaulting to zero would mean a request per resolve pass.
    default_max_age_s: int = 600


class StateDirectoryInsideLibrary(ValueError):
    """The state directory and a named library root overlap.

    Not a tidiness complaint. The library is a synced Drive folder: run records and PDFs
    written into it are handed to a sync client, and FR-001 promises the library is never
    written to at all.
    """


def default_state_dir(
    platform: str | None = None, environ: Mapping[str, str] | None = None
) -> Path:
    """The platform data directory (data-model.md § Configuration).

    Takes the platform and environment as arguments rather than reading them, so the branch
    that does not match the running machine is still reachable from a test.
    """
    platform = platform if platform is not None else sys.platform
    environ = environ if environ is not None else os.environ
    home = Path(environ.get("HOME") or Path.home())
    if platform.startswith("darwin"):
        return home / "Library" / "Application Support" / "marchamp"
    xdg = environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "marchamp"


@dataclass(frozen=True)
class ConfigProblem:
    kind: str
    detail: str


@dataclass(frozen=True)
class Settings:
    image_dir: Path | None
    catalog_path: Path | None
    host: str = "127.0.0.1"
    port: int = 8765
    limits: Limits = field(default_factory=Limits)
    # Feature 002. Unlike the two above it, this always has a value: FR-005 forbids
    # refusing to start because a location is unset, and SC-003a requires an assembly with
    # no environment variable set at all, so there is nothing for the user to configure
    # before the feature works.
    state_dir: Path = field(default_factory=default_state_dir)
    upstream: UpstreamSettings = field(default_factory=UpstreamSettings)

    def check_state_dir(self, library_root: Path) -> None:
        """Refuse a state directory that overlaps the library the run just named.

        Checked per run rather than at startup, because the library root is named per run
        (FR-005) and so cannot be known when the settings are built. Symmetric on purpose:
        the state directory sitting inside the library is the documented hazard, and the
        library sitting inside the state directory is the easier mistake to make.
        """
        state = Path(self.state_dir).expanduser().resolve()
        library = Path(library_root).expanduser().resolve()
        if state == library or library in state.parents or state in library.parents:
            raise StateDirectoryInsideLibrary(
                f"the state directory ({state}) and the library root ({library}) overlap. "
                "The library is read-only source material and is very likely a synced "
                "folder; set MARCHAMP_STATE_DIR somewhere outside it."
            )

    def __post_init__(self) -> None:
        if self.host not in LOOPBACK_HOSTS:
            # FR-0A2: staying private must not depend on a firewall or a reverse proxy.
            raise ValueError(
                f"host must be a loopback address, got {self.host!r}. "
                "Binding to an externally reachable address is a defect, not an option."
            )

    def problems(self) -> list[ConfigProblem]:
        """Distinguish 'not configured yet' from 'configured but wrong' (FR-019b)."""
        out: list[ConfigProblem] = []
        if self.image_dir is None:
            out.append(
                ConfigProblem(
                    "image_dir_unset",
                    "No card image directory configured. Set MARCHAMP_IMAGE_DIR to the "
                    "folder holding your card images.",
                )
            )
        elif not self.image_dir.is_dir():
            out.append(
                ConfigProblem(
                    "image_dir_missing",
                    f"Card image directory {self.image_dir.name!r} does not exist or is not "
                    "a directory. Check MARCHAMP_IMAGE_DIR points at the right folder.",
                )
            )

        if self.catalog_path is None:
            out.append(
                ConfigProblem(
                    "catalog_unset",
                    "No catalog configured. Set MARCHAMP_CATALOG to your catalog file.",
                )
            )
        elif not self.catalog_path.is_file():
            out.append(
                ConfigProblem(
                    "catalog_missing",
                    f"Catalog file {self.catalog_path.name!r} does not exist. Check "
                    "MARCHAMP_CATALOG points at the right file.",
                )
            )
        return out


def settings_from_env() -> Settings:
    img = os.environ.get("MARCHAMP_IMAGE_DIR")
    cat = os.environ.get("MARCHAMP_CATALOG")
    state = os.environ.get("MARCHAMP_STATE_DIR")
    return Settings(
        image_dir=Path(img).expanduser() if img else None,
        catalog_path=Path(cat).expanduser() if cat else None,
        host=os.environ.get("MARCHAMP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARCHAMP_PORT", "8765")),
        state_dir=Path(state).expanduser() if state else default_state_dir(),
    )
