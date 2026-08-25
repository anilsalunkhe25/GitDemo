"""Forecast service bridging the ML model with live database state.

Workflow (spec §33): historical data -> preprocessing -> prediction against
current inventory -> expected shortage calculation -> explainable
recommendation flagged for human review.
"""
import json
import logging
from datetime import date

from ..extensions import db
from ..ml.predict import DemandPredictor, compute_shortage, make_recommendation, model_metrics
from ..models.demand_forecast import DemandForecast, Notification
from ..models.emergency import AffectedArea, Emergency
from ..models.inventory import Inventory
from ..models.relief_request import ReliefRequest
from ..services.inventory_service import consumption_history
from ..utils.constants import PER_CAPITA_DAILY_CONSUMPTION, SEVERITY_MULTIPLIER

logger = logging.getLogger("relief.forecast")

SEVERITY_ENCODED = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


class ForecastError(Exception):
    pass


def current_stock_for_resource(resource_id: int) -> int:
    return int(
        db.session.query(db.func.coalesce(db.func.sum(Inventory.quantity_available), 0))
        .filter(
            Inventory.resource_id == resource_id,
            db.or_(Inventory.expiry_date.is_(None), Inventory.expiry_date >= date.today()),
        )
        .scalar()
    )


def previous_demand_avg(resource_id: int, area_id: int | None = None) -> float:
    query = db.session.query(db.func.avg(ReliefRequest.quantity)).filter(
        ReliefRequest.resource_id == resource_id
    )
    if area_id:
        query = query.filter(ReliefRequest.area_id == area_id)
    value = query.scalar()
    return round(float(value), 1) if value else 0.0


def build_features(emergency: Emergency, area: AffectedArea | None,
                   resource_id: int, resource_category: str) -> dict:
    """Assemble the exact feature vector used at training time."""
    days_since = max((date.today() - emergency.start_date).days, 0)
    duration = emergency.expected_duration or 7
    daily_modeled = (
        (area.population_affected if area else 100)
        * PER_CAPITA_DAILY_CONSUMPTION.get(resource_category, 0.01)
        * SEVERITY_MULTIPLIER.get(emergency.severity, 1.15)
    )
    daily_observed = consumption_history(resource_id, days=14)
    features = {
        "population_affected": int(area.population_affected) if area else 0,
        "emergency_duration": duration,
        "emergency_severity_encoded": SEVERITY_ENCODED.get(emergency.severity, 2),
        "resource_type_encoded": resource_category,
        "daily_consumption": max(daily_observed, round(daily_modeled, 2)),
        "days_since_emergency": min(days_since, duration),
        "previous_demand": previous_demand_avg(resource_id, area.id if area else None),
    }
    return features


def generate_forecast(emergency_id: int, area_id: int | None, resource_id: int,
                      predictor: DemandPredictor | None = None) -> dict:
    from ..models.resource import Resource

    emergency = db.session.get(Emergency, emergency_id)
    if not emergency:
        raise ForecastError("Emergency not found")
    area = db.session.get(AffectedArea, area_id) if area_id else None
    if area_id and not area:
        raise ForecastError("Affected area not found")
    resource = db.session.get(Resource, resource_id)
    if not resource:
        raise ForecastError("Resource not found")

    try:
        predictor = predictor or DemandPredictor.load()
        predicted = predictor.predict(
            population_affected=area.population_affected if area else 0,
            emergency_duration=emergency.expected_duration or 7,
            emergency_severity=emergency.severity,
            resource_category=resource.category,
            daily_consumption=None,
            resource_id=resource.id,
            days_since_emergency=max((date.today() - emergency.start_date).days, 0),
        )
    except FileNotFoundError:
        raise ForecastError(
            "ML model is not trained yet. Run: python -m backend.ml.train_model"
        )
    except Exception as exc:
        logger.exception("Prediction failed")
        raise ForecastError(f"Model prediction failed: {exc}")

    # Recompute daily consumption exactly as in feature builder for transparency
    feats = build_features(emergency, area, resource.id, resource.category)
    current_stock = current_stock_for_resource(resource.id)
    shortage, recommended_qty = compute_shortage(predicted, current_stock)
    recommendation = make_recommendation(resource.name, resource.unit or "units",
                                         predicted, current_stock, shortage)

    forecast = DemandForecast(
        emergency_id=emergency.id,
        area_id=area.id if area else emergency.areas.first().id if emergency.areas.count() else None,
        resource_id=resource.id,
        forecast_date=date.today(),
        predicted_quantity=float(predicted),
        current_stock=current_stock,
        expected_shortage=float(shortage),
        recommendation=recommendation["message"],
        input_features=json.dumps({**feats, "daily_consumption_used": feats["daily_consumption"]}),
        model_version=predictor.version,
    )
    if forecast.area_id is None:
        raise ForecastError("Emergency has no affected areas to forecast for")
    db.session.add(forecast)

    if shortage > 0:
        level = "CRITICAL" if shortage >= predicted * 0.5 else "WARNING"
        db.session.add(Notification(
            type=level,
            title=f"Expected {resource.name} shortage ({round(shortage)} {resource.unit})",
            message=recommendation["message"],
            reference_type="demand_forecast",
        ))
    db.session.commit()
    logger.info(
        "Forecast saved id=%s predicted=%.1f stock=%s shortage=%.1f",
        forecast.id, predicted, current_stock, shortage,
    )

    result = forecast.to_dict()
    result["human_review_required"] = True
    result["calculation"] = {
        "formula": "expected_shortage = predicted_requirement - current_available_stock",
        "predicted_requirement": round(predicted, 1),
        "current_available_stock": current_stock,
        "expected_shortage": round(shortage, 1),
    }
    result["model_metrics"] = model_metrics()
    return result


def list_forecasts(limit=50):
    return DemandForecast.query.order_by(DemandForecast.created_at.desc()).limit(limit).all()


def mark_reviewed(forecast_id: int, reviewed: bool = True):
    fc = db.session.get(DemandForecast, forecast_id)
    if not fc:
        raise ForecastError("Forecast not found")
    fc.human_reviewed = bool(reviewed)
    db.session.commit()
    return fc
