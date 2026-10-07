"""Sensors for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import DOMAIN
from .entity import IRSignalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: IRSignalHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            IRLastReceivedSensor(entry, hub),
            IRSignalDataSensor(entry, hub),
            IRSignalAnalysisSensor(entry, hub),
            IRUnparsedSignalSensor(entry, hub),
            IRDatabaseStatusSensor(entry, hub),
            IRDBSnapshotUpdatedSensor(entry, hub),
            IRProtocolSensor(entry, hub),
            IRCommandSensor(entry, hub),
        ]
    )


class IRLastReceivedSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "last_received"
    _attr_icon = "mdi:remote"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_last_received"

    @property
    def native_value(self):
        return self.hub.last_signal.received_at if self.hub.last_signal else None

    @property
    def extra_state_attributes(self):
        signal = self.hub.last_signal
        if signal is None:
            return {"decoder": self.hub.decoder, "last_error": self.hub.last_error}
        return {
            "source": signal.source,
            "decoder": self.hub.decoder,
            "detected_protocol": signal.analysis.protocol,
            "decode_status": signal.analysis.status,
            "fingerprint": signal.fingerprint,
            "shape_fingerprint": signal.shape_fingerprint,
            "legacy_fingerprint": signal.legacy_fingerprint,
            "pulse_count": len(signal.pulses),
            "device_sequence": signal.device_sequence,
            "device_uptime_ms": signal.device_uptime_ms,
            "raw": signal.raw,
            "decoded": signal.analysis.as_dict(),
            "last_error": self.hub.last_error,
        }


class IRProtocolSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "protocol"
    _attr_icon = "mdi:code-braces"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_protocol"

    @property
    def native_value(self):
        return self.hub.last_signal.analysis.protocol if self.hub.last_signal else None


class IRSignalDataSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "signal_data"
    _attr_icon = "mdi:pulse"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_signal_data"

    @property
    def native_value(self):
        signal = self.hub.last_signal
        if signal is None:
            return None

        analysis = signal.analysis
        data_hex = analysis.fields.get("data_hex")
        if data_hex:
            return f"{analysis.protocol.upper()} {data_hex}"
        if analysis.fields.get("repeat"):
            return f"{analysis.protocol.upper()} repeat"
        if len(signal.raw) <= 255:
            return signal.raw
        return f"{signal.raw[:220]}... [{signal.fingerprint}]"

    @property
    def extra_state_attributes(self):
        signal = self.hub.last_signal
        if signal is None:
            return None
        return {
            "source": signal.source,
            "protocol": signal.analysis.protocol,
            "decode_status": signal.analysis.status,
            "fingerprint": signal.fingerprint,
            "shape_fingerprint": signal.shape_fingerprint,
            "legacy_fingerprint": signal.legacy_fingerprint,
            "pulse_count": len(signal.pulses),
            "device_sequence": signal.device_sequence,
            "device_uptime_ms": signal.device_uptime_ms,
            "raw": signal.raw,
            "decoded": signal.analysis.as_dict(),
        }


class IRCommandSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "command"
    _attr_icon = "mdi:remote-tv"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_command"

    @property
    def native_value(self):
        if self.hub.last_signal is None:
            return None
        fields = self.hub.last_signal.analysis.fields
        return fields.get("command_hex") or fields.get("data_hex") or "unknown"

    @property
    def extra_state_attributes(self):
        if self.hub.last_signal is None:
            return None
        return self.hub.last_signal.analysis.as_dict()


class IRSignalAnalysisSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "signal_analysis"
    _attr_icon = "mdi:database-search"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_signal_analysis"

    @property
    def native_value(self):
        result = self.hub.last_interpretation
        return result.state if result else None

    @property
    def extra_state_attributes(self):
        result = self.hub.last_interpretation
        return result.attributes if result else None


class IRUnparsedSignalSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "unparsed_signal"
    _attr_icon = "mdi:help-rhombus"

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_unparsed_signal"

    @property
    def native_value(self):
        result = self.hub.last_unknown
        return result.unknown_state if result else None

    @property
    def extra_state_attributes(self):
        result = self.hub.last_unknown
        return result.unknown_attributes if result else None


class IRDatabaseStatusSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "ir_database_status"
    _attr_icon = "mdi:database-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_database_status"

    @property
    def native_value(self):
        return self.hub.catalog.status

    @property
    def extra_state_attributes(self):
        return self.hub.catalog.attributes


class IRDBSnapshotUpdatedSensor(IRSignalEntity, SensorEntity):
    _attr_translation_key = "irdb_snapshot_updated"
    _attr_icon = "mdi:calendar-clock"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_irdb_snapshot_updated"

    @property
    def native_value(self):
        return self.hub.catalog.last_update
