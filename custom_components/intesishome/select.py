"""Vertical / horizontal vane position selectors for IntesisHome.

The select entities expose only the discrete manual positions the device
supports. 'auto/stop' and 'swing' are intentionally not in the options
list — those are reachable via the climate entity's swing toggle.

The current value of the select represents the user's preferred manual
position for that axis. It is:

  - Pre-populated from the device's current state if it's a manual.
  - Restored from HA's state-restore on integration reload.
  - Auto-synced whenever the device reports a new manual position (from
    a physical remote, an automation, or the climate entity's swing-off
    landing the vane somewhere).
  - The value sent to the device when the user picks via the select.
  - The value the climate entity sends when SWING_OFF is set.
"""

from __future__ import annotations

import logging

from pyintesishome import IntesisBase

from homeassistant import config_entries, core
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import (
    CONF_EXPOSE_VANES,
    DEFAULT_EXPOSE_VANES,
    DOMAIN,
    _manual_options,
    get_vane_preference,
    set_vane_preference,
)

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
        if controller.has_vertical_swing(device_id) and _manual_options(
            controller, device_id, "vertical"
        ):
            entities.append(
                IntesisVaneSelect(
                    config_entry.entry_id, device_id, device, controller, "vertical"
                )
            )
        if controller.has_horizontal_swing(device_id) and _manual_options(
            controller, device_id, "horizontal"
        ):
            entities.append(
                IntesisVaneSelect(
                    config_entry.entry_id, device_id, device, controller, "horizontal"
                )
            )
    async_add_entities(entities, update_before_add=True)


class IntesisVaneSelect(SelectEntity, RestoreEntity):
    """User-preferred manual position for one vane axis."""

    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        device_id: str,
        device: dict,
        controller: IntesisBase,
        axis: str,
    ) -> None:
        """Initialise the selector for a given axis ('vertical' or 'horizontal')."""
        if axis not in ("vertical", "horizontal"):
            raise ValueError(f"axis must be 'vertical' or 'horizontal', got {axis!r}")
        self._entry_id = entry_id
        self._device_id = device_id
        self._device_name: str = device.get("name") or f"Device {device_id}"
        self._controller = controller
        self._axis = axis
        self._attr_unique_id = f"{device_id}_{axis}_vane"
        self._attr_name = f"{self._device_name} {axis.title()} Vane"
        # Options are only the manual positions the device advertises.
        self._attr_options = _manual_options(controller, device_id, axis)

    async def async_added_to_hass(self) -> None:
        """Restore previous selection (if any), then sync to device state.

        Restore wins if the user had picked a value last session and the
        device hasn't reported a different manual in the meantime. If the
        device IS currently at a manual position different from the
        restored value, prefer the current device state (the source of
        truth) — likely set by the climate's swing-off or a physical
        remote since restart.
        """
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            set_vane_preference(
                self.hass, self._entry_id, self._device_id, self._axis, last_state.state
            )

        current = self._current_device_value()
        if current and current.startswith("manual"):
            set_vane_preference(
                self.hass, self._entry_id, self._device_id, self._axis, current
            )

        self._controller.add_update_callback(self._async_update_callback)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister from controller updates."""
        self._controller.remove_update_callback(self._async_update_callback)

    async def _async_update_callback(self, device_id=None) -> None:
        """Refresh state when the controller pushes an update for our device."""
        if device_id is not None and device_id != self._device_id:
            return
        # If the device's current position is a manual, mirror that into
        # the preference so the user can see where the vane actually is.
        # Swing / auto/stop states leave the preference untouched.
        current = self._current_device_value()
        if current and current.startswith("manual"):
            set_vane_preference(
                self.hass, self._entry_id, self._device_id, self._axis, current
            )
        self.async_schedule_update_ha_state(True)

    def _current_device_value(self) -> str | None:
        if self._axis == "vertical":
            return self._controller.get_vertical_swing(self._device_id)
        return self._controller.get_horizontal_swing(self._device_id)

    @property
    def available(self) -> bool:
        """Mirror the controller's connection state."""
        return bool(self._controller and self._controller.is_connected)

    @property
    def current_option(self) -> str | None:
        """The user's preferred manual position for this axis."""
        return get_vane_preference(
            self.hass,
            self._entry_id,
            self._device_id,
            self._axis,
            self._controller,
        )

    async def async_select_option(self, option: str) -> None:
        """Record the new preference and move the vane there."""
        if option not in self._attr_options:
            _LOGGER.warning(
                "%s vane: %r is not a supported option (%s)",
                self._axis,
                option,
                self._attr_options,
            )
            return
        set_vane_preference(
            self.hass, self._entry_id, self._device_id, self._axis, option
        )
        if self._axis == "vertical":
            await self._controller.set_vertical_vane(self._device_id, option)
        else:
            await self._controller.set_horizontal_vane(self._device_id, option)
        self.async_schedule_update_ha_state(True)
