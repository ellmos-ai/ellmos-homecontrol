"""CLI entrypoint for ellmos-homecontrol."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from .hub import HomeControlHub


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ellmos-homecontrol", description="SmartHome & household appliance control CLI")
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

    args = parser.parse_args(argv)
    hub = HomeControlHub()

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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
