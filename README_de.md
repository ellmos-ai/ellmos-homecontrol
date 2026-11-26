<p align="center">
  <img src="assets/banner.svg" alt="ellmos-homecontrol banner" width="100%">
</p>

# ellmos-homecontrol

[English](README.md) | **Deutsch**

Steuerzentrale für Smart Home, Haushaltsgeräte und herstellerneutrale Router im ellmos-Ökosystem (BACH, Open Ocean). Das Paket definiert ein Gerätemodell, vier Smart-Home-Adapterklassen, eine herstellerneutrale `RouterAdapter`-Schicht (`FritzBoxRouterAdapter`, `HuaweiHiLinkRouterAdapter`, `GenericGatewayAdapter`) sowie eine werkzeugförmige Hub-API (`hc_*`) mit Bestätigungs- und Autoritäts-Gates. Ein kleines, abhängigkeitsfreies Python-Paket.

> **Status: early (v0.1.0).** `FritzBoxAdapter` / `FritzBoxRouterAdapter` (TR-064 SOAP mit HTTP-Digest-Auth und Pflicht-Readback per `GetInfo`) sowie `HuaweiHiLinkRouterAdapter` (lesend über `/api/device/basic_information` & `/api/monitoring/status`) enthalten echten lokalen Protokollcode. Die Adapter für Home Assistant, Matter und MQTT/Shelly halten bisher Verbindungseinstellungen. `HomeControlHub` arbeitet auf einer **Geräteregistry im Arbeitsspeicher**: Ohne eigene Geräte werden vier eingebaute Beispielgeräte verwendet, und jedes Geräteergebnis trägt `"demo": true`.

## Funktionen

- **`HomeControlHub`** bietet die Werkzeugoberfläche:
  - `hc_list_devices(adapter=None)`, `hc_get_state(device_id)`
  - `hc_set_state(device_id, target_state, confirmed=False)`
  - `hc_scene_activate(scene_id)` (eingebaute Szenen `focus_work` und `evening_calm`)
  - `hc_energy_status()` (Gesamtleistung, je Adapter)
  - `hc_router_discover(gateway_ip="192.0.2.1")`, `hc_router_status()`, `hc_router_hosts()`, `hc_router_wifi_status()` (`network-observer`-Rolle, Tier 1)
  - `hc_router_set_guest_wifi(enabled, confirmed=..., evidence_quote=...)` (Tier 2) und `hc_router_set_wifi(enabled, confirmed=..., hard_gate_ack=...)` (Tier-3-Hard-Gate beim Abschalten des Haupt-WLANs)
- **Berechtigungs-Gate:** Mit `smarthome_permission=False` löst jeder Aufruf `PermissionError` aus.
- **Bestätigungs-Gate:** `hc_set_state` löst `HighLoadConfirmationRequiredError` aus, solange nicht `confirmed=True` gesetzt ist, wenn das Gerät
  - `requires_confirmation` hat, oder
  - vom Typ `oven`, `stove`, `lock`, `garage_door` oder `heater_high_load` ist, oder
  - über 2000 W ausgelegt und kein einfacher `plug` ist.
- **Herstellerneutraler `RouterAdapter` & `discover_router()`:**
  - Prüft TCP-Port `:49000` vor jedem AVM-TR-064-Zugriff (`FritzBoxRouterAdapter`), erkennt Huawei-HiLink-Gateways über `/api/device/basic_information` (`HuaweiHiLinkRouterAdapter`) und fällt sonst sicher auf `GenericGatewayAdapter` zurück.
  - Erzwingt nach jedem `SetEnable`-Schaltbefehl einen `GetInfo`-Readback (`verified: true/false`), löst Zugangsdaten über OS-`keyring` -> `ELLMOS_HOMECONTROL_CREDENTIALS_DIR` auf und maskiert Passwörter sowie `SesInfo`/`TokInfo`-Tokens in allen Fehlertexten.
  - Meldet nicht unterstützte Schreiboperationen klar mit `UnsupportedCapabilityError`.

## Installation

Benötigt Python 3.10 oder neuer; es gibt keine Laufzeitabhängigkeiten. Aus einem Klon:

```bash
pip install -e .
pip install -e ".[dev]"   # pytest
```

## Nutzung

```bash
ellmos-homecontrol list --adapter fritzbox
ellmos-homecontrol get ha.light.studio_main
ellmos-homecontrol set ha.light.studio_main '{"brightness_pct": 50}'
ellmos-homecontrol set shelly.appliance.washer '{"on": true}' --confirm
ellmos-homecontrol scene evening_calm
ellmos-homecontrol energy
ellmos-homecontrol router-discover --gateway 192.0.2.1
ellmos-homecontrol router-status --gateway 192.0.2.1
ellmos-homecontrol router-set-guest-wifi on --gateway 192.0.2.1 --confirm
```

```python
from ellmos_homecontrol.hub import HomeControlHub, HomeDevice

hub = HomeControlHub(devices=[
    HomeDevice("plug.desk", "Schreibtisch-Steckdose", "fritzbox", "plug", {"on": True}, power_watts=40, max_rated_watts=2300),
])
print(hub.hc_energy_status()["total_power_watts"])   # 40.0, demo ist bei eigenen Geräten False
```

Die Tests liegen in `tests/test_homecontrol.py` und `tests/test_router_adapter.py` (Aufruf mit `pytest`).

## Bezug zu ellmos und Open Ocean

`ellmos-homecontrol` gehört zu den Erweiterungsmodulen in der Modulzuordnung von [Open Ocean](https://github.com/ellmos-ai/open-ocean). Der FritzBox-Code wurde aus dem Smart-Home-Handler von [BACH](https://github.com/ellmos-ai/bach) extrahiert. Die Modul-Metadaten sowie die Rollen `network-observer` und `router-operator` stehen in `ellmos-module.v2.json`.

## Lizenz

MIT, wie in `pyproject.toml` angegeben.
