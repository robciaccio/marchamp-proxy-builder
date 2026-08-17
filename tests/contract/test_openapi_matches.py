"""T035/T009 — the live OpenAPI document matches the features' contracts, merged.

Constitution Principle II: the contract is "generated from, or verified against, the
running service — never hand-maintained in isolation." This is the verification half.

**One service, two contract files** (T009). Each feature owns the document for the surface
it adds, but the service exposes their union, so the comparison is against the union too.
Before T009 this test read 001's file alone and asserted `set(live) == set(contract)`, which
made the very first 002 route a CI failure attributable to nothing. `_merged_contract()`
unions `paths` and every `components` section instead.

The merge is strict about overlap. Paths must not collide at all — two features claiming one
route is a design error, not something to resolve by precedence. Components *may* repeat,
because 002 legitimately reuses 001's `Problem`, but a repeated definition must be identical
in both files; a silent last-one-wins would let the two documents drift apart while this test
stayed green, which is the exact failure the merge exists to prevent. It caught one
immediately: 002's `Problem` claimed to be "001's shape, unchanged" while omitting `type`
from `required` and declaring `detail` non-nullable.

What is compared, and why not byte equality: `contracts/openapi.yaml` carries the design
reasoning — why generation is a POST'd resource, what each fit mode costs a user — and
that prose is the reason to keep the file hand-authored. So the test compares the
*surface* rather than the document: every path, method, parameter, request body, response
status, media type, and response-schema shape. A change to the service that the contract
does not describe fails here; a comment added to the contract does not.

The one deliberate asymmetry is FastAPI's automatic `422` on any operation that takes
parameters. It is framework behaviour, not a designed part of the interface, so the
contract is not required to enumerate it — see `_UNDECLARED_STATUS`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from marchamp.api.app import create_app
from marchamp.config import Settings

_SPECS = Path(__file__).resolve().parents[2] / "specs"

#: Every feature contract the service is required to satisfy. Adding a feature means adding
#: its file here; leaving it out means its routes are undocumented surface and this test says
#: so on the next run.
CONTRACT_PATHS = (
    _SPECS / "001-hero-deck-pdf-wizard" / "contracts" / "openapi.yaml",
    _SPECS / "002-starter-deck-assembly" / "contracts" / "openapi.yaml",
)

# FastAPI emits this for every operation with a parameter or a body. The contract declares
# it only where an unusable-but-well-formed request is a designed outcome (FR-021).
_UNDECLARED_STATUS = {"422"}

#: Operations 002's contract declares that a later phase builds, mapped to the task that
#: builds them. Feature 002 is delivered one user story at a time, so for several PRs the
#: contract legitimately describes more surface than the service exposes.
#:
#: This is an expiring exemption, not a suppression. `test_no_pending_operation_is_actually_
#: implemented` fails the moment one of these appears on the live app, which is what forces
#: the entry to be deleted in the same PR that implements the route — the alternative is a
#: list that silently outlives its contents and hides genuine drift behind stale entries.
_PENDING_OPERATIONS = {
    ("/api/assemblies", "get"): "T099 (US5, run list)",
    ("/api/assemblies/{run_id}", "delete"): "T104 (US5, retention)",
    ("/api/assemblies/{run_id}/cards/{card_code}/image", "post"): "T082 (US4, upload)",
    ("/api/assemblies/{run_id}/cards/{card_code}/omission", "post"): "T089 (US4, omission)",
    ("/api/packs/{pack_code}/snapshot", "get"): "T110b (US5, manual refresh)",
    ("/api/packs/{pack_code}/snapshot", "post"): "T110b (US5, manual refresh)",
    ("/api/pdfs", "get"): "T104 (US5, stored PDFs)",
    ("/api/pdfs/{pdf_id}", "delete"): "T104 (US5, stored PDFs)",
    ("/api/pdfs/{pdf_id}/document", "get"): "T104 (US5, stored PDFs)",
}

#: Request media types a later phase adds to an operation that already exists. Same expiring
#: contract as `_PENDING_OPERATIONS`, one level finer: `POST .../decklist` carries two shapes
#: on one path, and US1 builds only the JSON decision half (T048c). The multipart upload is
#: T093's, and exempting the whole operation would stop verifying the half that *is* built.
_PENDING_REQUEST_MEDIA_TYPES = {
    ("/api/assemblies/{run_id}/decklist", "post"): {
        "multipart/form-data": "T093 (US4, decklist upload)",
    },
}


_PROSE_KEYS = frozenset({"description", "title", "example", "examples", "summary"})


def _without_prose(node: Any) -> Any:
    """Strip documentation keys, recursively, so two copies can be compared on substance.

    The same reasoning as `_shape`: this file deliberately does not fail on prose, because a
    test that did would be one nobody could keep green. Two features repeating a component
    must agree on its *interface*; they are free to explain it differently, and 002's copy of
    `Problem` does exactly that.
    """
    if isinstance(node, dict):
        return {k: _without_prose(v) for k, v in sorted(node.items()) if k not in _PROSE_KEYS}
    if isinstance(node, list):
        return [_without_prose(v) for v in node]
    return node


def _merged_contract() -> dict[str, Any]:
    """Union the feature contracts into the one document the service is compared against.

    Not a `dict.update` chain: a collision is either a design error (paths) or drift
    (components), and both must fail loudly here rather than resolve by file order. See the
    module docstring.
    """
    docs = [(p, yaml.safe_load(p.read_text())) for p in CONTRACT_PATHS]
    merged: dict[str, Any] = {"paths": {}, "components": {}, "servers": docs[0][1]["servers"]}

    for path, doc in docs:
        for route, item in doc["paths"].items():
            if route in merged["paths"]:
                raise AssertionError(
                    f"{path.parent.parent.name} redeclares path {route!r}, which another "
                    f"feature contract already defines. One route has one owner."
                )
            merged["paths"][route] = item

        for section, entries in doc.get("components", {}).items():
            target = merged["components"].setdefault(section, {})
            for name, definition in entries.items():
                if name in target and _without_prose(target[name]) != _without_prose(definition):
                    raise AssertionError(
                        f"components.{section}.{name} is defined differently in "
                        f"{path.parent.parent.name} than in another feature contract. A "
                        f"shared component must be identical in every file that repeats it."
                    )
                target[name] = definition

    return merged


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return _merged_contract()


@pytest.fixture(scope="module")
def live(tmp_path_factory) -> dict[str, Any]:
    # A real catalog is not needed: the schema is a property of the routes, not the data.
    root = tmp_path_factory.mktemp("live")
    return create_app(Settings(image_dir=root, catalog_path=root / "catalog.json")).openapi()


# --------------------------------------------------------------- schema normalisation


def _resolve(schema: Any, doc: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    """Follow `$ref` and flatten `allOf`, so the two documents can be compared by shape.

    The contract composes `DeckDetail` out of `DeckSummary` with `allOf`; Pydantic emits
    the same thing as one flat object because it inherits. Both are the same interface,
    and normalising is what lets the test say so.
    """
    if not isinstance(schema, dict):
        return schema

    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:  # a self-referential schema would otherwise recurse forever
            return {"$circular": ref}
        node = doc
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]
        return _resolve(node, doc, seen | {ref})

    if "allOf" in schema:
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for part in schema["allOf"]:
            resolved = _resolve(part, doc, seen)
            merged["properties"].update(resolved.get("properties", {}))
            merged["required"] = sorted({*merged["required"], *resolved.get("required", [])})
        for key, value in schema.items():
            if key != "allOf":
                merged[key] = value
        return merged

    return schema


def _shape(schema: Any, doc: dict[str, Any]) -> Any:
    """The comparable essence of a schema: property names, required set, type, enum.

    Descriptions, titles, examples, and default values are excluded — they are
    documentation, and a test that failed on them would be a test nobody could keep green.
    """
    resolved = _resolve(schema, doc)
    if not isinstance(resolved, dict):
        return resolved

    out: dict[str, Any] = {}
    if "type" in resolved:
        out["type"] = resolved["type"]
    if "enum" in resolved:
        out["enum"] = sorted(resolved["enum"], key=str)
    elif "const" in resolved:
        # Pydantic writes a one-value Literal as `const`; the contract writes the
        # equivalent `enum` with one member. Same interface, two spellings.
        out["enum"] = [resolved["const"]]
    if "format" in resolved:
        out["format"] = resolved["format"]
    if "properties" in resolved:
        out["properties"] = {k: _shape(v, doc) for k, v in sorted(resolved["properties"].items())}
        out["required"] = sorted(resolved.get("required", []))
    if "items" in resolved:
        out["items"] = _shape(resolved["items"], doc)
    if "anyOf" in resolved or "oneOf" in resolved:
        # Pydantic writes `str | None` as anyOf; the contract writes `type: [string, null]`,
        # and for a nullable object reference it writes `oneOf: [$ref, {type: null}]`. All
        # three describe the same interface, and normalising is what lets the test say so.
        variants = [_shape(v, doc) for v in resolved.get("anyOf") or resolved["oneOf"]]
        types = sorted(str(v.get("type")) for v in variants if isinstance(v, dict))
        out["type"] = types[0] if len(types) == 1 else types
        for variant in variants:
            if isinstance(variant, dict) and "properties" in variant:
                out |= {k: v for k, v in variant.items() if k != "type"}
    if isinstance(out.get("type"), list):
        out["type"] = sorted(str(t) for t in out["type"])
    return out


def _operations(doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Every operation, with path-level parameters folded into each one.

    OpenAPI lets a path item declare parameters shared by all its operations, and 002's
    contract uses that for `run_id` while 001's repeated them per operation. Without the
    merge, every 002 operation appears to declare no path parameter at all and
    `test_parameters_match` fails on a difference that is only notation.
    """
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in doc["paths"].items():
        shared = item.get("parameters", [])
        for method, op in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            merged = dict(op)
            merged["parameters"] = [*shared, *op.get("parameters", [])]
            operations[(path, method)] = merged
    return operations


def _expected_operations(doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """The contract's operations minus the ones a later phase is scheduled to build."""
    return {k: v for k, v in _operations(doc).items() if k not in _PENDING_OPERATIONS}


def _expected_paths(doc: dict[str, Any]) -> set[str]:
    """Paths the service should serve now — those with at least one non-pending operation."""
    return {path for path, _ in _expected_operations(doc)}


# --------------------------------------------------------------------------- the tests


def test_the_same_paths_exist_on_both_sides(contract, live):
    # Both directions matter. An endpoint the contract omits is undocumented surface; an
    # endpoint the contract promises and the service lacks is a broken promise.
    assert set(live["paths"]) == _expected_paths(contract)


def test_no_pending_operation_is_actually_implemented(contract, live):
    """`_PENDING_OPERATIONS` must shrink as the feature lands, and never outlive its use.

    Every exemption above is a promise that a route does not exist yet. Implementing one
    without deleting its entry would leave that route permanently unverified against the
    contract, so this fails until the entry goes.
    """
    live_ops = set(_operations(live))
    arrived = {op: task for op, task in _PENDING_OPERATIONS.items() if op in live_ops}
    assert not arrived, (
        "these operations are implemented but still listed as pending — delete them from "
        f"_PENDING_OPERATIONS: {sorted(arrived)}"
    )
    stale = set(_PENDING_OPERATIONS) - set(_operations(contract))
    assert not stale, f"_PENDING_OPERATIONS names operations no contract declares: {sorted(stale)}"


def test_the_same_methods_exist_on_every_path(contract, live):
    assert set(_operations(live)) == set(_expected_operations(contract))


@pytest.mark.parametrize("key", sorted(_expected_operations(_merged_contract())))
def test_parameters_match(key, contract, live):
    def params(doc, op):
        return {
            (p["name"], p["in"], bool(p.get("required", p.get("in") == "path")))
            for p in (_resolve(raw, doc) for raw in op.get("parameters", []))
        }

    path, method = key
    live_op = _operations(live)[key]
    contract_op = _operations(contract)[key]
    assert params(live, live_op) == params(contract, contract_op)


@pytest.mark.parametrize("key", sorted(_expected_operations(_merged_contract())))
def test_request_body_matches(key, contract, live):
    pending = _PENDING_REQUEST_MEDIA_TYPES.get(key, {})

    def body(doc, op):
        content = op.get("requestBody", {}).get("content", {})
        return {
            media: _shape(v.get("schema", {}), doc)
            for media, v in content.items()
            if media not in pending
        }

    assert body(live, _operations(live)[key]) == body(contract, _operations(contract)[key])


def test_no_pending_request_media_type_is_actually_implemented(contract, live):
    """The finer exemption expires the same way the operation-level one does."""
    arrived = {
        (key, media)
        for key, media_types in _PENDING_REQUEST_MEDIA_TYPES.items()
        for media in media_types
        if media in _operations(live).get(key, {}).get("requestBody", {}).get("content", {})
    }
    assert not arrived, (
        "these request media types are implemented but still listed as pending — delete "
        f"them from _PENDING_REQUEST_MEDIA_TYPES: {sorted(arrived)}"
    )


@pytest.mark.parametrize("key", sorted(_expected_operations(_merged_contract())))
def test_declared_response_statuses_exist(key, contract, live):
    contract_codes = set(_operations(contract)[key]["responses"])
    live_codes = set(_operations(live)[key]["responses"])
    assert contract_codes <= live_codes
    assert live_codes - contract_codes <= _UNDECLARED_STATUS


@pytest.mark.parametrize("key", sorted(_expected_operations(_merged_contract())))
def test_response_media_types_and_shapes_match(key, contract, live):
    live_op, contract_op = _operations(live)[key], _operations(contract)[key]
    for code, raw in contract_op["responses"].items():
        # A whole response may itself be a `$ref` into `components.responses`, which 002's
        # contract uses for its shared `Problem404`/`Problem409State` and 001's never did.
        # Unresolved, such a response looks like one declaring no content at all, and every
        # error response appears to differ from the live document.
        expected = _resolve(raw, contract)
        actual = live_op["responses"][code]
        assert set(actual.get("content", {})) == set(expected.get("content", {})), (
            f"{key} {code}: media types differ"
        )
        for media, spec in expected.get("content", {}).items():
            if "schema" not in spec:
                continue
            assert _shape(actual["content"][media].get("schema", {}), live) == _shape(
                spec["schema"], contract
            ), f"{key} {code} {media}: schema shape differs"


def test_named_component_schemas_are_actually_generated(live):
    # The contract names these; if routes return bare dicts, FastAPI generates none of them
    # and the API is undocumented in practice even though the file looks complete.
    named = set(live.get("components", {}).get("schemas", {}))
    assert {
        "Generation",
        "DeckDetail",
        "DeckSummary",
        "Substitution",
        "Failure",
        "ValidationReport",
        "ValidationIssue",
        "Health",
        "Problem",
        "GenerationRequest",
    } <= named


def test_the_service_block_stays_loopback_only(contract, live):
    # FR-0A1/FR-0A2 are an interface promise, not only a runtime one.
    for doc in (contract, live):
        assert all("127.0.0.1" in s["url"] for s in doc["servers"])
