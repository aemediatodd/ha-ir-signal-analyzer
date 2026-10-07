from __future__ import annotations

from io import BytesIO
import importlib.util
from pathlib import Path
import sys
import unittest
from zipfile import ZIP_DEFLATED, ZipFile


CATALOG_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ir_signal_analyzer"
    / "catalog.py"
)
SPEC = importlib.util.spec_from_file_location("ir_catalog", CATALOG_PATH)
catalog = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = catalog
SPEC.loader.exec_module(catalog)


def make_archive(files: dict[str, str]) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return stream.getvalue()


def interpret(records, *, fingerprint="abc123", fields=None, protocol="nec"):
    return catalog.interpret_signal(
        protocol=protocol,
        status="decoded" if protocol == "nec" else "unrecognized",
        fields=fields
        or {
            "irdb_device": 7,
            "irdb_subdevice": -1,
            "irdb_function": 2,
            "address_hex": "0x07",
            "command_hex": "0x02",
            "esphome_address": 0xF807,
            "esphome_command": 0xFD02,
        },
        fingerprint=fingerprint,
        raw="9000,-4500,560,-560",
        pulse_count=4,
        source="xiao-ir-listener",
        received_at="2026-10-07T10:00:00+00:00",
        records=records,
        local_codes={},
        database_source="irdb_online",
    )


class CatalogTests(unittest.TestCase):
    def test_exact_nec_match(self):
        archive = make_archive(
            {
                "irdb-master/codes/Acme/TV/7,-1.csv": (
                    "functionname,protocol,device,subdevice,function\n"
                    "POWER,NEC,7,-1,2\n"
                )
            }
        )
        records, stats = catalog.parse_irdb_archive(archive)
        result = interpret(records)

        self.assertEqual(stats.profiles, 1)
        self.assertEqual(stats.commands, 1)
        self.assertEqual(result.state, "Acme / TV / POWER")
        self.assertEqual(result.attributes["match_status"], "exact")
        self.assertEqual(result.attributes["replay"]["mode"], "nec")

    def test_ambiguous_match_lists_candidates(self):
        archive = make_archive(
            {
                "irdb-master/codes/Acme/TV/7,-1.csv": (
                    "functionname,protocol,device,subdevice,function\n"
                    "POWER,NEC,7,-1,2\n"
                ),
                "irdb-master/codes/Other/Projector/7,-1.csv": (
                    "functionname,protocol,device,subdevice,function\n"
                    "INPUT,NEC,7,-1,2\n"
                ),
            }
        )
        records, _ = catalog.parse_irdb_archive(archive)
        result = interpret(records)

        self.assertEqual(result.attributes["match_status"], "ambiguous")
        self.assertEqual(result.attributes["candidate_count"], 2)
        self.assertIsNotNone(result.unknown_state)

    def test_local_codebook_overrides_irdb(self):
        local_codes = {
            "abc123": {
                "label": "Living room TV / Power",
                "manufacturer": "Hisense",
                "device_type": "TV",
                "model": "75E5N",
                "function": "POWER",
            }
        }
        result = catalog.interpret_signal(
            protocol="nec",
            status="decoded",
            fields={"irdb_device": 7, "irdb_subdevice": -1, "irdb_function": 2},
            fingerprint="abc123",
            raw="9000,-4500",
            pulse_count=2,
            source="listener",
            received_at="2026-10-07T10:00:00+00:00",
            records={(7, -1, 2): [{"manufacturer": "Other"}]},
            local_codes=local_codes,
            database_source="irdb_online",
        )

        self.assertEqual(result.state, "Living room TV / Power")
        self.assertEqual(result.attributes["match_source"], "local_codebook")
        self.assertEqual(result.attributes["confidence"], "confirmed")

    def test_legacy_fingerprint_still_matches_local_codebook(self):
        result = catalog.interpret_signal(
            protocol="unknown",
            status="unrecognized",
            fields={},
            fingerprint="new-shape-key",
            fingerprint_aliases=("old-timing-key",),
            raw="500,-500",
            pulse_count=2,
            source="listener",
            received_at="2026-10-07T10:00:00+00:00",
            records={},
            local_codes={"old-timing-key": {"label": "Existing learned button"}},
            database_source="irdb_online",
        )

        self.assertEqual(result.state, "Existing learned button")
        self.assertEqual(result.attributes["local_codebook_key"], "old-timing-key")

    def test_unmatched_nec_is_retained(self):
        result = interpret({})
        self.assertEqual(result.attributes["match_status"], "unmatched")
        self.assertIsNotNone(result.unknown_state)
        self.assertEqual(result.attributes["replay"]["mode"], "nec")

    def test_unparsed_raw_is_retained_for_replay(self):
        result = interpret({}, protocol="unknown", fields={})
        self.assertEqual(result.attributes["match_status"], "unparsed")
        self.assertEqual(result.attributes["replay"]["mode"], "raw")
        self.assertTrue(result.attributes["unknown_segments"])

    def test_decoded_tcl_air_conditioner_is_not_marked_unparsed(self):
        result = catalog.interpret_signal(
            protocol="tcl112ac",
            status="decoded",
            fields={
                "summary": "Cool 24.5 C / Quiet fan",
                "model_family": "TCL112AC",
                "checksum_valid": True,
            },
            fingerprint="tcl-state-key",
            raw="3000,-1650",
            pulse_count=228,
            source="listener",
            received_at="2026-10-07T10:00:00+00:00",
            records={},
            local_codes={},
            database_source="irdb_online",
        )

        self.assertEqual(result.state, "TCL AC / Cool 24.5 C / Quiet fan")
        self.assertEqual(result.attributes["match_status"], "decoded")
        self.assertIsNone(result.unknown_state)

    def test_tcl_pair_exposes_two_frame_replay_sequence(self):
        frames = [
            {"action": "send_raw", "raw": "special"},
            {"action": "send_raw", "raw": "normal"},
        ]
        result = catalog.interpret_signal(
            protocol="tcl112ac",
            status="decoded",
            fields={
                "summary": "Cool 24 C / High steps 4 5",
                "checksum_valid": True,
                "replay_sequence": frames,
            },
            fingerprint="paired-state-key",
            raw="3000,-1650",
            pulse_count=228,
            source="listener",
            received_at="2026-10-07T10:00:00+00:00",
            records={},
            local_codes={},
            database_source="irdb_online",
        )

        self.assertEqual(result.attributes["replay"]["mode"], "raw_sequence")
        self.assertEqual(result.attributes["replay"]["frames"], frames)

    def test_invalid_or_empty_archive_is_rejected(self):
        with self.assertRaises(ValueError):
            catalog.parse_irdb_archive(b"not a zip")
        with self.assertRaises(ValueError):
            catalog.parse_irdb_archive(make_archive({"readme.txt": "empty"}))


if __name__ == "__main__":
    unittest.main()
