"""Flask application factory."""
import logging
import os

from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager

from .config import get_config
from .extensions import db, jwt

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("relief.app")


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    if app.config.get("JWT_SECRET_KEY", "").startswith("dev-"):
        logger.warning("Using default development JWT secret; set JWT_SECRET_KEY in production")

    db.init_app(app)
    jwt.init_app(app)

    _register_error_handlers(app)
    _register_jwt_hooks()
    _register_cors(app)
    _register_routes(app)

    with app.app_context():
        # Import every model before create_all so SQLAlchemy knows all tables.
        from backend.models import allocation, delivery, demand_forecast, emergency, inventory, relief_center, relief_request, resource, user  # noqa: F401
        db.create_all()

    @app.get("/health")
    def health():
        return jsonify({"success": True, "message": "API is healthy", "data": {"service": "emergency-relief-api"}})

    return app


def _register_routes(app: Flask) -> None:
    from .routes.auth_routes import auth_bp
    from .routes.user_routes import users_bp
    from .routes.emergency_routes import emergencies_bp, areas_bp
    from .routes.request_routes import requests_bp
    from .routes.resource_routes import resources_bp
    from .routes.inventory_routes import inventory_bp
    from .routes.center_routes import centers_bp
    from .routes.allocation_routes import allocation_bp
    from .routes.delivery_routes import deliveries_bp
    from .routes.forecast_routes import forecast_bp
    from .routes.dashboard_routes import dashboard_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(emergencies_bp, url_prefix="/api/emergencies")
    app.register_blueprint(areas_bp, url_prefix="/api/areas")
    app.register_blueprint(requests_bp, url_prefix="/api/requests")
    app.register_blueprint(resources_bp, url_prefix="/api/resources")
    app.register_blueprint(inventory_bp, url_prefix="/api/inventory")
    app.register_blueprint(centers_bp, url_prefix="/api/centers")
    app.register_blueprint(allocation_bp, url_prefix="/api/allocation")
    app.register_blueprint(deliveries_bp, url_prefix="/api/deliveries")
    app.register_blueprint(forecast_bp, url_prefix="/api/forecast")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")


def _register_cors(app: Flask) -> None:
    origin = app.config["CORS_ORIGIN"]

    @app.after_request
    def add_cors_headers(resp):
        resp.headers.setdefault("Access-Control-Allow-Origin", origin)
        resp.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization")
        resp.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        if request.method == "OPTIONS":
            return "", 204
        return resp


def _register_error_handlers(app: Flask) -> None:
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError
    from werkzeug.exceptions import HTTPException

    from .services.allocation_service import AllocationError
    from .services.delivery_service import DeliveryError
    from .services.forecast_service import ForecastError
    from .utils.validators import ValidationError

    @app.errorhandler(ValidationError)
    def handle_validation(err):
        return jsonify({"success": False, "message": str(err), "error": "validation_failed"}), 422

    @app.errorhandler(ValueError)
    def handle_value(err):
        return jsonify({"success": False, "message": str(err), "error": "invalid_input"}), 400

    @app.errorhandler(AllocationError)
    def handle_allocation(err):
        return jsonify({"success": False, "message": str(err), "error": "allocation_error"}), 409

    @app.errorhandler(DeliveryError)
    def handle_delivery(err):
        return jsonify({"success": False, "message": str(err), "error": "delivery_error"}), 409

    @app.errorhandler(ForecastError)
    def handle_forecast(err):
        return jsonify({"success": False, "message": str(err), "error": "forecast_error"}), 409

    @app.errorhandler(IntegrityError)
    def handle_integrity(err):
        db.session.rollback()
        logger.warning("Integrity violation: %s", err.orig if hasattr(err, "orig") else err)
        return jsonify({"success": False,
                        "message": "Database constraint violated (duplicate or invalid reference)",
                        "error": "integrity_error"}), 409

    @app.errorhandler(SQLAlchemyError)
    def handle_db(err):
        db.session.rollback()
        logger.exception("Database error")
        return jsonify({"success": False, "message": "A database error occurred",
                        "error": "database_error"}), 500

    @app.errorhandler(PermissionError)
    def handle_permission(err):
        return jsonify({"success": False, "message": str(err), "error": "forbidden"}), 403

    @app.errorhandler(LookupError)
    def handle_lookup(err):
        return jsonify({"success": False, "message": "Resource not found", "error": "not_found"}), 404

    @app.errorhandler(HTTPException)
    def handle_http(err):
        return jsonify({"success": False, "message": err.description, "error": err.name.lower()}), err.code

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        logger.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({"success": False, "message": "Internal server error",
                        "error": "server_error"}), 500


def _register_jwt_hooks() -> None:
    @jwt.expired_token_loader
    def expired(_header, _payload):
        return jsonify({"success": False, "message": "Session expired. Please log in again.",
                        "error": "token_expired"}), 401

    @jwt.invalid_token_loader
    def invalid(_reason):
        return jsonify({"success": False, "message": "Invalid authentication token.",
                        "error": "invalid_token"}), 401

    @jwt.unauthorized_loader
    def missing(_reason):
        return jsonify({"success": False, "message": "Authentication required.",
                        "error": "missing_token"}), 401
