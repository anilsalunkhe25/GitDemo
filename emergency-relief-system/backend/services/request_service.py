"""Relief request service: creation, priority scoring, approval workflow."""
import logging
from datetime import date

from ..extensions import db
from ..models.emergency import AffectedArea, Emergency
from ..models.inventory import Inventory
from ..models.relief_request import ReliefRequest
from ..models.resource import Resource
from ..utils.constants import REQUEST_STATUSES
from ..utils.priority import calculate_priority
from ..utils.validators import (
    ValidationError,
    validate_choice,
    validate_positive_int,
    validate_required,
)

logger = logging.getLogger("relief.requests")


class ServiceError(Exception):
    pass


def total_available_stock(resource_id: int) -> int:
    return int(
        db.session.query(db.func.coalesce(db.func.sum(Inventory.quantity_available), 0))
        .filter(
            Inventory.resource_id == resource_id,
            db.or_(Inventory.expiry_date.is_(None), Inventory.expiry_date >= date.today()),
        )
        .scalar()
    )


def compute_request_priority(emergency: Emergency, area: AffectedArea | None,
                             resource_id: int, quantity: int, urgency: str, required_by) -> dict:
    available = total_available_stock(resource_id)
    return calculate_priority(
        emergency_severity=emergency.severity,
        population_affected=area.population_affected if area else 0,
        quantity_requested=quantity,
        total_available_stock=available,
        urgency=urgency,
        required_by=required_by,
    )


def create_request(data: dict, user=None):
    emergency = db.session.get(Emergency, data.get("emergency_id"))
    if not emergency:
        raise ValidationError("Emergency not found")
    area = db.session.get(AffectedArea, data.get("area_id"))
    if not area or area.emergency_id != emergency.id:
        raise ValidationError("Affected area not found for this emergency")
    resource = db.session.get(Resource, data.get("resource_id"))
    if not resource:
        raise ValidationError("Resource not found")
    quantity = validate_positive_int(data.get("quantity"), "quantity")
    urgency = validate_choice(data.get("urgency", "MEDIUM"), ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "urgency")
    required_by_raw = validate_required(data.get("required_by"), "required_by")
    try:
        from datetime import datetime as _dt

        required_by = _dt.strptime(str(required_by_raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError("required_by must be in YYYY-MM-DD format")

    scoring = compute_request_priority(emergency, area, resource.id, quantity, urgency, required_by)

    request = ReliefRequest(
        emergency_id=emergency.id,
        area_id=area.id,
        requested_by=user.id if user else None,
        resource_id=resource.id,
        people_affected=data.get("people_affected") or area.population_affected,
        description=(data.get("description") or "").strip() or None,
        quantity=quantity,
        urgency=urgency,
        priority_score=scoring["score"],
        priority_breakdown=__import__("json").dumps(scoring["breakdown"]),
        required_by=required_by,
    )
    db.session.add(request)
    db.session.commit()
    logger.info("Relief request %s created (priority=%s level=%s)", request.id, scoring["score"], scoring["level"])
    return request


def approve_request(request_id: int, approver) -> ReliefRequest:
    req = get_request_or_fail(request_id)
    if req.status != "PENDING":
        raise ServiceError(f"Only PENDING requests can be approved (current: {req.status})")
    req.status = "APPROVED"
    req.approved_by = getattr(approver, "id", None)
    db.session.commit()
    logger.info("Request %s approved by user %s", req.id, req.approved_by)
    return req


def reject_request(request_id: int, reason: str, approver) -> ReliefRequest:
    req = get_request_or_fail(request_id)
    if req.status not in ("PENDING", "APPROVED"):
        raise ServiceError(f"Request in status {req.status} cannot be rejected")
    if not reason:
        raise ValidationError("A rejection reason is required")
    req.status = "REJECTED"
    req.rejection_reason = reason[:255]
    req.approved_by = getattr(approver, "id", None)
    db.session.commit()
    logger.info("Request %s rejected by user %s", req.id, req.approved_by)
    return req


def update_request(request_id: int, data: dict) -> ReliefRequest:
    req = get_request_or_fail(request_id)
    editable_statuses = ("PENDING", "APPROVED", "WAITING_FOR_STOCK")
    if req.status not in editable_statuses:
        raise ServiceError(f"Request cannot be edited while status is {req.status}")

    if "quantity" in data:
        req.quantity = validate_positive_int(data["quantity"], "quantity")
    if "urgency" in data:
        req.urgency = validate_choice(data["urgency"], ["LOW", "MEDIUM", "HIGH", "CRITICAL"], "urgency")
    if "description" in data:
        req.description = (data["description"] or "").strip() or None
    if "required_by" in data and data["required_by"]:
        from datetime import datetime as _dt

        try:
            req.required_by = _dt.strptime(str(data["required_by"])[:10], "%Y-%m-%d").date()
        except ValueError:
            raise ValidationError("required_by must be in YYYY-MM-DD format")

    rescoring = compute_request_priority(req.emergency, req.area, req.resource_id, req.quantity, req.urgency, req.required_by)
    req.priority_score = rescoring["score"]
    req.priority_breakdown = __import__("json").dumps(rescoring["breakdown"])
    db.session.commit()
    return req


def delete_request(request_id: int) -> None:
    req = get_request_or_fail(request_id)
    if req.status not in ("PENDING", "REJECTED"):
        raise ServiceError(f"Only PENDING or REJECTED requests can be deleted (current: {req.status})")
    db.session.delete(req)
    db.session.commit()


def get_request_or_fail(request_id) -> ReliefRequest:
    req = db.session.get(ReliefRequest, request_id)
    if not req:
        raise RecordNotFoundErr(f"Relief request {request_id} not found")
    return req


class RecordNotFoundErr(Exception):
    pass


def list_requests(status=None, emergency_id=None, resource_id=None, min_priority=None):
    query = ReliefRequest.query
    if status:
        statuses = [status] if isinstance(status, str) else list(status)
        for s in statuses:
            validate_choice(s, REQUEST_STATUSES, "status")
        query = query.filter(ReliefRequest.status.in_(statuses))
    if emergency_id:
        query = query.filter_by(emergency_id=emergency_id)
    if resource_id:
        query = query.filter_by(resource_id=resource_id)
    if min_priority is not None:
        query = query.filter(ReliefRequest.priority_score >= float(min_priority))
    return query.order_by(ReliefRequest.priority_score.desc(), ReliefRequest.requested_at).all()
