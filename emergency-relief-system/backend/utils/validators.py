"""Input validation helpers. Raise ValidationError to map to HTTP 422."""
import re
from datetime import date, datetime


class ValidationError(ValueError):
    """Raised when user input fails validation."""


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_email(email: str) -> str:
    if not email or not EMAIL_RE.match(email.strip()):
        raise ValidationError("A valid email address is required")
    return email.strip().lower()


def validate_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one letter and one number")
    return password


def validate_positive_int(value, field: str = "quantity") -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be an integer")
    if value <= 0:
        raise ValidationError(f"{field} must be greater than zero")
    return value


def validate_non_negative_number(value, field: str = "value") -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number")
    if value < 0:
        raise ValidationError(f"{field} cannot be negative")
    return value


def validate_required(value, field: str) -> str:
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field} is required")
    return str(value).strip()


def validate_choice(value, choices, field: str):
    if value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(choices)}")
    return value


def parse_date(value, field: str = "date") -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be in YYYY-MM-DD format")


def parse_payload_date(data: dict, key: str, required: bool = True):
    value = data.get(key)
    if value is None:
        if required:
            raise ValidationError(f"{key} is required")
        return None
    parsed = parse_date(value, key)
    today = date.today()
    max_year = today.year + 2
    if parsed.year > max_year:
        raise ValidationError(f"{key} is unreasonably far in the future")
    return parsed
