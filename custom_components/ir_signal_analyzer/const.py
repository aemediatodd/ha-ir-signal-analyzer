from homeassistant.const import Platform


DOMAIN = "ir_signal_analyzer"
PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.BUTTON]

CONF_SOURCE = "source"
DEFAULT_NAME = "IR Signal Analyzer"
EVENT_IR_RECEIVED = "esphome.ir_received"
SIGNAL_UPDATE = f"{DOMAIN}_update"

DECODER_AUTO = "auto"
DECODER_RAW = "raw"
DECODER_NEC = "nec"

DECODER_OPTIONS = [
    DECODER_AUTO,
    DECODER_NEC,
    DECODER_RAW,
]
