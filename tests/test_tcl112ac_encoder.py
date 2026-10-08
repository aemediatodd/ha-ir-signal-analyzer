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
            ({"fan_step": 5, "soft_wind": True}, "0x23CB26020040D0008300000000B8", "0x23CB2601002403070500000080C8"),
            ({"fan_step": "auto", "sleep": True}, "0x23CB260200402000830000000008", "0x23CB2601002403070100000080C4"),
            ({"fan_step": 5, "swing_horizontal": True}, "0x23CB26020040C090830000000038", "0x23CB2601002403070500000088D0"),
            ({"fan_step": 4, "swing_vertical": True}, "0x23CB26020040A008830000000090", "0x23CB2601002403073D0000008000"),
            ({"fan_step": 4, "sleep": True, "swing_vertical": True}, "0x23CB26020040C0088300000000B0", "0x23CB26010024430739000000803C"),
            ({"fan_step": "auto", "soft_wind": True, "sleep": True}, "0x23CB260200403000830000000018", "0x23CB2601002403070100000080C4"),
            ({"fan_step": 0, "sleep": True, "swing_vertical": True}, "0x23CB260200604008830000000050", "0x23CB2601002403073900000080FC"),
            ({"fan_step": 0, "sleep": True, "swing_horizontal": True}, "0x23CB2602006040908300000000D8", "0x23CB2601002403070100000088CC"),
            ({"fan_step": 0, "sleep": True}, "0x23CB260200604000830000000048", "0x23CB2601002403070100000080C4"),
            ({"fan_step": "auto", "soft_wind": True, "sleep": True, "swing_vertical": True, "swing_horizontal": True}, "0x23CB2602004030988300000000B0", "0x23CB260100240307390000008804"),
            ({"mode": "heat", "fan_step": "auto", "sleep": True, "swing_vertical": True, "swing_horizontal": True}, "0x23CB2602004020988300000000A0", "0x23CB260100240107390000008802"),
            ({"mode": "heat", "fan_step": "auto", "sleep": True, "swing_horizontal": True}, "0x23CB260200402090830000000098", "0x23CB2601002401070100000088CA"),
            ({"mode": "heat", "fan_step": "auto", "sleep": True, "swing_vertical": True, "swing_horizontal": True, "auxiliary_heat": True}, "0x23CB2602004020988300000000A0", "0x23CB260100240107390000000882"),
            ({"mode": "heat", "fan_step": "1", "sleep": True, "swing_vertical": True, "swing_horizontal": True, "auxiliary_heat": True}, "0x23CB2602004040988300000000C0", "0x23CB2601002401073A0000000883"),
            ({"temperature": 23.5, "fan_step": "auto", "sleep": True, "vertical_airflow": "highest", "horizontal_airflow": "far_left"}, "0x23CB260200402011830000000019", "0x23CB26010024030801000000A0E5"),
            ({"mode": "dry", "temperature": 23.5, "fan_step": "1", "vertical_airflow": "highest", "horizontal_airflow": "left"}, "0x23CB260200404021830000000049", "0x23CB26010024020802000000A0E5"),
        ]
        for options, special_hex, normal_hex in cases:
            with self.subTest(options=options):
                parameters = {"mode": "cool", "temperature": 24}
                parameters.update(options)
                result = encoder.encode_tcl112ac(**parameters)
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

    def test_observed_airflow_command_nibbles(self):
        horizontal = {
            "left": "49", "center": "59", "right": "69", "far_right": "79",
            "left_center_swing": "89", "center_swing": "99",
            "right_center_swing": "A9", "full_swing": "B9",
        }
        for airflow, checksum in horizontal.items():
            with self.subTest(horizontal=airflow):
                result = encoder.encode_tcl112ac(
                    mode="dry", temperature=23.5, fan_step="1",
                    vertical_airflow="highest", horizontal_airflow=airflow,
                )
                self.assertEqual(result.special_hex[16:18], {
                    "left":"21", "center":"31", "right":"41", "far_right":"51",
                    "left_center_swing":"61", "center_swing":"71",
                    "right_center_swing":"81", "full_swing":"91",
                }[airflow])
                self.assertTrue(result.special_hex.endswith(checksum))
        for airflow, command, checksum in (
            ("lowest", "95", "BD"),
            ("lower_center_swing", "97", "BF"),
            ("full_swing", "98", "C0"),
        ):
            result = encoder.encode_tcl112ac(
                mode="dry", temperature=23.5, fan_step="1",
                vertical_airflow=airflow, horizontal_airflow="full_swing",
            )
            self.assertEqual(result.special_hex[16:18], command)
            self.assertTrue(result.special_hex.endswith(checksum))

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
        with self.assertRaises(ValueError):
            encoder.encode_tcl112ac(auxiliary_heat=True, mode="cool")
        with self.assertRaises(ValueError):
            encoder.encode_tcl112ac(vertical_airflow="invalid")

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
