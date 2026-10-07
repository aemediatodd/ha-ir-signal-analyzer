"""Switch entities for the TCL validation workbench."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import (
    DOMAIN,
    TCL_TEST_POWER,
    TCL_TEST_SLEEP,
    TCL_TEST_SOFT_WIND,
    TCL_TEST_SWING_HORIZONTAL,
    TCL_TEST_SWING_VERTICAL,
    TCL_TEST_AUXILIARY_HEAT,
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
            TCLTestSwitch(entry, hub, TCL_TEST_POWER, "tcl_test_power", "mdi:power"),
            TCLTestSwitch(entry, hub, TCL_TEST_SLEEP, "tcl_test_sleep", "mdi:sleep"),
            TCLTestSwitch(
                entry,
                hub,
                TCL_TEST_SOFT_WIND,
                "tcl_test_soft_wind",
                "mdi:weather-windy",
            ),
            TCLTestSwitch(
                entry,
                hub,
                TCL_TEST_SWING_VERTICAL,
                "tcl_test_vertical_swing",
                "mdi:swap-vertical",
            ),
            TCLTestSwitch(
                entry,
                hub,
                TCL_TEST_SWING_HORIZONTAL,
                "tcl_test_horizontal_swing",
                "mdi:swap-horizontal",
            ),
            TCLTestSwitch(
                entry,
                hub,
                TCL_TEST_AUXILIARY_HEAT,
                "tcl_test_auxiliary_heat",
                "mdi:radiator",
            ),
        ]
    )


class TCLTestSwitch(IRSignalEntity, SwitchEntity):
    def __init__(
        self,
        entry: ConfigEntry,
        hub: IRSignalHub,
        parameter_key: str,
        translation_key: str,
        icon: str,
    ) -> None:
        super().__init__(entry, hub)
        self._parameter_key = parameter_key
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{parameter_key}"

    @property
    def is_on(self) -> bool:
        return bool(self.hub.tcl_test_state[self._parameter_key])

    async def async_turn_on(self, **kwargs) -> None:
        self.hub.set_tcl_test_parameter(self._parameter_key, True)

    async def async_turn_off(self, **kwargs) -> None:
        self.hub.set_tcl_test_parameter(self._parameter_key, False)
