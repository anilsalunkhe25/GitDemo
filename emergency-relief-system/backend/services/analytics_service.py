"""Analytics aggregations for the analytics page."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models.delivery import Delivery
from ..models.demand_forecast import DemandForecast
from ..models.emergency import AffectedArea, Emergency
from ..models.inventory import InventoryTransaction
from ..models.relief_request import ReliefRequest


def _filtered_requests(emergency_id=None, resource_id=None, area_id=None,
                       start_date=None, end_date=None):
    query = ReliefRequest.query
    if emergency_id:
        query = query.filter(ReliefRequest.emergency_id == emergency_id)
    if resource_id:
        query = query.filter(ReliefRequest.resource_id == resource_id)
    if area_id:
        query = query.filter(ReliefRequest.area_id == area_id)
    if start_date:
        query = query.filter(ReliefRequest.requested_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(
            ReliefRequest.requested_at <= datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        )
    return query


def overview(**filters) -> dict:
    requests = _filtered_requests(**filters).all()
    total = len(requests)
    completed = sum(1 for r in requests if r.status == "COMPLETED")
    pending = sum(1 for r in requests if r.status in ("PENDING", "APPROVED", "WAITING_FOR_STOCK"))
    rejected = sum(1 for r in requests if r.status == "REJECTED")

    response_times = []
    for req in requests:
        if req.status in ("ALLOCATED", "PARTIALLY_ALLOCATED", "IN_DELIVERY", "COMPLETED"):
            alloc = next((a for a in req.allocations if a.allocation_date), None)
            if alloc and req.requested_at:
                delta = (alloc.allocation_date - req.requested_at).total_seconds() / 3600
                response_times.append(max(delta, 0))

    allocated_units = sum(req.allocated_quantity or 0 for req in requests)

    deliveries = Delivery.query.all()
    delivered = sum(1 for d in deliveries if d.status == "DELIVERED")
    delivery_total = len([d for d in deliveries if d.status not in ("CANCELLED",)])

    most_requested: dict[str, int] = {}
    for req in requests:
        most_requested[req.resource.name] = most_requested.get(req.resource.name, 0) + req.quantity

    most_affected: dict[str, int] = {}
    for req in requests:
        area_name = req.area.area_name
        most_affected[area_name] = max(most_affected.get(area_name, 0), req.people_affected or 0)

    forecast_rows = DemandForecast.query.order_by(DemandForecast.created_at.desc()).limit(30).all()
    forecast_vs_actual = [
        {
            "resource": fc.resource.name,
            "predicted": round(fc.predicted_quantity, 1),
            "actual_requested": fc.resource and round(
                float(db.session.query(db.func.coalesce(db.func.sum(ReliefRequest.quantity), 0))
                      .filter(ReliefRequest.resource_id == fc.resource_id).scalar()), 1),
            "expected_shortage": round(fc.expected_shortage, 1),
        }
        for fc in forecast_rows[:8]
    ]

    shortage_trend = (
        db.session.query(db.func.date(DemandForecast.created_at),
                         db.func.sum(DemandForecast.expected_shortage))
        .group_by(db.func.date(DemandForecast.created_at))
        .order_by(db.func.date(DemandForecast.created_at))
        .all()
    )

    return {
        "totals": {
            "requests": total,
            "completed": completed,
            "pending_or_open": pending,
            "rejected": rejected,
            "completion_rate_pct": round(completed / total * 100, 1) if total else 0.0,
            "avg_response_hours": round(sum(response_times) / len(response_times), 1) if response_times else None,
            "units_allocated": allocated_units,
            "delivery_completion_rate_pct":
                round(delivered / delivery_total * 100, 1) if delivery_total else 0.0,
        },
        "most_requested_resources": sorted(
            [{"resource": k, "quantity": v} for k, v in most_requested.items()],
            key=lambda x: -x["quantity"])[:10],
        "most_affected_areas": sorted(
            [{"area": k, "population": v} for k, v in most_affected.items()],
            key=lambda x: -x["population"])[:10],
        "forecast_vs_actual": forecast_vs_actual,
        "shortage_trend": [{"date": str(d), "shortage": float(s or 0)} for d, s in shortage_trend],
    }
