"""Runtime configuration (FR-005c3, FR-019b, FR-0A4)."""

from __future__ import annotations

import os
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
    return Settings(
        image_dir=Path(img).expanduser() if img else None,
        catalog_path=Path(cat).expanduser() if cat else None,
        host=os.environ.get("MARCHAMP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARCHAMP_PORT", "8765")),
    )
