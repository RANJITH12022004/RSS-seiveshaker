#!/usr/bin/env python3
"""
calculation_service.py - Sieve Shaker CFR recipe validation and form processing.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional


def init():
    pass


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def compute_sieve_analysis(
    test_data: Optional[Dict[str, Any]] = None,
    recipe: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Sieve analysis retained mass = after tare weight - before tare weight.

    Percentages are of the initial sample weight so retained bars sum toward 100%
    when mass balance is complete (sieves + pan == sample).
    """
    td = test_data if isinstance(test_data, dict) else {}
    recipe = recipe if isinstance(recipe, dict) else {}

    try:
        num_sieves = int(recipe.get("numSieves") or td.get("numSieves") or 0)
    except (TypeError, ValueError):
        num_sieves = 0
    num_sieves = max(0, num_sieves)

    sieve_sizes = list(recipe.get("sieveSizes") or td.get("sieveSizes") or [])
    before_weights = list(td.get("beforeWeights") or [])
    after_weights = list(td.get("afterWeights") or [])
    sieve_weights = list(td.get("sieveWeights") or [])
    sample_weight = _safe_float(td.get("initialWeight") or recipe.get("initialWeight") or 0.0)
    stored_pan = _safe_float(td.get("panWeight") or 0.0)

    rows: List[Dict[str, Any]] = []
    fracs: List[float] = []
    labels: List[str] = []

    for i in range(num_sieves):
        bw = _safe_float(before_weights[i] if i < len(before_weights) else 0.0)
        if i < len(after_weights):
            aw = _safe_float(after_weights[i])
            retained = aw - bw
            has_pair = True
        elif i < len(sieve_weights):
            aw = bw + _safe_float(sieve_weights[i])
            retained = _safe_float(sieve_weights[i])
            has_pair = False
        else:
            aw = 0.0
            retained = 0.0
            has_pair = False
        retained = max(0.0, retained)
        pct = (retained / sample_weight * 100.0) if sample_weight > 0 else 0.0
        size = sieve_sizes[i] if i < len(sieve_sizes) else ""
        label = f"C{i + 1}"
        rows.append({
            "index": i + 1,
            "label": label,
            "size": size,
            "before": bw,
            "after": aw,
            "retained": retained,
            "percent": pct,
            "isPan": False,
            "hasBeforeAfter": has_pair,
        })
        fracs.append(retained)
        labels.append(label)

    pan_before = _safe_float(before_weights[num_sieves] if len(before_weights) > num_sieves else 0.0)
    if len(after_weights) > num_sieves:
        pan_after = _safe_float(after_weights[num_sieves])
        pan_retained = max(0.0, pan_after - pan_before)
        pan_has_pair = True
    else:
        # panWeight is stored as retained fraction by the weigh wizard.
        pan_retained = max(0.0, stored_pan)
        pan_after = pan_before + pan_retained if pan_before or pan_retained else stored_pan
        pan_has_pair = False
    pan_pct = (pan_retained / sample_weight * 100.0) if sample_weight > 0 else 0.0
    rows.append({
        "index": num_sieves + 1,
        "label": "Pan",
        "size": "Receiver",
        "before": pan_before,
        "after": pan_after,
        "retained": pan_retained,
        "percent": pan_pct,
        "isPan": True,
        "hasBeforeAfter": pan_has_pair,
    })
    fracs.append(pan_retained)
    labels.append("Pan")

    total_retained = sum(fracs)
    total_pct = (total_retained / sample_weight * 100.0) if sample_weight > 0 else 0.0

    return {
        "numSieves": num_sieves,
        "sampleWeight": sample_weight,
        "rows": rows,
        "fractions": fracs,
        "labels": labels,
        "totalRetained": total_retained,
        "totalPercent": total_pct,
    }


def _parse_positive_int(val, field_name: str, min_val: int = 1) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}")
    if n < min_val:
        raise ValueError(f"{field_name} must be at least {min_val}")
    return n


def _validate_logical_segments(segments: List[Dict[str, Any]]) -> List[str]:
    errors = []
    if not segments:
        errors.append("At least one logical segment is required")
        return errors
    has_run = False
    for i, seg in enumerate(segments):
        seg_type = str(seg.get("type") or "").strip().lower()
        if seg_type not in ("run", "wait"):
            errors.append(f"Segment {i + 1}: type must be run or wait")
            continue
        if seg_type == "run":
            has_run = True
        try:
            _parse_positive_int(seg.get("durationSeconds"), f"Segment {i + 1} duration")
        except ValueError as e:
            errors.append(str(e))
    if not has_run:
        errors.append("Logical program must include at least one run segment")
    return errors


def validate_recipe(recipe_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate sieve shaker recipe.
    Required: productName, shakerMode, amplitude (5-30).
    """
    errors = []
    name = (recipe_data.get("productName") or recipe_data.get("name") or "").strip()
    if not name:
        errors.append("Product name is required")

    shaker_mode = str(recipe_data.get("shakerMode") or "").strip().upper()
    if shaker_mode not in ("CONTINUOUS", "INTERMITTENT", "LOGICAL"):
        errors.append("Shaker mode must be Continuous, Intermittent, or Logical")

    try:
        amp = int(recipe_data.get("amplitude"))
        if amp < 5 or amp > 30:
            errors.append("Amplitude must be between 5 and 30")
    except (TypeError, ValueError):
        errors.append("Amplitude is required (5-30)")

    if shaker_mode in ("CONTINUOUS", "INTERMITTENT"):
        try:
            _parse_positive_int(recipe_data.get("durationSeconds"), "Duration")
        except ValueError as e:
            errors.append(str(e))

    if shaker_mode == "LOGICAL":
        segments = recipe_data.get("logicalSegments") or []
        errors.extend(_validate_logical_segments(segments))

    if errors:
        return {"valid": False, "error": "; ".join(errors)}
    return {"valid": True}


def process_recipe_form_data(form_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize recipe form data for storage."""
    recipe = dict(form_data)
    recipe["shakerMode"] = str(recipe.get("shakerMode") or "CONTINUOUS").strip().upper()
    if recipe.get("amplitude") is not None:
        recipe["amplitude"] = int(recipe["amplitude"])
    for key in ("durationSeconds", "intermittentOnSeconds", "intermittentOffSeconds", "numSieves"):
        if recipe.get(key) is not None:
            try:
                recipe[key] = int(recipe[key])
            except (TypeError, ValueError):
                pass
    if "sieveAnalysis" in recipe:
        sa = recipe.get("sieveAnalysis")
        if isinstance(sa, bool):
            recipe["sieveAnalysis"] = sa
        elif isinstance(sa, (int, float)):
            recipe["sieveAnalysis"] = bool(sa)
        else:
            recipe["sieveAnalysis"] = str(sa).strip().lower() not in ("0", "false", "off", "no")
    else:
        recipe["sieveAnalysis"] = True
    if recipe.get("logicalSegments"):
        normalized = []
        for seg in recipe["logicalSegments"]:
            normalized.append({
                "type": str(seg.get("type") or "run").strip().lower(),
                "durationSeconds": int(seg.get("durationSeconds") or 0),
            })
        recipe["logicalSegments"] = normalized
    if "createdAt" not in recipe:
        recipe["createdAt"] = datetime.utcnow().isoformat() + "Z"
    if "lastUsed" not in recipe:
        recipe["lastUsed"] = recipe.get("createdAt", "")
    return recipe
