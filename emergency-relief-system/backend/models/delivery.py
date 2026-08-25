"""Delivery model with immutable status-history events."""
from datetime import datetime

from ..extensions import db
from ..utils.constants import DELIVERY_STATUSES


class Delivery(db.Model):
    __tablename__ = "deliveries"

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(db.Integer, db.ForeignKey("allocations.id"), nullable=False, index=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    source_center = db.Column(db.Integer, db.ForeignKey("relief_centers.id"), nullable=False)
    destination_area = db.Column(db.Integer, db.ForeignKey("affected_areas.id"), nullable=False)
    dispatch_date = db.Column(db.DateTime)
    expected_delivery_date = db.Column(db.Date)
    actual_delivery_date = db.Column(db.DateTime)
    status = db.Column(db.Enum(*DELIVERY_STATUSES, name="delivery_statuses"), nullable=False, default="PREPARING", index=True)
    notes = db.Column(db.Text)

    allocation = db.relationship("Allocation", back_populates="deliveries")
    volunteer = db.relationship("User", foreign_keys=[assigned_to])
    source_relief_center = db.relationship("ReliefCenter", foreign_keys=[source_center])
    destination = db.relationship("AffectedArea")
    events = db.relationship(
        "DeliveryEvent", back_populates="delivery",
        cascade="all, delete-orphan", order_by="DeliveryEvent.timestamp",
    )

    def to_dict(self, include_events: bool = True) -> dict:
        req = self.allocation.relief_request if self.allocation else None
        data = {
            "id": self.id,
            "allocation_id": self.allocation_id,
            "request_id": req.id if req else None,
            "resource_names": ", ".join(i.resource.name for i in self.allocation.items) if self.allocation else None,
            "total_quantity": sum(i.quantity for i in self.allocation.items) if self.allocation else 0,
            "assigned_to": self.assigned_to,
            "volunteer_name": self.volunteer.name if self.volunteer else None,
            "source_center": self.source_center,
            "source_center_name": self.source_relief_center.name if self.source_relief_center else None,
            "destination_area": self.destination_area,
            "destination_area_name": self.destination.area_name if self.destination else None,
            "dispatch_date": self.dispatch_date.isoformat() if self.dispatch_date else None,
            "expected_delivery_date": self.expected_delivery_date.isoformat() if self.expected_delivery_date else None,
            "actual_delivery_date": self.actual_delivery_date.isoformat() if self.actual_delivery_date else None,
            "status": self.status,
            "notes": self.notes,
        }
        if include_events:
            data["timeline"] = [e.to_dict() for e in self.events]
        return data


class DeliveryEvent(db.Model):
    """Immutable status-history entry for a delivery (business rule 9)."""

    __tablename__ = "delivery_events"

    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey("deliveries.id"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.String(255))
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    delivery = db.relationship("Delivery", back_populates="events")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "note": self.note,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
