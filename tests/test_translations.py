from __future__ import annotations

import json
from pathlib import Path
import unittest


INTEGRATION_PATH = (
    Path(__file__).parents[1] / "custom_components" / "ir_signal_analyzer"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def key_shape(value):
    if isinstance(value, dict):
        return {key: key_shape(child) for key, child in value.items()}
    return None


class TranslationTests(unittest.TestCase):
    def test_default_english_matches_english_translation(self):
        default = load_json(INTEGRATION_PATH / "strings.json")
        english = load_json(INTEGRATION_PATH / "translations" / "en.json")
        self.assertEqual(default, english)

    def test_english_and_chinese_entity_keys_match(self):
        english = load_json(INTEGRATION_PATH / "translations" / "en.json")
        chinese = load_json(INTEGRATION_PATH / "translations" / "zh-Hans.json")
        self.assertEqual(key_shape(english["entity"]), key_shape(chinese["entity"]))

    def test_every_entity_uses_translation_key(self):
        for filename in (
            "sensor.py",
            "select.py",
            "button.py",
            "number.py",
            "switch.py",
        ):
            source = (INTEGRATION_PATH / filename).read_text(encoding="utf-8")
            self.assertNotIn("_attr_name =", source, filename)

    def test_requested_interval_names(self):
        english = load_json(INTEGRATION_PATH / "translations" / "en.json")
        chinese = load_json(INTEGRATION_PATH / "translations" / "zh-Hans.json")
        key = "two_frame_remote_interval"
        self.assertEqual(english["entity"]["number"][key]["name"], "Remote 2-frame interval")
        self.assertEqual(chinese["entity"]["number"][key]["name"], "发送2帧间隔")


if __name__ == "__main__":
    unittest.main()
