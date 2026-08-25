"""Authentication and authorization service."""
import logging

from flask import current_app
from flask_jwt_extended import create_access_token, get_jwt

from ..extensions import db
from ..models.user import User
from ..utils.constants import ROLES
from ..utils.validators import ValidationError, validate_choice, validate_email, validate_password

logger = logging.getLogger("relief.auth")

USER_STATUSES = ["ACTIVE", "INACTIVE"]


class RecordMissing(Exception):
    """Raised when a required database record is not found."""
    pass


def register_user(name: str, email: str, password: str, role: str = "VOLUNTEER_LOGISTICS", phone: str | None = None) -> User:
    email = validate_email(email)
    validate_password(password)
    validate_choice(role, ROLES, "role")
    if not name or len(name.strip()) < 2:
        raise ValidationError("Name must be at least 2 characters long")
    if User.query.filter_by(email=email).first():
        raise ConflictError(f"An account with email {email} already exists")

    user = User(name=name.strip(), email=email, phone=phone, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    logger.info("User registered: id=%s role=%s", user.id, user.role)
    return user


class ConflictError(Exception):
    pass


class AuthError(Exception):
    pass


def authenticate(email: str, password: str) -> tuple[User, str]:
    """Verify credentials and return (user, access_token)."""
    if not email or not password:
        raise ValidationError("Email and password are required")
    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user or not user.check_password(password):
        logger.warning("Failed login attempt for email=%s", email)
        raise AuthError("Invalid email or password")
    if user.status != "ACTIVE":
        raise AuthError("Account is inactive. Contact an administrator.")
    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "name": user.name},
    )
    logger.info("User logged in: id=%s role=%s", user.id, user.role)
    return user, token


def current_user() -> User | None:
    from flask_jwt_extended import get_jwt_identity

    return db.session.get(User, int(get_jwt_identity()))


def require_roles(*roles):
    claims = get_jwt()
    if roles and claims.get("role") not in roles:
        raise PermissionError(f"Role '{claims.get('role')}' is not authorized for this action")


def is_admin() -> bool:
    return get_jwt().get("role") == "ADMIN"


def update_user_role_status(user_id: int, *, role=None, status=None, actor_id=None) -> User:
    user = db.session.get(User, user_id)
    if not user:
        raise RecordMissing("User not found")
    if role:
        validate_choice(role, ROLES, "role")
        user.role = role
    if status:
        validate_choice(status, USER_STATUSES, "status")
        user.status = status
    db.session.commit()
    logger.info("User %s updated by admin %s (role=%s status=%s)", user_id, actor_id, user.role, user.status)
    return user


def list_users(role=None, status=None, search=None):
    query = User.query
    if role:
        query = query.filter_by(role=role)
    if status:
        query = query.filter_by(status=status)
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.name.ilike(like), User.email.ilike(like)))
    return query.order_by(User.created_at.desc()).all()
