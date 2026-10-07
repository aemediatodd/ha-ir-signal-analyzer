# TCL112AC capture notes

This document and `tcl112ac-observations.json` preserve observed TCL air
conditioner remote frames for reuse by this integration and other projects.
They supplement the protocol implementation documented by
[IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266).

## Wire format

- Carrier: 38 kHz
- Header: approximately `3000us mark + 1650us space`
- Bit mark: approximately `500us`
- Zero space: approximately `325us`
- One space: approximately `1050us`
- Payload: 112 bits / 14 bytes, LSB-first within each byte
- Signature: bytes 0-2 are `23 CB 26`
- A typical ESPHome capture contains 228 signed pulse durations

Normal frames use message type `01` in byte 3. Type `02` frames are special
command frames and must not be interpreted as power-off merely because their
normal-frame power bit is clear. The observed remote sends a type-2 frame first
and a type-1 full-state frame immediately afterwards for each button action.

## Observed fields

| Field | Observation |
| --- | --- |
| Byte 5 bit 2 | Power in normal frames |
| Byte 5 bit 6 | Display off when set in observed normal frames |
| Byte 6 low nibble | Mode: `1` heat, `2` dry, `3` cool, `7` fan, `8` auto |
| Byte 6 bit 6 | Feature flag shared by observed turbo and sleep states; requires the preceding type-2 command to disambiguate |
| Byte 7 low nibble | Temperature: `31 - value`, plus 0.5 when byte 12 bit 5 is set |
| Byte 8 low 3 bits | Native fan group: 0 auto, 1 quiet/sleep, 2 steps 0-1, 3 steps 2-3, 5 steps 4-5 |
| Byte 8 bits 3-5 | Vertical swing; observed `7` means swing |
| Byte 12 bit 3 | Horizontal swing |
| Last byte | Sum of preceding bytes; type-2 frames add `0x0F` |

The special frame distinguishes remote fan steps that collapse into the same
native fan group in the following normal frame. For example, steps 0 and 1 both
produce native fan code 2, while steps 4 and 5 both produce code 5. Consumers
that need exact remote-button semantics should preserve and replay both frames
in their observed order.

The captured combination "cool, 24 C, automatic fan, soft wind, sleep" uses
special bytes `40 30 00` and a normal-frame fan code of 1. This differs from
soft wind alone (`40 D0 xx`) and from the earlier sleep/display-off sample
(`40 C0 08` plus the normal-frame feature flag). The encoder therefore treats
automatic-fan soft-wind sleep as its own observed command rather than inferring
it from either feature independently.

## Paired-frame timing

Eight Home Assistant observations measured the interval from the received
type-2 command frame to its following type-1 state frame:

```text
170, 193, 200, 187, 189, 191, 182, 189 ms
```

The range is 170-200 ms, the arithmetic mean is 187.625 ms, and the median is
189 ms. Encoders should use a nominal **190 ms delay** between the completed
type-2 transmission and the start of the type-1 transmission. This is an
application-layer observation and includes small ESPHome/API scheduling jitter;
receivers should tolerate at least the observed range rather than require an
exact interval.

## Home Assistant encoder

The integration action `ir_signal_analyzer.send_tcl112ac` builds both frames
from a complete requested state and converts each 14-byte frame to the observed
228-pulse waveform. It delegates the pair to the ESPHome `send_raw_pair` action,
so the 150-250 ms interval is executed on the transmitter rather than across
two Home Assistant service calls. The encoder reproduces the captured fan,
soft-wind, horizontal-swing, vertical-swing, turbo, and sleep samples byte for
byte. Unobserved conflicting feature combinations are rejected.

## Dataset cautions

These mappings are empirical observations from one TCL remote/air-conditioner
combination. TCL112AC is also used by related brands and model families, and
some feature bits differ between variants. Treat unobserved bits as unknown and
validate checksum and behavior on the target appliance before transmitting.
