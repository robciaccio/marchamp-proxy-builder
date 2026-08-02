"""T035 — the live OpenAPI document matches contracts/openapi.yaml.

Constitution Principle II: the contract is "generated from, or verified against, the
running service — never hand-maintained in isolation." This is the verification half.

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

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-hero-deck-pdf-wizard"
    / "contracts"
    / "openapi.yaml"
)

# FastAPI emits this for every operation with a parameter or a body. The contract declares
# it only where an unusable-but-well-formed request is a designed outcome (FR-021).
_UNDECLARED_STATUS = {"422"}


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT_PATH.read_text())


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
    if "anyOf" in resolved:
        # Pydantic writes `str | None` as anyOf; the contract writes `type: [string, null]`.
        variants = [_shape(v, doc) for v in resolved["anyOf"]]
        types = sorted(str(v.get("type")) for v in variants if isinstance(v, dict))
        out["type"] = types[0] if len(types) == 1 else types
        for variant in variants:
            if isinstance(variant, dict) and "properties" in variant:
                out |= {k: v for k, v in variant.items() if k != "type"}
    if isinstance(out.get("type"), list):
        out["type"] = sorted(str(t) for t in out["type"])
    return out


def _operations(doc: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (path, method): op
        for path, item in doc["paths"].items()
        for method, op in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }


# --------------------------------------------------------------------------- the tests


def test_the_same_paths_exist_on_both_sides(contract, live):
    # Both directions matter. An endpoint the contract omits is undocumented surface; an
    # endpoint the contract promises and the service lacks is a broken promise.
    assert set(live["paths"]) == set(contract["paths"])


def test_the_same_methods_exist_on_every_path(contract, live):
    assert set(_operations(live)) == set(_operations(contract))


@pytest.mark.parametrize("key", sorted(_operations(yaml.safe_load(CONTRACT_PATH.read_text()))))
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


@pytest.mark.parametrize("key", sorted(_operations(yaml.safe_load(CONTRACT_PATH.read_text()))))
def test_request_body_matches(key, contract, live):
    def body(doc, op):
        content = op.get("requestBody", {}).get("content", {})
        return {media: _shape(v.get("schema", {}), doc) for media, v in content.items()}

    assert body(live, _operations(live)[key]) == body(contract, _operations(contract)[key])


@pytest.mark.parametrize("key", sorted(_operations(yaml.safe_load(CONTRACT_PATH.read_text()))))
def test_declared_response_statuses_exist(key, contract, live):
    contract_codes = set(_operations(contract)[key]["responses"])
    live_codes = set(_operations(live)[key]["responses"])
    assert contract_codes <= live_codes
    assert live_codes - contract_codes <= _UNDECLARED_STATUS


@pytest.mark.parametrize("key", sorted(_operations(yaml.safe_load(CONTRACT_PATH.read_text()))))
def test_response_media_types_and_shapes_match(key, contract, live):
    live_op, contract_op = _operations(live)[key], _operations(contract)[key]
    for code, expected in contract_op["responses"].items():
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
