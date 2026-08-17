#!/usr/bin/env python3
"""Derive `tests/fixtures/snapshots/` from MarvelCDB (FR-038a, research R1, R11).

The committed fixture carries only the fields data-model.md § PackCard lists. Card text,
flavour, traits, and `imagesrc` are dropped *here*, at the point of ingest, so they never
enter the repository — this repository is public and FR-038 forbids anything resembling a
mirror of FFG's card text.

The nested `linked_card` matters and is the trap: upstream sends the linked card's whole
record, text and all. It is flattened to a bare code, which is the only part face expansion
needs (data-model.md § Face).

    uv run python scripts/derive_snapshot_fixtures.py
    git add tests/fixtures/snapshots

Run rarely and deliberately. Re-running it against changed upstream data will change
`revision` in every test that pins one, which is the point of pinning them.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import httpx

BASE = "https://marvelcdb.com/api/public"

#: The ten acceptance heroes (SC-002, SC-003, SC-003c) plus the Core Set, which is where a
#: reprint's image comes from and so is fixture material in its own right (research R11).
#:
#: `vision` is here for one reason and it is not an acceptance hero: measured across the ten
#: heroes plus `core`, the only `double_sided` records are the Core Set's villain main
#: schemes, so nothing in that set is a double-sided *player* card. That leaves R12's second
#: face mechanism — and with it FR-015f, the bug where Intangible prints front-only and the
#: run still reports clean — with no fixture to assert against.
PACKS = (
    "cap",
    "stld",
    "wsp",
    "hlk",
    "thor",
    "bkw",
    "ant",
    "msm",
    "phoenix",
    "wonder_man",
    "core",
    "vision",
)

#: Exactly data-model.md § PackCard. Adding a name here is a spec change, not a tweak — see
#: plan.md § Artifact Update Rule.
RETAINED = (
    "code",
    "pack_code",
    "position",
    "name",
    "type_code",
    "card_set_type_name_code",
    "quantity",
    "double_sided",
    "linked_codes",
    "duplicate_of_code",
    "duplicated_by",
)

USER_AGENT = "marchamp-proxy-builder/0.1 (fixture derivation; +https://github.com/rsciaccio/marchamp-proxy-builder)"

#: Self-imposed, matching FR-043's runtime pacing. Eleven requests cost eleven seconds.
PACE_S = 1.0


def _linked_codes(raw: dict[str, Any]) -> list[str]:
    """Flatten the `linked_card` chain to codes, discarding everything else about them."""
    codes: list[str] = []
    node = raw.get("linked_card")
    seen: set[str] = set()
    while isinstance(node, dict):
        code = node.get("code")
        if not isinstance(code, str) or code in seen:
            break
        seen.add(code)
        codes.append(code)
        node = node.get("linked_card")
    return codes


def _duplicated_by(raw: dict[str, Any]) -> list[str]:
    """Upstream sends either codes or whole records here; keep codes."""
    out: list[str] = []
    for item in raw.get("duplicated_by") or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("code"), str):
            out.append(item["code"])
    return out


def reduce_card(raw: dict[str, Any]) -> dict[str, Any]:
    card = {
        "code": raw["code"],
        "pack_code": raw["pack_code"],
        "position": raw["position"],
        "name": raw["name"],
        "type_code": raw["type_code"],
        "card_set_type_name_code": raw.get("card_set_type_name_code"),
        "quantity": raw["quantity"],
        "double_sided": bool(raw.get("double_sided", False)),
        "linked_codes": _linked_codes(raw),
        "duplicate_of_code": raw.get("duplicate_of_code"),
        "duplicated_by": _duplicated_by(raw),
    }
    assert set(card) == set(RETAINED), "reduction drifted from data-model § PackCard"
    return card


def fetch(client: httpx.Client, path: str) -> Any:
    r = client.get(f"{BASE}/{path}")
    r.raise_for_status()
    return r.json()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "snapshots",
        help="where to write the reduced fixtures (default: tests/fixtures/snapshots)",
    )
    args = ap.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(10.0, connect=5.0),
        headers={"User-Agent": USER_AGENT},
    ) as client:
        index = [
            {"code": p["code"], "name": p["name"]}
            for p in sorted(fetch(client, "packs/"), key=lambda p: p["code"])
        ]
        (out / "packs.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
        print(f"packs.json: {len(index)} entries")

        for pack in PACKS:
            time.sleep(PACE_S)
            cards = [reduce_card(c) for c in fetch(client, f"cards/{pack}.json")]
            cards.sort(key=lambda c: (c["position"], c["code"]))
            (out / f"{pack}.json").write_text(json.dumps(cards, indent=2, sort_keys=True) + "\n")
            print(f"{pack}.json: {len(cards)} cards")

    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
