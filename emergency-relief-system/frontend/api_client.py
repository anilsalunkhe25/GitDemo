"""Small HTTP client used by every Streamlit view."""
from __future__ import annotations

import os
from typing import Any

import requests


class ApiError(RuntimeError):
    """An API request returned an unsuccessful response."""


class ApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("API_URL", "http://localhost:5000")).rstrip("/")
        self.token = token

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = requests.request(method, f"{self.base_url}{path}", headers=headers, timeout=15, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(f"API returned HTTP {response.status_code}") from exc
        if not response.ok or payload.get("success") is False:
            raise ApiError(payload.get("message", f"API returned HTTP {response.status_code}"))
        return payload.get("data")

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)


def login(email: str, password: str, base_url: str | None = None) -> dict[str, Any]:
    return ApiClient(base_url).post("/api/auth/login", json={"email": email, "password": password})
