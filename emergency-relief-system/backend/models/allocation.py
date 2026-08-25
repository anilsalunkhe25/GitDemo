"""Allocation and allocation-item models."""
from datetime import datetime

from ..extensions import db
from ..utils.constants import ALLOCATION_STATUSES


class Allocation(db.Model):
    __tablename__ = "allocations"

    id = db.Column(db.Integer, primary_key=True)
    relief_request_id = db.Column(db.Integer, db.ForeignKey("relief_requests.id"), nullable=False, index=True)
    relief_center_id = db.Column(db.Integer, db.ForeignKey("relief_centers.id"), nullable=False)
    allocated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    allocation_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum(*ALLOCATION_STATUSES, name="allocation_statuses"), nullable=False, default="RESERVED")

    relief_request = db.relationship("ReliefRequest", backref="allocations")
    relief_center = db.relationship("ReliefCenter")
    allocator = db.relationship("User", foreign_keys=[allocated_by])
    items = db.relationship("AllocationItem", back_populates="allocation", cascade="all, delete-orphan")
    deliveries = db.relationship("Delivery", back_populates="allocation")

    @property
    def total_quantity(self) -> int:
        return sum(i.quantity for i in self.items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "relief_request_id": self.relief_request_id,
            "relief_center_id": self.relief_center_id,
            "relief_center_name": self.relief_center.name if self.relief_center else None,
            "allocated_by_name": self.allocator.name if self.allocator else None,
            "allocation_date": self.allocation_date.isoformat() if self.allocation_date else None,
            "status": self.status,
            "total_quantity": self.total_quantity,
            "items": [i.to_dict() for i in self.items],
            "deliveries": [d.to_dict(include_events=False) for d in self.deliveries],
        }


class AllocationItem(db.Model):
    __tablename__ = "allocation_items"

    id = db.Column(db.Integer, primary_key=True)
    allocation_id = db.Column(db.Integer, db.ForeignKey("allocations.id"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

    allocation = db.relationship("Allocation", back_populates="items")
    resource = db.relationship("Resource")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "resource_name": self.resource.name if self.resource else None,
            "quantity": self.quantity,
        }
