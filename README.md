# ellmos-homecontrol

SmartHome- & Haushaltsgeräte-Steuerung (`OCEAN-HOMECONTROL-01`, BACH `#3766` / Ocean `#536`) für BACH und Open-Ocean.

## Unterstützte Adapter & MCP-Tools

1. **Adapter:**
   - `FritzBoxAdapter`: FritzBox TR-064 (UPnP/SOAP) & DECT-200/210/301 Smart-Plugs/Thermostate (extrahiert aus `bach/system/hub/smarthome.py`).
   - `HomeAssistantAdapter`: REST/WebSocket-Bridge für Licht, Klima, Rollläden, Saugroboter, Waschmaschine/Spülmaschine.
   - `MatterBridgeAdapter`: Lokale Matter-over-Thread / Wi-Fi Geräte.
   - `MqttShellyAdapter`: Lokale MQTT/Tasmota/Shelly Leistungs- und Schaltaktoren.
2. **MCP-Tool-Oberfläche (`HomeControlHub`):**
   - `hc_list_devices`
   - `hc_get_state`
   - `hc_set_state` (inkl. Sicherheits-Gate für Hochlastgeräte > 2000 W / Öfen / Schlösser: erfordert `confirmed=True`)
   - `hc_scene_activate`
   - `hc_energy_status`
