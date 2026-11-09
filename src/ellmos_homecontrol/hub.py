"""SmartHome & household appliance adapters and MCP-ready HomeControlHub."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import re
from typing import Any
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

_XML_ENTITIES = {'"': '&quot;', "'": '&apos;'}
_XML_TAG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


class HighLoadConfirmationRequiredError(PermissionError):
    """Raised when switching a high-load (>2000 W) or safety-critical appliance without confirmation."""


@dataclass(frozen=True)
class HomeDevice:
    device_id: str
    name: str
    adapter: str  # "fritzbox" | "homeassistant" | "matter" | "mqtt_shelly"
    kind: str  # "plug" | "light" | "thermostat" | "appliance" | "lock" | "router"
    state: dict[str, Any]
    power_watts: float = 0.0
    max_rated_watts: float = 100.0
    requires_confirmation: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FritzBoxAdapter:
    """FritzBox TR-064 (UPnP/SOAP) and DECT SmartHome adapter (extracted from BACH smarthome.py)."""

    def __init__(self, base_url: str = "http://fritz.box:49000"):
        self.base_url = base_url.rstrip("/")

    def tr064_call(self, service: str, action: str, params: dict[str, Any] | None = None) -> str | None:
        if not (isinstance(action, str) and _XML_TAG_RE.fullmatch(action)):
            return None
        control_map = {
            "urn:dslforum-org:service:WANIPConnection:1": "/igdupnp/control/WANIPConn1",
            "urn:dslforum-org:service:WANCommonInterfaceConfig:1": "/igdupnp/control/WANCommonIFC1",
            "urn:dslforum-org:service:DeviceInfo:1": "/upnp/control/deviceinfo",
            "urn:dslforum-org:service:Hosts:1": "/upnp/control/hosts",
            "urn:dslforum-org:service:WLANConfiguration:3": "/upnp/control/wlanconfig3",
        }
        path = control_map.get(service, "/upnp/control/deviceinfo")
        url = f"{self.base_url}{path}"
        param_xml = ""
        if params:
            for k, v in params.items():
                if not (isinstance(k, str) and _XML_TAG_RE.fullmatch(k)):
                    return None
                esc_v = escape(str(v), _XML_ENTITIES)
                param_xml += f"<{k}>{esc_v}</{k}>"
        esc_service = escape(service, _XML_ENTITIES)
        esc_action = escape(action, _XML_ENTITIES)
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            f'<u:{esc_action} xmlns:u="{esc_service}">{param_xml}</u:{esc_action}>'
            "</s:Body></s:Envelope>"
        )
        clean_service = service.replace("\r", "").replace("\n", "")
        clean_action = action.replace("\r", "").replace("\n", "")
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"{clean_service}#{clean_action}"',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError):
            return None

    @staticmethod
    def xml_value(xml_str: str, tag: str) -> str | None:
        try:
            root = ET.fromstring(xml_str)
            for elem in root.iter():
                if elem.tag.endswith(tag):
                    return elem.text
        except ET.ParseError:
            import re

            m = re.search(rf"<(?:\w+:)?{re.escape(tag)}>(.*?)</(?:\w+:)?{re.escape(tag)}>", xml_str, re.DOTALL)
            if m:
                return m.group(1)
        return None


class HomeAssistantAdapter:
    """Local REST/WebSocket adapter for Home Assistant entities."""

    def __init__(self, base_url: str = "http://homeassistant.local:8123"):
        self.base_url = base_url.rstrip("/")


class MatterBridgeAdapter:
    """Local Matter-over-Thread / Wi-Fi device bridge."""

    def __init__(self, fabric_name: str = "ellmos-local-matter"):
        self.fabric_name = fabric_name


class MqttShellyAdapter:
    """Local MQTT / Shelly / Tasmota energy & relay adapter."""

    def __init__(self, broker_host: str = "127.0.0.1", broker_port: int = 1883):
        self.broker_host = broker_host
        self.broker_port = broker_port


class HomeControlHub:
    """Canonical MCP-aligned SmartHome and household appliance controller."""

    HIGH_LOAD_THRESHOLD_WATTS = 2000.0
    SAFETY_CRITICAL_KINDS = {"oven", "stove", "lock", "garage_door", "heater_high_load"}

    def __init__(self, devices: list[HomeDevice] | None = None, *, smarthome_permission: bool = True):
        self.smarthome_permission = smarthome_permission
        # Built-in sample devices are simulated data and must say so (Nutzerentscheidung E3).
        self.demo = devices is None
        self.fritzbox = FritzBoxAdapter()
        self.homeassistant = HomeAssistantAdapter()
        self.matter = MatterBridgeAdapter()
        self.mqtt_shelly = MqttShellyAdapter()
        default_devices = [
            HomeDevice(
                device_id="fritz.dect200.office",
                name="Büro Smart-Plug (DECT 200)",
                adapter="fritzbox",
                kind="plug",
                state={"on": True, "temperature_c": 21.5},
                power_watts=84.0,
                max_rated_watts=2300.0,
            ),
            HomeDevice(
                device_id="ha.light.studio_main",
                name="Studio Hauptlicht",
                adapter="homeassistant",
                kind="light",
                state={"on": True, "brightness_pct": 80, "color_temp_k": 4000},
                power_watts=18.5,
                max_rated_watts=40.0,
            ),
            HomeDevice(
                device_id="matter.thermostat.living",
                name="Wohnzimmer Thermostat",
                adapter="matter",
                kind="thermostat",
                state={"target_temp_c": 21.0, "current_temp_c": 20.8, "mode": "heat"},
                power_watts=1.2,
                max_rated_watts=15.0,
            ),
            HomeDevice(
                device_id="shelly.appliance.washer",
                name="Waschmaschine (Shelly Plus 1PM)",
                adapter="mqtt_shelly",
                kind="appliance",
                state={"on": False, "cycle": "idle"},
                power_watts=0.0,
                max_rated_watts=2400.0,
                requires_confirmation=True,
            ),
        ]
        self._devices: dict[str, HomeDevice] = {d.device_id: d for d in (devices or default_devices)}
        self._scenes: dict[str, dict[str, dict[str, Any]]] = {
            "focus_work": {
                "ha.light.studio_main": {"on": True, "brightness_pct": 100, "color_temp_k": 5000},
                "matter.thermostat.living": {"target_temp_c": 20.5},
            },
            "evening_calm": {
                "ha.light.studio_main": {"on": True, "brightness_pct": 35, "color_temp_k": 2700},
                "matter.thermostat.living": {"target_temp_c": 21.5},
            },
        }

    def _out(self, dev: HomeDevice) -> dict[str, Any]:
        return {**dev.as_dict(), "demo": self.demo}

    def _require_permission(self) -> None:
        if not self.smarthome_permission:
            raise PermissionError("SmartHome access is disabled in Permissions (smarthome_robotics=False).")

    def hc_list_devices(self, adapter: str | None = None) -> list[dict[str, Any]]:
        self._require_permission()
        items = list(self._devices.values())
        if adapter:
            items = [d for d in items if d.adapter == adapter]
        return [self._out(d) for d in items]

    def hc_get_state(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        if device_id not in self._devices:
            raise KeyError(f"Unknown device_id: {device_id}")
        return self._out(self._devices[device_id])

    def hc_set_state(
        self,
        device_id: str,
        target_state: dict[str, Any],
        *,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        self._require_permission()
        if device_id not in self._devices:
            raise KeyError(f"Unknown device_id: {device_id}")
        dev = self._devices[device_id]
        needs_confirm = (
            dev.requires_confirmation
            or dev.kind in self.SAFETY_CRITICAL_KINDS
            or (dev.max_rated_watts > self.HIGH_LOAD_THRESHOLD_WATTS and dev.kind != "plug")
        )
        if needs_confirm and not confirmed:
            raise HighLoadConfirmationRequiredError(
                f"Device '{dev.name}' ({dev.device_id}, {dev.max_rated_watts}W) requires explicit confirmed=True."
            )
        merged_state = {**dev.state, **target_state}
        updated = replace(dev, state=merged_state)
        self._devices[device_id] = updated
        return self._out(updated)

    def hc_scene_activate(self, scene_id: str) -> dict[str, Any]:
        self._require_permission()
        if scene_id not in self._scenes:
            raise KeyError(f"Unknown scene_id: {scene_id}")
        applied: list[str] = []
        for dev_id, patch in self._scenes[scene_id].items():
            if dev_id in self._devices:
                self.hc_set_state(dev_id, patch, confirmed=True)
                applied.append(dev_id)
        return {"scene_id": scene_id, "applied_devices": applied, "demo": self.demo}

    def hc_energy_status(self) -> dict[str, Any]:
        self._require_permission()
        total_watts = round(sum(d.power_watts for d in self._devices.values()), 2)
        return {
            "schema": "ellmos.homecontrol.energy.v1",
            "demo": self.demo,
            "total_power_watts": total_watts,
            "device_count": len(self._devices),
            "by_adapter": {
                adapter: round(sum(d.power_watts for d in self._devices.values() if d.adapter == adapter), 2)
                for adapter in ("fritzbox", "homeassistant", "matter", "mqtt_shelly")
            },
        }
