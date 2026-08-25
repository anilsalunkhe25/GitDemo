"""Inventory model with transaction ledger."""
from datetime import date, datetime

from ..extensions import db
from ..utils.constants import TRANSACTION_TYPES


class Inventory(db.Model):
    __tablename__ = "inventory"

    id = db.Column(db.Integer, primary_key=True)
    relief_center_id = db.Column(db.Integer, db.ForeignKey("relief_centers.id"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False, index=True)
    quantity_available = db.Column(db.Integer, nullable=False, default=0)
    quantity_reserved = db.Column(db.Integer, nullable=False, default=0)
    expiry_date = db.Column(db.Date, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    relief_center = db.relationship("ReliefCenter", back_populates="inventory_items")
    resource = db.relationship("Resource", back_populates="inventory_items")
    transactions = db.relationship(
        "InventoryTransaction", back_populates="inventory", cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint("relief_center_id", "resource_id", "expiry_date", name="uq_inventory_batch"),
    )

    @property
    def is_expired(self) -> bool:
        return bool(self.expiry_date and self.expiry_date < date.today())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "relief_center_id": self.relief_center_id,
            "relief_center_name": self.relief_center.name if self.relief_center else None,
            "resource_id": self.resource_id,
            "resource_name": self.resource.name if self.resource else None,
            "category": self.resource.category if self.resource else None,
            "unit": self.resource.unit if self.resource else None,
            "quantity_available": self.quantity_available,
            "quantity_reserved": self.quantity_reserved,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "is_expired": self.is_expired,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InventoryTransaction(db.Model):
    __tablename__ = "inventory_transactions"

    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey("inventory.id"), nullable=False, index=True)
    transaction_type = db.Column(db.Enum(*TRANSACTION_TYPES, name="txn_types"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)
    performed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    note = db.Column(db.String(255))
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    inventory = db.relationship("Inventory", back_populates="transactions")
    performer = db.relationship("User", foreign_keys=[performed_by])

    def to_dict(self) -> dict:
        inv = self.inventory
        return {
            "id": self.id,
            "inventory_id": self.inventory_id,
            "center_name": inv.relief_center.name if inv and inv.relief_center else None,
            "resource_name": inv.resource.name if inv and inv.resource else None,
            "transaction_type": self.transaction_type,
            "quantity": self.quantity,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "performed_by": self.performer.name if self.performer else None,
            "note": self.note,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
        }
