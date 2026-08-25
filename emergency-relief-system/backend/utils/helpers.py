"""Consistent JSON responses and shared query helpers."""
from flask import jsonify
from sqlalchemy.orm import joinedload


def success_response(data=None, message="OK", status=200):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return jsonify(body), status


def error_response(message="Error", error=None, status=400):
    body = {"success": False, "message": message, "error": error or message}
    return jsonify(body), status


def get_or_404(model, item_id, error_message="Resource not found"):
    obj = db_get_or_none(model, item_id)
    if obj is None:
        from .validators import ValidationError

        raise RecordNotFound(error_message)
    return obj


class RecordNotFound(Exception):
    pass


def db_get_or_none(model, item_id):
    from ..extensions import db

    try:
        return db.session.get(model, item_id)
    except (ValueError, TypeError):
        return None


def eager(query, *options):
    """Attach joinedload options to a Model.query."""
    return query.options(*[joinedload(o) for o in options])
