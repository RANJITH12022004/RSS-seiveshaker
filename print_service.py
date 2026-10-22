#!/usr/bin/env python3
"""
print_service.py - Printing operations service
Reference-aligned A4 and thermal printing over serial.
"""

import logging
import os
import pathlib
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

import calculation_service

# Serialize all printer I/O so a second Print press cannot interleave ESC/POS bytes.
_PRINT_IO_LOCK = threading.Lock()
_PRINT_BUSY = False

try:
    import serial
except ImportError:
    serial = None

try:
    import bridge_services
except ImportError:
    bridge_services = None

try:
    from report_service import (
        build_test_report_derived,
        format_duration_hhmmss,
        test_duration_seconds,
        _format_derived_number,
    )
except ImportError:
    def build_test_report_derived(td, recipe=None, report_id=None):
        return {}

    def _format_derived_number(val, decimals=3):
        return "--" if val is None else str(val)
    def format_duration_hhmmss(seconds_val):
        if seconds_val is None:
            return "--"
        try:
            total_s = int(seconds_val)
        except (TypeError, ValueError):
            return "--"
        if total_s < 0:
            return "--"
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def test_duration_seconds(td):
        if not isinstance(td, dict):
            return None
        sec = td.get("durationSeconds")
        if sec is not None:
            try:
                return max(0, int(sec))
            except (TypeError, ValueError):
                pass
        return None

A4_CANDIDATES = ["/dev/ttyAMA4", "/dev/ttyUSB0", "/dev/ttyUSB1", "COM3", "COM4"]
THERMAL_CANDIDATES = ["/dev/ttyAMA3", "/dev/ttyUSB0", "/dev/ttyUSB1", "COM3", "COM4"]
THERMAL_WIDTH = 32
THERMAL_LINE_CHUNK = 32
A4_TEXT_WIDTH = 80
# Blank lines after content so date/time and footer clear the cutter (avoid half-cut).
THERMAL_POST_PRINT_FEED_LINES = 3

_PRINTER_INIT_SEQ = b"\x1b\x40"
_log = logging.getLogger(__name__)

_config = {}
_a4_port = None
_a4_baud = None
_thermal_port = None
_thermal_baud = None


def init(config):
    global _config, _a4_port, _a4_baud, _thermal_port, _thermal_baud
    _config = dict(config)
    _a4_port = _config.get("A4_PORT", "/dev/ttyAMA4")
    _a4_baud = int(_config.get("A4_BAUD", 9600))
    _thermal_port = _config.get("THERMAL_PORT", "/dev/ttyAMA3")
    _thermal_baud = int(_config.get("THERMAL_BAUD", 9600))


def _is_windows_com_port(port: str) -> bool:
    return bool(port and str(port).strip().upper().startswith("COM"))


def _port_exists(port: str) -> bool:
    if not port:
        return False
    if _is_windows_com_port(port):
        return True
    return os.path.exists(port)


def _probe_port(port: str, candidates: list) -> str:
    cands = ([port] if port else []) + [c for c in candidates if c and c != port]
    if bridge_services:
        return bridge_services.probe_and_choose_port(port, candidates=cands)
    if port and _port_exists(port):
        return port
    for p in candidates:
        if p and _port_exists(p):
            return p
    raise FileNotFoundError(2, "Serial device not found", port or "no-config")


def check_printer_status(printer_type: str = "a4") -> Dict[str, Any]:
    port = _a4_port if printer_type == "a4" else _thermal_port
    baud = _a4_baud if printer_type == "a4" else _thermal_baud
    if not serial:
        return {"available": False, "error": "pyserial not installed", "port": port}
    if not _port_exists(port):
        return {"available": False, "error": f"Printer port not found: {port}", "port": port}
    try:
        ser = serial.Serial(port=port, baudrate=baud, timeout=1.0)
        ser.close()
        return {"available": True, "port": port, "baud": baud}
    except Exception as e:
        return {"available": False, "error": str(e), "port": port}


def _open_a4_serial(port: str, baud: int):
    params = dict(
        port=port,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=2,
        write_timeout=2,
    )
    try:
        return serial.Serial(**params)
    except Exception:
        time.sleep(0.5)
        return serial.Serial(**params)


def _send_printer_init(ser) -> None:
    ser.write(_PRINTER_INIT_SEQ)
    ser.flush()
    time.sleep(0.05)


def _send_bytes_chunked(ser, data: bytes, baud: int, chunk_size: int = 64) -> None:
    delay = 0.08 if baud <= 9600 else 0.04
    for i in range(0, len(data), chunk_size):
        ser.write(data[i : i + chunk_size])
        ser.flush()
        if i + chunk_size < len(data):
            time.sleep(delay)
    time.sleep(0.1)


def _send_text_chunked(ser, text: str, baud: int, chunk_size: int = 64) -> None:
    try:
        data = text.encode("utf-8", errors="replace")
    except Exception:
        data = text.encode("latin-1", errors="replace")
    _send_bytes_chunked(ser, data, baud, chunk_size=chunk_size)


def _thermal_sep(char: str, width: int = THERMAL_WIDTH) -> str:
    return (char * width)[:width]


def _fit_thermal_line(line: str, width: int = THERMAL_WIDTH) -> list:
    """Split or truncate a single logical line to at most `width` characters per row."""
    s = str(line) if line is not None else ""
    if not s.strip() and s == "":
        return [""]
    if len(s) <= width:
        return [s]
    out = []
    while s:
        out.append(s[:width])
        s = s[width:]
    return out


def _apply_thermal_line_spacing(lines: list, width: int = THERMAL_WIDTH) -> list:
    """Extra blank line after each printed row for readable line spacing."""
    out: list = []
    for line in lines:
        for part in _fit_thermal_line(line, width):
            out.append(part)
            if part.strip():
                out.append("")
    return out


def _compact_thermal_lines(lines: list, width: int = THERMAL_WIDTH) -> list:
    """Fit thermal lines without adding filler space between every row."""
    out: list = []
    previous_blank = False
    for line in lines:
        parts = _fit_thermal_line(line, width)
        for part in parts:
            is_blank = not str(part or "").strip()
            if is_blank and previous_blank:
                continue
            out.append(part)
            previous_blank = is_blank
    while out and not str(out[-1] or "").strip():
        out.pop()
    return out


def _send_text_to_thermal(ser, text: str, baud: int) -> None:
    """
    Send thermal text one line at a time (max THERMAL_WIDTH chars per row).
    Avoids buffer overrun that drops the start of long chunked writes.
    """
    line_delay = 0.06 if baud <= 9600 else 0.035
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for line in text.split("\n"):
        if line == "":
            ser.write(b"\n")
            ser.flush()
            time.sleep(0.02)
            continue
        for chunk in _fit_thermal_line(line, THERMAL_LINE_CHUNK):
            payload = (chunk + "\n").encode("latin-1", errors="replace")
            ser.write(payload)
            ser.flush()
            time.sleep(line_delay)
    for _ in range(THERMAL_POST_PRINT_FEED_LINES):
        ser.write(b"\n")
        ser.flush()
        time.sleep(0.06)
    time.sleep(0.5)


def _send_text_to_a4(ser, text: str, baud: int) -> int:
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    data = text.encode("utf-8", errors="replace")
    _send_bytes_chunked(ser, data, baud, chunk_size=512)
    return len(data)


def _format_ts_readable(ts: Any) -> str:
    if ts is None:
        return "--"
    if isinstance(ts, datetime):
        dt = ts.astimezone() if ts.tzinfo is not None else ts
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    s = str(ts).strip()
    if not s:
        return "--"
    try:
        s = s[:-1] + "+00:00" if s[-1:] in ("Z", "z") else s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(ts)


def _format_display_date(value: Any) -> str:
    """Normalize date-only values to DD/MM/YYYY for report output."""
    if value is None:
        return "N/A"
    s = str(value).strip()
    if not s:
        return "N/A"
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%d/%m/%Y")
        except Exception:
            continue
    return s


def _split_ts_date_and_time(ts: Any) -> tuple:
    """Return (date, time) strings for separate thermal print lines."""
    full = _format_ts_readable(ts)
    if full == "--":
        return "--", "--"
    parts = full.split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full, "--"


_THERMAL_FRIABILITY_COL_WIDTHS = (3, 6, 6, 6, 6)


def _thermal_grid_line(
    cells: list,
    widths: tuple = _THERMAL_FRIABILITY_COL_WIDTHS,
    *,
    headers: bool = False,
) -> str:
    """Fixed-position thermal table row with single-space column gaps."""
    parts = []
    for i, (cell, width) in enumerate(zip(cells, widths)):
        s = str(cell if cell is not None else "")
        if len(s) > width:
            s = s[:width]
        parts.append(s.center(width) if headers else s.rjust(width))
        if i < len(cells) - 1:
            parts.append(" ")
    return "".join(parts)


def _thermal_grid_width(widths: tuple = _THERMAL_FRIABILITY_COL_WIDTHS) -> int:
    return sum(widths) + max(0, len(widths) - 1)


def _fmt_friability_thermal(val: Any, width: int = 6) -> str:
    """Friability percent sized for the thermal Fri column."""
    if val is None or val in ("", "__"):
        return "--"
    try:
        f = float(val)
        for prec in (3, 2, 1, 0):
            s = f"{f:.{prec}f}%"
            if len(s) <= width:
                return s
        return f"{f:.0f}%"[:width]
    except (TypeError, ValueError):
        s = str(val).strip()
        if s and not s.endswith("%"):
            s += "%"
        return s[:width] if s else "--"


def _fmt_weight_thermal(val: Any, width: int = 6) -> str:
    s = _fmt_weight_val(val)
    return s[:width] if len(s) > width else s


def _strip_approver_role_label(name: Any) -> str:
    """Remove trailing role label e.g. 'Admin (admin)' -> 'Admin'."""
    s = str(name or "").strip()
    if not s or s == "--":
        return "--"
    if "(" in s and s.endswith(")"):
        head = s.rsplit("(", 1)[0].strip()
        if head:
            return head
    return s


def _is_power_interruption_report(report_data: Dict[str, Any], td: Dict[str, Any]) -> bool:
    """True when a report was system-closed after power loss during test/validation."""
    if not isinstance(report_data, dict):
        report_data = {}
    if not isinstance(td, dict):
        td = {}
    cause = str(report_data.get("abortCause") or td.get("abortCause") or "").strip().lower()
    if cause in ("power_interruption", "power_loss", "power"):
        return True
    for key in ("approvalRemarks", "remarks"):
        text = str(report_data.get(key) or td.get(key) or "").strip().lower()
        if "power interruption" in text:
            return True
    approved_by = str(report_data.get("approvedBy") or "").strip().lower()
    st = str(report_data.get("reportApprovalStatus") or "").strip().lower()
    remarks = str(report_data.get("approvalRemarks") or report_data.get("remarks") or "").lower()
    if approved_by == "system" and "power interruption" in remarks and st in ("approved", "aborted"):
        return True
    return False


def _wrap_lines(lines: list, width: int) -> list:
    out = []
    for line in lines:
        if "\t" in line:
            out.append(line)
            continue
        if len(line) <= width:
            out.append(line)
            continue
        words = line.split()
        if not words:
            out.append("")
            continue
        cur = ""
        for w in words:
            nxt = w if not cur else (cur + " " + w)
            if len(nxt) <= width:
                cur = nxt
            else:
                if cur:
                    out.append(cur)
                cur = w
        if cur:
            out.append(cur)
    return out


def _truncate_with_ellipsis(value: Any, max_len: int) -> str:
    s = "" if value is None else str(value)
    if max_len <= 0:
        return ""
    if len(s) <= max_len:
        return s
    if max_len <= 3:
        return "." * max_len
    return s[: max_len - 3] + "..."


def _append_two_column_pairs(lines: list, pairs: list, width: int) -> None:
    """Append key/value pairs as two aligned columns for A4 text output."""
    if width < 40:
        for label, value in pairs:
            lines.append(f"{label}: {value}")
        return
    gap = 4
    col_w = max(18, (width - gap) // 2)
    value_w = max(8, col_w - 2)

    def _cell(label: Any, value: Any) -> str:
        lbl = _truncate_with_ellipsis(label, 22)
        val = _truncate_with_ellipsis(value, value_w)
        text = f"{lbl}: {val}".strip()
        return text.ljust(col_w)[:col_w]

    normalized = [(str(k or "--"), str(v if v not in (None, "") else "--")) for k, v in pairs]
    for i in range(0, len(normalized), 2):
        left = _cell(normalized[i][0], normalized[i][1])
        right = ""
        if i + 1 < len(normalized):
            right = _cell(normalized[i + 1][0], normalized[i + 1][1])
        lines.append(left + (" " * gap) + right)



def _fmt_density_val(val: Any) -> str:
    if val is None or val == "":
        return "--"
    try:
        f = float(val)
        return f"{f:.3f}".rstrip("0").rstrip(".") if f != int(f) else str(int(f))
    except (TypeError, ValueError):
        return str(val)


def _cell_str(val: Any) -> str:
    if val is None or val in ("", "__"):
        return "--"
    return str(val)


def _normalize_pass_fail(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low in ("pass", "passed"):
        return "Pass"
    if low in ("fail", "failed"):
        return "Fail"
    return s


def _effective_approval_result(report_data: Dict[str, Any], td: Dict[str, Any]) -> str:
    candidates = []
    if isinstance(report_data, dict):
        candidates.extend([
            report_data.get("approvalPassFail"),
            report_data.get("approvalResult"),
            report_data.get("passFail"),
        ])
    if isinstance(td, dict):
        candidates.extend([
            td.get("approvalPassFail"),
            td.get("approvalResult"),
            td.get("passFail"),
        ])
        for row in td.get("stepResults") or []:
            if not isinstance(row, dict):
                continue
            candidates.extend([row.get("resultText"), row.get("result")])
    for value in candidates:
        normalized = _normalize_pass_fail(value)
        if normalized and normalized.lower() not in ("pending", "pending approval", "--", "n/a"):
            return normalized
    return ""


def _drum_approval_results(report_data: Dict[str, Any], td: Dict[str, Any]) -> list:
    rows = td.get("stepResults") if isinstance(td, dict) else []
    rows = rows if isinstance(rows, list) else []
    drum_map = {}
    if isinstance(report_data, dict) and isinstance(report_data.get("drumPassFail"), dict):
        drum_map.update(report_data.get("drumPassFail"))
    if isinstance(td, dict) and isinstance(td.get("drumPassFail"), dict):
        drum_map.update(td.get("drumPassFail"))
    fallback = _effective_approval_result(report_data, td)
    count = max(1, len(rows))
    if isinstance(td, dict):
        try:
            count = max(count, int(td.get("drumCount") or 0))
        except (TypeError, ValueError):
            pass
    count = min(2, count)
    out = []
    for idx in range(count):
        row = rows[idx] if idx < len(rows) and isinstance(rows[idx], dict) else {}
        value = row.get("approvalPassFail") or row.get("resultText") or row.get("result")
        if not value or str(value).strip().lower() in ("pending", "pending approval", "--", "n/a"):
            value = drum_map.get("drum{}".format(idx + 1)) or fallback
        out.append(("Drum {} Pass/Fail".format(idx + 1), _normalize_pass_fail(value) or "--"))
    return out


def _approval_result_pairs(
    report_data: Dict[str, Any], td: Dict[str, Any], report_type: str = "test"
) -> list:
    """Approval pass/fail lines: single Result for validation, drum rows for test reports."""
    rtype = str(report_type or "test").strip().lower()
    if rtype == "validation":
        result = _effective_approval_result(report_data, td)
        if not result:
            result = _validation_overall_status_label(
                td if isinstance(td, dict) else {},
                report_data if isinstance(report_data, dict) else {},
            )
        normalized = _normalize_pass_fail(result)
        return [("Result", normalized or _cell_str(result))]
    return _drum_approval_results(report_data, td)


def _effective_step_row_count(td: Dict[str, Any]) -> int:
    """Rows to print: actual stepResults only (not recipe stepCount)."""
    if not isinstance(td, dict):
        return 0
    results = td.get("stepResults") or []
    if isinstance(results, list) and results:
        return len(results)
    cs = td.get("completedSteps")
    if cs is not None:
        try:
            return max(0, int(cs))
        except (TypeError, ValueError):
            pass
    return 0


def _section_sep(char: str, width: int, thermal: bool) -> str:
    if thermal:
        return _thermal_sep(char, width)
    return char * width


def _thermal_test_data_row(sn: int, cnt: str, vol: str, dvol: str, bulk: str, tap: str) -> str:
    """Legacy tap-density row (kept for reference layouts)."""
    return f"{sn:>2} {str(cnt):>4} {str(vol):>5} {str(dvol):>4} {str(bulk):>4} {str(tap):>4}"


def _fmt_weight_val(val: Any) -> str:
    if val is None or val in ("", "__"):
        return "--"
    try:
        f = float(val)
        return f"{f:.3f}".rstrip("0").rstrip(".") if f != int(f) else str(int(f))
    except (TypeError, ValueError):
        return str(val)


def _fmt_friability_pct(val: Any) -> str:
    if val is None or val in ("", "__"):
        return "--"
    try:
        f = float(val)
        return f"{f:.3f}".rstrip("0").rstrip(".") + "%"
    except (TypeError, ValueError):
        return str(val)


def _effective_friability_step_count(td: Dict[str, Any]) -> int:
    """Rows to print: matches on-screen report preview."""
    if not isinstance(td, dict):
        return 0
    results = td.get("stepResults") or []
    if isinstance(results, list) and results:
        return len(results)
    sc = td.get("stepCount")
    if sc is not None:
        try:
            n = int(sc)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    if td.get("initialWeight") is not None or td.get("finalWeight") is not None:
        return 1
    return _effective_step_row_count(td)


def _friability_step_row_values(td: Dict[str, Any], results: list, index: int) -> Dict[str, str]:
    r = results[index] if index < len(results) and isinstance(results[index], dict) else {}
    w1 = r.get("initialWeight")
    if w1 in (None, ""):
        w1 = td.get("initialWeight")
    w2 = r.get("finalWeight")
    if w2 in (None, ""):
        w2 = td.get("finalWeight")
    diff = r.get("weightDifference")
    if diff in (None, ""):
        diff = td.get("weightDifference")
    fri = r.get("friabilityPercent")
    if fri in (None, ""):
        fri = td.get("friabilityPercent")
    trend = r.get("weightTrend")
    if trend in (None, ""):
        trend = td.get("weightTrend")
    result = r.get("resultText")
    if result in (None, "") or str(result).strip().lower() == "pending approval":
        result = td.get("approvalPassFail") or "--"
    return {
        "w1": _fmt_weight_val(w1),
        "w2": _fmt_weight_val(w2),
        "diff": _fmt_weight_val(diff),
        "friability": _fmt_friability_pct(fri),
        "trend": _cell_str(trend),
        "result": _cell_str(result),
    }


_THERMAL_FRIABILITY_DATA_HEADER = _thermal_grid_line(
    ["#", "W1", "W2", "Diff", "Fri%"], _THERMAL_FRIABILITY_COL_WIDTHS, headers=True
)


def _format_thermal_friability_test_data_table(td: Dict[str, Any], width: int = THERMAL_WIDTH) -> list:
    """Compact friability step table for 32-char thermal paper."""
    w = width
    cols = _THERMAL_FRIABILITY_COL_WIDTHS
    grid_w = _thermal_grid_width(cols)
    dash = _section_sep("-", grid_w, True)
    results = td.get("stepResults") or []
    row_count = _effective_friability_step_count(td)
    lines = [
        _section_sep("=", w, True),
        "TEST DATA",
        dash,
        _THERMAL_FRIABILITY_DATA_HEADER,
        dash,
    ]
    indent = " " * (cols[0] + 1)
    for i in range(row_count):
        row = _friability_step_row_values(td, results, i)
        r = results[i] if i < len(results) and isinstance(results[i], dict) else {}
        fri_raw = r.get("friabilityPercent")
        if fri_raw in (None, ""):
            fri_raw = td.get("friabilityPercent")
        lines.append(
            _thermal_grid_line(
                [
                    i + 1,
                    _fmt_weight_thermal(row["w1"]),
                    _fmt_weight_thermal(row["w2"]),
                    _fmt_weight_thermal(row["diff"]),
                    _fmt_friability_thermal(fri_raw),
                ],
                cols,
            )
        )
        lines.append(f"{indent}Trend: {row['trend']}"[:w])
        lines.append(f"{indent}Result: {row['result']}"[:w])
    lines.append(dash)
    return lines


_THERMAL_TEST_DATA_HEADER = f"{'#':>2} {'Cnt':>4} {'Vol':>5} {'dV':>4} {'Blk':>4} {'Tap':>4}"


def _format_thermal_test_data_table(
    row_count: int, results: list, steps: Optional[list] = None, width: int = THERMAL_WIDTH
) -> list:
    """Compact fixed-width step table for 32-char thermal paper."""
    w = width
    lines = [
        "",
        _section_sep("=", w, True),
        "TEST DATA",
        _section_sep("-", w, True),
        _THERMAL_TEST_DATA_HEADER,
        _section_sep("-", w, True),
    ]
    steps = steps if isinstance(steps, list) else []
    for i in range(row_count):
        r = results[i] if i < len(results) and isinstance(results[i], dict) else {}
        cnt = "--"
        if i < len(steps) and isinstance(steps[i], dict):
            cnt = _cell_str(steps[i].get("tapCount"))
        vol = _cell_str(r.get("volumeMl"))
        dvol = r.get("volumeDeltaMl", "__")
        if dvol not in (None, "", "__"):
            dvol = _fmt_density_val(dvol)
        else:
            dvol = _cell_str(dvol)
        bulk = r.get("bulkDensity", "__")
        if bulk not in (None, "", "__"):
            bulk = _fmt_density_val(bulk)
        else:
            bulk = _cell_str(bulk)
        tap = r.get("tapDensity", "__")
        if tap not in (None, "", "__"):
            tap = _fmt_density_val(tap)
        else:
            tap = _cell_str(tap)
        lines.append(_thermal_test_data_row(i + 1, cnt, vol, dvol, bulk, tap))
    lines.extend(["", _section_sep("-", w, True), ""])
    return lines


def _stat_display_value(val: dict) -> Any:
    """Single statistic value for print (value field, else mean)."""
    if val.get("value") is not None:
        return val.get("value")
    if val.get("mean") is not None:
        mean = val.get("mean")
        min_v = val.get("min")
        max_v = val.get("max")
        if min_v is not None or max_v is not None:
            return f"Avg: {mean} | Min: {min_v if min_v is not None else '--'} | Max: {max_v if max_v is not None else '--'}"
        return mean
    if val.get("Mean") is not None:
        mean = val.get("Mean")
        min_v = val.get("Min")
        max_v = val.get("Max")
        if min_v is not None or max_v is not None:
            return f"Avg: {mean} | Min: {min_v if min_v is not None else '--'} | Max: {max_v if max_v is not None else '--'}"
        return mean
    return None


def _recipe_total_tap_count(recipe: Dict[str, Any]) -> Optional[int]:
    if not isinstance(recipe, dict):
        return None
    ct = recipe.get("customTotalTaps")
    if ct is not None and ct != "":
        try:
            n = int(ct)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    total = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        try:
            total += int(step.get("tapCount") or 0)
        except (TypeError, ValueError):
            pass
    return total if total > 0 else None


def _recipe_total_taps_from_steps_only(recipe: Dict[str, Any]) -> Optional[int]:
    """A4 text report helper: sum only per-step taps, ignore custom total taps."""
    if not isinstance(recipe, dict):
        return None
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    total = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        try:
            total += int(step.get("tapCount") or 0)
        except (TypeError, ValueError):
            pass
    return total if total > 0 else None


def _performed_total_taps(td: Dict[str, Any], recipe: Dict[str, Any]) -> Optional[int]:
    """Sum taps only for steps that were actually performed."""
    if not isinstance(td, dict):
        return None
    results = td.get("stepResults") or []
    if not isinstance(results, list) or not results:
        return None
    steps = recipe.get("steps") if isinstance(recipe, dict) else []
    if not isinstance(steps, list):
        steps = []
    total = 0
    found = False
    for i in range(len(results)):
        step_taps = None
        if i < len(steps) and isinstance(steps[i], dict):
            step_taps = steps[i].get("tapCount")
        if step_taps in (None, "") and isinstance(results[i], dict):
            step_taps = results[i].get("tapCount")
        try:
            n = int(step_taps)
            if n > 0:
                total += n
                found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def _completed_steps_total_taps(td: Dict[str, Any], recipe: Dict[str, Any]) -> Optional[int]:
    """
    Fallback total taps from recipe steps limited to completed step count.
    Keeps totals aligned with "completed/performed" semantics.
    """
    if not isinstance(td, dict) or not isinstance(recipe, dict):
        return None
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    try:
        completed = int(td.get("completedSteps"))
    except (TypeError, ValueError):
        return None
    if completed <= 0:
        return None
    count = min(completed, len(steps))
    total = 0
    found = False
    for i in range(count):
        step = steps[i] if i < len(steps) and isinstance(steps[i], dict) else {}
        try:
            n = int(step.get("tapCount") or 0)
            if n > 0:
                total += n
                found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def _performed_diff_last_two_steps(td: Dict[str, Any]) -> Any:
    """
    Difference between last two performed step volumes.
    If only one performed step exists, use its available volume delta.
    """
    if not isinstance(td, dict):
        return None
    results = td.get("stepResults") or []
    if not isinstance(results, list) or not results:
        return None
    if len(results) >= 2:
        try:
            v1 = float((results[-2] or {}).get("volumeMl"))
            v2 = float((results[-1] or {}).get("volumeMl"))
            return abs(v2 - v1)
        except Exception:
            return None
    one = results[0] if isinstance(results[0], dict) else {}
    try:
        dv = one.get("volumeDeltaMl")
        if dv in (None, ""):
            return None
        return abs(float(dv))
    except Exception:
        return None


def _append_derived_test_summary_and_result(
    lines: list, derived: Dict[str, Any], width: int, thermal: bool
) -> None:
    """Friability weight summary (optional block after TEST DATA)."""
    if not isinstance(derived, dict) or not derived:
        return
    has_any = any(
        derived.get(k) not in (None, "", "--")
        for k in (
            "initialWeight",
            "finalWeight",
            "weightDifference",
            "friabilityPercent",
            "weightTrend",
            "rotationCount",
        )
    )
    if not has_any:
        return
    eq = _section_sep("=", width, thermal)
    dash = _section_sep("-", width, thermal)
    pairs = [
        ("Initial Weight (gms)", _fmt_weight_val(derived.get("initialWeight"))),
        ("Final Weight (gms)", _fmt_weight_val(derived.get("finalWeight"))),
        ("Difference (W2-W1 gms)", _fmt_weight_val(derived.get("weightDifference"))),
        ("Friability (%)", _fmt_friability_pct(derived.get("friabilityPercent")).replace("%", "")),
        ("Trend", _cell_str(derived.get("weightTrend"))),
        ("Rotations", _cell_str(derived.get("rotationCount"))),
        ("Target Rotations", _cell_str(derived.get("targetRotations"))),
    ]
    if thermal:
        lines.extend(["", eq, "TEST SUMMARY", dash])
        for label, val in pairs:
            lines.append(f"{label}: {val}")
        lines.append("")
        return
    lines.extend(["", eq, "TEST SUMMARY", dash])
    _append_two_column_pairs(lines, pairs, width)
    lines.append("")


def _normalize_validation_runs(td: Dict[str, Any], report_data: Dict[str, Any]) -> list:
    if not isinstance(td, dict):
        td = {}
    runs = td.get("validationRuns") or report_data.get("validationRuns")
    if runs and isinstance(runs, list) and len(runs) > 0:
        return [r if isinstance(r, dict) else {} for r in runs]
    return [
        {
            "usp": td.get("usp") or report_data.get("usp"),
            "validationSubtype": td.get("validationSubtype") or report_data.get("validationSubtype"),
            "rpm": td.get("rpm", report_data.get("rpm")),
            "timeMinutes": td.get("timeMinutes", report_data.get("timeMinutes")),
            "tapsMin": td.get("tapsMin", report_data.get("tapsMin")),
            "dropHeight": td.get("dropHeight", report_data.get("dropHeight")),
            "expectedTapCount": td.get("expectedTapCount", report_data.get("expectedTapCount")),
            "expectedTolerance": td.get("expectedTolerance", report_data.get("expectedTolerance")),
            "actualTapCount": td.get("actualTapCount", report_data.get("actualTapCount")),
            "validationDurationSec": td.get("validationDurationSec", report_data.get("validationDurationSec") or td.get("durationSeconds", report_data.get("durationSeconds"))),
            "durationSeconds": td.get("durationSeconds", report_data.get("durationSeconds")),
            "status": td.get("status", report_data.get("status")),
            "validationStartTime": td.get("validationStartTime", report_data.get("validationStartTime") or td.get("testStartTime", report_data.get("testStartTime"))),
            "validationEndTime": td.get("validationEndTime", report_data.get("validationEndTime") or td.get("testEndTime", report_data.get("testEndTime"))),
            "completedAt": td.get("completedAt", report_data.get("completedAt")),
        }
    ]


def _is_friability_validation_run(run: Dict[str, Any]) -> bool:
    sub = str(run.get("validationSubtype") or "").strip().lower()
    usp = str(run.get("usp") or "").strip().lower()
    return sub == "usp" or "friability" in usp


def _validation_expected_value(run: Dict[str, Any]):
    if not isinstance(run, dict):
        return None
    for key in ("expectedTapCount", "expectedRotationCount"):
        if run.get(key) not in (None, "", "--"):
            return run.get(key)
    return None


def _validation_actual_value(run: Dict[str, Any]):
    if not isinstance(run, dict):
        return None
    for key in ("actualTapCount", "actualRotationCount"):
        if run.get(key) not in (None, "", "--"):
            return run.get(key)
    return None


def _validation_duration_sec(run: Dict[str, Any]):
    if not isinstance(run, dict):
        return None
    for key in ("validationDurationSec", "durationSeconds", "durationSec"):
        if run.get(key) is not None:
            return run.get(key)
    return None


def _validation_time_minutes(run: Dict[str, Any]):
    if not isinstance(run, dict):
        return None
    if run.get("timeMinutes") not in (None, "", "--"):
        return run.get("timeMinutes")
    dur = _validation_duration_sec(run)
    if dur is None:
        return None
    try:
        return round(float(dur) / 60.0, 3)
    except (TypeError, ValueError):
        return None


def _validation_run_detail_pairs(run: Dict[str, Any]) -> list:
    pairs = [
        ("Start Time", _format_ts_readable(run.get("validationStartTime") or run.get("testStartTime"))),
        ("End Time", _format_ts_readable(run.get("validationEndTime") or run.get("testEndTime") or run.get("completedAt"))),
    ]
    if _is_friability_validation_run(run):
        pairs.extend([
            ("RPM", _cell_str(run.get("rpm") or run.get("tapsMin"))),
            ("Duration (min)", _cell_str(_validation_time_minutes(run))),
            ("Expected rotations", _validation_expected_display(run)),
            ("Actual rotations", _cell_str(_validation_actual_value(run))),
        ])
    else:
        pairs.extend([
            ("Taps/Min", _cell_str(run.get("tapsMin"))),
            ("Drop (mm)", _cell_str(run.get("dropHeight"))),
            ("Expected", _validation_expected_display(run)),
            ("Actual", _cell_str(_validation_actual_value(run))),
        ])
    dur = _validation_duration_sec(run)
    if dur is not None:
        try:
            pairs.append(("Elapsed", f"{int(dur)} s"))
        except (TypeError, ValueError):
            pass
    pairs.append(("Status", _cell_str(run.get("status"))))
    return pairs


def _validation_usp_label(run: Dict[str, Any]) -> str:
    usp = run.get("usp")
    if usp:
        return str(usp)
    return "USP 2" if run.get("validationSubtype") == "load" else "USP 1"


def _validation_expected_display(run: Dict[str, Any]) -> str:
    expected = _validation_expected_value(run)
    if expected is None:
        expected = "--"
    tol = run.get("expectedTolerance")
    if tol is not None and expected not in (None, "--", ""):
        try:
            return f"{expected} (+/-{tol})"
        except (TypeError, ValueError):
            pass
    return _cell_str(expected)


def _validation_overall_status_label(td: Dict[str, Any], report_data: Dict[str, Any]) -> str:
    overall = td.get("status") or report_data.get("status") or "--"
    s = str(overall).strip()
    low = s.lower()
    if low == "pass":
        return "Pass"
    if low == "fail":
        return "Fail"
    if low == "aborted":
        return "Aborted"
    return s or "--"


def _format_thermal_validation_runs_block(runs: list, width: int = THERMAL_WIDTH) -> list:
    w = width
    lines = ["", "VALIDATION RESULTS", _thermal_sep("-", w)]
    for idx, run in enumerate(runs):
        if idx > 0:
            lines.append("")
        lines.append(_validation_usp_label(run))
        if _is_friability_validation_run(run):
            lines.append(f"RPM: {_cell_str(run.get('rpm') or run.get('tapsMin'))}")
            lines.append(f"Duration (min): {_cell_str(_validation_time_minutes(run))}")
            lines.append(f"Expected rotations: {_validation_expected_display(run)}")
            lines.append(f"Actual rotations: {_cell_str(_validation_actual_value(run))}")
        else:
            lines.append(f"Taps/Min: {_cell_str(run.get('tapsMin'))}")
            lines.append(f"Drop(mm): {_cell_str(run.get('dropHeight'))}")
            lines.append(f"Expected: {_validation_expected_display(run)}")
            lines.append(f"Actual: {_cell_str(_validation_actual_value(run))}")
        dur = _validation_duration_sec(run)
        if dur is not None:
            try:
                lines.append(f"Duration: {int(dur)} s")
            except (TypeError, ValueError):
                pass
        start = run.get("validationStartTime") or run.get("testStartTime")
        if start:
            lines.append(f"Start Time: {_format_ts_readable(start)}")
        lines.append(f"Status: {_cell_str(run.get('status'))}")
    lines.extend(["", _thermal_sep("-", w), ""])
    return lines


def _append_validation_report_details(
    lines: list, td: Dict[str, Any], report_data: Dict[str, Any], width: int, thermal: bool
) -> None:
    if not isinstance(td, dict):
        td = {}
    runs = _normalize_validation_runs(td, report_data)
    overall_label = _validation_overall_status_label(td, report_data)
    ts_end = (
        report_data.get("validationEndTime")
        or td.get("validationEndTime")
        or report_data.get("testEndTime")
        or td.get("testEndTime")
        or (runs[-1].get("validationEndTime") if runs else None)
        or (runs[-1].get("testEndTime") if runs else None)
        or report_data.get("completedAt")
        or td.get("completedAt")
        or (runs[-1].get("completedAt") if runs else None)
        or report_data.get("createdAt")
        or td.get("createdAt")
    )
    ts_start = (
        report_data.get("validationStartTime")
        or td.get("validationStartTime")
        or report_data.get("testStartTime")
        or td.get("testStartTime")
        or (runs[0].get("validationStartTime") if runs else None)
        or (runs[0].get("testStartTime") if runs else None)
        or report_data.get("createdAt")
        or td.get("createdAt")
    )
    remarks = report_data.get("approvalRemarks")
    if remarks in (None, ""):
        remarks = report_data.get("remarks")
    if remarks is None:
        remarks = td.get("remarks")
    dash = "" if thermal else ("-" * width)

    if thermal:
        start_date, start_time = _split_ts_date_and_time(ts_start)
        end_date, end_time = _split_ts_date_and_time(ts_end)
        lines.extend(
            [
                "",
                "VALIDATION INFORMATION",
                f"Overall Status: {overall_label}",
                f"Start Date: {start_date}",
                f"Start Time: {start_time}",
                f"Completed Date: {end_date}",
                f"Completed Time: {end_time}",
                "",
            ]
        )
        if runs:
            lines.extend(_format_thermal_validation_runs_block(runs, width))
        else:
            lines.extend(["", "VALIDATION RESULTS", "No validation data", ""])
    else:
        lines.extend(["", "VALIDATION INFORMATION", dash if dash else ""])
        _append_two_column_pairs(
            lines,
            [
                ("Overall Status", overall_label),
                ("Start Time", _format_ts_readable(ts_start)),
                ("Completed", _format_ts_readable(ts_end)),
            ],
            width,
        )
        lines.extend(["", "VALIDATION RESULTS", dash if dash else ""])
        if not runs:
            lines.append("No validation data")
        for idx, run in enumerate(runs):
            if idx > 0:
                lines.append("")
            lines.append(_validation_usp_label(run))
            _append_two_column_pairs(lines, _validation_run_detail_pairs(run), width)
        lines.append("")

    if remarks not in (None, ""):
        if thermal:
            lines.extend(["", "REMARKS:", str(remarks), ""])
        else:
            lines.extend(["", "REMARKS", dash if dash else ""])
            _append_two_column_pairs(lines, [("Remarks", _truncate_with_ellipsis(remarks, max(16, width - 20)))], width)
            lines.append("")


def _format_thermal_run_detail_lines(td: Dict[str, Any], run_details: Any, width: int = THERMAL_WIDTH) -> list:
    mode = _cell_str(td.get("mode")) if isinstance(td, dict) else "--"
    target = _cell_str(td.get("target")) if isinstance(td, dict) else "--"
    details = str(run_details or "").strip()
    prefix = details
    if details:
        marker = "Mode:"
        idx = details.find(marker)
        if idx >= 0:
            prefix = details[:idx].strip(" ,.")
            rest = details[idx:]
            target_idx = rest.find("Target:")
            if target_idx >= 0:
                mode = rest[len("Mode:"):target_idx].strip(" ,")
                target = rest[target_idx + len("Target:"):].strip(" ,")
            else:
                mode = rest[len("Mode:"):].strip(" ,")
    lines = ["Run Details:"]
    if prefix:
        lines.extend(_fit_thermal_line(prefix + ".", width))
    if mode and mode != "--":
        lines.append(f"Mode: {mode}")
    if target and target != "--":
        lines.append(f"Target: {target}")
    return lines


def _append_test_report_details(lines: list, td: Dict[str, Any], report_data: Dict[str, Any], width: int, thermal: bool) -> None:
    """Append run details, friability drum rows, then remarks (matches A4 / on-screen preview)."""
    dash = "" if thermal else ("-" * width)
    # Comments: only approvalRemarks (and power-interruption system text). Never Mode/Target remarks.
    remarks = report_data.get("approvalRemarks")
    if remarks in (None, ""):
        cause = str(
            report_data.get("abortCause")
            or (td.get("abortCause") if isinstance(td, dict) else "")
            or ""
        ).strip().lower()
        approved_by = str(report_data.get("approvedBy") or "").strip().lower()
        fallback = report_data.get("remarks")
        if fallback in (None, "") and isinstance(td, dict):
            fallback = td.get("remarks")
        fb = str(fallback or "").strip().lower()
        is_power = (
            cause in ("power_interruption", "power_loss", "power")
            or "power interruption" in approved_by
            or "power interruption" in fb
        )
        if is_power and fallback not in (None, ""):
            remarks = fallback
        else:
            remarks = None

    if not isinstance(td, dict):
        td = {}
    results = td.get("stepResults") or []
    row_count = _effective_friability_step_count(td)

    run_details = td.get("runDetails") or td.get("runSummary")
    if not run_details and (td.get("mode") or td.get("target")):
        run_details = "Mode: {}, Target: {}".format(td.get("mode") or "--", td.get("target") or "--")
    if run_details:
        if thermal:
            lines.extend(_format_thermal_run_detail_lines(td, run_details, width))
        else:
            _append_two_column_pairs(lines, [("Run Details", _truncate_with_ellipsis(run_details, max(16, width - 20)))], width)

    recipe = report_data.get("recipe") or td.get("recipe") or {}
    if not isinstance(recipe, dict):
        recipe = {}

    if row_count > 0:
        if thermal:
            lines.extend(_format_thermal_friability_test_data_table(td, width))
        else:
            eq = _section_sep("=", width, False)
            lines.extend(["", eq, "TEST DATA", dash if dash else ""])
            hdr = f"{'S':>2}  {'W1 gms':>8}  {'W2 gms':>8}  {'Diff gms':>8}  {'Fri%':>8}  {'Trend':>10}  {'Result':>8}"
            lines.append(hdr)
            if dash:
                lines.append(dash)
            for i in range(row_count):
                row = _friability_step_row_values(td, results, i)
                sn = i + 1
                lines.append(
                    f"{sn:2d}  {row['w1']:>8}  {row['w2']:>8}  {row['diff']:>8}  "
                    f"{row['friability']:>8}  {row['trend']:>10}  {row['result']:>8}"
                )
            lines.append(dash if dash else "")
    elif str(report_data.get("type") or "test").strip().lower() == "test":
        lines.extend(["", "TEST DATA: No test data recorded"])

    if remarks not in (None, ""):
        if thermal:
            lines.extend(["", "REMARKS:", str(remarks), ""])
        else:
            lines.extend(["", "REMARKS", dash if dash else ""])
            _append_two_column_pairs(lines, [("Comments", _truncate_with_ellipsis(remarks, max(16, width - 20)))], width)
            lines.append("")


def _is_sieve_shaker_report(report_data: Dict[str, Any]) -> bool:
    """Return True if this report belongs to the Sieve Shaker."""
    recipe = (report_data or {}).get("recipe") or {}
    td = (report_data or {}).get("testData") or {}
    return bool(
        recipe.get("numSieves") or td.get("numSieves") or
        td.get("sieveSizes") or td.get("sieveWeights") or
        recipe.get("shakerMode") or td.get("shakerMode") or
        recipe.get("validationType") or td.get("validationType")
    )


def _fmt_amplitude_display(raw: Any) -> str:
    """Convert stored amplitude tenths (5–30) to display mm (0.5–3.0).

    Values already in display units (< 5) are shown as-is with one decimal when numeric.
    """
    if raw is None or raw == "":
        return "n/a"
    try:
        v = float(raw)
        if v >= 5:
            return f"{v / 10.0:.1f}"
        return f"{v:.1f}"
    except (TypeError, ValueError):
        return str(raw)


def _ascii_bar(fraction: float, bar_width: int = 12) -> str:
    """Return an ASCII bar of given width filled proportionally (ASCII-only for thermal/A4)."""
    filled = min(bar_width, max(0, int(round(fraction * bar_width))))
    return "#" * filled + "-" * (bar_width - filled)


def _sieve_chart_series(analysis: Dict[str, Any]) -> list:
    """Return list of (x_label, percent) for sieves + pan. One ## block = 5%."""
    series = []
    for row in list(analysis.get("rows") or []):
        pct = float(row.get("percent") or 0.0)
        if row.get("isPan"):
            label = "PAN"
        else:
            size = row.get("size")
            label = str(size) if size not in (None, "") else str(row.get("label") or row.get("index") or "?")
        series.append((label, pct))
    return series


def _pct_to_blocks(percent: float, step: float = 5.0) -> int:
    """Number of ## cells for a retained %."""
    if percent <= 0:
        return 0
    return max(0, int(round(float(percent) / step)))


def _format_sieve_vertical_ascii_chart(analysis: Dict[str, Any], width: int = 80) -> list:
    """Wide vertical ## bar chart for A4 (Y = % retained, X = sieve sizes).

    One ## cell = 5% retained. Columns spread across the full plot width.
    """
    series = _sieve_chart_series(analysis)
    if not series:
        return []
    n = len(series)
    step = 5
    max_pct = max((p for _, p in series), default=0.0)
    ymax = max(30, int(((max_pct + step - 1e-9) // step) * step))
    if ymax < step:
        ymax = step
    blocks = [_pct_to_blocks(p, step) for _, p in series]

    # Layout: "YY |" (4 chars) + plot area using remaining width
    axis_w = 4  # "30 |"
    plot_w = max(20, width - axis_w)
    # Column pitch fills plot; each bar glyph is "##" (2) centered in col
    col_w = max(4, plot_w // n)
    # Recenter so total columns use full plot_w
    used = col_w * n
    pad_left = max(0, (plot_w - used) // 2)

    def cell(i: int, filled: bool) -> str:
        glyph = "##" if filled else "  "
        return glyph.center(col_w)[:col_w]

    lines = [
        "PARTICLE SIZE DISTRIBUTION % RETAINED".center(width),
        "",
    ]
    for y in range(ymax, 0, -step):
        row_chars = [" "] * pad_left
        for i, b in enumerate(blocks):
            row_chars.append(cell(i, b * step >= y))
        plot = "".join(row_chars)
        if len(plot) < plot_w:
            plot = plot + (" " * (plot_w - len(plot)))
        else:
            plot = plot[:plot_w]
        lines.append(f"{y:>2} |{plot}")

    baseline = ("-" * plot_w)
    lines.append(f" 0 +{baseline}")

    # X labels centered under each column
    xlab = [" "] * pad_left
    for i, (lab, _) in enumerate(series):
        lab_s = str(lab)[:col_w]
        xlab.append(lab_s.center(col_w)[:col_w])
    xlab_line = "".join(xlab)
    if len(xlab_line) < plot_w:
        xlab_line = xlab_line + (" " * (plot_w - len(xlab_line)))
    else:
        xlab_line = xlab_line[:plot_w]
    lines.append(f"   {xlab_line}")
    return lines


def _format_sieve_horizontal_ascii_chart(analysis: Dict[str, Any], width: int = 32) -> list:
    """Thermal horizontal ## ## chart (one row per sieve). One ## = 5%."""
    series = _sieve_chart_series(analysis)
    if not series:
        return []
    step = 5
    sep = "-" * min(width, 32)
    lines = [
        "Sieve  Retained (% of sample)"[:width],
        sep,
    ]
    for lab, pct in series:
        blocks = _pct_to_blocks(pct, step)
        # Prefer spaced "## ##"; pack if needed for 32-col thermal
        label = str(lab)[:6]
        pct_str = f"{int(round(pct))}%" if abs(pct - round(pct)) < 0.05 else f"{pct:.1f}%"
        # Match sample style: integer-ish display as 5%, 10%, ...
        display_pct = f"{blocks * step}%"
        spaced = " ".join(["##"] * blocks) if blocks else ""
        packed = "##" * blocks if blocks else ""
        # "150    " + bar + spaces + pct
        prefix = f"{label:<6}"
        suffix = f" {display_pct}"
        avail = width - len(prefix) - len(suffix)
        if avail < 0:
            avail = 0
        if len(spaced) <= avail:
            bar = spaced.ljust(avail)
        else:
            bar = packed[:avail].ljust(avail)
        line = (prefix + bar + suffix.lstrip()).rstrip()
        if len(line) > width:
            line = line[:width]
        lines.append(line)
    lines.append(sep)
    return lines


def _format_sieve_ascii_chart(analysis: Dict[str, Any], width: int = 56, bar_width: int = 20) -> list:
    """Legacy horizontal [###---] chart — prefer vertical/horizontal ## charts."""
    if width < 48:
        return _format_sieve_horizontal_ascii_chart(analysis, width=width)
    return _format_sieve_vertical_ascii_chart(analysis, width=width)


_THERMAL_GRAPH_MARKER = "\x00__SIEVE_GRAPH__\x00"


def _build_bar_chart_escpos(fracs: list, labels: list, sample_weight: float, width_dots: int = 384) -> bytes:
    """Render an outline-only bar chart to ESC/POS GS v 0 raster bytes.

    Bars are white interior with a black outline so they are clearly readable
    on thermal paper.  Percentage labels are always printed above each bar.
    Bar height is scaled to sample_weight (100% of powder).
    """
    try:
        from PIL import Image as _PILImage, ImageDraw as _PILDraw, ImageFont as _PILFont
        import struct as _struct
    except ImportError:
        return b""
    num_bars = len(fracs)
    if num_bars == 0:
        return b""
    img_w = width_dots
    img_h = 140
    margin_l, margin_r, margin_t, margin_b = 30, 8, 22, 28
    chart_w = img_w - margin_l - margin_r
    chart_h = img_h - margin_t - margin_b
    bar_gap = max(3, chart_w // (num_bars * 7))
    bar_w = max(6, (chart_w - bar_gap * (num_bars + 1)) // num_bars)
    img = _PILImage.new("L", (img_w, img_h), 255)  # white background
    draw = _PILDraw.Draw(img)
    # Full scale = sample weight so bars reflect % of powder (sum toward 100%).
    scale = float(sample_weight) if sample_weight and sample_weight > 0 else 0.0
    if scale <= 0:
        scale = max((v for v in fracs if v > 0), default=1.0) or 1.0
    # Try to load a slightly larger font for labels; fall back to default
    try:
        font_lbl = _PILFont.load_default(size=11)
        font_pct = _PILFont.load_default(size=11)
    except TypeError:
        font_lbl = _PILFont.load_default()
        font_pct = _PILFont.load_default()
    for i, (val, lbl) in enumerate(zip(fracs, labels)):
        bar_h = int(min(1.0, max(0.0, float(val) / scale)) * chart_h)
        x0 = margin_l + bar_gap + i * (bar_w + bar_gap)
        x1 = x0 + bar_w
        y0 = margin_t + chart_h - bar_h
        y1 = margin_t + chart_h
        # Outline-only rectangle: white fill, black border
        draw.rectangle([x0, y0, x1, y1], fill=255, outline=0)
        pct = (float(val) / float(sample_weight) * 100) if sample_weight > 0 else 0.0
        pct_str = f"{pct:.1f}%"
        # Always draw percentage above the bar (even for very short bars)
        pct_y = max(margin_t + 8, y0 - 9)
        draw.text((x0 + bar_w // 2, pct_y), pct_str, fill=0, anchor="mm", font=font_pct)
        # Sieve label below x-axis
        draw.text((x0 + bar_w // 2, img_h - margin_b + 10), lbl, fill=0, anchor="mm", font=font_lbl)
    # Axes: Y-axis vertical line + X-axis baseline
    draw.line([(margin_l, margin_t), (margin_l, margin_t + chart_h)], fill=0, width=1)
    draw.line([(margin_l, margin_t + chart_h), (img_w - margin_r, margin_t + chart_h)], fill=0, width=1)
    # ESC/POS GS v 0: bit 1 = black dot (same polarity as thermal logo).
    bw = img.point(lambda p: 0 if p > 127 else 1, "1")
    bw_w, bw_h = bw.size
    bytes_per_row = (bw_w + 7) // 8
    cmd = bytearray(b"\x1d\x76\x30\x00")
    cmd += _struct.pack("<HH", bytes_per_row, bw_h)
    cmd += bw.tobytes()
    return bytes(cmd)


def _format_sieve_shaker_thermal(report_data: Dict[str, Any], width: int = 32) -> str:
    """Thermal text matching sample layout (32-col); no sieve chart on thermal."""
    try:
        from report_service import build_sieve_shaker_shared_lines
    except ImportError:
        build_sieve_shaker_shared_lines = None

    if build_sieve_shaker_shared_lines is not None:
        lines = build_sieve_shaker_shared_lines(
            report_data,
            width=width,
            include_graph_marker=False,
            graph_marker="",
            include_chart=False,
        )
    else:
        lines = ["SIEVE SHAKER", "Report unavailable"]

    flat: list = []
    for line in lines:
        if line == _THERMAL_GRAPH_MARKER:
            continue
        flat.extend(_fit_thermal_line(str(line), width))
    return "\n".join(_compact_thermal_lines(flat, width))


def _build_friability_test_info(
    recipe: Dict[str, Any], td: Dict[str, Any], report_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Build friability-specific test info fields (does NOT use sieve shaker derived)."""
    recipe = recipe if isinstance(recipe, dict) else {}
    td = td if isinstance(td, dict) else {}
    report_data = report_data if isinstance(report_data, dict) else {}

    # Test type: Friability
    test_type = "Friability"

    # Test method: from recipe uspMode / customCompletionMode
    mode_raw = str(recipe.get("uspMode") or td.get("uspMode") or "").strip().upper()
    completion = str(recipe.get("customCompletionMode") or td.get("customCompletionMode") or "COUNT").strip().upper()
    if mode_raw == "USP":
        test_method = "USP"
    elif mode_raw == "CUSTOM":
        test_method = completion  # "COUNT" or "TIME"
    else:
        test_method = completion or "--"

    # RPM / speed
    rpm = _recipe_rpm(recipe) or td.get("rpm") or td.get("speed")

    # Rotations / taps
    rotations = None
    for key in ("rotationCount", "completedRotations", "actualRotationCount", "actualTapCount"):
        v = td.get(key)
        if v not in (None, ""):
            rotations = v
            break
    if rotations is None:
        rotations = _recipe_rotations(recipe)

    # Drum count
    drum_count = td.get("drumCount") or recipe.get("drumCount")

    # Duration
    dur_sec = test_duration_seconds(td)
    if dur_sec is None:
        try:
            dur_sec = int(recipe.get("durationSeconds") or recipe.get("timeSeconds") or 0) or None
        except (TypeError, ValueError):
            dur_sec = None
    duration_formatted = format_duration_hhmmss(dur_sec) if dur_sec else "--"

    # Test number
    report_id = report_data.get("id")
    test_no = "--"
    if report_id is not None:
        try:
            test_no = f"{int(report_id):04d}"
        except (TypeError, ValueError):
            test_no = str(report_id)

    return {
        "testType": test_type,
        "testMethod": test_method,
        "rpm": _cell_str(rpm),
        "rotationCount": _cell_str(rotations),
        "drumCount": _cell_str(drum_count),
        "durationFormatted": duration_formatted,
        "testNumber": test_no,
    }


def _append_friability_statistics(
    lines: list, td: Dict[str, Any], report_data: Dict[str, Any], width: int, thermal: bool
) -> None:
    """Append the STATISTICS block for friability reports (matches on-screen preview)."""
    stats = None
    if isinstance(td, dict):
        stats = td.get("statistics")
    if not stats and isinstance(report_data, dict):
        stats = report_data.get("statistics")
    if not isinstance(stats, dict) or not stats:
        return
    sep = _thermal_sep("=", width) if thermal else ("=" * width)
    dash = _thermal_sep("-", width) if thermal else ("-" * width)
    lines.extend(["", sep, "STATISTICS", dash])
    for key, val in stats.items():
        if not isinstance(val, dict):
            continue
        display = _stat_display_value(val)
        if display is None:
            continue
        if thermal:
            lines.append(f"{key}: {display}")
        else:
            lines.append(f"{key}: {display}")
    lines.append("")


def _format_report_text(report_data: Dict[str, Any], width: int = A4_TEXT_WIDTH) -> str:
    # Sieve Shaker: bypass the friability formatter entirely
    if _is_sieve_shaker_report(report_data):
        thermal = width < 70
        if thermal:
            return _format_sieve_shaker_thermal(report_data, width=width)
        try:
            import report_service as _rs
            return _rs._format_sieve_shaker_a4_text(report_data, width=width)
        except Exception:
            pass

    thermal = width < 70
    sep = _thermal_sep("=", width) if thermal else ("=" * width)
    sep_dash = _thermal_sep("-", width) if thermal else ("-" * width)
    td = report_data.get("testData") or report_data
    approval_result = _effective_approval_result(report_data if isinstance(report_data, dict) else {}, td if isinstance(td, dict) else {})
    if isinstance(td, dict) and approval_result:
        td = dict(td)
        td["approvalPassFail"] = approval_result
    if isinstance(report_data, dict) and approval_result and not report_data.get("approvalPassFail"):
        report_data = dict(report_data)
        report_data["approvalPassFail"] = approval_result
    fs = report_data.get("factorySettings") or {}
    last_validation_date = _format_display_date(fs.get("lastValidationDate", "N/A"))
    next_validation_date = _format_display_date(fs.get("nextValidationDate", "N/A"))
    rtype = str(report_data.get("type") or "test").strip().lower()
    title = "FRIABILITY VALIDATION REPORT" if rtype == "validation" else "FRIABILITY TEST REPORT"
    lines: list = []
    if thermal:
        lines.extend([sep, "RAISE LAB EQUIPMENT", ""])
    else:
        lines.extend([sep, "RAISE LAB EQUIPMENT".center(width), ""])
    lines.append(title if thermal else title.center(width))
    if thermal:
        lines.append("")
    else:
        lines.append(sep)
    if thermal:
        lines.extend(
            [
                f"Company: {fs.get('companyName', 'N/A')}",
                f"Model No: {fs.get('modelNo', 'N/A')}",
                f"Serial No: {fs.get('serialNo', 'N/A')}",
                f"Location: {fs.get('companyLocation', fs.get('location', 'N/A'))}",
                f"Instrument ID: {fs.get('instrumentId', 'N/A')}",
                f"Last Val: {last_validation_date}",
                f"Next Val Due: {next_validation_date}",
            ]
        )
    else:
        _append_two_column_pairs(
            lines,
            [
                ("Company", fs.get("companyName", "N/A")),
                ("Model No", fs.get("modelNo", "N/A")),
                ("Serial No", fs.get("serialNo", "N/A")),
                ("Location", fs.get("companyLocation", fs.get("location", "N/A"))),
                ("Instrument ID", fs.get("instrumentId", "N/A")),
                ("Last Val", last_validation_date),
                ("Next Val Due", next_validation_date),
            ],
            width,
        )
    if not thermal:
        lines.append("")
    if rtype == "validation":
        _append_validation_report_details(lines, td if isinstance(td, dict) else {}, report_data, width, thermal)
    else:
        recipe = report_data.get("recipe") or (td.get("recipe") if isinstance(td, dict) else None) or {}
        if not isinstance(recipe, dict):
            recipe = {}
        status_raw = str(td.get("status", "")).lower() if isinstance(td, dict) else ""
        if status_raw == "aborted":
            status_label = "Aborted"
        elif _is_power_interruption_report(report_data if isinstance(report_data, dict) else {}, td if isinstance(td, dict) else {}):
            status_label = "Completed"
        else:
            status_label = "Completed" if status_raw == "completed" else (status_raw.title() if status_raw else "--")
        info = _build_friability_test_info(recipe, td if isinstance(td, dict) else {}, report_data)
        ts_start = (td.get("testStartTime") if isinstance(td, dict) else None) or report_data.get("createdAt")
        ts_end = (
            (td.get("testEndTime") if isinstance(td, dict) else None)
            or report_data.get("completedAt")
            or (td.get("completedAt") if isinstance(td, dict) else None)
            or report_data.get("createdAt")
        )
        start_date, start_time = _split_ts_date_and_time(ts_start)
        end_date, end_time = _split_ts_date_and_time(ts_end)
        batch_no = recipe.get("batchNumber") or (td.get("batchNumber") if isinstance(td, dict) else None) or "N/A"
        if batch_no in (None, "", "N/A"):
            b1 = (td.get("batchNumber1") if isinstance(td, dict) else None) or recipe.get("batchNumber1")
            b2 = (td.get("batchNumber2") if isinstance(td, dict) else None) or recipe.get("batchNumber2")
            if b1 or b2:
                batch_no = f"D1: {b1 or '--'}" + (f" | D2: {b2}" if b2 else "")
        operator = report_data.get("operatorName") or (td.get("operatorName") if isinstance(td, dict) else None) or "--"
        if thermal:
            info_lines = [
                sep,
                "TEST INFORMATION",
                f"Test No: {info['testNumber']}",
                f"Product: {recipe.get('productName') or (td.get('productName') if isinstance(td, dict) else None) or 'N/A'}",
                f"Batch: {batch_no}",
                f"Operator: {operator}",
                f"Test Type: {info['testType']}",
                f"Test Method: {info['testMethod']}",
                f"Drops/Min: {info['rpm']}",
                f"Total Taps: {info['rotationCount']}",
                f"Drums: {info['drumCount']}",
                f"Test Start Date: {start_date}",
                f"Test Start Time: {start_time}",
                f"Completed Date: {end_date}",
                f"Completed Time: {end_time}",
                f"Test Status: {status_label}",
                "",
                f"Test Duration: {info['durationFormatted']}",
            ]
            lines.extend(info_lines)
        else:
            lines.extend(["", "TEST INFORMATION", sep_dash])
            info_pairs = [
                ("Test No", info["testNumber"]),
                ("Product", recipe.get("productName") or (td.get("productName") if isinstance(td, dict) else None) or "N/A"),
                ("Batch", batch_no),
                ("Operator", operator),
                ("Test Type", info["testType"]),
                ("Test Method", info["testMethod"]),
                ("Drops/Min", info["rpm"]),
                ("Drop Height", "--"),
                ("Total Taps", info["rotationCount"]),
                ("Test Start", start_date + " " + start_time if start_date != "--" else "--"),
                ("Completed", end_date + " " + end_time if end_date != "--" else "--"),
                ("Test Status", status_label),
                ("Test Duration", info["durationFormatted"]),
            ]
            _append_two_column_pairs(lines, info_pairs, width)
        _append_test_report_details(lines, td if isinstance(td, dict) else {}, report_data, width, thermal)
        _append_friability_statistics(lines, td if isinstance(td, dict) else {}, report_data, width, thermal)
    # Approval remarks (thermal only — A4 path already handles via _append_test_report_details)
    if thermal:
        approval_remarks = report_data.get("approvalRemarks") if isinstance(report_data, dict) else None
        if approval_remarks not in (None, "") and rtype != "validation":
            # Already shown in REMARKS block by _append_test_report_details when present;
            # show again explicitly in the approval section on thermal for visibility.
            pass  # handled above in _append_test_report_details
    if thermal:
        lines.extend(["", "APPROVAL"])
    approval_pairs = _approval_result_pairs(
        report_data if isinstance(report_data, dict) else {},
        td if isinstance(td, dict) else {},
        rtype,
    )
    if thermal:
        lines.extend(
            [
                f"Operated by: {report_data.get('operatorName') or (td.get('operatorName') if isinstance(td, dict) else '--') or '--'}",
                f"Employee ID: {td.get('employeeId', '--') if isinstance(td, dict) else '--'}",
            ]
        )
        for label, value in approval_pairs:
            lines.append(f"{label}: {value}")
        approver_name = _strip_approver_role_label(report_data.get("approvedBy"))
        approver_id = report_data.get("approvedByUsername") or "--"
        lines.extend(
            [
                f"Approved By: {approver_name}",
                f"Approver ID: {approver_id}",
                f"Approved At: {_format_ts_readable(report_data.get('approvedAt'))}",
            ]
        )
    else:
        lines.extend(["", "APPROVAL", sep_dash])
        _append_two_column_pairs(
            lines,
            [
                ("Operated by", report_data.get("operatorName") or (td.get("operatorName") if isinstance(td, dict) else "--") or "--"),
                ("Employee ID", td.get("employeeId", "--") if isinstance(td, dict) else "--"),
            ] + approval_pairs + [
                ("Approved By", _strip_approver_role_label(report_data.get("approvedBy"))),
                ("Approver ID", report_data.get("approvedByUsername", "--")),
                ("Approved At", _format_ts_readable(report_data.get("approvedAt"))),
            ],
            width,
        )
    if thermal:
        lines.extend([sep, ""])
        flat: list = []
        for line in lines:
            flat.extend(_fit_thermal_line(line, width))
        lines = _compact_thermal_lines(flat, width)
        return "\n".join(lines)
    return "\n".join(_wrap_lines(lines, width))


def format_for_a4_printer(
    report_data: Dict[str, Any],
    *,
    include_printed_timestamp: bool = True,
    timestamp_kind: str = "printed",
) -> str:
    text = _format_report_text(report_data, width=A4_TEXT_WIDTH).rstrip("\n")
    if not include_printed_timestamp:
        return text
    footer = "\n".join(_report_timestamp_footer_lines(timestamp_kind))
    return text + "\n\n" + footer


def _report_timestamp_footer_lines(kind: str = "printed") -> list:
    """Date/time footer from device RTC. kind: 'printed' | 'exported'. Dates use DD/MM/YYYY."""
    try:
        import rtc_service

        payload = rtc_service.get_device_wall_datetime_payload()
        pdate = str(payload.get("date") or "--").replace("-", "/")
        ptime = payload.get("time") or "--"
    except Exception:
        now = datetime.now()
        pdate = now.strftime("%d/%m/%Y")
        ptime = now.strftime("%H:%M:%S")
    label = "Exported" if str(kind or "").strip().lower() == "exported" else "Printed"
    return ["", f"{label} Date: {pdate}", f"{label} Time: {ptime}"]


def _thermal_printed_timestamp_lines() -> list:
    """Printed date/time from device RTC at format time."""
    return _report_timestamp_footer_lines("printed")


def _thermal_trailing_feed() -> str:
    return "\n" * THERMAL_POST_PRINT_FEED_LINES


def format_for_thermal_printer(
    report_data: Dict[str, Any], *, timestamp_kind: str = "printed"
) -> str:
    text = _format_report_text(report_data, width=THERMAL_WIDTH).rstrip("\n")
    footer = "\n".join(_report_timestamp_footer_lines(timestamp_kind))
    return text + "\n\n" + footer + _thermal_trailing_feed()


def format_for_export(report_data: Dict[str, Any], *, thermal: bool = False) -> str:
    """A4/thermal text for USB/file export — no Printed/Exported footer (stamp only on live print)."""
    if thermal:
        text = _format_report_text(report_data, width=THERMAL_WIDTH).rstrip("\n")
        return text + _thermal_trailing_feed()
    return format_for_a4_printer(report_data, include_printed_timestamp=False)


def save_report_text_files(report_data: Dict[str, Any], report_id: int, reports_dir: pathlib.Path) -> None:
    if not report_data or report_id is None:
        return
    try:
        reports_dir = pathlib.Path(reports_dir)
        reports_dir.mkdir(parents=True, exist_ok=True)
        # Stored text matches preview: no Printed/Exported stamp (stamped at live print/export).
        text_48 = _format_report_text(report_data, width=THERMAL_WIDTH).rstrip("\n") + _thermal_trailing_feed()
        text_80 = format_for_a4_printer(report_data, include_printed_timestamp=False).rstrip() + "\r\n\x0c"
        (reports_dir / f"report_{report_id}_a4.txt").write_text(text_80, encoding="utf-8")
        (reports_dir / f"report_{report_id}_thermal.txt").write_text(text_48, encoding="utf-8")
    except Exception as e:
        _log.warning("save_report_text_files failed: %s", e)


def print_report_from_file(txt_path: pathlib.Path, port: str, baud: int, printer_type: str = "a4") -> Dict[str, Any]:
    txt_path = pathlib.Path(txt_path)
    if not txt_path.exists() or not txt_path.is_file():
        return {"success": False, "error": f"Report file not found: {txt_path}", "port": port}
    if not serial:
        return {"success": False, "error": "pyserial not installed", "port": port}
    if printer_type == "thermal":
        try:
            port = _probe_port(port, THERMAL_CANDIDATES)
        except FileNotFoundError as e:
            return {"success": False, "error": f"Printer port not found: {e.filename or port}", "port": port}
    elif not _port_exists(port):
        return {"success": False, "error": f"Printer port not found: {port}", "port": port}
    try:
        data = txt_path.read_bytes()
        if printer_type == "a4":
            ser = _open_a4_serial(port, baud)
            try:
                ser.reset_output_buffer()
                ser.flush()
                _send_printer_init(ser)
                _send_bytes_chunked(ser, data, baud, chunk_size=512)
                time.sleep(0.5)
                return {"success": True, "port": port}
            finally:
                ser.close()
        ser = serial.Serial(port=port, baudrate=baud, timeout=2.0)
        try:
            _send_printer_init(ser)
            time.sleep(0.2)
            _send_text_to_thermal(ser, data.decode("utf-8", errors="replace"), baud)
            time.sleep(0.5)
            return {"success": True, "port": port}
        finally:
            ser.close()
    except Exception as e:
        return {"success": False, "error": str(e), "port": port}


def print_a4_report(report_data: Dict[str, Any], printer_port: Optional[str] = None) -> Dict[str, Any]:
    global _PRINT_BUSY
    port = printer_port or _a4_port
    baud = _a4_baud
    if not serial:
        return {"success": False, "error": "pyserial not installed", "port": port}
    if not _port_exists(port):
        return {"success": False, "error": f"A4 printer port not found: {port}", "port": port}
    if not _PRINT_IO_LOCK.acquire(blocking=False):
        return {"success": False, "error": "Printer busy — wait for the current print to finish.", "port": port}
    _PRINT_BUSY = True
    try:
        text = format_for_a4_printer(report_data).rstrip() + "\r\n\x0c"
        ser = _open_a4_serial(port, baud)
        try:
            ser.reset_output_buffer()
            ser.flush()
            _send_printer_init(ser)
            _send_text_to_a4(ser, text, baud)
            time.sleep(0.5)
            return {"success": True, "port": port}
        finally:
            ser.close()
    except Exception as e:
        return {"success": False, "error": str(e), "port": port}
    finally:
        _PRINT_BUSY = False
        _PRINT_IO_LOCK.release()


def _sieve_analysis_enabled(report_data: Dict[str, Any]) -> bool:
    """True unless recipe/testData explicitly disables sieve analysis."""
    r = dict(report_data or {})
    td = r.get("testData") if isinstance(r.get("testData"), dict) else {}
    recipe = r.get("recipe") if isinstance(r.get("recipe"), dict) else {}
    for src in (td, recipe, r):
        if "sieveAnalysis" in src:
            val = src.get("sieveAnalysis")
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(val)
            s = str(val).strip().lower()
            if s in ("0", "false", "off", "no"):
                return False
            if s in ("1", "true", "on", "yes"):
                return True
    return True


def print_thermal_report(report_data: Dict[str, Any], printer_port: Optional[str] = None) -> Dict[str, Any]:
    global _PRINT_BUSY
    port = printer_port or _thermal_port
    baud = _thermal_baud
    if not serial:
        return {"success": False, "error": "pyserial not installed", "port": port}
    try:
        port = _probe_port(port, THERMAL_CANDIDATES)
    except FileNotFoundError as e:
        return {"success": False, "error": f"Thermal printer port not found: {e.filename or port}", "port": port}
    if not _PRINT_IO_LOCK.acquire(blocking=False):
        return {"success": False, "error": "Printer busy — wait for the current print to finish.", "port": port}
    _PRINT_BUSY = True
    try:
        text = format_for_thermal_printer(report_data)
        ser = serial.Serial(port=port, baudrate=baud, timeout=2.0)
        try:
            _send_printer_init(ser)
            time.sleep(0.2)
            _send_thermal_logo(ser, baud)
            # Sieve reports: horizontal ## ASCII chart is already in the text body.
            # Do not inject ESC/POS raster graphs (logo unchanged).
            safe_text = text.replace(_THERMAL_GRAPH_MARKER, "")
            _send_text_to_thermal(ser, safe_text, baud)
            time.sleep(0.5)
            return {"success": True, "port": port}
        finally:
            ser.close()
    except Exception as e:
        return {"success": False, "error": str(e), "port": port}
    finally:
        _PRINT_BUSY = False
        _PRINT_IO_LOCK.release()


_SIEVE_LOGO_BIN_PATH = pathlib.Path(__file__).parent / "assets" / "rle_logo_thermal.bin"
_ASSETS_DIR = pathlib.Path(__file__).resolve().parent / "assets"
# LeakTest-CFR aligned: prefer wide rle_logo, apple-touch as fallback (never first).
_THERMAL_LOGO_CANDIDATES = (
    _ASSETS_DIR / "rle_logo.png",
    _ASSETS_DIR / "rle_logo_nobg.png",
    _ASSETS_DIR / "imiages" / "rle_logo.png",
    _ASSETS_DIR / "apple-touch-icon.png",
    _ASSETS_DIR / "imiages" / "apple-touch-icon.png",
)
THERMAL_RASTER_WIDTH = 384  # 58mm ESC/POS paper width (multiple of 8)
THERMAL_LOGO_PRINT_WIDTH = 240  # Centered — not full-bleed (avoids tall/noisy square icons)
_thermal_logo_raster_cache: Optional[bytes] = None
_thermal_logo_raster_mtime: Optional[float] = None

try:
    from PIL import Image as _PILImage
except ImportError:
    _PILImage = None


def _resolve_thermal_logo_path() -> Optional[pathlib.Path]:
    for path in _THERMAL_LOGO_CANDIDATES:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _pil_to_escpos_raster(img: Any, width_pixels: int) -> bytes:
    """Convert a PIL image to ESC/POS GS v 0 raster bytes (width multiple of 8)."""
    if _PILImage is None:
        raise RuntimeError("Pillow (PIL) is required for thermal logo printing")
    width_pixels = max(8, int(width_pixels) - (int(width_pixels) % 8))
    if img.mode != "L":
        img = img.convert("L")
    w, h = img.size
    if w != width_pixels:
        new_h = max(1, int(round(h * (width_pixels / float(w)))))
        img = img.resize((width_pixels, new_h), _PILImage.NEAREST)
        w, h = img.size
    # Dark pixels print (1), light stay white (0)
    bw = img.point(lambda p: 0 if p > 160 else 1, "1")
    m = 0
    xL = (w // 8) & 0xFF
    xH = ((w // 8) >> 8) & 0xFF
    yL = h & 0xFF
    yH = (h >> 8) & 0xFF
    header = bytes([0x1D, 0x76, 0x30, m, xL, xH, yL, yH])
    row_bytes = w // 8
    raw = bw.tobytes()
    out = bytearray(header)
    for row in range(h):
        start = row * row_bytes
        out.extend(raw[start : start + row_bytes])
    return bytes(out)


def _build_centered_thermal_logo_raster(
    logo_path: pathlib.Path,
    *,
    paper_width: int = THERMAL_RASTER_WIDTH,
    logo_width: int = THERMAL_LOGO_PRINT_WIDTH,
) -> bytes:
    """Trim, scale with NEAREST, center on paper — LeakTest/DT clean mono thermal logo."""
    if _PILImage is None:
        raise RuntimeError("Pillow (PIL) is required for thermal logo printing")
    paper_width = max(8, int(paper_width) - (int(paper_width) % 8))
    logo_width = max(8, int(logo_width) - (int(logo_width) % 8))
    logo_width = min(logo_width, paper_width)

    src = _PILImage.open(logo_path)
    src.load()

    if src.mode in ("1", "L"):
        mono = src.convert("L")
    else:
        # Color brand art → mono for thermal (DT color→black rules)
        rgba = src.convert("RGBA")
        gray = _PILImage.new("L", rgba.size, 255)
        px = rgba.load()
        gp = gray.load()
        w0, h0 = rgba.size
        for y in range(h0):
            for x in range(w0):
                r, g, b, a = px[x, y]
                if a < 20:
                    continue
                if r < 50 and g < 55 and b < 70:
                    continue
                if (r + g + b) < 90:
                    continue
                if (r + g + b) > 120 or max(r, g, b) > 100:
                    gp[x, y] = 0
        mono = gray

    inv = _PILImage.eval(mono, lambda p: 255 - p)
    bbox = inv.getbbox()
    if bbox:
        mono = mono.crop(bbox)

    # Hard threshold before upscale so NEAREST does not invent mid-grays
    mono = mono.point(lambda p: 0 if p < 160 else 255)
    new_h = max(1, int(round(mono.height * (logo_width / float(max(1, mono.width))))))
    mono = mono.resize((logo_width, new_h), _PILImage.NEAREST)

    canvas = _PILImage.new("L", (paper_width, mono.height), 255)
    ox = max(0, (paper_width - logo_width) // 2)
    canvas.paste(mono, (ox, 0))
    return _pil_to_escpos_raster(canvas, paper_width)


def _thermal_logo_raster_bytes() -> Optional[bytes]:
    """Cached ESC/POS raster for thermal header logo (LeakTest pipeline)."""
    global _thermal_logo_raster_cache, _thermal_logo_raster_mtime
    if _PILImage is None:
        _log.warning("Pillow not installed; thermal logo skipped")
        return None
    path = _resolve_thermal_logo_path()
    if path is None:
        _log.warning("Thermal logo missing (checked rle_logo.png, apple-touch-icon.png)")
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if _thermal_logo_raster_cache is not None and _thermal_logo_raster_mtime == mtime:
        return _thermal_logo_raster_cache
    try:
        raster = _build_centered_thermal_logo_raster(path)
        _thermal_logo_raster_cache = raster
        _thermal_logo_raster_mtime = mtime
        return raster
    except Exception as e:
        _log.warning("Thermal logo raster failed: %s", e)
        return None


def _send_thermal_logo(ser, baud: int) -> bool:
    """Send LeakTest-style centered thermal logo (prebuilt .bin fallback)."""
    try:
        raster = _thermal_logo_raster_bytes()
        if not raster and _SIEVE_LOGO_BIN_PATH.is_file():
            raster = _SIEVE_LOGO_BIN_PATH.read_bytes()
        if not raster:
            return False
        chunk_size = 512 if baud <= 9600 else 1024
        pause = 0.08 if baud <= 9600 else 0.05
        for i in range(0, len(raster), chunk_size):
            ser.write(raster[i : i + chunk_size])
            ser.flush()
            if i + chunk_size < len(raster):
                time.sleep(pause)
        ser.write(b"\n")
        ser.flush()
        time.sleep(0.05)
        return True
    except Exception:
        return False


def _recipe_mode_label(recipe: Dict[str, Any]) -> str:
    mode = str(recipe.get("uspMode") or recipe.get("usp") or "").strip().upper()
    if mode == "USP":
        return "USP"
    if mode == "CUSTOM":
        comp = str(recipe.get("customCompletionMode") or "COUNT").strip().upper()
        if comp == "TIME":
            return "Custom (Time)"
        return "Custom (Count)"
    return "--"


def _recipe_rpm(recipe: Dict[str, Any]) -> Any:
    speed = recipe.get("speed")
    if speed not in (None, ""):
        return speed
    steps = recipe.get("steps") if isinstance(recipe.get("steps"), list) else []
    if steps and isinstance(steps[0], dict) and steps[0].get("speed") not in (None, ""):
        return steps[0].get("speed")
    return None


def _recipe_rotations(recipe: Dict[str, Any]) -> Any:
    for key in ("tabletCount", "customTotalTaps"):
        val = recipe.get(key)
        if val not in (None, ""):
            return val
    steps = recipe.get("steps") if isinstance(recipe.get("steps"), list) else []
    if len(steps) == 1 and isinstance(steps[0], dict):
        val = steps[0].get("tapCount")
        if val not in (None, ""):
            return val
    return None


def _recipe_time_display(recipe: Dict[str, Any]) -> str:
    time_seconds = recipe.get("timeSeconds")
    if time_seconds not in (None, ""):
        try:
            total = max(0, int(time_seconds))
            minutes, seconds = divmod(total, 60)
            return f"{minutes:02d}:{seconds:02d}"
        except (TypeError, ValueError):
            pass
    time_minutes = recipe.get("timeMinutes")
    if time_minutes not in (None, ""):
        try:
            total = max(0, int(round(float(time_minutes) * 60)))
            minutes, seconds = divmod(total, 60)
            return f"{minutes:02d}:{seconds:02d}"
        except (TypeError, ValueError):
            pass
    return "--"


def _is_sieve_shaker_recipe(recipe: Dict[str, Any]) -> bool:
    if not isinstance(recipe, dict):
        return False
    return recipe.get("numSieves") is not None or bool(recipe.get("shakerMode"))


def _sieve_recipe_duration_display(recipe: Dict[str, Any]) -> str:
    sec = recipe.get("durationSeconds")
    if sec in (None, ""):
        return "--"
    try:
        total = max(0, int(sec))
        minutes, seconds = divmod(total, 60)
        return f"{minutes:02d}:{seconds:02d}"
    except (TypeError, ValueError):
        return "--"


def _append_sieve_shaker_recipe_lines(lines: list, recipe: Dict[str, Any], thermal: bool) -> None:
    name = recipe.get("productName") or recipe.get("name") or "N/A"
    batch = recipe.get("batchNumber") or recipe.get("batch")
    analysis_on = recipe.get("sieveAnalysis")
    if isinstance(analysis_on, bool):
        analysis_label = "ON" if analysis_on else "OFF"
    else:
        analysis_label = "OFF" if str(analysis_on or "").strip().lower() in ("0", "false", "off", "no") else "ON"

    lines.append(f"Recipe Name: {name}")
    if batch not in (None, ""):
        lines.append(f"Batch No: {batch}")
    lines.append(f"Vibration Mode: {_cell_str(recipe.get('shakerMode'))}")
    lines.append(f"Amplitude: {_fmt_amplitude_display(recipe.get('amplitude'))} mm")
    lines.append(f"Duration: {_sieve_recipe_duration_display(recipe)} (MM:SS)")
    lines.append(f"No. of Sieves: {_cell_str(recipe.get('numSieves'))}")
    lines.append(f"Sieve Analysis: {analysis_label}")
    weigh_method = recipe.get("weighMethod")
    if weigh_method not in (None, ""):
        lines.append(f"Weigh Method: {str(weigh_method).title()}")
    sizes = recipe.get("sieveSizes")
    if isinstance(sizes, list) and sizes:
        lines.append(f"Sieve Sizes: {', '.join(str(s) for s in sizes)} um")
    if str(recipe.get("shakerMode") or "").strip().upper() == "LOGICAL":
        for key, label in (
            ("logicalRunSeconds", "Run Time"),
            ("logicalWaitSeconds", "Wait Time"),
            ("logicalCycles", "Cycles"),
        ):
            val = recipe.get(key)
            if val not in (None, ""):
                unit = " sec" if "Seconds" in key else ""
                lines.append(f"{label}: {_cell_str(val)}{unit}")

    approved_by = recipe.get("recipeApprovedBy")
    if approved_by not in (None, ""):
        lines.append(f"Recipe Approved By: {_strip_approver_role_label(approved_by)}")
    approver_id = recipe.get("recipeApprovedByUsername")
    if approver_id not in (None, ""):
        lines.append(f"Approver ID: {approver_id}")


def _append_recipe_detail_lines(lines: list, recipe: Dict[str, Any], thermal: bool) -> None:
    mode = str(recipe.get("uspMode") or recipe.get("usp") or "").strip().upper()
    completion = str(recipe.get("customCompletionMode") or "COUNT").strip().upper()
    name = recipe.get("productName") or recipe.get("name") or "N/A"
    batch = recipe.get("batchNumber") or recipe.get("batch")
    rpm = _recipe_rpm(recipe)
    rotations = _recipe_rotations(recipe)
    drum_count = recipe.get("drumCount")

    lines.append(f"Recipe Name: {name}")
    if batch not in (None, ""):
        lines.append(f"Batch No: {batch}")
    lines.append(f"Mode: {_recipe_mode_label(recipe)}")
    lines.append(f"RPM: {_cell_str(rpm)}")
    if mode == "USP":
        lines.append(f"Time: {_recipe_time_display(recipe)}")
        lines.append(f"Rotations: {_cell_str(rotations)}")
    elif mode == "CUSTOM":
        if completion == "TIME":
            lines.append(f"Time: {_recipe_time_display(recipe)}")
        else:
            lines.append(f"Rotations: {_cell_str(rotations)}")
    elif rotations not in (None, ""):
        lines.append(f"Rotations: {_cell_str(rotations)}")
    if drum_count not in (None, ""):
        lines.append(f"Drums: {_cell_str(drum_count)}")

    approved_by = recipe.get("recipeApprovedBy")
    if approved_by not in (None, ""):
        lines.append(f"Recipe Approved By: {_strip_approver_role_label(approved_by)}")
    approver_id = recipe.get("recipeApprovedByUsername")
    if approver_id not in (None, ""):
        lines.append(f"Approver ID: {approver_id}")


def _format_recipe_text(recipe_data: Dict[str, Any], width: int = A4_TEXT_WIDTH) -> str:
    thermal = width < 70
    sep = _thermal_sep("=", width) if thermal else ("=" * width)
    sep_dash = _thermal_sep("-", width) if thermal else ("-" * width)
    fs = recipe_data.get("factorySettings") or {}
    is_sieve = _is_sieve_shaker_recipe(recipe_data)
    title = "SIEVE SHAKER RECIPE" if is_sieve else "FRIABILITY RECIPE"
    lines = [
        sep,
        title if thermal else title.center(width),
        "",
        f"Company: {fs.get('companyName', 'N/A')}",
        f"Model No: {fs.get('modelNo', 'N/A')}",
        f"Serial No: {fs.get('serialNo', 'N/A')}",
        f"Location: {fs.get('companyLocation', fs.get('location', 'N/A'))}",
        f"Instrument ID: {fs.get('instrumentId', 'N/A')}",
        f"Last Val: {_format_display_date(fs.get('lastValidationDate', 'N/A'))}",
        f"Next Val Due: {_format_display_date(fs.get('nextValidationDate', 'N/A'))}",
        sep,
        "RECIPE DETAILS",
        sep_dash if thermal else "",
    ]
    if is_sieve:
        _append_sieve_shaker_recipe_lines(lines, recipe_data, thermal)
    else:
        _append_recipe_detail_lines(lines, recipe_data, thermal)
    lines.append(sep)
    if thermal:
        flat: list = []
        for line in lines:
            flat.extend(_fit_thermal_line(line, width))
        return "\n".join(_compact_thermal_lines(flat, width))
    return "\n".join(_wrap_lines(lines, width))


def print_recipe_a4(recipe_data: Dict[str, Any], printer_port: Optional[str] = None) -> Dict[str, Any]:
    port = printer_port or _a4_port
    baud = _a4_baud
    if not serial:
        return {"success": False, "error": "pyserial not installed", "port": port}
    if not _port_exists(port):
        return {"success": False, "error": f"A4 printer port not found: {port}", "port": port}
    try:
        text = _format_recipe_text(recipe_data, width=A4_TEXT_WIDTH).rstrip() + "\r\n\x0c"
        ser = _open_a4_serial(port, baud)
        try:
            ser.reset_output_buffer()
            ser.flush()
            _send_printer_init(ser)
            _send_text_to_a4(ser, text, baud)
            time.sleep(0.5)
            return {"success": True, "port": port}
        finally:
            ser.close()
    except Exception as e:
        return {"success": False, "error": str(e), "port": port}


def print_recipe_thermal(recipe_data: Dict[str, Any], printer_port: Optional[str] = None) -> Dict[str, Any]:
    port = printer_port or _thermal_port
    baud = _thermal_baud
    if not serial:
        return {"success": False, "error": "pyserial not installed", "port": port}
    try:
        port = _probe_port(port, THERMAL_CANDIDATES)
    except FileNotFoundError as e:
        return {"success": False, "error": f"Thermal printer port not found: {e.filename or port}", "port": port}
    try:
        text = _format_recipe_text(recipe_data, width=THERMAL_WIDTH).rstrip("\n")
        footer = "\n".join(_thermal_printed_timestamp_lines())
        text = text + "\n\n" + footer + _thermal_trailing_feed()
        ser = serial.Serial(port=port, baudrate=baud, timeout=2.0)
        try:
            _send_printer_init(ser)
            time.sleep(0.2)
            _send_text_to_thermal(ser, text, baud)
            time.sleep(0.5)
            return {"success": True, "port": port}
        finally:
            ser.close()
    except Exception as e:
        return {"success": False, "error": str(e), "port": port}
