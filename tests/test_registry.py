"""Role resolution tests (`orchestration/providers/registry.py`) — tier-only
resolution (pin), per-role overrides, and the privacy-routing invariant that a
cloud override can never defeat sensitivity routing (Epic 040 operator-lever
seam: `ADVENTURE_{PROVIDER,MODEL,LOCAL_MODEL}_<ROLE>`).

No network: `resolve()` only builds provider adapter instances, it never calls
them. Env is injected via `Settings.from_env({...})` per the existing pattern.
"""

from __future__ import annotations

import pytest

from orchestration.config import Settings
from orchestration.providers.anthropic_claude import AnthropicProvider
from orchestration.providers.local_openai import LocalOpenAIProvider
from orchestration.providers.registry import ROLE_TIER, resolve

ALL_ROLES = ("extract", "normalize", "judge", "curate")


# ── 1. Pin test: no role-override envs set → byte-identical to tier-only resolution ──


def test_resolve_all_roles_local_tier_defaults_no_overrides() -> None:
    # Empty env → both tiers default local, no models configured. mechanical
    # roles (extract/normalize) and judgment roles (judge/curate) all hit the
    # same "no model configured" error path — pin that shape first.
    settings = Settings.from_env({})
    for role in ALL_ROLES:
        with pytest.raises(ValueError, match=f"No model configured for role {role!r}"):
            resolve(role, settings)


def test_resolve_all_roles_local_tier_with_models_no_overrides() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_MODEL_MECHANICAL": "qwen2.5",
            "ADVENTURE_MODEL_JUDGMENT": "llama3.3",
        }
    )
    for role in ("extract", "normalize"):
        r = resolve(role, settings)
        assert r.provider_name == "local"
        assert r.model == "qwen2.5"
        assert r.forced_local is False
        assert isinstance(r.provider, LocalOpenAIProvider)
    for role in ("judge", "curate"):
        r = resolve(role, settings)
        assert r.provider_name == "local"
        assert r.model == "llama3.3"
        assert r.forced_local is False
        assert isinstance(r.provider, LocalOpenAIProvider)


def test_resolve_all_roles_anthropic_tier_no_overrides() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_MECHANICAL": "anthropic",
            "ADVENTURE_MODEL_MECHANICAL": "claude-haiku-4-5",
            "ADVENTURE_PROVIDER_JUDGMENT": "anthropic",
            "ADVENTURE_MODEL_JUDGMENT": "claude-sonnet-4-6",
            "ANTHROPIC_API_KEY": "key-123",
        }
    )
    for role in ("extract", "normalize"):
        r = resolve(role, settings)
        assert r.provider_name == "anthropic"
        assert r.model == "claude-haiku-4-5"
        assert r.forced_local is False
        assert isinstance(r.provider, AnthropicProvider)
    for role in ("judge", "curate"):
        r = resolve(role, settings)
        assert r.provider_name == "anthropic"
        assert r.model == "claude-sonnet-4-6"
        assert r.forced_local is False
        assert isinstance(r.provider, AnthropicProvider)


def test_resolve_touches_private_overlay_no_overrides_matches_today() -> None:
    # Judgment tier on anthropic; touches_private_overlay must force local using
    # the tier's local_model — unaffected by (absent) role overrides.
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_JUDGMENT": "anthropic",
            "ADVENTURE_MODEL_JUDGMENT": "claude-sonnet-4-6",
            "ADVENTURE_LOCAL_MODEL_JUDGMENT": "llama3.3",
        }
    )
    r = resolve("curate", settings, touches_private_overlay=True)
    assert r.provider_name == "local"
    assert r.model == "llama3.3"
    assert r.forced_local is True
    assert isinstance(r.provider, LocalOpenAIProvider)


# ── 2. Per-role override applies without leaking to siblings ──


def test_curate_model_override_does_not_leak_to_judge() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_MODEL_JUDGMENT": "claude-sonnet-4-6",
            "ADVENTURE_MODEL_CURATE": "fast-model",
        }
    )
    assert resolve("curate", settings).model == "fast-model"
    assert resolve("judge", settings).model == "claude-sonnet-4-6"


def test_extract_model_override_does_not_leak_to_normalize() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_MODEL_MECHANICAL": "qwen2.5",
            "ADVENTURE_MODEL_EXTRACT": "extract-only-model",
        }
    )
    assert resolve("extract", settings).model == "extract-only-model"
    assert resolve("normalize", settings).model == "qwen2.5"


def test_normalize_model_override_does_not_leak_to_extract() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_MODEL_MECHANICAL": "qwen2.5",
            "ADVENTURE_MODEL_NORMALIZE": "normalize-only-model",
        }
    )
    assert resolve("normalize", settings).model == "normalize-only-model"
    assert resolve("extract", settings).model == "qwen2.5"


# ── 3. Provider override builds the right adapter ──


def test_curate_provider_override_builds_anthropic_while_judge_stays_local() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_MODEL_JUDGMENT": "llama3.3",  # judgment tier default: local
            "ADVENTURE_PROVIDER_CURATE": "anthropic",
            "ADVENTURE_MODEL_CURATE": "claude-haiku-4-5",
            "ANTHROPIC_API_KEY": "key-123",
        }
    )
    r_curate = resolve("curate", settings)
    assert r_curate.provider_name == "anthropic"
    assert isinstance(r_curate.provider, AnthropicProvider)

    r_judge = resolve("judge", settings)
    assert r_judge.provider_name == "local"
    assert isinstance(r_judge.provider, LocalOpenAIProvider)
    assert r_judge.model == "llama3.3"


# ── 4. Privacy routing wins over a cloud override ──


def test_privacy_routing_forces_local_despite_cloud_override_with_role_local_model() -> None:
    # (a) role-level ADVENTURE_LOCAL_MODEL_CURATE present → used.
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_CURATE": "anthropic",
            "ADVENTURE_MODEL_CURATE": "cloud-model",
            "ADVENTURE_LOCAL_MODEL_CURATE": "local-fallback",
            "ANTHROPIC_API_KEY": "key-123",
        }
    )
    r = resolve("curate", settings, touches_private_overlay=True)
    assert r.provider_name == "local"
    assert r.forced_local is True
    assert r.model == "local-fallback"
    assert isinstance(r.provider, LocalOpenAIProvider)


def test_privacy_routing_falls_back_to_tier_local_model_when_role_local_model_absent() -> None:
    # (b) no role-level local_model override → falls back to the tier's local_model.
    settings = Settings.from_env(
        {
            "ADVENTURE_LOCAL_MODEL_JUDGMENT": "tier-local-fallback",
            "ADVENTURE_PROVIDER_CURATE": "anthropic",
            "ADVENTURE_MODEL_CURATE": "cloud-model",
            "ANTHROPIC_API_KEY": "key-123",
        }
    )
    r = resolve("curate", settings, touches_private_overlay=True)
    assert r.provider_name == "local"
    assert r.forced_local is True
    assert r.model == "tier-local-fallback"
    assert isinstance(r.provider, LocalOpenAIProvider)


def test_privacy_routing_falls_back_to_effective_cloud_model_when_no_local_anywhere() -> None:
    # Neither role nor tier local_model set → existing fallback semantics: use
    # the effective (role-overridden) cloud model id, still forced onto the
    # local provider/adapter.
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_CURATE": "anthropic",
            "ADVENTURE_MODEL_CURATE": "cloud-model",
            "ANTHROPIC_API_KEY": "key-123",
        }
    )
    r = resolve("curate", settings, touches_private_overlay=True)
    assert r.provider_name == "local"
    assert r.forced_local is True
    assert r.model == "cloud-model"
    assert isinstance(r.provider, LocalOpenAIProvider)


def test_privacy_routing_cloud_override_never_returns_cloud_provider() -> None:
    # Explicit anti-regression: whatever the model resolves to, the returned
    # provider adapter must never be AnthropicProvider when
    # touches_private_overlay=True, regardless of the override.
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_CURATE": "anthropic",
            "ADVENTURE_MODEL_CURATE": "cloud-model",
            "ANTHROPIC_API_KEY": "key-123",
        }
    )
    r = resolve("curate", settings, touches_private_overlay=True)
    assert not isinstance(r.provider, AnthropicProvider)
    assert r.provider_name == "local"


# ── 5. Unset-everything error unchanged ──


def test_no_model_and_no_override_raises_same_error_text() -> None:
    settings = Settings.from_env({})
    for role in ALL_ROLES:
        with pytest.raises(
            ValueError,
            match=(
                f"No model configured for role {role!r} \\(tier {ROLE_TIER[role]!r}\\) — "
                "set ADVENTURE_MODEL_\\* in .env"
            ),
        ):
            resolve(role, settings)


# ── Off-by-one guard: an unset provider override must NOT force a role onto a
# different provider than its tier — it must fall through cleanly. ──


def test_unset_provider_override_falls_through_to_tier_provider() -> None:
    settings = Settings.from_env(
        {
            "ADVENTURE_PROVIDER_JUDGMENT": "anthropic",
            "ADVENTURE_MODEL_JUDGMENT": "claude-sonnet-4-6",
            "ANTHROPIC_API_KEY": "key-123",
            # ADVENTURE_MODEL_CURATE set but NOT ADVENTURE_PROVIDER_CURATE —
            # curate must still resolve on the judgment tier's anthropic provider,
            # not silently fall back to "local".
            "ADVENTURE_MODEL_CURATE": "fast-model",
        }
    )
    r = resolve("curate", settings)
    assert r.provider_name == "anthropic"
    assert r.model == "fast-model"
    assert isinstance(r.provider, AnthropicProvider)
