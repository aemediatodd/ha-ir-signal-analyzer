"""Decoder selector for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import (
    DECODER_OPTIONS,
    DOMAIN,
    TCL_TEST_FAN_OPTIONS,
    TCL_TEST_FAN_STEP,
    TCL_TEST_MODE,
    TCL_TEST_MODE_OPTIONS,
)
from .entity import IRSignalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: IRSignalHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            IRDecoderSelect(entry, hub),
            TCLTestModeSelect(entry, hub),
            TCLTestFanStepSelect(entry, hub),
        ]
    )


class IRDecoderSelect(IRSignalEntity, SelectEntity):
    _attr_translation_key = "decoder"
    _attr_icon = "mdi:code-json"
    _attr_options = DECODER_OPTIONS

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_decoder"

    @property
    def current_option(self):
        return self.hub.decoder

    async def async_select_option(self, option: str) -> None:
        if option not in DECODER_OPTIONS:
            raise ValueError(f"Unsupported decoder: {option}")
        self.hub.set_decoder(option)


class TCLTestModeSelect(IRSignalEntity, SelectEntity):
    _attr_translation_key = "tcl_test_mode"
    _attr_icon = "mdi:air-conditioner"
    _attr_options = TCL_TEST_MODE_OPTIONS

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_test_mode"

    @property
    def current_option(self):
        return self.hub.tcl_test_state[TCL_TEST_MODE]

    async def async_select_option(self, option: str) -> None:
        if option not in TCL_TEST_MODE_OPTIONS:
            raise ValueError(f"Unsupported TCL mode: {option}")
        self.hub.set_tcl_test_parameter(TCL_TEST_MODE, option)


class TCLTestFanStepSelect(IRSignalEntity, SelectEntity):
    _attr_translation_key = "tcl_test_fan_step"
    _attr_icon = "mdi:fan"
    _attr_options = TCL_TEST_FAN_OPTIONS

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_test_fan_step"

    @property
    def current_option(self):
        return self.hub.tcl_test_state[TCL_TEST_FAN_STEP]

    async def async_select_option(self, option: str) -> None:
        if option not in TCL_TEST_FAN_OPTIONS:
            raise ValueError(f"Unsupported TCL fan step: {option}")
        self.hub.set_tcl_test_parameter(TCL_TEST_FAN_STEP, option)
