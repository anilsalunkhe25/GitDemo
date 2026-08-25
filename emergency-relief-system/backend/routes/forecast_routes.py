"""AI demand forecasting endpoints."""
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models.user import User
from ..services import forecast_service
from ..services.auth_service import require_roles
from ..ml.predict import model_metrics
from ..utils.helpers import success_response

forecast_bp = Blueprint("forecast", __name__)


@forecast_bp.post("/predict")
@jwt_required()
def predict():
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    data = request.get_json(silent=True) or {}
    result = forecast_service.generate_forecast(
        emergency_id=data.get("emergency_id"),
        area_id=data.get("area_id"),
        resource_id=data.get("resource_id"),
    )
    return success_response(result, message="Forecast generated — human review required")


@forecast_bp.get("/history")
@jwt_required()
def history():
    emergency_id = request.args.get("emergency_id", type=int)
    resource_id = request.args.get("resource_id", type=int)
    query = forecast_service.list_forecasts(limit=min(int(request.args.get("limit", 50)), 200))
    rows = [
        f for f in query
        if (not emergency_id or f.emergency_id == emergency_id)
        and (not resource_id or f.resource_id == resource_id)
    ]
    return success_response([f.to_dict() for f in rows], message=f"{len(rows)} forecasts")


@forecast_bp.get("/metrics")
@jwt_required()
def metrics():
    """Honest model evaluation metrics (MAE / RMSE / R²)."""
    data = model_metrics()
    if data.get("status") == "not_trained":
        from flask import jsonify

        return jsonify({"success": False, "message": data["message"], "error": "model_not_trained"}), 409
    return success_response(data, message=f"Best model: {data.get('best_model')}")


@forecast_bp.put("/<int:forecast_id>/review")
@jwt_required()
def review(forecast_id: int):
    """Record that a human administrator reviewed the AI recommendation."""
    user = db.session.get(User, int(get_jwt_identity()))
    require_roles("ADMIN")
    fc = forecast_service.mark_reviewed(forecast_id, reviewed=True)
    _ = user
    return success_response(fc.to_dict(), message="Forecast marked as human-reviewed")
