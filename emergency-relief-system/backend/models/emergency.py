"""Emergency event and affected-area models."""
from datetime import datetime

from ..extensions import db
from ..utils.constants import EMERGENCY_STATUSES, EMERGENCY_TYPES, SEVERITIES


class Emergency(db.Model):
    __tablename__ = "emergencies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.Enum(*EMERGENCY_TYPES, name="emergency_types"), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date, nullable=False)
    expected_duration = db.Column(db.Integer, default=7)
    severity = db.Column(db.Enum(*SEVERITIES, name="emergency_severities"), nullable=False, default="MEDIUM")
    status = db.Column(db.Enum(*EMERGENCY_STATUSES, name="emergency_statuses"), nullable=False, default="ACTIVE")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    areas = db.relationship("AffectedArea", back_populates="emergency", cascade="all, delete-orphan", lazy="dynamic")

    @property
    def total_affected_population(self) -> int:
        return sum(a.population_affected or 0 for a in self.areas)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "expected_duration": self.expected_duration,
            "severity": self.severity,
            "status": self.status,
            "total_affected_population": self.total_affected_population,
            "areas_count": self.areas.count(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AffectedArea(db.Model):
    __tablename__ = "affected_areas"

    id = db.Column(db.Integer, primary_key=True)
    emergency_id = db.Column(db.Integer, db.ForeignKey("emergencies.id"), nullable=False, index=True)
    area_name = db.Column(db.String(120), nullable=False)
    population_affected = db.Column(db.Integer, nullable=False, default=0)
    severity = db.Column(db.Enum(*SEVERITIES, name="area_severities"), nullable=False, default="MEDIUM")
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    emergency = db.relationship("Emergency", back_populates="areas")

    __table_args__ = (db.UniqueConstraint("emergency_id", "area_name", name="uq_area_per_emergency"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "emergency_id": self.emergency_id,
            "area_name": self.area_name,
            "population_affected": self.population_affected,
            "severity": self.severity,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
