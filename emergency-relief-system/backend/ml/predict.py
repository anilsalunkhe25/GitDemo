"""Inference layer: load the trained model and turn predictions into
explainable shortage recommendations (business rules 4, 5, 6)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import pandas as pd

from .preprocessing import FEATURES

logger = logging.getLogger("relief.ml")

DEFAULT_MODEL_PATH = str(Path(__file__).resolve().parent / "model.pkl")
DEFAULT_METRICS_PATH = str(Path(__file__).resolve().parent / "metrics.json")


class ModelNotTrainedError(FileNotFoundError):
    pass


def model_metrics(metrics_path: str = DEFAULT_METRICS_PATH) -> dict:
    path = Path(metrics_path)
    if not path.exists():
        return {"status": "not_trained", "message": "Run python -m backend.ml.train_model"}
    return json.loads(path.read_text())


def compute_shortage(predicted_quantity: float, current_stock: float) -> tuple[float, float]:
    """expected_shortage = predicted_requirement - current_available_stock."""
    shortage = round(max(predicted_quantity - current_stock, 0.0), 1)
    recommended_qty = shortage
    return shortage, recommended_qty


def make_recommendation(resource_name: str, unit: str, predicted: float,
                        current_stock: float, shortage: float) -> dict:
    """Human-readable recommendation; always flagged for human review."""
    if shortage > 0:
        message = (
            f"AI Recommendation — Human Review Required: predicted demand for {resource_name} "
            f"is {predicted:,.0f} {unit} but only {current_stock:,.0f} {unit} are available. "
            f"Allocate/Procure approximately {shortage:,.0f} additional {unit} of {resource_name}."
        )
    else:
        surplus = current_stock - predicted
        message = (
            f"AI Recommendation — Human Review Required: current stock of {current_stock:,.0f} "
            f"{unit} is sufficient. Predicted demand is {predicted:,.0f} {unit} "
            f"(surplus margin ~{surplus:,.0f} {unit})."
        )
    return {
        "message": message,
        "human_review_required": True,
        "recommended_quantity": round(shortage if shortage > 0 else 0, 1),
    }


class DemandPredictor:
    """Loads the joblib model once and predicts future resource requirements."""

    def __init__(self, model, version: str):
        self.model = model
        self.version = version

    @classmethod
    def load(cls, model_path: str | None = None) -> "DemandPredictor":
        from flask import current_app

        path = model_path
        if path is None:
            try:
                path = current_app.config["ML_MODEL_PATH"]
            except RuntimeError:
                path = DEFAULT_MODEL_PATH
        if not Path(path).exists():
            raise ModelNotTrainedError(
                f"Model file not found at {path}. Train it with: python -m backend.ml.train_model"
            )
        metrics = model_metrics()
        version = f"{metrics.get('best_model', 'unknown')}@{metrics.get('trained_at', 'unversioned')}"
        logger.info("Loading ML model %s", version)
        return cls(joblib.load(path), version)

    def predict(self, *, population_affected: int, emergency_duration: int,
                emergency_severity: str, resource_category: str,
                daily_consumption: float | None = None, resource_id=None,
                days_since_emergency: int = 0, previous_demand: float | None = None) -> float:
        """Return the predicted future requirement for one emergency/area/resource.

        daily_consumption/previous_demand are estimated when not supplied so the
        API caller never needs to know the internal feature engineering.
        """
        from ..utils.constants import PER_CAPITA_DAILY_CONSUMPTION, SEVERITY_MULTIPLIER
        from .preprocessing import RESOURCE_TYPE_ENCODED, SEVERITY_ENCODED

        if daily_consumption is None or daily_consumption <= 0:
            daily_consumption = (
                max(population_affected, 1)
                * PER_CAPITA_DAILY_CONSUMPTION.get(resource_category, 0.01)
                * SEVERITY_MULTIPLIER.get(emergency_severity, 1.15)
            )
        if previous_demand is None:
            previous_demand = daily_consumption * max(days_since_emergency, 1)

        encoded_category = RESOURCE_TYPE_ENCODED.get(resource_category.upper(), 9)
        row = {
            "population_affected": [max(int(population_affected), 0)],
            "emergency_duration": [int(emergency_duration)],
            "emergency_severity_encoded": [
                SEVERITY_ENCODED.get(str(emergency_severity).upper(), 2)
            ],
            "resource_type_encoded": [encoded_category],
            "daily_consumption": [round(float(daily_consumption), 2)],
            "days_since_emergency": [max(int(days_since_emergency), 0)],
            "previous_demand": [round(float(previous_demand), 1)],
        }
        X = pd.DataFrame(row)[FEATURES]
        prediction = float(self.model.predict(X)[0])
        return max(round(prediction, 1), 0.0)
