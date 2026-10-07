"""IR pulse parsing and protocol decoders with no Home Assistant dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Callable


DEFAULT_TOLERANCE = 0.35
MAX_PULSES = 4096


@dataclass(frozen=True)
class DecodeResult:
    protocol: str
    status: str
    fields: dict[str, Any]
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocol": self.protocol,
            "status": self.status,
            **self.fields,
        }
        if self.error:
            result["error"] = self.error
        return result


def parse_raw(raw: str | list[int] | tuple[int, ...]) -> list[int]:
    """Parse comma/space-delimited signed pulse widths."""
    if isinstance(raw, str):
        normalized = raw.replace("[", " ").replace("]", " ").replace(",", " ")
        parts = normalized.split()
        try:
            pulses = [int(part) for part in parts]
        except ValueError as err:
            raise ValueError(f"invalid pulse value: {err}") from err
    else:
        pulses = [int(value) for value in raw]

    pulses = [value for value in pulses if value != 0]
    if not pulses:
        raise ValueError("raw signal is empty")
    if len(pulses) > MAX_PULSES:
        raise ValueError(f"signal has more than {MAX_PULSES} pulses")
    return pulses


def fingerprint(pulses: list[int], analysis: DecodeResult | None = None) -> str:
    """Return decoded-data identity when available, otherwise waveform shape."""
    if analysis is not None and analysis.status == "decoded":
        data_hex = analysis.fields.get("data_hex")
        if data_hex:
            identity = f"{analysis.protocol}|{data_hex}"
            return hashlib.sha256(identity.encode("ascii")).hexdigest()[:16]
    return shape_fingerprint(pulses)


def shape_fingerprint(pulses: list[int]) -> str:
    """Return a stable fingerprint from pulse-shape classes.

    IR receivers introduce enough jitter for fixed-width rounding boundaries to
    change between captures. Rank timing clusters separately for marks and
    spaces so the fingerprint represents the encoded shape instead of exact
    microseconds.
    """
    centers = {
        1: _timing_centers(value for value in pulses if value > 0),
        -1: _timing_centers(-value for value in pulses if value < 0),
    }
    tokens = []
    for value in pulses:
        sign = 1 if value > 0 else -1
        timings = centers[sign]
        cluster = min(
            range(len(timings)),
            key=lambda index: abs(abs(value) - timings[index]),
        )
        tokens.append(f"{'m' if sign > 0 else 's'}{cluster}")
    shape = f"{len(pulses)}|" + ",".join(tokens)
    return hashlib.sha256(shape.encode("ascii")).hexdigest()[:16]


def legacy_fingerprint(pulses: list[int]) -> str:
    """Return the pre-1.1.2 fingerprint for local-codebook compatibility."""
    quantized = ",".join(str(round(value / 50) * 50) for value in pulses)
    return hashlib.sha256(quantized.encode("ascii")).hexdigest()[:16]


def _timing_centers(values) -> list[float]:
    ordered = sorted(abs(value) for value in values)
    if not ordered:
        return [0.0]

    clusters: list[list[int]] = [[ordered[0]]]
    for value in ordered[1:]:
        center = sum(clusters[-1]) / len(clusters[-1])
        if value / center >= 1.6:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _matches(value: int, expected: int, tolerance: float = DEFAULT_TOLERANCE) -> bool:
    if value == 0 or (value > 0) != (expected > 0):
        return False
    return abs(abs(value) - abs(expected)) <= abs(expected) * tolerance


def _decode_lsb_bytes(bits: list[int]) -> list[int]:
    values: list[int] = []
    for offset in range(0, len(bits), 8):
        chunk = bits[offset : offset + 8]
        if len(chunk) != 8:
            break
        values.append(sum(bit << index for index, bit in enumerate(chunk)))
    return values


def _decode_pulse_distance_bits(
    pulses: list[int],
    *,
    header_mark: int,
    header_space: int,
    bit_mark: int,
    zero_space: int,
    one_space: int,
    bit_count: int,
) -> list[int]:
    minimum = 2 + bit_count * 2
    if len(pulses) < minimum:
        raise ValueError(f"expected at least {minimum} pulses, received {len(pulses)}")
    if not _matches(pulses[0], header_mark) or not _matches(pulses[1], -header_space):
        raise ValueError("header timing does not match")

    bits: list[int] = []
    for bit_index in range(bit_count):
        mark = pulses[2 + bit_index * 2]
        space = pulses[3 + bit_index * 2]
        if not _matches(mark, bit_mark):
            raise ValueError(f"bit {bit_index} mark does not match")
        if _matches(space, -zero_space):
            bits.append(0)
        elif _matches(space, -one_space):
            bits.append(1)
        else:
            raise ValueError(f"bit {bit_index} space does not match zero or one")
    return bits


def decode_nec(pulses: list[int]) -> DecodeResult:
    if (
        len(pulses) >= 3
        and _matches(pulses[0], 9000)
        and _matches(pulses[1], -2250)
        and _matches(pulses[2], 560)
    ):
        return DecodeResult("nec", "decoded", {"repeat": True})

    try:
        bits = _decode_pulse_distance_bits(
            pulses,
            header_mark=9000,
            header_space=4500,
            bit_mark=560,
            zero_space=560,
            one_space=1690,
            bit_count=32,
        )
    except ValueError as err:
        return DecodeResult("nec", "mismatch", {}, str(err))

    values = _decode_lsb_bytes(bits)
    address_is_standard = values[0] ^ values[1] == 0xFF
    command_checksum_ok = values[2] ^ values[3] == 0xFF
    encoded_address = values[0] | (values[1] << 8)
    encoded_command = values[2] | (values[3] << 8)
    address = values[0] if address_is_standard else values[0] | (values[1] << 8)
    command = values[2] if command_checksum_ok else values[2] | (values[3] << 8)
    data = sum(bit << index for index, bit in enumerate(bits))

    return DecodeResult(
        "nec",
        "decoded",
        {
            "bit_count": 32,
            "data_hex": f"0x{data:08X}",
            "bytes_hex": [f"0x{value:02X}" for value in values],
            "address": address,
            "address_hex": f"0x{address:04X}" if not address_is_standard else f"0x{address:02X}",
            "address_format": "standard" if address_is_standard else "extended",
            "irdb_device": values[0],
            "irdb_subdevice": -1 if address_is_standard else values[1],
            "irdb_function": values[2],
            "esphome_address": encoded_address,
            "esphome_address_hex": f"0x{encoded_address:04X}",
            "command": command,
            "command_hex": f"0x{command:04X}" if not command_checksum_ok else f"0x{command:02X}",
            "command_checksum_ok": command_checksum_ok,
            "esphome_command": encoded_command,
            "esphome_command_hex": f"0x{encoded_command:04X}",
        },
    )


def decode_tcl112ac(pulses: list[int]) -> DecodeResult:
    """Decode the TCL 112-bit full-state air-conditioner protocol."""
    try:
        bits = _decode_pulse_distance_bits(
            pulses,
            header_mark=3000,
            header_space=1650,
            bit_mark=500,
            zero_space=325,
            one_space=1050,
            bit_count=112,
        )
    except ValueError as err:
        return DecodeResult("tcl112ac", "mismatch", {}, str(err))

    values = _decode_lsb_bytes(bits)
    if values[:3] != [0x23, 0xCB, 0x26]:
        return DecodeResult(
            "tcl112ac",
            "mismatch",
            {},
            "TCL112AC signature does not match 0x23CB26",
        )

    message_type = values[3] & 0x03
    checksum_offset = 0x0F if values[3] == 0x02 else 0
    expected_checksum = (sum(values[:-1]) + checksum_offset) & 0xFF
    checksum_valid = values[-1] == expected_checksum
    data_hex = "0x" + "".join(f"{value:02X}" for value in values)
    common = {
        "bit_count": 112,
        "data_hex": data_hex,
        "bytes_hex": [f"0x{value:02X}" for value in values],
        "manufacturer": "TCL",
        "device_type": "air_conditioner",
        "model_family": "TCL112AC",
        "message_type": {1: "normal", 2: "special"}.get(message_type, "unknown"),
        "message_type_code": message_type,
        "checksum": f"0x{values[-1]:02X}",
        "expected_checksum": f"0x{expected_checksum:02X}",
        "checksum_valid": checksum_valid,
    }

    if message_type == 2:
        special = _decode_tcl112ac_special(values)
        return DecodeResult("tcl112ac", "decoded", {**common, **special})

    power = bool(values[5] & 0x04)
    mode_code = values[6] & 0x0F
    fan_code = values[8] & 0x07
    swing_vertical_code = (values[8] >> 3) & 0x07
    temperature = 31.0 - (values[7] & 0x0F)
    if values[12] & 0x20:
        temperature += 0.5

    mode = {1: "heat", 2: "dry", 3: "cool", 7: "fan", 8: "auto"}.get(
        mode_code, "unknown"
    )
    fan_mode = {
        0: "auto",
        1: "quiet_sleep",
        2: "low_steps_0_1",
        3: "medium_steps_2_3",
        5: "high_steps_4_5",
    }.get(fan_code, "unknown")
    swing_vertical = {
        0: "off",
        1: "highest",
        2: "high",
        3: "middle",
        4: "low",
        5: "lowest",
        7: "swing",
    }.get(swing_vertical_code, "unknown")
    feature_flag_0x40 = bool(values[6] & 0x40)

    if not power:
        summary = "Power off"
    else:
        fan_summary = fan_mode.replace("_", " ").title()
        summary = f"{mode.title()} {temperature:g} C / {fan_summary}"

    return DecodeResult(
        "tcl112ac",
        "decoded",
        {
            **common,
            "power": power,
            "mode": mode,
            "mode_code": mode_code,
            "temperature_c": temperature,
            "fan_mode": fan_mode,
            "fan_code": fan_code,
            "swing_vertical": swing_vertical,
            "swing_vertical_code": swing_vertical_code,
            "swing_horizontal": bool(values[12] & 0x08),
            "health": bool(values[6] & 0x10),
            "feature_flag_0x40": feature_flag_0x40,
            "econo": bool(values[5] & 0x80),
            "display_light": not bool(values[5] & 0x40),
            "summary": summary,
        },
    )


def _decode_tcl112ac_special(values: list[int]) -> dict[str, Any]:
    """Describe a TCL type-2 command frame without treating it as power-off."""
    special_bytes = f"{values[5]:02X}{values[6]:02X}{values[7]:02X}"
    observed_command = {
        "40D090": "soft_wind_horizontal_swing",
        "40C090": "fan_step_5_horizontal_swing",
        "40C000": "fan_step_5_or_turbo",
        "402000": "fan_auto",
        "604000": "fan_step_0_quiet",
        "404000": "fan_step_1",
        "406000": "fan_step_2",
        "408000": "fan_step_3",
        "40A000": "fan_step_4",
        "40A008": "fan_step_4_vertical_swing",
        "40C008": "sleep_display_off_vertical_swing",
    }.get(special_bytes)
    parameter = values[6] & 0xF0
    if values[5] == 0x60 and parameter == 0x40:
        fan_request = "quiet_step_0"
    else:
        fan_request = {
            0x20: "auto",
            0x40: "step_1",
            0x60: "step_2",
            0x80: "step_3",
            0xA0: "step_4",
            0xC0: "step_5_or_feature",
            0xD0: "soft_wind",
        }.get(parameter, "unknown")

    vertical_swing = bool(values[7] & 0x08)
    horizontal_swing = (values[7] & 0x90) == 0x90
    parts = [
        (observed_command or f"fan request {fan_request}").replace("_", " ")
    ]
    if vertical_swing:
        parts.append("vertical swing")
    if horizontal_swing:
        parts.append("horizontal swing")

    return {
        "special_command": True,
        "special_bytes_hex": f"0x{special_bytes}",
        "observed_command": observed_command,
        "fan_request": fan_request,
        "vertical_swing_request": vertical_swing,
        "horizontal_swing_request": horizontal_swing,
        "summary": "Special command / " + " / ".join(parts),
    }


DECODERS: dict[str, Callable[[list[int]], DecodeResult]] = {
    "tcl112ac": decode_tcl112ac,
    "nec": decode_nec,
}


def analyze(pulses: list[int], decoder: str = "auto") -> DecodeResult:
    if decoder == "raw":
        return DecodeResult("raw", "captured", {"bit_count": None})
    if decoder != "auto":
        try:
            decode = DECODERS[decoder]
        except KeyError as err:
            raise ValueError(f"unsupported decoder: {decoder}") from err
        return decode(pulses)

    mismatches: list[str] = []
    for name, decode in DECODERS.items():
        result = decode(pulses)
        if result.status == "decoded":
            return result
        mismatches.append(f"{name}: {result.error}")
    return DecodeResult(
        "unknown",
        "unrecognized",
        {},
        "; ".join(mismatches),
    )
