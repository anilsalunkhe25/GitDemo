"""Relief center management endpoints with capacity tracking."""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models.relief_center import ReliefCenter
from ..services.auth_service import require_roles
from ..utils.helpers import success_response
from ..utils.validators import ValidationError, validate_choice, validate_non_negative_number, validate_required

centers_bp = Blueprint("centers", __name__)


@centers_bp.get("")
@jwt_required()
def list_centers():
    query = ReliefCenter.query.order_by(ReliefCenter.name)
    status = request.args.get("status")
    if status:
        validate_choice(status, ["ACTIVE", "FULL", "INACTIVE"], "status")
        query = query.filter_by(status=status)
    centers = [c.to_dict() for c in query]
    threshold = 80.0
    for c in centers:
        c["capacity_warning"] = c["utilization_pct"] > threshold
    return success_response(centers, message=f"{len(centers)} relief centers")


@centers_bp.post("")
@jwt_required()
def create_center():
    require_roles("ADMIN")
    data = request.get_json(silent=True) or {}
    name = validate_required(data.get("name"), "name")
    if ReliefCenter.query.filter_by(name=name).first():
        raise ValidationError(f"Relief center '{name}' already exists")
    capacity = int(validate_non_negative_number(data.get("storage_capacity", 10000), "storage_capacity"))
    center = ReliefCenter(
        name=name,
        location=(data.get("location") or "").strip() or None,
        address=(data.get("address") or "").strip() or None,
        storage_capacity=capacity,
        manager_id=data.get("manager_id"),
        status="ACTIVE",
    )
    db.session.add(center)
    db.session.commit()
    return success_response(center.to_dict(), message="Relief center created", status=201)


@centers_bp.put("/<int:center_id>")
@jwt_required()
def update_center(center_id: int):
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    center = db.session.get(ReliefCenter, center_id)
    if not center:
        raise LookupError("Relief center not found")
    data = request.get_json(silent=True) or {}
    if "name" in data:
        center.name = validate_required(data["name"], "name")
    if "location" in data:
        center.location = (data["location"] or "").strip() or None
    if "address" in data:
        center.address = (data["address"] or "").strip() or None
    if "storage_capacity" in data:
        capacity = int(validate_non_negative_number(data["storage_capacity"], "storage_capacity"))
        if capacity < center.current_utilization:
            raise ValidationError(
                f"Capacity cannot be below current utilization ({center.current_utilization})"
            )
        center.storage_capacity = capacity
    if "manager_id" in data:
        center.manager_id = data["manager_id"]
    if "status" in data:
        center.status = validate_choice(data["status"], ["ACTIVE", "FULL", "INACTIVE"], "status")
    db.session.commit()
    return success_response(center.to_dict(), message="Relief center updated")


@centers_bp.get("/<int:center_id>/inventory")
@jwt_required()
def center_inventory(center_id: int):
    center = db.session.get(ReliefCenter, center_id)
    if not center:
        raise LookupError("Relief center not found")
    items = [i.to_dict() for i in center.inventory_items]
    return success_response({
        "center": center.to_dict(),
        "inventory": items,
        "incoming_units": sum(i["quantity_available"] + i["quantity_reserved"] for i in items),
    })
