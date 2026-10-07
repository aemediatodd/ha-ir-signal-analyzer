"""TCL-Advanced climate entity."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import DOMAIN, TCL_TEST_AUXILIARY_HEAT, TCL_TEST_FAN_STEP, TCL_TEST_MODE, TCL_TEST_POWER, TCL_TEST_SLEEP, TCL_TEST_SOFT_WIND, TCL_TEST_SWING_HORIZONTAL, TCL_TEST_SWING_VERTICAL, TCL_TEST_TEMPERATURE
from .entity import IRSignalEntity


HVAC_TO_MODE = {
    HVACMode.AUTO: "auto",
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan_only",
}
MODE_TO_HVAC = {value: key for key, value in HVAC_TO_MODE.items()}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: IRSignalHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TCLAdvancedClimate(entry, hub)])


class TCLAdvancedClimate(IRSignalEntity, ClimateEntity):
    _attr_translation_key = "tcl_advanced_climate"
    _attr_icon = "mdi:air-conditioner"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 31
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_advanced_climate"

    @property
    def hvac_mode(self):
        state = self.hub.tcl_test_state
        if not state[TCL_TEST_POWER]:
            return HVACMode.OFF
        return MODE_TO_HVAC.get(state[TCL_TEST_MODE], HVACMode.COOL)

    @property
    def hvac_modes(self):
        return [HVACMode.OFF, HVACMode.AUTO, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY]

    @property
    def target_temperature(self):
        return float(self.hub.tcl_test_state[TCL_TEST_TEMPERATURE])

    @property
    def fan_mode(self):
        return str(self.hub.tcl_test_state[TCL_TEST_FAN_STEP])

    @property
    def fan_modes(self):
        mode = self.hub.tcl_test_state[TCL_TEST_MODE]
        if mode == "dry":
            return ["1"]
        if mode in {"auto", "fan_only"}:
            return ["auto"]
        return ["auto", "0", "1", "2", "3", "4", "5", "6"]

    @property
    def swing_mode(self):
        vertical = bool(self.hub.tcl_test_state[TCL_TEST_SWING_VERTICAL])
        horizontal = bool(self.hub.tcl_test_state[TCL_TEST_SWING_HORIZONTAL])
        return "both" if vertical and horizontal else "vertical" if vertical else "horizontal" if horizontal else "off"

    @property
    def swing_modes(self):
        return ["off", "vertical", "horizontal", "both"]

    @property
    def preset_mode(self):
        state = self.hub.tcl_test_state
        if state[TCL_TEST_SLEEP] and state[TCL_TEST_SOFT_WIND]:
            return "soft_wind_sleep"
        if state[TCL_TEST_SLEEP]:
            return "sleep"
        if state[TCL_TEST_SOFT_WIND]:
            return "soft_wind"
        return "none"

    @property
    def preset_modes(self):
        mode = self.hub.tcl_test_state[TCL_TEST_MODE]
        presets = ["none"]
        if mode not in {"auto", "dry", "fan_only"}:
            presets.extend(["sleep", "soft_wind_sleep"])
            if not self.hub.tcl_test_state[TCL_TEST_AUXILIARY_HEAT]:
                presets.append("soft_wind")
        return presets

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        if hvac_mode == HVACMode.OFF:
            self.hub.set_tcl_test_parameter(TCL_TEST_POWER, False)
        elif hvac_mode in HVAC_TO_MODE:
            self.hub.set_tcl_test_parameter(TCL_TEST_POWER, True)
            self.hub.set_tcl_test_parameter(TCL_TEST_MODE, HVAC_TO_MODE[hvac_mode])
        await self.hub.async_send_current_tcl()

    async def async_set_temperature(self, **kwargs) -> None:
        self.hub.set_tcl_test_parameter(TCL_TEST_TEMPERATURE, round(float(kwargs[ATTR_TEMPERATURE]) * 2) / 2)
        await self.hub.async_send_current_tcl()

    async def async_set_fan_mode(self, fan_mode) -> None:
        if fan_mode not in self.fan_modes:
            raise ValueError(f"Unsupported fan mode: {fan_mode}")
        self.hub.set_tcl_test_parameter(TCL_TEST_FAN_STEP, fan_mode)
        await self.hub.async_send_current_tcl()

    async def async_set_swing_mode(self, swing_mode) -> None:
        if swing_mode not in self.swing_modes:
            raise ValueError(f"Unsupported swing mode: {swing_mode}")
        self.hub.set_tcl_test_parameter(TCL_TEST_SWING_VERTICAL, swing_mode in {"vertical", "both"})
        self.hub.set_tcl_test_parameter(TCL_TEST_SWING_HORIZONTAL, swing_mode in {"horizontal", "both"})
        await self.hub.async_send_current_tcl()

    async def async_set_preset_mode(self, preset_mode) -> None:
        if preset_mode not in self.preset_modes:
            raise ValueError(f"Unsupported preset: {preset_mode}")
        self.hub.set_tcl_test_parameter(TCL_TEST_SLEEP, preset_mode in {"sleep", "soft_wind_sleep"})
        self.hub.set_tcl_test_parameter(TCL_TEST_SOFT_WIND, preset_mode in {"soft_wind", "soft_wind_sleep"})
        await self.hub.async_send_current_tcl()
