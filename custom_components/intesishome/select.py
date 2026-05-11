"""Vertical / horizontal vane position selectors for IntesisHome."""

from __future__ import annotations

import logging

from pyintesishome import IntesisBase

from homeassistant import config_entries, core
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_EXPOSE_VANES, DEFAULT_EXPOSE_VANES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create vane select entities for each device that supports them."""
    if not config_entry.options.get(CONF_EXPOSE_VANES, DEFAULT_EXPOSE_VANES):
        _LOGGER.debug(
            "Vane select entities disabled by options; skipping select platform setup"
        )
        return
    controller: IntesisBase = hass.data[DOMAIN][config_entry.entry_id]["controller"]
    entities: list[SelectEntity] = []
    for device_id, device in (controller.get_devices() or {}).items():
        if controller.has_vertical_swing(device_id):
            entities.append(IntesisVaneSelect(device_id, device, controller, "vertical"))
        if controller.has_horizontal_swing(device_id):
            entities.append(
                IntesisVaneSelect(device_id, device, controller, "horizontal")
            )
    async_add_entities(entities, update_before_add=True)


class IntesisVaneSelect(SelectEntity):
    """Expose a single discrete vane axis as a select entity.

    Options are derived from the device's config bitmap (the same source
    has_vertical_swing / get_vertical_swing_list use), so a 5-position
    device exposes 7 options (auto/stop + manual1-5 + swing) and a
    9-position device exposes 11.
    """

    _attr_should_poll = False

    def __init__(
        self,
        device_id: str,
        device: dict,
        controller: IntesisBase,
        axis: str,
    ) -> None:
        """Initialise the selector for a given axis ('vertical' or 'horizontal')."""
        if axis not in ("vertical", "horizontal"):
            raise ValueError(f"axis must be 'vertical' or 'horizontal', got {axis!r}")
        self._device_id = device_id
        self._device_name: str = device.get("name") or f"Device {device_id}"
        self._controller = controller
        self._axis = axis
        self._attr_unique_id = f"{device_id}_{axis}_vane"
        self._attr_name = f"{self._device_name} {axis.title()} Vane"
        # Snapshot the options at construction time. The device's supported
        # position bitmap doesn't change during a session.
        if axis == "vertical":
            options = controller.get_vertical_swing_list(device_id)
        else:
            options = controller.get_horizontal_swing_list(device_id)
        self._attr_options = list(options or [])

    async def async_added_to_hass(self) -> None:
        """Register for controller state updates."""
        self._controller.add_update_callback(self._async_update_callback)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister from controller updates."""
        self._controller.remove_update_callback(self._async_update_callback)

    async def _async_update_callback(self, device_id=None) -> None:
        """Refresh state when the controller pushes an update for our device."""
        if device_id is None or device_id == self._device_id:
            self.async_schedule_update_ha_state(True)

    @property
    def available(self) -> bool:
        """Mirror the controller's connection state."""
        return bool(self._controller and self._controller.is_connected)

    @property
    def current_option(self) -> str | None:
        """Return the current vane position."""
        if self._axis == "vertical":
            return self._controller.get_vertical_swing(self._device_id)
        return self._controller.get_horizontal_swing(self._device_id)

    async def async_select_option(self, option: str) -> None:
        """Send the new vane position to the device."""
        if option not in self._attr_options:
            _LOGGER.warning(
                "%s vane: %r is not a supported option (%s)",
                self._axis,
                option,
                self._attr_options,
            )
            return
        if self._axis == "vertical":
            await self._controller.set_vertical_vane(self._device_id, option)
        else:
            await self._controller.set_horizontal_vane(self._device_id, option)
