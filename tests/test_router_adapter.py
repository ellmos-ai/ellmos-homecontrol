"""Tests for vendor-neutral RouterAdapter discovery (TF-08), FritzBox GetInfo readback (TF-09), secret masking, and authority gates."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from ellmos_homecontrol import (
    FritzBoxRouterAdapter,
    GenericGatewayAdapter,
    HomeControlHub,
    HuaweiHiLinkRouterAdapter,
    RouterAuthorityGateError,
    RouterCredentials,
    RouterError,
    RouterReadbackVerificationError,
    UnsupportedCapabilityError,
    discover_router,
    redact_secrets,
    resolve_router_credentials,
)
from ellmos_homecontrol.cli import main as cli_main

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_GATEWAY_IP = "192.0.2.1"  # RFC 5737 TEST-NET-1


# ---- TF-08: Vendor-neutral router discovery & UnsupportedCapabilityError ----


def test_tf08_discover_huawei_hilink_when_port_49000_closed_and_reject_unsupported_writes() -> None:
    """TF-08: Closed :49000 + Huawei basic_information detects huawei_hilink without TR-064 calls and rejects set_wifi."""
    http_calls: list[str] = []
    port_checks: list[tuple[str, int]] = []

    def _port_prober(host: str, port: int, _timeout: float) -> bool:
        port_checks.append((host, port))
        return port == 80  # TCP 49000 is closed!

    def _http_fetcher(url: str, _timeout: float) -> tuple[int, str, dict[str, str]]:
        http_calls.append(url)
        if url.endswith("/api/device/basic_information"):
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<response>"
                "<DeviceName>TEST-CPE</DeviceName>"
                "<ProductFamily>LTE CPE</ProductFamily>"
                "<SoftwareVersion>v2.1-SIMULATED</SoftwareVersion>"
                "</response>"
            )
            return (200, xml, {"content-type": "text/xml"})
        if url.endswith("/api/monitoring/status"):
            xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<response>"
                "<ConnectionStatus>901</ConnectionStatus>"
                "<CurrentNetworkType>19</CurrentNetworkType>"
                "<SignalIcon>4</SignalIcon>"
                "</response>"
            )
            return (200, xml, {"content-type": "text/xml"})
        return (404, "", {})

    router = discover_router(TEST_GATEWAY_IP, port_prober=_port_prober, http_fetcher=_http_fetcher)
    assert isinstance(router, HuaweiHiLinkRouterAdapter)
    assert router.adapter_kind == "huawei_hilink"
    assert not any(":49000" in url for url in http_calls), "Must not send HTTP/SOAP to :49000 when port is closed"

    status = router.get_status()
    assert status["adapter"] == "huawei_hilink"
    assert status["model"] == "TEST-CPE"
    assert status["connection_status"] == "901"
    assert status["signal_bars"] == 4

    wan = router.get_wan_info()
    assert wan["connected"] is True

    # Unsupported write operations MUST raise UnsupportedCapabilityError (never return True)
    caps = router.capabilities()
    assert caps["router.set_wifi"].supported is False
    assert caps["router.set_guest_wifi"].supported is False

    with pytest.raises(UnsupportedCapabilityError, match="router.set_wifi"):
        router.set_wifi(True)
    with pytest.raises(UnsupportedCapabilityError, match="router.set_guest_wifi"):
        router.set_guest_wifi(False)
    with pytest.raises(UnsupportedCapabilityError, match="router.list_hosts"):
        router.list_hosts()


def test_tf08_discover_fritzbox_and_generic_fallback() -> None:
    """TF-08: Open :49000 with AVM tr64desc.xml yields FritzBoxRouterAdapter; unknown host yields GenericGatewayAdapter."""
    fb = discover_router(
        "198.51.100.1",
        port_prober=lambda _h, port, _t: port == 49000,
        http_fetcher=lambda url, _t: (
            (200, "<root xmlns='urn:dslforum-org:device-1-0'><friendlyName>AVM FRITZ!Box</friendlyName></root>", {})
            if "tr64desc.xml" in url
            else (404, "", {})
        ),
    )
    assert isinstance(fb, FritzBoxRouterAdapter)
    assert fb.adapter_kind == "fritzbox"

    generic = discover_router(
        "203.0.113.1",
        port_prober=lambda _h, port, _t: port == 80,
        http_fetcher=lambda _url, _t: (200, "<html>Generic TEST-CPE Gateway</html>", {}),
    )
    assert isinstance(generic, GenericGatewayAdapter)
    assert generic.adapter_kind == "generic_gateway"
    assert generic.get_status()["reachable"] is True
    with pytest.raises(UnsupportedCapabilityError, match="router.set_guest_wifi"):
        generic.set_guest_wifi(True)


# ---- TF-09: FritzBox Post-Switch GetInfo Readback & Non-Zero Exit on Mismatch ----


def test_tf09_fritzbox_post_switch_readback_success_and_mismatch(capsys: pytest.CaptureFixture[str]) -> None:
    """TF-09: After SetEnable, adapter polls GetInfo and reports verified=True/False; CLI exits 1 on mismatch."""
    soap_log: list[tuple[str, str, dict | None]] = []
    # Simulate radio taking 1 backoff step before transitioning from '0' to '1'
    getinfo_states = ["0", "1"]

    def _soap_ok(service: str, action: str, params: dict | None) -> str:
        soap_log.append((service, action, params))
        if action == "SetEnable":
            return "<s:Envelope><u:SetEnableResponse/></s:Envelope>"
        if action == "GetInfo":
            cur = getinfo_states.pop(0) if getinfo_states else "1"
            st = "Up" if cur == "1" else "Disabled"
            return (
                "<s:Envelope>"
                f"<NewEnable>{cur}</NewEnable>"
                f"<NewStatus>{st}</NewStatus>"
                "<NewSSID>Guest-TestNet</NewSSID>"
                "</s:Envelope>"
            )
        return "<s:Envelope/>"

    fb_ok = FritzBoxRouterAdapter(
        TEST_GATEWAY_IP,
        soap_caller=_soap_ok,
        max_readback_attempts=3,
        readback_backoff_s=0.0,
    )
    res_ok = fb_ok.set_guest_wifi(True)
    assert res_ok["ok"] is True
    assert res_ok["verified"] is True
    assert res_ok["requested_enabled"] is True
    assert res_ok["actual_enabled"] is True
    assert res_ok["status"] == "Up"
    assert res_ok["readback_attempts"] == 2
    assert [a for _, a, _ in soap_log] == ["SetEnable", "GetInfo", "GetInfo"]

    # Now simulate router ignoring SetEnable (stays '0' / Disabled across all readback attempts)
    def _soap_stuck(_service: str, action: str, _params: dict | None) -> str:
        if action == "SetEnable":
            return "<s:Envelope><u:SetEnableResponse/></s:Envelope>"
        return "<s:Envelope><NewEnable>0</NewEnable><NewStatus>Disabled</NewStatus><NewSSID>Guest-TestNet</NewSSID></s:Envelope>"

    fb_mismatch = FritzBoxRouterAdapter(
        TEST_GATEWAY_IP,
        soap_caller=_soap_stuck,
        max_readback_attempts=2,
        readback_backoff_s=0.0,
    )
    res_bad = fb_mismatch.set_guest_wifi(True)
    assert res_bad["ok"] is False
    assert res_bad["verified"] is False
    assert res_bad["requested_enabled"] is True
    assert res_bad["actual_enabled"] is False
    assert res_bad["status"] == "Disabled"

    with pytest.raises(RouterReadbackVerificationError):
        fb_mismatch.set_guest_wifi(True, raise_on_unverified=True)

    # CLI must NEVER exit 0 silently when readback is unverified!
    from unittest.mock import patch

    hub = HomeControlHub(router=fb_mismatch)
    with patch("ellmos_homecontrol.cli.HomeControlHub", return_value=hub):
        rc = cli_main(["router-set-guest-wifi", "on", "--confirm"])
    assert rc == 1
    out_json = json.loads(capsys.readouterr().out)
    assert out_json["verified"] is False

    # Honest DHCP static lease capability declaration (§3.3)
    assert fb_ok.capabilities()["router.set_dhcp_reservation"].supported is False
    assert fb_ok.capabilities()["router.set_dhcp_reservation"].method == "web_session"
    with pytest.raises(UnsupportedCapabilityError, match="web_session"):
        fb_ok.set_dhcp_reservation("02:00:5E:10:00:01", "192.0.2.50", "robot-test")


# ---- Credential Resolution & Secret Masking (`SesInfo` / `TokInfo` / Passwords) ----


def test_credential_resolution_priority_and_secret_masking(tmp_path: Path) -> None:
    """Verifies keyring -> ELLMOS_HOMECONTROL_CREDENTIALS_DIR priority and strict redaction in logs/errors."""

    class FakeKeyring:
        def __init__(self, data: dict[tuple[str, str], str]) -> None:
            self.data = data

        def get_password(self, service: str, key: str) -> str | None:
            return self.data.get((service, key))

    cred_dir = tmp_path / "creds"
    fb_dir = cred_dir / "router-fritzbox"
    fb_dir.mkdir(parents=True)
    (fb_dir / "default.txt").write_text("USERNAME=dir-admin\nPASSWORD=DirSecretValue99!\n", encoding="utf-8")

    # 1. Keyring wins over credentials_dir
    kr = FakeKeyring({("ellmos-homecontrol", "router.fritzbox.default"): '{"username": "kr-user", "password": "KrTopSecret42!"}'})
    c1 = resolve_router_credentials("fritzbox", "default", credentials_dir=cred_dir, keyring_backend=kr)
    assert isinstance(c1, RouterCredentials)
    assert c1.source == "keyring"
    assert c1.username == "kr-user"
    assert c1.secret == "KrTopSecret42!"
    assert "KrTopSecret42!" not in repr(c1)
    assert "KrTopSecret42!" not in json.dumps(c1.as_safe_dict())

    # 2. Fallback to credentials_dir when keyring has no entry
    empty_kr = FakeKeyring({})
    c2 = resolve_router_credentials("fritzbox", "default", credentials_dir=cred_dir, keyring_backend=empty_kr)
    assert c2.source == "credentials_dir"
    assert c2.username == "dir-admin"
    assert c2.secret == "DirSecretValue99!"

    # 3. Secret scrubbing for Huawei SesInfo/TokInfo, SOAP passwords, and HTTP headers
    raw_leak = (
        "<response><SesInfo>SessionID=abcdef1234567890</SesInfo>"
        "<TokInfo>9876543210fedcba</TokInfo>"
        "<NewPassword>SuperGeheim123</NewPassword></response> "
        "Authorization: Digest username=\"admin\", response=\"deadbeef\" "
        "password=PlainPassValue"
    )
    masked = redact_secrets(raw_leak, extra_secrets=["CustomSecretXYZ"])
    for forbidden_tok in ("abcdef1234567890", "9876543210fedcba", "SuperGeheim123", "deadbeef", "PlainPassValue"):
        assert forbidden_tok not in masked
    assert "<redacted>" in masked

    err = RouterError("Auth failed with token CustomSecretXYZ and SesInfo=mycookie123", extra_secrets=["CustomSecretXYZ"])
    assert "CustomSecretXYZ" not in str(err)
    assert "mycookie123" not in str(err)


# ---- HomeControlHub Roles (`network-observer` / `router-operator`) & Tier-2 / Tier-3 Gates ----


def test_hub_router_roles_and_tier2_tier3_authority_gates() -> None:
    """Verifies manifest roles[] and Tier-2 (guest Wi-Fi) vs Tier-3 (disabling main Wi-Fi) confirmation gates."""
    manifest = json.loads((REPO_ROOT / "ellmos-module.v2.json").read_text(encoding="utf-8"))
    roles = {r["id"]: r for r in manifest.get("roles", [])}
    assert "network-observer" in roles
    assert "router-operator" in roles
    assert "router.discover" in roles["network-observer"]["capabilities"]
    assert "router.set_wifi" in roles["router-operator"]["capabilities"]

    def _soap_mock(_svc: str, action: str, params: dict | None) -> str:
        if action == "GetInfo":
            return "<s:Envelope><NewModelName>FRITZ!Box Test</NewModelName><NewEnable>1</NewEnable><NewStatus>Up</NewStatus></s:Envelope>"
        if action == "GetHostNumberOfEntries":
            return "<s:Envelope><NewHostNumberOfEntries>1</NewHostNumberOfEntries></s:Envelope>"
        if action == "GetGenericHostEntry":
            return (
                "<s:Envelope><NewHostName>test-sensor</NewHostName>"
                "<NewIPAddress>192.0.2.25</NewIPAddress>"
                "<NewMACAddress>02:00:5E:10:00:25</NewMACAddress>"
                "<NewInterfaceType>802.11</NewInterfaceType>"
                "<NewActive>1</NewActive></s:Envelope>"
            )
        _ = params
        return "<s:Envelope/>"

    fb = FritzBoxRouterAdapter(TEST_GATEWAY_IP, soap_caller=_soap_mock, readback_backoff_s=0.0)
    hub = HomeControlHub(router=fb)

    # Tier-1 read works without confirmation
    st = hub.hc_router_status()
    assert st["model"] == "FRITZ!Box Test"
    hosts = hub.hc_router_hosts()
    assert len(hosts) == 1
    assert hosts[0]["ip_address"] == "192.0.2.25"

    # Permission gate blocks router access when smarthome_permission=False
    locked_hub = HomeControlHub(router=fb, smarthome_permission=False)
    with pytest.raises(PermissionError, match="smarthome_robotics=False"):
        locked_hub.hc_router_status()

    # Tier-2 gate: Guest Wi-Fi requires confirmed=True or non-empty evidence_quote
    with pytest.raises(RouterAuthorityGateError) as exc_t2:
        hub.hc_router_set_guest_wifi(True)
    assert exc_t2.value.tier == 2

    ok_guest = hub.hc_router_set_guest_wifi(True, evidence_quote="2026-11-26 User: Schalte das Gast-WLAN ein")
    assert ok_guest["verified"] is True

    # Tier-3 hard gate: Disabling main Wi-Fi (self-lockout risk!) requires BOTH confirmed=True AND hard_gate_ack=True
    def _soap_disable_mock(_svc: str, action: str, _params: dict | None) -> str:
        if action == "GetInfo":
            return "<s:Envelope><NewEnable>0</NewEnable><NewStatus>Disabled</NewStatus></s:Envelope>"
        return "<s:Envelope/>"

    fb_dis = FritzBoxRouterAdapter(TEST_GATEWAY_IP, soap_caller=_soap_disable_mock, readback_backoff_s=0.0)
    hub_dis = HomeControlHub(router=fb_dis)

    with pytest.raises(RouterAuthorityGateError) as exc_t3_a:
        hub_dis.hc_router_set_wifi(False, confirmed=True, hard_gate_ack=False)
    assert exc_t3_a.value.tier == 3

    ok_dis = hub_dis.hc_router_set_wifi(False, confirmed=True, hard_gate_ack=True)
    assert ok_dis["verified"] is True
    assert ok_dis["actual_enabled"] is False


def test_public_repo_privacy_guard() -> None:
    """Ensures only RFC 5737 synthetic test IPs and zero local user paths exist in tracked sources."""
    user_path_re = re.compile(r"[A-Z]:\\Users\\", re.IGNORECASE)
    rfc1918_re = re.compile(r"\b192\.168\.\d+\.\d+\b")
    for folder in (REPO_ROOT / "src", REPO_ROOT / "tests"):
        for py_file in folder.rglob("*.py"):
            if py_file.name == "test_router_adapter.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            assert not user_path_re.search(text), f"Local user path found in {py_file.name}"
            assert not rfc1918_re.search(text), f"Non-RFC5737 192.168.x.x IP found in {py_file.name}"
