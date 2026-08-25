"""Inventory service enforcing business rules 1, 7, 10 and 11.

Every stock change writes an InventoryTransaction row; inventory can never
go negative; expired batches are never counted as allocatable.
"""
import logging
from datetime import date, datetime

from ..extensions import db
from ..models.inventory import Inventory, InventoryTransaction
from ..models.relief_center import ReliefCenter
from ..models.resource import Resource
from ..utils.validators import ValidationError, validate_non_negative_number, validate_positive_int

logger = logging.getLogger("relief.inventory")


class InventoryError(Exception):
    pass


def _get_inventory_row(center_id: int, resource_id: int, expiry_date) -> Inventory:
    row = Inventory.query.filter_by(
        relief_center_id=center_id,
        resource_id=resource_id,
        expiry_date=expiry_date if expiry_date else None,
    ).first()
    if not row:
        row = Inventory(
            relief_center_id=center_id,
            resource_id=resource_id,
            expiry_date=expiry_date,
            quantity_available=0,
            quantity_reserved=0,
        )
        db.session.add(row)
        db.session.flush()
    return row


def _check_center_capacity(center: ReliefCenter, additional_units: int) -> None:
    if center.current_utilization + additional_units > center.storage_capacity:
        raise InventoryError(
            f"Capacity exceeded for center '{center.name}': "
            f"{center.current_utilization}/{center.storage_capacity} used, cannot add {additional_units}"
        )


def _log_transaction(inventory: Inventory, txn_type: str, quantity: int, performed_by=None,
                     reference_type=None, reference_id=None, note=None) -> None:
    db.session.add(InventoryTransaction(
        inventory_id=inventory.id,
        transaction_type=txn_type,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
        note=note,
    ))


def add_stock(center_id: int, resource_id: int, quantity: int, expiry_date=None,
              performed_by=None, commit=True) -> Inventory:
    quantity = validate_positive_int(quantity, "quantity")
    center = db.session.get(ReliefCenter, center_id)
    resource = db.session.get(Resource, resource_id)
    if not center:
        raise ValidationError("Relief center not found")
    if not resource:
        raise ValidationError("Resource not found")
    if center.status == "INACTIVE":
        raise InventoryError(f"Center '{center.name}' is inactive")
    _check_center_capacity(center, quantity)

    row = _get_inventory_row(center_id, resource_id, expiry_date)
    if row.is_expired:
        raise InventoryError("Cannot add stock with an already-expired date")
    row.quantity_available += quantity
    center.current_utilization += quantity
    _log_transaction(row, "IN", quantity, performed_by=performed_by, note="Stock received")
    logger.info("IN %s %s -> center=%s by user=%s", quantity, resource.name, center.name, performed_by)
    if commit:
        db.session.commit()
    return row


def remove_stock(center_id: int, resource_id: int, quantity: int, performed_by=None,
                 reference_type=None, reference_id=None, allow_expired=False, commit=True) -> Inventory:
    """Remove from available stock (FIFO by nearest expiry). Raises on shortage."""
    quantity = validate_positive_int(quantity, "quantity")
    rows = (
        Inventory.query.filter_by(relief_center_id=center_id, resource_id=resource_id)
        .filter(Inventory.quantity_available > 0)
        .order_by(Inventory.expiry_date.asc().nullslast(), Inventory.id.asc())
        .all()
    )
    if not allow_expired:
        rows = [r for r in rows if not r.is_expired]
    available = sum(r.quantity_available for r in rows)
    if available < quantity:
        raise InventoryError(
            f"Insufficient stock: requested {quantity}, only {available} available at this center"
        )

    remaining = quantity
    first_row = None
    for row in rows:
        take = min(row.quantity_available, remaining)
        row.quantity_available -= take
        center = row.relief_center
        center.current_utilization = max(center.current_utilization - take, 0)
        _log_transaction(row, "OUT", take, performed_by=performed_by,
                         reference_type=reference_type, reference_id=reference_id)
        remaining -= take
        first_row = first_row or row
        if remaining == 0:
            break
    logger.info("OUT %s units center=%s resource=%s by user=%s", quantity, center_id, resource_id, performed_by)
    if commit:
        db.session.commit()
    return first_row


def transfer_stock(from_center_id: int, to_center_id: int, resource_id: int, quantity: int, performed_by=None):
    if from_center_id == to_center_id:
        raise ValidationError("Source and destination centers must differ")
    source = db.session.get(ReliefCenter, from_center_id)
    dest = db.session.get(ReliefCenter, to_center_id)
    if not source or not dest:
        raise ValidationError("Both relief centers must exist")
    _check_center_capacity(dest, validate_positive_int(quantity, "quantity"))
    remove_stock(from_center_id, resource_id, quantity, performed_by=performed_by, commit=False)
    add_stock(to_center_id, resource_id, quantity, performed_by=performed_by, commit=False)
    db.session.commit()


def reserve_stock(center_id: int, resource_id: int, quantity: int, reference_type=None, reference_id=None,
                  performed_by=None, commit=True) -> Inventory:
    """Reserve available (non-expired) stock for an allocation without removing it yet."""
    quantity = validate_positive_int(quantity, "quantity")
    row = (
        Inventory.query.filter_by(relief_center_id=center_id, resource_id=resource_id)
        .filter(Inventory.quantity_available > 0)
        .filter(db.or_(Inventory.expiry_date.is_(None), Inventory.expiry_date >= date.today()))
        .order_by(Inventory.expiry_date.asc().nullslast(), Inventory.id.asc())
        .first()
    )
    if not row or row.quantity_available < quantity:
        available = row.quantity_available if row else 0
        raise InventoryError(f"Cannot reserve {quantity}; only {available} unreserved units available")
    row.quantity_available -= quantity
    row.quantity_reserved += quantity
    _log_transaction(row, "RESERVE", quantity, performed_by=performed_by,
                     reference_type=reference_type, reference_id=reference_id)
    if commit:
        db.session.commit()
    return row


def release_reserved(inventory_id: int, quantity: int, performed_by=None,
                     reference_type=None, reference_id=None, commit=True) -> None:
    """Return previously reserved stock to the available pool (business rule 7)."""
    quantity = validate_positive_int(quantity, "quantity")
    row = db.session.get(Inventory, inventory_id)
    if not row:
        raise InventoryError("Inventory record not found")
    if row.quantity_reserved < quantity:
        raise InventoryError(
            f"Cannot release {quantity}; only {row.quantity_reserved} reserved at this record"
        )
    row.quantity_reserved -= quantity
    row.quantity_available += quantity
    _log_transaction(row, "RELEASE", quantity, performed_by=performed_by,
                     reference_type=reference_type, reference_id=reference_id)
    if commit:
        db.session.commit()


def convert_reservation_to_outbound(inventory_id: int, quantity: int, performed_by=None,
                                    reference_type=None, reference_id=None) -> None:
    """On dispatch: reserved units physically leave the center."""
    row = db.session.get(Inventory, inventory_id)
    if not row:
        raise InventoryError("Inventory record not found")
    if row.quantity_reserved < quantity:
        raise InventoryError("Reserved quantity mismatch during dispatch")
    row.quantity_reserved -= quantity
    center = row.relief_center
    center.current_utilization = max((center.current_utilization or 0) - quantity, 0)
    _log_transaction(row, "OUT", quantity, performed_by=performed_by,
                     reference_type=reference_type, reference_id=reference_id)


def write_off_candidates() -> list[dict]:
    today = date.today()
    rows = (
        Inventory.query.filter(Inventory.expiry_date < today)
        .filter(Inventory.quantity_available > 0)
        .all()
    )
    return [
        {
            "inventory_id": r.id,
            "center": r.relief_center.name,
            "resource": r.resource.name,
            "quantity": r.quantity_available,
            "expiry_date": r.expiry_date.isoformat(),
        }
        for r in rows
    ]


def write_off_expired(performed_by=None) -> list[dict]:
    """Remove fully-expired batches from availability (business rule 10 support)."""
    today = date.today()
    expired_rows = Inventory.query.filter(Inventory.expiry_date < today).filter(
        db.or_(Inventory.quantity_available > 0, Inventory.quantity_reserved > 0)
    ).all()
    written_off = []
    for row in expired_rows:
        qty = row.quantity_available
        if qty > 0:
            row.quantity_available = 0
            center = row.relief_center
            center.current_utilization = max((center.current_utilization or 0) - qty, 0)
            _log_transaction(row, "EXPIRED_WRITE_OFF", qty, performed_by=performed_by,
                             note=f"Expired {row.expiry_date.isoformat()}")
        written_off.append({"inventory_id": row.id, "resource": row.resource.name,
                            "center": row.relief_center.name, "written_off": qty})
    if written_off:
        db.session.commit()
        logger.info("Expired stock write-off: %s batches", len(written_off))
    return written_off


def low_stock_resources():
    resources = Resource.query.all()
    alerts = []
    for res in resources:
        total = res.total_available
        threshold = res.minimum_stock_level
        if total <= threshold:
            severity = "CRITICAL" if total <= threshold * 0.2 else "WARNING"
            alerts.append({
                "resource_id": res.id,
                "resource_name": res.name,
                "unit": res.unit,
                "total_available": total,
                "minimum_stock_level": threshold,
                "severity": severity,
                "message": f"{res.name}: {total} {res.unit} available (minimum {threshold})",
            })
    return sorted(alerts, key=lambda a: a["total_available"] / max(a["minimum_stock_level"], 1))


def expiring_soon(days: int = 14) -> list[dict]:
    limit = date.today().fromordinal(date.today().toordinal() + days)
    rows = (
        Inventory.query.filter(Inventory.expiry_date.isnot(None))
        .filter(Inventory.expiry_date >= date.today())
        .filter(Inventory.expiry_date <= limit)
        .filter(Inventory.quantity_available > 0)
        .all()
    )
    return [r.to_dict() for r in rows]


def list_transactions(limit: int = 200, center_id=None, resource_id=None):
    query = InventoryTransaction.query.order_by(InventoryTransaction.transaction_date.desc())
    if center_id or resource_id:
        query = query.join(Inventory)
        if center_id:
            query = query.filter(Inventory.relief_center_id == center_id)
        if resource_id:
            query = query.filter(Inventory.resource_id == resource_id)
    return query.limit(limit).all()


def consumption_history(resource_id: int, days: int = 14) -> float:
    """Average daily OUT consumption for a resource across all centers."""
    since = datetime.combine(date.fromordinal(date.today().toordinal() - days), datetime.min.time())
    total_out = (
        db.session.query(db.func.coalesce(db.func.sum(InventoryTransaction.quantity), 0))
        .join(Inventory)
        .filter(
            Inventory.resource_id == resource_id,
            InventoryTransaction.transaction_type == "OUT",
            InventoryTransaction.transaction_date >= since,
        )
        .scalar()
    )
    return round(float(total_out) / days, 2)
