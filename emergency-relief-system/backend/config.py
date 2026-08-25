"""Application configuration loaded from environment variables."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class BaseConfig:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "86400"))

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

    CORS_ORIGIN = os.getenv("CORS_ORIGIN", "http://localhost:8501")

    LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
    LOGIN_RATE_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "60"))

    ML_MODEL_PATH = os.getenv(
        "ML_MODEL_PATH", str(PROJECT_ROOT / "backend" / "ml" / "model.pkl")
    )
    ML_DATASET_PATH = os.getenv(
        "ML_DATASET_PATH", str(PROJECT_ROOT / "backend" / "ml" / "dataset.csv")
    )
    ML_METRICS_PATH = os.getenv(
        "ML_METRICS_PATH", str(PROJECT_ROOT / "backend" / "ml" / "metrics.json")
    )

    LOW_STOCK_WARNING_RATIO = float(os.getenv("LOW_STOCK_WARNING_RATIO", "0.2"))
    CENTER_CAPACITY_WARNING_PCT = float(os.getenv("CENTER_CAPACITY_WARNING_PCT", "80"))


def _default_database_url() -> str:
    """MySQL when configured via env, otherwise a local SQLite file for development."""
    url = os.getenv("DATABASE_URL", "")
    if url:
        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+pymysql://", 1)
        return url
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    return f"sqlite:///{data_dir / 'emergency_relief_dev.db'}"


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = _default_database_url()


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(BaseConfig):
    DEBUG = False
    PROPAGATE_EXCEPTIONS = True
    SQLALCHEMY_DATABASE_URI = _default_database_url()


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.getenv("FLASK_ENV", "development")
    return CONFIG_BY_NAME.get(name, DevelopmentConfig)
