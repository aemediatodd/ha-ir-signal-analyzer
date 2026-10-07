# XIAO Smart IR Mate Signal Analyzer

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aemediatodd&repository=ha-ir-signal-analyzer&category=integration)

This bundle assigns two XIAO Smart IR Mate devices dedicated roles: one
continuous listener and one transmitter. Received signals are exposed as Home
Assistant entities with Recorder history.

Every entity name and decoder option includes English and Simplified Chinese
translations. Home Assistant selects them from the current user's interface
language and falls back to English for other languages.

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
- `sensor.ir_signal_analysis`: displays the best local-codebook or IRDB match.
  Its attributes contain manufacturer, device type, function, candidates,
  unknown fields, and a structured replay payload.
- `sensor.ir_signal_unparsed_signal`: retains the most recent unmatched or
  ambiguous signal separately for later analysis.
- `sensor.ir_signal_ir_database_status`: reports the active database source,
  cached record counts, errors, and local codebook status.
- `sensor.ir_signal_irdb_snapshot_updated`: timestamp of the snapshot currently
  stored on disk and used for offline matching.
- `button.ir_signal_refresh_irdb_snapshot`: manually downloads and validates a
  fresh IRDB snapshot, updates the timestamp, reloads the local codebook, and
  re-analyzes the latest captured signal.
- **Remote 2-frame interval**: configures the TCL inter-frame
  transmit delay from 150 to 250 ms in 1 ms steps; it defaults to 190 ms and is
  persisted across restarts.
- `select.ir_signal_decoder`: selects `auto`, `nec`, or `raw`. Changing this
  re-analyzes the most recently received signal.
- A TCL validation workbench exposes one shared set of power, mode,
  temperature, fan-step, sleep, soft-wind, and swing controls; two buttons start
  original-remote capture or generated-transmission testing.
- **TCL validation result** reports `waiting`, `matched`, `semantic_match`,
  `mismatch`, `timed_out`, or `error`, with expected/captured frames and byte
  differences in its attributes.
- **TCL validated combination** shows the latest byte-exact original-remote
  match and the number of persisted validated combinations.

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
the listener's ESPHome DEBUG log when temporarily enabled for troubleshooting.
The supplied low-latency listener configuration keeps protocol dumping disabled
during normal operation so log traffic cannot delay Home Assistant events.

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

The transmitter also exposes ESPHome's official `TCL Air Conditioner` climate
entity for basic controls and a device-timed `send_raw_pair` action for advanced
TCL command/state pairs. The `ir_signal_analyzer.send_tcl112ac` Home Assistant
action generates both frames from power, mode, temperature, remote fan step,
sleep, soft-wind, vertical-swing, and horizontal-swing parameters. Importable
scripts are provided in `examples/` for generated control and captured replay.

Example generated control:

```yaml
action: ir_signal_analyzer.send_tcl112ac
data:
  transmitter_action: esphome.xiao_ir_transmitter_send_raw_pair
  power: true
  mode: cool
  temperature: 24
  fan_step: "5"
  sleep: false
  soft_wind: true
  swing_vertical: false
  swing_horizontal: true
```

Modes are `auto`, `cool`, `heat`, `dry`, and `fan_only`; temperature is 16-31 C
in 0.5 C steps; fan step is `auto` or remote steps 0-6. Omitting `delay_ms`
uses the configured Remote 2-frame interval. Soft wind is restricted to the
observed fan-step-5 combination when used alone. The captured combined
soft-wind and sleep command uses automatic fan with both swing modes disabled;
other unobserved conflicting combinations are rejected.

## TCL validation workbench

Use `examples/ha-dashboard-tcl-validation-workbench.yaml` as an Entities card,
replacing entity IDs if Home Assistant added a prefix or suffix. Select the
complete candidate state, press **Wait for original remote sample**, and send
the same state once from the physical remote within 30 seconds. A byte-exact
pair is persisted to
`/config/ir_signal_analyzer/tcl112ac-validated.json`.

Press **Send encoded test** to generate and transmit the selected pair. The
dedicated listener captures the transmission and reports the comparison with
source `generated_echo`. Generated loopback tests never create original-remote
evidence. A semantic match indicates known decoded fields agree but unknown
bytes differ, so it is retained for analysis rather than marked validated.

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
  - entity: sensor.ir_signal_signal_analysis
  - entity: sensor.ir_signal_unparsed_signal
  - entity: sensor.ir_signal_ir_database_status
  - entity: sensor.ir_signal_irdb_snapshot_updated
  - entity: button.ir_signal_refresh_irdb_snapshot
  - entity: sensor.ir_signal_protocol
  - entity: sensor.ir_signal_command
  - entity: select.ir_signal_decoder
```

## IRDB matching and local labels

On startup, the integration loads the saved snapshot first so Home Assistant is
not blocked by a network request, then refreshes it in the background. Press
**Refresh IRDB snapshot** whenever you want to force an update. A validated
download is saved as `/config/ir_signal_analyzer/irdb.zip`; if GitHub is
unavailable, the last valid copy remains active. The snapshot timestamp entity
shows the modification time of that usable local copy.

IRDB matches are candidates, not guaranteed identifications: NEC addresses are
not globally unique, so one signal may match several products. A local learned
entry keyed by signal fingerprint always takes priority. Create
`/config/ir_signal_analyzer/codebook.json`, for example:

```json
{
  "824e21a380d457f1": {
    "label": "Living room TV / Power",
    "manufacturer": "Hisense",
    "device_type": "TV",
    "model": "75E5N",
    "function": "POWER",
    "location": "Living room"
  }
}
```

After editing the file, press the refresh button to reload it. Matching order is
local codebook, current online snapshot, then the local backup. Samsung and Sony
waveform decoding are not implemented in this release; their raw signals remain
available for replay and future decoding.

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

- `auto` currently tries TCL112AC full-state air-conditioner frames and NEC.
- A specific decoder forces analysis with that encoding and reports a useful
  mismatch error when the waveform does not fit.
- `raw` performs no protocol decoding but still records the complete waveform.
- Unknown signals are retained with a stable SHA-256-derived fingerprint, so a
  decoder can be added later without recapturing the remote.
- Since `v1.1.2`, raw fingerprints hash timing-cluster shapes rather than fixed
  microsecond rounding. Small receiver jitter therefore keeps the same key,
  while different pulse patterns remain distinct. `legacy_fingerprint` is
  retained as a compatibility key for existing local codebooks.
- TCL112AC decoding exposes power, mode, 0.5 C temperature steps, fan, swing,
  health, turbo, economy, display-light, and checksum fields. Its primary
  fingerprint hashes the decoded 14-byte state, so identical settings remain
  stable across timing jitter while 24.0 C and 24.5 C remain distinct.
- Observed remotes send a type-2 command frame followed by a type-1 full-state
  frame. The integration links pairs received within 1.5 seconds and exposes an
  ordered two-frame `replay_sequence`. Reusable captures and field notes are in
  `reference/tcl112ac-observations.json` and `reference/TCL112AC.md`.

The XIAO IR Mate receiver is a demodulating receiver intended mainly for 38 kHz
IR. It cannot truly capture every carrier frequency. Long air-conditioner frames
may also exceed the ESP32-C3 RMT hardware capacity; use an ESP32-S3 listener for
those signals if captures are truncated.

## References

- [Official XIAO IR Mate ESPHome configuration](https://github.com/esphome/infrared-proxies/blob/main/xiao-ir-mate/xiao-ir-mate.yaml)
- [ESPHome remote receiver documentation](https://esphome.io/components/remote_receiver/)
- [ESPHome Home Assistant event action](https://esphome.io/components/api/#homeassistantevent-action)
- [IRDB](https://github.com/probonopd/irdb) - see
  [IRDB attribution](IRDB_ATTRIBUTION.md)
