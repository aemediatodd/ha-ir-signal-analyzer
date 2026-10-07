from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


DECODER_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ir_signal_analyzer"
    / "decoder.py"
)
SPEC = importlib.util.spec_from_file_location("ir_decoder", DECODER_PATH)
decoder = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = decoder
SPEC.loader.exec_module(decoder)


def pulse_distance_signal(header_mark: int, header_space: int, values: list[int]) -> list[int]:
    pulses = [header_mark, -header_space]
    for value in values:
        for bit_index in range(8):
            pulses.extend([560, -1690 if value & (1 << bit_index) else -560])
    pulses.append(560)
    return pulses


def tcl112_signal(values: list[int], jitter: int = 0) -> list[int]:
    pulses = [3000 + jitter, -(1650 - jitter)]
    pulse_index = 0
    for value in values:
        for bit_index in range(8):
            variation = jitter if pulse_index % 2 else -jitter
            pulses.extend(
                [
                    500 + variation,
                    -(1050 - variation if value & (1 << bit_index) else 325 - variation),
                ]
            )
            pulse_index += 1
    pulses.extend([500, -10000])
    return pulses


class DecoderTests(unittest.TestCase):
    def test_parse_and_fingerprint_are_stable(self):
        first = decoder.parse_raw("[9002, -4498, 562, -558]")
        second = decoder.parse_raw("9000,-4500,560,-560")
        self.assertEqual(decoder.fingerprint(first), decoder.fingerprint(second))

    def test_raw_fingerprint_ignores_receiver_jitter(self):
        first = decoder.parse_raw(
            "3099,-1565,542,-1039,542,-1038,544,-279,536,-279,540,-281,"
            "535,-1038,543,-305,513,-280,536,-1038,542,-1039,543,-279,"
            "537,-1040,542,-280,537,-276,540,-1039,541,-1040,541,-279,"
            "539,-1038,543,-1039,542,-281,535,-280,538,-1039"
        )
        second = decoder.parse_raw(
            "3107,-1561,548,-1033,547,-1034,546,-279,538,-279,538,-279,"
            "538,-1033,548,-279,538,-279,537,-1035,547,-1034,548,-278,"
            "537,-1033,548,-279,537,-279,538,-1034,546,-1036,548,-303,"
            "514,-1032,548,-1034,545,-280,539,-278,538,-1034"
        )

        self.assertEqual(len(first), len(second))
        self.assertEqual(decoder.fingerprint(first), decoder.fingerprint(second))
        self.assertNotEqual(
            decoder.legacy_fingerprint(first), decoder.legacy_fingerprint(second)
        )

    def test_nec_standard(self):
        pulses = pulse_distance_signal(9000, 4500, [0x10, 0xEF, 0x34, 0xCB])
        result = decoder.analyze(pulses, "nec")
        self.assertEqual(result.status, "decoded")
        self.assertEqual(result.fields["address"], 0x10)
        self.assertEqual(result.fields["command"], 0x34)
        self.assertEqual(result.fields["esphome_address"], 0xEF10)
        self.assertEqual(result.fields["esphome_command"], 0xCB34)
        self.assertTrue(result.fields["command_checksum_ok"])

    def test_different_commands_have_different_shape_fingerprints(self):
        power = pulse_distance_signal(9000, 4500, [0x10, 0xEF, 0x34, 0xCB])
        volume_up = pulse_distance_signal(9000, 4500, [0x10, 0xEF, 0x35, 0xCA])
        self.assertNotEqual(decoder.fingerprint(power), decoder.fingerprint(volume_up))

    def test_nec_extended_address(self):
        pulses = pulse_distance_signal(9000, 4500, [0x34, 0x12, 0x56, 0xA9])
        result = decoder.analyze(pulses, "auto")
        self.assertEqual(result.protocol, "nec")
        self.assertEqual(result.fields["address"], 0x1234)

    def test_nec_repeat(self):
        result = decoder.analyze([9000, -2250, 560], "nec")
        self.assertEqual(result.status, "decoded")
        self.assertTrue(result.fields["repeat"])

    def test_unknown_signal_is_retained(self):
        result = decoder.analyze([100, -200, 300, -400], "auto")
        self.assertEqual(result.protocol, "unknown")
        self.assertEqual(result.status, "unrecognized")

    def test_tcl112ac_decodes_complete_air_conditioner_state(self):
        values = [
            0x23,
            0xCB,
            0x26,
            0x01,
            0x00,
            0x24,
            0x03,
            0x07,
            0x01,
            0x00,
            0x00,
            0x00,
            0xA0,
        ]
        values.append(sum(values) & 0xFF)
        result = decoder.analyze(tcl112_signal(values), "auto")

        self.assertEqual(result.protocol, "tcl112ac")
        self.assertEqual(result.status, "decoded")
        self.assertTrue(result.fields["power"])
        self.assertEqual(result.fields["mode"], "cool")
        self.assertEqual(result.fields["temperature_c"], 24.5)
        self.assertEqual(result.fields["fan_mode"], "quiet")
        self.assertTrue(result.fields["checksum_valid"])

    def test_tcl112ac_fingerprint_uses_decoded_data_not_timing(self):
        values = [0x23, 0xCB, 0x26, 0x01, 0, 0x20, 0x03, 0x07, 0, 0, 0, 0, 0x80]
        values.append(sum(values) & 0xFF)
        first = tcl112_signal(values, jitter=0)
        second = tcl112_signal(values, jitter=12)
        first_result = decoder.analyze(first, "auto")
        second_result = decoder.analyze(second, "auto")

        self.assertEqual(
            decoder.fingerprint(first, first_result),
            decoder.fingerprint(second, second_result),
        )


if __name__ == "__main__":
    unittest.main()
