"""Aggregated KPIs, alerts and chart datasets for the admin dashboard."""
from datetime import date, datetime, timedelta

from ..extensions import db
from ..models.delivery import Delivery
from ..models.demand_forecast import DemandForecast, Notification
from ..models.emergency import Emergency
from ..models.inventory import Inventory
from ..models.relief_request import ReliefRequest
from ..services.inventory_service import expiring_soon, low_stock_resources


def _count(query) -> int:
    return int(query.count())


def summary() -> dict:
    today = date.today()

    active_emergencies = _count(Emergency.query.filter(Emergency.status.in_(["ACTIVE", "MONITORING"])))
    pending_requests = _count(ReliefRequest.query.filter_by(status="PENDING"))
    critical_requests = _count(
        ReliefRequest.query.filter(
            ReliefRequest.priority_score >= 81,
            ReliefRequest.status.in_(["PENDING", "APPROVED", "WAITING_FOR_STOCK"]),
        )
    )
    open_requests = _count(
        ReliefRequest.query.filter(
            ReliefRequest.status.notin_(["COMPLETED", "REJECTED"])
        )
    )
    active_deliveries = _count(Delivery.query.filter(Delivery.status.in_(["PREPARING", "DISPATCHED", "IN_TRANSIT"])))
    failed_deliveries = _count(Delivery.query.filter_by(status="FAILED"))

    total_available = int(db.session.query(db.func.coalesce(db.func.sum(Inventory.quantity_available), 0)).scalar())
    low_stock = low_stock_resources()
    expired_batches = _count(
        Inventory.query.filter(Inventory.expiry_date.isnot(None))
        .filter(Inventory.expiry_date < today)
        .filter(Inventory.quantity_available > 0)
    )
    latest_shortage_rows = (
        db.session.query(DemandForecast)
        .filter(DemandForecast.expected_shortage > 0)
        .order_by(DemandForecast.created_at.desc())
        .limit(10).all()
    )
    expected_shortages = len(latest_shortage_rows)

    kpis = {
        "active_emergencies": active_emergencies,
        "pending_requests": pending_requests,
        "open_requests": open_requests,
        "critical_requests": critical_requests,
        "available_resources_units": total_available,
        "low_stock_items": len(low_stock),
        "expired_batches": expired_batches,
        "active_deliveries": active_deliveries,
        "failed_deliveries": failed_deliveries,
        "expected_shortages": expected_shortages,
    }

    alerts = build_alerts(critical_requests, low_stock, expired_batches, failed_deliveries, latest_shortage_rows)

    charts = {
        "requests_by_priority": requests_by_priority(),
        "requests_by_status": requests_by_status(),
        "inventory_by_category": inventory_by_category(),
        "delivery_status": delivery_status_chart(),
        "emergency_severity": emergency_severity_chart(),
        "shortage_by_resource": shortage_by_resource(latest_shortage_rows),
        "consumption_last_7_days": consumption_trend(),
    }

    return {"kpis": kpis, "alerts": alerts, "charts": charts, "generated_at": datetime.utcnow().isoformat()}


def build_alerts(critical_requests, low_stock, expired_batches, failed_deliveries, shortages) -> list[dict]:
    alerts: list[dict] = []
    if critical_requests:
        alerts.append({"level": "CRITICAL", "title": f"{critical_requests} critical relief request(s)",
                       "message": "Requests scoring 81+ are waiting for action."})
    for item in low_stock:
        if item["severity"] == "CRITICAL":
            alerts.append({"level": "CRITICAL", "title": f"Stock-out risk: {item['resource_name']}",
                           "message": item["message"]})
    if expired_batches:
        alerts.append({"level": "CRITICAL", "title": f"{expired_batches} expired batch(es)",
                       "message": "Expired stock must be written off and cannot be allocated."})
    if failed_deliveries:
        alerts.append({"level": "CRITICAL", "title": f"{failed_deliveries} failed delivery(ies)",
                       "message": "Failed deliveries need re-dispatch decisions."})
    for fc in shortages[:5]:
        alerts.append({
            "level": "WARNING",
            "title": f"Forecasted {fc.resource.name} shortage",
            "message": (f"Predicted {round(fc.predicted_quantity)} vs stock {fc.current_stock} "
                        f"-> shortage {round(fc.expected_shortage)}"),
        })
    for item in low_stock:
        if item["severity"] != "CRITICAL":
            alerts.append({"level": "WARNING", "title": f"Low stock: {item['resource_name']}",
                           "message": item["message"]})
    for center_row in over_capacity_centers():
        alerts.append({
            "level": "WARNING",
            "title": f"Capacity {center_row['utilization_pct']}% at {center_row['name']}",
            "message": "Storage utilization exceeded the 80% warning threshold.",
        })
    new_requests = _count(ReliefRequest.query.filter_by(status="PENDING"))
    if new_requests:
        alerts.append({"level": "INFO", "title": f"{new_requests} new request(s)",
                       "message": "Pending requests await triage and approval."})
    return alerts[:20]


def over_capacity_centers(threshold_pct: float | None = None) -> list[dict]:
    from flask import current_app

    threshold = threshold_pct or current_app.config["CENTER_CAPACITY_WARNING_PCT"]
    rows = []
    for center in __import__("backend.models.relief_center", fromlist=["ReliefCenter"]).ReliefCenter.query.all():
        if center.utilization_pct > threshold:
            rows.append({"id": center.id, "name": center.name, "utilization_pct": center.utilization_pct})
    return rows


def requests_by_priority() -> list[dict]:
    rows = ReliefRequest.query.filter(ReliefRequest.status.notin_(["REJECTED"])).all()
    buckets = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for r in rows:
        buckets[r.priority_level] += 1
    return [{"priority": k, "count": v} for k, v in buckets.items()]


def requests_by_status() -> list[dict]:
    rows = (
        db.session.query(ReliefRequest.status, db.func.count(ReliefRequest.id))
        .group_by(ReliefRequest.status).all()
    )
    return [{"status": s, "count": c} for s, c in rows]


def inventory_by_category() -> list[dict]:
    from ..models.resource import Resource

    rows = (
        db.session.query(Resource.category,
                         db.func.coalesce(db.func.sum(Inventory.quantity_available), 0))
        .outerjoin(Inventory, Inventory.resource_id == Resource.id)
        .group_by(Resource.category).all()
    )
    return [{"category": cat, "units": int(units)} for cat, units in rows]


def delivery_status_chart() -> list[dict]:
    rows = db.session.query(Delivery.status, db.func.count(Delivery.id)).group_by(Delivery.status).all()
    return [{"status": s, "count": c} for s, c in rows]


def emergency_severity_chart() -> list[dict]:
    from ..utils.constants import SEVERITIES

    counts = {s: 0 for s in SEVERITIES}
    for sev, cnt in db.session.query(Emergency.severity, db.func.count()).group_by(Emergency.severity):
        counts[sev] = cnt
    return [{"severity": s, "count": c} for s, c in counts.items()]


def shortage_by_resource(forecasts) -> list[dict]:
    agg: dict[str, float] = {}
    for fc in forecasts:
        if fc.expected_shortage > 0:
            name = fc.resource.name
            agg[name] = round(max(agg.get(name, 0), fc.expected_shortage), 1)
    return [{"resource": k, "expected_shortage": v} for k, v in sorted(agg.items(), key=lambda x: -x[1])]


def consumption_trend(days: int = 7) -> list[dict]:
    from ..models.inventory import InventoryTransaction

    since = datetime.combine(today := date.today() - timedelta(days=days - 1), datetime.min.time())
    rows = (
        db.session.query(
            db.func.date(InventoryTransaction.transaction_date),
            db.func.coalesce(db.func.sum(InventoryTransaction.quantity), 0),
        )
        .filter(InventoryTransaction.transaction_type == "OUT",
                InventoryTransaction.transaction_date >= since)
        .group_by(db.func.date(InventoryTransaction.transaction_date))
        .all()
    )
    by_day = {str(d): int(q) for d, q in rows}
    series = []
    d = since.date()
    while d <= date.today():
        key = d.isoformat()
        series.append({"date": key, "out_units": by_day.get(key, 0)})
        d = date.fromordinal(d.toordinal() + 1)
    return series
