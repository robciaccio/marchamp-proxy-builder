"""T033 — local-only posture (FR-0A1, FR-0A2, FR-0A3, SC-001a)."""

from __future__ import annotations

import pytest

from marchamp.api.app import create_app
from marchamp.config import LOOPBACK_HOSTS, Settings


def test_default_host_is_loopback():
    assert Settings(image_dir=None, catalog_path=None).host in LOOPBACK_HOSTS


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "10.0.0.4", "example.com"])
def test_externally_reachable_host_is_refused(host):
    # FR-0A2: privacy must not depend on a firewall or a reverse proxy being in front.
    with pytest.raises(ValueError):
        Settings(image_dir=None, catalog_path=None, host=host)


def test_app_exposes_no_authentication_surface(image_dir, catalog_path):
    # FR-0A3: the sole user is whoever is running it; the trust boundary is the machine.
    app = create_app(Settings(image_dir=image_dir, catalog_path=catalog_path))
    paths = set(app.openapi()["paths"])
    assert not any(
        seg in p for p in paths for seg in ("/login", "/auth", "/session", "/token", "/users")
    )


def test_openapi_declares_only_a_loopback_server(image_dir, catalog_path):
    app = create_app(Settings(image_dir=image_dir, catalog_path=catalog_path))
    for server in app.openapi().get("servers", []):
        assert "127.0.0.1" in server["url"]
