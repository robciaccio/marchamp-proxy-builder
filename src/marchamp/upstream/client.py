"""The only outbound path in the project (FR-003, FR-040–FR-043, research R1, R2).

Feature 001 made no network call and recorded that as deliberate, so that the constitution's
egress clause would come *into force* here rather than be inherited as an N/A. Every rule in
it applies to this module and nowhere else, which is the point of there being exactly one.

**One host, checked as a name and as an address.** The allowlist is a hostname, and hostnames
resolve to addresses; a DNS record for the allowlisted host pointing at `169.254.169.254` is
the whole of the SSRF attack the clause exists to stop, and checking only the name catches
none of it. So every request resolves the host first and refuses if *any* returned address
is loopback, link-local, private, or otherwise reserved — any, not the first, because the
connection may use any entry in the list.

**Redirects are errors.** The clause permits following one and re-validating the target;
refusing is strictly smaller and nothing here needs a redirect. A `3xx` therefore raises.

**The pack code is the only user-influenced part of any URL**, and it is checked twice before
one is built: against `^[a-z0-9_]{1,32}$`, and against the pack index. Shape is not
existence, and without the second check any well-formed string a caller mistakenly passes
becomes traffic somebody else has to absorb.

Conduct (FR-041–FR-043) is not security but is not optional either. MarvelCDB is a free
service run by volunteers and publishes no rate limit; its absence is not permission. One
request in flight, at least a second between them, at most two retries, and `Retry-After`
honoured when the server offers it — capped, because a hostile or broken header must not
become an unbounded wait inside a request.
"""

from __future__ import annotations

import ipaddress
import json
import random
import re
import socket
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field

import httpx

from marchamp.config import UpstreamSettings
from marchamp.upstream.models import (
    PackCard,
    PackIndexEntry,
    SnapshotInvalid,
    parse_pack_index,
    parse_snapshot_cards,
)

#: The same rule `store.layout` applies before a pack code becomes a filename. Stated in
#: both places deliberately: a URL and a path are different attack surfaces and neither
#: should depend on the other having checked.
PACK_CODE_RE = re.compile(r"^[a-z0-9_]{1,32}$")

#: A MarvelCDB card code: a two-digit pack ordinal, a position, and an optional face letter
#: — `03001a`, `01071`. Validated before it can become a URL, for the same reason a pack code
#: is: shape is checked at the boundary rather than trusted from a reprint link.
CARD_CODE_RE = re.compile(r"^[0-9]{4,8}[a-z]?$")

#: The allowlist, as a constant rather than as configuration. `UpstreamSettings.host`
#: records the same name so the rest of the application can read it, but the check below is
#: against *this* — a guarantee that a settings object can widen is not a guarantee, and the
#: constitution's clause is a MUST. Adding a host here is a deliberate, reviewable edit.
ALLOWED_HOSTS = frozenset({"marvelcdb.com"})

#: Statuses worth trying again. A 404 or a 500 is not — retrying either is traffic that
#: cannot succeed.
RETRYABLE = frozenset({429, 503})

#: However long `Retry-After` asks for, a request does not wait longer than this. A user is
#: sitting in front of a wizard; a day-long sleep inside a request is a hang.
MAX_RETRY_AFTER_S = 60.0

_MAX_AGE_RE = re.compile(r"max-age\s*=\s*(\d+)")


class UpstreamError(Exception):
    """Base for anything that went wrong talking to MarvelCDB."""


class UpstreamRefused(UpstreamError):
    """*This application* refused to make or accept the request.

    A policy decision, not a failure: a host outside the allowlist, a redirect, an address
    in a denied range, or a pack code that is not one. Distinct from `UpstreamUnavailable`
    because retrying cannot help and the user needs to hear something different.
    """


class UpstreamUnavailable(UpstreamError):
    """MarvelCDB could not be reached, or answered with something unusable.

    FR-046: the honest response is to refuse and name the pack, never to guess.
    """


class UpstreamNotFound(UpstreamUnavailable):
    """Upstream answered, and the answer is that there is no such thing.

    A subclass, so every caller that only cares about "this did not work" is unaffected. It
    exists for the one caller that cares about the difference: a 404 is a *definitive*
    answer worth remembering, where a timeout says nothing about the card and remembering it
    would turn one bad network moment into a permanent gap (FR-039, SC-006d).
    """


@dataclass
class UpstreamResponse:
    status: int
    #: `None` on a 304 — measured, a revalidation carries zero bytes.
    cards: list[PackCard] | None = None
    last_modified: str | None = None
    max_age_s: int | None = None
    warnings: list[str] = field(default_factory=list)


def _default_resolve(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


class MarvelCdbClient:
    """Every outbound request the application makes passes through here."""

    def __init__(
        self,
        settings: UpstreamSettings | None = None,
        transport: httpx.BaseTransport | None = None,
        resolve: Callable[[str], list[str]] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.settings = settings or UpstreamSettings()
        # Resolved at call time rather than bound as a default argument, matching
        # `monotonic` and `sleep` above. A default argument is captured when the function is
        # defined, so `_default_resolve` could not be substituted for a whole process — and
        # the suite needed real DNS to reach a `MockTransport` that answers without one.
        self._resolve = resolve if resolve is not None else _default_resolve
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self.timeout = httpx.Timeout(
            self.settings.read_timeout_s, connect=self.settings.connect_timeout_s
        )
        self._client = httpx.Client(
            transport=transport,
            # Not a preference: the constitution forbids following one, and httpx defaulting
            # this way means the guarantee does not depend on remembering to set it.
            follow_redirects=False,
            timeout=self.timeout,
            headers={"User-Agent": self.settings.user_agent, "Accept": "application/json"},
        )
        # One request in flight, and never two inside `min_request_interval_s` (FR-043).
        self._gate = threading.Lock()
        self._last_request_at: float | None = None
        #: Every path requested, in order. Cheap, and it makes "no image is ever fetched"
        #: assertable rather than merely intended (FR-002).
        self.requested_paths: list[str] = []

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MarvelCdbClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------- endpoints

    def fetch_pack_index(self) -> list[PackIndexEntry]:
        """`GET /api/public/packs/` — 61 entries, ~9 KB, reduced to code and name."""
        response = self._get("/api/public/packs/")
        try:
            return parse_pack_index(response.json())
        except (SnapshotInvalid, json.JSONDecodeError, ValueError) as exc:
            raise UpstreamUnavailable(f"the pack index was not usable: {exc}") from exc

    def fetch_pack_cards(
        self,
        pack_code: str,
        known_pack_codes: Collection[str],
        if_modified_since: str | None = None,
        known_pack_prefixes: set[str] | None = None,
    ) -> UpstreamResponse:
        """`GET /api/public/cards/{pack_code}.json` — the one bulk endpoint (FR-040).

        `GET /api/public/cards/` would return every card in one request and is simpler. It
        is refused by FR-040: it is a mirror of the whole database in all but name, and the
        spec is explicit that only packs actually being assembled are retrieved.
        """
        self._check_pack_code(pack_code, known_pack_codes)
        headers = {"If-Modified-Since": if_modified_since} if if_modified_since else None
        response = self._get(f"/api/public/cards/{pack_code}.json", headers=headers)

        last_modified = response.headers.get("last-modified")
        max_age = self._max_age(response.headers.get("cache-control"))
        if response.status_code == 304:
            return UpstreamResponse(304, last_modified=last_modified, max_age_s=max_age)

        try:
            cards, warnings = parse_snapshot_cards(
                response.json(), pack_code, known_pack_prefixes=known_pack_prefixes
            )
        except (SnapshotInvalid, json.JSONDecodeError, ValueError) as exc:
            # Aborts the capture and names the pack, rather than surfacing at print time.
            raise UpstreamUnavailable(f"pack {pack_code}: {exc}") from exc
        return UpstreamResponse(200, cards, last_modified, max_age, warnings)

    def fetch_card_pack_code(self, card_code: str) -> str | None:
        """`GET /api/public/card/{code}.json` — which pack one card belongs to.

        The third and last allowlisted endpoint (research R4). It exists for exactly one
        question: a reprint link points at a card code whose two-digit prefix maps to no pack
        this application has fetched, and the prefix→pack map cannot answer it.

        Only `pack_code` is read off the response. The rest of a card record is precisely the
        card text, flavour, traits and `imagesrc` that FR-038a forbids retaining, and the
        narrowest possible reading of the response is what keeps that guarantee cheap to
        verify.

        This is a per-*pack* cost, not a per-card one: the answer is cached with the
        snapshot the caller then fetches, so a pack referenced by six reprints costs one of
        these, not six (FR-040, SC-006d).
        """
        if not CARD_CODE_RE.match(card_code or ""):
            raise UpstreamRefused(
                f"card code {card_code!r} is not of the form {CARD_CODE_RE.pattern}, so no "
                "URL is built from it"
            )
        try:
            response = self._get(f"/api/public/card/{card_code}.json")
        except UpstreamNotFound:
            # Upstream knows nothing about this code. An answer, not a failure — the caller
            # stores it so the question is asked once rather than once per run.
            return None
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return None
        pack_code = payload.get("pack_code") if isinstance(payload, dict) else None
        return pack_code if isinstance(pack_code, str) and PACK_CODE_RE.match(pack_code) else None

    # ------------------------------------------------------------------ validation

    def _check_pack_code(self, pack_code: str, known: Collection[str]) -> None:
        if not isinstance(pack_code, str) or not PACK_CODE_RE.match(pack_code):
            raise UpstreamRefused(
                f"pack code {pack_code!r} is not of the form {PACK_CODE_RE.pattern}, so no "
                "URL is built from it"
            )
        if pack_code not in known:
            raise UpstreamRefused(
                f"pack code {pack_code!r} is not in the pack index. Shape is not existence, "
                "and an unknown code must not become a request."
            )

    def _check_destination(self) -> None:
        """Resolve the allowlisted host and refuse any denied address (ASVS 13.2.5)."""
        if self.settings.scheme != "https":
            raise UpstreamRefused(f"outbound requests must be https, not {self.settings.scheme!r}")
        try:
            addresses = self._resolve(self.settings.host)
        except OSError as exc:
            raise UpstreamRefused(f"{self.settings.host} did not resolve: {exc}") from exc
        if not addresses:
            raise UpstreamRefused(f"{self.settings.host} resolved to no addresses")

        for raw in addresses:
            address = ipaddress.ip_address(raw)
            # Every one of them, not the first: `getaddrinfo` returns a list and the
            # connection may use any entry in it.
            if (
                address.is_loopback
                or address.is_link_local
                or address.is_private
                or address.is_reserved
                or address.is_multicast
                or address.is_unspecified
            ):
                raise UpstreamRefused(
                    f"{self.settings.host} resolves to address {raw}, which is in a range "
                    "outbound requests are denied. Cloud metadata endpoints and internal "
                    "services live there."
                )

    # ------------------------------------------------------------------ the request

    def _get(self, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
        url = httpx.URL(f"{self.settings.scheme}://{self.settings.host}{path}")
        if url.host not in ALLOWED_HOSTS:
            raise UpstreamRefused(
                f"{url.host!r} is not on the allowlist {sorted(ALLOWED_HOSTS)}. The "
                "allowlist is a constant in this module, not configuration, so no settings "
                "value can widen it."
            )

        with self._gate:  # one request in flight (FR-043)
            self._check_destination()
            attempts = 0
            while True:
                self._pace()
                self.requested_paths.append(path)
                try:
                    response = self._client.get(url, headers=headers)
                except httpx.HTTPError as exc:
                    if attempts >= self.settings.max_retries:
                        raise UpstreamUnavailable(
                            f"could not reach {self.settings.host}: {exc}"
                        ) from exc
                    self._sleep(self._backoff(attempts, None))
                    attempts += 1
                    continue

                # 304 is inside httpx's redirect range but is not a hop — it is the
                # successful outcome of revalidation, and the whole of FR-039's saving.
                if response.status_code != 304 and response.is_redirect:
                    raise UpstreamRefused(
                        f"{path} answered {response.status_code}, a redirect. Redirects are "
                        "not followed, so this is an error rather than a hop."
                    )
                if response.status_code in RETRYABLE and attempts < self.settings.max_retries:
                    self._sleep(self._backoff(attempts, response.headers.get("retry-after")))
                    attempts += 1
                    continue
                if response.status_code == 404:
                    raise UpstreamNotFound(f"{self.settings.host}{path} answered 404")
                if response.status_code >= 400:
                    raise UpstreamUnavailable(
                        f"{self.settings.host}{path} answered {response.status_code}"
                    )
                return response

    def _pace(self) -> None:
        """At least `min_request_interval_s` between requests (FR-043).

        Self-imposed. An assembly makes a handful of requests — seven for `cap`, and none at
        all for a second run inside `max-age` — so the floor costs nothing and makes
        "conservative" a property a test can check rather than a claim.
        """
        now = self._monotonic()
        if self._last_request_at is not None:
            wait = self.settings.min_request_interval_s - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
                now = self._monotonic()
        self._last_request_at = now

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        """`Retry-After` when the server offers it, capped; exponential otherwise.

        A server saying how long to wait is the strongest signal available and overrides the
        guess — up to `MAX_RETRY_AFTER_S`, because a header asking for a day is either
        broken or hostile and either way must not hang the request.
        """
        if retry_after:
            try:
                return min(float(retry_after), MAX_RETRY_AFTER_S)
            except ValueError:
                pass  # an HTTP-date form; fall through to the computed backoff

        base = self.settings.backoff_base_s * (2**attempt)
        return base + random.uniform(0, self.settings.backoff_jitter_s)

    def _max_age(self, cache_control: str | None) -> int | None:
        if not cache_control:
            return self.settings.default_max_age_s
        match = _MAX_AGE_RE.search(cache_control)
        return int(match.group(1)) if match else self.settings.default_max_age_s
