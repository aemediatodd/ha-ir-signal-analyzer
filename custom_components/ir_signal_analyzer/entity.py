"""Shared entities for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import IRSignalHub
from .const import DOMAIN, SIGNAL_UPDATE


class IRSignalEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        self.entry = entry
        self.hub = hub
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Local",
            model="IR signal analyzer",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE}_{self.entry.entry_id}",
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
