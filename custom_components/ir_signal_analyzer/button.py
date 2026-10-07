"""Buttons for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import DOMAIN
from .entity import IRSignalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: IRSignalHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            IRDBRefreshButton(entry, hub),
            TCLCaptureValidationButton(entry, hub),
            TCLSendGeneratedTestButton(entry, hub),
        ]
    )


class IRDBRefreshButton(IRSignalEntity, ButtonEntity):
    _attr_translation_key = "refresh_irdb_snapshot"
    _attr_icon = "mdi:database-refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_refresh_irdb"

    async def async_press(self) -> None:
        await self.hub.async_refresh_catalog()


class TCLCaptureValidationButton(IRSignalEntity, ButtonEntity):
    _attr_translation_key = "tcl_capture_validation"
    _attr_icon = "mdi:remote"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_capture_validation"

    async def async_press(self) -> None:
        self.hub.start_capture_validation()


class TCLSendGeneratedTestButton(IRSignalEntity, ButtonEntity):
    _attr_translation_key = "tcl_send_generated_test"
    _attr_icon = "mdi:send"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_send_generated_test"

    async def async_press(self) -> None:
        await self.hub.async_send_generated_test()
