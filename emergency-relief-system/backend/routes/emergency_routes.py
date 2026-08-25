"""Emergency and affected-area management endpoints."""
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models.emergency import AffectedArea, Emergency
from ..utils.constants import EMERGENCY_STATUSES, EMERGENCY_TYPES, SEVERITIES
from ..utils.helpers import success_response
from ..utils.validators import (
    ValidationError,
    parse_payload_date,
    validate_choice,
    validate_non_negative_number,
    validate_required,
)

emergencies_bp = Blueprint("emergencies", __name__)
areas_bp = Blueprint("areas", __name__)


def _serialize_emergency(e: Emergency) -> dict:
    data = e.to_dict()
    data["areas"] = [a.to_dict() for a in e.areas]
    return data


@emergencies_bp.get("")
@jwt_required()
def list_emergencies():
    status = request.args.get("status")
    query = Emergency.query.order_by(Emergency.created_at.desc())
    if status:
        validate_choice(status, EMERGENCY_STATUSES, "status")
        query = query.filter_by(status=status)
    return success_response([e.to_dict() for e in query], message=f"{query.count()} emergencies")


@emergencies_bp.post("")
@jwt_required()
def create_emergency():
    auth_service_require_admin()
    data = request.get_json(silent=True) or {}
    name = validate_required(data.get("name"), "name")
    etype = validate_choice(data.get("type"), EMERGENCY_TYPES, "type")
    severity = validate_choice(data.get("severity", "MEDIUM"), SEVERITIES, "severity")
    start_date = parse_payload_date(data, "start_date", required=True)
    duration = int(validate_non_negative_number(data.get("expected_duration", 7), "expected_duration"))

    emergency = Emergency(
        name=name, type=etype, description=(data.get("description") or "").strip() or None,
        start_date=start_date, expected_duration=duration,
        severity=severity, status=data.get("status") or "ACTIVE",
        created_by=int(get_jwt_identity()),
    )
    db.session.add(emergency)
    db.session.commit()
    return success_response(_serialize_emergency(emergency), message="Emergency created", status=201)


@emergencies_bp.get("/<int:emergency_id>")
@jwt_required()
def get_emergency(emergency_id: int):
    emergency = db.session.get(Emergency, emergency_id)
    if not emergency:
        raise LookupError(f"Emergency {emergency_id} not found")
    return success_response(_serialize_emergency(emergency))


@emergencies_bp.put("/<int:emergency_id>")
@jwt_required()
def update_emergency(emergency_id: int):
    auth_service_require_admin()
    emergency = db.session.get(Emergency, emergency_id)
    if not emergency:
        raise LookupError(f"Emergency {emergency_id} not found")
    data = request.get_json(silent=True) or {}
    if "name" in data:
        emergency.name = validate_required(data["name"], "name")
    if "type" in data:
        emergency.type = validate_choice(data["type"], EMERGENCY_TYPES, "type")
    if "severity" in data:
        emergency.severity = validate_choice(data["severity"], SEVERITIES, "severity")
    if "description" in data:
        emergency.description = (data["description"] or "").strip() or None
    if "expected_duration" in data:
        emergency.expected_duration = int(
            validate_non_negative_number(data["expected_duration"], "expected_duration"))
    if "status" in data:
        emergency.status = validate_choice(data["status"], EMERGENCY_STATUSES, "status")
    db.session.commit()
    return success_response(_serialize_emergency(emergency), message="Emergency updated")


@emergencies_bp.delete("/<int:emergency_id>")
@jwt_required()
def delete_emergency(emergency_id: int):
    auth_service_require_admin()
    emergency = db.session.get(Emergency, emergency_id)
    if not emergency:
        raise LookupError(f"Emergency {emergency_id} not found")
    if emergency.areas.count():
        raise ValidationError("Delete or reassign affected areas before deleting this emergency")
    db.session.delete(emergency)
    db.session.commit()
    return success_response(message="Emergency deleted")


def auth_service_require_admin() -> None:
    from ..services.auth_service import require_roles

    require_roles("ADMIN")


@areas_bp.get("")
@jwt_required()
def list_areas():
    emergency_id = request.args.get("emergency_id", type=int)
    query = AffectedArea.query
    if emergency_id:
        query = query.filter_by(emergency_id=emergency_id)
    return success_response([a.to_dict() for a in query], message=f"{query.count()} areas")


@areas_bp.post("")
@jwt_required()
def create_area():
    data = request.get_json(silent=True) or {}
    emergency = db.session.get(Emergency, data.get("emergency_id"))
    if not emergency:
        raise ValidationError("Emergency not found")
    area = AffectedArea(
        emergency_id=emergency.id,
        area_name=validate_required(data.get("area_name"), "area_name"),
        population_affected=int(validate_non_negative_number(
            data.get("population_affected", 0), "population_affected")),
        severity=validate_choice(data.get("severity", "MEDIUM"), SEVERITIES, "severity"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
    )
    db.session.add(area)
    try:
        db.session.commit()
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            raise ValidationError("This area already exists for the emergency")
        raise
    return success_response(area.to_dict(), message="Affected area added", status=201)


@areas_bp.put("/<int:area_id>")
@jwt_required()
def update_area(area_id: int):
    area = db.session.get(AffectedArea, area_id)
    if not area:
        raise LookupError(f"Area {area_id} not found")
    data = request.get_json(silent=True) or {}
    if "area_name" in data:
        area.area_name = validate_required(data["area_name"], "area_name")
    if "population_affected" in data:
        area.population_affected = int(validate_non_negative_number(
            data["population_affected"], "population_affected"))
    if "severity" in data:
        area.severity = validate_choice(data["severity"], SEVERITIES, "severity")
    db.session.commit()
    return success_response(area.to_dict(), message="Area updated")


@areas_bp.delete("/<int:area_id>")
@jwt_required()
def delete_area(area_id: int):
    auth_service_require_admin()
    area = db.session.get(AffectedArea, area_id)
    if not area:
        raise LookupError(f"Area {area_id} not found")
    db.session.delete(area)
    db.session.commit()
    return success_response(message="Area deleted")
