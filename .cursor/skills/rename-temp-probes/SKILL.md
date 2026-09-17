---
name: rename-temp-probes
description: >-
  Rename thermistor temperature probes and keep every copy of the 12-channel
  name/order in sync. Use when the user wants to rename temp probes, rename
  thermistors, change thermistor labels, retitle temperature sensors, update
  temperature_sources, or make the temp sensor order the same everywhere.
---

# Rename temp probes

Logical UI / CSV / control temperatures come from the 12 ADS1115 thermistors.
**Source of truth** is `config.yaml` → `thermistor_sensors.labels` (channels 0–11).
Order of those labels is display order.

## Workflow

1. Read `thermistor_sensors.labels` and the user's new names.
2. Apply names to channel 0–11. Every name must be **unique** (YAML maps and reading dicts drop duplicates).
3. Copy the same 12 names, same order, into every list below.
4. Retarget config keys that still point at an old name.
5. Keep old `KNOWN_LABELS` entries so historical CSVs still decode.
6. Grep the old name(s) and update remaining hardcoded uses.
7. Run `python -m unittest tests.test_thermistor_reader tests.test_session_logs tests.test_flow_reader tests.test_cooling_power -v`.

Preserve the `Cartrige` spelling unless the user asks to fix it.

## Must stay identical (name + order)

| Location | What to set |
|---|---|
| `config.yaml` `thermistor_sensors.labels` | Channel 0–11 display names |
| `config.yaml` `temperature_sources` | Same 12 keys, each `thermistor` |
| `config.yaml` `simulation.thermistors` | Same 12 keys; keep prior °C if the name is unchanged |
| `src/log_analyzer.py` `_DEFAULT_TEMP_NAMES` | Same 12 names in order |
| `scripts/generate_operator_pdf.py` `TEMPS` | Same 12 keys (dummy °C ok) |

`tests/test_thermistor_reader.py` (`test_config_yaml_adds_four_thermistors_on_i2c6`) asserts labels 8–11 and that `temperature_sources` keys equal labels in channel order. Update the 8–11 expected list when those names change.

## Config keys that reference a probe by name

If that probe is renamed or removed, update the key to the new name (ask only if the replacement is ambiguous):

- `control_temp_label`
- `alarms.csf_label`, `alarms.heat_ex_label`
- `compressor.heat_ex_label` / `compressor.heat_ex_labels`
- `cooling_power.catheter_in_label` / `catheter_out_label` / `cartridge_in_label` / `cartridge_out_label`
- `simulation.csf_label`, `simulation.heat_ex_label`, `simulation.cart_in_label`, `simulation.cart_out_label`

`simulation.csf_label` drives thermistor sim physics (Tip / CSF cooling loop).

## Other hardcoded copies

- `src/session_logs.py` `KNOWN_LABELS`: add slugs for new names (`Hot bath1` → `hot_bath1`). Do not delete old slugs.
- `scripts/generate_operator_pdf.py`: any leftover string uses of the old name (`TEMPS["…"]`, CSF/heat-ex captions).
- `tests/test_flow_reader.py` asserts `labels[4] == "Cartrige In"` — update if channel 4 is renamed.
- `tests/test_session_logs.py` evaluation-sample check may still expect old CSV names; do not rewrite historical fixtures.

CSV slug rule (same as `CSVLogger._csv_slug`): lowercase, non-alnum → `_`, collapse `__`. Example: `Body Temp` → `body_temp`.

## Do not touch

- `pressure_sensors.labels`
- Digital GPIO sensor names
- Evaluation / historical session CSVs
