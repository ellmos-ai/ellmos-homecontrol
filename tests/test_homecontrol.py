"""Tests for ellmos-homecontrol SmartHome adapters, MCP tools, and high-load safety gate."""

from __future__ import annotations

import json
import pytest

from ellmos_homecontrol import (
    FritzBoxAdapter,
    HighLoadConfirmationRequiredError,
    HomeControlHub,
)
from ellmos_homecontrol.cli import main


def test_list_and_energy_status():
    hub = HomeControlHub()
    devices = hub.hc_list_devices()
    assert len(devices) == 4
    fritz_only = hub.hc_list_devices(adapter="fritzbox")
    assert len(fritz_only) == 1
    energy = hub.hc_energy_status()
    assert energy["schema"] == "ellmos.homecontrol.energy.v1"
    assert energy["total_power_watts"] > 0


def test_high_load_appliance_requires_confirmation():
    hub = HomeControlHub()
    with pytest.raises(HighLoadConfirmationRequiredError, match="confirmed=True"):
        hub.hc_set_state("shelly.appliance.washer", {"on": True, "cycle": "eco_40"})

    updated = hub.hc_set_state("shelly.appliance.washer", {"on": True, "cycle": "eco_40"}, confirmed=True)
    assert updated["state"]["on"] is True
    assert updated["state"]["cycle"] == "eco_40"


def test_permission_gate_blocks_when_disabled():
    hub = HomeControlHub(smarthome_permission=False)
    with pytest.raises(PermissionError, match="smarthome_robotics=False"):
        hub.hc_list_devices()


def test_scene_activation_and_fritz_xml_helper():
    hub = HomeControlHub()
    res = hub.hc_scene_activate("focus_work")
    assert "ha.light.studio_main" in res["applied_devices"]
    assert hub.hc_get_state("ha.light.studio_main")["state"]["brightness_pct"] == 100

    xml_sample = "<s:Envelope><NewConnectionStatus>Connected</NewConnectionStatus></s:Envelope>"
    assert FritzBoxAdapter.xml_value(xml_sample, "NewConnectionStatus") == "Connected"


def test_cli_commands(capsys):
    assert main(["energy"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["device_count"] == 4


def test_demo_data_is_marked_demo():
    hub = HomeControlHub()
    assert all(d["demo"] is True for d in hub.hc_list_devices())
    assert hub.hc_get_state("ha.light.studio_main")["demo"] is True
    assert hub.hc_energy_status()["demo"] is True
    assert hub.hc_scene_activate("focus_work")["demo"] is True
    assert hub.hc_set_state("ha.light.studio_main", {"on": False})["demo"] is True


def test_custom_devices_are_not_marked_demo():
    from ellmos_homecontrol import HomeDevice

    dev = HomeDevice("x.plug", "Plug", "fritzbox", "plug", {"on": True})
    hub = HomeControlHub(devices=[dev])
    assert hub.hc_list_devices()[0]["demo"] is False
    assert hub.hc_energy_status()["demo"] is False


def test_tr064_soap_injection_is_escaped_or_rejected():
    from unittest.mock import MagicMock, patch

    fb = FritzBoxAdapter()

    # 1. Parameter value with XML tags must be escaped
    resp = MagicMock()
    resp.read.return_value = b"<s:Envelope/>"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=resp) as m:
        fb.tr064_call(
            "urn:dslforum-org:service:DeviceInfo:1",
            "GetInfo",
            params={"NewEnable": "1</NewEnable><injected>pwned</injected><NewEnable>1"},
        )
    assert m.called
    sent_body = m.call_args[0][0].data.decode("utf-8")
    assert "<injected>pwned</injected>" not in sent_body
    assert "&lt;injected&gt;pwned&lt;/injected&gt;" in sent_body

    # 2. Invalid action name with XML tag injection must be rejected without network
    with patch("urllib.request.urlopen") as m:
        assert fb.tr064_call("urn:dslforum-org:service:DeviceInfo:1", "GetInfo><evil/>") is None
        m.assert_not_called()

    # 3. Invalid argument key with XML tag injection must be rejected without network
    with patch("urllib.request.urlopen") as m:
        assert fb.tr064_call(
            "urn:dslforum-org:service:DeviceInfo:1",
            "GetInfo",
            params={"bad<tag>": "1"},
        ) is None
        m.assert_not_called()

