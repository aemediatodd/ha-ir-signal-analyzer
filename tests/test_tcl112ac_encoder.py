from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).parents[1] / "custom_components" / "ir_signal_analyzer"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


encoder = load_module("ir_tcl112_encoder", "tcl112ac.py")
decoder = load_module("ir_tcl112_decoder", "decoder.py")


class Tcl112AcEncoderTests(unittest.TestCase):
    def test_observed_fan_and_swing_pairs_match(self):
        cases = [
            ({"fan_step": 5}, "0x23CB26020040C0008300000000A8", "0x23CB2601002403070500000080C8"),
            ({"fan_step": 5, "soft_wind": True, "swing_horizontal": True}, "0x23CB26020040D090830000000048", "0x23CB2601002403070500000088D0"),
            ({"fan_step": 5, "swing_horizontal": True}, "0x23CB26020040C090830000000038", "0x23CB2601002403070500000088D0"),
            ({"fan_step": 4, "swing_vertical": True}, "0x23CB26020040A008830000000090", "0x23CB2601002403073D0000008000"),
            ({"fan_step": 4, "sleep": True, "swing_vertical": True}, "0x23CB26020040C0088300000000B0", "0x23CB26010024430739000000803C"),
            ({"fan_step": "auto", "soft_wind": True, "sleep": True}, "0x23CB260200403000830000000018", "0x23CB2601002403070100000080C4"),
            ({"fan_step": 0, "sleep": True, "swing_vertical": True}, "0x23CB260200604008830000000050", "0x23CB2601002403073900000080FC"),
            ({"fan_step": 0, "sleep": True, "swing_horizontal": True}, "0x23CB2602006040908300000000D8", "0x23CB2601002403070100000088CC"),
            ({"fan_step": 0, "sleep": True}, "0x23CB260200604000830000000048", "0x23CB2601002403070100000080C4"),
            ({"fan_step": "auto", "soft_wind": True, "sleep": True, "swing_vertical": True, "swing_horizontal": True}, "0x23CB2602004030988300000000B0", "0x23CB260100240307390000008804"),
            ({"mode": "heat", "fan_step": "auto", "sleep": True, "swing_vertical": True, "swing_horizontal": True}, "0x23CB2602004020988300000000A0", "0x23CB260100240107390000008802"),
        ]
        for options, special_hex, normal_hex in cases:
            with self.subTest(options=options):
                result = encoder.encode_tcl112ac(
                    mode=options.pop("mode", "cool"), temperature=24, **options
                )
                self.assertEqual(result.special_hex, special_hex)
                self.assertEqual(result.normal_hex, normal_hex)

    def test_all_remote_fan_steps_match_observed_frames(self):
        expected = {
            "auto": ("402000", "00"),
            0: ("604000", "02"),
            1: ("404000", "02"),
            2: ("406000", "03"),
            3: ("408000", "03"),
            4: ("40A000", "05"),
            5: ("40C000", "05"),
            6: ("40C000", "05"),
        }
        for fan, (special_fields, normal_fan) in expected.items():
            with self.subTest(fan=fan):
                result = encoder.encode_tcl112ac(fan_step=fan)
                self.assertEqual(result.special_hex[12:18], special_fields)
                self.assertEqual(result.normal_hex[18:20], normal_fan)

    def test_generated_frames_round_trip_through_decoder(self):
        result = encoder.encode_tcl112ac(
            mode="heat",
            temperature=24.5,
            fan_step=3,
            swing_vertical=True,
            swing_horizontal=True,
        )
        special = decoder.decode_tcl112ac(result.special)
        normal = decoder.decode_tcl112ac(result.normal)
        self.assertEqual(len(result.special), 228)
        self.assertEqual(len(result.normal), 228)
        self.assertTrue(special.fields["checksum_valid"])
        self.assertTrue(normal.fields["checksum_valid"])
        self.assertEqual(normal.fields["mode"], "heat")
        self.assertEqual(normal.fields["temperature_c"], 24.5)
        self.assertTrue(normal.fields["swing_vertical"] == "swing")
        self.assertTrue(normal.fields["swing_horizontal"])

    def test_power_off_and_every_mode_round_trip(self):
        for mode in ("auto", "cool", "heat", "dry", "fan_only"):
            with self.subTest(mode=mode):
                result = encoder.encode_tcl112ac(power=False, mode=mode)
                normal = decoder.decode_tcl112ac(result.normal)
                self.assertFalse(normal.fields["power"])
                self.assertEqual(
                    normal.fields["mode"], "fan" if mode == "fan_only" else mode
                )

    def test_invalid_unverified_combinations_are_rejected(self):
        with self.assertRaises(ValueError):
            encoder.encode_tcl112ac(fan_step=4, soft_wind=True)
        with self.assertRaises(ValueError):
            encoder.encode_tcl112ac(fan_step=5, soft_wind=True, sleep=True)

    def test_frame_byte_differences_identifies_frame_and_byte(self):
        differences = encoder.frame_byte_differences(
            "0x0102", "0x0304", "0x0105", "0x0604"
        )
        self.assertEqual(
            differences,
            [
                {
                    "frame": "special",
                    "index": 1,
                    "expected": "0x02",
                    "captured": "0x05",
                },
                {
                    "frame": "normal",
                    "index": 0,
                    "expected": "0x03",
                    "captured": "0x06",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
