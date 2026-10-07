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


def fingerprint(pulses: list[int]) -> str:
    """Return a stable fingerprint after modest timing quantization."""
    quantized = ",".join(str(round(value / 50) * 50) for value in pulses)
    return hashlib.sha256(quantized.encode("ascii")).hexdigest()[:16]


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
            "esphome_address": encoded_address,
            "esphome_address_hex": f"0x{encoded_address:04X}",
            "command": command,
            "command_hex": f"0x{command:04X}" if not command_checksum_ok else f"0x{command:02X}",
            "command_checksum_ok": command_checksum_ok,
            "esphome_command": encoded_command,
            "esphome_command_hex": f"0x{encoded_command:04X}",
        },
    )


DECODERS: dict[str, Callable[[list[int]], DecodeResult]] = {
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
