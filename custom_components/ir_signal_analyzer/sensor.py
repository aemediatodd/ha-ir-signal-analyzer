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
            IRProtocolSensor(entry, hub),
            IRCommandSensor(entry, hub),
        ]
    )


class IRLastReceivedSensor(IRSignalEntity, SensorEntity):
    _attr_name = "Last received"
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
            "pulse_count": len(signal.pulses),
            "raw": signal.raw,
            "decoded": signal.analysis.as_dict(),
            "last_error": self.hub.last_error,
        }


class IRProtocolSensor(IRSignalEntity, SensorEntity):
    _attr_name = "Protocol"
    _attr_icon = "mdi:code-braces"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_protocol"

    @property
    def native_value(self):
        return self.hub.last_signal.analysis.protocol if self.hub.last_signal else None


class IRCommandSensor(IRSignalEntity, SensorEntity):
    _attr_name = "Command"
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

