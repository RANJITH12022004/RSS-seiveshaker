#!/usr/bin/env python3
"""
calculation_service.py - Sieve Shaker CFR recipe validation and form processing.
"""

from datetime import datetime
from typing import Dict, Any, List


def init():
    pass


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

    if shaker_mode == "INTERMITTENT":
        try:
            _parse_positive_int(recipe_data.get("intermittentOnSeconds"), "On time")
        except ValueError as e:
            errors.append(str(e))
        try:
            _parse_positive_int(recipe_data.get("intermittentOffSeconds"), "Off time")
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
    for key in ("durationSeconds", "intermittentOnSeconds", "intermittentOffSeconds"):
        if recipe.get(key) is not None:
            recipe[key] = int(recipe[key])
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
