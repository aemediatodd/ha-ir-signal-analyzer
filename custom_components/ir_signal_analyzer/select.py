"""Decoder selector for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    TCL_TEST_REMOTE_PROFILE,
    TCL_REMOTE_PROFILE_TCL_ADVANCED,
    TCL_VERTICAL_AIRFLOW,
    TCL_HORIZONTAL_AIRFLOW,
    TCL_VERTICAL_OPTIONS,
    TCL_HORIZONTAL_OPTIONS,
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
            TCLRemoteProfileSelect(entry, hub),
            TCLAirflowSelect(entry, hub, TCL_HORIZONTAL_AIRFLOW, "tcl_horizontal_fixed", ["off", "far_left", "left", "center", "right", "far_right"], False),
            TCLAirflowSelect(entry, hub, TCL_HORIZONTAL_AIRFLOW, "tcl_horizontal_swing", ["off", "left_center_swing", "center_swing", "right_center_swing", "full_swing"], False),
            TCLAirflowSelect(entry, hub, TCL_VERTICAL_AIRFLOW, "tcl_vertical_fixed", ["off", "highest", "high", "middle", "low", "lowest"], False),
            TCLAirflowSelect(entry, hub, TCL_VERTICAL_AIRFLOW, "tcl_vertical_swing", ["off", "upper_center_swing", "full_swing", "lower_center_swing"], False),
            TCLAirflowSelect(entry, hub, TCL_HORIZONTAL_AIRFLOW, "tcl_test_horizontal_airflow", TCL_HORIZONTAL_OPTIONS, True),
            TCLAirflowSelect(entry, hub, TCL_VERTICAL_AIRFLOW, "tcl_test_vertical_airflow", TCL_VERTICAL_OPTIONS, True),
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
    _attr_entity_category = EntityCategory.CONFIG
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
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = TCL_TEST_FAN_OPTIONS

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_test_fan_step"

    @property
    def current_option(self):
        return self.hub.tcl_test_state[TCL_TEST_FAN_STEP]

    @property
    def options(self):
        mode = self.hub.tcl_test_state[TCL_TEST_MODE]
        if mode == "dry":
            return ["1"]
        if mode in {"auto", "fan_only"}:
            return ["auto"]
        return TCL_TEST_FAN_OPTIONS

    async def async_select_option(self, option: str) -> None:
        if option not in TCL_TEST_FAN_OPTIONS:
            raise ValueError(f"Unsupported TCL fan step: {option}")
        self.hub.set_tcl_test_parameter(TCL_TEST_FAN_STEP, option)


class TCLRemoteProfileSelect(IRSignalEntity, SelectEntity):
    """Select the configured transmitter profile used by the workbench."""

    _attr_translation_key = "tcl_test_remote_profile"
    _attr_icon = "mdi:remote"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_tcl_remote_profile"

    @property
    def options(self):
        return [TCL_REMOTE_PROFILE_TCL_ADVANCED]

    @property
    def current_option(self):
        return self.hub.tcl_test_state[TCL_TEST_REMOTE_PROFILE]

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unsupported remote profile: {option}")
        self.hub.set_tcl_test_parameter(TCL_TEST_REMOTE_PROFILE, option)


class TCLAirflowSelect(IRSignalEntity, SelectEntity):
    def __init__(self, entry, hub, parameter_key, translation_key, options, config) -> None:
        super().__init__(entry, hub)
        self._parameter_key = parameter_key
        self._attr_translation_key = translation_key
        self._attr_options = options
        self._attr_entity_category = EntityCategory.CONFIG if config else None
        self._send_immediately = not config
        self._attr_unique_id = f"{entry.entry_id}_{translation_key}"

    @property
    def current_option(self):
        value = self.hub.tcl_test_state[self._parameter_key]
        return value if value in self.options else "off"

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unsupported airflow option: {option}")
        self.hub.set_tcl_test_parameter(self._parameter_key, option)
        if self._send_immediately:
            await self.hub.async_send_current_tcl()
