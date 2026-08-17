"""Command line entry point — `marchamp serve`.

Configuration problems are reported here, before the server starts, rather than left for
the user to discover as an empty deck list. FR-019b's distinction is the point: "you have
not set this yet" and "you set it to somewhere that does not exist" are different mistakes
with different fixes, and a blank page tells you neither.

**Feature 002 changed what those problems mean.** They used to stop the server, because
`MARCHAMP_IMAGE_DIR` and `MARCHAMP_CATALOG` were the only way to reach any card at all.
Pack assembly names its library per run and needs neither, so FR-005 forbids refusing to
start over them and SC-003a requires an assembly with no environment variable set. They are
now reported as what they became: feature 001's deck list is unavailable, and the rest of
the application is not. Reporting them at all still matters — a user who *meant* to
configure 001 would otherwise meet an empty list with no explanation.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from marchamp.config import Settings, settings_from_env


def _report(settings: Settings, stream) -> bool:
    """Print what is wrong, if anything. True when feature 001's deck list is usable."""
    problems = settings.problems()
    if not problems:
        return True

    # FR-019b's distinction, kept in the headline and not only in the bullets: "you have
    # not set this yet" and "you set it to somewhere that is not there" are different
    # mistakes, and telling someone who mistyped a path that they have not configured
    # anything sends them to fix the wrong thing.
    unset = [p for p in problems if p.kind.endswith("_unset")]
    if len(unset) == len(problems):
        headline = "The prebuilt deck list is not configured yet:"
    elif not unset:
        headline = "The prebuilt deck list points at something that is not there:"
    else:
        headline = "The prebuilt deck list is configured incompletely:"

    print(f"{headline}\n", file=stream)
    for problem in problems:
        print(f"  • {problem.detail}", file=stream)
    if unset:
        print(
            "\nSet both to use it:\n"
            '  export MARCHAMP_IMAGE_DIR="/path/to/card-images"\n'
            '  export MARCHAMP_CATALOG="/path/to/catalog.json"',
            file=stream,
        )
    # Pack assembly names its library per run, so it is unaffected. Said out loud because
    # the paragraph above otherwise reads as though nothing works.
    print("\nPack assembly needs neither and is available.", file=stream)
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
            state_dir=settings.state_dir,
            upstream=settings.upstream,
        )

    # Reported, never fatal (FR-005, SC-003a). The return value is deliberately ignored
    # here rather than deleted: `_report` still distinguishes the two mistakes, and the
    # boolean is what a caller that genuinely needs 001's catalog would branch on.
    _report(settings, sys.stderr)

    import uvicorn

    from marchamp.api.app import create_app

    print(f"Marchamp is at http://{settings.host}:{settings.port}", file=sys.stderr)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
