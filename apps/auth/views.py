from datetime import date

from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import (
    CurrentUserService,
    SessionInitializationService,
    error_response,
    parse_json_request,
)
from apps.master_data.models import BusinessUnit, Employee


def _serialize_current_user(current_user) -> dict:
    return {
        "employee": {
            "id": current_user.employee_id,
            "employee_code": current_user.employee_code,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "canonical_email": current_user.canonical_email,
            "country": {
                "id": current_user.country_id,
                "country_name": current_user.country_name,
                "status": current_user.country_status,
            },
            "primary_business_unit_id": current_user.primary_business_unit_id,
            "primary_business_unit_code": current_user.primary_business_unit_code,
        },
        "roles": list(current_user.role_codes),
        "business_units": [
            {"id": unit.id, "bu_code": unit.bu_code, "name": unit.name}
            for unit in current_user.scoped_business_units
        ],
    }


def _serialize_employee(employee: Employee) -> dict:
    role_codes = sorted(
        {
            assignment.role.value_code
            for assignment in employee.role_assignments.select_related("role").all()
        }
    )
    return {
        "id": employee.id,
        "employee_code": employee.employee_code,
        "full_name": employee.full_name,
        "email": employee.email,
        "canonical_email": employee.canonical_email,
        "primary_business_unit": {
            "id": employee.primary_business_unit_id,
            "bu_code": employee.primary_business_unit.bu_code,
            "name": employee.primary_business_unit.name,
        },
        "country": {
            "id": employee.country_id,
            "country_name": employee.country.country_name,
            "status": employee.country.status.value_code,
        },
        "roles": role_codes,
        "status": employee.status.value_code,
    }


@require_POST
def initialize_session(request: HttpRequest) -> JsonResponse:
    try:
        payload = parse_json_request(request)
        validated_email = str(payload.get("validated_email", "")).strip()
        if not validated_email:
            raise AuthError("AUTH_INVALID_REQUEST", "validated_email is required.", 400)
        current_user = SessionInitializationService.initialize(request, validated_email)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"session": _serialize_current_user(current_user)}, status=201)


@require_GET
def get_session(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"session": _serialize_current_user(current_user)})


@require_POST
def logout(request: HttpRequest) -> JsonResponse:
    SessionInitializationService.logout(request)
    return JsonResponse({"status": "ok"})


@require_GET
def list_employees(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if not AuthorizationPolicyService.can_list_employees(current_user):
            raise AuthError(
                "AUTH_ACCESS_DENIED",
                "You are not authorized to list employees.",
                403,
            )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    effective_date = date.today()
    employees = (
        Employee.objects.select_related(
            "primary_business_unit", "status", "country", "country__status"
        )
        .prefetch_related("role_assignments__role")
        .filter(
            Q(primary_business_unit_id__in=current_user.scoped_business_unit_ids)
            | Q(
                business_unit_assignments__business_unit_id__in=current_user.scoped_business_unit_ids,
                business_unit_assignments__status__domain__domain_code="EMPLOYEE_BU_STATUS",
                business_unit_assignments__status__value_code="ACTIVE",
                business_unit_assignments__valid_from__lte=effective_date,
            )
        )
        .filter(
            Q(business_unit_assignments__valid_to__isnull=True)
            | Q(business_unit_assignments__valid_to__gte=effective_date)
            | Q(primary_business_unit_id__in=current_user.scoped_business_unit_ids)
        )
        .distinct()
        .order_by("employee_code")
    )
    return JsonResponse({"employees": [_serialize_employee(employee) for employee in employees]})


@require_GET
def employee_detail(request: HttpRequest, employee_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        employee = (
            Employee.objects.select_related("primary_business_unit", "status")
            .select_related("country", "country__status")
            .prefetch_related("role_assignments__role", "business_unit_assignments")
            .get(id=employee_id)
        )
        if not AuthorizationPolicyService.can_view_employee(current_user, employee):
            raise AuthError(
                "AUTH_ACCESS_DENIED",
                "You are not authorized to view this employee.",
                403,
            )
    except Employee.DoesNotExist:
        return error_response("EMPLOYEE_NOT_FOUND", "Employee not found.", 404)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"employee": _serialize_employee(employee)})


@require_GET
def list_business_units(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    business_units = BusinessUnit.objects.filter(
        id__in=current_user.scoped_business_unit_ids
    ).order_by("bu_code")
    return JsonResponse(
        {
            "business_units": [
                {"id": unit.id, "bu_code": unit.bu_code, "name": unit.name}
                for unit in business_units
            ]
        }
    )
