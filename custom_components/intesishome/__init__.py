# pylint: disable=duplicate-code
"""The IntesisHome integration."""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_vendor_path = _Path(__file__).parent / "_vendor"
if _vendor_path.is_dir():
    _vendor_str = str(_vendor_path)
    if _vendor_str not in _sys.path:
        _sys.path.insert(0, _vendor_str)
    for _name in list(_sys.modules):
        if _name == "pyintesishome" or _name.startswith("pyintesishome."):
            del _sys.modules[_name]
del _sys, _Path, _vendor_path

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "intesishome"
PLATFORMS = ["climate"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IntesisHome from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    await hass.config_entries.async_forward_entry_setups(entry, ["climate"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # example
    # unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(entry, "climate")]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
