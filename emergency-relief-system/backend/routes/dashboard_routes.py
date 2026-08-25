"""Dashboard and analytics endpoints."""
from datetime import date

from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..services import analytics_service, dashboard_service
from ..utils.helpers import error_response, success_response
from ..utils.validators import ValidationError, parse_date

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/summary")
@jwt_required()
def summary():
    return success_response(dashboard_service.summary(), message="Dashboard summary")


@dashboard_bp.get("/notifications")
@jwt_required()
def notifications():
    from ..models.demand_forecast import Notification

    rows = Notification.query.order_by(Notification.created_at.desc()).limit(50).all()
    return success_response([n.to_dict() for n in rows], message=f"{len(rows)} notifications")


@dashboard_bp.get("/analytics")
@jwt_required()
def analytics():
    try:
        start = parse_date(request.args["start_date"], "start_date") if "start_date" in request.args else None
        end = parse_date(request.args["end_date"], "end_date") if "end_date" in request.args else None
    except ValidationError as exc:
        return error_response(str(exc), error="validation_failed", status=422)
    if start and end and end < start:
        return error_response("end_date must be after start_date", error="validation_failed", status=422)
    result = analytics_service.overview(
        emergency_id=request.args.get("emergency_id", type=int),
        resource_id=request.args.get("resource_id", type=int),
        area_id=request.args.get("area_id", type=int),
        start_date=start,
        end_date=end,
    )
    return success_response(result, message="Analytics overview")
