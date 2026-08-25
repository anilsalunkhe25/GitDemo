"""Feature definitions and deterministic encoding shared by training and inference."""
from __future__ import annotations

import numpy as np
import pandas as pd

TARGET = "future_requirement"

NUMERIC_FEATURES = [
    "population_affected",
    "emergency_duration",
    "emergency_severity_encoded",
    "resource_type_encoded",
    "daily_consumption",
    "days_since_emergency",
    "previous_demand",
]

FEATURES = NUMERIC_FEATURES  # current_inventory is context, not a model input

SEVERITY_ENCODED = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

RESOURCE_TYPE_ENCODED = {
    "FOOD": 1,
    "WATER": 2,
    "MEDICINE": 3,
    "BLANKETS": 4,
    "HYGIENE_KITS": 5,
    "BABY_SUPPLIES": 6,
    "CLOTHING": 7,
    "FIRST_AID_KITS": 8,
    "OTHER": 9,
}

REQUIRED_RAW_COLUMNS = [
    "emergency_type", "emergency_severity", "population_affected",
    "emergency_duration", "resource_type", "daily_consumption",
    "days_since_emergency", "previous_demand", "current_inventory",
    TARGET,
]


def load_dataset(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Handle missing values and clip implausible values before encoding."""
    df = df.copy()
    df = df.dropna(subset=[TARGET])
    numeric_present = [c for c in NUMERIC_FEATURES if c in df.columns]
    df[numeric_present] = df[numeric_present].fillna(df[numeric_present].median())
    df["emergency_severity"] = df["emergency_severity"].fillna("MEDIUM")
    df["emergency_type"] = df["emergency_type"].fillna("OTHER")
    df["resource_type"] = df["resource_type"].fillna("OTHER")
    df["population_affected"] = pd.to_numeric(df["population_affected"], errors="coerce").clip(lower=0)
    df[TARGET] = pd.to_numeric(df[TARGET], errors="coerce").clip(lower=0)
    return df


def encode_features(df: pd.DataFrame) -> pd.DataFrame:
    """Map categorical fields to their stable integer encodings."""
    X = pd.DataFrame(index=df.index)
    X["population_affected"] = pd.to_numeric(df["population_affected"], errors="coerce")
    X["emergency_duration"] = pd.to_numeric(df["emergency_duration"], errors="coerce")
    X["emergency_severity_encoded"] = (
        df["emergency_severity"].astype(str).str.upper().map(SEVERITY_ENCODED)
    )
    X["resource_type_encoded"] = (
        df["resource_type"].astype(str).str.upper().map(RESOURCE_TYPE_ENCODED)
    )
    X["daily_consumption"] = pd.to_numeric(df["daily_consumption"], errors="coerce")
    X["days_since_emergency"] = pd.to_numeric(df["days_since_emergency"], errors="coerce")
    X["previous_demand"] = pd.to_numeric(df["previous_demand"], errors="coerce")
    X = X.fillna(X.median(numeric_only=True))
    return X[FEATURES]
