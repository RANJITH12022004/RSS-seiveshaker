#!/usr/bin/env python3
"""
shaker_run_service.py - Backend scheduler for Sieve Shaker CFR test programs.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

import hardware_service

_program_lock = threading.Lock()
_run_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_complete_event = threading.Event()
_abort_event = threading.Event()
_program: Dict[str, Any] = {}
_run_result: Dict[str, Any] = {}


def _now() -> float:
    return time.time()


def _normalize_mode(mode: str) -> str:
    m = str(mode or "CONTINUOUS").strip().upper()
    if m in ("C", "CONTINUOUS"):
        return "CONTINUOUS"
    if m in ("I", "INTERMITTENT"):
        return "INTERMITTENT"
    if m in ("L", "LOGICAL"):
        return "LOGICAL"
    return m


def _hw_mode_for_shaker(shaker_mode: str) -> str:
    return "I" if _normalize_mode(shaker_mode) == "INTERMITTENT" else "C"


def _sleep_until(
    stop_at: float,
    tick: float = 0.1,
    on_tick=None,
    progress_tick: float = 0.5,
) -> bool:
    """Sleep until stop_at or until stop/abort requested. Returns True if interrupted."""
    last_progress_at = 0.0
    while _now() < stop_at:
        now = _now()
        if on_tick and (
            last_progress_at == 0.0
            or (now - last_progress_at) >= progress_tick
            or (stop_at - now) <= progress_tick
        ):
            on_tick(now)
            last_progress_at = now
        if _stop_event.is_set() or _abort_event.is_set():
            return True
        time.sleep(min(tick, max(0.01, stop_at - now)))
    if on_tick:
        on_tick(_now())
    return _stop_event.is_set() or _abort_event.is_set()


def _ensure_off(hw_mode: str) -> None:
    hardware_service.cmd_shaker_stop(hw_mode)


def _run_on(amplitude: int, hw_mode: str) -> dict:
    return hardware_service.cmd_shaker_start(amplitude, hw_mode)


def _update_progress(
    *,
    phase: str,
    elapsed_sec: float,
    target_duration_sec: float,
    segment_index: int = 0,
    segment_count: int = 0,
    running: bool = True,
    program_done: bool = False,
    completed_early: bool = False,
) -> None:
    remaining = max(0.0, float(target_duration_sec) - float(elapsed_sec))
    hardware_service.update_shaker_live_state(
        running=running,
        phase=phase,
        elapsedSec=round(elapsed_sec, 1),
        targetDurationSec=int(target_duration_sec),
        remainingSec=round(remaining, 1),
        segmentIndex=segment_index,
        segmentCount=segment_count,
        programDone=program_done,
        completedEarly=completed_early,
    )


def _run_continuous(program: Dict[str, Any]) -> None:
    amplitude = int(program["amplitude"])
    duration = max(1, int(program.get("durationSeconds") or 1))
    hw_mode = _hw_mode_for_shaker(program.get("shakerMode"))
    start = _now()

    def publish_progress(now: float) -> None:
        _update_progress(
            phase="run",
            elapsed_sec=min(duration, max(0.0, now - start)),
            target_duration_sec=duration,
        )

    _run_on(amplitude, hw_mode)
    interrupted = _sleep_until(start + duration, on_tick=publish_progress)
    elapsed = min(duration, max(0.0, _now() - start))
    _ensure_off(hw_mode)
    _update_progress(
        phase="off",
        elapsed_sec=elapsed,
        target_duration_sec=duration,
        running=False,
        program_done=True,
        completed_early=interrupted and not _abort_event.is_set(),
    )


def _run_intermittent(program: Dict[str, Any]) -> None:
    """Run for durationSeconds with firmware intermittent mode (command letter I).

    On/off pulse timing is owned by the ESP when mode is I — do not software-toggle
    from UI on/off fields (those belong to Logical run/wait cycles only).
    """
    _run_continuous(program)


def _run_logical(program: Dict[str, Any]) -> None:
    amplitude = int(program["amplitude"])
    segments: List[Dict[str, Any]] = list(program.get("logicalSegments") or [])
    hw_mode = "C"
    total_target = sum(max(1, int(s.get("durationSeconds") or 1)) for s in segments)
    start = _now()
    seg_count = len(segments)
    for idx, seg in enumerate(segments):
        if _stop_event.is_set() or _abort_event.is_set():
            break
        seg_type = str(seg.get("type") or "run").strip().lower()
        seg_dur = max(1, int(seg.get("durationSeconds") or 1))
        seg_end = _now() + seg_dur

        def publish_segment_progress(now: float) -> None:
            _update_progress(
                phase="run" if seg_type == "run" else "wait",
                elapsed_sec=min(total_target, max(0.0, now - start)),
                target_duration_sec=total_target,
                segment_index=idx + 1,
                segment_count=seg_count,
                running=(seg_type == "run"),
            )

        if seg_type == "run":
            _run_on(amplitude, hw_mode)
        else:
            _ensure_off(hw_mode)
        if _sleep_until(seg_end, on_tick=publish_segment_progress):
            break
    _ensure_off(hw_mode)
    elapsed = min(total_target, max(0.0, _now() - start))
    _update_progress(
        phase="off",
        elapsed_sec=elapsed,
        target_duration_sec=total_target,
        segment_index=seg_count,
        segment_count=seg_count,
        running=False,
        program_done=True,
        completed_early=(_stop_event.is_set() or elapsed < total_target) and not _abort_event.is_set(),
    )


def _run_worker(program: Dict[str, Any]) -> None:
    global _run_result
    mode = _normalize_mode(program.get("shakerMode"))
    hw_mode = _hw_mode_for_shaker(mode)
    try:
        hardware_service.reset_shaker_live_state(
            amplitude=int(program.get("amplitude") or 5),
            mode=hw_mode,
            shakerMode=mode,
            targetDurationSec=int(program.get("durationSeconds") or 0),
            segmentCount=len(program.get("logicalSegments") or []),
        )
        if mode == "INTERMITTENT":
            _run_intermittent(program)
        elif mode == "LOGICAL":
            _run_logical(program)
        else:
            _run_continuous(program)
        state = hardware_service.get_live_state()
        _run_result = {
            "ok": True,
            "aborted": _abort_event.is_set(),
            "completedEarly": bool(state.get("completedEarly")),
            "elapsedSec": state.get("elapsedSec"),
            "programDone": bool(state.get("programDone")),
        }
    except Exception as e:
        _ensure_off(_hw_mode_for_shaker(program.get("shakerMode")))
        hardware_service.stop_shaker_live_state()
        _run_result = {"ok": False, "error": str(e)}
    finally:
        _complete_event.set()


def start_program(program: Dict[str, Any]) -> Dict[str, Any]:
    global _run_thread, _run_result
    with _program_lock:
        if _run_thread and _run_thread.is_alive():
            return {"ok": False, "error": "program_already_running"}
        _stop_event.clear()
        _abort_event.clear()
        _complete_event.clear()
        _program = dict(program or {})
        _run_result = {}
        _run_thread = threading.Thread(target=_run_worker, args=(_program,), daemon=True)
        _run_thread.start()
    return {"ok": True, "started": True}


def complete_program() -> Dict[str, Any]:
    _stop_event.set()
    return {"ok": True, "completing": True}


def abort_program() -> Dict[str, Any]:
    _abort_event.set()
    _stop_event.set()
    state = hardware_service.get_live_state()
    hw_mode = str(state.get("mode") or "C")
    hardware_service.cmd_shaker_stop(hw_mode)
    hardware_service.stop_shaker_live_state()
    return {"ok": True, "aborted": True}


def get_program_status() -> Dict[str, Any]:
    alive = bool(_run_thread and _run_thread.is_alive())
    state = hardware_service.get_live_state()
    out = {"ok": True, "running": alive or bool(state.get("running")), **state}
    if _complete_event.is_set() and _run_result:
        out["result"] = dict(_run_result)
    return out


def is_program_running() -> bool:
    return bool(_run_thread and _run_thread.is_alive())
