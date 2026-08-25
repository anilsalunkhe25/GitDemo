"""Relief center model with capacity tracking."""
from ..extensions import db
from ..utils.constants import CENTER_STATUSES


class ReliefCenter(db.Model):
    __tablename__ = "relief_centers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    location = db.Column(db.String(150))
    address = db.Column(db.Text)
    storage_capacity = db.Column(db.Integer, nullable=False, default=10000)
    current_utilization = db.Column(db.Integer, nullable=False, default=0)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    status = db.Column(db.Enum(*CENTER_STATUSES, name="center_statuses"), nullable=False, default="ACTIVE")

    manager = db.relationship("User", foreign_keys=[manager_id])
    inventory_items = db.relationship("Inventory", back_populates="relief_center")

    @property
    def available_capacity(self) -> int:
        return max(self.storage_capacity - self.current_utilization, 0)

    @property
    def utilization_pct(self) -> float:
        if not self.storage_capacity:
            return 100.0
        return round(self.current_utilization / self.storage_capacity * 100, 1)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "address": self.address,
            "storage_capacity": self.storage_capacity,
            "current_utilization": self.current_utilization,
            "available_capacity": self.available_capacity,
            "utilization_pct": self.utilization_pct,
            "manager_id": self.manager_id,
            "manager_name": self.manager.name if self.manager else None,
            "status": self.status,
        }
