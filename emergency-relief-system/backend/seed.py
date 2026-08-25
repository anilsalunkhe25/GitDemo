"""Database seeding for instant demo readiness.

Run: python -m backend.seed
Idempotent - skips when an admin already exists.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, timedelta

from .app import create_app
from .extensions import db
from .models.demand_forecast import Notification
from .models.allocation import Allocation  # noqa: F401
from .models.delivery import Delivery, DeliveryEvent
from .models.emergency import AffectedArea, Emergency
from .models.inventory import Inventory, InventoryTransaction
from .models.relief_center import ReliefCenter
from .models.relief_request import ReliefRequest
from .models.resource import Resource
from .models.user import User
from .services.inventory_service import add_stock
from .services.request_service import compute_request_priority

logger = logging.getLogger("relief.seed")

USERS = [
    ("Dr. Anjali Deshmukh", "admin@relief.local", "ADMIN", "9822000001"),
    ("Rahul Patil", "operator1@relief.local", "RELIEF_CENTER_OPERATOR", "9822000002"),
    ("Sunita Kulkarni", "operator2@relief.local", "RELIEF_CENTER_OPERATOR", "9822000003"),
    ("Vikram Jadhav", "volunteer1@relief.local", "VOLUNTEER_LOGISTICS", "9822000004"),
    ("Meera Shah", "volunteer2@relief.local", "VOLUNTEER_LOGISTICS", "9822000005"),
    ("Arjun Nair", "volunteer3@relief.local", "VOLUNTEER_LOGISTICS", "9822000006"),
]
DEFAULT_PASSWORD = "Admin@123"

RESOURCES = [
    ("Drinking Water", "WATER", "liters", None, 5000),
    ("Rice Bags (10kg)", "FOOD", "bags", 365, 800),
    ("Wheat Flour (10kg)", "FOOD", "bags", 240, 600),
    ("Ready-to-Eat Meals", "FOOD", "packs", 90, 1500),
    ("Paracetamol 500mg", "MEDICINE", "strips", 540, 400),
    ("ORS Sachets", "MEDICINE", "boxes", 450, 300),
    ("Antibiotic Course", "MEDICINE", "courses", 365, 150),
    ("Thermal Blankets", "BLANKETS", "units", None, 700),
    ("Hygiene Kits", "HYGIENE_KITS", "kits", None, 600),
    ("Baby Food Packs", "BABY_SUPPLIES", "packs", 120, 250),
    ("Baby Diapers", "BABY_SUPPLIES", "packs", None, 300),
    ("First Aid Kits", "FIRST_AID_KITS", "kits", 730, 200),
]

CENTERS = [
    ("Kolhapur Central Relief Hub", "Kolhapur", "Station Road, Kolhapur", 60000, "operator1@relief.local"),
    ("Sangli District Warehouse", "Sangli", "Miraj Road, Sangli", 45000, "operator1@relief.local"),
    ("Karad Transit Center", "Karad", "Krishna Nagar, Karad", 30000, "operator2@relief.local"),
    ("Pune Regional Depot", "Pune", "Bhosari MIDC, Pune", 80000, "operator2@relief.local"),
    ("Satara Field Base", "Satara", "Powai Naka, Satara", 22000, "operator2@relief.local"),
]


def seed() -> dict:
    app = create_app()
    with app.app_context():
        if User.query.filter_by(role="ADMIN").first():
            logger.info("Database already seeded; skipping")
            return {"seeded": False, "message": "Database already contains data"}

        rng = random.Random(42)
        today = date.today()

        users: dict[str, User] = {}
        for name, email, role, phone in USERS:
            user = User(name=name, email=email, role=role, phone=phone)
            user.set_password(DEFAULT_PASSWORD)
            db.session.add(user)
            users[email] = user
        db.session.flush()
        admin = users["admin@relief.local"]

        flood = Emergency(
            name="Krishna Basin Monsoon Flood", type="FLOOD",
            description="Severe flooding across Krishna river basin due to record rainfall.",
            start_date=today - timedelta(days=6), expected_duration=21,
            severity="CRITICAL", status="ACTIVE", created_by=admin.id,
        )
        quake = Emergency(
            name="Western Ghats Earthquake", type="EARTHQUAKE",
            description="Moderate earthquake damaging villages in the Western Ghats belt.",
            start_date=today - timedelta(days=12), expected_duration=14,
            severity="HIGH", status="MONITORING", created_by=admin.id,
        )
        cyclone = Emergency(
            name="Cyclone Tejas Coastal Impact", type="CYCLONE",
            description="Coastal cyclone with wind damage and storm surge displacement.",
            start_date=today + timedelta(days=1), expected_duration=10,
            severity="MEDIUM", status="ACTIVE", created_by=admin.id,
        )
        db.session.add_all([flood, quake, cyclone])
        db.session.flush()

        area_defs = [
            (flood, "Kolhapur Area A", 5200, "CRITICAL", 16.70, 74.24),
            (flood, "Kolhapur Area B (Rural)", 3800, "HIGH", 16.55, 74.35),
            (flood, "Sangli North", 4600, "HIGH", 16.85, 74.58),
            (flood, "Sangli South Belt", 2900, "MEDIUM", 16.72, 74.99),
            (flood, "Karad Riverside", 2100, "MEDIUM", 17.28, 74.18),
            (quake, "Ghat Village Cluster", 1750, "CRITICAL", 17.93, 73.65),
            (quake, "Hillside Settlements", 980, "HIGH", 18.02, 73.71),
            (quake, "Wai Taluka", 1450, "MEDIUM", 17.94, 74.23),
            (cyclone, "Coastal Guhagar", 2300, "HIGH", 17.49, 73.39),
            (cyclone, "Dabhol Port Zone", 1600, "MEDIUM", 17.59, 73.47),
        ]
        areas: list[AffectedArea] = []
        for emergency, area_name, population, severity, lat, lon in area_defs:
            areas.append(AffectedArea(
                emergency_id=emergency.id, area_name=area_name,
                population_affected=population, severity=severity,
                latitude=lat, longitude=lon,
            ))
        db.session.add_all(areas)
        db.session.flush()

        resources: dict[str, Resource] = {}
        for name, category, unit, shelf, minimum in RESOURCES:
            resource = Resource(name=name, category=category, unit=unit,
                                shelf_life_days=shelf, minimum_stock_level=minimum)
            db.session.add(resource)
            resources[name] = resource
        db.session.flush()

        centers: dict[str, ReliefCenter] = {}
        for name, location, address, capacity, manager_email in CENTERS:
            center = ReliefCenter(
                name=name, location=location, address=address,
                storage_capacity=capacity, manager_id=users[manager_email].id,
            )
            db.session.add(center)
            centers[name] = center
        db.session.flush()

        # ---- Inventory with realistic stock levels & expiry dates ----
        stock_plan = {
            "Kolhapur Central Relief Hub": {
                "Drinking Water": (18000, (45, 75)), "Rice Bags (10kg)": (900, None),
                "Ready-to-Eat Meals": (2200, (30, 60)), "Paracetamol 500mg": (650, (200, 400)),
                "Thermal Blankets": (1100, None), "Hygiene Kits": (850, None),
                "First Aid Kits": (320, None), "ORS Sachets": (420, (120, 240)),
            },
            "Sangli District Warehouse": {
                "Drinking Water": (14000, (60, 90)), "Wheat Flour (10kg)": (700, None),
                "Ready-to-Eat Meals": (1800, (15, 30)), "Antibiotic Course": (260, (300, 500)),
                "Thermal Blankets": (780, None), "Baby Diapers": (350, None),
                "First Aid Kits": (210, None),
            },
            "Karad Transit Center": {
                "Drinking Water": (9000, (20, 40)), "Rice Bags (10kg)": (520, None),
                "Hygiene Kits": (430, None), "ORS Sachets": (280, (90, 150)),
                "Baby Food Packs": (190, (20, 30)),
            },
            "Pune Regional Depot": {
                "Drinking Water": (26000, (80, 100)), "Rice Bags (10kg)": (1400, None),
                "Ready-to-Eat Meals": (3100, (50, 70)), "Paracetamol 500mg": (820, (400, 600)),
                "Thermal Blankets": (1500, None), "Hygiene Kits": (1200, None),
                "Baby Diapers": (600, None), "Baby Food Packs": (340, (30, 50)),
                "First Aid Kits": (480, None),
            },
            "Satara Field Base": {
                "Drinking Water": (5200, (10, 20)), "Wheat Flour (10kg)": (380, None),
                "Thermal Blankets": (420, None), "ORS Sachets": (150, (50, 80)),
                "First Aid Kits": (130, None),
            },
        }
        for center_name, items in stock_plan.items():
            for resource_name, (qty, shelf_window) in items.items():
                expiry = today + timedelta(days=rng.randint(*shelf_window)) if shelf_window else None
                add_stock(centers[center_name].id, resources[resource_name].id, qty,
                          expiry_date=expiry, performed_by=admin.id, commit=False)
        db.session.commit()

        # Historical OUT consumption over the past 14 days (feeds daily_consumption)
        for _ in range(140):
            inv_row = rng.choice(Inventory.query.all())
            out_qty = max(int(inv_row.quantity_available * rng.uniform(0.01, 0.05)), 1)
            txn_day = today - timedelta(days=rng.randint(0, 13))
            db.session.add(InventoryTransaction(
                inventory_id=inv_row.id, transaction_type="OUT",
                quantity=out_qty, reference_type="SEED_HISTORY",
                performed_by=admin.id,
                transaction_date=datetime.combine(txn_day, datetime.min.time()) + timedelta(hours=rng.randint(6, 20)),
            ))
        db.session.commit()

        # ---- 32 relief requests with computed priorities ----
        request_specs = [
            (flood, "Kolhapur Area A", "Drinking Water", 9000, "CRITICAL", 2),
            (flood, "Kolhapur Area A", "Ready-to-Eat Meals", 2500, "CRITICAL", 2),
            (flood, "Kolhapur Area A", "Thermal Blankets", 1200, "HIGH", 3),
            (flood, "Kolhapur Area A", "ORS Sachets", 400, "CRITICAL", 1),
            (flood, "Kolhapur Area B (Rural)", "Drinking Water", 6000, "HIGH", 4),
            (flood, "Kolhapur Area B (Rural)", "Rice Bags (10kg)", 800, "MEDIUM", 6),
            (flood, "Sangli North", "Drinking Water", 7500, "CRITICAL", 2),
            (flood, "Sangli North", "Hygiene Kits", 1000, "HIGH", 4),
            (flood, "Sangli North", "Paracetamol 500mg", 350, "MEDIUM", 7),
            (flood, "Sangli South Belt", "Ready-to-Eat Meals", 1500, "HIGH", 3),
            (flood, "Sangli South Belt", "Thermal Blankets", 600, "MEDIUM", 8),
            (flood, "Karad Riverside", "Drinking Water", 3000, "MEDIUM", 5),
            (flood, "Karad Riverside", "First Aid Kits", 150, "MEDIUM", 6),
            (quake, "Ghat Village Cluster", "Thermal Blankets", 900, "CRITICAL", 2),
            (quake, "Ghat Village Cluster", "Ready-to-Eat Meals", 1400, "CRITICAL", 1),
            (quake, "Ghat Village Cluster", "First Aid Kits", 220, "HIGH", 2),
            (quake, "Ghat Village Cluster", "Antibiotic Course", 120, "HIGH", 4),
            (quake, "Hillside Settlements", "Rice Bags (10kg)", 300, "MEDIUM", 6),
            (quake, "Hillside Settlements", "Hygiene Kits", 260, "LOW", 10),
            (quake, "Wai Taluka", "Drinking Water", 2200, "MEDIUM", 5),
            (quake, "Wai Taluka", "Baby Food Packs", 90, "HIGH", 3),
            (cyclone, "Coastal Guhagar", "Drinking Water", 4000, "HIGH", 4),
            (cyclone, "Coastal Guhagar", "Thermal Blankets", 500, "MEDIUM", 7),
            (cyclone, "Coastal Guhagar", "Baby Diapers", 180, "MEDIUM", 8),
            (cyclone, "Dabhol Port Zone", "Ready-to-Eat Meals", 900, "MEDIUM", 6),
            (cyclone, "Dabhol Port Zone", "Hygiene Kits", 320, "LOW", 12),
        ]
        requests_made: list[ReliefRequest] = []
        for i, (emergency, area_name, res_name, qty, urgency, days_until_needed) in enumerate(request_specs):
            area = next(a for a in areas if a.area_name == area_name)
            scoring = compute_request_priority(
                emergency, area, resources[res_name].id, qty, urgency,
                today + timedelta(days=days_until_needed),
            )
            import json as _json

            req = ReliefRequest(
                emergency_id=emergency.id, area_id=area.id,
                requested_by=users[rng.choice([
                    "operator1@relief.local", "operator2@relief.local", "volunteer1@relief.local"])].id,
                resource_id=resources[res_name].id,
                people_affected=area.population_affected,
                quantity=qty, urgency=urgency,
                priority_score=scoring["score"],
                priority_breakdown=_json.dumps(scoring["breakdown"]),
                required_by=today + timedelta(days=days_until_needed),
                status="PENDING",
                requested_at=datetime.utcnow() - timedelta(hours=rng.randint(2, 96)),
                description=f"Urgent need reported by field team {i + 1}",
            )
            db.session.add(req)
            requests_made.append(req)
        db.session.commit()

        # ---- Demonstrate a completed flow: approve -> allocate -> deliver ----
        from .services import allocation_service

        completed_flow = sorted(requests_made, key=lambda r: -r.priority_score)[:6]
        for req in completed_flow[:4]:
            req.status = "APPROVED"
            req.approved_by = admin.id
        db.session.commit()
        allocation_service.run_allocation(admin)

        delivered_allocs = [d for d in Delivery.query.all()][:3]
        for dlv in delivered_allocs:
            delivery_service_flow(dlv, users["volunteer1@relief.local"])
        db.session.commit()

        # One WAITING_FOR_STOCK case: huge water demand beyond total stock
        big_area = areas[0]
        scoring = compute_request_priority(
            flood, big_area, resources["Drinking Water"].id, 999999, "CRITICAL",
            today + timedelta(days=1))
        req = ReliefRequest(
            emergency_id=flood.id, area_id=big_area.id,
            requested_by=admin.id, resource_id=resources["Drinking Water"].id,
            people_affected=big_area.population_affected, quantity=999999,
            urgency="CRITICAL",             priority_score=scoring["score"],
            priority_breakdown=json.dumps(scoring["breakdown"]),
            required_by=today + timedelta(days=1),
            status="APPROVED", approved_by=admin.id,
            description="Mass-scale pre-positioning requirement (demo of stock-out handling)",
        )
        db.session.add(req)
        allocation_service.run_allocation(admin, request_ids=[req.id])
        db.session.commit()

        db.session.add(Notification(
            type="INFO", title="Demo data loaded",
            message=f"Seeded {len(USERS)} users, 3 emergencies, {len(area_defs)} areas, "
                    f"{len(RESOURCES)} resources, {len(CENTERS)} centers, "
                    f"{len(request_specs)} requests.",
        ))
        db.session.commit()

        logger.info("Seed complete")
        return {"seeded": True}


def delivery_service_flow(dlv: Delivery, volunteer: User) -> None:
    """Advance a seeded delivery through DISPATCHED -> IN_TRANSIT -> DELIVERED."""
    dlv.assigned_to = volunteer.id
    now = datetime.utcnow()
    for status, note, offset in [
        ("DISPATCHED", "Truck loaded and dispatched", -8),
        ("IN_TRANSIT", "En route to destination", -4),
        ("DELIVERED", "Handed over to local coordinator", -1),
    ]:
        dlv.status = status
        ts = now + timedelta(hours=offset)
        if status == "DISPATCHED":
            dlv.dispatch_date = ts
            for item in dlv.allocation.items:
                inv_row = Inventory.query.filter_by(
                    relief_center_id=dlv.source_center, resource_id=item.resource_id
                ).filter(Inventory.quantity_reserved > 0).first()
                if inv_row:
                    take = min(item.quantity, inv_row.quantity_reserved)
                    inv_row.quantity_reserved -= take
                    center = inv_row.relief_center
                    center.current_utilization = max(center.current_utilization - take, 0)
                    db.session.add(InventoryTransaction(
                        inventory_id=inv_row.id, transaction_type="OUT",
                        quantity=take, reference_type="DELIVERY", reference_id=dlv.id,
                        performed_by=volunteer.id,
                        transaction_date=ts,
                    ))
            dlv.allocation.status = "DISPATCHED"
            req = dlv.allocation.relief_request
            req.status = "IN_DELIVERY"
        elif status == "DELIVERED":
            dlv.actual_delivery_date = ts
            dlv.allocation.status = "COMPLETED"
            dlv.allocation.relief_request.status = "COMPLETED"
        db.session.add(DeliveryEvent(delivery_id=dlv.id, status=status, note=note,
                                     updated_by=volunteer.id, timestamp=ts))


if __name__ == "__main__":
    result = seed()
    print("Seed result:", result)
