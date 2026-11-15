<p align="center">
  <img src="assets/banner.svg" alt="ellmos-homecontrol banner" width="100%">
</p>

# ellmos-homecontrol

**English** | [Deutsch](README_de.md)

Smart-home and household appliance control hub for the ellmos ecosystem (BACH, Open Ocean). It defines a device model, four adapter classes and a tool-shaped hub API (`hc_*`) with a confirmation gate for high-load and safety-critical devices. A small, dependency-free Python package.

> **Status: early (v0.1.0), demo-level.** Only the FritzBox adapter contains real protocol code (a TR-064 SOAP helper). The Home Assistant, Matter and MQTT/Shelly adapters currently only hold connection settings. `HomeControlHub` works on an **in-memory device registry**: unless you pass your own devices it uses four built-in sample devices, and every result is marked `"demo": true`. `hc_set_state` changes that in-memory state; it does not send commands to real devices yet.

## What it does

- **`HomeControlHub`** exposes the tool surface:
  - `hc_list_devices(adapter=None)`, `hc_get_state(device_id)`
  - `hc_set_state(device_id, target_state, confirmed=False)`
  - `hc_scene_activate(scene_id)` (built-in scenes `focus_work` and `evening_calm`)
  - `hc_energy_status()` (summed power, per adapter)
- **Permission gate:** with `smarthome_permission=False` every call raises `PermissionError`.
- **Confirmation gate:** `hc_set_state` raises `HighLoadConfirmationRequiredError` unless `confirmed=True` when the device
  - has `requires_confirmation`, or
  - is of kind `oven`, `stove`, `lock`, `garage_door` or `heater_high_load`, or
  - is rated above 2000 W and is not a plain `plug`.
- **`HomeDevice`**: frozen dataclass (`device_id`, `name`, `adapter`, `kind`, `state`, `power_watts`, `max_rated_watts`, `requires_confirmation`).
- **Adapters** (`fritzbox`, `homeassistant`, `matter`, `mqtt_shelly`):
  - `FritzBoxAdapter.tr064_call(service, action, params)` builds and sends a TR-064 SOAP request (2.5 s timeout, default base URL `http://fritz.box:49000`). Action and parameter names are validated and all values are XML-escaped; invalid names return `None`. `xml_value(xml, tag)` extracts a value from a response.
  - `HomeAssistantAdapter`, `MatterBridgeAdapter`, `MqttShellyAdapter`: configuration holders (base URL, fabric name, broker host and port) without network code.

## Installation

Requires Python 3.10 or newer; there are no runtime dependencies. From a clone:

```bash
pip install -e .
pip install -e ".[dev]"   # pytest
```

## Usage

```bash
ellmos-homecontrol list --adapter fritzbox
ellmos-homecontrol get ha.light.studio_main
ellmos-homecontrol set ha.light.studio_main '{"brightness_pct": 50}'
ellmos-homecontrol set shelly.appliance.washer '{"on": true}' --confirm
ellmos-homecontrol scene evening_calm
ellmos-homecontrol energy
```

```python
from ellmos_homecontrol.hub import HomeControlHub, HomeDevice

hub = HomeControlHub(devices=[
    HomeDevice("plug.desk", "Desk plug", "fritzbox", "plug", {"on": True}, power_watts=40, max_rated_watts=2300),
])
print(hub.hc_energy_status()["total_power_watts"])   # 40.0, demo is False for custom devices
```

Tests live in `tests/test_homecontrol.py` (run with `pytest`).

## Relation to ellmos and Open Ocean

`ellmos-homecontrol` is one of the extension modules listed in the [Open Ocean](https://github.com/ellmos-ai/open-ocean) module map. Its FritzBox code was extracted from the smart-home handler of [BACH](https://github.com/ellmos-ai/bach). Module metadata is in `ellmos-module.v2.json`.

## License

MIT, as declared in `pyproject.toml`.
