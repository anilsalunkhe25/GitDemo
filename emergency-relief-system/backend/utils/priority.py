"""Transparent priority scoring engine.

priority_score = severity*0.30 + population*0.25 + shortage*0.20
                 + urgency*0.15 + time_criticality*0.10

Every sub-score is normalized to 0-100 and returned with a human-readable
reason so the score is fully explainable (business rules 3 and 5).
"""
from datetime import date

from .constants import PRIORITY_LEVELS, PRIORITY_WEIGHTS

SEVERITY_SCORES = {"LOW": 20, "MEDIUM": 50, "HIGH": 75, "CRITICAL": 95}
URGENCY_SCORES = {"LOW": 25, "MEDIUM": 55, "HIGH": 80, "CRITICAL": 95}


def _severity_component(emergency_severity: str) -> tuple[int, str]:
    score = SEVERITY_SCORES.get(emergency_severity, 50)
    return score, f"Emergency severity is {emergency_severity}"


def _population_component(population_affected: int | None) -> tuple[float, str]:
    population = max(int(population_affected or 0), 0)
    if population <= 0:
        return 0.0, "No affected population recorded for the area"
    # Logarithmic scale: 100 people -> ~20, 1k -> ~40, 10k -> ~60, 50k+ -> ~75+
    import math

    score = min(100.0, math.log10(population) / math.log10(100000) * 100)
    return round(score, 1), f"{population:,} people are affected in this area"


def _shortage_component(quantity_requested: int, total_available: int | None) -> tuple[float, str]:
    if total_available is None:
        return 50.0, "Stock position unknown; neutral shortage score applied"
    if quantity_requested <= 0:
        return 0.0, "No quantity requested"
    if total_available <= 0:
        return 100.0, "No stock available anywhere in the system"
    ratio = quantity_requested / (quantity_requested + total_available)
    score = round(min(100.0, ratio * 100), 1)
    reason = (
        f"Requested {quantity_requested} vs {total_available} in stock "
        f"({score:.0f}% gap)"
    )
    return score, reason


def _time_component(required_by: date) -> tuple[float, str]:
    days_left = (required_by - date.today()).days
    if days_left < 0:
        return 100.0, "Required-by date has already passed"
    if days_left == 0:
        return 95.0, "Needed today"
    if days_left <= 1:
        return 85.0, f"Due within {days_left} day"
    if days_left <= 3:
        return 70.0, f"Due within {days_left} days"
    if days_left <= 7:
        return 50.0, f"Due within a week ({days_left} days)"
    if days_left <= 14:
        return 30.0, f"Due in {days_left} days"
    return 15.0, f"Due in {days_left} days"


def calculate_priority(
    emergency_severity: str,
    population_affected: int | None,
    quantity_requested: int,
    total_available_stock: int | None,
    urgency: str,
    required_by,
) -> dict:
    """Return {'score': float 0-100, 'level': LOW/MEDIUM/HIGH/CRITICAL, 'breakdown': [...]}"""
    components = {
        "severity": _severity_component(emergency_severity),
        "population": _population_component(population_affected),
        "shortage": _shortage_component(quantity_requested, total_available_stock),
        "urgency": (
            URGENCY_SCORES.get(urgency, 55),
            f"Request urgency is {urgency}",
        ),
        "time_criticality": _time_component(required_by),
    }

    breakdown = []
    total = 0.0
    for name, weight_key in [
        ("severity", "severity"),
        ("population", "population"),
        ("shortage", "shortage"),
        ("urgency", "urgency"),
        ("time_criticality", "time_criticality"),
    ]:
        weight = PRIORITY_WEIGHTS[weight_key]
        raw_score, reason = components[name]
        weighted = round(raw_score * weight, 2)
        total += weighted
        breakdown.append({
            "factor": weight_key,
            "weight": weight,
            "raw_score": raw_score,
            "weighted_score": weighted,
            "reason": reason,
        })

    score = round(min(max(total, 0.0), 100.0), 1)
    level = priority_level(score)
    return {"score": score, "level": level, "breakdown": breakdown}


def priority_level(score: float) -> str:
    for level, (low, high) in PRIORITY_LEVELS.items():
        if low <= score <= high:
            return level
    return "CRITICAL" if score > 100 else "LOW"
