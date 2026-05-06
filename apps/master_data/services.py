from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.audit.services import write_audit_event
from apps.auth.constants import ACTIVE_COUNTRY_STATUS
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import canonicalize_email
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    Country,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    Project,
    ProjectAssignment,
    YearlyCalendar,
)
from apps.master_data.models import (
    Client as ClientRecord,
)
from apps.master_data.models import (
    CostCenter as CostCenterRecord,
)
from apps.master_data.models import (
    GeneralChargeCode as GeneralChargeCodeRecord,
)
from apps.master_data.models import (
    InternalCategory as InternalCategoryRecord,
)
from apps.reference_data.models import RefValue


def _ref_value(domain_code: str, value_code: str) -> RefValue:
    try:
        return RefValue.objects.get(domain__domain_code=domain_code, value_code=value_code)
    except RefValue.DoesNotExist as exc:
        raise AuthError(
            "REFERENCE_VALUE_NOT_FOUND",
            f"Unknown reference value {domain_code}:{value_code}.",
            400,
        ) from exc


def _ensure_ts_admin(current_user: CurrentUser) -> None:
    if not current_user.is_ts_admin:
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to perform this administrative action.",
            403,
        )


def _ensure_ts_admin_master(current_user: CurrentUser) -> None:
    if not current_user.is_ts_admin_master:
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to perform this master administrative action.",
            403,
        )


def _get_current_country(current_user: CurrentUser) -> Country:
    try:
        return Country.objects.select_related("status").get(id=current_user.country_id)
    except Country.DoesNotExist as exc:
        raise AuthError("COUNTRY_NOT_FOUND", "Country not found.", 404) from exc


def _ensure_country_in_scope(
    current_user: CurrentUser,
    country_id: int,
    *,
    message: str,
) -> None:
    if country_id != current_user.country_id:
        raise AuthError("COUNTRY_OUT_OF_SCOPE", message, 403)


def _ensure_country_active_for_write(country: Country, *, message: str) -> None:
    if country.status.value_code != ACTIVE_COUNTRY_STATUS:
        raise AuthError("COUNTRY_INACTIVE_FOR_WRITE", message, 403)


def _ensure_current_country_active_for_write(current_user: CurrentUser) -> Country:
    current_country = _get_current_country(current_user)
    _ensure_country_active_for_write(
        current_country,
        message="Your active country is inactive. New records and edits are blocked.",
    )
    return current_country


def _ensure_scoped_active_country_for_write(
    current_user: CurrentUser,
    country: Country,
    *,
    out_of_scope_message: str,
) -> None:
    _ensure_country_in_scope(
        current_user,
        country.id,
        message=out_of_scope_message,
    )
    _ensure_country_active_for_write(
        country,
        message="Records in inactive countries cannot be created or edited.",
    )


def _validate_optional_country_payload(
    payload: dict,
    *,
    code_prefix: str,
    expected_country_id: int,
    mismatch_message: str,
    immutable_country_id: int | None = None,
    immutable_message: str | None = None,
) -> None:
    if "country_id" not in payload:
        return

    payload_country_id = _parse_required_int(
        payload.get("country_id"),
        code=f"{code_prefix}_COUNTRY_REQUIRED",
        message="country_id must be a valid country identifier.",
    )
    if immutable_country_id is not None and payload_country_id != immutable_country_id:
        raise AuthError(
            f"{code_prefix}_COUNTRY_IMMUTABLE",
            immutable_message or "Country cannot be changed.",
            400,
        )
    if payload_country_id != expected_country_id:
        raise AuthError(
            f"{code_prefix}_COUNTRY_MISMATCH",
            mismatch_message,
            400,
        )


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise AuthError(code, message, 400) from exc
    if parsed_value <= 0:
        raise AuthError(code, message, 400)
    return parsed_value


def _parse_iso_date(value: object, *, code: str, message: str) -> date:
    if value in (None, ""):
        raise AuthError(code, message, 400)
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AuthError(code, message, 400) from exc


def _parse_optional_iso_date(value: object, *, code: str, message: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AuthError(code, message, 400) from exc


def _parse_decimal(value: object, *, code: str, message: str) -> Decimal:
    if value in (None, ""):
        raise AuthError(code, message, 400)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AuthError(code, message, 400) from exc


def _parse_status_filter(value: object, *, domain_code: str) -> str | None:
    if value in (None, "", "ALL"):
        return None
    status_code = str(value).strip().upper()
    try:
        _ref_value(domain_code, status_code)
    except AuthError as exc:
        raise AuthError(
            "STATUS_FILTER_INVALID",
            f"Unknown status filter for {domain_code}: {status_code}.",
            400,
        ) from exc
    return status_code


def _apply_status_filter(queryset, status_code: str | None):
    if status_code is None:
        return queryset
    return queryset.filter(status__value_code=status_code)


def _parse_business_unit_scope(
    payload: dict,
) -> tuple[int, set[int]]:
    primary_business_unit_id = _parse_required_int(
        payload.get("primary_business_unit_id"),
        code="EMPLOYEE_PRIMARY_BU_REQUIRED",
        message="primary_business_unit_id is required.",
    )
    try:
        business_unit_ids = {
            int(value) for value in payload.get("business_unit_ids", []) if str(value).strip()
        }
    except (TypeError, ValueError) as exc:
        raise AuthError(
            "BUSINESS_UNIT_INVALID",
            "business_unit_ids must contain valid Business Unit identifiers.",
            400,
        ) from exc
    business_unit_ids.add(primary_business_unit_id)
    return primary_business_unit_id, business_unit_ids


def _parse_role_codes(payload: dict) -> list[str]:
    role_codes = sorted(
        {str(code).strip() for code in payload.get("role_codes", []) if str(code).strip()}
    )
    for role_code in role_codes:
        try:
            _ref_value("ROLE_CODE", role_code)
        except AuthError as exc:
            raise AuthError(
                "EMPLOYEE_ROLE_INVALID",
                f"Unknown employee role: {role_code}.",
                400,
            ) from exc
    return role_codes


def _ensure_business_units_in_scope(current_user: CurrentUser, business_unit_ids: set[int]) -> None:
    if not business_unit_ids.issubset(set(current_user.scoped_business_unit_ids)):
        raise AuthError(
            "BUSINESS_UNIT_OUT_OF_SCOPE",
            "One or more Business Units are outside your administration scope.",
            403,
        )


def _get_scoped_business_unit(current_user: CurrentUser, business_unit_id: int) -> BusinessUnit:
    _ensure_business_units_in_scope(current_user, {business_unit_id})
    try:
        business_unit = BusinessUnit.objects.select_related("country", "country__status").get(
            id=business_unit_id
        )
    except BusinessUnit.DoesNotExist as exc:
        raise AuthError("BUSINESS_UNIT_NOT_FOUND", "Business Unit not found.", 404) from exc
    _ensure_country_in_scope(
        current_user,
        business_unit.country_id,
        message="Business Unit is outside your active country.",
    )
    return business_unit


def _get_scoped_employee_for_management(current_user: CurrentUser, employee_id: int) -> Employee:
    try:
        employee = (
            Employee.objects.select_related("primary_business_unit", "country", "status")
            .prefetch_related(
                "business_unit_assignments__business_unit",
                "business_unit_assignments__status__domain",
                "role_assignments__role",
                "role_assignments__status__domain",
            )
            .get(id=employee_id)
        )
    except Employee.DoesNotExist as exc:
        raise AuthError("EMPLOYEE_NOT_FOUND", "Employee not found.", 404) from exc

    if not AuthorizationPolicyService.can_manage_employee(current_user, employee):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to manage this employee.",
            403,
        )
    _ensure_country_in_scope(
        current_user,
        employee.country_id,
        message="Employee is outside your active country.",
    )
    return employee


def _refresh_employee(employee_id: int) -> Employee:
    return (
        Employee.objects.select_related("primary_business_unit", "country", "status")
        .prefetch_related(
            "business_unit_assignments__business_unit",
            "business_unit_assignments__status__domain",
            "role_assignments__role",
            "role_assignments__status__domain",
        )
        .get(id=employee_id)
    )


def _get_employee_for_project_assignment(employee_id: int) -> Employee:
    try:
        return Employee.objects.select_related(
            "primary_business_unit",
            "country",
            "status",
        ).get(id=employee_id)
    except Employee.DoesNotExist as exc:
        raise AuthError("EMPLOYEE_NOT_FOUND", "Employee not found.", 404) from exc


def _actor_employee(current_user: CurrentUser) -> Employee | None:
    return Employee.objects.filter(id=current_user.employee_id).first()


def _employee_has_active_role(
    employee_id: int,
    *,
    role_code: str,
    business_unit_id: int | None = None,
) -> bool:
    assignments = EmployeeRole.objects.filter(
        employee_id=employee_id,
        role__domain__domain_code="ROLE_CODE",
        role__value_code=role_code,
        status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    )
    if business_unit_id is not None:
        assignments = assignments.filter(
            Q(business_unit_id=business_unit_id) | Q(business_unit__isnull=True)
        )
    return assignments.exists()


def _employee_has_active_business_unit_scope(employee_id: int, business_unit_id: int) -> bool:
    return EmployeeBusinessUnit.objects.filter(
        employee_id=employee_id,
        business_unit_id=business_unit_id,
        status__domain__domain_code="EMPLOYEE_BU_STATUS",
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    ).exists()


def _serialize_employee(employee: Employee) -> dict:
    active_roles = sorted(
        {
            assignment.role.value_code
            for assignment in employee.role_assignments.all()
            if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
            and assignment.status.value_code == "ACTIVE"
            and assignment.valid_to is None
        }
    )
    active_business_units = sorted(
        {
            assignment.business_unit
            for assignment in employee.business_unit_assignments.all()
            if assignment.status.domain.domain_code == "EMPLOYEE_BU_STATUS"
            and assignment.status.value_code == "ACTIVE"
            and assignment.valid_to is None
        },
        key=lambda business_unit: business_unit.bu_code,
    )
    return {
        "id": employee.id,
        "employee_code": employee.employee_code,
        "full_name": employee.full_name,
        "email": employee.email,
        "canonical_email": employee.canonical_email,
        "status": employee.status.value_code,
        "country": {
            "id": employee.country_id,
            "country_name": employee.country.country_name,
        },
        "primary_business_unit": {
            "id": employee.primary_business_unit_id,
            "bu_code": employee.primary_business_unit.bu_code,
            "name": employee.primary_business_unit.name,
        },
        "role_codes": active_roles,
        "business_units": [
            {"id": business_unit.id, "bu_code": business_unit.bu_code, "name": business_unit.name}
            for business_unit in active_business_units
        ],
    }


def _serialize_client(client: ClientRecord) -> dict:
    return {
        "id": client.id,
        "client_code": client.client_code,
        "name": client.name,
        "status": client.status.value_code,
        "country": {
            "id": client.country_id,
            "country_name": client.country.country_name,
        },
        "business_unit": {
            "id": client.business_unit_id,
            "bu_code": client.business_unit.bu_code,
            "name": client.business_unit.name,
        },
        "parent_client": (
            {
                "id": client.parent_client_id,
                "client_code": client.parent_client.client_code,
                "name": client.parent_client.name,
            }
            if client.parent_client_id is not None
            else None
        ),
    }


def _serialize_internal_category(category: InternalCategoryRecord) -> dict:
    return {
        "id": category.id,
        "category_code": category.category_code,
        "name": category.name,
        "description": category.description,
        "status": category.status.value_code,
        "country": {
            "id": category.country_id,
            "country_name": category.country.country_name,
        },
        "business_unit": {
            "id": category.business_unit_id,
            "bu_code": category.business_unit.bu_code,
            "name": category.business_unit.name,
        },
    }


def _serialize_cost_center(cost_center: CostCenterRecord) -> dict:
    return {
        "id": cost_center.id,
        "cost_center_code": cost_center.cost_center_code,
        "name": cost_center.name,
        "description": cost_center.description,
        "status": cost_center.status.value_code,
        "country": {
            "id": cost_center.country_id,
            "country_name": cost_center.country.country_name,
        },
        "business_unit": {
            "id": cost_center.business_unit_id,
            "bu_code": cost_center.business_unit.bu_code,
            "name": cost_center.business_unit.name,
        },
    }


def _serialize_general_charge_code(general_charge_code: GeneralChargeCodeRecord) -> dict:
    return {
        "id": general_charge_code.id,
        "code": general_charge_code.code,
        "name": general_charge_code.name,
        "charge_type": general_charge_code.charge_type.value_code,
        "billable_flag": general_charge_code.billable_flag,
        "common_code_flag": general_charge_code.common_code_flag,
        "requires_approval_flag": general_charge_code.requires_approval_flag,
        "description_required_flag": general_charge_code.description_required_flag,
        "valid_from": general_charge_code.valid_from.isoformat(),
        "valid_to": general_charge_code.valid_to.isoformat()
        if general_charge_code.valid_to
        else None,
        "status": general_charge_code.status.value_code,
        "country": {
            "id": general_charge_code.country_id,
            "country_name": general_charge_code.country.country_name,
        },
        "business_unit": {
            "id": general_charge_code.business_unit_id,
            "bu_code": general_charge_code.business_unit.bu_code,
            "name": general_charge_code.business_unit.name,
        },
    }


def _serialize_yearly_calendar(yearly_calendar: YearlyCalendar) -> dict:
    return {
        "id": yearly_calendar.id,
        "calendar_year": yearly_calendar.calendar_year,
        "calendar_name": yearly_calendar.calendar_name,
        "status": yearly_calendar.status.value_code,
        "name": f"{yearly_calendar.calendar_year} - {yearly_calendar.calendar_name}",
        "country": {
            "id": yearly_calendar.country_id,
            "country_name": yearly_calendar.country.country_name,
        },
        "business_unit": {
            "id": yearly_calendar.business_unit_id,
            "bu_code": yearly_calendar.business_unit.bu_code,
            "name": yearly_calendar.business_unit.name,
        },
    }


def _serialize_calendar_period_rule(rule: CalendarPeriodRule) -> dict:
    return {
        "id": rule.id,
        "name": (
            f"{rule.yearly_calendar.calendar_name} "
            f"({rule.effective_from.isoformat()} - {rule.effective_to.isoformat()})"
        ),
        "effective_from": rule.effective_from.isoformat(),
        "effective_to": rule.effective_to.isoformat(),
        "monday_max_hours": str(rule.monday_max_hours),
        "tuesday_max_hours": str(rule.tuesday_max_hours),
        "wednesday_max_hours": str(rule.wednesday_max_hours),
        "thursday_max_hours": str(rule.thursday_max_hours),
        "friday_max_hours": str(rule.friday_max_hours),
        "status": rule.status.value_code,
        "country": {
            "id": rule.country_id,
            "country_name": rule.country.country_name,
        },
        "yearly_calendar": _serialize_yearly_calendar(rule.yearly_calendar),
    }


def _serialize_project(project: Project) -> dict:
    return {
        "id": project.id,
        "project_code": project.project_code,
        "name": project.name,
        "description": project.description,
        "start_date": project.start_date.isoformat(),
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "close_date": project.close_date.isoformat() if project.close_date else None,
        "billable_flag": project.billable_flag,
        "status": project.status.value_code,
        "country": {
            "id": project.country_id,
            "country_name": project.country.country_name,
        },
        "business_unit": {
            "id": project.business_unit_id,
            "bu_code": project.business_unit.bu_code,
            "name": project.business_unit.name,
        },
        "project_owner_employee": {
            "id": project.project_owner_employee_id,
            "employee_code": project.project_owner_employee.employee_code,
            "full_name": project.project_owner_employee.full_name,
        },
        "project_manager_employee": {
            "id": project.project_manager_employee_id,
            "employee_code": project.project_manager_employee.employee_code,
            "full_name": project.project_manager_employee.full_name,
        },
        "client": {
            "id": project.client_id,
            "client_code": project.client.client_code,
            "name": project.client.name,
        },
        "internal_category": {
            "id": project.internal_category_id,
            "category_code": project.internal_category.category_code,
            "name": project.internal_category.name,
        },
        "cost_center": {
            "id": project.cost_center_id,
            "cost_center_code": project.cost_center.cost_center_code,
            "name": project.cost_center.name,
        },
    }


def _serialize_project_assignment(assignment: ProjectAssignment) -> dict:
    return {
        "id": assignment.id,
        "name": (
            f"{assignment.project.project_code} -> "
            f"{assignment.employee.employee_code} ({assignment.assignment_start_date.isoformat()})"
        ),
        "assignment_start_date": assignment.assignment_start_date.isoformat(),
        "assignment_end_date": assignment.assignment_end_date.isoformat()
        if assignment.assignment_end_date
        else None,
        "status": assignment.status.value_code,
        "project": {
            "id": assignment.project_id,
            "project_code": assignment.project.project_code,
            "name": assignment.project.name,
            "business_unit": {
                "id": assignment.project.business_unit_id,
                "bu_code": assignment.project.business_unit.bu_code,
                "name": assignment.project.business_unit.name,
            },
        },
        "employee": {
            "id": assignment.employee_id,
            "employee_code": assignment.employee.employee_code,
            "full_name": assignment.employee.full_name,
            "primary_business_unit": {
                "id": assignment.employee.primary_business_unit_id,
                "bu_code": assignment.employee.primary_business_unit.bu_code,
                "name": assignment.employee.primary_business_unit.name,
            },
        },
    }


def _serialize_country(country: Country) -> dict:
    return {
        "id": country.id,
        "name": country.country_name,
        "country_name": country.country_name,
        "status": country.status.value_code,
    }


class CountryManagementService:
    @staticmethod
    def list_countries(current_user: CurrentUser, *, status_code: str | None = None) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        countries = _apply_status_filter(
            Country.objects.select_related("status").order_by("country_name"),
            status_code,
        )
        return [_serialize_country(country) for country in countries]

    @staticmethod
    def get_country(current_user: CurrentUser, country_id: int) -> dict:
        _ensure_ts_admin_master(current_user)
        return _serialize_country(CountryManagementService._refresh_country(country_id))

    @staticmethod
    @transaction.atomic
    def create_country(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country_name = str(payload.get("country_name", "")).strip()
        if not country_name:
            raise AuthError("COUNTRY_NAME_REQUIRED", "Country name is required.", 400)
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        try:
            country = Country.objects.create(
                country_name=country_name,
                status=_ref_value("COUNTRY_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "COUNTRY_NAME_NOT_UNIQUE",
                "Country name must be unique.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="country",
            entity_id=country.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Country created by Timesheet Master Administrator.",
        )
        return _serialize_country(CountryManagementService._refresh_country(country.id))

    @staticmethod
    @transaction.atomic
    def update_country(current_user: CurrentUser, country_id: int, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country = CountryManagementService._refresh_country(country_id)
        changed_fields: list[tuple[str, str, str]] = []

        if "country_name" in payload:
            new_country_name = str(payload.get("country_name", "")).strip()
            if not new_country_name:
                raise AuthError("COUNTRY_NAME_REQUIRED", "Country name is required.", 400)
            if new_country_name != country.country_name:
                changed_fields.append(("country_name", country.country_name, new_country_name))
                country.country_name = new_country_name

        if "status_code" in payload:
            new_status = _ref_value("COUNTRY_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != country.status_id:
                changed_fields.append(("status", country.status.value_code, new_status.value_code))
                country.status = new_status

        if changed_fields:
            try:
                country.updated_by = current_user.email
                country.save()
            except IntegrityError as exc:
                raise AuthError(
                    "COUNTRY_NAME_NOT_UNIQUE",
                    "Country name must be unique.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="country",
                entity_id=country.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Country updated by Timesheet Master Administrator.",
            )

        return _serialize_country(CountryManagementService._refresh_country(country.id))

    @staticmethod
    def _refresh_country(country_id: int) -> Country:
        try:
            return Country.objects.select_related("status").get(id=country_id)
        except Country.DoesNotExist as exc:
            raise AuthError("COUNTRY_NOT_FOUND", "Country not found.", 404) from exc


class EmployeeManagementService:
    @staticmethod
    def list_employees(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        employees = _apply_status_filter(
            Employee.objects.select_related("primary_business_unit", "country", "status")
            .prefetch_related(
                "business_unit_assignments__business_unit",
                "business_unit_assignments__status__domain",
                "role_assignments__role",
                "role_assignments__status__domain",
            )
            .filter(
                primary_business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by("employee_code"),
            _parse_status_filter(status_code, domain_code="EMPLOYEE_STATUS"),
        )
        return [_serialize_employee(employee) for employee in employees]

    @staticmethod
    def get_employee(current_user: CurrentUser, employee_id: int) -> dict:
        _ensure_ts_admin(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        return _serialize_employee(employee)

    @staticmethod
    @transaction.atomic
    def create_employee(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        employee_code = str(payload.get("employee_code", "")).strip()
        full_name = str(payload.get("full_name", "")).strip()
        email = str(payload.get("email", "")).strip()
        if not employee_code:
            raise AuthError("EMPLOYEE_CODE_REQUIRED", "Employee code is required.", 400)
        if not full_name:
            raise AuthError("EMPLOYEE_NAME_REQUIRED", "Employee full name is required.", 400)
        if not email:
            raise AuthError("EMPLOYEE_EMAIL_REQUIRED", "Employee email is required.", 400)

        primary_business_unit_id, business_unit_ids = _parse_business_unit_scope(payload)
        _ensure_business_units_in_scope(current_user, business_unit_ids)
        role_codes = _parse_role_codes(payload)
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"

        try:
            primary_business_unit = BusinessUnit.objects.get(id=primary_business_unit_id)
        except BusinessUnit.DoesNotExist as exc:
            raise AuthError(
                "BUSINESS_UNIT_NOT_FOUND", "Primary Business Unit not found.", 404
            ) from exc
        _ensure_scoped_active_country_for_write(
            current_user,
            primary_business_unit.country,
            out_of_scope_message="Primary Business Unit is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="EMPLOYEE",
            expected_country_id=primary_business_unit.country_id,
            mismatch_message=(
                "Employee country must match the selected primary Business Unit country."
            ),
        )

        try:
            employee = Employee.objects.create(
                employee_code=employee_code,
                full_name=full_name,
                email=email,
                canonical_email=canonicalize_email(email),
                country=primary_business_unit.country,
                status=_ref_value("EMPLOYEE_STATUS", status_code),
                primary_business_unit=primary_business_unit,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "EMPLOYEE_EMAIL_NOT_UNIQUE",
                "Employee email must be unique.",
                400,
            ) from exc

        EmployeeManagementService._replace_business_unit_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            primary_business_unit_id=primary_business_unit_id,
            business_unit_ids=business_unit_ids,
            reason="Employee created with initial BU assignments.",
        )
        EmployeeManagementService._replace_role_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            role_codes=role_codes,
            reason="Employee created with initial role assignments.",
        )

        write_audit_event(
            action_code="CREATE",
            entity_name="employee",
            entity_id=employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=employee.primary_business_unit,
            reason_text="Employee created by Timesheet Administrator.",
        )
        return _serialize_employee(_refresh_employee(employee.id))

    @staticmethod
    @transaction.atomic
    def update_employee(current_user: CurrentUser, employee_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            employee.country,
            out_of_scope_message="Employee is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="EMPLOYEE",
            expected_country_id=employee.country_id,
            immutable_country_id=employee.country_id,
            mismatch_message="Employee country must match the employee country.",
            immutable_message="Employee country cannot be changed.",
        )

        changed_fields: list[tuple[str, str, str]] = []

        if "full_name" in payload:
            new_full_name = str(payload.get("full_name", "")).strip()
            if not new_full_name:
                raise AuthError("EMPLOYEE_NAME_REQUIRED", "Employee full name is required.", 400)
            if new_full_name != employee.full_name:
                changed_fields.append(("full_name", employee.full_name, new_full_name))
                employee.full_name = new_full_name

        if "email" in payload:
            new_email = str(payload.get("email", "")).strip()
            if not new_email:
                raise AuthError("EMPLOYEE_EMAIL_REQUIRED", "Employee email is required.", 400)
            new_canonical_email = canonicalize_email(new_email)
            if new_email != employee.email or new_canonical_email != employee.canonical_email:
                changed_fields.append(("email", employee.email, new_email))
                employee.email = new_email
                employee.canonical_email = new_canonical_email

        if "status_code" in payload:
            new_status = _ref_value("EMPLOYEE_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != employee.status_id:
                changed_fields.append(("status", employee.status.value_code, new_status.value_code))
                employee.status = new_status

        if changed_fields:
            try:
                employee.updated_by = current_user.email
                employee.save()
            except IntegrityError as exc:
                raise AuthError(
                    "EMPLOYEE_EMAIL_NOT_UNIQUE",
                    "Employee email must be unique.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="employee",
                entity_id=employee.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=employee.primary_business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Employee core data updated.",
            )

        return _serialize_employee(_refresh_employee(employee.id))

    @staticmethod
    @transaction.atomic
    def replace_roles(current_user: CurrentUser, employee_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        actor_employee = _actor_employee(current_user)
        role_codes = _parse_role_codes(payload)

        EmployeeManagementService._replace_role_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            role_codes=role_codes,
            reason="Employee roles replaced by administrator.",
        )
        return _serialize_employee(_refresh_employee(employee.id))

    @staticmethod
    @transaction.atomic
    def replace_business_units(current_user: CurrentUser, employee_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        actor_employee = _actor_employee(current_user)
        primary_business_unit_id, business_unit_ids = _parse_business_unit_scope(payload)
        _ensure_business_units_in_scope(current_user, business_unit_ids)
        _validate_optional_country_payload(
            payload,
            code_prefix="EMPLOYEE",
            expected_country_id=employee.country_id,
            immutable_country_id=employee.country_id,
            mismatch_message="Employee country must match the employee country.",
            immutable_message="Employee country cannot be changed.",
        )

        EmployeeManagementService._replace_business_unit_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            primary_business_unit_id=primary_business_unit_id,
            business_unit_ids=business_unit_ids,
            reason="Employee BU scope replaced by administrator.",
        )
        return _serialize_employee(_refresh_employee(employee.id))

    @staticmethod
    def _replace_role_assignments(
        current_user: CurrentUser,
        employee: Employee,
        *,
        actor_employee: Employee | None,
        role_codes: list[str],
        reason: str,
    ) -> None:
        desired_role_codes = set(role_codes)
        active_status = _ref_value("ROLE_ASSIGNMENT_STATUS", "ACTIVE")
        inactive_status = _ref_value("ROLE_ASSIGNMENT_STATUS", "INACTIVE")
        active_assignments = list(
            employee.role_assignments.select_related("role", "status", "status__domain").filter(
                valid_to__isnull=True
            )
        )

        current_active_codes = {
            assignment.role.value_code
            for assignment in active_assignments
            if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
            and assignment.status.value_code == "ACTIVE"
        }

        for assignment in active_assignments:
            if (
                assignment.role.value_code not in desired_role_codes
                and assignment.status.value_code == "ACTIVE"
            ):
                assignment.status = inactive_status
                assignment.valid_to = date.today()
                assignment.updated_by = current_user.email
                assignment.save(update_fields=["status", "valid_to", "updated_by", "updated_at"])
                write_audit_event(
                    action_code="UPDATE",
                    entity_name="employee_role",
                    entity_id=assignment.id,
                    actor_employee=actor_employee,
                    actor_email=current_user.email,
                    business_unit=employee.primary_business_unit,
                    field_name="role_code",
                    old_value=assignment.role.value_code,
                    new_value="",
                    reason_text=reason,
                )

        for role_code in sorted(desired_role_codes - current_active_codes):
            role = _ref_value("ROLE_CODE", role_code)
            existing_inactive = (
                employee.role_assignments.filter(
                    role=role, business_unit__isnull=True, valid_to=date.today()
                )
                .order_by("-id")
                .first()
            )
            if existing_inactive is not None:
                existing_inactive.status = active_status
                existing_inactive.valid_to = None
                existing_inactive.updated_by = current_user.email
                existing_inactive.save(
                    update_fields=["status", "valid_to", "updated_by", "updated_at"]
                )
                assignment = existing_inactive
            else:
                assignment = EmployeeRole.objects.create(
                    employee=employee,
                    role=role,
                    business_unit=None,
                    valid_from=date.today(),
                    status=active_status,
                    created_by=current_user.email,
                    updated_by=current_user.email,
                )
            write_audit_event(
                action_code="UPDATE",
                entity_name="employee_role",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=employee.primary_business_unit,
                field_name="role_code",
                old_value="",
                new_value=role_code,
                reason_text=reason,
            )

    @staticmethod
    def _replace_business_unit_assignments(
        current_user: CurrentUser,
        employee: Employee,
        *,
        actor_employee: Employee | None,
        primary_business_unit_id: int,
        business_unit_ids: set[int],
        reason: str,
    ) -> None:
        active_status = _ref_value("EMPLOYEE_BU_STATUS", "ACTIVE")
        inactive_status = _ref_value("EMPLOYEE_BU_STATUS", "INACTIVE")
        desired_business_units = {
            business_unit.id: business_unit
            for business_unit in BusinessUnit.objects.select_related("country", "country__status")
            .filter(id__in=business_unit_ids)
            .order_by("bu_code")
        }
        if primary_business_unit_id not in desired_business_units:
            raise AuthError(
                "EMPLOYEE_PRIMARY_BU_OUT_OF_SCOPE",
                "Primary Business Unit must be included in the employee scope.",
                400,
            )
        if employee.country_id != desired_business_units[primary_business_unit_id].country_id:
            raise AuthError(
                "EMPLOYEE_COUNTRY_IMMUTABLE",
                "Employee country cannot be changed.",
                400,
            )
        desired_country_ids = {
            business_unit.country_id for business_unit in desired_business_units.values()
        }
        if len(desired_country_ids) != 1:
            raise AuthError(
                "EMPLOYEE_BUSINESS_UNIT_COUNTRY_MISMATCH",
                "All employee Business Units must belong to the same country.",
                400,
            )
        desired_country = next(iter(desired_business_units.values())).country
        _ensure_scoped_active_country_for_write(
            current_user,
            desired_country,
            out_of_scope_message="Employee Business Units must stay inside your active country.",
        )

        active_assignments = {
            assignment.business_unit_id: assignment
            for assignment in employee.business_unit_assignments.select_related(
                "business_unit",
                "status",
                "status__domain",
            ).filter(valid_to__isnull=True)
            if assignment.status.domain.domain_code == "EMPLOYEE_BU_STATUS"
            and assignment.status.value_code == "ACTIVE"
        }
        previous_primary_bu_code = employee.primary_business_unit.bu_code
        previous_scope_codes = sorted(
            assignment.business_unit.bu_code for assignment in active_assignments.values()
        )

        for assignment in active_assignments.values():
            if assignment.is_primary_flag:
                assignment.is_primary_flag = False
                assignment.updated_by = current_user.email
                assignment.save(update_fields=["is_primary_flag", "updated_by", "updated_at"])

        for business_unit_id, assignment in active_assignments.items():
            if business_unit_id not in desired_business_units:
                assignment.status = inactive_status
                assignment.valid_to = date.today()
                assignment.updated_by = current_user.email
                assignment.save(update_fields=["status", "valid_to", "updated_by", "updated_at"])

        for business_unit_id, business_unit in desired_business_units.items():
            assignment = active_assignments.get(business_unit_id)
            is_primary = business_unit_id == primary_business_unit_id
            if assignment is None:
                EmployeeBusinessUnit.objects.create(
                    employee=employee,
                    business_unit=business_unit,
                    is_primary_flag=is_primary,
                    status=active_status,
                    valid_from=date.today(),
                    created_by=current_user.email,
                    updated_by=current_user.email,
                )
            else:
                assignment.is_primary_flag = is_primary
                assignment.updated_by = current_user.email
                assignment.save(update_fields=["is_primary_flag", "updated_by", "updated_at"])

        if employee.primary_business_unit_id != primary_business_unit_id:
            employee.primary_business_unit = desired_business_units[primary_business_unit_id]
            employee.updated_by = current_user.email
            employee.save(update_fields=["primary_business_unit", "updated_by", "updated_at"])
            write_audit_event(
                action_code="UPDATE",
                entity_name="employee",
                entity_id=employee.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=employee.primary_business_unit,
                field_name="primary_business_unit",
                old_value=previous_primary_bu_code,
                new_value=employee.primary_business_unit.bu_code,
                reason_text=reason,
            )

        new_scope_codes = sorted(
            business_unit.bu_code for business_unit in desired_business_units.values()
        )
        if previous_scope_codes != new_scope_codes:
            write_audit_event(
                action_code="UPDATE",
                entity_name="employee_business_unit",
                entity_id=employee.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=employee.primary_business_unit,
                field_name="business_unit_scope",
                old_value=",".join(previous_scope_codes),
                new_value=",".join(new_scope_codes),
                reason_text=reason,
            )


class ClientManagementService:
    @staticmethod
    def list_clients(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        clients = _apply_status_filter(
            ClientRecord.objects.select_related(
                "business_unit",
                "country",
                "parent_client",
                "status",
            )
            .filter(
                business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by("business_unit__bu_code", "client_code"),
            _parse_status_filter(status_code, domain_code="CLIENT_STATUS"),
        )
        return [_serialize_client(client) for client in clients]

    @staticmethod
    def get_client(current_user: CurrentUser, client_id: int) -> dict:
        _ensure_ts_admin(current_user)
        client = ClientManagementService._get_scoped_client(current_user, client_id)
        return _serialize_client(client)

    @staticmethod
    @transaction.atomic
    def create_client(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="CLIENT_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            business_unit.country,
            out_of_scope_message="Client Business Unit is outside your active country.",
        )

        client_code = str(payload.get("client_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not client_code:
            raise AuthError("CLIENT_CODE_REQUIRED", "Client code is required.", 400)
        if not name:
            raise AuthError("CLIENT_NAME_REQUIRED", "Client name is required.", 400)

        parent_client = ClientManagementService._resolve_parent_client(
            current_user,
            business_unit_id=business_unit_id,
            parent_client_id=payload.get("parent_client_id"),
        )
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_country_payload(
            payload,
            code_prefix="CLIENT",
            expected_country_id=business_unit.country_id,
            mismatch_message="Client country must match the selected Business Unit country.",
        )

        try:
            client = ClientRecord.objects.create(
                business_unit=business_unit,
                country=business_unit.country,
                parent_client=parent_client,
                client_code=client_code,
                name=name,
                status=_ref_value("CLIENT_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "CLIENT_CODE_NOT_UNIQUE",
                "Client code must be unique within the Business Unit.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="client",
            entity_id=client.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=client.business_unit,
            reason_text="Client created by Timesheet Administrator.",
        )
        return _serialize_client(ClientManagementService._refresh_client(client.id))

    @staticmethod
    @transaction.atomic
    def update_client(current_user: CurrentUser, client_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        client = ClientManagementService._get_scoped_client(current_user, client_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            client.country,
            out_of_scope_message="Client is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="CLIENT",
            expected_country_id=client.country_id,
            immutable_country_id=client.country_id,
            mismatch_message="Client country must match the client country.",
            immutable_message="Client country cannot be changed.",
        )

        if (
            "business_unit_id" in payload
            and _parse_required_int(
                payload.get("business_unit_id"),
                code="CLIENT_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id must be a valid Business Unit identifier.",
            )
            != client.business_unit_id
        ):
            raise AuthError(
                "CLIENT_BUSINESS_UNIT_IMMUTABLE",
                "Client Business Unit cannot be changed.",
                400,
            )

        changed_fields: list[tuple[str, str, str]] = []

        if "client_code" in payload:
            new_client_code = str(payload.get("client_code", "")).strip()
            if not new_client_code:
                raise AuthError("CLIENT_CODE_REQUIRED", "Client code is required.", 400)
            if new_client_code != client.client_code:
                changed_fields.append(("client_code", client.client_code, new_client_code))
                client.client_code = new_client_code

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError("CLIENT_NAME_REQUIRED", "Client name is required.", 400)
            if new_name != client.name:
                changed_fields.append(("name", client.name, new_name))
                client.name = new_name

        if "status_code" in payload:
            new_status = _ref_value("CLIENT_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != client.status_id:
                changed_fields.append(("status", client.status.value_code, new_status.value_code))
                client.status = new_status

        if "parent_client_id" in payload:
            new_parent_client = ClientManagementService._resolve_parent_client(
                current_user,
                business_unit_id=client.business_unit_id,
                parent_client_id=payload.get("parent_client_id"),
            )
            old_parent_code = client.parent_client.client_code if client.parent_client_id else ""
            new_parent_code = new_parent_client.client_code if new_parent_client is not None else ""
            if client.parent_client_id != (new_parent_client.id if new_parent_client else None):
                changed_fields.append(("parent_client", old_parent_code, new_parent_code))
                client.parent_client = new_parent_client

        if changed_fields:
            try:
                client.updated_by = current_user.email
                client.save()
            except IntegrityError as exc:
                raise AuthError(
                    "CLIENT_CODE_NOT_UNIQUE",
                    "Client code must be unique within the Business Unit.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="client",
                entity_id=client.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=client.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Client updated by Timesheet Administrator.",
            )

        return _serialize_client(ClientManagementService._refresh_client(client.id))

    @staticmethod
    def _get_scoped_client(current_user: CurrentUser, client_id: int) -> ClientRecord:
        try:
            client = ClientRecord.objects.select_related(
                "business_unit", "country", "parent_client", "status"
            ).get(id=client_id)
        except ClientRecord.DoesNotExist as exc:
            raise AuthError("CLIENT_NOT_FOUND", "Client not found.", 404) from exc

        _ensure_business_units_in_scope(current_user, {client.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            client.country_id,
            message="Client is outside your active country.",
        )
        return client

    @staticmethod
    def _refresh_client(client_id: int) -> ClientRecord:
        return ClientRecord.objects.select_related(
            "business_unit", "country", "parent_client", "status"
        ).get(id=client_id)

    @staticmethod
    def _resolve_parent_client(
        current_user: CurrentUser,
        *,
        business_unit_id: int,
        parent_client_id: object,
    ) -> ClientRecord | None:
        if parent_client_id in (None, ""):
            return None

        resolved_parent_client_id = _parse_required_int(
            parent_client_id,
            code="CLIENT_PARENT_INVALID",
            message="parent_client_id must be a valid client identifier.",
        )
        try:
            parent_client = ClientRecord.objects.select_related("business_unit").get(
                id=resolved_parent_client_id
            )
        except ClientRecord.DoesNotExist as exc:
            raise AuthError("CLIENT_PARENT_NOT_FOUND", "Parent client not found.", 404) from exc

        _ensure_business_units_in_scope(current_user, {parent_client.business_unit_id})
        if parent_client.business_unit_id != business_unit_id:
            raise AuthError(
                "CLIENT_PARENT_BU_MISMATCH",
                "Parent client must belong to the same Business Unit.",
                400,
            )
        return parent_client


class InternalCategoryManagementService:
    @staticmethod
    def list_categories(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        categories = _apply_status_filter(
            InternalCategoryRecord.objects.select_related("business_unit", "country", "status")
            .filter(
                business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by("business_unit__bu_code", "category_code"),
            _parse_status_filter(status_code, domain_code="INTERNAL_CATEGORY_STATUS"),
        )
        return [_serialize_internal_category(category) for category in categories]

    @staticmethod
    def get_category(current_user: CurrentUser, category_id: int) -> dict:
        _ensure_ts_admin(current_user)
        category = InternalCategoryManagementService._get_scoped_category(current_user, category_id)
        return _serialize_internal_category(category)

    @staticmethod
    @transaction.atomic
    def create_category(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="INTERNAL_CATEGORY_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            business_unit.country,
            out_of_scope_message="Internal category Business Unit is outside your active country.",
        )

        category_code = str(payload.get("category_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not category_code:
            raise AuthError("INTERNAL_CATEGORY_CODE_REQUIRED", "Category code is required.", 400)
        if not name:
            raise AuthError("INTERNAL_CATEGORY_NAME_REQUIRED", "Category name is required.", 400)

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_country_payload(
            payload,
            code_prefix="INTERNAL_CATEGORY",
            expected_country_id=business_unit.country_id,
            mismatch_message=(
                "Internal category country must match the selected Business Unit country."
            ),
        )

        try:
            category = InternalCategoryRecord.objects.create(
                business_unit=business_unit,
                country=business_unit.country,
                category_code=category_code,
                name=name,
                description=description,
                status=_ref_value("INTERNAL_CATEGORY_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "INTERNAL_CATEGORY_CODE_NOT_UNIQUE",
                "Category code must be unique within the Business Unit.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="internal_category",
            entity_id=category.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=category.business_unit,
            reason_text="Internal category created by Timesheet Administrator.",
        )
        return _serialize_internal_category(
            InternalCategoryManagementService._refresh_category(category.id)
        )

    @staticmethod
    @transaction.atomic
    def update_category(current_user: CurrentUser, category_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        category = InternalCategoryManagementService._get_scoped_category(current_user, category_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            category.country,
            out_of_scope_message="Internal category is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="INTERNAL_CATEGORY",
            expected_country_id=category.country_id,
            immutable_country_id=category.country_id,
            mismatch_message="Internal category country must match the internal category country.",
            immutable_message="Internal category country cannot be changed.",
        )

        if (
            "business_unit_id" in payload
            and _parse_required_int(
                payload.get("business_unit_id"),
                code="INTERNAL_CATEGORY_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id must be a valid Business Unit identifier.",
            )
            != category.business_unit_id
        ):
            raise AuthError(
                "INTERNAL_CATEGORY_BUSINESS_UNIT_IMMUTABLE",
                "Internal category Business Unit cannot be changed.",
                400,
            )

        changed_fields: list[tuple[str, str, str]] = []

        if "category_code" in payload:
            new_category_code = str(payload.get("category_code", "")).strip()
            if not new_category_code:
                raise AuthError(
                    "INTERNAL_CATEGORY_CODE_REQUIRED", "Category code is required.", 400
                )
            if new_category_code != category.category_code:
                changed_fields.append(("category_code", category.category_code, new_category_code))
                category.category_code = new_category_code

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError(
                    "INTERNAL_CATEGORY_NAME_REQUIRED", "Category name is required.", 400
                )
            if new_name != category.name:
                changed_fields.append(("name", category.name, new_name))
                category.name = new_name

        if "description" in payload:
            new_description = str(payload.get("description", "")).strip()
            if new_description != category.description:
                changed_fields.append(("description", category.description, new_description))
                category.description = new_description

        if "status_code" in payload:
            new_status = _ref_value(
                "INTERNAL_CATEGORY_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != category.status_id:
                changed_fields.append(("status", category.status.value_code, new_status.value_code))
                category.status = new_status

        if changed_fields:
            try:
                category.updated_by = current_user.email
                category.save()
            except IntegrityError as exc:
                raise AuthError(
                    "INTERNAL_CATEGORY_CODE_NOT_UNIQUE",
                    "Category code must be unique within the Business Unit.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="internal_category",
                entity_id=category.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=category.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Internal category updated by Timesheet Administrator.",
            )

        return _serialize_internal_category(
            InternalCategoryManagementService._refresh_category(category.id)
        )

    @staticmethod
    def _get_scoped_category(
        current_user: CurrentUser,
        category_id: int,
    ) -> InternalCategoryRecord:
        try:
            category = InternalCategoryRecord.objects.select_related(
                "business_unit", "country", "status"
            ).get(id=category_id)
        except InternalCategoryRecord.DoesNotExist as exc:
            raise AuthError(
                "INTERNAL_CATEGORY_NOT_FOUND", "Internal category not found.", 404
            ) from exc

        _ensure_business_units_in_scope(current_user, {category.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            category.country_id,
            message="Internal category is outside your active country.",
        )
        return category

    @staticmethod
    def _refresh_category(category_id: int) -> InternalCategoryRecord:
        return InternalCategoryRecord.objects.select_related(
            "business_unit",
            "country",
            "status",
        ).get(id=category_id)


class CostCenterManagementService:
    @staticmethod
    def list_cost_centers(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        cost_centers = _apply_status_filter(
            CostCenterRecord.objects.select_related("business_unit", "country", "status")
            .filter(
                business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by("business_unit__bu_code", "cost_center_code"),
            _parse_status_filter(status_code, domain_code="COST_CENTER_STATUS"),
        )
        return [_serialize_cost_center(cost_center) for cost_center in cost_centers]

    @staticmethod
    def get_cost_center(current_user: CurrentUser, cost_center_id: int) -> dict:
        _ensure_ts_admin(current_user)
        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user, cost_center_id
        )
        return _serialize_cost_center(cost_center)

    @staticmethod
    @transaction.atomic
    def create_cost_center(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="COST_CENTER_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            business_unit.country,
            out_of_scope_message="Cost center Business Unit is outside your active country.",
        )

        cost_center_code = str(payload.get("cost_center_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not cost_center_code:
            raise AuthError("COST_CENTER_CODE_REQUIRED", "Cost center code is required.", 400)
        if not name:
            raise AuthError("COST_CENTER_NAME_REQUIRED", "Cost center name is required.", 400)

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_country_payload(
            payload,
            code_prefix="COST_CENTER",
            expected_country_id=business_unit.country_id,
            mismatch_message="Cost center country must match the selected Business Unit country.",
        )

        try:
            cost_center = CostCenterRecord.objects.create(
                business_unit=business_unit,
                country=business_unit.country,
                cost_center_code=cost_center_code,
                name=name,
                description=description,
                status=_ref_value("COST_CENTER_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "COST_CENTER_CODE_NOT_UNIQUE",
                "Cost center code must be unique within the Business Unit.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="cost_center",
            entity_id=cost_center.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=cost_center.business_unit,
            reason_text="Cost center created by Timesheet Administrator.",
        )
        return _serialize_cost_center(
            CostCenterManagementService._refresh_cost_center(cost_center.id)
        )

    @staticmethod
    @transaction.atomic
    def update_cost_center(current_user: CurrentUser, cost_center_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user, cost_center_id
        )
        _ensure_scoped_active_country_for_write(
            current_user,
            cost_center.country,
            out_of_scope_message="Cost center is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="COST_CENTER",
            expected_country_id=cost_center.country_id,
            immutable_country_id=cost_center.country_id,
            mismatch_message="Cost center country must match the cost center country.",
            immutable_message="Cost center country cannot be changed.",
        )

        if (
            "business_unit_id" in payload
            and _parse_required_int(
                payload.get("business_unit_id"),
                code="COST_CENTER_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id must be a valid Business Unit identifier.",
            )
            != cost_center.business_unit_id
        ):
            raise AuthError(
                "COST_CENTER_BUSINESS_UNIT_IMMUTABLE",
                "Cost center Business Unit cannot be changed.",
                400,
            )

        changed_fields: list[tuple[str, str, str]] = []

        if "cost_center_code" in payload:
            new_cost_center_code = str(payload.get("cost_center_code", "")).strip()
            if not new_cost_center_code:
                raise AuthError("COST_CENTER_CODE_REQUIRED", "Cost center code is required.", 400)
            if new_cost_center_code != cost_center.cost_center_code:
                changed_fields.append(
                    ("cost_center_code", cost_center.cost_center_code, new_cost_center_code)
                )
                cost_center.cost_center_code = new_cost_center_code

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError("COST_CENTER_NAME_REQUIRED", "Cost center name is required.", 400)
            if new_name != cost_center.name:
                changed_fields.append(("name", cost_center.name, new_name))
                cost_center.name = new_name

        if "description" in payload:
            new_description = str(payload.get("description", "")).strip()
            if new_description != cost_center.description:
                changed_fields.append(("description", cost_center.description, new_description))
                cost_center.description = new_description

        if "status_code" in payload:
            new_status = _ref_value(
                "COST_CENTER_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != cost_center.status_id:
                changed_fields.append(
                    ("status", cost_center.status.value_code, new_status.value_code)
                )
                cost_center.status = new_status

        if changed_fields:
            try:
                cost_center.updated_by = current_user.email
                cost_center.save()
            except IntegrityError as exc:
                raise AuthError(
                    "COST_CENTER_CODE_NOT_UNIQUE",
                    "Cost center code must be unique within the Business Unit.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="cost_center",
                entity_id=cost_center.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=cost_center.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Cost center updated by Timesheet Administrator.",
            )

        return _serialize_cost_center(
            CostCenterManagementService._refresh_cost_center(cost_center.id)
        )

    @staticmethod
    def _get_scoped_cost_center(
        current_user: CurrentUser,
        cost_center_id: int,
    ) -> CostCenterRecord:
        try:
            cost_center = CostCenterRecord.objects.select_related(
                "business_unit", "country", "status"
            ).get(id=cost_center_id)
        except CostCenterRecord.DoesNotExist as exc:
            raise AuthError("COST_CENTER_NOT_FOUND", "Cost center not found.", 404) from exc

        _ensure_business_units_in_scope(current_user, {cost_center.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            cost_center.country_id,
            message="Cost center is outside your active country.",
        )
        return cost_center

    @staticmethod
    def _refresh_cost_center(cost_center_id: int) -> CostCenterRecord:
        return CostCenterRecord.objects.select_related("business_unit", "country", "status").get(
            id=cost_center_id
        )


class GeneralChargeCodeManagementService:
    @staticmethod
    def list_general_charge_codes(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        general_charge_codes = _apply_status_filter(
            GeneralChargeCodeRecord.objects.select_related(
                "business_unit",
                "country",
                "charge_type",
                "status",
            )
            .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
            .filter(country_id=current_user.country_id)
            .order_by("business_unit__bu_code", "code"),
            _parse_status_filter(status_code, domain_code="GENERAL_CHARGE_CODE_STATUS"),
        )
        return [
            _serialize_general_charge_code(general_charge_code)
            for general_charge_code in general_charge_codes
        ]

    @staticmethod
    def get_general_charge_code(current_user: CurrentUser, general_charge_code_id: int) -> dict:
        _ensure_ts_admin(current_user)
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            general_charge_code_id,
        )
        return _serialize_general_charge_code(general_charge_code)

    @staticmethod
    @transaction.atomic
    def create_general_charge_code(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="GENERAL_CHARGE_CODE_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            business_unit.country,
            out_of_scope_message=(
                "General charge code Business Unit is outside your active country."
            ),
        )

        code = str(payload.get("code", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not code:
            raise AuthError(
                "GENERAL_CHARGE_CODE_CODE_REQUIRED", "General charge code is required.", 400
            )
        if not name:
            raise AuthError(
                "GENERAL_CHARGE_CODE_NAME_REQUIRED", "General charge code name is required.", 400
            )

        valid_from = _parse_iso_date(
            payload.get("valid_from"),
            code="GENERAL_CHARGE_CODE_VALID_FROM_REQUIRED",
            message="valid_from must be a valid ISO date.",
        )
        valid_to = _parse_optional_iso_date(
            payload.get("valid_to"),
            code="GENERAL_CHARGE_CODE_VALID_TO_INVALID",
            message="valid_to must be a valid ISO date.",
        )
        GeneralChargeCodeManagementService._validate_date_range(valid_from, valid_to)

        charge_type_code = str(payload.get("charge_type_code", "STANDARD")).strip() or "STANDARD"
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_country_payload(
            payload,
            code_prefix="GENERAL_CHARGE_CODE",
            expected_country_id=business_unit.country_id,
            mismatch_message=(
                "General charge code country must match the selected Business Unit country."
            ),
        )

        try:
            general_charge_code = GeneralChargeCodeRecord.objects.create(
                business_unit=business_unit,
                country=business_unit.country,
                code=code,
                name=name,
                charge_type=_ref_value("GENERAL_CHARGE_CODE_TYPE", charge_type_code),
                billable_flag=bool(payload.get("billable_flag", False)),
                common_code_flag=bool(payload.get("common_code_flag", False)),
                requires_approval_flag=bool(payload.get("requires_approval_flag", False)),
                description_required_flag=bool(payload.get("description_required_flag", False)),
                valid_from=valid_from,
                valid_to=valid_to,
                status=_ref_value("GENERAL_CHARGE_CODE_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_NOT_UNIQUE",
                "General charge code must be unique within the Business Unit.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="general_charge_code",
            entity_id=general_charge_code.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=general_charge_code.business_unit,
            reason_text="General charge code created by Timesheet Administrator.",
        )
        return _serialize_general_charge_code(
            GeneralChargeCodeManagementService._refresh_general_charge_code(general_charge_code.id)
        )

    @staticmethod
    @transaction.atomic
    def update_general_charge_code(
        current_user: CurrentUser,
        general_charge_code_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            general_charge_code_id,
        )
        _ensure_scoped_active_country_for_write(
            current_user,
            general_charge_code.country,
            out_of_scope_message="General charge code is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="GENERAL_CHARGE_CODE",
            expected_country_id=general_charge_code.country_id,
            immutable_country_id=general_charge_code.country_id,
            mismatch_message="General charge code country must match the existing country.",
            immutable_message="General charge code country cannot be changed.",
        )

        if (
            "business_unit_id" in payload
            and _parse_required_int(
                payload.get("business_unit_id"),
                code="GENERAL_CHARGE_CODE_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id must be a valid Business Unit identifier.",
            )
            != general_charge_code.business_unit_id
        ):
            raise AuthError(
                "GENERAL_CHARGE_CODE_BUSINESS_UNIT_IMMUTABLE",
                "General charge code Business Unit cannot be changed.",
                400,
            )

        changed_fields: list[tuple[str, str, str]] = []

        if "code" in payload:
            new_code = str(payload.get("code", "")).strip()
            if not new_code:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_CODE_REQUIRED", "General charge code is required.", 400
                )
            if new_code != general_charge_code.code:
                changed_fields.append(("code", general_charge_code.code, new_code))
                general_charge_code.code = new_code

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_NAME_REQUIRED",
                    "General charge code name is required.",
                    400,
                )
            if new_name != general_charge_code.name:
                changed_fields.append(("name", general_charge_code.name, new_name))
                general_charge_code.name = new_name

        if "charge_type_code" in payload:
            new_charge_type = _ref_value(
                "GENERAL_CHARGE_CODE_TYPE",
                str(payload.get("charge_type_code", "")).strip(),
            )
            if new_charge_type.id != general_charge_code.charge_type_id:
                changed_fields.append(
                    (
                        "charge_type",
                        general_charge_code.charge_type.value_code,
                        new_charge_type.value_code,
                    )
                )
                general_charge_code.charge_type = new_charge_type

        for field_name in (
            "billable_flag",
            "common_code_flag",
            "requires_approval_flag",
            "description_required_flag",
        ):
            if field_name in payload:
                new_value = bool(payload.get(field_name))
                if getattr(general_charge_code, field_name) != new_value:
                    changed_fields.append(
                        (field_name, str(getattr(general_charge_code, field_name)), str(new_value))
                    )
                    setattr(general_charge_code, field_name, new_value)

        proposed_valid_from = general_charge_code.valid_from
        proposed_valid_to = general_charge_code.valid_to
        if "valid_from" in payload:
            proposed_valid_from = _parse_iso_date(
                payload.get("valid_from"),
                code="GENERAL_CHARGE_CODE_VALID_FROM_REQUIRED",
                message="valid_from must be a valid ISO date.",
            )
        if "valid_to" in payload:
            proposed_valid_to = _parse_optional_iso_date(
                payload.get("valid_to"),
                code="GENERAL_CHARGE_CODE_VALID_TO_INVALID",
                message="valid_to must be a valid ISO date.",
            )
        GeneralChargeCodeManagementService._validate_date_range(
            proposed_valid_from, proposed_valid_to
        )
        if proposed_valid_from != general_charge_code.valid_from:
            changed_fields.append(
                (
                    "valid_from",
                    general_charge_code.valid_from.isoformat(),
                    proposed_valid_from.isoformat(),
                )
            )
            general_charge_code.valid_from = proposed_valid_from
        if proposed_valid_to != general_charge_code.valid_to:
            changed_fields.append(
                (
                    "valid_to",
                    general_charge_code.valid_to.isoformat()
                    if general_charge_code.valid_to
                    else "",
                    proposed_valid_to.isoformat() if proposed_valid_to else "",
                )
            )
            general_charge_code.valid_to = proposed_valid_to

        if "status_code" in payload:
            new_status = _ref_value(
                "GENERAL_CHARGE_CODE_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != general_charge_code.status_id:
                changed_fields.append(
                    ("status", general_charge_code.status.value_code, new_status.value_code)
                )
                general_charge_code.status = new_status

        if changed_fields:
            try:
                general_charge_code.updated_by = current_user.email
                general_charge_code.save()
            except IntegrityError as exc:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_NOT_UNIQUE",
                    "General charge code must be unique within the Business Unit.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="general_charge_code",
                entity_id=general_charge_code.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=general_charge_code.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="General charge code updated by Timesheet Administrator.",
            )

        return _serialize_general_charge_code(
            GeneralChargeCodeManagementService._refresh_general_charge_code(general_charge_code.id)
        )

    @staticmethod
    def _validate_date_range(valid_from: date, valid_to: date | None) -> None:
        if valid_to is not None and valid_to < valid_from:
            raise AuthError(
                "GENERAL_CHARGE_CODE_DATE_RANGE_INVALID",
                "valid_to must be on or after valid_from.",
                400,
            )

    @staticmethod
    def _get_scoped_general_charge_code(
        current_user: CurrentUser,
        general_charge_code_id: int,
    ) -> GeneralChargeCodeRecord:
        try:
            general_charge_code = GeneralChargeCodeRecord.objects.select_related(
                "business_unit", "country", "charge_type", "status"
            ).get(id=general_charge_code_id)
        except GeneralChargeCodeRecord.DoesNotExist as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_NOT_FOUND",
                "General charge code not found.",
                404,
            ) from exc

        _ensure_business_units_in_scope(current_user, {general_charge_code.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            general_charge_code.country_id,
            message="General charge code is outside your active country.",
        )
        return general_charge_code

    @staticmethod
    def _refresh_general_charge_code(
        general_charge_code_id: int,
    ) -> GeneralChargeCodeRecord:
        return GeneralChargeCodeRecord.objects.select_related(
            "business_unit", "country", "charge_type", "status"
        ).get(id=general_charge_code_id)


class CalendarPeriodRuleManagementService:
    @staticmethod
    def list_period_rules(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        period_rules = _apply_status_filter(
            CalendarPeriodRule.objects.select_related(
                "country",
                "yearly_calendar",
                "yearly_calendar__country",
                "yearly_calendar__business_unit",
                "yearly_calendar__status",
                "status",
            )
            .filter(
                yearly_calendar__business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by(
                "yearly_calendar__business_unit__bu_code",
                "yearly_calendar__calendar_year",
                "yearly_calendar__calendar_name",
                "effective_from",
            ),
            _parse_status_filter(status_code, domain_code="CALENDAR_PERIOD_STATUS"),
        )
        return [_serialize_calendar_period_rule(period_rule) for period_rule in period_rules]

    @staticmethod
    def list_yearly_calendars(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        calendars = (
            YearlyCalendar.objects.select_related("business_unit", "country", "status")
            .filter(
                business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by("business_unit__bu_code", "calendar_year", "calendar_name")
        )
        return [_serialize_yearly_calendar(calendar) for calendar in calendars]

    @staticmethod
    def get_period_rule(current_user: CurrentUser, period_rule_id: int) -> dict:
        _ensure_ts_admin(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        return _serialize_calendar_period_rule(period_rule)

    @staticmethod
    @transaction.atomic
    def create_period_rule(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = CalendarPeriodRuleManagementService._get_scoped_yearly_calendar(
            current_user,
            _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED",
                message="yearly_calendar_id is required.",
            ),
        )
        _ensure_scoped_active_country_for_write(
            current_user,
            yearly_calendar.country,
            out_of_scope_message="Yearly calendar is outside your active country.",
        )
        effective_from = _parse_iso_date(
            payload.get("effective_from"),
            code="CALENDAR_PERIOD_RULE_EFFECTIVE_FROM_REQUIRED",
            message="effective_from must be a valid ISO date.",
        )
        effective_to = _parse_iso_date(
            payload.get("effective_to"),
            code="CALENDAR_PERIOD_RULE_EFFECTIVE_TO_REQUIRED",
            message="effective_to must be a valid ISO date.",
        )
        CalendarPeriodRuleManagementService._validate_date_range(effective_from, effective_to)
        CalendarPeriodRuleManagementService._ensure_no_overlap(
            yearly_calendar.id,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="CALENDAR_PERIOD_RULE",
            expected_country_id=yearly_calendar.country_id,
            mismatch_message=(
                "Calendar Period Rule country must match the selected yearly calendar country."
            ),
        )
        period_rule = CalendarPeriodRule.objects.create(
            yearly_calendar=yearly_calendar,
            country=yearly_calendar.country,
            effective_from=effective_from,
            effective_to=effective_to,
            monday_max_hours=_parse_decimal(
                payload.get("monday_max_hours"),
                code="CALENDAR_PERIOD_RULE_MONDAY_REQUIRED",
                message="monday_max_hours is required.",
            ),
            tuesday_max_hours=_parse_decimal(
                payload.get("tuesday_max_hours"),
                code="CALENDAR_PERIOD_RULE_TUESDAY_REQUIRED",
                message="tuesday_max_hours is required.",
            ),
            wednesday_max_hours=_parse_decimal(
                payload.get("wednesday_max_hours"),
                code="CALENDAR_PERIOD_RULE_WEDNESDAY_REQUIRED",
                message="wednesday_max_hours is required.",
            ),
            thursday_max_hours=_parse_decimal(
                payload.get("thursday_max_hours"),
                code="CALENDAR_PERIOD_RULE_THURSDAY_REQUIRED",
                message="thursday_max_hours is required.",
            ),
            friday_max_hours=_parse_decimal(
                payload.get("friday_max_hours"),
                code="CALENDAR_PERIOD_RULE_FRIDAY_REQUIRED",
                message="friday_max_hours is required.",
            ),
            status=_ref_value(
                "CALENDAR_PERIOD_STATUS",
                str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
            ),
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        write_audit_event(
            action_code="CREATE",
            entity_name="calendar_period_rule",
            entity_id=period_rule.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=yearly_calendar.business_unit,
            reason_text="Calendar period rule created by Timesheet Administrator.",
        )
        return _serialize_calendar_period_rule(
            CalendarPeriodRuleManagementService._refresh_period_rule(period_rule.id)
        )

    @staticmethod
    @transaction.atomic
    def update_period_rule(current_user: CurrentUser, period_rule_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        _ensure_scoped_active_country_for_write(
            current_user,
            period_rule.country,
            out_of_scope_message="Calendar Period Rule is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="CALENDAR_PERIOD_RULE",
            expected_country_id=period_rule.country_id,
            immutable_country_id=period_rule.country_id,
            mismatch_message="Calendar Period Rule country must match the existing country.",
            immutable_message="Calendar Period Rule country cannot be changed.",
        )
        if (
            "yearly_calendar_id" in payload
            and _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED",
                message="yearly_calendar_id must be a valid calendar identifier.",
            )
            != period_rule.yearly_calendar_id
        ):
            raise AuthError(
                "CALENDAR_PERIOD_RULE_CALENDAR_IMMUTABLE",
                "Calendar Period Rule calendar cannot be changed.",
                400,
            )
        proposed_effective_from = period_rule.effective_from
        proposed_effective_to = period_rule.effective_to
        if "effective_from" in payload:
            proposed_effective_from = _parse_iso_date(
                payload.get("effective_from"),
                code="CALENDAR_PERIOD_RULE_EFFECTIVE_FROM_REQUIRED",
                message="effective_from must be a valid ISO date.",
            )
        if "effective_to" in payload:
            proposed_effective_to = _parse_iso_date(
                payload.get("effective_to"),
                code="CALENDAR_PERIOD_RULE_EFFECTIVE_TO_REQUIRED",
                message="effective_to must be a valid ISO date.",
            )
        CalendarPeriodRuleManagementService._validate_date_range(
            proposed_effective_from,
            proposed_effective_to,
        )
        CalendarPeriodRuleManagementService._ensure_no_overlap(
            period_rule.yearly_calendar_id,
            effective_from=proposed_effective_from,
            effective_to=proposed_effective_to,
            exclude_rule_id=period_rule.id,
        )
        changed_fields: list[tuple[str, str, str]] = []
        for field_name, code, message in (
            (
                "monday_max_hours",
                "CALENDAR_PERIOD_RULE_MONDAY_REQUIRED",
                "monday_max_hours is required.",
            ),
            (
                "tuesday_max_hours",
                "CALENDAR_PERIOD_RULE_TUESDAY_REQUIRED",
                "tuesday_max_hours is required.",
            ),
            (
                "wednesday_max_hours",
                "CALENDAR_PERIOD_RULE_WEDNESDAY_REQUIRED",
                "wednesday_max_hours is required.",
            ),
            (
                "thursday_max_hours",
                "CALENDAR_PERIOD_RULE_THURSDAY_REQUIRED",
                "thursday_max_hours is required.",
            ),
            (
                "friday_max_hours",
                "CALENDAR_PERIOD_RULE_FRIDAY_REQUIRED",
                "friday_max_hours is required.",
            ),
        ):
            if field_name in payload:
                new_value = _parse_decimal(payload.get(field_name), code=code, message=message)
                if getattr(period_rule, field_name) != new_value:
                    changed_fields.append(
                        (field_name, str(getattr(period_rule, field_name)), str(new_value))
                    )
                    setattr(period_rule, field_name, new_value)
        if proposed_effective_from != period_rule.effective_from:
            changed_fields.append(
                (
                    "effective_from",
                    period_rule.effective_from.isoformat(),
                    proposed_effective_from.isoformat(),
                )
            )
            period_rule.effective_from = proposed_effective_from
        if proposed_effective_to != period_rule.effective_to:
            changed_fields.append(
                (
                    "effective_to",
                    period_rule.effective_to.isoformat(),
                    proposed_effective_to.isoformat(),
                )
            )
            period_rule.effective_to = proposed_effective_to
        if "status_code" in payload:
            new_status = _ref_value(
                "CALENDAR_PERIOD_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != period_rule.status_id:
                changed_fields.append(
                    ("status", period_rule.status.value_code, new_status.value_code)
                )
                period_rule.status = new_status
        if changed_fields:
            period_rule.updated_by = current_user.email
            period_rule.save()
        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="calendar_period_rule",
                entity_id=period_rule.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=period_rule.yearly_calendar.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Calendar period rule updated by Timesheet Administrator.",
            )
        return _serialize_calendar_period_rule(
            CalendarPeriodRuleManagementService._refresh_period_rule(period_rule.id)
        )

    @staticmethod
    def _validate_date_range(effective_from: date, effective_to: date) -> None:
        if effective_to < effective_from:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_DATE_RANGE_INVALID",
                "effective_to must be on or after effective_from.",
                400,
            )

    @staticmethod
    def _ensure_no_overlap(
        yearly_calendar_id: int,
        *,
        effective_from: date,
        effective_to: date,
        exclude_rule_id: int | None = None,
    ) -> None:
        overlaps = CalendarPeriodRule.objects.filter(
            yearly_calendar_id=yearly_calendar_id,
            effective_from__lte=effective_to,
            effective_to__gte=effective_from,
        )
        if exclude_rule_id is not None:
            overlaps = overlaps.exclude(id=exclude_rule_id)
        if overlaps.exists():
            raise AuthError(
                "CALENDAR_PERIOD_RULE_OVERLAP",
                "Calendar Period Rules cannot overlap within the same yearly calendar.",
                400,
            )

    @staticmethod
    def _get_scoped_yearly_calendar(
        current_user: CurrentUser, yearly_calendar_id: int
    ) -> YearlyCalendar:
        try:
            yearly_calendar = YearlyCalendar.objects.select_related(
                "business_unit",
                "country",
                "country__status",
                "status",
            ).get(id=yearly_calendar_id)
        except YearlyCalendar.DoesNotExist as exc:
            raise AuthError("YEARLY_CALENDAR_NOT_FOUND", "Yearly calendar not found.", 404) from exc
        _ensure_business_units_in_scope(current_user, {yearly_calendar.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            yearly_calendar.country_id,
            message="Yearly calendar is outside your active country.",
        )
        return yearly_calendar

    @staticmethod
    def _get_scoped_period_rule(
        current_user: CurrentUser, period_rule_id: int
    ) -> CalendarPeriodRule:
        try:
            period_rule = CalendarPeriodRule.objects.select_related(
                "country",
                "yearly_calendar",
                "yearly_calendar__country",
                "yearly_calendar__business_unit",
                "yearly_calendar__status",
                "status",
            ).get(id=period_rule_id)
        except CalendarPeriodRule.DoesNotExist as exc:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_NOT_FOUND", "Calendar Period Rule not found.", 404
            ) from exc
        _ensure_business_units_in_scope(
            current_user, {period_rule.yearly_calendar.business_unit_id}
        )
        _ensure_country_in_scope(
            current_user,
            period_rule.country_id,
            message="Calendar Period Rule is outside your active country.",
        )
        return period_rule

    @staticmethod
    def _refresh_period_rule(period_rule_id: int) -> CalendarPeriodRule:
        return CalendarPeriodRule.objects.select_related(
            "country",
            "yearly_calendar",
            "yearly_calendar__country",
            "yearly_calendar__business_unit",
            "yearly_calendar__status",
            "status",
        ).get(id=period_rule_id)


class ProjectManagementService:
    @staticmethod
    def list_projects(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        projects = _apply_status_filter(
            Project.objects.select_related(
                "business_unit",
                "country",
                "project_owner_employee",
                "project_manager_employee",
                "client",
                "internal_category",
                "cost_center",
                "status",
            )
            .filter(
                business_unit_id__in=current_user.scoped_business_unit_ids,
                country_id=current_user.country_id,
            )
            .order_by("business_unit__bu_code", "project_code"),
            _parse_status_filter(status_code, domain_code="PROJECT_STATUS"),
        )
        return [_serialize_project(project) for project in projects]

    @staticmethod
    def get_project(current_user: CurrentUser, project_id: int) -> dict:
        _ensure_ts_admin(current_user)
        project = ProjectManagementService._get_scoped_project(current_user, project_id)
        return _serialize_project(project)

    @staticmethod
    @transaction.atomic
    def create_project(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        business_unit = _get_scoped_business_unit(
            current_user,
            _parse_required_int(
                payload.get("business_unit_id"),
                code="PROJECT_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id is required.",
            ),
        )
        _ensure_scoped_active_country_for_write(
            current_user,
            business_unit.country,
            out_of_scope_message="Project Business Unit is outside your active country.",
        )
        project_code = str(payload.get("project_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not project_code:
            raise AuthError("PROJECT_CODE_REQUIRED", "Project code is required.", 400)
        if not name:
            raise AuthError("PROJECT_NAME_REQUIRED", "Project name is required.", 400)
        project_owner = ProjectManagementService._resolve_project_employee(
            current_user,
            employee_id=payload.get("project_owner_employee_id"),
            business_unit_id=business_unit.id,
            required_role_code="PROJECT_OWNER",
            code_prefix="PROJECT_OWNER",
        )
        project_manager = ProjectManagementService._resolve_project_employee(
            current_user,
            employee_id=payload.get("project_manager_employee_id"),
            business_unit_id=business_unit.id,
            required_role_code="PROJECT_MANAGER",
            code_prefix="PROJECT_MANAGER",
        )
        client = ProjectManagementService._resolve_project_client(
            current_user,
            business_unit_id=business_unit.id,
            client_id=payload.get("client_id"),
        )
        internal_category = ProjectManagementService._resolve_project_internal_category(
            current_user,
            business_unit_id=business_unit.id,
            category_id=payload.get("internal_category_id"),
        )
        cost_center = ProjectManagementService._resolve_project_cost_center(
            current_user,
            business_unit_id=business_unit.id,
            cost_center_id=payload.get("cost_center_id"),
        )
        start_date = _parse_iso_date(
            payload.get("start_date"),
            code="PROJECT_START_DATE_REQUIRED",
            message="start_date must be a valid ISO date.",
        )
        end_date = _parse_optional_iso_date(
            payload.get("end_date"),
            code="PROJECT_END_DATE_INVALID",
            message="end_date must be a valid ISO date.",
        )
        close_date = _parse_optional_iso_date(
            payload.get("close_date"),
            code="PROJECT_CLOSE_DATE_INVALID",
            message="close_date must be a valid ISO date.",
        )
        ProjectManagementService._validate_project_dates(
            start_date=start_date,
            end_date=end_date,
            close_date=close_date,
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="PROJECT",
            expected_country_id=business_unit.country_id,
            mismatch_message="Project country must match the selected Business Unit country.",
        )
        try:
            project = Project.objects.create(
                business_unit=business_unit,
                country=business_unit.country,
                project_code=project_code,
                name=name,
                description=description,
                project_owner_employee=project_owner,
                project_manager_employee=project_manager,
                client=client,
                internal_category=internal_category,
                cost_center=cost_center,
                start_date=start_date,
                end_date=end_date,
                close_date=close_date,
                billable_flag=bool(payload.get("billable_flag", False)),
                status=_ref_value(
                    "PROJECT_STATUS",
                    str(payload.get("status_code", "DRAFT")).strip() or "DRAFT",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "PROJECT_CODE_NOT_UNIQUE",
                "Project code must be unique within the Business Unit.",
                400,
            ) from exc
        write_audit_event(
            action_code="CREATE",
            entity_name="project",
            entity_id=project.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=project.business_unit,
            reason_text="Project created by Timesheet Administrator.",
        )
        return _serialize_project(ProjectManagementService._refresh_project(project.id))

    @staticmethod
    @transaction.atomic
    def update_project(current_user: CurrentUser, project_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        project = ProjectManagementService._get_scoped_project(current_user, project_id)
        _ensure_scoped_active_country_for_write(
            current_user,
            project.country,
            out_of_scope_message="Project is outside your active country.",
        )
        _validate_optional_country_payload(
            payload,
            code_prefix="PROJECT",
            expected_country_id=project.country_id,
            immutable_country_id=project.country_id,
            mismatch_message="Project country must match the project country.",
            immutable_message="Project country cannot be changed.",
        )
        if (
            "business_unit_id" in payload
            and _parse_required_int(
                payload.get("business_unit_id"),
                code="PROJECT_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id must be a valid Business Unit identifier.",
            )
            != project.business_unit_id
        ):
            raise AuthError(
                "PROJECT_BUSINESS_UNIT_IMMUTABLE",
                "Project Business Unit cannot be changed.",
                400,
            )
        changed_fields: list[tuple[str, str, str]] = []
        if "project_code" in payload:
            new_project_code = str(payload.get("project_code", "")).strip()
            if not new_project_code:
                raise AuthError("PROJECT_CODE_REQUIRED", "Project code is required.", 400)
            if new_project_code != project.project_code:
                changed_fields.append(("project_code", project.project_code, new_project_code))
                project.project_code = new_project_code
        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError("PROJECT_NAME_REQUIRED", "Project name is required.", 400)
            if new_name != project.name:
                changed_fields.append(("name", project.name, new_name))
                project.name = new_name
        if "description" in payload:
            new_description = str(payload.get("description", "")).strip()
            if new_description != project.description:
                changed_fields.append(("description", project.description, new_description))
                project.description = new_description
        if "project_owner_employee_id" in payload:
            new_project_owner = ProjectManagementService._resolve_project_employee(
                current_user,
                employee_id=payload.get("project_owner_employee_id"),
                business_unit_id=project.business_unit_id,
                required_role_code="PROJECT_OWNER",
                code_prefix="PROJECT_OWNER",
            )
            if new_project_owner.id != project.project_owner_employee_id:
                changed_fields.append(
                    (
                        "project_owner_employee",
                        project.project_owner_employee.employee_code,
                        new_project_owner.employee_code,
                    )
                )
                project.project_owner_employee = new_project_owner
        if "project_manager_employee_id" in payload:
            new_project_manager = ProjectManagementService._resolve_project_employee(
                current_user,
                employee_id=payload.get("project_manager_employee_id"),
                business_unit_id=project.business_unit_id,
                required_role_code="PROJECT_MANAGER",
                code_prefix="PROJECT_MANAGER",
            )
            if new_project_manager.id != project.project_manager_employee_id:
                changed_fields.append(
                    (
                        "project_manager_employee",
                        project.project_manager_employee.employee_code,
                        new_project_manager.employee_code,
                    )
                )
                project.project_manager_employee = new_project_manager
        if "client_id" in payload:
            new_client = ProjectManagementService._resolve_project_client(
                current_user,
                business_unit_id=project.business_unit_id,
                client_id=payload.get("client_id"),
            )
            if new_client.id != project.client_id:
                changed_fields.append(
                    ("client", project.client.client_code, new_client.client_code)
                )
                project.client = new_client
        if "internal_category_id" in payload:
            new_category = ProjectManagementService._resolve_project_internal_category(
                current_user,
                business_unit_id=project.business_unit_id,
                category_id=payload.get("internal_category_id"),
            )
            if new_category.id != project.internal_category_id:
                changed_fields.append(
                    (
                        "internal_category",
                        project.internal_category.category_code,
                        new_category.category_code,
                    )
                )
                project.internal_category = new_category
        if "cost_center_id" in payload:
            new_cost_center = ProjectManagementService._resolve_project_cost_center(
                current_user,
                business_unit_id=project.business_unit_id,
                cost_center_id=payload.get("cost_center_id"),
            )
            if new_cost_center.id != project.cost_center_id:
                changed_fields.append(
                    (
                        "cost_center",
                        project.cost_center.cost_center_code,
                        new_cost_center.cost_center_code,
                    )
                )
                project.cost_center = new_cost_center
        proposed_start_date = project.start_date
        proposed_end_date = project.end_date
        proposed_close_date = project.close_date
        if "start_date" in payload:
            proposed_start_date = _parse_iso_date(
                payload.get("start_date"),
                code="PROJECT_START_DATE_REQUIRED",
                message="start_date must be a valid ISO date.",
            )
        if "end_date" in payload:
            proposed_end_date = _parse_optional_iso_date(
                payload.get("end_date"),
                code="PROJECT_END_DATE_INVALID",
                message="end_date must be a valid ISO date.",
            )
        if "close_date" in payload:
            proposed_close_date = _parse_optional_iso_date(
                payload.get("close_date"),
                code="PROJECT_CLOSE_DATE_INVALID",
                message="close_date must be a valid ISO date.",
            )
        ProjectManagementService._validate_project_dates(
            start_date=proposed_start_date,
            end_date=proposed_end_date,
            close_date=proposed_close_date,
        )
        if proposed_start_date != project.start_date:
            changed_fields.append(
                ("start_date", project.start_date.isoformat(), proposed_start_date.isoformat())
            )
            project.start_date = proposed_start_date
        if proposed_end_date != project.end_date:
            changed_fields.append(
                (
                    "end_date",
                    project.end_date.isoformat() if project.end_date else "",
                    proposed_end_date.isoformat() if proposed_end_date else "",
                )
            )
            project.end_date = proposed_end_date
        if proposed_close_date != project.close_date:
            changed_fields.append(
                (
                    "close_date",
                    project.close_date.isoformat() if project.close_date else "",
                    proposed_close_date.isoformat() if proposed_close_date else "",
                )
            )
            project.close_date = proposed_close_date
        if "billable_flag" in payload:
            new_billable_flag = bool(payload.get("billable_flag"))
            if new_billable_flag != project.billable_flag:
                changed_fields.append(
                    ("billable_flag", str(project.billable_flag), str(new_billable_flag))
                )
                project.billable_flag = new_billable_flag
        if "status_code" in payload:
            new_status = _ref_value("PROJECT_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != project.status_id:
                changed_fields.append(("status", project.status.value_code, new_status.value_code))
                project.status = new_status
        if changed_fields:
            try:
                project.updated_by = current_user.email
                project.save()
            except IntegrityError as exc:
                raise AuthError(
                    "PROJECT_CODE_NOT_UNIQUE",
                    "Project code must be unique within the Business Unit.",
                    400,
                ) from exc
        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="project",
                entity_id=project.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=project.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Project updated by Timesheet Administrator.",
            )
        return _serialize_project(ProjectManagementService._refresh_project(project.id))

    @staticmethod
    def _validate_project_dates(
        *,
        start_date: date,
        end_date: date | None,
        close_date: date | None,
    ) -> None:
        if end_date is not None and end_date < start_date:
            raise AuthError(
                "PROJECT_DATE_RANGE_INVALID",
                "end_date must be on or after start_date.",
                400,
            )
        if close_date is not None and close_date < start_date:
            raise AuthError(
                "PROJECT_CLOSE_DATE_INVALID",
                "close_date must be on or after start_date.",
                400,
            )

    @staticmethod
    def _resolve_project_employee(
        current_user: CurrentUser,
        *,
        employee_id: object,
        business_unit_id: int,
        required_role_code: str,
        code_prefix: str,
    ) -> Employee:
        resolved_employee_id = _parse_required_int(
            employee_id,
            code=f"{code_prefix}_REQUIRED",
            message=f"{code_prefix.lower()}_employee_id is required.",
        )
        employee = _get_scoped_employee_for_management(current_user, resolved_employee_id)
        if employee.status.value_code != "ACTIVE":
            raise AuthError(
                f"{code_prefix}_INACTIVE",
                f"{required_role_code.replace('_', ' ').title()} must be active.",
                400,
            )
        if not _employee_has_active_business_unit_scope(employee.id, business_unit_id):
            raise AuthError(
                f"{code_prefix}_BU_SCOPE_INVALID",
                (
                    f"{required_role_code.replace('_', ' ').title()} "
                    "must be assigned to the same Business Unit."
                ),
                400,
            )
        if not _employee_has_active_role(
            employee.id,
            role_code=required_role_code,
            business_unit_id=business_unit_id,
        ):
            raise AuthError(
                f"{code_prefix}_ROLE_INVALID",
                f"Selected employee must have the {required_role_code} role.",
                400,
            )
        return employee

    @staticmethod
    def _resolve_project_client(
        current_user: CurrentUser,
        *,
        business_unit_id: int,
        client_id: object,
    ) -> ClientRecord:
        client = ClientManagementService._get_scoped_client(
            current_user,
            _parse_required_int(
                client_id,
                code="PROJECT_CLIENT_REQUIRED",
                message="client_id is required.",
            ),
        )
        if client.business_unit_id != business_unit_id:
            raise AuthError(
                "PROJECT_CLIENT_BU_MISMATCH",
                "Project client must belong to the same Business Unit.",
                400,
            )
        return client

    @staticmethod
    def _resolve_project_internal_category(
        current_user: CurrentUser,
        *,
        business_unit_id: int,
        category_id: object,
    ) -> InternalCategoryRecord:
        category = InternalCategoryManagementService._get_scoped_category(
            current_user,
            _parse_required_int(
                category_id,
                code="PROJECT_INTERNAL_CATEGORY_REQUIRED",
                message="internal_category_id is required.",
            ),
        )
        if category.business_unit_id != business_unit_id:
            raise AuthError(
                "PROJECT_INTERNAL_CATEGORY_BU_MISMATCH",
                "Project internal category must belong to the same Business Unit.",
                400,
            )
        return category

    @staticmethod
    def _resolve_project_cost_center(
        current_user: CurrentUser,
        *,
        business_unit_id: int,
        cost_center_id: object,
    ) -> CostCenterRecord:
        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user,
            _parse_required_int(
                cost_center_id,
                code="PROJECT_COST_CENTER_REQUIRED",
                message="cost_center_id is required.",
            ),
        )
        if cost_center.business_unit_id != business_unit_id:
            raise AuthError(
                "PROJECT_COST_CENTER_BU_MISMATCH",
                "Project cost center must belong to the same Business Unit.",
                400,
            )
        return cost_center

    @staticmethod
    def _get_scoped_project(current_user: CurrentUser, project_id: int) -> Project:
        try:
            project = Project.objects.select_related(
                "business_unit",
                "country",
                "project_owner_employee",
                "project_manager_employee",
                "client",
                "internal_category",
                "cost_center",
                "status",
            ).get(id=project_id)
        except Project.DoesNotExist as exc:
            raise AuthError("PROJECT_NOT_FOUND", "Project not found.", 404) from exc
        _ensure_business_units_in_scope(current_user, {project.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            project.country_id,
            message="Project is outside your active country.",
        )
        return project

    @staticmethod
    def _refresh_project(project_id: int) -> Project:
        return Project.objects.select_related(
            "business_unit",
            "country",
            "project_owner_employee",
            "project_manager_employee",
            "client",
            "internal_category",
            "cost_center",
            "status",
        ).get(id=project_id)


class ProjectAssignmentManagementService:
    @staticmethod
    def list_assignments(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        assignments = _apply_status_filter(
            ProjectAssignment.objects.select_related(
                "project",
                "project__country",
                "project__business_unit",
                "employee",
                "employee__primary_business_unit",
                "status",
            )
            .filter(
                project__business_unit_id__in=current_user.scoped_business_unit_ids,
                project__country_id=current_user.country_id,
            )
            .order_by(
                "project__business_unit__bu_code",
                "project__project_code",
                "employee__employee_code",
                "assignment_start_date",
            ),
            _parse_status_filter(status_code, domain_code="PROJECT_ASSIGNMENT_STATUS"),
        )
        return [_serialize_project_assignment(assignment) for assignment in assignments]

    @staticmethod
    def get_assignment(current_user: CurrentUser, assignment_id: int) -> dict:
        _ensure_ts_admin(current_user)
        assignment = ProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        return _serialize_project_assignment(assignment)

    @staticmethod
    @transaction.atomic
    def create_assignment(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        project = ProjectManagementService._get_scoped_project(
            current_user,
            _parse_required_int(
                payload.get("project_id"),
                code="PROJECT_ASSIGNMENT_PROJECT_REQUIRED",
                message="project_id is required.",
            ),
        )
        if project.status.value_code == "CLOSED":
            raise AuthError(
                "PROJECT_ASSIGNMENT_PROJECT_CLOSED",
                "Closed projects cannot receive new assignments.",
                400,
            )
        employee = _get_employee_for_project_assignment(
            _parse_required_int(
                payload.get("employee_id"),
                code="PROJECT_ASSIGNMENT_EMPLOYEE_REQUIRED",
                message="employee_id is required.",
            ),
        )
        if employee.status.value_code != "ACTIVE":
            raise AuthError(
                "PROJECT_ASSIGNMENT_EMPLOYEE_INACTIVE",
                "Project assignment employee must be active.",
                400,
            )
        assignment_start_date = _parse_iso_date(
            payload.get("assignment_start_date"),
            code="PROJECT_ASSIGNMENT_START_REQUIRED",
            message="assignment_start_date must be a valid ISO date.",
        )
        assignment_end_date = _parse_optional_iso_date(
            payload.get("assignment_end_date"),
            code="PROJECT_ASSIGNMENT_END_INVALID",
            message="assignment_end_date must be a valid ISO date.",
        )
        ProjectAssignmentManagementService._validate_assignment_dates(
            project=project,
            assignment_start_date=assignment_start_date,
            assignment_end_date=assignment_end_date,
        )
        try:
            assignment = ProjectAssignment.objects.create(
                project=project,
                employee=employee,
                assignment_start_date=assignment_start_date,
                assignment_end_date=assignment_end_date,
                status=_ref_value(
                    "PROJECT_ASSIGNMENT_STATUS",
                    str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "PROJECT_ASSIGNMENT_NOT_UNIQUE",
                "Project assignment start date must be unique for the employee within the project.",
                400,
            ) from exc
        write_audit_event(
            action_code="CREATE",
            entity_name="project_assignment",
            entity_id=assignment.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=project.business_unit,
            reason_text="Project assignment created by Timesheet Administrator.",
        )
        return _serialize_project_assignment(
            ProjectAssignmentManagementService._refresh_assignment(assignment.id)
        )

    @staticmethod
    @transaction.atomic
    def update_assignment(current_user: CurrentUser, assignment_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_country_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        assignment = ProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        _ensure_scoped_active_country_for_write(
            current_user,
            assignment.project.country,
            out_of_scope_message="Project assignment is outside your active country.",
        )
        if (
            "project_id" in payload
            and _parse_required_int(
                payload.get("project_id"),
                code="PROJECT_ASSIGNMENT_PROJECT_REQUIRED",
                message="project_id must be a valid project identifier.",
            )
            != assignment.project_id
        ):
            raise AuthError(
                "PROJECT_ASSIGNMENT_PROJECT_IMMUTABLE",
                "Project Assignment project cannot be changed.",
                400,
            )
        if (
            "employee_id" in payload
            and _parse_required_int(
                payload.get("employee_id"),
                code="PROJECT_ASSIGNMENT_EMPLOYEE_REQUIRED",
                message="employee_id must be a valid employee identifier.",
            )
            != assignment.employee_id
        ):
            raise AuthError(
                "PROJECT_ASSIGNMENT_EMPLOYEE_IMMUTABLE",
                "Project Assignment employee cannot be changed.",
                400,
            )
        proposed_start_date = assignment.assignment_start_date
        proposed_end_date = assignment.assignment_end_date
        if "assignment_start_date" in payload:
            proposed_start_date = _parse_iso_date(
                payload.get("assignment_start_date"),
                code="PROJECT_ASSIGNMENT_START_REQUIRED",
                message="assignment_start_date must be a valid ISO date.",
            )
        if "assignment_end_date" in payload:
            proposed_end_date = _parse_optional_iso_date(
                payload.get("assignment_end_date"),
                code="PROJECT_ASSIGNMENT_END_INVALID",
                message="assignment_end_date must be a valid ISO date.",
            )
        ProjectAssignmentManagementService._validate_assignment_dates(
            project=assignment.project,
            assignment_start_date=proposed_start_date,
            assignment_end_date=proposed_end_date,
        )
        changed_fields: list[tuple[str, str, str]] = []
        if proposed_start_date != assignment.assignment_start_date:
            changed_fields.append(
                (
                    "assignment_start_date",
                    assignment.assignment_start_date.isoformat(),
                    proposed_start_date.isoformat(),
                )
            )
            assignment.assignment_start_date = proposed_start_date
        if proposed_end_date != assignment.assignment_end_date:
            changed_fields.append(
                (
                    "assignment_end_date",
                    assignment.assignment_end_date.isoformat()
                    if assignment.assignment_end_date
                    else "",
                    proposed_end_date.isoformat() if proposed_end_date else "",
                )
            )
            assignment.assignment_end_date = proposed_end_date
        if "status_code" in payload:
            new_status = _ref_value(
                "PROJECT_ASSIGNMENT_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != assignment.status_id:
                changed_fields.append(
                    ("status", assignment.status.value_code, new_status.value_code)
                )
                assignment.status = new_status
        if changed_fields:
            try:
                assignment.updated_by = current_user.email
                assignment.save()
            except IntegrityError as exc:
                raise AuthError(
                    "PROJECT_ASSIGNMENT_NOT_UNIQUE",
                    (
                        "Project assignment start date must be unique for the "
                        "employee within the project."
                    ),
                    400,
                ) from exc
        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="project_assignment",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=assignment.project.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Project assignment updated by Timesheet Administrator.",
            )
        return _serialize_project_assignment(
            ProjectAssignmentManagementService._refresh_assignment(assignment.id)
        )

    @staticmethod
    def _validate_assignment_dates(
        *,
        project: Project,
        assignment_start_date: date,
        assignment_end_date: date | None,
    ) -> None:
        if assignment_end_date is not None and assignment_end_date < assignment_start_date:
            raise AuthError(
                "PROJECT_ASSIGNMENT_DATE_RANGE_INVALID",
                "assignment_end_date must be on or after assignment_start_date.",
                400,
            )
        if assignment_start_date < project.start_date:
            raise AuthError(
                "PROJECT_ASSIGNMENT_BEFORE_PROJECT_START",
                "assignment_start_date cannot be before the project start_date.",
                400,
            )
        if (
            project.end_date is not None
            and assignment_end_date is not None
            and assignment_end_date > project.end_date
        ):
            raise AuthError(
                "PROJECT_ASSIGNMENT_AFTER_PROJECT_END",
                "assignment_end_date cannot be after the project end_date.",
                400,
            )
        if project.close_date is not None and assignment_start_date > project.close_date:
            raise AuthError(
                "PROJECT_ASSIGNMENT_AFTER_PROJECT_CLOSE",
                "assignment_start_date cannot be after the project close_date.",
                400,
            )

    @staticmethod
    def _get_scoped_assignment(current_user: CurrentUser, assignment_id: int) -> ProjectAssignment:
        try:
            assignment = ProjectAssignment.objects.select_related(
                "project",
                "project__country",
                "project__business_unit",
                "employee",
                "employee__primary_business_unit",
                "status",
            ).get(id=assignment_id)
        except ProjectAssignment.DoesNotExist as exc:
            raise AuthError(
                "PROJECT_ASSIGNMENT_NOT_FOUND", "Project Assignment not found.", 404
            ) from exc
        _ensure_business_units_in_scope(current_user, {assignment.project.business_unit_id})
        _ensure_country_in_scope(
            current_user,
            assignment.project.country_id,
            message="Project assignment is outside your active country.",
        )
        return assignment

    @staticmethod
    def _refresh_assignment(assignment_id: int) -> ProjectAssignment:
        return ProjectAssignment.objects.select_related(
            "project",
            "project__country",
            "project__business_unit",
            "employee",
            "employee__primary_business_unit",
            "status",
        ).get(id=assignment_id)
