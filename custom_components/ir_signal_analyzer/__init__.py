"""IR Signal Analyzer integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_SOURCE,
    CONF_TCL_PAIR_DELAY_MS,
    DECODER_AUTO,
    DEFAULT_TCL_PAIR_DELAY_MS,
    DOMAIN,
    EVENT_IR_RECEIVED,
    PLATFORMS,
    SIGNAL_UPDATE,
    MAX_TCL_PAIR_DELAY_MS,
    MIN_TCL_PAIR_DELAY_MS,
    SERVICE_SEND_TCL112AC,
)
from .catalog import SignalInterpretation
from .catalog_manager import CatalogManager
from .decoder import (
    DecodeResult,
    analyze,
    fingerprint,
    legacy_fingerprint,
    parse_raw,
    shape_fingerprint,
)
from .tcl112ac import FAN_NATIVE_CODES, MODE_CODES, encode_tcl112ac


SEND_TCL112AC_SCHEMA = vol.Schema(
    {
        vol.Required("transmitter_action"): cv.string,
        vol.Required("power", default=True): cv.boolean,
        vol.Required("mode", default="cool"): vol.In(tuple(MODE_CODES)),
        vol.Required("temperature", default=24.0): vol.Coerce(float),
        vol.Required("fan_step", default="auto"): vol.All(
            cv.string, vol.In(tuple(FAN_NATIVE_CODES))
        ),
        vol.Required("sleep", default=False): cv.boolean,
        vol.Required("soft_wind", default=False): cv.boolean,
        vol.Required("swing_vertical", default=False): cv.boolean,
        vol.Required("swing_horizontal", default=False): cv.boolean,
        vol.Optional("delay_ms"): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_TCL_PAIR_DELAY_MS, max=MAX_TCL_PAIR_DELAY_MS),
        ),
    }
)


@dataclass
class CapturedSignal:
    received_at: datetime
    source: str
    raw: str
    pulses: list[int]
    fingerprint: str
    shape_fingerprint: str
    legacy_fingerprint: str
    analysis: DecodeResult
    device_sequence: int | None = None
    device_uptime_ms: int | None = None


class IRSignalHub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.source_filter = str(entry.data.get(CONF_SOURCE, "")).strip()
        self.decoder = str(entry.options.get("decoder", DECODER_AUTO))
        self.tcl_pair_delay_ms = max(
            MIN_TCL_PAIR_DELAY_MS,
            min(
                MAX_TCL_PAIR_DELAY_MS,
                int(
                    entry.options.get(
                        CONF_TCL_PAIR_DELAY_MS, DEFAULT_TCL_PAIR_DELAY_MS
                    )
                ),
            ),
        )
        self.catalog = CatalogManager(hass)
        self.last_signal: CapturedSignal | None = None
        self.last_interpretation: SignalInterpretation | None = None
        self.last_unknown: SignalInterpretation | None = None
        self.pending_tcl_special: CapturedSignal | None = None
        self.last_error: str | None = None

    async def async_initialize(self) -> None:
        await self.catalog.async_initialize()

    @callback
    def handle_event(self, event: Event) -> None:
        source = str(event.data.get("source", "unknown"))
        if self.source_filter and source != self.source_filter:
            return

        try:
            pulses = parse_raw(event.data.get("raw", ""))
            raw = ",".join(str(value) for value in pulses)
            analysis = analyze(pulses, self.decoder)
            captured = CapturedSignal(
                received_at=datetime.now(timezone.utc),
                source=source,
                raw=raw,
                pulses=pulses,
                fingerprint=fingerprint(pulses, analysis),
                shape_fingerprint=shape_fingerprint(pulses),
                legacy_fingerprint=legacy_fingerprint(pulses),
                analysis=analysis,
                device_sequence=_optional_int(event.data.get("capture_sequence")),
                device_uptime_ms=_optional_int(event.data.get("device_uptime_ms")),
            )
            self._link_tcl_frames(captured)
            self.last_signal = captured
            self._update_interpretation()
            self.last_error = None
        except (TypeError, ValueError) as err:
            self.last_error = str(err)

        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def set_decoder(self, decoder: str) -> None:
        self.decoder = decoder
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, "decoder": decoder},
        )
        if self.last_signal is not None:
            analysis = analyze(self.last_signal.pulses, decoder)
            self.last_signal.analysis = analysis
            self.last_signal.fingerprint = fingerprint(
                self.last_signal.pulses, analysis
            )
            self._update_interpretation()
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def set_tcl_pair_delay_ms(self, value: int) -> None:
        self.tcl_pair_delay_ms = max(
            MIN_TCL_PAIR_DELAY_MS,
            min(MAX_TCL_PAIR_DELAY_MS, int(value)),
        )
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={
                **self.entry.options,
                CONF_TCL_PAIR_DELAY_MS: self.tcl_pair_delay_ms,
            },
        )
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    async def async_refresh_catalog(self) -> None:
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")
        await self.catalog.async_refresh()
        self._update_interpretation()
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    def _update_interpretation(self) -> None:
        signal = self.last_signal
        if signal is None:
            return
        interpretation = self.catalog.interpret(
            protocol=signal.analysis.protocol,
            status=signal.analysis.status,
            fields=signal.analysis.fields,
            fingerprint=signal.fingerprint,
            shape_fingerprint=signal.shape_fingerprint,
            legacy_fingerprint=signal.legacy_fingerprint,
            raw=signal.raw,
            pulse_count=len(signal.pulses),
            source=signal.source,
            received_at=signal.received_at.isoformat(),
        )
        self.last_interpretation = interpretation
        if interpretation.unknown_state is not None:
            self.last_unknown = interpretation

    def _link_tcl_frames(self, signal: CapturedSignal) -> None:
        fields = signal.analysis.fields
        if signal.analysis.protocol != "tcl112ac":
            self.pending_tcl_special = None
            return
        if fields.get("message_type") == "special":
            self.pending_tcl_special = signal
            return
        if fields.get("message_type") != "normal":
            return

        special = self.pending_tcl_special
        self.pending_tcl_special = None
        if special is None:
            return
        interval_ms = int(
            (signal.received_at - special.received_at).total_seconds() * 1000
        )
        if not 0 <= interval_ms <= 1500:
            return

        special_fields = special.analysis.fields
        fields["preceding_special_frame"] = {
            "data_hex": special_fields.get("data_hex"),
            "summary": special_fields.get("summary"),
            "fan_request": special_fields.get("fan_request"),
            "observed_command": special_fields.get("observed_command"),
            "vertical_swing_request": special_fields.get("vertical_swing_request"),
            "horizontal_swing_request": special_fields.get(
                "horizontal_swing_request"
            ),
        }
        fields["pair_interval_ms"] = interval_ms
        fields["configured_pair_delay_ms"] = self.tcl_pair_delay_ms
        observed_command = special_fields.get("observed_command")
        if observed_command:
            fields["remote_command"] = observed_command
            fields["summary"] = (
                f"{fields.get('summary')} / "
                f"{str(observed_command).replace('_', ' ').title()}"
            )
        fields["replay_sequence"] = [
            {
                "action": "esphome.xiao_ir_transmitter_send_raw",
                "carrier_frequency": 38000,
                "raw": special.raw,
                "delay_after_ms": self.tcl_pair_delay_ms,
            },
            {
                "action": "esphome.xiao_ir_transmitter_send_raw",
                "carrier_frequency": 38000,
                "raw": signal.raw,
            },
        ]


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration actions."""

    async def async_send_tcl112ac(call: ServiceCall) -> None:
        action_parts = call.data["transmitter_action"].split(".", 1)
        if len(action_parts) != 2 or action_parts[0] != "esphome":
            raise HomeAssistantError(
                "transmitter_action must be an ESPHome action such as "
                "esphome.xiao_ir_transmitter_send_raw_pair"
            )

        try:
            encoded = encode_tcl112ac(
                power=call.data["power"],
                mode=call.data["mode"],
                temperature=call.data["temperature"],
                fan_step=call.data["fan_step"],
                sleep=call.data["sleep"],
                soft_wind=call.data["soft_wind"],
                swing_vertical=call.data["swing_vertical"],
                swing_horizontal=call.data["swing_horizontal"],
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

        delay_ms = call.data.get("delay_ms")
        if delay_ms is None:
            hubs = hass.data.get(DOMAIN, {}).values()
            delay_ms = next(
                (
                    hub.tcl_pair_delay_ms
                    for hub in hubs
                    if isinstance(hub, IRSignalHub)
                ),
                DEFAULT_TCL_PAIR_DELAY_MS,
            )

        await hass.services.async_call(
            action_parts[0],
            action_parts[1],
            {
                "first_code": encoded.special,
                "second_code": encoded.normal,
                "delay_ms": delay_ms,
                "carrier_frequency": 38000,
            },
            blocking=True,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TCL112AC,
        async_send_tcl112ac,
        schema=SEND_TCL112AC_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = IRSignalHub(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    await hub.async_initialize()
    entry.async_on_unload(hass.bus.async_listen(EVENT_IR_RECEIVED, hub.handle_event))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(
        hass,
        hub.async_refresh_catalog(),
        "refresh IRDB snapshot",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
