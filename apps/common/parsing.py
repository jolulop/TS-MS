from datetime import date
from decimal import Decimal, InvalidOperation

from apps.auth.errors import AuthError
from apps.common.reference_data import get_ref_value


def parse_required_int(value: object, *, code: str, message: str) -> int:
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise AuthError(code, message, 400) from exc
    if parsed_value <= 0:
        raise AuthError(code, message, 400)
    return parsed_value


def parse_iso_date(value: object, *, code: str, message: str) -> date:
    if value in (None, ""):
        raise AuthError(code, message, 400)
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AuthError(code, message, 400) from exc


def parse_optional_iso_date(value: object, *, code: str, message: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AuthError(code, message, 400) from exc


def parse_decimal(value: object, *, code: str, message: str) -> Decimal:
    if value in (None, ""):
        raise AuthError(code, message, 400)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AuthError(code, message, 400) from exc


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


def parse_status_filter(value: object, *, domain_code: str) -> str | None:
    if value in (None, "", "ALL"):
        return None
    status_code = str(value).strip().upper()
    try:
        get_ref_value(domain_code, status_code)
    except AuthError as exc:
        raise AuthError(
            "STATUS_FILTER_INVALID",
            f"Unknown status filter for {domain_code}: {status_code}.",
            400,
        ) from exc
    return status_code


def apply_status_filter(queryset, status_code: str | None):
    if status_code is None:
        return queryset
    return queryset.filter(status__value_code=status_code)


def parse_optional_date_query(value: object) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
