import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.http import HttpRequest, JsonResponse

from apps.audit.services import write_audit_event
from apps.auth.constants import (
    ACTIVE_COUNTRY_STATUS,
    ACTIVE_EMPLOYEE_BU_STATUS,
    ACTIVE_EMPLOYEE_STATUS,
    ACTIVE_ROLE_ASSIGNMENT_STATUS,
    AUDIT_ACTION_DENY,
    AUDIT_ACTION_LOGIN_IDENTIFICATION,
    ROLE_TS_ADMIN_MASTER,
    SESSION_EMAIL_KEY,
    SESSION_EMPLOYEE_ID_KEY,
)
from apps.auth.context import CurrentUser, ScopedBusinessUnit
from apps.auth.errors import AuthError
from apps.master_data.models import BusinessUnit, Employee, EmployeeBusinessUnit


def parse_json_request(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthError("AUTH_INVALID_REQUEST", "Request body must be valid JSON.", 400) from exc
    if not isinstance(payload, dict):
        raise AuthError("AUTH_INVALID_REQUEST", "Request body must be a JSON object.", 400)
    return payload


def error_response(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def canonicalize_email(value: str) -> str:
    return value.strip().lower()


@dataclass(frozen=True)
class ExternalIdentityClaims:
    email: str
    provider: str


class CurrentUserService:
    @staticmethod
    def build_for_employee(employee: Employee, *, on_date: date | None = None) -> CurrentUser:
        effective_date = on_date or date.today()
        if not CurrentUserService.is_employee_active(employee):
            raise AuthError(
                "AUTH_EMPLOYEE_INACTIVE",
                "The matched employee is not active.",
                403,
            )

        active_roles = list(
            employee.role_assignments.filter(
                status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                status__value_code=ACTIVE_ROLE_ASSIGNMENT_STATUS,
                valid_from__lte=effective_date,
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=effective_date))
            .select_related("role")
            .order_by("role__value_code")
        )
        role_codes = tuple(sorted({assignment.role.value_code for assignment in active_roles}))
        if not role_codes:
            raise AuthError(
                "AUTH_NO_ACTIVE_ROLE",
                "The employee has no active internal role.",
                403,
            )
        if (
            employee.office.status.domain.domain_code == "COUNTRY_STATUS"
            and employee.office.status.value_code != ACTIVE_COUNTRY_STATUS
            and ROLE_TS_ADMIN_MASTER not in role_codes
        ):
            raise AuthError(
                "AUTH_COUNTRY_INACTIVE",
                "The employee country is inactive for this login.",
                403,
            )

        scoped_business_unit_ids = {
            employee.primary_business_unit_id,
            *EmployeeBusinessUnit.objects.filter(
                employee=employee,
                status__domain__domain_code="EMPLOYEE_BU_STATUS",
                status__value_code=ACTIVE_EMPLOYEE_BU_STATUS,
                valid_from__lte=effective_date,
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=effective_date))
            .values_list("business_unit_id", flat=True),
        }
        business_units = list(
            BusinessUnit.objects.filter(id__in=scoped_business_unit_ids).order_by("bu_code")
        )
        scoped_units = tuple(
            ScopedBusinessUnit(id=unit.id, bu_code=unit.bu_code, name=unit.name)
            for unit in business_units
        )

        return CurrentUser(
            employee_id=employee.id,
            employee_code=employee.employee_code,
            full_name=employee.full_name,
            email=employee.email,
            canonical_email=employee.canonical_email,
            office_id=employee.office_id,
            office_name=employee.office.office_name,
            office_status=employee.office.status.value_code,
            primary_business_unit_id=employee.primary_business_unit_id,
            primary_business_unit_code=employee.primary_business_unit.bu_code,
            role_codes=role_codes,
            scoped_business_units=scoped_units,
        )

    @staticmethod
    def get_from_request(request: HttpRequest) -> CurrentUser:
        current_user = getattr(request, "ts_user", None)
        if current_user is None:
            raise AuthError(
                "AUTH_SESSION_REQUIRED",
                "A valid internal session is required.",
                401,
            )
        return current_user

    @staticmethod
    def is_employee_active(employee: Employee) -> bool:
        return (
            employee.status.domain.domain_code == "EMPLOYEE_STATUS"
            and employee.status.value_code == ACTIVE_EMPLOYEE_STATUS
        )


class SessionInitializationService:
    @staticmethod
    def initialize_from_external_identity(
        request: HttpRequest,
        identity_claims: ExternalIdentityClaims,
    ) -> CurrentUser:
        normalized_email = canonicalize_email(identity_claims.email)
        employee = SessionInitializationService._find_employee_for_validated_email(normalized_email)
        try:
            current_user = CurrentUserService.build_for_employee(employee)
        except AuthError as exc:
            SessionInitializationService._audit_denial(
                normalized_email,
                exc.code,
                exc.message,
                employee=employee,
            )
            raise

        request.session.cycle_key()
        request.session[SESSION_EMPLOYEE_ID_KEY] = employee.id
        request.session[SESSION_EMAIL_KEY] = normalized_email

        write_audit_event(
            action_code=AUDIT_ACTION_LOGIN_IDENTIFICATION,
            entity_name="internal_session",
            entity_id=employee.id,
            actor_employee=employee,
            actor_email=normalized_email,
            business_unit=employee.primary_business_unit,
            reason_text=(
                f"Internal session initialized from {identity_claims.provider} external identity."
            ),
        )
        return current_user

    @staticmethod
    def initialize(request: HttpRequest, validated_email: str) -> CurrentUser:
        identity_claims = ExternalIdentityAdapterService._resolve_development_email_claims(
            {"validated_email": validated_email}
        )
        return SessionInitializationService.initialize_from_external_identity(
            request,
            identity_claims,
        )

    @staticmethod
    def logout(request: HttpRequest) -> None:
        request.session.flush()

    @staticmethod
    def _find_employee_for_validated_email(normalized_email: str) -> Employee:
        candidates = list(
            Employee.objects.filter(
                Q(canonical_email=normalized_email) | Q(email__iexact=normalized_email)
            )
            .select_related(
                "status",
                "status__domain",
                "office",
                "office__status",
                "office__status__domain",
                "primary_business_unit",
            )
            .order_by("id")
        )

        if not candidates:
            SessionInitializationService._audit_denial(
                normalized_email,
                "AUTH_EMPLOYEE_NOT_FOUND",
                "No active employee found for validated email.",
            )
            raise AuthError(
                "AUTH_EMPLOYEE_NOT_FOUND",
                "No active employee found for validated email.",
                403,
            )

        active_candidates = [
            employee
            for employee in candidates
            if employee.status.domain.domain_code == "EMPLOYEE_STATUS"
            and employee.status.value_code == ACTIVE_EMPLOYEE_STATUS
        ]
        if not active_candidates:
            SessionInitializationService._audit_denial(
                normalized_email,
                "AUTH_EMPLOYEE_NOT_FOUND",
                "No active employee found for validated email.",
            )
            raise AuthError(
                "AUTH_EMPLOYEE_NOT_FOUND",
                "No active employee found for validated email.",
                403,
            )

        if len(active_candidates) > 1:
            SessionInitializationService._audit_denial(
                normalized_email,
                "AUTH_DUPLICATE_EMPLOYEE_EMAIL",
                "Duplicate active employee email detected.",
            )
            raise AuthError(
                "AUTH_DUPLICATE_EMPLOYEE_EMAIL",
                "Duplicate active employee email detected.",
                403,
            )

        return active_candidates[0]

    @staticmethod
    def _audit_denial(
        validated_email: str,
        code: str,
        message: str,
        employee: Employee | None = None,
    ) -> None:
        write_audit_event(
            action_code=AUDIT_ACTION_DENY,
            entity_name="internal_session",
            entity_id=employee.id if employee else None,
            actor_employee=employee,
            actor_email=validated_email,
            business_unit=employee.primary_business_unit if employee else None,
            reason_text=f"{code}: {message}",
        )


class ExternalIdentityAdapterService:
    DEVELOPMENT_EMAIL_PROVIDER = "development-email"
    TRUSTED_HEADER_PROVIDER = "trusted-header"

    @staticmethod
    def initialize_session(
        request: HttpRequest,
        payload: dict[str, Any] | None = None,
    ) -> CurrentUser:
        identity_claims = ExternalIdentityAdapterService.resolve_identity_claims(
            request,
            payload or {},
        )
        return SessionInitializationService.initialize_from_external_identity(
            request,
            identity_claims,
        )

    @staticmethod
    def resolve_identity_claims(
        request: HttpRequest,
        payload: dict[str, Any],
    ) -> ExternalIdentityClaims:
        provider = getattr(
            settings,
            "TSMS_AUTH_PROVIDER",
            ExternalIdentityAdapterService.DEVELOPMENT_EMAIL_PROVIDER,
        )
        if provider == ExternalIdentityAdapterService.DEVELOPMENT_EMAIL_PROVIDER:
            return ExternalIdentityAdapterService._resolve_development_email_claims(payload)
        if provider == ExternalIdentityAdapterService.TRUSTED_HEADER_PROVIDER:
            return ExternalIdentityAdapterService._resolve_trusted_header_claims(request)
        raise AuthError(
            "AUTH_PROVIDER_UNSUPPORTED",
            "The configured authentication provider is not supported.",
            500,
        )

    @staticmethod
    def _resolve_development_email_claims(payload: dict[str, Any]) -> ExternalIdentityClaims:
        raw_email = str(payload.get("validated_email", "")).strip()
        if getattr(settings, "TSMS_ENVIRONMENT", "development") == "production" or not getattr(
            settings, "TSMS_ENABLE_DEV_AUTH", False
        ):
            normalized_email = canonicalize_email(raw_email)
            SessionInitializationService._audit_denial(
                normalized_email,
                "AUTH_DEV_LOGIN_DISABLED",
                "Development email login is disabled outside local development.",
            )
            raise AuthError(
                "AUTH_DEV_LOGIN_DISABLED",
                "Development email login is disabled outside local development.",
                403,
            )
        if not raw_email:
            raise AuthError("AUTH_INVALID_REQUEST", "validated_email is required.", 400)
        return ExternalIdentityClaims(
            email=raw_email,
            provider=ExternalIdentityAdapterService.DEVELOPMENT_EMAIL_PROVIDER,
        )

    @staticmethod
    def _resolve_trusted_header_claims(request: HttpRequest) -> ExternalIdentityClaims:
        header_name = getattr(
            settings,
            "TSMS_TRUSTED_EMAIL_HEADER",
            "HTTP_X_MS_CLIENT_PRINCIPAL_NAME",
        )
        raw_email = str(request.META.get(header_name, "")).strip()
        if not raw_email:
            SessionInitializationService._audit_denial(
                "",
                "AUTH_EXTERNAL_IDENTITY_MISSING",
                "Trusted external identity email claim is missing.",
            )
            raise AuthError(
                "AUTH_EXTERNAL_IDENTITY_MISSING",
                "Trusted external identity email claim is missing.",
                401,
            )
        return ExternalIdentityClaims(
            email=raw_email,
            provider=ExternalIdentityAdapterService.TRUSTED_HEADER_PROVIDER,
        )
