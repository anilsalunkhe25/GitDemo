"""AI demand forecast and notification models."""
from datetime import datetime

from ..extensions import db
from ..utils.constants import NOTIFICATION_TYPES


class DemandForecast(db.Model):
    __tablename__ = "demand_forecasts"

    id = db.Column(db.Integer, primary_key=True)
    emergency_id = db.Column(db.Integer, db.ForeignKey("emergencies.id"), nullable=False, index=True)
    area_id = db.Column(db.Integer, db.ForeignKey("affected_areas.id"), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False, index=True)
    forecast_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    predicted_quantity = db.Column(db.Float, nullable=False)
    current_stock = db.Column(db.Integer, nullable=False, default=0)
    expected_shortage = db.Column(db.Float, nullable=False, default=0.0)
    recommendation = db.Column(db.Text)
    input_features = db.Column(db.Text)
    model_version = db.Column(db.String(80))
    human_reviewed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    emergency = db.relationship("Emergency")
    area = db.relationship("AffectedArea")
    resource = db.relationship("Resource")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "emergency_id": self.emergency_id,
            "emergency_name": self.emergency.name if self.emergency else None,
            "area_id": self.area_id,
            "area_name": self.area.area_name if self.area else None,
            "resource_id": self.resource_id,
            "resource_name": self.resource.name if self.resource else None,
            "unit": self.resource.unit if self.resource else None,
            "forecast_date": self.forecast_date.isoformat() if self.forecast_date else None,
            "predicted_quantity": round(self.predicted_quantity, 1),
            "current_stock": self.current_stock,
            "expected_shortage": round(self.expected_shortage, 1),
            "recommendation": self.recommendation,
            "input_features": self.input_features,
            "model_version": self.model_version,
            "human_reviewed": self.human_reviewed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.Enum(*NOTIFICATION_TYPES, name="notification_types"), nullable=False, default="INFO")
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text)
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)
    target_role = db.Column(db.String(40))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "target_role": self.target_role,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
