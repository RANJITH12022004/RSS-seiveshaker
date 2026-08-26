#!/usr/bin/env python3
"""
hx711_service.py - HX711 load cell ADC reader using GPIO IO0 (DATA) and IO1 (CLK).
Uses lgpio for bit-bang communication with the HX711 chip.
Supports 4-decimal-place weight output.
"""

import threading
import time
import logging
import os

_logger = logging.getLogger(__name__)

# GPIO pin numbers (BCM) — IO0 = DATA, IO1 = CLK
DATA_PIN = 0   # IO0
CLK_PIN  = 1   # IO1

GAIN_128 = 1   # Channel A, gain 128
GAIN_64  = 3   # Channel A, gain 64
GAIN_32  = 2   # Channel B, gain 32

_hx_lock = threading.Lock()
_h = None           # lgpio handle
_tare_offset = 0.0
_scale_factor = 1.0  # grams per raw unit — calibrate via /api/scale/calibrate
_last_weight = None
_last_raw = None
_initialized = False
_config = {}


def _allow_scale_sim() -> bool:
    return str(os.environ.get("ALLOW_SCALE_SIM", "0")).strip().lower() in ("1", "true", "yes", "on")


def _open_gpio():
    global _h
    try:
        import lgpio
        _h = lgpio.gpiochip_open(0)
        lgpio.gpio_claim_input(_h, DATA_PIN, lgpio.SET_PULL_UP)
        lgpio.gpio_claim_output(_h, CLK_PIN, 0)
        return True
    except Exception as e:
        _logger.warning("hx711_service: failed to open GPIO: %s", e)
        _h = None
        return False


def _read_raw_hx711(gain_pulses=GAIN_128):
    """Bit-bang read 24-bit signed value from HX711. Returns int or None on error."""
    import lgpio
    if _h is None:
        return None

    # Wait for DATA to go LOW (DRDY) — up to 500 ms
    deadline = time.monotonic() + 0.5
    while lgpio.gpio_read(_h, DATA_PIN) != 0:
        if time.monotonic() > deadline:
            _logger.debug("hx711_service: DRDY timeout")
            return None
        time.sleep(0.0001)

    raw = 0
    for _ in range(24):
        lgpio.gpio_write(_h, CLK_PIN, 1)
        time.sleep(0.000001)
        bit = lgpio.gpio_read(_h, DATA_PIN)
        lgpio.gpio_write(_h, CLK_PIN, 0)
        time.sleep(0.000001)
        raw = (raw << 1) | bit

    # Send gain selection pulses
    for _ in range(gain_pulses):
        lgpio.gpio_write(_h, CLK_PIN, 1)
        time.sleep(0.000001)
        lgpio.gpio_write(_h, CLK_PIN, 0)
        time.sleep(0.000001)

    # Convert 24-bit two's complement to signed int
    if raw & 0x800000:
        raw -= 0x1000000
    return raw


def init(app_or_config, config=None):
    global _initialized, _config, _scale_factor, _tare_offset
    if config is None:
        cfg = app_or_config or {}
    else:
        cfg = config
    _config = dict(cfg)
    _scale_factor = float(_config.get("HX711_SCALE_FACTOR", 1.0))
    _tare_offset = float(_config.get("HX711_TARE_OFFSET", 0.0))
    _initialized = _open_gpio()
    if _initialized:
        _logger.info("hx711_service: GPIO opened (DATA=IO%d, CLK=IO%d)", DATA_PIN, CLK_PIN)
    else:
        _logger.warning("hx711_service: running in simulation mode (no GPIO)")


def tare(samples=10):
    """Set tare by averaging N samples."""
    global _tare_offset
    with _hx_lock:
        readings = []
        for _ in range(samples):
            r = _read_raw_hx711()
            if r is not None:
                readings.append(r)
            time.sleep(0.05)
        if readings:
            _tare_offset = sum(readings) / len(readings)
            _logger.info("hx711_service: tare set to %.2f", _tare_offset)
            return True
        return False


def set_scale_factor(factor):
    global _scale_factor
    _scale_factor = float(factor)


def read_weight(samples=5):
    """
    Read weight averaged over N samples.
    Returns dict: { ok: bool, weight: float (4dp), raw: int, unit: 'g' }
    """
    global _last_weight, _last_raw
    with _hx_lock:
        if not _initialized or _h is None:
            if _allow_scale_sim():
                import random
                sim = round(50.0 + random.uniform(-0.5, 0.5), 4)
                return {"ok": True, "weight": sim, "raw": 0, "unit": "g", "simulated": True}
            return {"ok": False, "weight": None, "raw": 0, "unit": "g", "simulated": True, "error": "Scale not ready"}

        readings = []
        for _ in range(samples):
            r = _read_raw_hx711()
            if r is not None:
                readings.append(r)
            time.sleep(0.02)

        if not readings:
            # HX711 not responding — never invent a weight in production
            if _allow_scale_sim():
                import random
                sim = round(50.0 + random.uniform(-0.5, 0.5), 4)
                _logger.debug("hx711_service: HX711 not responding, returning simulated weight")
                return {"ok": True, "weight": sim, "raw": 0, "unit": "g", "simulated": True, "warning": "HX711 DRDY timeout"}
            return {"ok": False, "weight": None, "raw": 0, "unit": "g", "simulated": True, "error": "Scale not ready", "warning": "HX711 DRDY timeout"}

        avg_raw = sum(readings) / len(readings)
        _last_raw = avg_raw

        if _scale_factor == 0:
            return {"ok": False, "error": "Scale factor is zero", "weight": None}

        grams = (avg_raw - _tare_offset) / _scale_factor
        grams = round(grams, 4)
        _last_weight = grams
        return {"ok": True, "weight": grams, "raw": int(avg_raw), "unit": "g"}


def get_status():
    return {
        "initialized": _initialized,
        "data_pin": DATA_PIN,
        "clk_pin": CLK_PIN,
        "tare_offset": _tare_offset,
        "scale_factor": _scale_factor,
        "last_weight": _last_weight,
        "last_raw": _last_raw,
    }
