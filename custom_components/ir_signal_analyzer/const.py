from homeassistant.const import Platform


DOMAIN = "ir_signal_analyzer"
PLATFORMS = [Platform.SENSOR, Platform.SELECT, Platform.BUTTON, Platform.NUMBER]

CONF_SOURCE = "source"
DEFAULT_NAME = "IR Signal Analyzer"
EVENT_IR_RECEIVED = "esphome.ir_received"
SIGNAL_UPDATE = f"{DOMAIN}_update"

CONF_TCL_PAIR_DELAY_MS = "tcl_pair_delay_ms"
DEFAULT_TCL_PAIR_DELAY_MS = 190
MIN_TCL_PAIR_DELAY_MS = 150
MAX_TCL_PAIR_DELAY_MS = 250

DECODER_AUTO = "auto"
DECODER_RAW = "raw"
DECODER_NEC = "nec"
DECODER_TCL112AC = "tcl112ac"

DECODER_OPTIONS = [
    DECODER_AUTO,
    DECODER_TCL112AC,
    DECODER_NEC,
    DECODER_RAW,
]
