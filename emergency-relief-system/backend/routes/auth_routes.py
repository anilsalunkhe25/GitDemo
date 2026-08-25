"""Authentication endpoints: register, login, current user."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..models.user import User
from ..services import auth_service
from ..utils.helpers import error_response, success_response
from ..utils.rate_limit import rate_limit
from ..utils.validators import ValidationError

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    try:
        user = auth_service.register_user(
            name=data.get("name"),
            email=data.get("email"),
            password=data.get("password"),
            role="VOLUNTEER_LOGISTICS",  # public self-registration is always logistics role
            phone=data.get("phone"),
        )
    except auth_service.ConflictError as exc:
        return error_response(str(exc), error="duplicate_email", status=409)
    return success_response(user.to_dict(), message="Registration successful. You can now log in.", status=201)


@auth_bp.post("/login")
@rate_limit()
def login():
    data = request.get_json(silent=True) or {}
    try:
        user, token = auth_service.authenticate(data.get("email"), data.get("password"))
    except (auth_service.AuthError, ValidationError) as exc:
        return error_response(str(exc), error="invalid_credentials", status=401)
    return success_response(
        {"access_token": token, "token_type": "Bearer", "user": user.to_dict()},
        message=f"Welcome back, {user.name}",
    )


@auth_bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return error_response("Account no longer exists", error="not_found", status=404)
    claims = get_jwt()
    return success_response({**user.to_dict(), "session_role": claims.get("role")}, message="Current session")


@auth_bp.post("/logout")
@jwt_required()
def logout():
    """Stateless JWT logout: the client discards its token."""
    identity = get_jwt_identity()
    return success_response({"user_id": identity}, message="Logged out. Discard your access token.")
