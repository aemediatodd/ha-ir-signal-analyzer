"""TCL112AC frame encoder used by Home Assistant actions."""

from __future__ import annotations

from dataclasses import dataclass


MODE_CODES = {
    "auto": 0x08,
    "cool": 0x03,
    "heat": 0x01,
    "dry": 0x02,
    "fan_only": 0x07,
}
FAN_NATIVE_CODES = {
    "auto": 0x00,
    "0": 0x02,
    "1": 0x02,
    "2": 0x03,
    "3": 0x03,
    "4": 0x05,
    "5": 0x05,
    "6": 0x05,
}
FAN_SPECIAL_PARAMETERS = {
    "auto": 0x20,
    "0": 0x40,
    "1": 0x40,
    "2": 0x60,
    "3": 0x80,
    "4": 0xA0,
    "5": 0xC0,
    "6": 0xC0,
}


@dataclass(frozen=True)
class EncodedTcl112Ac:
    """A generated TCL command frame followed by its full-state frame."""

    special: list[int]
    normal: list[int]
    special_hex: str
    normal_hex: str


def frame_byte_differences(
    expected_special: str,
    expected_normal: str,
    captured_special: str,
    captured_normal: str,
) -> list[dict[str, str | int]]:
    """Return byte-level differences for a captured TCL frame pair."""
    differences: list[dict[str, str | int]] = []
    for frame, expected, captured in (
        ("special", expected_special, captured_special),
        ("normal", expected_normal, captured_normal),
    ):
        expected_bytes = bytes.fromhex(expected.removeprefix("0x"))
        captured_bytes = bytes.fromhex(captured.removeprefix("0x"))
        width = max(len(expected_bytes), len(captured_bytes))
        for index in range(width):
            expected_value = expected_bytes[index] if index < len(expected_bytes) else None
            captured_value = captured_bytes[index] if index < len(captured_bytes) else None
            if expected_value != captured_value:
                differences.append(
                    {
                        "frame": frame,
                        "index": index,
                        "expected": (
                            f"0x{expected_value:02X}"
                            if expected_value is not None
                            else "missing"
                        ),
                        "captured": (
                            f"0x{captured_value:02X}"
                            if captured_value is not None
                            else "missing"
                        ),
                    }
                )
    return differences


def encode_tcl112ac(
    *,
    power: bool = True,
    mode: str = "cool",
    temperature: float = 24.0,
    fan_step: str | int = "auto",
    sleep: bool = False,
    soft_wind: bool = False,
    swing_vertical: bool = False,
    swing_horizontal: bool = False,
    auxiliary_heat: bool = False,
) -> EncodedTcl112Ac:
    """Generate the observed TCL type-2 command and type-1 state frames."""
    if mode not in MODE_CODES:
        raise ValueError(f"unsupported TCL112AC mode: {mode}")
    if auxiliary_heat and mode != "heat":
        raise ValueError("auxiliary_heat is validated only in heat mode")
    if not 16.0 <= temperature <= 31.0 or (temperature * 2) % 1:
        raise ValueError("temperature must be 16-31 C in 0.5 C steps")

    fan = str(fan_step).lower()
    if fan not in FAN_NATIVE_CODES:
        raise ValueError("fan_step must be auto or an integer from 0 to 6")
    soft_sleep = sleep and soft_wind
    if soft_sleep and fan != "auto":
        raise ValueError("soft_wind with sleep is validated only with automatic fan")
    if soft_wind and not sleep and fan != "5":
        raise ValueError("soft_wind without sleep is validated only with fan_step 5")

    # Type 2 tells the appliance which physical remote command was selected.
    special = [0x23, 0xCB, 0x26, 0x02, 0x00, 0x40, 0x00, 0x00, 0x83, 0, 0, 0, 0, 0]
    if fan == "0" and not soft_sleep:
        special[5] = 0x60
    special[6] = (
        0x30
        if soft_sleep
        else (
            0x20
            if sleep and fan == "auto"
            else (
                0x40
                if sleep and fan == "0"
            else (0xC0 if sleep else (0xD0 if soft_wind else FAN_SPECIAL_PARAMETERS[fan]))
            )
        )
    )
    if auxiliary_heat:
        # Observed auxiliary-heat commands retain the heat fan selector in
        # the type-2 frame: automatic uses 0x20, fan step 1 uses 0x40.
        special[6] = 0x20 if fan == "auto" else 0x40 if fan == "1" else special[6]
    if swing_vertical:
        special[7] |= 0x08
    if swing_horizontal:
        special[7] |= 0x90
    special[-1] = (sum(special[:-1]) + 0x0F) & 0xFF

    # Type 1 contains the complete resulting state.
    normal = [0x23, 0xCB, 0x26, 0x01, 0x00, 0x20, 0, 0, 0, 0, 0, 0, 0x80, 0]
    if power:
        normal[5] |= 0x04
    normal[6] = MODE_CODES[mode]
    if (sleep and not soft_sleep and fan in {"4", "5", "6"}) or fan == "6":
        normal[6] |= 0x40

    half_degrees = int(round(temperature * 2))
    normal[7] = 31 - half_degrees // 2
    if half_degrees & 1:
        normal[12] |= 0x20

    normal[8] = 0x01 if sleep else FAN_NATIVE_CODES[fan]
    if auxiliary_heat and fan == "1":
        normal[8] = 0x02
    if swing_vertical:
        normal[8] |= 0x38
    if swing_horizontal:
        normal[12] |= 0x08
    if auxiliary_heat:
        normal[12] &= 0x7F
    normal[-1] = sum(normal[:-1]) & 0xFF

    return EncodedTcl112Ac(
        special=_bytes_to_raw(special),
        normal=_bytes_to_raw(normal),
        special_hex=_bytes_to_hex(special),
        normal_hex=_bytes_to_hex(normal),
    )


def _bytes_to_raw(values: list[int]) -> list[int]:
    pulses = [3000, -1650]
    for value in values:
        for bit_index in range(8):
            pulses.extend([500, -1050 if value & (1 << bit_index) else -325])
    pulses.extend([500, -10000])
    return pulses


def _bytes_to_hex(values: list[int]) -> str:
    return "0x" + "".join(f"{value:02X}" for value in values)
