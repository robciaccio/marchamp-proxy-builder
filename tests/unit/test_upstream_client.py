"""T030 — the only outbound path in the project (FR-003, FR-041, FR-042, FR-043).

Feature 001 made no outbound call and recorded that as deliberate so that this moment would
bring the constitution's egress clause back rather than inherit an N/A. It is in force here
for the first time, and every requirement in it is a MUST:

- **one allowlisted host.** Not a default, not a base URL someone can override — a request
  to any other host is refused before a socket is opened;
- **redirects are not followed.** A `3xx` is an error. Following one and re-validating is
  the alternative the clause permits, and refusing outright is strictly smaller: there is no
  documented feature here that needs a redirect;
- **loopback, link-local, and private ranges are denied after resolution.** The allowlist is
  a name and names resolve to addresses; checking only the name is checking nothing;
- **the pack code is validated twice before it reaches a URL** — against its shape, and
  against the pack index. It is the only user-influenced component of any URL this
  application builds.

And FR-041 to FR-043, which are conduct rather than security: an attributable `User-Agent`,
explicit timeouts, at most two retries honouring `Retry-After`, one request in flight, and
at least a second between requests. MarvelCDB publishes no rate limit; its absence is not
permission.

The clock and the sleep are injected throughout. Asserting pacing against a real clock would
mean a test suite that takes a second per request to prove it waits a second.
"""

from __future__ import annotations

import threading

import httpx
import pytest

from marchamp.config import UpstreamSettings
from marchamp.upstream.client import (
    MarvelCdbClient,
    UpstreamRefused,
    UpstreamUnavailable,
)

PACK_CODES = {"cap", "wsp", "core", "vision", "wonder_man"}


class FakeClock:
    """A monotonic clock that only moves when something sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def public_resolver(host: str) -> list[str]:
    """Stands in for DNS. `marvelcdb.com` really does resolve to a public address."""
    return ["104.21.0.1"]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_client(transport, clock, resolver=public_resolver, settings=None) -> MarvelCdbClient:
    return MarvelCdbClient(
        settings=settings or UpstreamSettings(),
        transport=transport,
        resolve=resolver,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


@pytest.fixture
def client(upstream_transport, clock) -> MarvelCdbClient:
    return make_client(upstream_transport, clock)


# ------------------------------------------------------------------ it works at all


def test_it_fetches_a_pack_index(client):
    entries = client.fetch_pack_index()
    assert any(e.code == "cap" for e in entries)
    assert all(set(vars(e)) == {"code", "name"} for e in entries)


def test_it_fetches_a_pack_listing(client):
    response = client.fetch_pack_cards("cap", known_pack_codes=PACK_CODES)
    assert response.status == 200
    assert response.cards and any(c.code == "03001a" for c in response.cards)
    assert response.last_modified
    assert response.max_age_s == 600


def test_a_conditional_request_that_is_still_fresh_returns_304_with_no_body(client):
    """Measured: `If-Modified-Since` against `cards/cap.json` returns 304 and 0 bytes."""
    first = client.fetch_pack_cards("cap", known_pack_codes=PACK_CODES)
    again = client.fetch_pack_cards(
        "cap", known_pack_codes=PACK_CODES, if_modified_since=first.last_modified
    )
    assert again.status == 304
    assert again.cards is None


# ------------------------------------------------------------------------- the allowlist


def test_no_request_reaches_a_host_other_than_marvelcdb(clock, upstream_transport):
    """The transport fails loudly on any other host, so this asserts the URL, not a mock."""
    settings = UpstreamSettings(host="example.com")
    client = make_client(upstream_transport, clock, settings=settings)
    with pytest.raises(UpstreamRefused, match="allowlist"):
        client.fetch_pack_index()


def test_the_scheme_cannot_be_downgraded(clock, upstream_transport):
    client = make_client(upstream_transport, clock, settings=UpstreamSettings(scheme="http"))
    with pytest.raises(UpstreamRefused):
        client.fetch_pack_index()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_an_error_rather_than_something_to_follow(clock, status):
    """Refusing is smaller than following-and-revalidating, and nothing here needs one."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, headers={"location": "https://evil.example/x"})
    )
    client = make_client(transport, clock)
    with pytest.raises(UpstreamRefused, match="redirect"):
        client.fetch_pack_index()


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "::1",
        "169.254.169.254",  # the cloud metadata endpoint the clause names
        "10.0.0.5",  # private
        "192.168.1.5",
        "172.16.0.9",
        "0.0.0.0",
    ],
)
def test_a_host_resolving_into_a_denied_range_is_refused(clock, upstream_transport, address):
    """The allowlist is a *name*, and names resolve to addresses.

    A DNS record for the allowlisted host pointing at 169.254.169.254 is the whole attack,
    and checking only the name catches none of it.
    """
    client = make_client(upstream_transport, clock, resolver=lambda host: [address])
    with pytest.raises(UpstreamRefused, match="address"):
        client.fetch_pack_index()


def test_one_public_address_among_denied_ones_is_still_refused(clock, upstream_transport):
    """`getaddrinfo` returns a list, and the connection may use any entry in it."""
    client = make_client(upstream_transport, clock, resolver=lambda h: ["104.21.0.1", "10.0.0.5"])
    with pytest.raises(UpstreamRefused, match="address"):
        client.fetch_pack_index()


def test_a_host_that_does_not_resolve_is_refused_not_attempted(clock, upstream_transport):
    def fails(host: str):
        raise OSError("Name or service not known")

    client = make_client(upstream_transport, clock, resolver=fails)
    with pytest.raises(UpstreamRefused):
        client.fetch_pack_index()


# --------------------------------------------------------------- the one user input


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "cap/../core", "CAP", "cap.json", "a" * 33, "", "cap core", "cap?x=1"],
)
def test_a_pack_code_that_is_not_the_documented_shape_never_reaches_a_url(client, hostile):
    with pytest.raises(UpstreamRefused, match="pack code"):
        client.fetch_pack_cards(hostile, known_pack_codes=PACK_CODES)


def test_a_well_shaped_pack_code_that_is_not_a_real_pack_is_also_refused(client):
    """Shape is not existence. Both checks happen before a URL is built (FR-003).

    Without the second, any well-formed string becomes a request, which is a way for a
    caller's bug to turn into traffic somebody else has to absorb.
    """
    with pytest.raises(UpstreamRefused, match="pack"):
        client.fetch_pack_cards("not_a_pack", known_pack_codes=PACK_CODES)


# ------------------------------------------------------------------------- conduct


def test_every_request_is_attributable(clock):
    """FR-041 — so the operator can contact rather than only block."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"code": "cap", "name": "Captain America"}])

    make_client(httpx.MockTransport(record), clock).fetch_pack_index()
    agent = seen[0].headers["user-agent"]
    assert "marchamp" in agent.lower()
    assert "http" in agent.lower()  # a contact address, not just a name


def test_timeouts_are_explicit(client):
    # httpx defaults to a timeout, but the clause requires it to be a decision.
    assert client.timeout.connect == UpstreamSettings().connect_timeout_s
    assert client.timeout.read == UpstreamSettings().read_timeout_s


def test_two_requests_are_never_less_than_a_second_apart(client, clock):
    client.fetch_pack_index()
    client.fetch_pack_cards("cap", known_pack_codes=PACK_CODES)
    assert clock.slept and sum(clock.slept) >= UpstreamSettings().min_request_interval_s


def test_a_request_after_a_long_gap_does_not_wait(client, clock):
    client.fetch_pack_index()
    clock.now += 60
    clock.slept.clear()
    client.fetch_pack_cards("cap", known_pack_codes=PACK_CODES)
    assert clock.slept == []


def test_only_one_request_is_in_flight_at_a_time(clock):
    """FR-043. Asserted by observing overlap rather than by trusting a lock exists."""
    concurrent, peak = 0, 0
    guard = threading.Lock()
    entered = threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        nonlocal concurrent, peak
        with guard:
            concurrent += 1
            peak = max(peak, concurrent)
        entered.set()
        # Long enough that a second thread would overlap if nothing prevented it.
        threading.Event().wait(0.05)
        with guard:
            concurrent -= 1
        return httpx.Response(200, json=[{"code": "cap", "name": "Captain America"}])

    client = make_client(httpx.MockTransport(slow), clock)
    threads = [threading.Thread(target=client.fetch_pack_index) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1


# ------------------------------------------------------------- retries and backoff


@pytest.mark.parametrize("status", [429, 503])
def test_a_throttled_request_is_retried_at_most_twice(clock, status):
    attempts = 0

    def throttle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status)

    client = make_client(httpx.MockTransport(throttle), clock)
    with pytest.raises(UpstreamUnavailable):
        client.fetch_pack_index()
    assert attempts == 1 + UpstreamSettings().max_retries


def test_retry_after_is_honoured_rather_than_the_default_backoff(clock):
    """A server saying how long to wait is the strongest signal available; use it."""
    attempts = 0

    def throttle(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, json=[{"code": "cap", "name": "Captain America"}])

    make_client(httpx.MockTransport(throttle), clock).fetch_pack_index()
    assert 7 in clock.slept


def test_an_absurd_retry_after_does_not_hang_the_request(clock):
    """A hostile or broken header must not become an unbounded wait inside a request."""

    def throttle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"retry-after": "86400"})

    client = make_client(httpx.MockTransport(throttle), clock)
    with pytest.raises(UpstreamUnavailable):
        client.fetch_pack_index()
    assert all(s <= 60 for s in clock.slept)


def test_a_retry_succeeding_returns_normally(clock):
    attempts = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, json=[{"code": "cap", "name": "Captain America"}])

    entries = make_client(httpx.MockTransport(flaky), clock).fetch_pack_index()
    assert entries[0].code == "cap"


@pytest.mark.parametrize("status", [400, 404, 418, 500])
def test_a_response_that_is_not_a_throttle_is_not_retried(clock, status):
    """Retrying a 404 is traffic that cannot succeed."""
    attempts = 0

    def fail(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status)

    client = make_client(httpx.MockTransport(fail), clock)
    with pytest.raises(UpstreamUnavailable):
        client.fetch_pack_index()
    assert attempts == 1


def test_a_response_that_is_not_json_fails_as_upstream_not_as_a_crash(clock):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text="<html>maintenance"))
    with pytest.raises(UpstreamUnavailable):
        make_client(transport, clock).fetch_pack_index()


def test_no_credential_is_ever_sent(clock):
    """FR-003 — there are none to send, and this asserts that stays true."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"code": "cap", "name": "Captain America"}])

    make_client(httpx.MockTransport(record), clock).fetch_pack_index()
    headers = {k.lower() for k in seen[0].headers}
    assert not headers & {"authorization", "cookie", "x-api-key", "proxy-authorization"}


def test_no_image_is_ever_requested(client):
    """FR-002 — identity and quantity come from upstream; images never do."""
    client.fetch_pack_cards("cap", known_pack_codes=PACK_CODES)
    # The stub transport raises on any path outside the two documented endpoints, so
    # reaching here at all is the assertion; this states it for a reader.
    assert client.requested_paths == ["/api/public/cards/cap.json"]
