#!/usr/bin/env python3
"""Probe RSS-2B sieve shaker UART: start at amp 5, stop, expect OK."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hardware_service


def main():
    port = os.environ.get("ESP_PORT", "/dev/serial0")
    print(f"Probing shaker on {port}...")
    hardware_service.init(type("App", (), {"logger": None})(), {
        "ESP_PORT": port,
        "ESP_BAUD": int(os.environ.get("ESP_BAUD", "9600")),
        "UART_LOG_PATH": os.path.join(os.path.dirname(os.path.dirname(__file__)), "uart_communications.log"),
    })
    time.sleep(0.5)
    print("TX #05C")
    start = hardware_service.cmd_shaker_start(5, "C")
    print("Start:", start)
    time.sleep(2)
    print("TX #00C")
    stop = hardware_service.cmd_shaker_stop("C")
    print("Stop:", stop)
    if stop.get("ok"):
        print("PASS — received OK on stop")
        return 0
    print("FAIL — no OK on stop")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
