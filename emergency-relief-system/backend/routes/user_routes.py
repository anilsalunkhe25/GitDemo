"""User management endpoints (admin only)."""
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services import auth_service
from ..utils.helpers import success_response

users_bp = Blueprint("users", __name__)


@users_bp.get("")
@jwt_required()
def list_users():
    auth_service.require_roles("ADMIN")
    users = auth_service.list_users(
        role=request.args.get("role"),
        status=request.args.get("status"),
        search=request.args.get("search"),
    )
    return success_response([u.to_dict() for u in users], message=f"{len(users)} users")


@users_bp.post("")
@jwt_required()
def create_user():
    """Admin can create accounts with any role."""
    auth_service.require_roles("ADMIN")
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.register_user(
            name=data.get("name"),
            email=data.get("email"),
            password=data.get("password"),
            role=data.get("role") or "VOLUNTEER_LOGISTICS",
            phone=data.get("phone"),
        )
    except auth_service.ConflictError as exc:
        from ..utils.helpers import error_response

        return error_response(str(exc), error="duplicate_email", status=409)
    return success_response(user.to_dict(), message="User created", status=201)


@users_bp.put("/<int:user_id>")
@jwt_required()
def update_user(user_id: int):
    auth_service.require_roles("ADMIN")
    data = request.get_json(silent=True) or {}
    user = auth_service.update_user_role_status(
        user_id, role=data.get("role"), status=data.get("status"),
        actor_id=int(get_jwt_identity()),
    )
    return success_response(user.to_dict(), message="User updated")
