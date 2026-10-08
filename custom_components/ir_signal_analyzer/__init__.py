"""IR Signal Analyzer integration."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

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
    TCL_TEST_DEFAULTS,
    TCL_TEST_AUXILIARY_HEAT,
    TCL_TEST_REMOTE_PROFILE,
    TCL_TEST_FAN_STEP,
    TCL_TEST_MODE,
    TCL_TEST_POWER,
    TCL_TEST_SLEEP,
    TCL_TEST_SOFT_WIND,
    TCL_TEST_SWING_HORIZONTAL,
    TCL_TEST_SWING_VERTICAL,
    TCL_TEST_TEMPERATURE,
    TCL_TEST_TRANSMITTER_ACTION,
    TCL_VERTICAL_AIRFLOW,
    TCL_HORIZONTAL_AIRFLOW,
    TCL_VALIDATION_TIMEOUT_SECONDS,
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
from .tcl112ac import (
    FAN_NATIVE_CODES,
    MODE_CODES,
    EncodedTcl112Ac,
    encode_tcl112ac,
    frame_byte_differences,
)


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
        vol.Required("auxiliary_heat", default=False): cv.boolean,
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
        self.tcl_test_state = {
            key: entry.options.get(key, default)
            for key, default in TCL_TEST_DEFAULTS.items()
        }
        self.validation_status = "idle"
        self.validation_details: dict[str, Any] = {}
        self.validated_combinations: dict[str, dict[str, Any]] = {}
        self.last_validated_combination: dict[str, Any] | None = None
        self._validation_expected: EncodedTcl112Ac | None = None
        self._validation_source: str | None = None
        self._validation_token = 0
        self._validation_timeout_cancel = None
        self._validated_path = Path(
            hass.config.path("ir_signal_analyzer", "tcl112ac-validated.json")
        )
        self._validated_write_lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        await self.catalog.async_initialize()
        await self._async_load_validated_combinations()

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
            self._sync_tcl_state_from_received(captured)
            self.last_signal = captured
            self._update_interpretation()
            self.last_error = None
        except (TypeError, ValueError) as err:
            self.last_error = str(err)

        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def _sync_tcl_state_from_received(self, signal: CapturedSignal) -> None:
        """Mirror received TCL state into the climate workbench without sending."""
        fields = signal.analysis.fields
        if signal.analysis.protocol != "tcl112ac" or fields.get("message_type") != "normal":
            return
        mode = fields.get("mode")
        if mode in {"auto", "cool", "heat", "dry", "fan"}:
            self.tcl_test_state[TCL_TEST_MODE] = "fan_only" if mode == "fan" else mode
        self.tcl_test_state[TCL_TEST_POWER] = bool(fields.get("power"))
        if isinstance(fields.get("temperature_c"), (int, float)):
            self.tcl_test_state[TCL_TEST_TEMPERATURE] = float(fields["temperature_c"])
        self.tcl_test_state[TCL_TEST_SWING_VERTICAL] = fields.get("swing_vertical") == "swing"
        self.tcl_test_state[TCL_TEST_SWING_HORIZONTAL] = bool(fields.get("swing_horizontal"))
        self.tcl_test_state[TCL_TEST_AUXILIARY_HEAT] = bool(fields.get("auxiliary_heat"))
        preceding = fields.get("preceding_special_frame") or {}
        if preceding.get("vertical_airflow"):
            self.tcl_test_state[TCL_VERTICAL_AIRFLOW] = preceding["vertical_airflow"]
        if preceding.get("horizontal_airflow"):
            self.tcl_test_state[TCL_HORIZONTAL_AIRFLOW] = preceding["horizontal_airflow"]
        command = str(preceding.get("observed_command") or "")
        request = str(preceding.get("fan_request") or "")
        fan_map = {
            "auto": "auto", "quiet_step_0": "0", "step_1": "1",
            "step_2": "2", "step_3": "3", "step_4": "4",
            "step_5_or_feature": "5",
        }
        if request in fan_map:
            self.tcl_test_state[TCL_TEST_FAN_STEP] = fan_map[request]
        elif fields.get("fan_mode") == "quiet_sleep":
            self.tcl_test_state[TCL_TEST_FAN_STEP] = "0"
        elif fields.get("fan_mode") == "auto":
            self.tcl_test_state[TCL_TEST_FAN_STEP] = "auto"
        self.tcl_test_state[TCL_TEST_SLEEP] = (
            fields.get("fan_mode") == "quiet_sleep"
            or "sleep" in command
        )
        self.tcl_test_state[TCL_TEST_SOFT_WIND] = "soft_wind" in command

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

    @callback
    def set_tcl_test_parameter(self, key: str, value: Any) -> None:
        if key not in TCL_TEST_DEFAULTS:
            raise ValueError(f"unsupported TCL test parameter: {key}")
        if key == TCL_TEST_REMOTE_PROFILE:
            self.tcl_test_state[key] = str(value)
        else:
            self._normalize_tcl_test_state(key, value)
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, **self.tcl_test_state},
        )
        self._cancel_validation_timeout()
        self._validation_expected = None
        self._validation_source = None
        self.validation_status = "idle"
        self.validation_details = {"parameters": self.tcl_test_parameters}
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def _normalize_tcl_test_state(self, key: str, value: Any) -> None:
        """Apply the remote's mutually exclusive mode/feature rules."""
        self.tcl_test_state[key] = value
        mode = str(self.tcl_test_state[TCL_TEST_MODE])
        auxiliary = bool(self.tcl_test_state[TCL_TEST_AUXILIARY_HEAT])
        if key == TCL_TEST_AUXILIARY_HEAT and value:
            self.tcl_test_state[TCL_TEST_MODE] = "heat"
            mode = "heat"
        if mode != "heat":
            self.tcl_test_state[TCL_TEST_AUXILIARY_HEAT] = False
        if mode in {"auto", "dry", "fan_only"}:
            self.tcl_test_state[TCL_TEST_FAN_STEP] = "auto" if mode != "dry" else "1"
            self.tcl_test_state[TCL_TEST_SOFT_WIND] = False
            self.tcl_test_state[TCL_TEST_SLEEP] = False
            if mode != "heat":
                self.tcl_test_state[TCL_TEST_AUXILIARY_HEAT] = False
        if auxiliary and mode == "heat":
            self.tcl_test_state[TCL_TEST_SOFT_WIND] = False

    @property
    def tcl_test_parameters(self) -> dict[str, Any]:
        return {
            "power": bool(self.tcl_test_state[TCL_TEST_POWER]),
            "mode": str(self.tcl_test_state[TCL_TEST_MODE]),
            "temperature": float(self.tcl_test_state[TCL_TEST_TEMPERATURE]),
            "fan_step": str(self.tcl_test_state[TCL_TEST_FAN_STEP]),
            "sleep": bool(self.tcl_test_state[TCL_TEST_SLEEP]),
            "soft_wind": bool(self.tcl_test_state[TCL_TEST_SOFT_WIND]),
            "swing_vertical": bool(
                self.tcl_test_state[TCL_TEST_SWING_VERTICAL]
            ),
            "swing_horizontal": bool(
                self.tcl_test_state[TCL_TEST_SWING_HORIZONTAL]
            ),
            "auxiliary_heat": bool(self.tcl_test_state[TCL_TEST_AUXILIARY_HEAT]),
            "vertical_airflow": str(self.tcl_test_state[TCL_VERTICAL_AIRFLOW]),
            "horizontal_airflow": str(self.tcl_test_state[TCL_HORIZONTAL_AIRFLOW]),
        }

    @callback
    def start_capture_validation(self) -> None:
        self._begin_validation("original_remote")

    async def async_send_generated_test(self) -> None:
        encoded = self._begin_validation("generated_echo")
        if encoded is None:
            raise HomeAssistantError(
                self.validation_details.get("error", "invalid TCL test parameters")
            )

        action_parts = TCL_TEST_TRANSMITTER_ACTION.split(".", 1)
        if not self.hass.services.has_service(*action_parts):
            self._set_validation_error(
                f"ESPHome action {TCL_TEST_TRANSMITTER_ACTION} is unavailable"
            )
            raise HomeAssistantError(self.validation_details["error"])

        try:
            await self.async_transmit_encoded(encoded)
        except Exception as err:
            self._set_validation_error(str(err))
            raise

    async def async_send_current_tcl(self) -> None:
        """Encode and transmit the current TCL-Advanced state."""
        try:
            encoded = encode_tcl112ac(**self.tcl_test_parameters)
            await self.async_transmit_encoded(encoded)
            self.validation_details = {
                "source": "climate_entity",
                "parameters": self.tcl_test_parameters,
                "expected_special": encoded.special_hex,
                "expected_normal": encoded.normal_hex,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_transmit_encoded(self, encoded: EncodedTcl112Ac) -> None:
        action_parts = TCL_TEST_TRANSMITTER_ACTION.split(".", 1)
        if not self.hass.services.has_service(*action_parts):
            raise HomeAssistantError(
                f"ESPHome action {TCL_TEST_TRANSMITTER_ACTION} is unavailable"
            )
        await self.hass.services.async_call(
            action_parts[0],
            action_parts[1],
            {
                "first_code": encoded.special,
                "second_code": encoded.normal,
                "delay_ms": self.tcl_pair_delay_ms,
                "carrier_frequency": 38000,
            },
            blocking=True,
        )

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
            "vertical_airflow": special_fields.get("vertical_airflow"),
            "horizontal_airflow": special_fields.get("horizontal_airflow"),
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
        self._handle_validation_pair(special, signal, interval_ms)

    @callback
    def _begin_validation(self, source: str) -> EncodedTcl112Ac | None:
        try:
            encoded = encode_tcl112ac(**self.tcl_test_parameters)
        except ValueError as err:
            self._set_validation_error(str(err))
            return None

        self._cancel_validation_timeout()
        self.pending_tcl_special = None
        self._validation_token += 1
        token = self._validation_token
        self._validation_expected = encoded
        self._validation_source = source
        self.validation_status = "waiting"
        self.validation_details = {
            "source": source,
            "parameters": self.tcl_test_parameters,
            "expected_special": encoded.special_hex,
            "expected_normal": encoded.normal_hex,
            "timeout_seconds": TCL_VALIDATION_TIMEOUT_SECONDS,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        @callback
        def _timeout(_now) -> None:
            if token != self._validation_token or self.validation_status != "waiting":
                return
            self.validation_status = "timed_out"
            self.validation_details["finished_at"] = datetime.now(
                timezone.utc
            ).isoformat()
            self._validation_expected = None
            self._validation_source = None
            self._validation_timeout_cancel = None
            async_dispatcher_send(
                self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}"
            )

        self._validation_timeout_cancel = async_call_later(
            self.hass, TCL_VALIDATION_TIMEOUT_SECONDS, _timeout
        )
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")
        return encoded

    @callback
    def _set_validation_error(self, error: str) -> None:
        self._cancel_validation_timeout()
        self._validation_expected = None
        self._validation_source = None
        self.validation_status = "error"
        self.validation_details = {
            "parameters": self.tcl_test_parameters,
            "error": error,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def _handle_validation_pair(
        self,
        special: CapturedSignal,
        normal: CapturedSignal,
        interval_ms: int,
    ) -> None:
        expected = self._validation_expected
        source = self._validation_source
        if self.validation_status != "waiting" or expected is None or source is None:
            return

        captured_special = str(special.analysis.fields.get("data_hex", ""))
        captured_normal = str(normal.analysis.fields.get("data_hex", ""))
        differences = frame_byte_differences(
            expected.special_hex,
            expected.normal_hex,
            captured_special,
            captured_normal,
        )
        if not differences:
            status = "matched"
        elif self._is_semantic_match(expected, special, normal):
            status = "semantic_match"
        else:
            status = "mismatch"

        self._cancel_validation_timeout()
        self.validation_status = status
        self.validation_details = {
            "source": source,
            "parameters": self.tcl_test_parameters,
            "expected_special": expected.special_hex,
            "captured_special": captured_special,
            "expected_normal": expected.normal_hex,
            "captured_normal": captured_normal,
            "different_bytes": differences,
            "pair_interval_ms": interval_ms,
            "capture_sequence": normal.device_sequence,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        self._validation_expected = None
        self._validation_source = None
        if status == "matched":
            self._record_successful_validation(source, interval_ms)
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    def _is_semantic_match(
        self,
        expected: EncodedTcl112Ac,
        special: CapturedSignal,
        normal: CapturedSignal,
    ) -> bool:
        expected_special = analyze(expected.special, "tcl112ac").fields
        expected_normal = analyze(expected.normal, "tcl112ac").fields
        if not special.analysis.fields.get(
            "checksum_valid"
        ) or not normal.analysis.fields.get("checksum_valid"):
            return False
        special_keys = (
            "fan_request",
            "vertical_swing_request",
            "horizontal_swing_request",
        )
        normal_keys = (
            "power",
            "mode",
            "temperature_c",
            "fan_code",
            "swing_vertical_code",
            "swing_horizontal",
            "feature_flag_0x40",
        )
        return all(
            expected_special.get(key) == special.analysis.fields.get(key)
            for key in special_keys
        ) and all(
            expected_normal.get(key) == normal.analysis.fields.get(key)
            for key in normal_keys
        )

    def _record_successful_validation(self, source: str, interval_ms: int) -> None:
        parameters = self.tcl_test_parameters
        key = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        record = self.validated_combinations.get(key)
        if source == "original_remote":
            if record is None:
                record = {
                    "parameters": parameters,
                    "summary": _tcl_parameter_summary(parameters),
                    "remote_validation_count": 0,
                    "transmit_validation_count": 0,
                }
                self.validated_combinations[key] = record
            record["remote_validation_count"] += 1
            record["special_frame"] = self.validation_details["captured_special"]
            record["normal_frame"] = self.validation_details["captured_normal"]
            record["last_pair_interval_ms"] = interval_ms
            record["last_remote_validation"] = self.validation_details["finished_at"]
            self.last_validated_combination = record
        elif record is not None:
            record["transmit_validation_count"] += 1
            record["last_transmit_validation"] = self.validation_details["finished_at"]

        if record is not None:
            self.entry.async_create_background_task(
                self.hass,
                self._async_save_validated_combinations(),
                "save TCL112AC validated combinations",
            )

    async def _async_load_validated_combinations(self) -> None:
        def _load() -> list[dict[str, Any]]:
            if not self._validated_path.exists():
                return []
            try:
                data = json.loads(self._validated_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            return data.get("combinations", []) if isinstance(data, dict) else []

        records = await self.hass.async_add_executor_job(_load)
        for record in records:
            parameters = record.get("parameters")
            if not isinstance(parameters, dict):
                continue
            key = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
            self.validated_combinations[key] = record
        if self.validated_combinations:
            self.last_validated_combination = max(
                self.validated_combinations.values(),
                key=lambda item: str(item.get("last_remote_validation", "")),
            )

    async def _async_save_validated_combinations(self) -> None:
        async with self._validated_write_lock:
            snapshot = {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "combinations": list(self.validated_combinations.values()),
            }

            def _save() -> None:
                self._validated_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._validated_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(self._validated_path)

            await self.hass.async_add_executor_job(_save)

    async def async_export_validated_combinations(self) -> None:
        """Rewrite the validated combination JSON for manual export/viewing."""
        await self._async_save_validated_combinations()
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def _cancel_validation_timeout(self) -> None:
        if self._validation_timeout_cancel is not None:
            self._validation_timeout_cancel()
            self._validation_timeout_cancel = None

    @callback
    def shutdown(self) -> None:
        self._cancel_validation_timeout()

    @property
    def validated_storage_path(self) -> str:
        return str(self._validated_path)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _tcl_parameter_summary(parameters: dict[str, Any]) -> str:
    parts = [
        "On" if parameters["power"] else "Off",
        str(parameters["mode"]).replace("_", " ").title(),
        f"{parameters['temperature']:g} C",
        f"fan {parameters['fan_step']}",
    ]
    for key, label in (
        ("sleep", "sleep"),
        ("soft_wind", "soft wind"),
        ("swing_vertical", "vertical swing"),
        ("swing_horizontal", "horizontal swing"),
        ("auxiliary_heat", "auxiliary heat"),
    ):
        if parameters[key]:
            parts.append(label)
    return " / ".join(parts)


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
                auxiliary_heat=call.data["auxiliary_heat"],
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
        hub: IRSignalHub = hass.data[DOMAIN].pop(entry.entry_id)
        hub.shutdown()
    return unloaded
