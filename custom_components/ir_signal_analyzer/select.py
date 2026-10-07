"""Decoder selector for IR Signal Analyzer."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import IRSignalHub
from .const import DECODER_OPTIONS, DOMAIN
from .entity import IRSignalEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: IRSignalHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IRDecoderSelect(entry, hub)])


class IRDecoderSelect(IRSignalEntity, SelectEntity):
    _attr_name = "Decoder"
    _attr_icon = "mdi:code-json"
    _attr_options = DECODER_OPTIONS

    def __init__(self, entry: ConfigEntry, hub: IRSignalHub) -> None:
        super().__init__(entry, hub)
        self._attr_unique_id = f"{entry.entry_id}_decoder"

    @property
    def current_option(self):
        return self.hub.decoder

    async def async_select_option(self, option: str) -> None:
        if option not in DECODER_OPTIONS:
            raise ValueError(f"Unsupported decoder: {option}")
        self.hub.set_decoder(option)

