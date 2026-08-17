#!/usr/bin/env python3
"""Derive `tests/fixtures/library/` from the real scan library (FR-038a, research R11).

What crosses from the real library into the repository is **filenames and folder layout**
and nothing else. Every image this writes is generated here, in this process, from a solid
fill — no source file is ever opened, let alone copied. That is not a convention to be
polite about: FR-038a forbids committing card art, the repository is public, and the only
reason a fixture derived this way is legal at all is that a filename is not artwork.

Run it on the machine that has the library mounted, then commit the output:

    uv run python scripts/derive_library_fixture.py --library-root "/path/to/library"
    git add tests/fixtures/library

The resolver under test matches on positions and names, never on pixels, so a fixture built
from generated fills exercises the real behaviour. What it must preserve verbatim is the
library's awkwardness — the three filename conventions, the typos, the missing positions,
the `.tif`/`.tiff` pairs, Ant-Man's duplicate position, Quincarrier filed under Wasp, and
both spellings of the decklist scan (`decklist` and `deck list`). Renaming anything on the
way through would quietly delete the test.

Operational note (research R13): BSD `find` does not traverse the Drive mount. `Path.rglob`
and `os.walk` do, which is why this script uses the former.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

#: The ten acceptance heroes (SC-002, SC-003, SC-003c). Matched against the *direct children*
#: of `Heros/`, which are `<alter ego>_<hero>` — so "Iceman" finds "Bobby Drake_Iceman"
#: without this script needing to know the alter ego. See `hero_key` for why the match is an
#: equality on a normalised key rather than the substring test this started as.
HEROES = (
    "Captain America",
    "Star-Lord",
    "Wasp",
    "Hulk",
    "Thor",
    "Black Widow",
    "Ant-Man",
    "Ms. Marvel",
    "Phoenix",
    "Wonder Man",
)

#: Non-hero folders that are fixture material in their own right. The Core Set holds the
#: other printing a reprint resolves to, and `Aspects/` holds the pack's extra aspect cards
#: — without them the reprint path and the whole-library search have nothing to find.
EXTRA_ROOTS = ("Core Set",)
ASPECTS_DIRNAME = "Aspects"

#: Hero folders live directly under this one. Restricting to its direct children is not
#: tidiness: `Expansion Campaings/Civil War/Resistance/1_Captain America` and
#: `Expansion Campaings/Agends of SHIELD/Black Widow` are *also* hero folders by name, and a
#: library-wide search silently derives two folders for one acceptance hero.
HEROS_DIRNAME = "Heros"

IMAGE_SUFFIXES = frozenset({".tif", ".tiff", ".jpg", ".jpeg", ".png"})

#: 780x1122 clears the 300 DPI floor on both axes at 63.5x88.9 mm (312 DPI), and keeps the
#: real scans' awkward property of being proportionally taller than a card, so CROP has
#: something to trim. Large enough to print, small enough that ~1,500 of them are a
#: reasonable thing to commit.
FIXTURE_W, FIXTURE_H = 780, 1122

#: A mistyped `--library-root` should stop rather than mirror a filesystem.
DEFAULT_FILE_CEILING = 20_000


#: The three colours a placeholder is allowed to contain. The guard test
#: (`test_no_image_fixture_is_a_real_scan`) admits at most 64 distinct colours as its proof
#: that an image was generated rather than scanned, so the count must not depend on how
#: Pillow happens to render text — see `write_placeholder`.
FILL = (18, 32, 84)
BAND = (220, 40, 40)
INK = (255, 255, 255)


def write_placeholder(path: Path, label: str, width: int, height: int) -> None:
    """Write one generated card face. Opens no source file, by construction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), FILL)
    d = ImageDraw.Draw(img)
    band = max(1, height // 40)
    # Edge bands, as in tests/conftest.py, so a test can detect how much CROP trimmed.
    d.rectangle([0, 0, width, band], fill=BAND)
    d.rectangle([0, height - band, width, height], fill=BAND)
    # The label is drawn through a hard-thresholded mask rather than straight onto the
    # image. Pillow 10.1 changed `load_default()` from a bitmap font to a FreeType one, so
    # `d.text(...)` now anti-aliases and smears a few hundred intermediate colours between
    # INK and FILL — which reads as a photograph to the FR-038a guard and fails it. A 1-bit
    # mask pins the output at exactly three colours whatever font Pillow supplies.
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).text((band, height // 2), label[:40], fill=255)
    img.paste(INK, (0, 0), mask.point(lambda v: 255 if v >= 128 else 0, mode="1"))
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        img.save(path, format="JPEG", quality=60, dpi=(300, 300))
    elif suffix == ".png":
        img.save(path, format="PNG")
    else:
        # LZW keeps a solid fill to a few KB; uncompressed would be 2.6 MB per file.
        img.save(path, format="TIFF", compression="tiff_lzw", dpi=(300, 300))


def hero_key(name: str) -> str:
    """Reduce a hero name or folder name to the key the two are compared on.

    Three things in the real library defeat a plain casefolded comparison, and all three are
    load-bearing — get any of them wrong and an acceptance hero derives no fixture at all:

    - The hero is the segment after the last `_` (`Kamala Khan_Ms.Marvel` → `Ms.Marvel`),
      except in the folders that carry no alter ego (`Maria Hill`, `Hercules (u)`).
    - A trailing parenthetical marks the scan's state, not the hero: `Jean Grey_Phoenix (u)`
      is Phoenix.
    - Spacing and punctuation are not observed. The library writes `Ms.Marvel` for "Ms.
      Marvel" and `Wonderman` for "Wonder Man", so the key drops every non-alphanumeric.

    Equality on this key — not a substring test — is what keeps `Hulk` off
    `Teddy Altman_Hulking` and off the `She-Hulk` scenario folder.
    """
    hero = name.rsplit("_", 1)[-1]
    hero = re.sub(r"\s*\([^)]*\)\s*$", "", hero)
    return re.sub(r"[^a-z0-9]+", "", hero.casefold())


def select_source_dirs(root: Path) -> list[Path]:
    """The hero folders, the Core Set, and every `Aspects/` subtree beneath either."""
    selected: list[Path] = []
    seen: set[Path] = set()

    def add(d: Path) -> None:
        if d.is_dir() and d not in seen:
            seen.add(d)
            selected.append(d)

    heros_dir = root / HEROS_DIRNAME
    if not heros_dir.is_dir():
        raise SystemExit(f"no {HEROS_DIRNAME}/ under {root} — is --library-root correct?")
    by_key: dict[str, list[Path]] = {}
    for d in heros_dir.iterdir():
        if d.is_dir():
            by_key.setdefault(hero_key(d.name), []).append(d)

    missing: list[str] = []
    for hero in HEROES:
        matches = by_key.get(hero_key(hero), [])
        if not matches:
            missing.append(hero)
            print(f"  ! no folder found for {hero!r}", file=sys.stderr)
        for d in matches:
            add(d)
    # A missing acceptance hero is a fixture that quietly cannot support T042's calibration
    # or T058's end-to-end run. Fail rather than write an incomplete library.
    if missing:
        raise SystemExit(
            f"{len(missing)} of {len(HEROES)} acceptance heroes have no folder under "
            f"{heros_dir}: {', '.join(missing)}"
        )

    for name in EXTRA_ROOTS:
        for d in root.rglob(name):
            add(d)

    # Aspects/ may sit outside the Core Set; take it wherever it is.
    for d in root.rglob(ASPECTS_DIRNAME):
        add(d)

    # Drop any directory nested inside another already selected, so its files are not
    # written twice under two different relative paths.
    tops: list[Path] = []
    for d in sorted(selected):
        if not any(parent in seen for parent in d.parents if parent != root):
            tops.append(d)
    return tops


def derive(root: Path, out: Path, ceiling: int, dry_run: bool) -> int:
    sources = select_source_dirs(root)
    if not sources:
        raise SystemExit(f"no fixture-worthy folders found under {root}")

    written = 0
    for src in sources:
        rel_dir = src.relative_to(root)
        files = sorted(p for p in src.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
        print(f"  {rel_dir}: {len(files)} images")
        for f in files:
            written += 1
            if written > ceiling:
                raise SystemExit(
                    f"stopped at {ceiling} files — is --library-root pointing at the "
                    f"right folder? Raise --file-ceiling if this is genuinely the library."
                )
            if dry_run:
                continue
            target = out / f.relative_to(root)
            # The stem is the label so a failing fixture is identifiable by eye. It is the
            # filename, which is what this fixture is *for*; no card data is involved.
            write_placeholder(target, f.stem, FIXTURE_W, FIXTURE_H)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--library-root",
        required=True,
        type=Path,
        help="the mounted scan library (the folder holding Heros/ and Core Set/)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "library",
        help="where to write the derived fixture (default: tests/fixtures/library)",
    )
    ap.add_argument("--file-ceiling", type=int, default=DEFAULT_FILE_CEILING)
    ap.add_argument("--dry-run", action="store_true", help="report what would be written")
    args = ap.parse_args(argv)

    root = args.library_root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"--library-root is not a directory: {root}")

    print(f"reading {root}")
    written = derive(root, args.out.resolve(), args.file_ceiling, args.dry_run)
    verb = "would write" if args.dry_run else "wrote"
    print(f"{verb} {written} generated placeholders to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
