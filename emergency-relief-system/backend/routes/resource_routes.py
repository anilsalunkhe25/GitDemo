"""Resource catalog endpoints."""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models.resource import Resource
from ..services.auth_service import require_roles
from ..utils.constants import RESOURCE_CATEGORIES
from ..utils.helpers import success_response
from ..utils.validators import ValidationError, validate_choice, validate_non_negative_number, validate_required

resources_bp = Blueprint("resources", __name__)


@resources_bp.get("")
@jwt_required()
def list_resources():
    category = request.args.get("category")
    query = Resource.query.order_by(Resource.name)
    if category:
        validate_choice(category, RESOURCE_CATEGORIES, "category")
        query = query.filter_by(category=category)
    return success_response([r.to_dict() for r in query], message=f"{query.count()} resources")


@resources_bp.post("")
@jwt_required()
def create_resource():
    require_roles("ADMIN")
    data = request.get_json(silent=True) or {}
    name = validate_required(data.get("name"), "name")
    if Resource.query.filter_by(name=name).first():
        raise ValidationError(f"Resource '{name}' already exists")
    resource = Resource(
        name=name,
        category=validate_choice(data.get("category"), RESOURCE_CATEGORIES, "category"),
        unit=(data.get("unit") or "units").strip()[:30],
        shelf_life_days=int(v) if (v := data.get("shelf_life_days")) else None,
        minimum_stock_level=int(validate_non_negative_number(
            data.get("minimum_stock_level", 50), "minimum_stock_level")),
    )
    db.session.add(resource)
    db.session.commit()
    return success_response(resource.to_dict(), message="Resource created", status=201)


@resources_bp.put("/<int:resource_id>")
@jwt_required()
def update_resource(resource_id: int):
    require_roles("ADMIN")
    resource = db.session.get(Resource, resource_id)
    if not resource:
        raise LookupError("Resource not found")
    data = request.get_json(silent=True) or {}
    if "minimum_stock_level" in data:
        resource.minimum_stock_level = int(validate_non_negative_number(
            data["minimum_stock_level"], "minimum_stock_level"))
    if "unit" in data:
        resource.unit = (data["unit"] or "units").strip()[:30]
    if "shelf_life_days" in data:
        resource.shelf_life_days = int(validate_non_negative_number(
            data["shelf_life_days"], "shelf_life_days"))
    db.session.commit()
    return success_response(resource.to_dict(), message="Resource updated")
