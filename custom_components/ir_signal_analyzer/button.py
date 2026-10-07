"""Buttons for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import DOMAIN, TCL_TEST_AUXILIARY_HEAT, TCL_TEST_MODE
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
            TCLAuxiliaryHeatButton(entry, hub),
            TCLExportValidatedButton(entry, hub),
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
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_capture_validation"

    async def async_press(self) -> None:
        self.hub.start_capture_validation()


class TCLSendGeneratedTestButton(IRSignalEntity, ButtonEntity):
    _attr_translation_key = "tcl_send_generated_test"
    _attr_icon = "mdi:send"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_send_generated_test"

    async def async_press(self) -> None:
        await self.hub.async_send_generated_test()


class TCLAuxiliaryHeatButton(IRSignalEntity, ButtonEntity):
    """One-shot control that enables auxiliary heat and transmits the state."""

    _attr_translation_key = "tcl_auxiliary_heat"
    _attr_icon = "mdi:radiator"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_auxiliary_heat_button"

    async def async_press(self) -> None:
        self.hub.set_tcl_test_parameter(TCL_TEST_MODE, "heat")
        self.hub.set_tcl_test_parameter(TCL_TEST_AUXILIARY_HEAT, True)
        await self.hub.async_send_current_tcl()


class TCLExportValidatedButton(IRSignalEntity, ButtonEntity):
    _attr_translation_key = "tcl_export_validated"
    _attr_icon = "mdi:export"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_export_validated"

    async def async_press(self) -> None:
        await self.hub.async_export_validated_combinations()
