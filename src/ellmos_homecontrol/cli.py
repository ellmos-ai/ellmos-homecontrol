"""CLI entrypoint for ellmos-homecontrol."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .hub import HomeControlHub
from .router import RouterAuthorityGateError, RouterError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ellmos-homecontrol",
        description="SmartHome, household appliance, and vendor-neutral router control CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_p = sub.add_parser("list", help="List SmartHome devices")
    list_p.add_argument("--adapter", choices=["fritzbox", "homeassistant", "matter", "mqtt_shelly"])

    get_p = sub.add_parser("get", help="Get state of a specific device")
    get_p.add_argument("device_id")

    set_p = sub.add_parser("set", help="Update device state with JSON patch")
    set_p.add_argument("device_id")
    set_p.add_argument("state_json")
    set_p.add_argument("--confirm", action="store_true", help="Confirm high-load/appliance action")

    scene_p = sub.add_parser("scene", help="Activate a SmartHome scene")
    scene_p.add_argument("scene_id")

    sub.add_parser("energy", help="Show aggregated SmartHome power consumption")

    # Vendor-neutral router subcommands
    r_disc = sub.add_parser("router-discover", help="Auto-detect gateway router vendor and capabilities")
    r_disc.add_argument("--gateway", default="192.0.2.1", help="Gateway IPv4 address")

    r_stat = sub.add_parser("router-status", help="Read vendor-neutral router status")
    r_stat.add_argument("--gateway", default="192.0.2.1", help="Gateway IPv4 address")

    r_hosts = sub.add_parser("router-hosts", help="List router-known LAN/WLAN hosts when supported")
    r_hosts.add_argument("--gateway", default="192.0.2.1", help="Gateway IPv4 address")

    r_guest = sub.add_parser("router-set-guest-wifi", help="Switch guest Wi-Fi with mandatory GetInfo readback")
    r_guest.add_argument("target", choices=["on", "off"])
    r_guest.add_argument("--gateway", default="192.0.2.1", help="Gateway IPv4 address")
    r_guest.add_argument("--confirm", action="store_true", help="Confirm Tier-2 router operator action")
    r_guest.add_argument("--evidence-quote", default=None, help="User quote authorizing Tier-2 action")

    r_wifi = sub.add_parser("router-set-wifi", help="Switch main Wi-Fi with mandatory GetInfo readback")
    r_wifi.add_argument("target", choices=["on", "off"])
    r_wifi.add_argument("--service-index", type=int, default=1, choices=[1, 2], help="WLANConfiguration index (1 or 2)")
    r_wifi.add_argument("--gateway", default="192.0.2.1", help="Gateway IPv4 address")
    r_wifi.add_argument("--confirm", action="store_true", help="Confirm router operator action")
    r_wifi.add_argument(
        "--hard-gate-ack",
        action="store_true",
        help="Required Tier-3 acknowledgment when disabling main Wi-Fi (self-lockout protection)",
    )
    r_wifi.add_argument("--evidence-quote", default=None, help="User quote authorizing Tier-2 enable action")

    args = parser.parse_args(argv)
    hub = HomeControlHub()

    try:
        if args.cmd == "list":
            print(json.dumps(hub.hc_list_devices(adapter=args.adapter), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "get":
            print(json.dumps(hub.hc_get_state(args.device_id), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "set":
            res = hub.hc_set_state(args.device_id, json.loads(args.state_json), confirmed=args.confirm)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "scene":
            print(json.dumps(hub.hc_scene_activate(args.scene_id), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "energy":
            print(json.dumps(hub.hc_energy_status(), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "router-discover":
            print(json.dumps(hub.hc_router_discover(gateway_ip=args.gateway), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "router-status":
            print(json.dumps(hub.hc_router_status(gateway_ip=args.gateway), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "router-hosts":
            print(json.dumps(hub.hc_router_hosts(gateway_ip=args.gateway), indent=2, ensure_ascii=False))
            return 0
        if args.cmd == "router-set-guest-wifi":
            res = hub.hc_router_set_guest_wifi(
                args.target == "on",
                confirmed=bool(args.confirm),
                evidence_quote=args.evidence_quote,
                gateway_ip=args.gateway,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0 if res.get("verified") is True else 1
        if args.cmd == "router-set-wifi":
            res = hub.hc_router_set_wifi(
                args.target == "on",
                service_index=int(args.service_index),
                confirmed=bool(args.confirm),
                hard_gate_ack=bool(args.hard_gate_ack),
                evidence_quote=args.evidence_quote,
                gateway_ip=args.gateway,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0 if res.get("verified") is True else 1
    except (RouterAuthorityGateError, RouterError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), indent=2, ensure_ascii=False, file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
