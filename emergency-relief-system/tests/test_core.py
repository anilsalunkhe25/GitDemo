from datetime import date, timedelta

import pytest

from backend.app import create_app
from backend.extensions import db
from backend.ml.predict import compute_shortage, make_recommendation
from backend.utils.priority import calculate_priority, priority_level


@pytest.fixture()
def client():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_health_and_schema(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["success"] is True


def test_register_login_me_and_logout(client):
    registration = client.post("/api/auth/register", json={"name": "Test User", "email": "test@example.com", "password": "Secure@123"})
    assert registration.status_code == 201
    login = client.post("/api/auth/login", json={"email": "test@example.com", "password": "Secure@123"})
    assert login.status_code == 200
    token = login.json["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200


def test_duplicate_email_is_rejected(client):
    payload = {"name": "Test User", "email": "duplicate@example.com", "password": "Secure@123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_protected_endpoint_requires_jwt(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 401
    assert response.json["error"] == "missing_token"


def test_invalid_credentials_are_rejected(client):
    client.post("/api/auth/register", json={"name": "Test User", "email": "wrong@example.com", "password": "Secure@123"})
    response = client.post("/api/auth/login", json={"email": "wrong@example.com", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json["error"] == "invalid_credentials"


def test_public_registration_cannot_escalate_role(client):
    response = client.post("/api/auth/register", json={"name": "Volunteer", "email": "volunteer@example.com", "password": "Secure@123", "role": "ADMIN"})
    assert response.status_code == 201
    assert response.json["data"]["role"] == "VOLUNTEER_LOGISTICS"


def test_missing_required_registration_fields_are_rejected(client):
    response = client.post("/api/auth/register", json={"email": "missing@example.com"})
    assert response.status_code == 422


def test_invalid_json_date_is_rejected_by_analytics_api(client):
    registration = client.post("/api/auth/register", json={"name": "Analyst", "email": "analyst@example.com", "password": "Secure@123"})
    assert registration.status_code == 201
    login = client.post("/api/auth/login", json={"email": "analyst@example.com", "password": "Secure@123"})
    token = login.json["data"]["access_token"]
    response = client.get("/api/dashboard/analytics?start_date=not-a-date", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422


@pytest.mark.parametrize(("score", "level"), [(10, "LOW"), (45, "MEDIUM"), (70, "HIGH"), (90, "CRITICAL")])
def test_priority_level_boundaries(score, level):
    assert priority_level(score) == level


def test_priority_is_bounded_and_explainable():
    result = calculate_priority("CRITICAL", 5000, 1000, 0, "CRITICAL", date.today())
    assert 0 <= result["score"] <= 100
    assert result["level"] == "CRITICAL"
    assert len(result["breakdown"]) == 5
    assert all(item["reason"] for item in result["breakdown"])


def test_due_date_increases_time_criticality():
    today = calculate_priority("HIGH", 1000, 100, 1000, "MEDIUM", date.today())
    later = calculate_priority("HIGH", 1000, 100, 1000, "MEDIUM", date.today() + timedelta(days=30))
    assert today["score"] > later["score"]


@pytest.mark.parametrize(("predicted", "stock", "shortage"), [(12500, 8000, 4500), (100, 200, 0), (0, 0, 0), (10.5, 2.2, 8.3)])
def test_shortage_calculation(predicted, stock, shortage):
    assert compute_shortage(predicted, stock)[0] == shortage


def test_recommendation_always_requires_human_review():
    result = make_recommendation("Water", "liters", 12500, 8000, 4500)
    assert result["human_review_required"] is True
    assert result["recommended_quantity"] == 4500
    assert "4,500" in result["message"]


def test_model_metrics_file_is_available():
    from backend.ml.predict import model_metrics
    metrics = model_metrics()
    assert metrics.get("best_model")
    assert {"MAE", "RMSE", "R2"}.issubset(metrics["results"][metrics["best_model"]])
