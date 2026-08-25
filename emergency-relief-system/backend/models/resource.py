"""Resource catalog model."""
from ..extensions import db
from ..utils.constants import RESOURCE_CATEGORIES


class Resource(db.Model):
    __tablename__ = "resources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    category = db.Column(db.Enum(*RESOURCE_CATEGORIES, name="resource_categories"), nullable=False)
    unit = db.Column(db.String(30), nullable=False, default="units")
    shelf_life_days = db.Column(db.Integer)
    minimum_stock_level = db.Column(db.Integer, nullable=False, default=100)

    inventory_items = db.relationship("Inventory", back_populates="resource")

    @property
    def total_available(self) -> int:
        return sum(i.quantity_available for i in self.inventory_items)

    @property
    def total_reserved(self) -> int:
        return sum(i.quantity_reserved for i in self.inventory_items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "shelf_life_days": self.shelf_life_days,
            "minimum_stock_level": self.minimum_stock_level,
            "total_available": self.total_available,
            "total_reserved": self.total_reserved,
        }
