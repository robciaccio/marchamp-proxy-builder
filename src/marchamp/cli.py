"""Command line entry point — `marchamp serve`.

Configuration problems are reported here, before the server starts, rather than left for
the user to discover as an empty deck list. FR-019b's distinction is the point: "you have
not set this yet" and "you set it to somewhere that does not exist" are different mistakes
with different fixes, and a blank page tells you neither.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from marchamp.config import Settings, settings_from_env


def _report(settings: Settings, stream) -> bool:
    """Print what is wrong, if anything. True when the service is usable."""
    problems = settings.problems()
    if not problems:
        return True
    print("Cannot start — the application is not configured yet:\n", file=stream)
    for problem in problems:
        print(f"  • {problem.detail}", file=stream)
    print(
        "\nSet both, then run again:\n"
        '  export MARCHAMP_IMAGE_DIR="/path/to/card-images"\n'
        '  export MARCHAMP_CATALOG="/path/to/catalog.json"',
        file=stream,
    )
    return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marchamp",
        description="Assemble print-ready proxy sheets for Marvel Champions, locally.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    serve = subcommands.add_parser("serve", help="Serve the wizard and API on 127.0.0.1.")
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on. Defaults to MARCHAMP_PORT, or 8765.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "serve":  # pragma: no cover - argparse rejects anything else
        return 2

    settings = settings_from_env()
    if args.port is not None:
        # The host is deliberately not exposed: Settings refuses a non-loopback address, so
        # offering a --host flag would only offer a way to be told no (FR-0A2).
        settings = Settings(
            image_dir=settings.image_dir,
            catalog_path=settings.catalog_path,
            host=settings.host,
            port=args.port,
            limits=settings.limits,
        )

    if not _report(settings, sys.stderr):
        return 1

    import uvicorn

    from marchamp.api.app import create_app

    print(f"Marchamp is at http://{settings.host}:{settings.port}", file=sys.stderr)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
