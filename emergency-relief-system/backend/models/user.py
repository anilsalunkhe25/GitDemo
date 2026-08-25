"""User model with hashed passwords and role-based access."""
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..utils.constants import ROLES, USER_STATUSES


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(*ROLES, name="user_roles"), nullable=False, default="VOLUNTEER_LOGISTICS")
    phone = db.Column(db.String(20))
    status = db.Column(db.Enum(*USER_STATUSES, name="user_statuses"), nullable=False, default="ACTIVE")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "phone": self.phone,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
