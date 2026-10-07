"""IR Signal Analyzer integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_SOURCE,
    DECODER_AUTO,
    DOMAIN,
    EVENT_IR_RECEIVED,
    PLATFORMS,
    SIGNAL_UPDATE,
)
from .decoder import DecodeResult, analyze, fingerprint, parse_raw


@dataclass
class CapturedSignal:
    received_at: datetime
    source: str
    raw: str
    pulses: list[int]
    fingerprint: str
    analysis: DecodeResult


class IRSignalHub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.source_filter = str(entry.data.get(CONF_SOURCE, "")).strip()
        self.decoder = str(entry.options.get("decoder", DECODER_AUTO))
        self.last_signal: CapturedSignal | None = None
        self.last_error: str | None = None

    @callback
    def handle_event(self, event: Event) -> None:
        source = str(event.data.get("source", "unknown"))
        if self.source_filter and source != self.source_filter:
            return

        try:
            pulses = parse_raw(event.data.get("raw", ""))
            raw = ",".join(str(value) for value in pulses)
            self.last_signal = CapturedSignal(
                received_at=datetime.now(timezone.utc),
                source=source,
                raw=raw,
                pulses=pulses,
                fingerprint=fingerprint(pulses),
                analysis=analyze(pulses, self.decoder),
            )
            self.last_error = None
        except (TypeError, ValueError) as err:
            self.last_error = str(err)

        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")

    @callback
    def set_decoder(self, decoder: str) -> None:
        self.decoder = decoder
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, "decoder": decoder},
        )
        if self.last_signal is not None:
            self.last_signal.analysis = analyze(self.last_signal.pulses, decoder)
        async_dispatcher_send(self.hass, f"{SIGNAL_UPDATE}_{self.entry.entry_id}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = IRSignalHub(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    entry.async_on_unload(hass.bus.async_listen(EVENT_IR_RECEIVED, hub.handle_event))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded

