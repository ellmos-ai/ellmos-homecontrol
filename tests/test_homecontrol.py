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
