"""Online IRDB refresh, backup, and local codebook management."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from aiohttp import ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .catalog import CatalogStats, SignalInterpretation, interpret_signal, parse_irdb_archive


IRDB_ARCHIVE_URL = "https://github.com/probonopd/irdb/archive/refs/heads/master.zip"
IRDB_PROJECT_URL = "https://github.com/probonopd/irdb"
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024


class CatalogManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        data_dir = Path(hass.config.path("ir_signal_analyzer"))
        self.backup_path = data_dir / "irdb.zip"
        self.codebook_path = data_dir / "codebook.json"
        self.records: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
        self.local_codes: dict[str, dict[str, Any]] = {}
        self.stats = CatalogStats(0, 0)
        self.status = "not_loaded"
        self.source = "none"
        self.last_update: datetime | None = None
        self.last_error: str | None = None
        self.codebook_error: str | None = None
        self.backup_available = False
        self._refresh_lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Load local data immediately, then let the caller refresh online."""
        await self._async_load_codebook()
        await self._async_load_backup()

    async def async_refresh(self) -> None:
        async with self._refresh_lock:
            await self._async_refresh_locked()

    async def _async_refresh_locked(self) -> None:
        self.status = "updating"
        self.last_error = None
        await self._async_load_codebook()

        try:
            content = await self._async_download_archive()
            records, stats = await self.hass.async_add_executor_job(
                parse_irdb_archive, content
            )
            await self.hass.async_add_executor_job(self._write_backup, content)
            self.records = records
            self.stats = stats
            self.source = "irdb_online"
            self.status = "ready"
            self.last_update = datetime.now(timezone.utc)
            self.backup_available = True
            return
        except Exception as err:  # Network/parser errors fall back to the last backup.
            self.last_error = str(err)

        if not await self._async_load_backup():
            self.status = "unavailable"
            self.source = "none"

    async def _async_load_backup(self) -> bool:
        try:
            content = await self.hass.async_add_executor_job(self.backup_path.read_bytes)
            self.records, self.stats = await self.hass.async_add_executor_job(
                parse_irdb_archive, content
            )
            modified = await self.hass.async_add_executor_job(self.backup_path.stat)
        except FileNotFoundError:
            self.backup_available = False
            if self.status == "not_loaded":
                self.status = "no_snapshot"
            return False
        except Exception as err:
            self.backup_available = False
            self.last_error = _append_error(self.last_error, f"backup: {err}")
            return False

        self.source = "irdb_backup"
        self.status = "ready"
        self.last_update = datetime.fromtimestamp(modified.st_mtime, timezone.utc)
        self.backup_available = True
        return True

    def interpret(
        self,
        *,
        protocol: str,
        status: str,
        fields: dict[str, Any],
        fingerprint: str,
        raw: str,
        pulse_count: int,
        source: str,
        received_at: str,
    ) -> SignalInterpretation:
        return interpret_signal(
            protocol=protocol,
            status=status,
            fields=fields,
            fingerprint=fingerprint,
            raw=raw,
            pulse_count=pulse_count,
            source=source,
            received_at=received_at,
            records=self.records,
            local_codes=self.local_codes,
            database_source=self.source,
        )

    @property
    def attributes(self) -> dict[str, Any]:
        return {
            "primary_source": "irdb_online",
            "active_source": self.source,
            "online_url": IRDB_PROJECT_URL,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "cached_profiles": self.stats.profiles,
            "cached_commands": self.stats.commands,
            "backup_available": self.backup_available,
            "backup_path": str(self.backup_path),
            "local_codebook_path": str(self.codebook_path),
            "local_learned_codes": len(self.local_codes),
            "matching_order": ["local_codebook", "irdb_online", "irdb_backup"],
            "last_error": self.last_error,
            "codebook_error": self.codebook_error,
            "attribution": (
                "Contains/accesses irdb by Simon Peter and contributors, used "
                "under permission. https://github.com/probonopd/irdb"
            ),
        }

    async def _async_download_archive(self) -> bytes:
        session = async_get_clientsession(self.hass)
        timeout = ClientTimeout(total=60)
        async with session.get(IRDB_ARCHIVE_URL, timeout=timeout) as response:
            response.raise_for_status()
            content = await response.read()
        if len(content) > MAX_ARCHIVE_BYTES:
            raise ValueError("IRDB archive exceeds the 20 MiB safety limit")
        return content

    async def _async_load_codebook(self) -> None:
        self.codebook_error = None
        try:
            loaded = await self.hass.async_add_executor_job(self._read_codebook)
            self.local_codes = loaded
        except FileNotFoundError:
            self.local_codes = {}
        except Exception as err:
            self.local_codes = {}
            self.codebook_error = str(err)

    def _write_backup(self, content: bytes) -> None:
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.backup_path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(self.backup_path)

    def _read_codebook(self) -> dict[str, dict[str, Any]]:
        data = json.loads(self.codebook_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("codebook.json must contain an object keyed by fingerprint")
        result: dict[str, dict[str, Any]] = {}
        for fingerprint, record in data.items():
            if not isinstance(record, dict):
                raise ValueError(f"codebook entry {fingerprint!r} must be an object")
            result[str(fingerprint)] = record
        return result


def _append_error(existing: str | None, addition: str) -> str:
    return f"{existing}; {addition}" if existing else addition
