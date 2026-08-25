"""Allocation engine endpoints (admin only) and read access for operators."""
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models.allocation import Allocation
from ..models.user import User
from ..services import allocation_service
from ..services.auth_service import require_roles
from ..utils.helpers import success_response

allocation_bp = Blueprint("allocation", __name__)


@allocation_bp.post("")
@jwt_required()
def run_allocation():
    require_roles("ADMIN")
    user = db.session.get(User, int(get_jwt_identity()))
    data = request.get_json(silent=True) or {}
    result = allocation_service.run_allocation(
        user,
        emergency_id=data.get("emergency_id"),
        request_ids=data.get("request_ids"),
    )
    return success_response(result, message=(
        f"Processed {result['processed']} request(s): "
        f"{result['fully_allocated']} full, {result['partially_allocated']} partial, "
        f"{result['waiting_for_stock']} waiting for stock"
    ))


@allocation_bp.get("")
@jwt_required()
def list_allocations():
    status = request.args.get("status")
    rows = allocation_service.list_allocations(status=status)
    return success_response([a.to_dict() for a in rows], message=f"{len(rows)} allocations")


@allocation_bp.get("/<int:allocation_id>")
@jwt_required()
def get_allocation(allocation_id: int):
    allocation = db.session.get(Allocation, allocation_id)
    if not allocation:
        raise LookupError("Allocation not found")
    return success_response(allocation.to_dict())


@allocation_bp.put("/<int:allocation_id>/cancel")
@jwt_required()
def cancel(allocation_id: int):
    require_roles("ADMIN")
    user = db.session.get(User, int(get_jwt_identity()))
    result = allocation_service.cancel_allocation(allocation_id, user)
    return success_response(result, message="Allocation cancelled and stock released")
