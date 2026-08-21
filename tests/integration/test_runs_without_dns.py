"""The suite must not need DNS to talk to a stub (constitution egress gate, ASVS 13.2.5).

Every outbound request resolves the allowlisted host first, because a hostname allowlist
catches no SSRF on its own — a DNS record pointing `marvelcdb.com` at `169.254.169.254` is
the whole of the attack. That guard is right and stays.

What was wrong is that it ran even when the transport was a `MockTransport` and no packet
would leave the machine. So tests that make no network request still needed working DNS, and
a blip mid-run on 2026-08-20 failed six tests and errored dozens more, none of which touch
the network. The same suite would fail on a plane, or in an offline CI runner.

`conftest.offline_resolver` substitutes a fixed address for every non-`physical` test. This
file is the check on that: it makes name resolution fail outright, the way an offline machine
does, and drives a real run through the API anyway.

**The guard itself is not weakened, and two things prove it.** A test that passes `resolve=`
explicitly bypasses the substitution — which is how `test_egress.py` drives loopback,
link-local and private addresses through the real check. And `physical` tests are exempt, so
the paths that genuinely talk to MarvelCDB still resolve it for real.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings
from tests.conftest import ACCEPTANCE_HEROES

THOR_FOLDER = ACCEPTANCE_HEROES["thor"]


@pytest.fixture
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name resolution fails, exactly as it does with no network.

    `EAI_NONAME` is what macOS raised in the reported case: "nodename nor servname provided,
    or not known".
    """

    def refuse(*args: object, **kwargs: object):
        raise socket.gaierror(socket.EAI_NONAME, "nodename nor servname provided, or not known")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def client(tmp_path: Path, patched_upstream) -> TestClient:
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


def test_a_run_identifies_and_resolves_with_no_working_dns(client, scan_library, no_dns):
    """The whole point, end to end: a stubbed upstream needs no name server.

    Driven through the API rather than against the client directly, because the failure was
    not in the client — it was that every route which reaches upstream inherited a
    dependency nobody had noticed.
    """
    created = client.post(
        "/api/assemblies",
        json={"library_root": str(scan_library), "hero_folder": THOR_FOLDER},
    )
    assert created.status_code == 202, created.text
    run = created.json()
    assert run["identification"]["pack_code"] == "thor"

    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    assert confirmed.json()["unresolved"] == []


def test_the_address_guard_still_runs(no_dns):
    """The substitution must not have turned the check off, only made it deterministic.

    A resolver handed a denied address still refuses, which is the property the constitution
    requires and the reason the check exists at all.
    """
    from marchamp.config import UpstreamSettings
    from marchamp.upstream.client import MarvelCdbClient, UpstreamRefused

    with (
        MarvelCdbClient(UpstreamSettings(), resolve=lambda host: ["169.254.169.254"]) as client,
        pytest.raises(UpstreamRefused, match="denied"),
    ):
        client.fetch_pack_index()


def test_an_explicit_resolver_still_wins(no_dns):
    """`test_egress.py` depends on this: it injects addresses to exercise the real guard,
    and an autouse fixture that overrode explicit arguments would silently disarm it."""
    from marchamp.config import UpstreamSettings
    from marchamp.upstream.client import MarvelCdbClient

    with MarvelCdbClient(UpstreamSettings(), resolve=lambda host: ["203.0.113.7"]) as client:
        assert client._resolve("marvelcdb.com") == ["203.0.113.7"]
