"""Delivery tracking service with enforced status transitions (rule 9)."""
import logging
from datetime import datetime

from ..extensions import db
from ..models.allocation import Allocation
from ..models.delivery import Delivery, DeliveryEvent
from ..services import inventory_service
from ..utils.constants import DELIVERY_TRANSITIONS

logger = logging.getLogger("relief.delivery")


class DeliveryError(Exception):
    pass


def create_delivery(data: dict, user) -> Delivery:
    from ..models.relief_center import ReliefCenter
    from ..models.emergency import AffectedArea

    allocation = db.session.get(Allocation, data.get("allocation_id"))
    if not allocation:
        raise DeliveryError("Allocation not found")
    source = db.session.get(ReliefCenter, data.get("source_center") or allocation.relief_center_id)
    destination = db.session.get(AffectedArea, data.get("destination_area") or allocation.relief_request.area_id)
    if not source or not destination:
        raise DeliveryError("Source center and destination area are required")
    if delivery_exists_for(allocation.id):
        raise DeliveryError(f"Delivery already exists for allocation #{allocation.id}")

    delivery = Delivery(
        allocation_id=allocation.id,
        assigned_to=data.get("assigned_to"),
        source_center=source.id,
        destination_area=destination.id,
        expected_delivery_date=data.get("expected_delivery_date"),
        status="PREPARING",
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(delivery)
    db.session.flush()
    db.session.add(DeliveryEvent(
        delivery_id=delivery.id, status="PREPARING",
        note="Delivery created", updated_by=getattr(user, "id", None),
    ))
    db.session.commit()
    logger.info("Delivery %s created for allocation %s", delivery.id, allocation.id)
    return delivery


def delivery_exists_for(allocation_id: int) -> bool:
    return db.session.query(
        Delivery.query.filter_by(allocation_id=allocation_id).exists()
    ).scalar()


def update_status(delivery_id: int, new_status: str, user, note: str = None) -> Delivery:
    from ..utils.constants import DELIVERY_STATUSES

    if new_status not in DELIVERY_STATUSES:
        raise DeliveryError(f"Invalid status '{new_status}'")
    delivery = db.session.get(Delivery, delivery_id)
    if not delivery:
        raise DeliveryError("Delivery not found")

    allowed = DELIVERY_TRANSITIONS[delivery.status]
    if new_status not in allowed:
        raise DeliveryError(
            f"Illegal transition {delivery.status} -> {new_status}. "
            f"Allowed next states: {sorted(allowed) or 'none (terminal)'}"
        )

    claims_role = getattr(user, "role", None)
    if new_status in ("DISPATCHED", "IN_TRANSIT", "DELIVERED", "FAILED") and \
            claims_role == "ADMIN":
        pass  # admins may perform logistics updates too
    elif claims_role not in ("VOLUNTEER_LOGISTICS", "ADMIN"):
        raise PermissionError("Only logistics volunteers or admins can update delivery status")

    delivery.status = new_status
    now = datetime.utcnow()
    if new_status == "DISPATCHED":
        delivery.dispatch_date = now
        _dispatch_stock(delivery, user)
    elif new_status == "DELIVERED":
        delivery.actual_delivery_date = now
        req = delivery.allocation.relief_request
        req.status = "COMPLETED"
    elif new_status in ("FAILED", "CANCELLED"):
        _release_on_failure(delivery, user)

    db.session.add(DeliveryEvent(
        delivery_id=delivery.id, status=new_status,
        note=(note or f"Status changed to {new_status}")[:250],
        updated_by=getattr(user, "id", None),
    ))
    db.session.commit()
    logger.info("Delivery %s -> %s by user=%s", delivery.id, new_status, getattr(user, "id", None))
    return delivery


def _dispatch_stock(delivery: Delivery, user) -> None:
    """Reserved units physically leave the source center at dispatch."""
    for item in delivery.allocation.items:
        inv_row = _find_reserved_row(delivery.source_center, item.resource_id)
        inventory_service.convert_reservation_to_outbound(
            inv_row.id, item.quantity,
            performed_by=getattr(user, "id", None),
            reference_type="DELIVERY", reference_id=delivery.id,
        )
    delivery.allocation.status = "DISPATCHED"
    req = delivery.allocation.relief_request
    if req.status in ("ALLOCATED", "PARTIALLY_ALLOCATED"):
        req.status = "IN_DELIVERY"


def _find_reserved_row(center_id: int, resource_id: int):
    from ..models.inventory import Inventory

    row = (
        Inventory.query.filter_by(relief_center_id=center_id, resource_id=resource_id)
        .filter(Inventory.quantity_reserved > 0)
        .first()
    )
    if row is None:
        raise DeliveryError(
            f"No reserved stock found at center {center_id} for resource {resource_id} to dispatch"
        )
    return row


def _release_on_failure(delivery: Delivery, user) -> None:
    """If dispatch has not happened yet, reserved stock returns to the pool."""
    dispatched_before = bool(delivery.dispatch_date)
    if dispatched_before:
        return
    for item in delivery.allocation.items:
        inv_row = (
            Inventory.query.filter_by(resource_id=item.resource_id)
            .filter(Inventory.quantity_reserved > 0, Inventory.relief_center_id == delivery.source_center)
            .first()
        )
        if inv_row:
            inventory_service.release_reserved(
                inv_row.id, min(item.quantity, inv_row.quantity_reserved),
                performed_by=getattr(user, "id", None),
                reference_type="DELIVERY_FAIL", reference_id=delivery.id,
            )
    req = delivery.allocation.relief_request
    if req.status == "IN_DELIVERY":
        req.status = "ALLOCATED"


def assign_volunteer(delivery_id: int, volunteer_id: int | None) -> Delivery:
    delivery = db.session.get(Delivery, delivery_id)
    if not delivery:
        raise DeliveryError("Delivery not found")
    if volunteer_id is not None:
        from ..models.user import User

        volunteer = db.session.get(User, volunteer_id)
        if not volunteer or volunteer.role != "VOLUNTEER_LOGISTICS":
            raise DeliveryError("Assigned user must be an active VOLUNTEER_LOGISTICS account")
    delivery.assigned_to = volunteer_id
    db.session.commit()
    return delivery


def list_deliveries(status=None, assigned_to=None):
    query = Delivery.query.order_by(Delivery.id.desc())
    if status:
        query = query.filter_by(status=status)
    if assigned_to:
        query = query.filter_by(assigned_to=assigned_to)
    return query.all()
