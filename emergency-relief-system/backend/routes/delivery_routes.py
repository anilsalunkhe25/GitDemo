"""Delivery tracking endpoints with role-aware status updates."""
from flask import Blueprint, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..models.delivery import Delivery
from ..models.user import User
from ..services import delivery_service
from ..services.auth_service import require_roles
from ..utils.helpers import success_response
from ..utils.validators import parse_payload_date

deliveries_bp = Blueprint("deliveries", __name__)


@deliveries_bp.get("")
@jwt_required()
def list_deliveries():
    claims = get_jwt()
    status = request.args.get("status")
    assigned_to = request.args.get("assigned_to", type=int)

    # Volunteers see only their own deliveries (rule 12)
    if claims.get("role") == "VOLUNTEER_LOGISTICS" and not assigned_to:
        assigned_to = int(get_jwt_identity())
    rows = delivery_service.list_deliveries(status=status, assigned_to=assigned_to)
    return success_response([d.to_dict(include_events=False) for d in rows],
                            message=f"{len(rows)} deliveries")


@deliveries_bp.post("")
@jwt_required()
def create_delivery():
    require_roles("ADMIN")
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    if "expected_delivery_date" in data:
        data["expected_delivery_date"] = parse_payload_date(data, "expected_delivery_date", required=False)
    delivery = delivery_service.create_delivery(data, user)
    return success_response(delivery.to_dict(), message="Delivery created", status=201)


@deliveries_bp.get("/<int:delivery_id>")
@jwt_required()
def get_delivery(delivery_id: int):
    delivery = db.session.get(Delivery, delivery_id)
    if not delivery:
        raise LookupError("Delivery not found")
    claims = get_jwt()
    if claims.get("role") == "VOLUNTEER_LOGISTICS" and delivery.assigned_to != int(get_jwt_identity()):
        from ..utils.helpers import error_response

        return error_response("You can only view your own deliveries", error="forbidden", status=403)
    return success_response(delivery.to_dict())


@deliveries_bp.put("/<int:delivery_id>/status")
@jwt_required()
def update_status(delivery_id: int):
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    try:
        delivery = delivery_service.update_status(
            delivery_id, (data.get("status") or "").upper(), user, note=data.get("note"))
    except PermissionError as exc:
        from ..utils.helpers import error_response

        return error_response(str(exc), error="forbidden", status=403)
    except ValueError as exc:
        from flask import jsonify

        return jsonify({"success": False, "message": str(exc), "error": "invalid_transition"}), 409
    return success_response(delivery.to_dict(), message=f"Delivery is now {delivery.status}")


@deliveries_bp.put("/<int:delivery_id>/assign")
@jwt_required()
def assign(delivery_id: int):
    require_roles("ADMIN")
    data = request.get_json(silent=True) or {}
    delivery = delivery_service.assign_volunteer(delivery_id, data.get("volunteer_id"))
    return success_response(delivery.to_dict(), message="Volunteer assignment updated")


@deliveries_bp.get("/<int:delivery_id>/timeline")
@jwt_required()
def timeline(delivery_id: int):
    delivery = db.session.get(Delivery, delivery_id)
    if not delivery:
        raise LookupError("Delivery not found")
    return success_response({
        "delivery_id": delivery.id,
        "current_status": delivery.status,
        "timeline": [e.to_dict() for e in delivery.events],
    }, message="Delivery timeline")
