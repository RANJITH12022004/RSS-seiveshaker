#!/usr/bin/env python3
"""
report_service.py - Tap Density report generation and context.
"""

import html as html_module
import json
import pathlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

import data_service

_config = {}
_reports_dir = None
_storage_dir = None


def init(config):
    global _config, _reports_dir, _storage_dir
    _config = dict(config)
    _reports_dir = pathlib.Path(_config.get("REPORTS_DIR", "./reports"))
    _storage_dir = pathlib.Path(_config.get("STORAGE_DIR", "./storage"))
    _reports_dir.mkdir(parents=True, exist_ok=True)


def generate_report(
    test_data: Dict[str, Any],
    recipe: Optional[Dict[str, Any]] = None,
    factory_settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    report = dict(test_data)
    if recipe:
        # Keep speed/USP/drums on the stub — print/preview derived RPM reads these.
        # Full recipe also remains under testData.recipe from the client payload.
        report["recipe"] = {
            "id": recipe.get("id"),
            "name": recipe.get("name") or recipe.get("productName"),
            "productName": recipe.get("productName"),
            "batchNumber": recipe.get("batchNumber"),
            "unit": recipe.get("unit"),
            "shakerMode": recipe.get("shakerMode"),
            "amplitude": recipe.get("amplitude"),
            "durationSeconds": recipe.get("durationSeconds"),
            "quickTest": recipe.get("quickTest"),
            "validationType": recipe.get("validationType"),
            "numSieves": recipe.get("numSieves"),
            "sieveSizes": recipe.get("sieveSizes"),
            "weighMethod": recipe.get("weighMethod"),
            "initialWeight": recipe.get("initialWeight"),
        }
    if not factory_settings:
        factory_settings = data_service.get_factory_settings()
    report["factorySettings"] = enrich_factory_settings(factory_settings or {})
    if not report.get("createdAt"):
        report["createdAt"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if not report.get("completedAt"):
        report["completedAt"] = report["createdAt"]
    report = enrich_report_context(report)
    return report


def enrich_factory_settings(factory_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Merge display defaults; keep policy fields (auto logout, password reset period, etc.)."""
    fs_in = dict(factory_settings or {})
    out = dict(fs_in)
    out.update(
        {
            "companyName": fs_in.get("companyName") or "N/A",
            "modelNo": fs_in.get("modelNo") or "N/A",
            "serialNo": fs_in.get("serialNo") or "N/A",
            "companyLocation": fs_in.get("companyLocation") or fs_in.get("location") or "N/A",
            "instrumentId": fs_in.get("instrumentId") or "N/A",
            "lastValidationDate": fs_in.get("lastValidationDate") or "N/A",
            "nextValidationDate": fs_in.get("nextValidationDate") or "N/A",
        }
    )
    dates = _resolve_validation_dates(fs_in)
    if dates.get("lastValidationDate"):
        out["lastValidationDate"] = dates["lastValidationDate"]
    if dates.get("nextValidationDate"):
        out["nextValidationDate"] = dates["nextValidationDate"]
    return out


def format_duration_hhmmss(seconds_val: Any) -> str:
    """Format elapsed seconds as HH:MM:SS for reports."""
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


def test_duration_seconds(td: Dict[str, Any]) -> Optional[int]:
    """Resolve test duration in seconds from stored testData."""
    if not isinstance(td, dict):
        return None
    sec = td.get("durationSeconds")
    if sec is not None:
        try:
            return max(0, int(sec))
        except (TypeError, ValueError):
            pass
    start_raw = td.get("testStartTime")
    end_raw = td.get("testEndTime")
    if start_raw and end_raw:
        try:
            start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
            return max(0, int((end - start).total_seconds()))
        except Exception:
            pass
    return None


def _parse_density_number(val: Any) -> Optional[float]:
    if val is None or val == "" or val == "--":
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _stat_display_value(val: Dict[str, Any]) -> Any:
    if val.get("value") is not None:
        return val.get("value")
    if val.get("mean") is not None:
        return val.get("mean")
    if val.get("Mean") is not None:
        return val.get("Mean")
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


def _agg_mean_min_max(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    return {
        "mean": round(sum(values) / len(values), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def _parse_float(val: Any) -> Optional[float]:
    if val is None or val == "" or val == "--":
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _format_derived_number(val: Any, decimals: int = 3) -> str:
    if val is None:
        return "--"
    try:
        f = float(val)
        if decimals <= 0:
            return str(int(round(f)))
        fmt = f"{{:.{decimals}f}}"
        s = fmt.format(f)
        return s.rstrip("0").rstrip(".") if "." in s else s
    except (TypeError, ValueError):
        return str(val)


def _report_print_timestamp() -> Dict[str, str]:
    try:
        import rtc_service

        payload = rtc_service.get_device_wall_datetime_payload()
        return {
            "printDate": _display_date_slashes(payload.get("date") or "--"),
            "printTime": str(payload.get("time") or "--"),
        }
    except Exception:
        now = datetime.now()
        return {
            "printDate": now.strftime("%d/%m/%Y"),
            "printTime": now.strftime("%H:%M:%S"),
        }


def _test_type_label(recipe: Dict[str, Any], td: Dict[str, Any]) -> str:
    recipe = recipe or {}
    td = td or {}
    mode = str(recipe.get("uspMode") or td.get("uspMode") or "").strip().upper()
    if mode == "USP1":
        return "USP 1"
    if mode == "USP2":
        return "USP 2"
    if mode == "CUSTOM":
        return "Custom"
    usp = str(recipe.get("usp") or td.get("usp") or "").strip()
    if not usp:
        return "--"
    u = usp.upper().replace("  ", " ")
    if u in ("USP1", "USP 1"):
        return "USP 1"
    if u in ("USP2", "USP 2"):
        return "USP 2"
    if "CUSTOM" in u:
        return "Custom"
    return usp


def _test_method_label(recipe: Dict[str, Any], td: Dict[str, Any], test_type: str) -> str:
    recipe = recipe or {}
    td = td or {}
    cyl = recipe.get("cylinder") if isinstance(recipe.get("cylinder"), dict) else {}
    cyl_ml = cyl.get("volume") or cyl.get("volumeMl") or td.get("sampleVolumeMl")
    parts = [test_type] if test_type and test_type != "--" else []
    if cyl_ml not in (None, "", "--"):
        parts.append(f"{cyl_ml} ml cylinder")
    return ", ".join(parts) if parts else "--"


def completed_step_count(td: Dict[str, Any]) -> int:
    """Number of recipe steps that actually ran (recorded in the report)."""
    if not isinstance(td, dict):
        return 0
    results = td.get("stepResults") or []
    if isinstance(results, list) and results:
        return len(results)
    try:
        return max(0, int(td.get("completedSteps") or 0))
    except (TypeError, ValueError):
        return 0


def _recipe_steps_for_report(td: Dict[str, Any], recipe: Dict[str, Any]) -> list:
    steps = recipe.get("steps") if isinstance(recipe, dict) else []
    if not isinstance(steps, list) or not steps:
        steps = td.get("steps") if isinstance(td, dict) else []
    return steps if isinstance(steps, list) else []


def performed_total_drops(td: Dict[str, Any], recipe: Dict[str, Any]) -> Optional[int]:
    """Sum per-step drop counts for completed steps only (not planned recipe total)."""
    if not isinstance(td, dict):
        return None
    n = completed_step_count(td)
    if n <= 0:
        return None
    results = td.get("stepResults") or []
    if not isinstance(results, list):
        results = []
    steps = _recipe_steps_for_report(td, recipe if isinstance(recipe, dict) else {})
    total = 0
    found = False
    for i in range(n):
        step_taps = None
        if i < len(steps) and isinstance(steps[i], dict):
            step_taps = steps[i].get("tapCount")
        if step_taps in (None, "") and i < len(results) and isinstance(results[i], dict):
            step_taps = results[i].get("tapCount")
        try:
            val = int(step_taps)
            if val > 0:
                total += val
                found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


def completed_step_drop_counts(td: Dict[str, Any], recipe: Dict[str, Any]) -> List[Any]:
    """Per-step drop counts for completed steps only."""
    n = completed_step_count(td)
    if n <= 0:
        return []
    steps = _recipe_steps_for_report(td, recipe if isinstance(recipe, dict) else {})
    counts: List[Any] = []
    results = td.get("stepResults") or []
    if not isinstance(results, list):
        results = []
    for i in range(n):
        step_taps = None
        if i < len(steps) and isinstance(steps[i], dict):
            step_taps = steps[i].get("tapCount")
        if step_taps in (None, "") and i < len(results) and isinstance(results[i], dict):
            step_taps = results[i].get("tapCount")
        if step_taps is not None:
            counts.append(step_taps)
    return counts


def resolve_initial_volume_ml(td: Dict[str, Any]) -> Optional[float]:
    """V₀ from weight-entry volume; not the first step reading unless legacy data lacks V₀."""
    if not isinstance(td, dict):
        return None
    initial_vol = _parse_float(td.get("initialVolumeMl"))
    if initial_vol is not None and initial_vol > 0:
        return initial_vol
    results = td.get("stepResults") or []
    if isinstance(results, list) and results and isinstance(results[0], dict):
        legacy = _parse_float(results[0].get("volumeMl"))
        if legacy is not None and legacy > 0:
            return legacy
    return None


def _drop_height_display(recipe: Dict[str, Any], td: Dict[str, Any]) -> str:
    recipe = recipe or {}
    td = td or {}
    dh = recipe.get("dropHeight")
    steps = recipe.get("steps") or td.get("steps") or []
    if dh is None and isinstance(steps, list) and steps and isinstance(steps[0], dict):
        dh = steps[0].get("dropHeight")
    if dh is None and isinstance(td, dict):
        dh = td.get("dropHeight")
    if dh is None or dh == "":
        return "--"
    try:
        mm = float(dh)
        return f"{_format_derived_number(mm, 0)} mm +/- 0.2 mm"
    except (TypeError, ValueError):
        return str(dh)


def _merge_recipe_for_derived(
    td: Dict[str, Any], recipe: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Prefer full embedded testData.recipe when top-level recipe was stripped."""
    recipe = recipe if isinstance(recipe, dict) else {}
    td_recipe = td.get("recipe") if isinstance(td.get("recipe"), dict) else {}
    if td_recipe:
        merged = dict(td_recipe)
        for k, v in recipe.items():
            if v not in (None, ""):
                merged[k] = v
        return merged
    return dict(recipe)


def _resolve_report_rpm(recipe: Dict[str, Any], td: Dict[str, Any]) -> Any:
    """RPM from recipe.speed, testData.speed/rpm, or first step speed (quick + saved recipes)."""
    speed = recipe.get("speed")
    if speed in (None, ""):
        speed = td.get("speed")
    if speed in (None, ""):
        speed = td.get("rpm")
    steps = recipe.get("steps") or td.get("steps") or []
    if speed in (None, "") and isinstance(steps, list) and steps and isinstance(steps[0], dict):
        speed = steps[0].get("speed")
    return speed


def build_test_report_derived(
    td: Optional[Dict[str, Any]],
    recipe: Optional[Dict[str, Any]] = None,
    report_id: Any = None,
) -> Dict[str, Any]:
    """Sieve shaker test report fields."""
    td = td if isinstance(td, dict) else {}
    recipe = _merge_recipe_for_derived(td, recipe)

    shaker_mode = td.get("shakerMode") or recipe.get("shakerMode") or "CONTINUOUS"
    amplitude = td.get("amplitude") if td.get("amplitude") is not None else recipe.get("amplitude")
    duration_sec = td.get("durationSeconds") or recipe.get("durationSeconds")
    if duration_sec is None:
        duration_sec = test_duration_seconds(td)

    test_no = "--"
    if report_id is not None:
        try:
            test_no = f"{int(report_id):04d}"
        except (TypeError, ValueError):
            test_no = str(report_id)

    ts = _report_print_timestamp()
    return {
        **ts,
        "testNumber": test_no,
        "testType": "Sieve Shaker",
        "testMethod": shaker_mode,
        "shakerMode": shaker_mode,
        "amplitude": amplitude if amplitude is not None else "--",
        "durationSeconds": duration_sec,
        "durationFormatted": format_duration_hhmmss(duration_sec),
        "intermittentOnSeconds": td.get("intermittentOnSeconds") or recipe.get("intermittentOnSeconds"),
        "intermittentOffSeconds": td.get("intermittentOffSeconds") or recipe.get("intermittentOffSeconds"),
        "logicalSegments": td.get("logicalSegments") or recipe.get("logicalSegments") or [],
        "actualElapsedSeconds": td.get("actualElapsedSeconds"),
        "completedEarly": td.get("completedEarly"),
        "batchNumber": td.get("batchNumber") or recipe.get("batchNumber"),
        "productName": recipe.get("productName") or td.get("productName"),
    }


def compute_test_report_statistics(test_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Sieve shaker statistics from testData."""
    if not isinstance(test_data, dict):
        return None

    stats: Dict[str, Any] = {}
    amp = test_data.get("amplitude")
    if amp is not None:
        try:
            stats["Amplitude"] = {"value": int(amp)}
        except (TypeError, ValueError):
            pass
    mode = test_data.get("shakerMode")
    if mode:
        stats["Shaker mode"] = {"value": str(mode)}
    dur = test_data.get("actualElapsedSeconds") or test_data.get("durationSeconds")
    if dur is not None:
        try:
            stats["Duration (s)"] = {"value": int(float(dur))}
        except (TypeError, ValueError):
            pass
    if test_data.get("completedEarly") is True:
        stats["Completed early"] = {"value": "Yes"}

    return stats if stats else None


def enrich_report_context(report_data: Dict[str, Any]) -> Dict[str, Any]:
    if not report_data:
        return report_data
    factory_settings = data_service.get_factory_settings()
    fs = report_data.get("factorySettings") or {}
    for k, default in [
        ("companyName", "N/A"),
        ("modelNo", "N/A"),
        ("serialNo", "N/A"),
        ("companyLocation", "N/A"),
        ("instrumentId", "N/A"),
    ]:
        if not fs.get(k):
            fs[k] = factory_settings.get(k) or default
    dates = _resolve_validation_dates({**factory_settings, **fs})
    if dates.get("lastValidationDate"):
        fs["lastValidationDate"] = dates["lastValidationDate"]
    if dates.get("nextValidationDate"):
        fs["nextValidationDate"] = dates["nextValidationDate"]
    report_data["factorySettings"] = fs
    if str(report_data.get("type") or "").strip().lower() == "test":
        td = report_data.get("testData") if isinstance(report_data.get("testData"), dict) else report_data
        if isinstance(td, dict):
            td_remarks = td.get("remarks")
            if td_remarks not in (None, "") and not report_data.get("remarks"):
                report_data["remarks"] = td_remarks
        computed = compute_test_report_statistics(td if isinstance(td, dict) else None)
        if computed:
            report_data["statistics"] = computed
            if isinstance(report_data.get("testData"), dict):
                report_data["testData"]["statistics"] = computed
        recipe = report_data.get("recipe") if isinstance(report_data.get("recipe"), dict) else {}
        report_data["reportDerived"] = build_test_report_derived(
            td if isinstance(td, dict) else {},
            recipe,
            report_data.get("id"),
        )
    return report_data


def _as_naive_utc(dt: datetime) -> datetime:
    """Normalize aware/naive datetimes so comparisons never mix tzinfo."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _parse_report_datetime(value: Any) -> Optional[datetime]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return _as_naive_utc(dt)
    except Exception:
        return None


def _parse_display_date(value: Any) -> Optional[datetime]:
    """Parse DD-MM-YYYY, DD/MM/YYYY, or ISO datetime strings."""
    s = str(value or "").strip()
    if not s or s.upper() == "N/A":
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt)
        except Exception:
            continue
    return _parse_report_datetime(value)


def _display_date_slashes(value: Any) -> str:
    """Return DD/MM/YYYY for report-facing date-only fields when possible."""
    dt = _parse_display_date(value)
    if dt is not None:
        return dt.strftime("%d/%m/%Y")
    return str(value or "").strip() or "N/A"


def _add_years(dt: datetime, years: int = 1) -> datetime:
    """Add calendar years; Feb 29 rolls to Feb 28 on non-leap years."""
    try:
        return dt.replace(year=dt.year + int(years or 1))
    except ValueError:
        return dt.replace(month=2, day=28, year=dt.year + int(years or 1))


def _validation_dates_from_last(dt: datetime) -> Dict[str, str]:
    """Last validation date and next due exactly one calendar year later."""
    next_dt = _add_years(dt, 1)
    return {
        "lastValidationDate": dt.strftime("%d/%m/%Y"),
        "nextValidationDate": next_dt.strftime("%d/%m/%Y"),
    }


def _resolve_validation_dates(factory_settings: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Single source for validation dates: latest validation report, else stored last; next always +1 year."""
    try:
        computed = _compute_validation_dates_from_reports()
        if computed.get("lastValidationDate"):
            return computed
    except Exception as exc:
        print(f"[REPORT] Validation date compute failed: {exc}")
    fs = factory_settings or {}
    last_dt = _parse_display_date(fs.get("lastValidationDate"))
    if last_dt:
        return _validation_dates_from_last(last_dt)
    return {}


def sync_factory_validation_dates() -> Dict[str, str]:
    """Persist resolved validation dates into factory settings storage."""
    stored = data_service.get_factory_settings() or {}
    dates = _resolve_validation_dates(stored)
    if not dates:
        return {}
    updated = dict(stored)
    updated["lastValidationDate"] = dates["lastValidationDate"]
    updated["nextValidationDate"] = dates["nextValidationDate"]
    data_service.save_factory_settings(updated)
    return dates


def _compute_validation_dates_from_reports() -> Dict[str, str]:
    reports = data_service.list_reports("validation")
    latest_dt = None
    for report in reports or []:
        if str(report.get("type") or "").strip().lower() != "validation":
            continue
        td = report.get("testData") or {}
        status_raw = str(td.get("status") or report.get("status") or "").strip().lower()
        if status_raw == "aborted":
            continue
        dt = _parse_report_datetime(
            td.get("completedAt")
            or report.get("completedAt")
            or td.get("createdAt")
            or report.get("createdAt")
        )
        if not dt:
            continue
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
    if latest_dt is None:
        return {}
    return _validation_dates_from_last(latest_dt)


def _fmt(v: Any, w: int = 0) -> str:
    """Format value as string, padded to width w."""
    s = str(v) if v is not None else "n/a"
    return s.ljust(w) if w else s


def _format_sieve_shaker_a4_text(report: Dict[str, Any]) -> str:
    """Generate clean monospace A4 text for Sieve Shaker reports."""
    r = dict(report or {})
    recipe = r.get("recipe") or {}
    td = r.get("testData") or r
    fs = r.get("factorySettings") or {}

    product = recipe.get("productName") or td.get("productName") or "n/a"
    batch = recipe.get("batchNumber") or td.get("batchNumber") or "n/a"
    amplitude = recipe.get("amplitude") or td.get("amplitude") or "n/a"
    shaker_mode = recipe.get("shakerMode") or td.get("shakerMode") or "n/a"
    weigh_method = td.get("weighMethod") or recipe.get("weighMethod") or "n/a"
    tested_by = td.get("testedBy") or r.get("operatedByUsername") or "n/a"
    status = td.get("status") or "n/a"

    duration_sec = recipe.get("durationSeconds") or td.get("durationSeconds") or 0
    duration_str = f"{int(duration_sec)//60:02d}:{int(duration_sec)%60:02d}" if duration_sec else "n/a"

    created_at = r.get("createdAt") or ""
    date_str = created_at[:10] if len(created_at) >= 10 else "n/a"
    time_str = created_at[11:19] if len(created_at) >= 19 else "n/a"

    num_sieves = int(recipe.get("numSieves") or td.get("numSieves") or 0)
    sieve_sizes = recipe.get("sieveSizes") or td.get("sieveSizes") or []
    sieve_weights = td.get("sieveWeights") or []
    before_weights = td.get("beforeWeights") or []
    after_weights = td.get("afterWeights") or []
    pan_weight = float(td.get("panWeight") or 0)
    sample_weight = float(td.get("initialWeight") or 0)
    final_weight = float(td.get("finalWeight") or 0)

    approval_status = r.get("reportApprovalStatus") or "pending"
    approval_pf = r.get("approvalPassFail") or "PENDING"
    approved_by = r.get("approvedBy") or "n/a"
    approved_at = str(r.get("approvedAt") or "")[:10] or "n/a"
    approval_remarks = r.get("approvalRemarks") or ""

    w = 56  # line width
    SEP = "=" * w
    sep = "-" * w

    is_validation = str(r.get("type") or "").strip().lower() == "validation"
    report_title = "    Validation Report" if is_validation else "       Test Report"
    lines = [
        SEP,
        "  ELECTROMAGNETIC SIEVE SHAKER".center(w),
        report_title.center(w),
        SEP,
        f"  Company        : {fs.get('companyName', 'n/a')}",
        f"  Instrument     : Sieve Shaker",
        sep,
        f"  Product Name   : {product}",
        f"  Batch No       : {batch}",
        f"  Test Date      : {date_str}    Time : {time_str}",
        f"  Tested By      : {tested_by}",
        f"  Status         : {status}",
        sep,
        "  TEST PARAMETERS",
        sep,
        f"  Shaker Mode    : {shaker_mode}",
        f"  Amplitude      : {amplitude}",
        f"  Duration       : {duration_str} (MM:SS)",
        f"  Weigh Method   : {weigh_method}",
    ]
    if recipe.get("shakerMode") == "INTERMITTENT" or td.get("shakerMode") == "INTERMITTENT":
        lines.append(f"  On Time        : {recipe.get('intermittentOnSeconds', td.get('intermittentOnSeconds','n/a'))} s")
        lines.append(f"  Off Time       : {recipe.get('intermittentOffSeconds', td.get('intermittentOffSeconds','n/a'))} s")
    if is_validation:
        val_type = recipe.get("validationType") or td.get("validationType") or "n/a"
        set_amp = td.get("setAmplitude") or amplitude
        actual_amp = td.get("actualAmplitude") or "not recorded"
        lines += [
            sep,
            "  VALIDATION PARAMETERS",
            sep,
            f"  Validation Type: {val_type}",
            f"  Set Amplitude  : {set_amp}",
            f"  Actual Amplitude: {actual_amp}",
        ]
    if not is_validation:
        lines += [
            sep,
            "  SAMPLE WEIGHTS",
            sep,
            f"  Sample Weight  : {sample_weight:.4f} g",
            f"  Final Weight   : {final_weight:.4f} g",
            sep,
            "  SIEVE ANALYSIS",
            sep,
            f"  {'Sieve':<6} {'Size (µm)':<12} {'Before (g)':<12} {'After (g)':<12} {'Frac (g)':<10} {'%':<6}",
            sep,
        ]
    if not is_validation:
        for i in range(num_sieves):
            size = sieve_sizes[i] if i < len(sieve_sizes) else "n/a"
            bw = float(before_weights[i]) if i < len(before_weights) else 0.0
            aw = float(after_weights[i]) if i < len(after_weights) else (float(sieve_weights[i]) if i < len(sieve_weights) else 0.0)
            frac = aw - bw if (bw or aw) else float(sieve_weights[i]) if i < len(sieve_weights) else 0.0
            pct = (frac / sample_weight * 100) if sample_weight > 0 else 0.0
            lines.append(f"  {str(i+1):<6} {str(size):<12} {bw:<12.4f} {aw:<12.4f} {frac:<10.4f} {pct:<6.2f}")
        pan_pct = (pan_weight / sample_weight * 100) if sample_weight > 0 else 0.0
        lines.append(f"  {'PAN':<6} {'Receiver':<12} {'--':<12} {pan_weight:<12.4f} {pan_weight:<10.4f} {pan_pct:<6.2f}")
    lines += [
        sep,
        "  APPROVAL",
        sep,
        f"  Result         : {approval_pf}",
        f"  Approved By    : {approved_by}",
        f"  Approved On    : {approved_at}",
    ]
    if approval_remarks:
        lines.append(f"  Remarks        : {approval_remarks}")
    lines.append(SEP)
    return "\n".join(lines)


def get_report_preview_data(report: Dict[str, Any]) -> Dict[str, Any]:
    report = enrich_report_context(dict(report or {}))
    td = report.get("testData") or report
    remarks = report.get("remarks")
    if remarks is None and isinstance(td, dict):
        remarks = td.get("remarks")
    preview = {
        "id": report.get("id"),
        "type": report.get("type", "test"),
        "createdAt": report.get("createdAt"),
        "completedAt": report.get("completedAt"),
        "recipe": report.get("recipe", {}),
        "factorySettings": report.get("factorySettings", {}),
        "testData": report.get("testData", report),
        "statistics": report.get("statistics")
        or (td.get("statistics") if isinstance(td, dict) else {})
        or compute_test_report_statistics(td if isinstance(td, dict) else None)
        or {},
        "status": report.get("status", "PASS"),
        "remarks": remarks,
        "approvedBy": report.get("approvedBy"),
        "approvedAt": report.get("approvedAt"),
        "reportApprovalStatus": report.get("reportApprovalStatus"),
        "approvalPassFail": report.get("approvalPassFail"),
        "approvalRemarks": report.get("approvalRemarks"),
        "abortCause": report.get("abortCause")
        or (td.get("abortCause") if isinstance(td, dict) else None),
        "operatedByUsername": report.get("operatedByUsername")
        or (td.get("operatedByUsername") if isinstance(td, dict) else None)
        or (td.get("employeeId") if isinstance(td, dict) else None),
        "operatorName": report.get("operatorName")
        or (td.get("operatorName") if isinstance(td, dict) else None),
        "employeeId": report.get("employeeId")
        or (td.get("employeeId") if isinstance(td, dict) else None),
        "reportDerived": report.get("reportDerived")
        or build_test_report_derived(
            td if isinstance(td, dict) else {},
            report.get("recipe") if isinstance(report.get("recipe"), dict) else {},
            report.get("id"),
        ),
    }
    if report.get("type") == "validation":
        preview["validationSubtype"] = report.get("validationSubtype")
        preview["usp"] = report.get("usp")
        preview["tapsMin"] = report.get("tapsMin")
        preview["dropHeight"] = report.get("dropHeight")
        preview["expectedTapCount"] = report.get("expectedTapCount")
        if preview["expectedTapCount"] in (None, ""):
            preview["expectedTapCount"] = report.get("expectedRotationCount")
        if preview["expectedTapCount"] in (None, "") and isinstance(td, dict):
            preview["expectedTapCount"] = td.get("expectedTapCount") or td.get("expectedRotationCount")
        preview["actualTapCount"] = report.get("actualTapCount")
        if preview["actualTapCount"] in (None, ""):
            preview["actualTapCount"] = report.get("actualRotationCount")
        if preview["actualTapCount"] in (None, "") and isinstance(td, dict):
            preview["actualTapCount"] = td.get("actualTapCount") or td.get("actualRotationCount")
        preview["expectedRotationCount"] = report.get("expectedRotationCount") or preview.get("expectedTapCount")
        preview["actualRotationCount"] = report.get("actualRotationCount") or preview.get("actualTapCount")
        preview["validationStartTime"] = report.get("validationStartTime") or report.get("testStartTime")
        if preview["validationStartTime"] in (None, "") and isinstance(td, dict):
            preview["validationStartTime"] = td.get("validationStartTime") or td.get("testStartTime")
        runs = report.get("validationRuns")
        if not runs and isinstance(td, dict):
            runs = td.get("validationRuns")
        if runs:
            preview["validationRuns"] = runs
    # For sieve shaker reports, generate dedicated text preview instead of the
    # generic friability/tap-density formatter.
    recipe_check = preview.get("recipe") or {}
    td_check = preview.get("testData") or {}
    is_sieve = bool(
        recipe_check.get("numSieves") or td_check.get("numSieves") or
        td_check.get("sieveSizes") or td_check.get("sieveWeights") or
        recipe_check.get("shakerMode") or td_check.get("shakerMode") or
        recipe_check.get("validationType") or td_check.get("validationType")
    )
    if is_sieve:
        try:
            preview["a4Text"] = _format_sieve_shaker_a4_text(report)
            preview["isSieveShaker"] = True
        except Exception:
            preview["a4Text"] = ""
        try:
            preview["htmlPreview"] = build_sieve_shaker_report_html(report)
        except Exception:
            preview["htmlPreview"] = ""
    else:
        try:
            import print_service
            preview["a4Text"] = print_service.format_for_a4_printer(
                report, include_printed_timestamp=False
            ).rstrip()
        except Exception:
            preview["a4Text"] = ""
    return preview


def _html_esc(value: Any) -> str:
    if value is None or value == "":
        return "N/A"
    return html_module.escape(str(value))


def _format_report_ts(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return "--"
    try:
        clean = s.replace("Z", "").strip()
        if "+" in clean:
            clean = clean.split("+", 1)[0].strip()
        if clean.count("-") > 2:
            clean = clean.rsplit("-", 1)[0].strip()
        dt = datetime.fromisoformat(clean)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return s


def _report_step_row_count(td: Dict[str, Any]) -> int:
    if not isinstance(td, dict):
        return 0
    results = td.get("stepResults") or []
    if isinstance(results, list) and results:
        return len(results)
    try:
        cs = int(td.get("completedSteps") or 0)
        return max(0, cs)
    except (TypeError, ValueError):
        return 0


def _statistics_table_html(preview: Dict[str, Any], td: Dict[str, Any]) -> str:
    if str(td.get("status") or "").strip().lower() == "aborted":
        return '<tr><td colspan="2">N/A</td></tr>'
    stats = preview.get("statistics") or td.get("statistics") or {}
    if not isinstance(stats, dict) or not stats:
        return '<tr><td colspan="2">N/A</td></tr>'
    rows = []
    for key, val in stats.items():
        if not isinstance(val, dict):
            continue
        display = _stat_display_value(val)
        if display is None:
            continue
        rows.append(
            "<tr><th>{}</th><td>{}</td></tr>".format(
                _html_esc(key), _html_esc(display)
            )
        )
    return "".join(rows) if rows else '<tr><td colspan="2">N/A</td></tr>'


def _validation_details_table_html(preview: Dict[str, Any]) -> str:
    td = preview.get("testData") if isinstance(preview.get("testData"), dict) else preview
    runs = preview.get("validationRuns")
    if not runs and isinstance(td, dict):
        runs = td.get("validationRuns")
    rows = []
    if isinstance(runs, list) and runs:
        for run in runs:
            if not isinstance(run, dict):
                continue
            usp = run.get("usp") or ("USP 2" if run.get("validationSubtype") == "load" else "USP 1")
            date_str = _format_report_ts(run.get("completedAt") or preview.get("completedAt") or preview.get("createdAt"))
            taps_min = run.get("tapsMin", "--")
            drop_h = run.get("dropHeight", "--")
            expected = run.get("expectedTapCount", "--")
            tol = run.get("expectedTolerance")
            expected_disp = (
                "{} (+/- {})".format(expected, tol)
                if tol is not None and expected not in (None, "", "--")
                else expected
            )
            actual = run.get("actualTapCount", "--")
            status = run.get("status", "--")
            rows.append('<tr><th colspan="4" class="usp-hdr">{} validation</th></tr>'.format(_html_esc(usp)))
            rows.append('<tr><th>Date / Time</th><td colspan="3">{}</td></tr>'.format(_html_esc(date_str)))
            rows.append(
                "<tr><th>USP</th><td>{}</td><th>Taps/Min</th><td>{}</td></tr>".format(
                    _html_esc(usp), _html_esc(taps_min)
                )
            )
            rows.append(
                "<tr><th>Drop Height (mm)</th><td>{}</td><th>Status</th><td>{}</td></tr>".format(
                    _html_esc(drop_h), _html_esc(status)
                )
            )
            rows.append(
                "<tr><th>Expected Tap Count</th><td>{}</td><th>Actual Tap Count</th><td>{}</td></tr>".format(
                    _html_esc(expected_disp), _html_esc(actual)
                )
            )
    elif isinstance(td, dict):
        date_str = _format_report_ts(td.get("completedAt") or preview.get("completedAt") or preview.get("createdAt"))
        usp = td.get("usp") or preview.get("usp") or "--"
        taps_min = td.get("tapsMin", preview.get("tapsMin", "--"))
        drop_h = td.get("dropHeight", preview.get("dropHeight", "--"))
        expected = td.get("expectedTapCount", preview.get("expectedTapCount", "--"))
        tol = td.get("expectedTolerance", preview.get("expectedTolerance"))
        expected_disp = (
            "{} (+/- {})".format(expected, tol)
            if tol is not None and expected not in (None, "", "--")
            else expected
        )
        actual = td.get("actualTapCount", preview.get("actualTapCount", "--"))
        status = td.get("status") or preview.get("status") or "--"
        rows.append('<tr><th>Date / Time</th><td colspan="3">{}</td></tr>'.format(_html_esc(date_str)))
        rows.append(
            "<tr><th>USP</th><td>{}</td><th>Taps/Min</th><td>{}</td></tr>".format(
                _html_esc(usp), _html_esc(taps_min)
            )
        )
        rows.append(
            "<tr><th>Drop Height (mm)</th><td>{}</td><th>Status</th><td>{}</td></tr>".format(
                _html_esc(drop_h), _html_esc(status)
            )
        )
        rows.append(
            "<tr><th>Expected Tap Count</th><td>{}</td><th>Actual Tap Count</th><td>{}</td></tr>".format(
                _html_esc(expected_disp), _html_esc(actual)
            )
        )
    return "".join(rows) if rows else '<tr><td colspan="4">No validation data</td></tr>'


def _derived_summary_html(derived: Dict[str, Any]) -> str:
    if not isinstance(derived, dict):
        return ""
    total_drops = derived.get("totalDrops")
    if total_drops is None:
        total_drops = derived.get("totalTaps")
    total_taps_str = str(total_drops) if total_drops is not None else "--"
    return (
        '<h3>TEST SUMMARY</h3>'
        '<table class="ident">'
        '<tr><th>Sample Weight (g)</th><td>{w}</td><th>Total No. of Drops</th><td>{drops}</td></tr>'
        '<tr><th>Initial Volume (V₀) (ml)</th><td>{v0}</td><th>Diff. of Last Two Volumes (ml)</th><td>{diff}</td></tr>'
        '</table>'
    ).format(
        w=_html_esc(_format_derived_number(derived.get("sampleWeightG"), 2)),
        drops=_html_esc(total_taps_str),
        v0=_html_esc(_format_derived_number(derived.get("initialVolumeMl"), 4)),
        diff=_html_esc(_format_derived_number(derived.get("diffLastTwoVolumesMl"), 4)),
    )


def _derived_test_result_html(derived: Dict[str, Any]) -> str:
    if not isinstance(derived, dict):
        return ""
    return (
        '<h3>TEST RESULT</h3>'
        '<table class="ident">'
        '<tr><th>Final Volume (Vf) (ml)</th><td>{vf}</td>'
        '<th>Initial Density (W/V₀) (g/mL)</th><td>{id}</td></tr>'
        '<tr><th>Tapped Density (W/Vf) (g/mL)</th><td>{td}</td>'
        '<th>Compressibility Index (%)</th><td>{ci}</td></tr>'
        '<tr><th>Hausner Ratio (V₀/Vf)</th><td colspan="3">{hr}</td></tr>'
        '</table>'
    ).format(
        vf=_html_esc(_format_derived_number(derived.get("finalVolumeMl"), 4)),
        id=_html_esc(_format_derived_number(derived.get("initialDensityGPerMl"), 3)),
        td=_html_esc(_format_derived_number(derived.get("tappedDensityGPerMl"), 3)),
        ci=_html_esc(_format_derived_number(derived.get("compressibilityIndexPct"), 2)),
        hr=_html_esc(_format_derived_number(derived.get("hausnerRatio"), 3)),
    )


_RLE_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 60" width="180" height="42">'
    '<rect width="260" height="60" rx="4" fill="#0f172a"/>'
    '<path d="M8 8h14v6H14v7h8v6H14v15H8V8z" fill="#f97316"/>'
    '<path d="M8 38h14v6H8z" fill="#f97316"/>'
    '<path d="M24 8h10c7 0 11 3.5 11 9.5S41 27 34 27h-4v15h-6V8zm6 14h4c3.5 0 5-1.8 5-4.5S37.5 13 34 13h-4v9z" fill="#3b82f6"/>'
    '<text x="56" y="26" font-family="Arial,sans-serif" font-size="14" font-weight="bold" fill="#3b82f6">RAISE</text>'
    '<text x="56" y="44" font-family="Arial,sans-serif" font-size="12" font-weight="bold" fill="#3b82f6">LAB EQUIPMENT</text>'
    '<text x="150" y="52" font-family="Arial,sans-serif" font-size="7" fill="#94a3b8" font-style="italic">Committed To Deliver The Best</text>'
    '</svg>'
)


def build_sieve_shaker_report_html(report: Dict[str, Any]) -> str:
    """Build a rich HTML A4 report for the Sieve Shaker.
    Handles both test reports (sieve table + bar chart) and validation reports."""
    r = dict(report or {})
    recipe = r.get("recipe") or {}
    fs = r.get("factorySettings") or {}
    td = r.get("testData") or r
    is_validation = str(r.get("type") or "").strip().lower() == "validation"

    esc = html_module.escape

    # ── Factory / instrument fields ──────────────────────────────────────────
    company      = esc(str(fs.get("companyName") or ""))
    model_no     = esc(str(fs.get("modelNo") or ""))
    serial_no    = esc(str(fs.get("serialNo") or ""))
    location     = esc(str(fs.get("companyLocation") or fs.get("location") or ""))
    inst_id      = esc(str(fs.get("instrumentId") or ""))
    last_val     = esc(str(fs.get("lastValidationDate") or ""))
    next_val     = esc(str(fs.get("nextValidationDate") or ""))

    # ── Report fields ─────────────────────────────────────────────────────────
    batch        = esc(str(recipe.get("batchNumber") or td.get("batchNumber") or "--"))
    product      = esc(str(recipe.get("productName") or td.get("productName") or "--"))
    created_at   = str(r.get("createdAt") or "")
    test_date    = created_at[:10] if len(created_at) >= 10 else "--"
    test_time    = created_at[11:19] if len(created_at) >= 19 else "--"
    tested_by    = esc(str(td.get("testedBy") or r.get("operatedByUsername") or r.get("testedBy") or "--"))
    status_raw   = str(td.get("status") or "")
    test_status  = esc(status_raw.title() if status_raw else "--")
    remarks      = esc(str(td.get("remarks") or r.get("remarks") or ""))

    amplitude_raw = recipe.get("amplitude") or td.get("amplitude")
    # Display amplitude as user-facing value (divide by 10 if stored as hardware units)
    try:
        amp_display = f"{float(amplitude_raw) / 10:.1f}" if amplitude_raw and float(amplitude_raw) >= 5 else str(amplitude_raw or "--")
    except Exception:
        amp_display = str(amplitude_raw or "--")

    duration_sec = int(recipe.get("durationSeconds") or td.get("durationSeconds") or 0)
    duration_str = f"{duration_sec // 60:02d}:{duration_sec % 60:02d}" if duration_sec else "--"
    elapsed_sec  = int(td.get("actualElapsedSeconds") or td.get("elapsedSeconds") or 0)
    elapsed_str  = f"{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}" if elapsed_sec else "--"
    shaker_mode  = esc(str(recipe.get("shakerMode") or td.get("shakerMode") or "--"))
    weigh_method = esc(str(td.get("weighMethod") or recipe.get("weighMethod") or "--").title())

    # Intermittent timing
    on_sec  = recipe.get("intermittentOnSeconds") or td.get("intermittentOnSeconds")
    off_sec = recipe.get("intermittentOffSeconds") or td.get("intermittentOffSeconds")

    # Logical mode
    run_time  = recipe.get("runTimeSeconds") or td.get("runTimeSeconds")
    wait_time = recipe.get("waitTimeSeconds") or td.get("waitTimeSeconds")
    cycles    = recipe.get("cycles") or td.get("cycles")

    # Test start/end timestamps
    ts_start = td.get("testStartTime") or r.get("createdAt") or ""
    ts_end   = td.get("testEndTime") or r.get("completedAt") or r.get("createdAt") or ""
    start_date = ts_start[:10] if len(ts_start) >= 10 else "--"
    start_time = ts_start[11:19] if len(ts_start) >= 19 else "--"
    end_date   = ts_end[:10] if len(ts_end) >= 10 else "--"
    end_time   = ts_end[11:19] if len(ts_end) >= 19 else "--"

    # Operator / tested-by fields
    operator_name    = esc(str(r.get("operatorName") or td.get("operatorName") or td.get("testedBy") or r.get("operatedByUsername") or "--"))
    operator_id      = esc(str(r.get("employeeId") or td.get("employeeId") or r.get("operatedByUsername") or "--"))

    # Approval
    approved_by      = esc(str(r.get("approvedBy") or "--"))
    approved_by_user = esc(str(r.get("approvedByUsername") or "--"))
    approved_at_raw  = str(r.get("approvedAt") or "")
    approved_date    = approved_at_raw[:10] if len(approved_at_raw) >= 10 else "--"
    approved_time    = approved_at_raw[11:19] if len(approved_at_raw) >= 19 else "--"
    approval_pf      = esc(str(r.get("approvalPassFail") or "PENDING"))
    approval_remarks = esc(str(r.get("approvalRemarks") or ""))

    # ── Test-specific: sieve weights ─────────────────────────────────────────
    num_sieves    = int(recipe.get("numSieves") or td.get("numSieves") or 0)
    sieve_sizes   = recipe.get("sieveSizes") or td.get("sieveSizes") or []
    before_weights = [float(x) for x in (td.get("beforeWeights") or [])]
    after_weights  = [float(x) for x in (td.get("afterWeights") or [])]
    sieve_weights  = [float(x) for x in (td.get("sieveWeights") or [])]
    pan_weight     = float(td.get("panWeight") or 0)
    initial_weight = float(td.get("initialWeight") or recipe.get("initialWeight") or 0)
    final_weight   = float(td.get("finalWeight") or 0)

    # Compute fractions: prefer explicit sieve_weights, otherwise after - before
    fractions = []
    for i in range(num_sieves):
        if i < len(sieve_weights) and sieve_weights[i]:
            fractions.append(sieve_weights[i])
        elif i < len(after_weights) and i < len(before_weights):
            fractions.append(max(0.0, after_weights[i] - before_weights[i]))
        elif i < len(after_weights):
            fractions.append(after_weights[i])
        else:
            fractions.append(0.0)

    total_fraction = sum(fractions) + pan_weight

    # ── Validation-specific ──────────────────────────────────────────────────
    val_type    = esc(str(recipe.get("validationType") or td.get("validationType") or "--").title())
    set_amp     = esc(str(td.get("setAmplitude") or amplitude_raw or "--"))
    actual_amp  = esc(str(td.get("actualAmplitude") or "--"))

    # ── Bar chart SVG (greyscale, test reports only) ──────────────────────────
    bar_html = ""
    if not is_validation and num_sieves > 0:
        bar_values = fractions + [pan_weight]
        bar_labels = [str(i + 1) for i in range(num_sieves)] + ["PAN"]
        max_val    = max(bar_values) if any(v > 0 for v in bar_values) else 1.0
        if max_val == 0:
            max_val = 1.0
        bw = 38; bg = 10; ch = 200; pad_l = 50; pad_r = 20; pad_t = 20; pad_b = 30
        cw = pad_l + (bw + bg) * len(bar_values) + pad_r
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cw} {ch}" width="100%" style="max-height:220px;border:1px solid #aaa;background:#fff;">'
        # Y-axis gridlines and labels
        for tick_pct in range(0, 101, 20):
            tick_val = max_val * tick_pct / 100
            y = pad_t + (ch - pad_t - pad_b) * (1 - tick_pct / 100)
            svg += f'<line x1="{pad_l}" y1="{y:.1f}" x2="{cw - pad_r}" y2="{y:.1f}" stroke="#ddd" stroke-width="0.8"/>'
            svg += f'<text x="{pad_l - 4}" y="{y + 3:.1f}" text-anchor="end" font-size="8" fill="#444">{tick_val:.2f}</text>'
        # Y-axis label
        svg += f'<text x="10" y="{ch//2}" text-anchor="middle" font-size="9" fill="#333" transform="rotate(-90,10,{ch//2})">Weight (g)</text>'
        # Bars
        greys = ["#111","#333","#555","#666","#777","#888","#999","#aaa","#444"]
        for idx, (val, lbl) in enumerate(zip(bar_values, bar_labels)):
            h = (val / max_val) * (ch - pad_t - pad_b)
            x = pad_l + idx * (bw + bg)
            y = pad_t + (ch - pad_t - pad_b) - h
            color = greys[idx % len(greys)]
            svg += f'<rect x="{x}" y="{y:.1f}" width="{bw}" height="{h:.1f}" fill="{color}"/>'
            pct = (val / initial_weight * 100) if initial_weight > 0 else 0
            svg += f'<text x="{x + bw/2:.1f}" y="{y - 3:.1f}" text-anchor="middle" font-size="8" fill="#000">{pct:.1f}%</text>'
            svg += f'<text x="{x + bw/2:.1f}" y="{ch - pad_b + 14}" text-anchor="middle" font-size="9" fill="#000">{lbl}</text>'
        svg += '</svg>'
        bar_html = f'''
<h3>Particle Size Distribution — Fraction per Sieve (g)</h3>
<div class="chart-section">{svg}</div>'''

    # ── Sieve table rows ──────────────────────────────────────────────────────
    sieve_table_html = ""
    if not is_validation:
        rows = ""
        for i in range(num_sieves):
            size   = sieve_sizes[i] if i < len(sieve_sizes) else "--"
            bw_val = before_weights[i] if i < len(before_weights) else 0.0
            aw_val = after_weights[i]  if i < len(after_weights)  else 0.0
            frac   = fractions[i] if i < len(fractions) else 0.0
            pct    = (frac / initial_weight * 100) if initial_weight > 0 else 0.0
            rows  += f"<tr><td>{i+1}</td><td>{size} µm</td><td>{bw_val:.4f}</td><td>{aw_val:.4f}</td><td>{frac:.4f}</td><td>{pct:.2f}%</td></tr>\n"
        # PAN row
        pan_before = before_weights[num_sieves] if num_sieves < len(before_weights) else 0.0
        pan_after  = after_weights[num_sieves]  if num_sieves < len(after_weights)  else pan_weight
        pan_pct    = (pan_weight / initial_weight * 100) if initial_weight > 0 else 0.0
        rows += f"<tr><td>PAN</td><td>Receiver</td><td>{pan_before:.4f}</td><td>{pan_after:.4f}</td><td>{pan_weight:.4f}</td><td>{pan_pct:.2f}%</td></tr>\n"
        total_pct  = (total_fraction / initial_weight * 100) if initial_weight > 0 else 0.0
        rows += f'<tr style="font-weight:bold;background:#f0f0f0;"><td colspan="4">Total</td><td>{total_fraction:.4f}</td><td>{total_pct:.2f}%</td></tr>\n'
        sieve_table_html = f'''
<h3>Sieve Analysis Data</h3>
<table>
<thead><tr><th>Sieve No</th><th>Mesh Size</th><th>Before (g)</th><th>After (g)</th><th>Fraction (g)</th><th>Fraction (%)</th></tr></thead>
<tbody>{rows}</tbody>
</table>'''

    # ── Mode-specific extra params ────────────────────────────────────────────
    mode_extra = ""
    mode_upper = str(recipe.get("shakerMode") or td.get("shakerMode") or "").upper()
    if mode_upper == "INTERMITTENT" and (on_sec or off_sec):
        mode_extra = f'<tr><td class="lbl">On Time:</td><td>{on_sec} sec</td><td class="lbl">Off Time:</td><td>{off_sec} sec</td></tr>\n'
    elif mode_upper == "LOGICAL" and (run_time or wait_time):
        mode_extra = (
            f'<tr><td class="lbl">Run Time:</td><td>{run_time} sec</td>'
            f'<td class="lbl">Wait Time:</td><td>{wait_time} sec</td></tr>\n'
            f'<tr><td class="lbl">Cycles:</td><td>{cycles or "--"}</td><td></td><td></td></tr>\n'
        )

    # ── Validation section ────────────────────────────────────────────────────
    validation_section = ""
    if is_validation:
        validation_section = f'''
<h3>Validation Parameters</h3>
<table class="info-table">
<tr><td class="lbl">Validation Type:</td><td>{val_type}</td><td class="lbl">Set Amplitude:</td><td>{set_amp}</td></tr>
<tr><td class="lbl">Actual Amplitude:</td><td>{actual_amp}</td><td class="lbl">Test Duration:</td><td>{duration_str} (mm:ss)</td></tr>
<tr><td class="lbl">Elapsed Time:</td><td>{elapsed_str} (mm:ss)</td><td class="lbl">Vibration Mode:</td><td>{shaker_mode}</td></tr>
<tr><td class="lbl">Test Status:</td><td>{test_status}</td><td class="lbl">Remarks:</td><td>{remarks}</td></tr>
</table>'''

    # ── Test data section (test reports only) ─────────────────────────────────
    # Final weight = total powder recovered (sum of fractions + pan) for mass balance
    final_weight_display = total_fraction if total_fraction > 0 else final_weight
    test_data_section = ""
    if not is_validation:
        test_data_section = f'''
<h3>Test Data</h3>
<table class="info-table">
<tr><td class="lbl">Initial Sample Weight (g):</td><td>{initial_weight:.4f}</td><td class="lbl">Final Weight Recovered (g):</td><td>{final_weight_display:.4f}</td></tr>
<tr><td class="lbl">Total Fraction (g):</td><td>{total_fraction:.4f}</td><td class="lbl">Weigh Method:</td><td>{weigh_method}</td></tr>
</table>'''

    report_type_label = "Validation Report" if is_validation else "Test Report"

    html = f'''<!doctype html>
<html><head><meta charset="utf-8">
<title>Sieve Shaker {report_type_label}</title>
<style>
@page{{size:A4 portrait;margin:12mm 10mm;}}
body{{margin:0;padding:0;color:#000;background:#fff;font-family:Arial,sans-serif;font-size:11pt;max-width:100%;}}
.report-header{{display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid #000;padding-bottom:6px;margin-bottom:8px;}}
.report-title{{font-size:13pt;font-weight:bold;text-align:center;flex:1;line-height:1.3;}}
.report-subtitle{{font-size:9pt;font-weight:normal;display:block;color:#333;}}
h3{{text-align:center;margin:10px 0 4px;font-size:11.5pt;background:#d0d0d0;padding:5px 8px;border-top:3px solid #444;border-bottom:1px solid #888;}}
table{{border-collapse:collapse;width:100%;margin:3px 0;}}
th,td{{border:1px solid #666;padding:3px 6px;font-size:9pt;}}
th{{background:#e0e0e0;font-weight:bold;text-align:center;}}
td{{text-align:left;}}
.info-table .lbl{{font-weight:bold;width:20%;background:#f5f5f5;}}
.chart-section{{margin:8px 0;text-align:center;page-break-inside:avoid;}}
.pass{{color:#006600;font-weight:bold;}}
.fail{{color:#cc0000;font-weight:bold;}}
.pending{{color:#555;}}
.footer-approval{{margin-top:14px;border:1px solid #000;padding:6px 8px;}}
.footer-approval table td{{border:none;padding:2px 8px;font-size:9pt;}}
.two-col td{{width:50%;}}
</style>
</head><body>

<div class="report-header">
  <div class="report-title">
    Sieve Shaker
    <span class="report-subtitle">{report_type_label}</span>
  </div>
</div>

<h3>Instrument &amp; Company Information</h3>
<table class="info-table">
<tr><td class="lbl">Company:</td><td>{company}</td><td class="lbl">Model No:</td><td>{model_no}</td></tr>
<tr><td class="lbl">Serial No:</td><td>{serial_no}</td><td class="lbl">Location:</td><td>{location}</td></tr>
<tr><td class="lbl">Instrument ID:</td><td>{inst_id}</td><td class="lbl">Last Validation:</td><td>{last_val}</td></tr>
<tr><td class="lbl">Next Validation:</td><td>{next_val}</td><td class="lbl"></td><td></td></tr>
</table>

<h3>{'Validation' if is_validation else 'Test'} Information</h3>
<table class="info-table">
<tr><td class="lbl">Product Name:</td><td>{product}</td><td class="lbl">Batch No:</td><td>{batch}</td></tr>
<tr><td class="lbl">Test Date:</td><td>{test_date.replace("-", "/")}</td><td class="lbl">Test Time:</td><td>{test_time}</td></tr>
<tr><td class="lbl">Start Date:</td><td>{start_date.replace("-", "/")}</td><td class="lbl">Start Time:</td><td>{start_time}</td></tr>
<tr><td class="lbl">End Date:</td><td>{end_date.replace("-", "/")}</td><td class="lbl">End Time:</td><td>{end_time}</td></tr>
<tr><td class="lbl">Operator Name:</td><td>{operator_name}</td><td class="lbl">Operator ID:</td><td>{operator_id}</td></tr>
<tr><td class="lbl">Tested By:</td><td>{tested_by}</td><td class="lbl">Status:</td><td>{test_status}</td></tr>
</table>

<h3>Test Parameters</h3>
<table class="info-table">
<tr><td class="lbl">Vibration Mode:</td><td>{shaker_mode}</td><td class="lbl">Set Amplitude:</td><td>{amp_display}</td></tr>
<tr><td class="lbl">Set Duration:</td><td>{duration_str} (mm:ss)</td><td class="lbl">Elapsed Time:</td><td>{elapsed_str} (mm:ss)</td></tr>
<tr><td class="lbl">No. of Sieves:</td><td>{num_sieves}</td><td class="lbl">Weigh Method:</td><td>{weigh_method}</td></tr>
{mode_extra}
</table>
{validation_section}
{test_data_section}
{sieve_table_html}
{bar_html}

<div class="footer-approval">
<strong>Approval / Sign-off</strong>
<table>
<tr>
  <td><b>Result:</b> <span class="{'pass' if approval_pf == 'PASS' else 'fail' if approval_pf == 'FAIL' else 'pending'}">{approval_pf}</span></td>
  <td><b>Approved By:</b> {approved_by}</td>
  <td><b>Approver ID:</b> {approved_by_user}</td>
</tr>
<tr>
  <td><b>Approval Date:</b> {approved_date.replace("-", "/")}</td>
  <td><b>Approval Time:</b> {approved_time}</td>
  <td></td>
</tr>
{f'<tr><td colspan="3"><b>Remarks:</b> {approval_remarks}</td></tr>' if approval_remarks else ''}
</table>
</div>

</body></html>'''
    return html


def build_report_pdf_html(
    report: Dict[str, Any],
    *,
    include_printed_timestamp: bool = False,
    timestamp_kind: str = "printed",
) -> str:
    """
    Build PDF HTML from the A4 text formatter output (====, ----, ****).
    For sieve shaker reports (those with numSieves), uses the rich HTML template.
    """
    r = report or {}
    recipe = r.get("recipe") or {}
    td = r.get("testData") or r
    if (recipe.get("numSieves") or td.get("numSieves") or
            td.get("sieveSizes") or td.get("sieveWeights") or
            recipe.get("shakerMode") or td.get("shakerMode") or
            recipe.get("validationType") or td.get("validationType")):
        return build_sieve_shaker_report_html(r)

    import print_service

    enriched = enrich_report_context(dict(report or {}))
    a4_text = print_service.format_for_a4_printer(
        enriched,
        include_printed_timestamp=include_printed_timestamp,
        timestamp_kind=timestamp_kind,
    ).rstrip()
    escaped = html_module.escape(a4_text)

    css = (
        "@page{size:A4 portrait;margin:10mm;}"
        "body{margin:0;padding:3mm 0;color:#000;background:#fff;"
        "font-family:'Courier New',Courier,monospace;font-size:11pt;line-height:1.25;"
        "text-align:center;box-sizing:border-box;"
        "-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
        ".a4-sheet{display:inline-block;width:190mm;max-width:190mm;text-align:left;vertical-align:top;}"
        "pre{margin:0;white-space:pre-wrap;tab-size:4;letter-spacing:0;font-size:inherit;line-height:inherit;}"
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>Report</title>'
        '<style>{}</style></head><body><div class="a4-sheet"><pre>{}</pre></div></body></html>'
    ).format(css, escaped)


def create_pdf_report(report_data: Dict[str, Any], template_type: str = "standard") -> Optional[pathlib.Path]:
    try:
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        recipe_name = report_data.get("recipe", {}).get("productName", "report")
        safe_name = "".join(c for c in recipe_name if c.isalnum() or c in "-_")
        filename = f"{safe_name}_{timestamp}.json"
        pdf_path = _reports_dir / filename
        with open(pdf_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        return pdf_path
    except Exception:
        return None


def export_reports_to_usb(report_ids: List[int], export_path: str) -> Dict[str, Any]:
    try:
        export_dir = pathlib.Path(export_path)
        export_dir.mkdir(parents=True, exist_ok=True)
        exported_files = []
        for report_id in report_ids:
            report = data_service.get_report(report_id)
            if not report:
                continue
            timestamp = report.get("createdAt", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
            safe_ts = "".join(c for c in str(timestamp) if c.isalnum() or c in "-_.T")
            recipe_name = report.get("recipe", {}).get("productName", "report")
            safe_name = "".join(c for c in recipe_name if c.isalnum() or c in "-_")
            filename = f"{safe_name}_{report_id}_{safe_ts}.json"
            export_file = export_dir / filename
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            exported_files.append(str(export_file))
        return {"success": True, "exported_files": exported_files, "count": len(exported_files)}
    except Exception as e:
        return {"success": False, "error": str(e)}
