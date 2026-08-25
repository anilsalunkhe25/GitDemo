"""Synthetic historical demand dataset generator.

Produces backend/ml/dataset.csv with realistic relationships between
emergency characteristics and future resource requirements.

NOTE: this is SYNTHETIC DEMO DATA generated for the academic project.
It must never be treated as real disaster-response data.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_ROWS = 800
RANDOM_SEED = 42

EMERGENCY_TYPES = ["FLOOD", "EARTHQUAKE", "CYCLONE", "LANDSLIDE", "DROUGHT", "FIRE", "EPIDEMIC"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RESOURCE_CATEGORIES = [
    "FOOD", "WATER", "MEDICINE", "BLANKETS", "HYGIENE_KITS",
    "BABY_SUPPLIES", "CLOTHING", "FIRST_AID_KITS",
]

TYPE_MULTIPLIER = {
    "FLOOD": 1.15, "EARTHQUAKE": 1.30, "CYCLONE": 1.20, "LANDSLIDE": 1.05,
    "DROUGHT": 0.95, "FIRE": 1.00, "EPIDEMIC": 0.90,
}
SEVERITY_MULTIPLIER = {"LOW": 1.00, "MEDIUM": 1.20, "HIGH": 1.45, "CRITICAL": 1.75}

PER_CAPITA_DAILY = {
    "FOOD": 0.6, "WATER": 3.0, "MEDICINE": 0.01, "BLANKETS": 0.02,
    "HYGIENE_KITS": 0.01, "BABY_SUPPLIES": 0.005, "CLOTHING": 0.01,
    "FIRST_AID_KITS": 0.004,
}


def generate(rows: int = DEFAULT_ROWS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    emergency_type = rng.choice(EMERGENCY_TYPES, rows, p=[0.24, 0.14, 0.16, 0.10, 0.12, 0.10, 0.14])
    severity = rng.choice(SEVERITIES, rows, p=[0.15, 0.35, 0.32, 0.18])
    resource_type = rng.choice(RESOURCE_CATEGORIES, rows)

    population = rng.integers(150, 20001, rows).astype(float)
    duration = rng.integers(5, 46, rows).astype(float)
    days_since = np.round(rng.uniform(0, 0.85, rows) * duration).clip(0)

    sev_mult = np.array([SEVERITY_MULTIPLIER[s] for s in severity])
    type_mult = np.array([TYPE_MULTIPLIER[t] for t in emergency_type])
    res_mult = np.array([PER_CAPITA_DAILY[r] for r in resource_type])

    daily_consumption = population * res_mult * sev_mult * rng.uniform(0.85, 1.25, rows)
    daily_consumption = np.round(daily_consumption, 2)

    previous_demand = np.round(
        daily_consumption * np.maximum(days_since, 1) * rng.uniform(0.7, 1.3, rows), 1
    )

    remaining_days = np.maximum(duration - days_since, 1)
    future_requirement = np.round(
        daily_consumption * remaining_days * type_mult
        * rng.normal(1.02, 0.08, rows).clip(0.8, 1.3), 1
    ).clip(min=1)

    # Current inventory typically covers 40-110% of what will be needed
    current_inventory = np.round(future_requirement * rng.uniform(0.4, 1.1, rows)).astype(int)

    df = pd.DataFrame({
        "emergency_type": emergency_type,
        "emergency_severity": severity,
        "population_affected": population.astype(int),
        "emergency_duration": duration.astype(int),
        "resource_type": resource_type,
        "daily_consumption": daily_consumption,
        "days_since_emergency": days_since.astype(int),
        "previous_demand": previous_demand,
        "current_inventory": current_inventory,
        "future_requirement": future_requirement,
    })
    return df.sample(frac=1.0, random_state=seed).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic demand dataset")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--out", type=str,
                        default=str(Path(__file__).resolve().parent / "dataset.csv"))
    args = parser.parse_args()
    df = generate(args.rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} synthetic records to {args.out}")


if __name__ == "__main__":
    main()
