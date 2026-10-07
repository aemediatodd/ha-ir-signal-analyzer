from homeassistant.const import Platform


DOMAIN = "ir_signal_analyzer"
SERVICE_SEND_TCL112AC = "send_tcl112ac"
PLATFORMS = [
    Platform.SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SWITCH,
]

CONF_SOURCE = "source"
DEFAULT_NAME = "IR Signal Analyzer"
EVENT_IR_RECEIVED = "esphome.ir_received"
SIGNAL_UPDATE = f"{DOMAIN}_update"

CONF_TCL_PAIR_DELAY_MS = "tcl_pair_delay_ms"
DEFAULT_TCL_PAIR_DELAY_MS = 190
MIN_TCL_PAIR_DELAY_MS = 150
MAX_TCL_PAIR_DELAY_MS = 250

TCL_TEST_POWER = "tcl_test_power"
TCL_TEST_MODE = "tcl_test_mode"
TCL_TEST_TEMPERATURE = "tcl_test_temperature"
TCL_TEST_FAN_STEP = "tcl_test_fan_step"
TCL_TEST_SLEEP = "tcl_test_sleep"
TCL_TEST_SOFT_WIND = "tcl_test_soft_wind"
TCL_TEST_SWING_VERTICAL = "tcl_test_swing_vertical"
TCL_TEST_SWING_HORIZONTAL = "tcl_test_swing_horizontal"
TCL_TEST_AUXILIARY_HEAT = "tcl_test_auxiliary_heat"
TCL_TEST_REMOTE_PROFILE = "tcl_test_remote_profile"
TCL_REMOTE_PROFILE_TCL_ADVANCED = "TCL-高级"
TCL_TEST_MODE_OPTIONS = ["auto", "cool", "heat", "dry", "fan_only"]
TCL_TEST_FAN_OPTIONS = ["auto", "0", "1", "2", "3", "4", "5", "6"]
TCL_TEST_DEFAULTS = {
    TCL_TEST_POWER: True,
    TCL_TEST_MODE: "cool",
    TCL_TEST_TEMPERATURE: 24.0,
    TCL_TEST_FAN_STEP: "auto",
    TCL_TEST_SLEEP: False,
    TCL_TEST_SOFT_WIND: False,
    TCL_TEST_SWING_VERTICAL: False,
    TCL_TEST_SWING_HORIZONTAL: False,
    TCL_TEST_AUXILIARY_HEAT: False,
    TCL_TEST_REMOTE_PROFILE: TCL_REMOTE_PROFILE_TCL_ADVANCED,
}
TCL_TEST_TRANSMITTER_ACTION = "esphome.xiao_ir_transmitter_send_raw_pair"
TCL_VALIDATION_TIMEOUT_SECONDS = 30

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
