"""Stage 0 smoke tests — structure imports and the provider-seam wiring resolve.

No network, no heavy deps, no app logic. Just proves the scaffold holds together
so CI has something green to protect.
"""

from __future__ import annotations

import importlib


def test_packages_import() -> None:
    for name in ("ingestion", "orchestration", "graph", "api", "evals"):
        importlib.import_module(name)


def test_settings_load_with_defaults() -> None:
    from orchestration.config import Settings

    s = Settings.from_env({})
    assert s.neo4j_uri.startswith("bolt://")
    assert s.region  # a default pilot region is set
    assert set(s.tiers) == {"mechanical", "judgment"}
    # Local-first: tiers default to the local provider.
    assert s.tiers["mechanical"].provider == "local"
    assert s.tiers["judgment"].provider == "local"


def test_registry_routes_roles_to_tiers() -> None:
    from orchestration.config import Settings
    from orchestration.providers.registry import resolve

    s = Settings.from_env({})
    assert resolve("normalize", s).provider_name == "local"  # mechanical tier
    assert resolve("curate", s).provider_name == "local"  # judgment tier, local-first


def test_sensitivity_routing_forces_local_for_private_overlay() -> None:
    from orchestration.config import Settings
    from orchestration.providers.registry import resolve

    # Even if the judgment tier is pointed at the cloud yardstick...
    s = Settings.from_env(
        {"ADVENTURE_PROVIDER_JUDGMENT": "anthropic", "ADVENTURE_MODEL_JUDGMENT": "some-model"}
    )
    assert resolve("curate", s).provider_name == "anthropic"

    # ...anything touching the private overlay is forced back on-device (§13).
    private = resolve("curate", s, touches_private_overlay=True)
    assert private.provider_name == "local"
    assert private.forced_local is True
