"""Vendor-neutral RouterAdapter protocol, gateway discovery, FritzBox TR-064 readback, and Huawei HiLink status."""

from __future__ import annotations

from abc import ABC, abstractmethod
import contextlib
from dataclasses import asdict, dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import time
from typing import Any, Callable, Sequence
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

_XML_ENTITIES = {'"': "&quot;", "'": "&apos;"}
_XML_TAG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")

_SECRET_TAG_RE = re.compile(
    r"(<(?:\w+:)?(?:SesInfo|TokInfo|Password|Passwd|NewPassword|X_AVM-DE_RemoteAccessPassword)>)"
    r"(.*?)"
    r"(</(?:\w+:)?(?:SesInfo|TokInfo|Password|Passwd|NewPassword|X_AVM-DE_RemoteAccessPassword)>)",
    re.IGNORECASE | re.DOTALL,
)
_HEADER_SECRET_RE = re.compile(
    r"((?:Authorization|__RequestVerificationToken|Cookie)\s*:\s*)([^\r\n]+)",
    re.IGNORECASE,
)
_COOKIE_TOKEN_RE = re.compile(
    r"((?:SessionID|SesInfo|TokInfo|password|passwd|secret|token)\s*[=:]\s*[\"']?)([^\"'\s;&,>]+)",
    re.IGNORECASE,
)


def redact_secrets(text: str, extra_secrets: Sequence[str] = ()) -> str:
    """Masks passwords, auth headers, Huawei SesInfo/TokInfo tokens, and explicit secret values."""
    if not text:
        return text
    scrubbed = _SECRET_TAG_RE.sub(r"\1<redacted>\3", text)
    scrubbed = _HEADER_SECRET_RE.sub(r"\1<redacted>", scrubbed)
    scrubbed = _COOKIE_TOKEN_RE.sub(r"\1<redacted>", scrubbed)
    for secret in extra_secrets:
        if secret and len(secret) >= 3:
            scrubbed = scrubbed.replace(secret, "<redacted>")
    return scrubbed


class RouterError(RuntimeError):
    """Base exception for router operations; automatically scrubs secrets from error messages."""

    def __init__(self, message: str, *, extra_secrets: Sequence[str] = ()) -> None:
        super().__init__(redact_secrets(message, extra_secrets=extra_secrets))


class UnsupportedCapabilityError(RouterError):
    """Raised when an adapter does not support a requested read/write capability (TF-08)."""

    def __init__(self, capability: str, adapter_kind: str, *, method: str = "unsupported", detail: str = "") -> None:
        msg = f"Capability '{capability}' is not supported by router adapter '{adapter_kind}' (method={method})."
        if detail:
            msg = f"{msg} {detail}"
        super().__init__(msg)
        self.capability = capability
        self.adapter_kind = adapter_kind
        self.method = method


class RouterReadbackVerificationError(RouterError):
    """Raised when post-switch GetInfo readback contradicts the requested router state (TF-09)."""

    def __init__(self, message: str, *, readback: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.readback = readback or {}


class RouterAuthorityGateError(PermissionError):
    """Raised when a Tier-2 or Tier-3 router mutation lacks required authority confirmation (§3.3)."""

    def __init__(self, capability: str, *, tier: int, message: str) -> None:
        super().__init__(message)
        self.capability = capability
        self.tier = tier


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Honest capability declaration per adapter (`tr064`, `hilink_http`, `web_session`, `unsupported`)."""

    supported: bool
    method: str
    tier: int  # 1 = network-observer read, 2 = reversible operator write, 3 = lockout-sensitive hard gate
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouterCredentials:
    """Resolved router credentials that never expose secret material in repr or serialized dicts."""

    username: str | None = None
    secret: str | None = None
    source: str = "none"  # "keyring" | "credentials_dir" | "memory" | "none"

    def __repr__(self) -> str:
        masked = "'<redacted>'" if self.secret else "None"
        return f"RouterCredentials(username={self.username!r}, secret={masked}, source={self.source!r})"

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "has_secret": bool(self.secret),
            "source": self.source,
        }


def _parse_kv_credentials(raw_text: str) -> tuple[str | None, str | None]:
    user: str | None = None
    secret: str | None = None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        k = key.strip().upper()
        v = val.strip().strip("\"'")
        if k in ("USERNAME", "USER", "ROUTER_USER") and v:
            user = v
        elif k in ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "ROUTER_PASSWORD") and v:
            secret = v
    return (user, secret)


def resolve_router_credentials(
    adapter_kind: str,
    router_id: str = "default",
    *,
    username: str | None = None,
    credentials_dir: str | Path | None = None,
    keyring_backend: Any = None,
) -> RouterCredentials:
    """Resolves router credentials strictly via: 1. OS keyring -> 2. ELLMOS_HOMECONTROL_CREDENTIALS_DIR -> 3. none."""
    clean_adapter = re.sub(r"[^a-z0-9_-]", "", adapter_kind.lower()) or "generic"
    clean_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", router_id.strip()) or "default"

    # 1. OS Keyring (`ellmos-homecontrol` / `router.<adapter>.<router_id>`)
    kr = keyring_backend
    if kr is None and importlib.util.find_spec("keyring") is not None:
        with contextlib.suppress(Exception):
            import keyring  # type: ignore[import-not-found]

            kr = keyring

    if kr is not None:
        key_name = f"router.{clean_adapter}.{clean_id}"
        with contextlib.suppress(Exception):
            stored = kr.get_password("ellmos-homecontrol", key_name)
            if stored:
                text = str(stored).strip()
                if text.startswith("{"):
                    parsed = json.loads(text)
                    return RouterCredentials(
                        username=parsed.get("username") or username,
                        secret=parsed.get("password") or parsed.get("secret") or parsed.get("token"),
                        source="keyring",
                    )
                if ":" in text and username is None:
                    u_part, _, s_part = text.partition(":")
                    return RouterCredentials(username=u_part or None, secret=s_part, source="keyring")
                return RouterCredentials(username=username, secret=text, source="keyring")

    # 2. Explicit credentials directory (`credentials_dir` or `ELLMOS_HOMECONTROL_CREDENTIALS_DIR`)
    eff_dir_raw = str(credentials_dir or os.environ.get("ELLMOS_HOMECONTROL_CREDENTIALS_DIR", "")).strip()
    if eff_dir_raw:
        base_dir = Path(eff_dir_raw)
        candidates = [
            base_dir / f"router-{clean_adapter}" / f"{clean_id}.json",
            base_dir / f"router-{clean_adapter}" / "credentials.json",
            base_dir / f"router-{clean_adapter}" / f"{clean_id}.txt",
            base_dir / f"router-{clean_adapter}" / "credentials.txt",
        ]
        for cand in candidates:
            if not cand.is_file():
                continue
            try:
                raw = cand.read_text(encoding="utf-8")
                if cand.suffix.lower() == ".json":
                    data = json.loads(raw)
                    sec = data.get("password") or data.get("secret") or data.get("token")
                    if sec:
                        return RouterCredentials(
                            username=data.get("username") or username,
                            secret=str(sec),
                            source="credentials_dir",
                        )
                else:
                    kv_user, kv_sec = _parse_kv_credentials(raw)
                    if kv_sec:
                        return RouterCredentials(
                            username=kv_user or username,
                            secret=kv_sec,
                            source="credentials_dir",
                        )
            except (OSError, ValueError):
                continue

    return RouterCredentials(username=username, secret=None, source="none")


def _extract_xml_text(xml_str: str, tag: str) -> str | None:
    try:
        root = ET.fromstring(xml_str)
        for elem in root.iter():
            local = elem.tag.split("}", 1)[-1] if "}" in elem.tag else elem.tag
            if local == tag:
                return (elem.text or "").strip()
    except ET.ParseError:
        m = re.search(rf"<(?:\w+:)?{re.escape(tag)}>(.*?)</(?:\w+:)?{re.escape(tag)}>", xml_str, re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def _default_port_prober(host: str, port: int, timeout_s: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _default_http_fetcher(url: str, timeout_s: float) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "ellmos-homecontrol/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = int(getattr(resp, "status", 200))
            body = resp.read().decode("utf-8", errors="replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return (status, body, headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        return (int(exc.code), body, headers)


class RouterAdapter(ABC):
    """Vendor-neutral router interface for `network-observer` (read) and `router-operator` (write) roles."""

    adapter_kind: str = "generic_gateway"

    def __init__(self, gateway_ip: str = "192.0.2.1") -> None:
        self.gateway_ip = gateway_ip.strip()

    @abstractmethod
    def capabilities(self) -> dict[str, CapabilityDescriptor]:
        """Returns supported and unsupported capabilities with honest transport metadata."""

    def capabilities_dict(self) -> dict[str, dict[str, Any]]:
        return {name: desc.as_dict() for name, desc in self.capabilities().items()}

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Returns vendor-neutral router health and identity summary (`router.status`)."""

    def get_wan_info(self) -> dict[str, Any]:
        raise UnsupportedCapabilityError("router.wan_info", self.adapter_kind)

    def list_hosts(self) -> list[dict[str, Any]]:
        raise UnsupportedCapabilityError("router.list_hosts", self.adapter_kind)

    def get_wifi_status(self) -> dict[str, Any]:
        raise UnsupportedCapabilityError("router.wifi_status", self.adapter_kind)

    def set_guest_wifi(self, enabled: bool) -> dict[str, Any]:
        _ = enabled
        raise UnsupportedCapabilityError("router.set_guest_wifi", self.adapter_kind)

    def set_wifi(self, enabled: bool, *, service_index: int = 1) -> dict[str, Any]:
        _ = (enabled, service_index)
        raise UnsupportedCapabilityError("router.set_wifi", self.adapter_kind)

    def wan_reconnect(self) -> dict[str, Any]:
        raise UnsupportedCapabilityError("router.wan_reconnect", self.adapter_kind)

    def set_dhcp_reservation(self, mac_address: str, ip_address: str, hostname: str | None = None) -> dict[str, Any]:
        _ = (mac_address, ip_address, hostname)
        raise UnsupportedCapabilityError("router.set_dhcp_reservation", self.adapter_kind)


class GenericGatewayAdapter(RouterAdapter):
    """Read-only fallback adapter for unknown gateways; rejects writes with `UnsupportedCapabilityError`."""

    adapter_kind = "generic_gateway"

    def __init__(
        self,
        gateway_ip: str = "192.0.2.1",
        *,
        reachable: bool = True,
        fingerprint: str = "generic",
    ) -> None:
        super().__init__(gateway_ip)
        self.reachable = reachable
        self.fingerprint = fingerprint

    def capabilities(self) -> dict[str, CapabilityDescriptor]:
        return {
            "router.discover": CapabilityDescriptor(True, "probe", 1),
            "router.status": CapabilityDescriptor(True, "probe", 1),
            "router.wan_info": CapabilityDescriptor(False, "unsupported", 1),
            "router.list_hosts": CapabilityDescriptor(False, "unsupported", 1),
            "router.wifi_status": CapabilityDescriptor(False, "unsupported", 1),
            "router.set_guest_wifi": CapabilityDescriptor(False, "unsupported", 2),
            "router.set_wifi": CapabilityDescriptor(False, "unsupported", 3),
            "router.wan_reconnect": CapabilityDescriptor(False, "unsupported", 2),
            "router.set_dhcp_reservation": CapabilityDescriptor(False, "unsupported", 2),
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "schema": "ellmos.homecontrol.router.status.v1",
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "reachable": self.reachable,
            "model": self.fingerprint,
        }


class HuaweiHiLinkRouterAdapter(RouterAdapter):
    """Read-only Huawei HiLink LTE/5G CPE adapter (`/api/device/basic_information`, `/api/monitoring/status`)."""

    adapter_kind = "huawei_hilink"

    def __init__(
        self,
        gateway_ip: str = "192.0.2.1",
        *,
        model_name: str | None = None,
        timeout_s: float = 2.5,
        http_fetcher: Callable[[str, float], tuple[int, str, dict[str, str]]] | None = None,
    ) -> None:
        super().__init__(gateway_ip)
        self._initial_model = model_name
        self.timeout_s = timeout_s
        self._http_fetcher = http_fetcher or _default_http_fetcher

    def capabilities(self) -> dict[str, CapabilityDescriptor]:
        return {
            "router.discover": CapabilityDescriptor(True, "hilink_http", 1),
            "router.status": CapabilityDescriptor(True, "hilink_http", 1, "Read-only basic_information & monitoring/status"),
            "router.wan_info": CapabilityDescriptor(True, "hilink_http", 1, "Cellular/WAN connection status"),
            "router.list_hosts": CapabilityDescriptor(False, "unsupported", 1, "Requires authenticated HiLink session"),
            "router.wifi_status": CapabilityDescriptor(False, "unsupported", 1, "Requires authenticated HiLink session"),
            "router.set_guest_wifi": CapabilityDescriptor(False, "unsupported", 2, "Write actions disabled in HiLink MVP"),
            "router.set_wifi": CapabilityDescriptor(False, "unsupported", 3, "Write actions disabled in HiLink MVP"),
            "router.wan_reconnect": CapabilityDescriptor(False, "unsupported", 2, "Write actions disabled in HiLink MVP"),
            "router.set_dhcp_reservation": CapabilityDescriptor(False, "unsupported", 2, "Unsupported via unauthenticated API"),
        }

    def _fetch_xml(self, path: str) -> str:
        url = f"http://{self.gateway_ip}{path}"
        try:
            status, body, _ = self._http_fetcher(url, self.timeout_s)
        except Exception as exc:
            raise RouterError(f"Huawei HiLink request to {path} failed: {exc}") from exc
        if status != 200 or not body:
            raise RouterError(f"Huawei HiLink {path} returned HTTP {status}: {redact_secrets(body[:200])}")
        return body

    def get_status(self) -> dict[str, Any]:
        basic_xml = self._fetch_xml("/api/device/basic_information")
        model = _extract_xml_text(basic_xml, "DeviceName") or self._initial_model or "Huawei HiLink CPE"
        family = _extract_xml_text(basic_xml, "ProductFamily") or "LTE/5G CPE"
        sw_ver = _extract_xml_text(basic_xml, "SoftwareVersion")

        conn_status: str | None = None
        net_type: str | None = None
        signal_icon: str | None = None
        with contextlib.suppress(RouterError):
            mon_xml = self._fetch_xml("/api/monitoring/status")
            conn_status = _extract_xml_text(mon_xml, "ConnectionStatus")
            net_type = _extract_xml_text(mon_xml, "CurrentNetworkType")
            signal_icon = _extract_xml_text(mon_xml, "SignalIcon")

        return {
            "schema": "ellmos.homecontrol.router.status.v1",
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "reachable": True,
            "model": model,
            "product_family": family,
            "software_version": sw_ver,
            "connection_status": conn_status,
            "network_type": net_type,
            "signal_bars": int(signal_icon) if (signal_icon and signal_icon.isdigit()) else None,
        }

    def get_wan_info(self) -> dict[str, Any]:
        mon_xml = self._fetch_xml("/api/monitoring/status")
        conn_code = _extract_xml_text(mon_xml, "ConnectionStatus") or "unknown"
        return {
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "connected": conn_code == "901",
            "connection_code": conn_code,
            "network_type": _extract_xml_text(mon_xml, "CurrentNetworkType"),
        }


class FritzBoxRouterAdapter(RouterAdapter):
    """AVM FritzBox TR-064 adapter with HTTP Digest auth, secret scrubbing, and mandatory GetInfo readback (TF-09)."""

    adapter_kind = "fritzbox"

    _CONTROL_PATHS: dict[str, str] = {
        "urn:dslforum-org:service:DeviceInfo:1": "/upnp/control/deviceinfo",
        "urn:dslforum-org:service:WANIPConnection:1": "/igdupnp/control/WANIPConn1",
        "urn:dslforum-org:service:WANPPPConnection:1": "/upnp/control/wanpppconn1",
        "urn:dslforum-org:service:Hosts:1": "/upnp/control/hosts",
        "urn:dslforum-org:service:WLANConfiguration:1": "/upnp/control/wlanconfig1",
        "urn:dslforum-org:service:WLANConfiguration:2": "/upnp/control/wlanconfig2",
        "urn:dslforum-org:service:WLANConfiguration:3": "/upnp/control/wlanconfig3",
    }

    def __init__(
        self,
        gateway_ip: str = "192.0.2.1",
        *,
        port: int = 49000,
        router_id: str = "default",
        credentials: RouterCredentials | None = None,
        credentials_dir: str | Path | None = None,
        keyring_backend: Any = None,
        timeout_s: float = 3.0,
        soap_caller: Callable[[str, str, dict[str, Any] | None], str | None] | None = None,
        max_readback_attempts: int = 3,
        readback_backoff_s: float = 0.15,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(gateway_ip)
        self.port = int(port)
        self.router_id = router_id
        self.timeout_s = timeout_s
        self._soap_caller = soap_caller
        self.max_readback_attempts = max(1, int(max_readback_attempts))
        self.readback_backoff_s = max(0.0, float(readback_backoff_s))
        self._sleep_fn = sleep_fn
        self._credentials = credentials or resolve_router_credentials(
            "fritzbox",
            router_id=router_id,
            credentials_dir=credentials_dir,
            keyring_backend=keyring_backend,
        )

    @property
    def base_url(self) -> str:
        return f"http://{self.gateway_ip}:{self.port}"

    @property
    def credential_info(self) -> dict[str, Any]:
        return self._credentials.as_safe_dict()

    def capabilities(self) -> dict[str, CapabilityDescriptor]:
        return {
            "router.discover": CapabilityDescriptor(True, "tr064", 1),
            "router.status": CapabilityDescriptor(True, "tr064", 1, "DeviceInfo:1 GetInfo"),
            "router.wan_info": CapabilityDescriptor(True, "tr064", 1, "WANIPConnection:1 GetStatusInfo & GetExternalIPAddress"),
            "router.list_hosts": CapabilityDescriptor(True, "tr064", 1, "Hosts:1 GetHostNumberOfEntries & GetGenericHostEntry"),
            "router.wifi_status": CapabilityDescriptor(True, "tr064", 1, "WLANConfiguration:1..3 GetInfo"),
            "router.set_guest_wifi": CapabilityDescriptor(True, "tr064", 2, "WLANConfiguration:3 SetEnable + GetInfo readback"),
            "router.set_wifi": CapabilityDescriptor(True, "tr064", 3, "WLANConfiguration:1..2 SetEnable + GetInfo readback"),
            "router.wan_reconnect": CapabilityDescriptor(True, "tr064", 2, "WANIPConnection:1 ForceTermination"),
            "router.set_dhcp_reservation": CapabilityDescriptor(
                False,
                "web_session",
                2,
                "Static IPv4 lease binding is not portably exposed via TR-064 Hosts:1 without FritzOS Web-LUA SID.",
            ),
        }

    def tr064_call(self, service: str, action: str, params: dict[str, Any] | None = None) -> str | None:
        if not (isinstance(action, str) and _XML_TAG_RE.fullmatch(action)):
            raise RouterError(f"Invalid TR-064 SOAP action tag: {action!r}")
        if params:
            for k in params:
                if not (isinstance(k, str) and _XML_TAG_RE.fullmatch(k)):
                    raise RouterError(f"Invalid TR-064 SOAP parameter tag: {k!r}")

        if self._soap_caller is not None:
            return self._soap_caller(service, action, params)

        path = self._CONTROL_PATHS.get(service, "/upnp/control/deviceinfo")
        url = f"{self.base_url}{path}"
        param_xml = ""
        if params:
            for k, v in params.items():
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
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"{service.strip()}#{action.strip()}"',
            },
        )

        secrets = [self._credentials.secret] if self._credentials.secret else []
        try:
            if self._credentials.secret:
                mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                mgr.add_password(None, self.base_url, self._credentials.username or "dslf-config", self._credentials.secret)
                opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(mgr))
                with opener.open(req, timeout=self.timeout_s) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise RouterError(f"TR-064 {action} on {service} failed: {exc}", extra_secrets=secrets) from exc

    def get_status(self) -> dict[str, Any]:
        xml = self.tr064_call("urn:dslforum-org:service:DeviceInfo:1", "GetInfo")
        if not xml:
            raise RouterError("Empty TR-064 DeviceInfo:1 GetInfo response.")
        model = _extract_xml_text(xml, "NewModelName") or "FRITZ!Box"
        sw_ver = _extract_xml_text(xml, "NewSoftwareVersion")
        uptime_raw = _extract_xml_text(xml, "NewUpTime")
        return {
            "schema": "ellmos.homecontrol.router.status.v1",
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "reachable": True,
            "model": model,
            "software_version": sw_ver,
            "uptime_s": int(uptime_raw) if (uptime_raw and uptime_raw.isdigit()) else None,
            "credentials": self.credential_info,
        }

    def get_wan_info(self) -> dict[str, Any]:
        svc = "urn:dslforum-org:service:WANIPConnection:1"
        st_xml = self.tr064_call(svc, "GetStatusInfo") or ""
        ip_xml = self.tr064_call(svc, "GetExternalIPAddress") or ""
        conn_status = _extract_xml_text(st_xml, "NewConnectionStatus") or "Unknown"
        ext_ip = _extract_xml_text(ip_xml, "NewExternalIPAddress")
        return {
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "connected": conn_status == "Connected",
            "connection_status": conn_status,
            "external_ip": ext_ip,
        }

    def list_hosts(self) -> list[dict[str, Any]]:
        svc = "urn:dslforum-org:service:Hosts:1"
        count_xml = self.tr064_call(svc, "GetHostNumberOfEntries") or ""
        raw_count = _extract_xml_text(count_xml, "NewHostNumberOfEntries")
        total = int(raw_count) if (raw_count and raw_count.isdigit()) else 0
        hosts: list[dict[str, Any]] = []
        for idx in range(min(total, 256)):
            entry_xml = self.tr064_call(svc, "GetGenericHostEntry", {"NewIndex": idx})
            if not entry_xml:
                continue
            active_raw = _extract_xml_text(entry_xml, "NewActive")
            hosts.append(
                {
                    "index": idx,
                    "hostname": _extract_xml_text(entry_xml, "NewHostName") or "",
                    "ip_address": _extract_xml_text(entry_xml, "NewIPAddress") or "",
                    "mac_address": _extract_xml_text(entry_xml, "NewMACAddress") or "",
                    "interface_type": _extract_xml_text(entry_xml, "NewInterfaceType") or "",
                    "active": active_raw == "1",
                }
            )
        return hosts

    def _read_wlan_service_info(self, service_index: int) -> dict[str, Any]:
        svc = f"urn:dslforum-org:service:WLANConfiguration:{service_index}"
        xml = self.tr064_call(svc, "GetInfo")
        if not xml:
            return {"service_index": service_index, "reachable": False, "enabled": None, "status": None, "ssid": None}
        en_raw = _extract_xml_text(xml, "NewEnable")
        enabled: bool | None = True if en_raw == "1" else (False if en_raw == "0" else None)
        return {
            "service_index": service_index,
            "reachable": True,
            "enabled": enabled,
            "status": _extract_xml_text(xml, "NewStatus"),
            "ssid": _extract_xml_text(xml, "NewSSID"),
        }

    def get_wifi_status(self, *, indices: Sequence[int] = (1, 3)) -> dict[str, Any]:
        radios: dict[str, dict[str, Any]] = {}
        for idx in indices:
            with contextlib.suppress(RouterError):
                info = self._read_wlan_service_info(idx)
                if info["reachable"]:
                    label = "guest_wifi" if idx == 3 else f"wlan_{idx}"
                    radios[label] = info
        return {
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "radios": radios,
        }

    def set_wifi(
        self,
        enabled: bool,
        *,
        service_index: int = 1,
        raise_on_unverified: bool = False,
    ) -> dict[str, Any]:
        """Switches WLANConfiguration:<index> via SetEnable and verifies target state via GetInfo readback (TF-09)."""
        if service_index not in (1, 2, 3):
            raise ValueError(f"Unsupported WLANConfiguration service_index: {service_index}")
        svc = f"urn:dslforum-org:service:WLANConfiguration:{service_index}"
        desired_flag = "1" if enabled else "0"
        self.tr064_call(svc, "SetEnable", {"NewEnable": desired_flag})

        actual_enabled: bool | None = None
        actual_status: str | None = None
        actual_ssid: str | None = None
        attempts = 0

        for attempt in range(1, self.max_readback_attempts + 1):
            attempts = attempt
            info = self._read_wlan_service_info(service_index)
            actual_enabled = info["enabled"]
            actual_status = info["status"]
            actual_ssid = info["ssid"]
            if actual_enabled is enabled:
                return {
                    "ok": True,
                    "verified": True,
                    "adapter": self.adapter_kind,
                    "gateway_ip": self.gateway_ip,
                    "service": svc,
                    "service_index": service_index,
                    "requested_enabled": bool(enabled),
                    "actual_enabled": actual_enabled,
                    "status": actual_status,
                    "ssid": actual_ssid,
                    "readback_attempts": attempts,
                }
            if attempt < self.max_readback_attempts and self.readback_backoff_s > 0:
                self._sleep_fn(self.readback_backoff_s)

        result = {
            "ok": False,
            "verified": False,
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "service": svc,
            "service_index": service_index,
            "requested_enabled": bool(enabled),
            "actual_enabled": actual_enabled,
            "status": actual_status,
            "ssid": actual_ssid,
            "readback_attempts": attempts,
            "error": (
                f"Post-switch GetInfo readback mismatch on {svc}: "
                f"requested={bool(enabled)}, actual={actual_enabled}, status={actual_status!r}"
            ),
        }
        if raise_on_unverified:
            raise RouterReadbackVerificationError(result["error"], readback=result)
        return result

    def set_guest_wifi(self, enabled: bool, *, raise_on_unverified: bool = False) -> dict[str, Any]:
        return self.set_wifi(enabled, service_index=3, raise_on_unverified=raise_on_unverified)

    def wan_reconnect(self) -> dict[str, Any]:
        svc = "urn:dslforum-org:service:WANIPConnection:1"
        self.tr064_call(svc, "ForceTermination")
        return {
            "ok": True,
            "adapter": self.adapter_kind,
            "gateway_ip": self.gateway_ip,
            "action": "ForceTermination",
        }

    def set_dhcp_reservation(self, mac_address: str, ip_address: str, hostname: str | None = None) -> dict[str, Any]:
        _ = (mac_address, ip_address, hostname)
        raise UnsupportedCapabilityError(
            "router.set_dhcp_reservation",
            self.adapter_kind,
            method="web_session",
            detail="FritzOS TR-064 Hosts:1 does not portably bind static IPv4 DHCP leases without a Web-LUA SID session.",
        )


def discover_router(
    gateway_ip: str = "192.0.2.1",
    *,
    timeout_s: float = 1.5,
    port_prober: Callable[[str, int, float], bool] | None = None,
    http_fetcher: Callable[[str, float], tuple[int, str, dict[str, str]]] | None = None,
    credentials: RouterCredentials | None = None,
    credentials_dir: str | Path | None = None,
    keyring_backend: Any = None,
) -> RouterAdapter:
    """Read-only vendor-neutral router discovery without blind TR-064 SOAP calls on closed port 49000 (TF-08)."""
    clean_ip = gateway_ip.strip()
    if not clean_ip:
        raise ValueError("gateway_ip must not be empty.")

    eff_port_probe = port_prober or _default_port_prober
    eff_http = http_fetcher or _default_http_fetcher

    # 1. Check AVM FritzBox TR-064 description on TCP :49000 ONLY when port 49000 is open (TF-08)
    if eff_port_probe(clean_ip, 49000, timeout_s):
        for desc_path in ("/tr64desc.xml", "/igddesc.xml"):
            with contextlib.suppress(Exception):
                status, body, _ = eff_http(f"http://{clean_ip}:49000{desc_path}", timeout_s)
                if status in (200, 401) and any(tok in body.lower() for tok in ("avm", "fritz", "dslforum-org")):
                    return FritzBoxRouterAdapter(
                        clean_ip,
                        credentials=credentials,
                        credentials_dir=credentials_dir,
                        keyring_backend=keyring_backend,
                        timeout_s=max(2.0, timeout_s),
                    )

    # 2. Check Huawei HiLink XML signature (`/api/device/basic_information` or `/api/webserver/SesTokInfo`)
    for hilink_path in ("/api/device/basic_information", "/api/webserver/SesTokInfo"):
        with contextlib.suppress(Exception):
            status, body, _ = eff_http(f"http://{clean_ip}{hilink_path}", timeout_s)
            if status == 200 and "<response" in body.lower():
                dev_name = _extract_xml_text(body, "DeviceName")
                prod_fam = _extract_xml_text(body, "ProductFamily")
                has_ses = "<sesinfo>" in body.lower() or "<tokinfo>" in body.lower()
                if dev_name or prod_fam or has_ses:
                    return HuaweiHiLinkRouterAdapter(
                        clean_ip,
                        model_name=dev_name,
                        timeout_s=max(2.0, timeout_s),
                        http_fetcher=eff_http,
                    )

    # 3. Safe generic read-only gateway fallback
    reachable = eff_port_probe(clean_ip, 80, timeout_s) or eff_port_probe(clean_ip, 443, timeout_s)
    return GenericGatewayAdapter(clean_ip, reachable=reachable)
