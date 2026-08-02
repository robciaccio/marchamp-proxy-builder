"""The entry point `pyproject.toml` promises and quickstart.md documents.

`[project.scripts]` has declared `marchamp = "marchamp.cli:main"` since T002, and the
module did not exist — so `uv run marchamp serve`, the one command the quickstart tells a
user to run, failed with an import error. These tests exist so it cannot silently go
missing again.
"""

from __future__ import annotations

import pytest

from marchamp import cli
from marchamp.config import Settings


def test_the_declared_entry_point_is_importable_and_callable():
    # What was actually broken: the console script pointed at a module that did not exist.
    import importlib
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())
    module_name, _, attribute = pyproject["project"]["scripts"]["marchamp"].partition(":")
    assert callable(getattr(importlib.import_module(module_name), attribute))


def test_serve_refuses_and_explains_when_nothing_is_configured(monkeypatch, capsys):
    # FR-019b — "not set yet" must not present as an empty deck list.
    monkeypatch.delenv("MARCHAMP_IMAGE_DIR", raising=False)
    monkeypatch.delenv("MARCHAMP_CATALOG", raising=False)

    assert cli.main(["serve"]) == 1
    err = capsys.readouterr().err
    assert "not configured" in err
    assert "MARCHAMP_IMAGE_DIR" in err and "MARCHAMP_CATALOG" in err


def test_serve_distinguishes_a_wrong_path_from_an_unset_one(monkeypatch, capsys, tmp_path):
    # The two mistakes have different fixes, so they must not read the same — including in
    # the headline. Telling someone who mistyped a path that they have configured nothing
    # sends them to fix the wrong thing.
    monkeypatch.setenv("MARCHAMP_IMAGE_DIR", str(tmp_path / "nowhere"))
    monkeypatch.setenv("MARCHAMP_CATALOG", str(tmp_path / "absent.json"))

    assert cli.main(["serve"]) == 1
    err = capsys.readouterr().err
    assert "points at something that is not there" in err
    assert "not configured yet" not in err
    assert "does not exist" in err
    assert "No card image directory configured" not in err
    # Nothing is unset, so the "export these" hint would be misleading advice.
    assert "export MARCHAMP_IMAGE_DIR" not in err


def test_serve_names_the_one_setting_that_is_missing(monkeypatch, capsys, image_dir, tmp_path):
    # One set correctly, one pointing nowhere: the report must not flatten to either
    # extreme, and must still name both the good news and the bad.
    monkeypatch.setenv("MARCHAMP_IMAGE_DIR", str(image_dir))
    monkeypatch.delenv("MARCHAMP_CATALOG", raising=False)

    assert cli.main(["serve"]) == 1
    err = capsys.readouterr().err
    assert "not configured yet" in err
    # Exactly one problem is reported: the catalog. The image directory is fine and must
    # not be listed as though it were also wrong.
    assert [line for line in err.splitlines() if line.startswith("  •")] == [
        "  • No catalog configured. Set MARCHAMP_CATALOG to your catalog file."
    ]


def test_serve_starts_the_app_when_configured(monkeypatch, image_dir, catalog_path):
    monkeypatch.setenv("MARCHAMP_IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("MARCHAMP_CATALOG", str(catalog_path))

    served: dict = {}

    def fake_run(app, host, port):
        served["app"], served["host"], served["port"] = app, host, port

    monkeypatch.setattr("uvicorn.run", fake_run)
    assert cli.main(["serve", "--port", "8790"]) == 0
    assert served["host"] == "127.0.0.1"
    assert served["port"] == 8790
    # It really is the wizard plus the API, not a bare app.
    assert "/api/decks" in served["app"].openapi()["paths"]


def test_there_is_no_way_to_ask_for_a_public_address(monkeypatch, image_dir, catalog_path):
    # FR-0A2: staying private must not depend on remembering to omit a flag.
    monkeypatch.setenv("MARCHAMP_IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("MARCHAMP_CATALOG", str(catalog_path))
    with pytest.raises(SystemExit):
        cli.main(["serve", "--host", "0.0.0.0"])

    # And the setting itself refuses regardless of how it is reached.
    with pytest.raises(ValueError):
        Settings(image_dir=image_dir, catalog_path=catalog_path, host="0.0.0.0")
