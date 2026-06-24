"""Device-adapter registry — config-driven, mirroring orchestration/providers/registry.py.

The single place that knows which vendors exist. Everything else iterates the list
returned by `enabled_adapters`. Adding a manufacturer = one entry here + one config
line in ADVENTURE_WATCH_ADAPTERS + the adapter file.
"""

from __future__ import annotations

from collections.abc import Callable

from orchestration.config import Settings

from .base import DeviceAdapter


def _build_garmin(settings: Settings) -> DeviceAdapter:
    from .garmin import GarminAdapter

    return GarminAdapter(settings.garmin_email, settings.garmin_password)


def _build_coros(settings: Settings) -> DeviceAdapter:
    from .coros import CorosAdapter

    return CorosAdapter(settings.coros_client_id, settings.coros_client_secret)


# name -> factory. Factories import the adapter lazily so an unused vendor's deps
# (garth, etc.) are never imported. Add a vendor here to register it.
ADAPTER_REGISTRY: dict[str, Callable[[Settings], DeviceAdapter]] = {
    "garmin": _build_garmin,
    "coros": _build_coros,
}


def enabled_adapters(settings: Settings) -> list[DeviceAdapter]:
    """Instantiate the adapters named in ADVENTURE_WATCH_ADAPTERS.

    AC-1.3: unknown name raises ValueError (fail loudly at the boundary).
    AC-1.4: empty config → empty list (no devices, pipeline still runs — rule #6).
    AC-1.5: each adapter is constructed lazily; construction makes no network call.
    """
    adapters: list[DeviceAdapter] = []
    for name in settings.watch_adapters:
        factory = ADAPTER_REGISTRY.get(name)
        if factory is None:
            known = ", ".join(sorted(ADAPTER_REGISTRY)) or "(none)"
            raise ValueError(
                f"Unknown watch adapter {name!r} in ADVENTURE_WATCH_ADAPTERS. Known: {known}"
            )
        adapters.append(factory(settings))
    return adapters
