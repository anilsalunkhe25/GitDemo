"""Relief request endpoints including transparent priority breakdown."""
import json

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models.relief_request import ReliefRequest
from ..services import request_service
from ..services.auth_service import require_roles
from ..utils.helpers import success_response

requests_bp = Blueprint("requests", __name__)


@requests_bp.get("")
@jwt_required()
def list_requests():
    rows = request_service.list_requests(
        status=request.args.get("status"),
        emergency_id=request.args.get("emergency_id", type=int),
        resource_id=request.args.get("resource_id", type=int),
        min_priority=request.args.get("min_priority", type=float),
    )
    return success_response([r.to_dict() for r in rows], message=f"{len(rows)} relief requests")


@requests_bp.post("")
@jwt_required()
def create_request():
    from ..models.user import User

    data = request.get_json(silent=True) or {}
    user = db.session.get(User, int(get_jwt_identity()))
    req = request_service.create_request(data, user)
    return success_response(req.to_dict(), message="Relief request created and prioritized", status=201)


@requests_bp.get("/<int:request_id>")
@jwt_required()
def get_request(request_id: int):
    req = request_service.get_request_or_fail(request_id)
    data = req.to_dict()
    data["priority_breakdown"] = json.loads(req.priority_breakdown or "[]")
    return success_response(data)


@requests_bp.put("/<int:request_id>")
@jwt_required()
def update_request(request_id: int):
    data = request.get_json(silent=True) or {}
    req = request_service.update_request(request_id, data)
    return success_response(req.to_dict(), message="Request updated and re-prioritized")


@requests_bp.delete("/<int:request_id>")
@jwt_required()
def delete_request(request_id: int):
    require_roles("ADMIN")
    request_service.delete_request(request_id)
    return success_response(message="Request deleted")


@requests_bp.put("/<int:request_id>/approve")
@jwt_required()
def approve(request_id: int):
    require_roles("ADMIN")
    from ..models.user import User

    user = db.session.get(User, int(get_jwt_identity()))
    req = request_service.approve_request(request_id, user)
    return success_response(req.to_dict(), message=f"Request approved (priority {req.priority_score})")


@requests_bp.put("/<int:request_id>/reject")
@jwt_required()
def reject(request_id: int):
    require_roles("ADMIN")
    from ..models.user import User

    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    req = request_service.reject_request(request_id, data.get("reason"), user)
    return success_response(req.to_dict(), message="Request rejected")


@requests_bp.get("/<int:request_id>/priority-explanation")
@jwt_required()
def explain_priority(request_id: int):
    """Full transparency for the viva/demo: every factor behind the score."""
    req = request_service.get_request_or_fail(request_id)
    try:
        breakdown = json.loads(req.priority_breakdown or "[]")
    except ValueError:
        breakdown = []
    explanation = {
        "request_id": req.id,
        "priority_score": round(req.priority_score or 0, 1),
        "priority_level": req.priority_level,
        "formula": (
            "priority = severity*0.30 + population*0.25 + shortage*0.20 "
            "+ urgency*0.15 + time_criticality*0.10"
        ),
        "factors": breakdown,
    }
    return success_response(explanation, message="Priority explanation")
