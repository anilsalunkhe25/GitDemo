"""Inventory management endpoints with transaction ledger access."""
from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..models.inventory import Inventory
from ..extensions import db
from ..services import inventory_service
from ..services.auth_service import require_roles
from ..utils.helpers import success_response

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.get("")
@jwt_required()
def list_inventory():
    center_id = request.args.get("center_id", type=int)
    resource_id = request.args.get("resource_id", type=int)
    include_expired = request.args.get("include_expired", "true").lower() == "true"
    query = Inventory.query.order_by(Inventory.expiry_date.asc().nullslast())
    if center_id:
        query = query.filter_by(relief_center_id=center_id)
    if resource_id:
        query = query.filter_by(resource_id=resource_id)
    rows = query.all()
    if not include_expired:
        from datetime import date

        rows = [r for r in rows if not r.is_expired]
    return success_response([r.to_dict() for r in rows], message=f"{len(rows)} inventory records")


@inventory_bp.post("/add")
@jwt_required()
def add_stock():
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    data = request.get_json(silent=True) or {}
    row = inventory_service.add_stock(
        center_id=data.get("relief_center_id"),
        resource_id=data.get("resource_id"),
        quantity=data.get("quantity"),
        expiry_date=_parse_optional_date(data),
        performed_by=int(get_jwt_identity()),
    )
    return success_response(row.to_dict(), message="Stock added and logged", status=201)


@inventory_bp.post("/remove")
@jwt_required()
def remove_stock():
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    data = request.get_json(silent=True) or {}
    row = inventory_service.remove_stock(
        center_id=data.get("relief_center_id"),
        resource_id=data.get("resource_id"),
        quantity=data.get("quantity"),
        performed_by=int(get_jwt_identity()),
        reference_type="MANUAL_REMOVE",
    )
    return success_response(row.to_dict(), message="Stock removed and logged")


@inventory_bp.post("/transfer")
@jwt_required()
def transfer():
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    data = request.get_json(silent=True) or {}
    inventory_service.transfer_stock(
        from_center_id=data.get("from_center_id"),
        to_center_id=data.get("to_center_id"),
        resource_id=data.get("resource_id"),
        quantity=data.get("quantity"),
        performed_by=int(get_jwt_identity()),
    )
    return success_response(message="Transfer completed; both legs logged")


@inventory_bp.put("/<int:inventory_id>/reserve")
@jwt_required()
def reserve(inventory_id: int):
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    data = request.get_json(silent=True) or {}
    row = db.session.get(Inventory, inventory_id)
    if not row:
        raise LookupError("Inventory record not found")
    if row.quantity_available < int(data.get("quantity", 0)):
        from ..services.inventory_service import InventoryError

        raise InventoryError("Cannot reserve more than the available quantity")
    inventory_service.reserve_stock(
        center_id=row.relief_center_id, resource_id=row.resource_id,
        quantity=data.get("quantity"), reference_type="MANUAL_RESERVE",
        performed_by=int(get_jwt_identity()), commit=False,
    )
    db.session.commit()
    return success_response(row.to_dict(), message="Stock reserved")


@inventory_bp.put("/<int:inventory_id>/release")
@jwt_required()
def release(inventory_id: int):
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    data = request.get_json(silent=True) or {}
    inventory_service.release_reserved(
        inventory_id=inventory_id, quantity=data.get("quantity"),
        performed_by=int(get_jwt_identity()), reference_type="MANUAL_RELEASE",
    )
    row = db.session.get(Inventory, inventory_id)
    return success_response(row.to_dict(), message="Reserved stock released")


@inventory_bp.post("/transaction")
@jwt_required()
def generic_transaction():
    """Single endpoint handling IN / OUT / TRANSFER transactions."""
    data = request.get_json(silent=True) or {}
    txn = (data.get("transaction_type") or "").upper()
    if txn == "IN":
        return add_stock()
    if txn == "OUT":
        return remove_stock()
    if txn in ("TRANSFER_IN", "TRANSFER_OUT"):
        return transfer()
    from ..utils.validators import ValidationError

    raise ValidationError("transaction_type must be one of IN, OUT, TRANSFER_IN/OUT")


@inventory_bp.get("/transactions")
@jwt_required()
def transactions():
    txns = inventory_service.list_transactions(
        limit=min(int(request.args.get("limit", 200)), 500),
        center_id=request.args.get("center_id", type=int),
        resource_id=request.args.get("resource_id", type=int),
    )
    return success_response([t.to_dict() for t in txns], message=f"{len(txns)} transactions")


@inventory_bp.get("/alerts/low-stock")
@jwt_required()
def low_stock():
    return success_response(inventory_service.low_stock_resources(), message="Low-stock alerts")


@inventory_bp.get("/alerts/expiring")
@jwt_required()
def expiring():
    days = min(int(request.args.get("days", 14)), 180)
    return success_response({
        "expiring_soon": inventory_service.expiring_soon(days),
        "write_off_candidates": inventory_service.write_off_candidates(),
    }, message="Expiry alerts")


@inventory_bp.post("/alerts/write-off-expired")
@jwt_required()
def write_off_expired():
    require_roles("ADMIN", "RELIEF_CENTER_OPERATOR")
    written = inventory_service.write_off_expired(performed_by=int(get_jwt_identity()))
    return success_response(written, message=f"{len(written)} expired batch(es) processed")


def _parse_optional_date(data: dict):
    raw = data.get("expiry_date")
    if not raw:
        return None
    from datetime import date, datetime

    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        from ..utils.validators import ValidationError

        raise ValidationError("expiry_date must be in YYYY-MM-DD format") from exc
