# XIAO Smart IR Mate Signal Analyzer

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aemediatodd&repository=ha-ir-signal-analyzer&category=integration)

This bundle assigns two XIAO Smart IR Mate devices dedicated roles: one
continuous listener and one transmitter. Received signals are exposed as Home
Assistant entities with Recorder history.

## Entities

After installation, the integration creates:

- `sensor.ir_signal_last_received`: timestamp that changes for every received
  signal. Its attributes contain the raw timings, fingerprint, source, decoder,
  decode status, and decoded fields.
- `sensor.ir_signal_protocol`: the detected or selected protocol.
- `sensor.ir_signal_command`: the decoded command or data value.
- `sensor.ir_signal_data`: displays the IR data directly as its state. NEC
  signals show the protocol and complete encoded value; raw timings are shown
  for unknown signals. Long raw states are truncated to Home Assistant's
  255-character limit while the complete value remains in the `raw` attribute.
- `select.ir_signal_decoder`: selects `auto`, `nec`, or `raw`. Changing this
  re-analyzes the most recently received signal.

Because the last-received sensor state is a timestamp, repeated presses of the
same remote button still create separate Recorder history entries.

## 1. Flash both XIAO devices

1. Flash `esphome/xiao-ir-mate-listener.yaml` to the dedicated listener.
2. Flash `esphome/xiao-ir-mate-transmitter.yaml` to the dedicated transmitter.
3. Add these values to the ESPHome `secrets.yaml` used by both configurations:

   ```yaml
   wifi_ssid: "YOUR_WIFI_NAME"
   wifi_password: "YOUR_WIFI_PASSWORD"
   api_encryption_key: "YOUR_32_BYTE_BASE64_KEY"
   ota_password: "YOUR_OTA_PASSWORD"
   ```

4. Validate, compile, and install both configurations.
5. Add both ESPHome devices to Home Assistant.
6. On the ESPHome integration page, select **Configure** for the listener and
   enable **Allow the device to perform Home Assistant actions**. This is
   required for the `esphome.ir_received` event.

The listener only enables the official receiver entity and sends every captured
raw signal to the Home Assistant event bus. The transmitter only enables the
official transmitter entity and Home Assistant actions for raw and NEC
transmission. `dump: all` also prints protocol guesses, Pronto, and raw data to
the listener's ESPHome DEBUG log.

## 2. Install the Home Assistant integration

Recommended HACS installation:

1. Open **HACS > Integrations**.
2. Select **Custom repositories** from the top-right menu.
3. Enter `https://github.com/aemediatodd/ha-ir-signal-analyzer` and choose
   **Integration**, or use the HACS button at the top of this document.
4. Find and download **IR Signal Analyzer**.
5. Restart Home Assistant.
6. Open **Settings > Devices & services > Add integration** and add
   **IR Signal Analyzer**.

For manual installation, copy:

```text
custom_components/ir_signal_analyzer
```

to:

```text
/config/custom_components/ir_signal_analyzer
```

Restart Home Assistant, then add **IR Signal Analyzer**.

Set the source filter to `xiao-ir-listener`. Leaving it empty accepts all
listeners, which is useful only when their histories should be combined.

## Recommended two-device layout

- Use `xiao-ir-transmitter` near the appliance as the main transmitter.
- Use `xiao-ir-listener` as the always-on listener.
- Keep the analyzer source filter set to `xiao-ir-listener`.

A transmitter's own receiver can see its outgoing IR. A separate listener is
the reliable way to distinguish other physical remotes while transmission is
in progress. Position it so that it sees the room but is not directly saturated
by the main transmitter. The transmitter firmware does not enable its receiver,
so it cannot create duplicate listening events.

## 3. Verify reception

Open **Developer tools > Events**, listen for `esphome.ir_received`, and press a
remote button. The event should contain `source`, `raw`, and `pulse_count`.

The integration parses that event and updates its entities. The normal Home
Assistant Recorder stores entity history; no separate log-file integration is
required.

To replay the latest captured raw signal through the dedicated transmitter:

```yaml
action: esphome.xiao_ir_transmitter_send_raw
data:
  code: >-
    {{ (state_attr('sensor.ir_signal_last_received', 'raw') or '').split(',')
       | map('int') | list }}
  carrier_frequency: 38000
```

Example dashboard card:

```yaml
type: entities
title: IR Signal Analyzer
entities:
  - entity: sensor.ir_signal_last_received
  - entity: sensor.ir_signal_data
  - entity: sensor.ir_signal_protocol
  - entity: sensor.ir_signal_command
  - entity: select.ir_signal_decoder
```

To display the complete current signal (adjust the entity ID if Home Assistant
assigned a suffix):

````yaml
type: markdown
content: |-
  **Fingerprint:** {{ state_attr('sensor.ir_signal_last_received', 'fingerprint') }}

  **Decoded:**
  ```json
  {{ state_attr('sensor.ir_signal_last_received', 'decoded') | to_json(pretty_print=true) }}
  ```

  **Raw timings:**
  ```text
  {{ state_attr('sensor.ir_signal_last_received', 'raw') }}
  ```
````

## Decoder behavior

- `auto` currently tries NEC.
- A specific decoder forces analysis with that encoding and reports a useful
  mismatch error when the waveform does not fit.
- `raw` performs no protocol decoding but still records the complete waveform.
- Unknown signals are retained with a stable SHA-256-derived fingerprint, so a
  decoder can be added later without recapturing the remote.

The XIAO IR Mate receiver is a demodulating receiver intended mainly for 38 kHz
IR. It cannot truly capture every carrier frequency. Long air-conditioner frames
may also exceed the ESP32-C3 RMT hardware capacity; use an ESP32-S3 listener for
those signals if captures are truncated.

## References

- [Official XIAO IR Mate ESPHome configuration](https://github.com/esphome/infrared-proxies/blob/main/xiao-ir-mate/xiao-ir-mate.yaml)
- [ESPHome remote receiver documentation](https://esphome.io/components/remote_receiver/)
- [ESPHome Home Assistant event action](https://esphome.io/components/api/#homeassistantevent-action)
