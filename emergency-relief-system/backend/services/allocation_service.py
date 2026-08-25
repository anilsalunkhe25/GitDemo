"""Resource allocation engine (business rules 2, 3, 8, 10, 12).

Sorts pending/approved requests by transparent priority score, reserves
non-expired stock across relief centers (FIFO by expiry), creates traceable
Allocation + AllocationItem + InventoryTransaction rows and a Delivery in
PREPARING state. Partial fulfilment is supported explicitly.
"""
import logging
from datetime import date, timedelta

from ..extensions import db
from ..models.allocation import Allocation, AllocationItem
from ..models.delivery import Delivery, DeliveryEvent
from ..models.demand_forecast import Notification
from ..models.inventory import Inventory, InventoryTransaction
from ..models.relief_center import ReliefCenter
from ..models.relief_request import ReliefRequest

logger = logging.getLogger("relief.allocation")

ALLOCATABLE_STATUSES = ("PENDING", "APPROVED", "WAITING_FOR_STOCK")


class AllocationError(Exception):
    pass


def _available_batches(resource_id: int):
    return (
        Inventory.query.filter(
            Inventory.resource_id == resource_id,
            Inventory.quantity_available > 0,
            db.or_(Inventory.expiry_date.is_(None), Inventory.expiry_date >= date.today()),
        )
        .join(ReliefCenter)
        .filter(ReliefCenter.status == "ACTIVE")
        .order_by(Inventory.expiry_date.asc().nullslast(), Inventory.id.asc())
        .all()
    )


def run_allocation(user=None, emergency_id=None, request_ids=None) -> dict:
    """Execute the allocation engine over the eligible queue."""
    query = ReliefRequest.query.filter(ReliefRequest.status.in_(ALLOCATABLE_STATUSES))
    if emergency_id:
        query = query.filter(ReliefRequest.emergency_id == emergency_id)
    if request_ids:
        query = query.filter(ReliefRequest.id.in_(request_ids))
    queue = query.order_by(ReliefRequest.priority_score.desc(), ReliefRequest.requested_at.asc()).all()

    if not queue:
        raise AllocationError("No pending or approved requests are waiting for allocation")

    results = []
    for req in queue:
        try:
            results.append(_allocate_single(req, user))
        except Exception as exc:
            logger.exception("Allocation failed for request %s", req.id)
            db.session.rollback()
            results.append({"request_id": req.id, "status": "ERROR", "message": str(exc)})
    db.session.commit()

    summary = {
        "processed": len(results),
        "fully_allocated": sum(1 for r in results if r.get("status") == "ALLOCATED"),
        "partially_allocated": sum(1 for r in results if r.get("status") == "PARTIALLY_ALLOCATED"),
        "waiting_for_stock": sum(1 for r in results if r.get("status") == "WAITING_FOR_STOCK"),
        "results": results,
    }
    logger.info(
        "Allocation run by user=%s: %s full, %s partial, %s waiting",
        getattr(user, "id", None), summary["fully_allocated"],
        summary["partially_allocated"], summary["waiting_for_stock"],
    )
    return summary


def _allocate_single(req, user) -> dict:
    batches = _available_batches(req.resource_id)

    remaining = req.quantity - (req.allocated_quantity or 0)
    if remaining <= 0:
        return {"request_id": req.id, "status": req.status, "message": "Already fully allocated"}

    picks = []
    for batch in batches:
        take = min(batch.quantity_available, remaining)
        batch.quantity_available -= take
        batch.quantity_reserved += take
        db.session.add(InventoryTransaction(
            inventory_id=batch.id,
            transaction_type="RESERVE",
            quantity=take,
            reference_type="ALLOCATION",
            performed_by=getattr(user, "id", None),
        ))
        picks.append((batch, take))
        remaining -= take
        if remaining == 0:
            break

    allocated_qty = (req.quantity - (req.allocated_quantity or 0)) - max(remaining, 0)
    unit = req.resource.unit or "units"

    if not picks:
        _notify_waiting(req)
        req.status = "WAITING_FOR_STOCK"
        return {
            "request_id": req.id,
            "status": "WAITING_FOR_STOCK",
            "requested": req.quantity,
            "allocated": 0,
            "message": f"No unexpired stock available for {req.resource.name}; request queued",
        }

    primary_center = picks[0][0].relief_center
    allocation = Allocation(
        relief_request_id=req.id,
        relief_center_id=primary_center.id,
        allocated_by=getattr(user, "id", None),
        status="RESERVED",
    )
    db.session.add(allocation)
    db.session.flush()

    item_rows = []
    for batch, take in picks:
        db.session.add(AllocationItem(
            allocation_id=allocation.id, resource_id=batch.resource_id, quantity=take
        ))
        item_rows.append({
            "inventory_id": batch.id,
            "center": batch.relief_center.name,
            "quantity": take,
            "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
        })

    delivery = Delivery(
        allocation_id=allocation.id,
        source_center=primary_center.id,
        destination_area=req.area_id,
        expected_delivery_date=date.today() + timedelta(days=2),
        status="PREPARING",
        notes=f"Auto-created for allocation #{allocation.id}",
    )
    db.session.add(delivery)
    db.session.flush()
    db.session.add(DeliveryEvent(
        delivery_id=delivery.id, status="PREPARING",
        note="Allocation reserved; preparing consignment",
        updated_by=getattr(user, "id", None),
    ))

    req.allocated_quantity = (req.allocated_quantity or 0) + allocated_qty
    req.status = "ALLOCATED" if req.allocated_quantity >= req.quantity else "PARTIALLY_ALLOCATED"

    if req.status == "PARTIALLY_ALLOCATED":
        db.session.add(Notification(
            type="WARNING",
            title=f"Partial allocation for request #{req.id}",
            message=f"{remaining} {unit} still needed beyond current stock",
            reference_type="relief_request",
            reference_id=req.id,
        ))

    return {
        "request_id": req.id,
        "priority_score": round(req.priority_score, 1),
        "priority_level": req.priority_level,
        "status": req.status,
        "requested": req.quantity,
        "total_allocated": req.allocated_quantity,
        "allocated_now": allocated_qty,
        "still_needed": max(req.quantity - req.allocated_quantity, 0),
        "stock_sources": item_rows,
        "allocation_id": allocation.id,
        "delivery_id": delivery.id,
        "message": (
            f"Allocated {allocated_qty} of {req.quantity} {unit}"
            if req.status == "PARTIALLY_ALLOCATED"
            else f"Fully allocated ({allocated_qty} {unit})"
        ),
    }


def _notify_waiting(req) -> None:
    db.session.add(Notification(
        type="CRITICAL",
        title=f"Stock-out: request #{req.id}",
        message=(
            f"{req.quantity} units of {req.resource.name} requested for "
            f"{req.area.area_name} cannot be fulfilled from any center"
        ),
        reference_type="relief_request",
        reference_id=req.id,
    ))


def cancel_allocation(allocation_id: int, user) -> dict:
    """Release reserved stock back to availability (traceability rule 8)."""
    from ..services import inventory_service

    allocation = db.session.get(Allocation, allocation_id)
    if not allocation:
        raise AllocationError("Allocation not found")
    if allocation.status != "RESERVED":
        raise AllocationError(f"Only RESERVED allocations can be cancelled (current: {allocation.status})")

    released = []
    total_qty = 0
    for item in allocation.items:
        inv_row = (
            Inventory.query.filter_by(resource_id=item.resource_id)
            .filter(Inventory.quantity_reserved > 0, Inventory.relief_center_id == allocation.relief_center_id)
            .first()
        )
        qty = item.quantity if inv_row else 0
        if inv_row and inv_row.quantity_reserved > 0:
            released_qty = min(qty, inv_row.quantity_reserved)
            inventory_service.release_reserved(
                inv_row.id, released_qty,
                performed_by=getattr(user, "id", None),
                reference_type="ALLOCATION_CANCEL", reference_id=allocation.id, commit=False,
            )
            released.append({"inventory_id": inv_row.id, "released": released_qty})
        total_qty += item.quantity

    allocation.status = "CANCELLED"
    req = allocation.relief_request
    req.allocated_quantity = max((req.allocated_quantity or 0) - total_qty, 0)
    if req.status in ("ALLOCATED", "PARTIALLY_ALLOCATED"):
        req.status = "APPROVED" if req.allocated_quantity == 0 else "PARTIALLY_ALLOCATED"
    for dlv in allocation.deliveries:
        if dlv.status == "PREPARING":
            dlv.status = "CANCELLED"
            db.session.add(DeliveryEvent(
                delivery_id=dlv.id, status="CANCELLED",
                note="Allocation cancelled; stock returned to pool",
                updated_by=getattr(user, "id", None),
            ))
    db.session.commit()
    logger.info("Allocation %s cancelled by user=%s", allocation_id, getattr(user, "id", None))
    return {"allocation_id": allocation.id, "released": released}


def list_allocations(status=None):
    query = Allocation.query.order_by(Allocation.allocation_date.desc())
    if status:
        query = query.filter_by(status=status)
    return query.all()
