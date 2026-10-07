"""Number entities for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import (
    DOMAIN,
    MAX_TCL_PAIR_DELAY_MS,
    MIN_TCL_PAIR_DELAY_MS,
    TCL_TEST_TEMPERATURE,
)
from .entity import IRSignalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: IRSignalHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [TCLPairDelayNumber(entry, hub), TCLTestTemperatureNumber(entry, hub)]
    )


class TCLPairDelayNumber(IRSignalEntity, NumberEntity):
    """Configure the delay between TCL command and state frames."""

    _attr_translation_key = "two_frame_remote_interval"
    _attr_icon = "mdi:timer-settings-outline"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = MIN_TCL_PAIR_DELAY_MS
    _attr_native_max_value = MAX_TCL_PAIR_DELAY_MS
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_pair_delay_ms"

    @property
    def native_value(self) -> float:
        return self.hub.tcl_pair_delay_ms

    async def async_set_native_value(self, value: float) -> None:
        self.hub.set_tcl_pair_delay_ms(round(value))


class TCLTestTemperatureNumber(IRSignalEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "tcl_test_temperature"
    _attr_icon = "mdi:thermometer"
    _attr_native_min_value = 16
    _attr_native_max_value = 31
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_test_temperature"

    @property
    def native_value(self) -> float:
        return float(self.hub.tcl_test_state[TCL_TEST_TEMPERATURE])

    async def async_set_native_value(self, value: float) -> None:
        self.hub.set_tcl_test_parameter(TCL_TEST_TEMPERATURE, round(value * 2) / 2)
