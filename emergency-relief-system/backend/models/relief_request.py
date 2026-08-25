"""Relief request model with transparent priority scoring."""
from datetime import datetime

from ..extensions import db
from ..utils.constants import REQUEST_STATUSES, URGENCIES

import json


class ReliefRequest(db.Model):
    __tablename__ = "relief_requests"

    id = db.Column(db.Integer, primary_key=True)
    emergency_id = db.Column(db.Integer, db.ForeignKey("emergencies.id"), nullable=False, index=True)
    area_id = db.Column(db.Integer, db.ForeignKey("affected_areas.id"), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False, index=True)
    people_affected = db.Column(db.Integer)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, nullable=False)
    urgency = db.Column(db.Enum(*URGENCIES, name="request_urgencies"), nullable=False, default="MEDIUM")
    priority_score = db.Column(db.Float, nullable=False, default=0.0)
    priority_breakdown = db.Column(db.Text)
    status = db.Column(db.Enum(*REQUEST_STATUSES, name="request_statuses"), nullable=False, default="PENDING", index=True)
    rejection_reason = db.Column(db.String(255))
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    allocated_quantity = db.Column(db.Integer, nullable=False, default=0)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    required_by = db.Column(db.Date, nullable=False)

    emergency = db.relationship("Emergency")
    area = db.relationship("AffectedArea")
    resource = db.relationship("Resource")
    requester = db.relationship("User", foreign_keys=[requested_by])

    @property
    def priority_level(self) -> str:
        score = self.priority_score or 0
        if score >= 81:
            return "CRITICAL"
        if score >= 61:
            return "HIGH"
        if score >= 31:
            return "MEDIUM"
        return "LOW"

    @property
    def breakdown_dict(self) -> dict:
        try:
            return json.loads(self.priority_breakdown or "{}")
        except (ValueError, TypeError):
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "emergency_id": self.emergency_id,
            "emergency_name": self.emergency.name if self.emergency else None,
            "area_id": self.area_id,
            "area_name": self.area.area_name if self.area else None,
            "requested_by": self.requested_by,
            "requested_by_name": self.requester.name if self.requester else None,
            "resource_id": self.resource_id,
            "resource_name": self.resource.name if self.resource else None,
            "unit": self.resource.unit if self.resource else None,
            "people_affected": self.people_affected,
            "description": self.description,
            "quantity": self.quantity,
            "allocated_quantity": self.allocated_quantity,
            "urgency": self.urgency,
            "priority_score": round(self.priority_score or 0, 1),
            "priority_level": self.priority_level,
            "priority_breakdown": self.breakdown_dict,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "required_by": self.required_by.isoformat() if self.required_by else None,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
        }
