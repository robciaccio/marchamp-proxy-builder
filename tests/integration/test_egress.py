"""T112 — the one outbound path, held to the constitution's egress clause.

**A host allowlist alone cannot discharge FR-002.** MarvelCDB serves card art from
`marvelcdb.com`, the same host the card data comes from, so "every request went to the
allowlisted host" is satisfied exactly as well by a client that downloaded 34 card images as
by one that downloaded a JSON listing. That is why the assertions below are about *paths* and
about what was done with the bodies, not only about hosts.

So this module serves a deliberately hostile version of upstream: every card record carries
the `imagesrc` field the real API returns, pointing at an image on the allowlisted host, plus
the card text and flavour that FR-038a forbids retaining. A client that widened its reduction,
or a resolver that reached for the URL it was handed, both show up here — the first as a field
in a captured snapshot, the second as a request for a `.png`.

The remaining four are the clause's other MUSTs, each asserted against the mechanism rather
than the intention: a redirect raises instead of being followed, a host resolving into a
denied range is refused *after* resolution rather than by name, and the `User-Agent` names
the application so a volunteer-run service can attribute the traffic (FR-041).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from marchamp.api.app import create_app
from marchamp.config import Settings, UpstreamSettings
from marchamp.upstream.client import MarvelCdbClient, UpstreamRefused
from tests.conftest import (
    ACCEPTANCE_HEROES,
    SNAPSHOT_FIXTURES,
    UPSTREAM_LAST_MODIFIED,
    UPSTREAM_MAX_AGE,
    UnstubbedRequest,
)

THOR_FOLDER = ACCEPTANCE_HEROES["thor"]

#: The three endpoints research R4 settled on, and the only paths any URL may have.
ALLOWED_PATH_PREFIXES = ("/api/public/packs/", "/api/public/cards/", "/api/public/card/")

#: What the real API returns alongside the fields this feature keeps. `imagesrc` is the one
#: that matters — it is a working URL to the card's artwork on the allowlisted host, which is
#: precisely why the host check cannot be the whole guarantee (FR-002, FR-038a).
UPSTREAM_EXTRAS = {
    "imagesrc": "/bundles/cards/{code}.png",
    "backimagesrc": "/bundles/cards/{code}.back.png",
    "text": "Card text this application must not retain.",
    "flavor": "Flavour text, likewise.",
    "illustrator": "An Artist",
    "url": "https://marvelcdb.com/card/{code}",
}


class RecordingUpstream:
    """MarvelCDB as it really answers, with every request written down."""

    def __init__(self) -> None:
        #: `(host, path)` for every request, in order.
        self.requests: list[tuple[str, str]] = []
        self.user_agents: list[str] = []
        self.redirect_paths: set[str] = set()

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def _decorate(self, records: list[dict]) -> list[dict]:
        out = []
        for raw in records:
            enriched = dict(raw)
            enriched.update(
                {k: v.format(code=raw.get("code", "")) for k, v in UPSTREAM_EXTRAS.items()}
            )
            out.append(enriched)
        return out

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.url.host, request.url.path))
        self.user_agents.append(request.headers.get("user-agent", ""))
        path = request.url.path

        if path in self.redirect_paths:
            return httpx.Response(
                302, headers={"location": "https://elsewhere.example/api/public/packs/"}
            )

        headers = {
            "cache-control": f"max-age={UPSTREAM_MAX_AGE}, public",
            "last-modified": UPSTREAM_LAST_MODIFIED,
            "content-type": "application/json",
        }
        if path == "/api/public/packs/":
            return httpx.Response(
                200,
                json=json.loads((SNAPSHOT_FIXTURES / "packs.json").read_text()),
                headers=headers,
            )
        if path.startswith("/api/public/cards/") and path.endswith(".json"):
            pack = path.removeprefix("/api/public/cards/").removesuffix(".json")
            fixture = SNAPSHOT_FIXTURES / f"{pack}.json"
            if not fixture.is_file():
                return httpx.Response(404, json={"error": "no such pack"}, headers=headers)
            return httpx.Response(
                200, json=self._decorate(json.loads(fixture.read_text())), headers=headers
            )
        if path.startswith("/api/public/card/") and path.endswith(".json"):
            code = path.removeprefix("/api/public/card/").removesuffix(".json")
            for fixture in sorted(SNAPSHOT_FIXTURES.glob("*.json")):
                if fixture.stem == "packs":
                    continue
                for raw in json.loads(fixture.read_text()):
                    if raw.get("code") == code:
                        return httpx.Response(
                            200,
                            json={"code": code, "pack_code": fixture.stem, **UPSTREAM_EXTRAS},
                            headers=headers,
                        )
            return httpx.Response(404, json={"error": "no such card"}, headers=headers)

        # Reached only by a client asking for something outside the three endpoints — an
        # image, most plausibly. Loud rather than 404, so it names the URL.
        raise UnstubbedRequest(f"unallowlisted path {path}")


@pytest.fixture
def upstream() -> RecordingUpstream:
    return RecordingUpstream()


@pytest.fixture
def client(tmp_path: Path, upstream: RecordingUpstream, monkeypatch) -> TestClient:
    original = MarvelCdbClient.__init__

    def with_transport(self, settings, transport=None):
        original(self, settings, transport=transport or upstream.transport)

    monkeypatch.setattr(MarvelCdbClient, "__init__", with_transport)
    settings = Settings(image_dir=None, catalog_path=None, state_dir=tmp_path / "state")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def rendered(client, writable_library) -> dict:
    """A whole thor run, so the assertions cover every request an assembly makes."""
    created = client.post(
        "/api/assemblies",
        json={"library_root": str(writable_library), "hero_folder": THOR_FOLDER},
    )
    assert created.status_code == 202, created.text
    run = created.json()
    confirmed = client.post(
        f"/api/assemblies/{run['id']}/pack",
        json={"action": "confirm"},
        headers={"If-Match": str(run["version"])},
    )
    assert confirmed.status_code == 202, confirmed.text
    run = confirmed.json()
    if run["decklist_candidate"] is not None:
        run = client.post(
            f"/api/assemblies/{run['id']}/decklist",
            json={"action": "confirm"},
            headers={"If-Match": str(run["version"])},
        ).json()
    done = client.post(
        f"/api/assemblies/{run['id']}/confirmation",
        json={},
        headers={"If-Match": str(run["version"])},
    )
    assert done.status_code == 202, done.text
    return done.json()


# ----------------------------------------------------------------- where requests went


def test_no_request_reaches_any_host_but_marvelcdb(rendered, upstream):
    """FR-003, constitution egress gate. The floor, not the guarantee."""
    assert upstream.requests, "the run made no request at all, so this asserts nothing"
    assert {host for host, _ in upstream.requests} == {"marvelcdb.com"}


def test_every_request_path_is_one_of_the_three_allowlisted_endpoints(rendered, upstream):
    """FR-040, research R4 — and, with the next test, the whole of FR-002.

    `GET /api/public/cards/` without a pack code is a mirror of the database in all but name
    and is refused by FR-040; anything under `/bundles/` is card art. Both are on the
    allowlisted host, so only the path distinguishes them.
    """
    for _host, path in upstream.requests:
        assert path.startswith(ALLOWED_PATH_PREFIXES), path
        assert path == "/api/public/packs/" or path.endswith(".json"), path
        assert path != "/api/public/cards/", (
            "the whole-database endpoint is refused by FR-040 even though it is one request"
        )


def test_no_response_body_is_consumed_as_image_bytes(rendered, upstream):
    """FR-002 — card *images* come from the user's library, never from upstream.

    Asserted from both ends. No request ever asked for an image, and every face in the
    finished report was sourced from the library or from a file the user supplied. The
    second half is what makes the first half mean something: a resolver that fetched art
    would have to record it as coming from somewhere, and there is nowhere for it to say.
    """
    for _host, path in upstream.requests:
        assert not path.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff"))
        assert "/bundles/" not in path

    sources = {r["source"] for r in rendered["report"]["resolutions"]}
    assert sources, "the report resolved nothing, so this asserts nothing"
    assert sources <= {"library", "upload"}


def test_imagesrc_is_absent_from_every_captured_snapshot(rendered, tmp_path):
    """FR-038a — the reduction is real, not a convention the fixtures happen to follow.

    Upstream served `imagesrc` on every card in this module. What lands on disk is checked
    field by field rather than by searching the text, so a snapshot that kept the URL under
    a different key fails here too.
    """
    snapshots = sorted((tmp_path / "state" / "snapshots").glob("*.json"))
    assert snapshots, "no snapshot was captured, so this asserts nothing"

    for path in snapshots:
        payload = json.loads(path.read_text())
        if "cards" not in payload:  # the pack index, which carries only code and name
            continue
        assert payload["cards"], path.name
        for card in payload["cards"]:
            for forbidden in UPSTREAM_EXTRAS:
                assert forbidden not in card, f"{path.name} retained {forbidden!r}"
        assert "imagesrc" not in path.read_text()


# --------------------------------------------------------------- how requests are made


def test_the_user_agent_names_the_application(rendered, upstream):
    """FR-041 — a volunteer-run service must be able to attribute the traffic."""
    assert upstream.user_agents
    for agent in upstream.user_agents:
        assert "marchamp-proxy-builder" in agent
        assert "github.com/" in agent, "an attributable agent needs somewhere to complain to"


def test_a_redirect_is_refused_rather_than_followed(upstream):
    """The constitution permits following one and re-validating; refusing is strictly smaller.

    The second assertion is the one worth having: a client that followed the hop would have
    left a request for `elsewhere.example` in the record even if it then rejected the
    response.
    """
    upstream.redirect_paths.add("/api/public/packs/")
    with (
        MarvelCdbClient(UpstreamSettings(), transport=upstream.transport) as client,
        pytest.raises(UpstreamRefused, match="redirect"),
    ):
        client.fetch_pack_index()

    assert {host for host, _ in upstream.requests} == {"marvelcdb.com"}


@pytest.mark.parametrize(
    ("address", "why"),
    [
        ("127.0.0.1", "loopback — the application's own services"),
        ("169.254.169.254", "link-local — the cloud metadata endpoint"),
        ("10.0.0.7", "private — something else on the user's network"),
        ("192.168.1.5", "private"),
        ("0.0.0.0", "unspecified"),
    ],
)
def test_a_host_resolving_into_a_denied_range_is_refused(upstream, address, why):
    """ASVS 13.2.5 — the name is allowlisted, so only the address can catch this.

    A DNS record for `marvelcdb.com` pointing at `169.254.169.254` is the whole of the SSRF
    this clause exists to stop, and a check on the hostname catches none of it.
    """
    with (
        MarvelCdbClient(
            UpstreamSettings(), transport=upstream.transport, resolve=lambda host: [address]
        ) as client,
        pytest.raises(UpstreamRefused, match="denied"),
    ):
        client.fetch_pack_index()

    assert upstream.requests == [], f"a request was issued to a {why} address"


def test_one_denied_address_among_several_is_enough_to_refuse(upstream):
    """Every entry, not the first: `getaddrinfo` returns a list and any of them may be used."""
    with (
        MarvelCdbClient(
            UpstreamSettings(),
            transport=upstream.transport,
            resolve=lambda host: ["93.184.216.34", "169.254.169.254"],
        ) as client,
        pytest.raises(UpstreamRefused, match="denied"),
    ):
        client.fetch_pack_index()
    assert upstream.requests == []


def test_a_settings_object_cannot_widen_the_allowlist(upstream):
    """The allowlist is a module constant, and this is what that buys.

    `UpstreamSettings.host` exists so the rest of the application can read the name. If the
    check were against *it*, the guarantee would be configuration, and a guarantee that
    configuration can widen is not a guarantee.
    """
    settings = UpstreamSettings(host="marvelcdb.com.attacker.example")
    with (
        MarvelCdbClient(settings, transport=upstream.transport) as client,
        pytest.raises(UpstreamRefused, match="allowlist"),
    ):
        client.fetch_pack_index()
    assert upstream.requests == []


def test_plain_http_is_refused(upstream):
    """The clause names TLS. Downgrading is a settings typo away otherwise."""
    with (
        MarvelCdbClient(UpstreamSettings(scheme="http"), transport=upstream.transport) as client,
        pytest.raises(UpstreamRefused, match="https"),
    ):
        client.fetch_pack_index()
    assert upstream.requests == []
