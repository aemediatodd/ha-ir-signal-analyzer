"""Pure IRDB parsing and signal interpretation helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from io import BytesIO, TextIOWrapper
from pathlib import PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile


MAX_CANDIDATES_IN_ATTRIBUTES = 10


@dataclass(frozen=True)
class CatalogStats:
    profiles: int
    commands: int


@dataclass(frozen=True)
class SignalInterpretation:
    state: str
    attributes: dict[str, Any]
    unknown_state: str | None = None
    unknown_attributes: dict[str, Any] | None = None


def parse_irdb_archive(
    content: bytes,
) -> tuple[dict[tuple[int, int, int], list[dict[str, Any]]], CatalogStats]:
    """Build a compact NEC device/subdevice/function index from an IRDB zip."""
    records: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    seen: dict[tuple[int, int, int], set[tuple[str, ...]]] = {}
    profiles = 0
    commands = 0

    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as err:
        raise ValueError("downloaded IRDB archive is not a valid zip file") from err

    with archive:
        for info in archive.infolist():
            filename = info.filename.replace("\\", "/")
            if info.is_dir() or "/codes/" not in filename or not filename.endswith(".csv"):
                continue
            relative = filename.split("/codes/", 1)[1]
            parts = PurePosixPath(relative).parts
            if len(parts) < 3:
                continue

            manufacturer = parts[0]
            device_type = parts[1]
            database_record = relative
            profile_has_nec = False

            with archive.open(info) as raw_file:
                text_file = TextIOWrapper(
                    raw_file,
                    encoding="utf-8-sig",
                    errors="replace",
                    newline="",
                )
                for row in csv.DictReader(text_file):
                    protocol = str(row.get("protocol", "")).strip()
                    if not protocol.upper().startswith("NEC"):
                        continue
                    try:
                        device = int(str(row.get("device", "")).strip())
                        subdevice = int(str(row.get("subdevice", "-1")).strip() or "-1")
                        function = int(str(row.get("function", "")).strip())
                    except ValueError:
                        continue

                    profile_has_nec = True
                    key = (device, subdevice, function)
                    candidate = {
                        "manufacturer": manufacturer,
                        "device_type": device_type,
                        "function": str(row.get("functionname", "UNKNOWN")).strip(),
                        "protocol": protocol,
                        "database_record": database_record,
                    }
                    identity = tuple(str(value) for value in candidate.values())
                    if identity in seen.setdefault(key, set()):
                        continue
                    seen[key].add(identity)
                    records.setdefault(key, []).append(candidate)
                    commands += 1

            if profile_has_nec:
                profiles += 1

    if not records:
        raise ValueError("IRDB archive contains no NEC command records")
    return records, CatalogStats(profiles=profiles, commands=commands)


def interpret_signal(
    *,
    protocol: str,
    status: str,
    fields: dict[str, Any],
    fingerprint: str,
    raw: str,
    pulse_count: int,
    source: str,
    received_at: str,
    records: dict[tuple[int, int, int], list[dict[str, Any]]],
    local_codes: dict[str, dict[str, Any]],
    database_source: str,
    fingerprint_aliases: tuple[str, ...] = (),
) -> SignalInterpretation:
    """Interpret one decoded signal using local labels and the IRDB index."""
    replay = _replay_payload(protocol, status, fields, raw)
    base = {
        "received_at": received_at,
        "source_device": source,
        "protocol": protocol,
        "decode_status": status,
        "fingerprint": fingerprint,
        "legacy_fingerprints": list(fingerprint_aliases),
        "pulse_count": pulse_count,
        "raw": raw,
        "replay": replay,
    }

    local_key = fingerprint
    local = local_codes.get(local_key)
    if local is None:
        for alias in fingerprint_aliases:
            if alias in local_codes:
                local_key = alias
                local = local_codes[alias]
                break
    if local is not None:
        candidates = _find_candidates(protocol, status, fields, records)
        label = str(local.get("label") or _candidate_label(local) or fingerprint)
        attributes = {
            **base,
            "match_status": "learned",
            "confidence": "confirmed",
            "match_source": "local_codebook",
            "manufacturer": local.get("manufacturer"),
            "device_type": local.get("device_type"),
            "model": local.get("model"),
            "function": local.get("function"),
            "local_label": label,
            "local_codebook_key": local_key,
            "known_fields": fields,
            "unknown_fields": [],
            "irdb_candidate_count": len(candidates),
            "irdb_candidates": candidates[:MAX_CANDIDATES_IN_ATTRIBUTES],
        }
        return SignalInterpretation(label[:255], attributes)

    candidates = _find_candidates(protocol, status, fields, records)
    if len(candidates) == 1:
        candidate = candidates[0]
        attributes = {
            **base,
            "match_status": "exact",
            "confidence": "high",
            "match_source": database_source,
            "candidate_count": 1,
            **candidate,
            "known_fields": fields,
            "unknown_fields": [],
        }
        return SignalInterpretation(_candidate_label(candidate)[:255], attributes)

    if len(candidates) > 1:
        attributes = {
            **base,
            "match_status": "ambiguous",
            "confidence": "low",
            "match_source": database_source,
            "candidate_count": len(candidates),
            "candidates": candidates[:MAX_CANDIDATES_IN_ATTRIBUTES],
            "known_fields": fields,
            "unknown_fields": ["manufacturer", "device_type", "model", "function"],
        }
        unknown = {
            **attributes,
            "unmatched_reason": "multiple IRDB candidates use this code",
        }
        return SignalInterpretation(
            f"Candidate match: {len(candidates)} devices",
            attributes,
            f"Ambiguous {fingerprint}",
            unknown,
        )

    if protocol == "tcl112ac" and status == "decoded":
        summary = str(fields.get("summary") or "Decoded TCL air conditioner state")
        attributes = {
            **base,
            "match_status": "decoded",
            "confidence": "high" if fields.get("checksum_valid") else "medium",
            "match_source": "protocol_decoder",
            "manufacturer": "TCL",
            "device_type": "air_conditioner",
            "model": fields.get("model_family"),
            "function": summary,
            "known_fields": fields,
            "unknown_fields": [] if fields.get("checksum_valid") else ["checksum"],
        }
        return SignalInterpretation(f"TCL AC / {summary}"[:255], attributes)

    if protocol == "nec" and status == "decoded":
        address = fields.get("address_hex", fields.get("address"))
        command = fields.get("command_hex", fields.get("command"))
        state = "NEC repeat" if fields.get("repeat") else f"Unmatched: NEC A={address} C={command}"
        attributes = {
            **base,
            "match_status": "unmatched",
            "confidence": "none",
            "match_source": database_source,
            "candidate_count": 0,
            "known_fields": fields,
            "unknown_fields": ["manufacturer", "device_type", "model", "function"],
            "unmatched_reason": "IRDB has no matching device/subdevice/function",
        }
        return SignalInterpretation(
            state[:255],
            attributes,
            f"Unmatched NEC {fingerprint}",
            attributes,
        )

    attributes = {
        **base,
        "match_status": "unparsed",
        "confidence": "none",
        "match_source": "none",
        "known_fields": {
            "fingerprint": fingerprint,
            "pulse_count": pulse_count,
        },
        "unknown_fields": [
            "protocol",
            "manufacturer",
            "device_type",
            "model",
            "function",
            "address",
            "command",
        ],
        "unknown_segments": [
            {
                "start_pulse": 0,
                "end_pulse": max(0, pulse_count - 1),
                "reason": "no supported protocol matched the waveform",
            }
        ],
    }
    return SignalInterpretation(
        f"Unparsed: RAW {fingerprint}",
        attributes,
        f"RAW {fingerprint} / {pulse_count} pulses",
        attributes,
    )


def _find_candidates(
    protocol: str,
    status: str,
    fields: dict[str, Any],
    records: dict[tuple[int, int, int], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if protocol != "nec" or status != "decoded" or fields.get("repeat"):
        return []
    required = ("irdb_device", "irdb_subdevice", "irdb_function")
    if any(name not in fields for name in required):
        return []
    key = tuple(int(fields[name]) for name in required)
    return records.get(key, [])


def _candidate_label(candidate: dict[str, Any]) -> str:
    return " / ".join(
        str(candidate.get(key))
        for key in ("manufacturer", "device_type", "function")
        if candidate.get(key)
    )


def _replay_payload(
    protocol: str,
    status: str,
    fields: dict[str, Any],
    raw: str,
) -> dict[str, Any]:
    replay_sequence = fields.get("replay_sequence")
    if replay_sequence:
        return {
            "mode": "raw_sequence",
            "frame_count": len(replay_sequence),
            "frames": replay_sequence,
        }
    if protocol == "nec" and status == "decoded" and not fields.get("repeat"):
        return {
            "mode": "nec",
            "action": "esphome.xiao_ir_transmitter_send_nec",
            "address": fields.get("esphome_address"),
            "address_hex": fields.get("esphome_address_hex"),
            "command": fields.get("esphome_command"),
            "command_hex": fields.get("esphome_command_hex"),
        }
    return {
        "mode": "raw",
        "action": "esphome.xiao_ir_transmitter_send_raw",
        "carrier_frequency": 38000,
        "raw": raw,
    }
