from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError

from apps.audit.models import AuditLog
from apps.audit.services import write_audit_event
from apps.auth.constants import ACTIVE_COUNTRY_STATUS
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import canonicalize_email
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    CalendarSpecialDay,
    Country,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    GeneralChargeCodeApprovalRole,
    GeneralChargeCodeApprovalRoleAssignment,
    GeneralChargeCodeApproverRole,
    Office,
    OfficeConfiguration,
    Project,
    ProjectAssignment,
    YearlyCalendar,
)
from apps.master_data.models import (
    CalendarSpecialDay as CalendarSpecialDayRecord,
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
from apps.master_data.models import (
    PricingModel as PricingModelRecord,
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


def _ensure_ts_admin_or_project_owner(current_user: CurrentUser) -> None:
    if not (current_user.is_ts_admin or current_user.has_role("PROJECT_OWNER")):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to perform this project administrative action.",
            403,
        )


def _ensure_ts_admin_or_project_assignment_manager(current_user: CurrentUser) -> None:
    if not (
        current_user.is_ts_admin
        or current_user.has_role("PROJECT_OWNER")
        or current_user.has_role("PROJECT_MANAGER")
    ):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to perform this project assignment administrative action.",
            403,
        )


def _ensure_ts_admin_master(current_user: CurrentUser) -> None:
    if not current_user.is_ts_admin_master:
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to perform this master administrative action.",
            403,
        )


def _get_current_office(current_user: CurrentUser) -> Office:
    try:
        return Office.objects.select_related("status").get(id=current_user.office_id)
    except Office.DoesNotExist as exc:
        raise AuthError("COUNTRY_NOT_FOUND", "Office not found.", 404) from exc


def _ensure_office_in_scope(
    current_user: CurrentUser,
    office_id: int,
    *,
    message: str,
) -> None:
    if office_id != current_user.office_id:
        raise AuthError("COUNTRY_OUT_OF_SCOPE", message, 403)


def _ensure_office_active_for_write(office: Office, *, message: str) -> None:
    if office.status.value_code != ACTIVE_COUNTRY_STATUS:
        raise AuthError("COUNTRY_INACTIVE_FOR_WRITE", message, 403)


def _ensure_current_office_active_for_write(current_user: CurrentUser) -> Office:
    current_office = _get_current_office(current_user)
    _ensure_office_active_for_write(
        current_office,
        message="Your active office is inactive. New records and edits are blocked.",
    )
    return current_office


def _ensure_scoped_active_office_for_write(
    current_user: CurrentUser,
    office: Office,
    *,
    out_of_scope_message: str,
) -> None:
    _ensure_office_in_scope(
        current_user,
        office.id,
        message=out_of_scope_message,
    )
    _ensure_office_active_for_write(
        office,
        message="Records in inactive offices cannot be created or edited.",
    )


def _validate_optional_office_payload(
    payload: dict,
    *,
    code_prefix: str,
    expected_office_id: int,
    mismatch_message: str,
    immutable_office_id: int | None = None,
    immutable_message: str | None = None,
) -> None:
    if "office_id" not in payload:
        return

    payload_office_id = _parse_required_int(
        payload.get("office_id"),
        code=f"{code_prefix}_COUNTRY_REQUIRED",
        message="office_id must be a valid office identifier.",
    )
    if immutable_office_id is not None and payload_office_id != immutable_office_id:
        raise AuthError(
            f"{code_prefix}_COUNTRY_IMMUTABLE",
            immutable_message or "Office cannot be changed.",
            400,
        )
    if payload_office_id != expected_office_id:
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


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return bool(value)


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


def _parse_general_charge_code_approver_keys(payload: dict) -> list[str]:
    values = payload.get("approver_keys", [])
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        raise AuthError(
            "GENERAL_CHARGE_CODE_APPROVER_ROLE_INVALID",
            "approver_keys must be a list of approver role identifiers.",
            400,
        )
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _decode_general_charge_code_approver_key(value: str) -> tuple[str, str]:
    normalized = value.strip()
    if ":" not in normalized:
        raise AuthError(
            "GENERAL_CHARGE_CODE_APPROVER_ROLE_INVALID",
            f"Unknown approver role identifier: {value}.",
            400,
        )
    prefix, raw_identifier = normalized.split(":", 1)
    prefix = prefix.strip().upper()
    identifier = raw_identifier.strip()
    if prefix not in {"ROLE", "ADHOC"} or not identifier:
        raise AuthError(
            "GENERAL_CHARGE_CODE_APPROVER_ROLE_INVALID",
            f"Unknown approver role identifier: {value}.",
            400,
        )
    return prefix, identifier


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
        business_unit = BusinessUnit.objects.select_related("office", "office__status").get(
            id=business_unit_id
        )
    except BusinessUnit.DoesNotExist as exc:
        raise AuthError("BUSINESS_UNIT_NOT_FOUND", "Business Unit not found.", 404) from exc
    _ensure_office_in_scope(
        current_user,
        business_unit.office_id,
        message="Business Unit is outside your active office.",
    )
    return business_unit


def _get_scoped_employee_for_management(current_user: CurrentUser, employee_id: int) -> Employee:
    try:
        employee = (
            Employee.objects.select_related("primary_business_unit", "office", "status")
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
    _ensure_office_in_scope(
        current_user,
        employee.office_id,
        message="Employee is outside your active office.",
    )
    return employee


def _refresh_employee(employee_id: int) -> Employee:
    return (
        Employee.objects.select_related("primary_business_unit", "office", "status")
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
            "office",
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


def _office_business_units(office_id: int) -> dict[int, BusinessUnit]:
    return {
        business_unit.id: business_unit
        for business_unit in BusinessUnit.objects.select_related("office", "office__status")
        .filter(office_id=office_id)
        .order_by("bu_code")
    }


def _ensure_business_unit_code_available(
    *,
    office_id: int,
    bu_code: str,
    exclude_business_unit_id: int | None = None,
    message: str,
) -> None:
    duplicates = BusinessUnit.objects.filter(office_id=office_id, bu_code=bu_code)
    if exclude_business_unit_id is not None:
        duplicates = duplicates.exclude(id=exclude_business_unit_id)
    if duplicates.exists():
        raise AuthError(
            "BUSINESS_UNIT_CODE_NOT_UNIQUE",
            message,
            400,
        )


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
        "office": {
            "id": employee.office_id,
            "office_name": employee.office.office_name,
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
        "office": {
            "id": client.office_id,
            "office_name": client.office.office_name,
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
        "office": {
            "id": category.office_id,
            "office_name": category.office.office_name,
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
        "office": {
            "id": cost_center.office_id,
            "office_name": cost_center.office.office_name,
        },
    }


def _serialize_pricing_model(pricing_model: PricingModelRecord) -> dict:
    return {
        "id": pricing_model.id,
        "name": pricing_model.name,
        "description": pricing_model.description,
        "office": {
            "id": pricing_model.office_id,
            "office_name": pricing_model.office.office_name,
        },
    }


def _active_general_charge_code_role_assignments(
    approval_role: GeneralChargeCodeApprovalRole,
) -> list[GeneralChargeCodeApprovalRoleAssignment]:
    assignments = [
        assignment
        for assignment in approval_role.member_assignments.all()
        if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
        and assignment.status.value_code == "ACTIVE"
        and assignment.valid_to is None
        and assignment.employee.status.value_code == "ACTIVE"
    ]
    assignments.sort(key=lambda assignment: assignment.employee.employee_code)
    return assignments


def _dependent_general_charge_codes_for_approval_role(
    approval_role: GeneralChargeCodeApprovalRole,
) -> list[GeneralChargeCodeRecord]:
    general_charge_codes = [
        mapping.general_charge_code
        for mapping in approval_role.general_charge_code_assignments.all()
    ]
    general_charge_codes.sort(
        key=lambda general_charge_code: (
            general_charge_code.business_unit.bu_code,
            general_charge_code.code,
        )
    )
    return general_charge_codes


def _serialize_general_charge_code_routing_health(
    general_charge_code: GeneralChargeCodeRecord,
) -> dict:
    if not general_charge_code.requires_approval_flag:
        return {
            "status": "NOT_REQUIRED",
            "warning": None,
            "ad_hoc_roles_without_active_members": [],
            "inactive_ad_hoc_roles": [],
        }

    ad_hoc_roles_without_active_members: list[str] = []
    inactive_ad_hoc_roles: list[str] = []
    for approver_role in general_charge_code.approver_roles.all():
        if approver_role.approval_role_id is None:
            continue
        if approver_role.approval_role.status.value_code != "ACTIVE":
            inactive_ad_hoc_roles.append(approver_role.approval_role.role_code)
            continue
        if not _active_general_charge_code_role_assignments(approver_role.approval_role):
            ad_hoc_roles_without_active_members.append(approver_role.approval_role.role_code)

    if not general_charge_code.approver_roles.exists():
        return {
            "status": "ATTENTION",
            "warning": "Requires approval but no approver roles are configured.",
            "ad_hoc_roles_without_active_members": [],
            "inactive_ad_hoc_roles": [],
        }

    if inactive_ad_hoc_roles:
        role_list = ", ".join(sorted(inactive_ad_hoc_roles))
        return {
            "status": "ATTENTION",
            "warning": f"Inactive ad-hoc approver roles are still assigned: {role_list}.",
            "ad_hoc_roles_without_active_members": [],
            "inactive_ad_hoc_roles": sorted(inactive_ad_hoc_roles),
        }

    if ad_hoc_roles_without_active_members:
        role_list = ", ".join(sorted(ad_hoc_roles_without_active_members))
        return {
            "status": "ATTENTION",
            "warning": f"Ad-hoc approver roles without active members: {role_list}.",
            "ad_hoc_roles_without_active_members": sorted(
                ad_hoc_roles_without_active_members
            ),
            "inactive_ad_hoc_roles": [],
        }

    return {
        "status": "READY",
        "warning": None,
        "ad_hoc_roles_without_active_members": [],
        "inactive_ad_hoc_roles": [],
    }


def _serialize_general_charge_code(general_charge_code: GeneralChargeCodeRecord) -> dict:
    routing_health = _serialize_general_charge_code_routing_health(general_charge_code)
    return {
        "id": general_charge_code.id,
        "code": general_charge_code.code,
        "name": general_charge_code.name,
        "charge_type": general_charge_code.charge_type.value_code,
        "cost_center": {
            "id": general_charge_code.cost_center_id,
            "cost_center_code": general_charge_code.cost_center.cost_center_code,
            "name": general_charge_code.cost_center.name,
        },
        "billable_flag": general_charge_code.billable_flag,
        "requires_approval_flag": general_charge_code.requires_approval_flag,
        "description_required_flag": general_charge_code.description_required_flag,
        "valid_from": general_charge_code.valid_from.isoformat(),
        "valid_to": general_charge_code.valid_to.isoformat()
        if general_charge_code.valid_to
        else None,
        "status": general_charge_code.status.value_code,
        "office": {
            "id": general_charge_code.office_id,
            "office_name": general_charge_code.office.office_name,
        },
        "business_unit": {
            "id": general_charge_code.business_unit_id,
            "bu_code": general_charge_code.business_unit.bu_code,
            "name": general_charge_code.business_unit.name,
        },
        "approver_roles": [
            _serialize_general_charge_code_approver_role(approver_role)
            for approver_role in sorted(
                general_charge_code.approver_roles.all(),
                key=lambda approver_role: (
                    approver_role.existing_role.value_code
                    if approver_role.existing_role_id is not None
                    else f"ZZZ-{approver_role.approval_role.role_code}"
                ),
            )
        ],
        "routing_health": routing_health,
    }


def _serialize_yearly_calendar(yearly_calendar: YearlyCalendar) -> dict:
    return {
        "id": yearly_calendar.id,
        "calendar_year": yearly_calendar.calendar_year,
        "calendar_name": yearly_calendar.calendar_name,
        "status": yearly_calendar.status.value_code,
        "name": f"{yearly_calendar.calendar_year} - {yearly_calendar.calendar_name}",
        "office": {
            "id": yearly_calendar.office_id,
            "office_name": yearly_calendar.office.office_name,
        },
    }


def _serialize_general_charge_code_approval_role(
    approval_role: GeneralChargeCodeApprovalRole,
) -> dict:
    active_members = _active_general_charge_code_role_assignments(approval_role)
    dependent_general_charge_codes = _dependent_general_charge_codes_for_approval_role(
        approval_role
    )
    has_active_members = bool(active_members)
    is_referenced = bool(dependent_general_charge_codes)
    coverage_status = "READY"
    coverage_warning = None
    if approval_role.status.value_code != "ACTIVE":
        coverage_status = "ATTENTION" if is_referenced else "INACTIVE"
        coverage_warning = (
            "This ad-hoc approval role is inactive and should not be used for new routing."
            if not is_referenced
            else (
                "This ad-hoc approval role is inactive but still referenced by "
                "General Charge Codes."
            )
        )
    elif is_referenced and not has_active_members:
        coverage_status = "ATTENTION"
        coverage_warning = (
            "This ad-hoc approval role is referenced by General Charge Codes but "
            "has no active members."
        )
    elif not has_active_members:
        coverage_status = "UNMANNED"
        coverage_warning = (
            "This ad-hoc approval role has no active members and is not ready for new routing."
        )
    return {
        "id": approval_role.id,
        "role_code": approval_role.role_code,
        "name": approval_role.name,
        "description": approval_role.description,
        "status": approval_role.status.value_code,
        "office": {
            "id": approval_role.office_id,
            "office_name": approval_role.office.office_name,
        },
        "member_employees": [
            {
                "id": assignment.employee_id,
                "employee_code": assignment.employee.employee_code,
                "full_name": assignment.employee.full_name,
            }
            for assignment in active_members
        ],
        "active_member_count": len(active_members),
        "has_active_members": has_active_members,
        "dependent_general_charge_code_count": len(dependent_general_charge_codes),
        "dependent_general_charge_codes": [
            {
                "id": general_charge_code.id,
                "code": general_charge_code.code,
                "name": general_charge_code.name,
                "business_unit": {
                    "id": general_charge_code.business_unit_id,
                    "bu_code": general_charge_code.business_unit.bu_code,
                    "name": general_charge_code.business_unit.name,
                },
                "status": general_charge_code.status.value_code,
            }
            for general_charge_code in dependent_general_charge_codes
        ],
        "routing_health": {
            "status": coverage_status,
            "warning": coverage_warning,
        },
    }


def _serialize_general_charge_code_approver_role(
    approver_role: GeneralChargeCodeApproverRole,
) -> dict:
    if approver_role.existing_role_id is not None:
        return {
            "key": f"ROLE:{approver_role.existing_role.value_code}",
            "kind": "EXISTING_ROLE",
            "code": approver_role.existing_role.value_code,
            "name": approver_role.existing_role.value_label,
        }
    active_member_assignments = _active_general_charge_code_role_assignments(
        approver_role.approval_role
    )
    return {
        "key": f"ADHOC:{approver_role.approval_role_id}",
        "kind": "AD_HOC_ROLE",
        "code": approver_role.approval_role.role_code,
        "name": approver_role.approval_role.name,
        "id": approver_role.approval_role_id,
        "status": approver_role.approval_role.status.value_code,
        "active_member_count": len(active_member_assignments),
        "has_active_members": bool(active_member_assignments),
    }


def _serialize_calendar_special_day(special_day: CalendarSpecialDayRecord) -> dict:
    return {
        "id": special_day.id,
        "special_date": special_day.special_date.isoformat(),
        "name": special_day.name,
        "status": special_day.status.value_code,
        "day_type": {
            "id": special_day.day_type_id,
            "value_code": special_day.day_type.value_code,
            "value_label": special_day.day_type.value_label,
        },
        "yearly_calendar": _serialize_yearly_calendar(special_day.yearly_calendar),
        "default_general_charge_code": (
            {
                "id": special_day.default_general_charge_code_id,
                "code": special_day.default_general_charge_code.code,
                "name": special_day.default_general_charge_code.name,
            }
            if special_day.default_general_charge_code_id is not None
            else None
        ),
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
        "working_on_saturdays_flag": rule.working_on_saturdays_flag,
        "working_on_sundays_flag": rule.working_on_sundays_flag,
        "saturday_max_hours": str(rule.saturday_max_hours),
        "sunday_max_hours": str(rule.sunday_max_hours),
        "status": rule.status.value_code,
        "office": {
            "id": rule.office_id,
            "office_name": rule.office.office_name,
        },
        "business_unit": (
            {
                "id": rule.business_unit_id,
                "bu_code": rule.business_unit.bu_code,
                "name": rule.business_unit.name,
            }
            if rule.business_unit_id is not None
            else None
        ),
        "yearly_calendar": _serialize_yearly_calendar(rule.yearly_calendar),
    }


def _build_special_day_name(day_type: RefValue, special_date: date) -> str:
    return f"{day_type.value_label} {special_date.isoformat()}"


def _validate_weekend_hours(
    period_rule: CalendarPeriodRule | None,
    payload: dict,
) -> tuple[Decimal, Decimal]:
    saturday_max_hours = (
        _parse_decimal(
            payload.get("saturday_max_hours"),
            code="CALENDAR_PERIOD_RULE_SATURDAY_REQUIRED",
            message="saturday_max_hours must be a valid decimal value.",
        )
        if payload.get("saturday_max_hours") not in (None, "")
        else (
            period_rule.saturday_max_hours if period_rule is not None else Decimal("0")
        )
    )
    sunday_max_hours = (
        _parse_decimal(
            payload.get("sunday_max_hours"),
            code="CALENDAR_PERIOD_RULE_SUNDAY_REQUIRED",
            message="sunday_max_hours must be a valid decimal value.",
        )
        if payload.get("sunday_max_hours") not in (None, "")
        else (
            period_rule.sunday_max_hours if period_rule is not None else Decimal("0")
        )
    )
    working_on_saturdays_flag = (
        _parse_bool(payload.get("working_on_saturdays_flag"))
        if "working_on_saturdays_flag" in payload or period_rule is None
        else period_rule.working_on_saturdays_flag
    )
    working_on_sundays_flag = (
        _parse_bool(payload.get("working_on_sundays_flag"))
        if "working_on_sundays_flag" in payload or period_rule is None
        else period_rule.working_on_sundays_flag
    )
    if working_on_saturdays_flag and saturday_max_hours <= 0:
        raise AuthError(
            "CALENDAR_PERIOD_RULE_SATURDAY_HOURS_INVALID",
            "saturday_max_hours must be greater than zero when Saturdays are working days.",
            400,
        )
    if working_on_sundays_flag and sunday_max_hours <= 0:
        raise AuthError(
            "CALENDAR_PERIOD_RULE_SUNDAY_HOURS_INVALID",
            "sunday_max_hours must be greater than zero when Sundays are working days.",
            400,
        )
    return saturday_max_hours, sunday_max_hours


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
        "office": {
            "id": project.office_id,
            "office_name": project.office.office_name,
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
        "pricing_model": {
            "id": project.pricing_model_id,
            "name": project.pricing_model.name,
            "description": project.pricing_model.description,
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


def _serialize_office(office: Office) -> dict:
    payload = {
        "id": office.id,
        "name": office.office_name,
        "office_name": office.office_name,
        "status": office.status.value_code,
        "active_employee_count": getattr(office, "active_employee_count", 0),
        "country": {
            "id": office.country_id,
            "country_code": office.country.country_code,
            "country_name": office.country.country_name,
            "status": office.country.status.value_code,
        },
    }
    configuration = getattr(office, "_configuration_cache", None)
    if configuration is None:
        configuration = getattr(office, "configuration", None)
    payload["configuration"] = _serialize_office_configuration(configuration)
    payload["administrators"] = [
        {
            "id": employee.id,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "email": employee.email,
            "status": employee.status.value_code,
            "primary_business_unit": {
                "id": employee.primary_business_unit_id,
                "bu_code": employee.primary_business_unit.bu_code,
                "name": employee.primary_business_unit.name,
            },
        }
        for employee in getattr(office, "_administrators_cache", [])
    ]
    return payload


def _serialize_country(country: Country) -> dict:
    return {
        "id": country.id,
        "country_code": country.country_code,
        "country_name": country.country_name,
        "name": country.country_name,
        "status": country.status.value_code,
        "office_count": getattr(country, "office_count", None)
        if hasattr(country, "office_count")
        else country.offices.count(),
    }


def _default_office_configuration_data() -> dict:
    return {
        "approval_mode": "PROJECT",
        "allow_employee_withdraw_flag": False,
        "timesheet_cutoff_date": None,
        "count_non_billable_in_daily_limit_flag": False,
        "archive_after_years": 5,
        "enable_timer_flag": False,
        "enable_leave_integration_flag": False,
        "enable_copy_previous_week_flag": False,
    }


def _serialize_office_configuration(
    configuration: OfficeConfiguration | None,
) -> dict:
    if configuration is None:
        return _default_office_configuration_data()
    return {
        "approval_mode": configuration.approval_mode.value_code,
        "allow_employee_withdraw_flag": configuration.allow_employee_withdraw_flag,
        "timesheet_cutoff_date": configuration.timesheet_cutoff_date.isoformat()
        if configuration.timesheet_cutoff_date
        else None,
        "count_non_billable_in_daily_limit_flag": (
            configuration.count_non_billable_in_daily_limit_flag
        ),
        "archive_after_years": configuration.archive_after_years,
        "enable_timer_flag": configuration.enable_timer_flag,
        "enable_leave_integration_flag": configuration.enable_leave_integration_flag,
        "enable_copy_previous_week_flag": configuration.enable_copy_previous_week_flag,
    }


def _serialize_business_unit(
    business_unit: BusinessUnit,
    *,
    include_configuration: bool = False,
) -> dict:
    payload = {
        "id": business_unit.id,
        "name": business_unit.name,
        "bu_code": business_unit.bu_code,
        "description": business_unit.description,
        "status": business_unit.status.value_code,
        "office": {
            "id": business_unit.office_id,
            "office_name": business_unit.office.office_name,
        },
        "employee_count": getattr(business_unit, "employee_count", 0),
        "project_count": getattr(business_unit, "project_count", 0),
    }
    if include_configuration:
        office = business_unit.office
        payload["configuration"] = _serialize_office_configuration(
            getattr(office, "_configuration_cache", getattr(office, "configuration", None))
        )
    return payload


class BusinessUnitManagementService:
    CONFIG_FIELD_NAMES = {
        "approval_mode_code",
        "allow_employee_withdraw_flag",
        "timesheet_cutoff_date",
        "count_non_billable_in_daily_limit_flag",
        "archive_after_years",
        "enable_timer_flag",
        "enable_leave_integration_flag",
        "enable_copy_previous_week_flag",
    }

    @staticmethod
    def list_business_units(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        business_units = _apply_status_filter(
            BusinessUnit.objects.select_related("office", "status")
            .filter(
                id__in=current_user.scoped_business_unit_ids,
                office_id=current_user.office_id,
            )
            .annotate(
                employee_count=Count("primary_employees", distinct=True),
                project_count=Count("projects", distinct=True),
            )
            .order_by("bu_code"),
            _parse_status_filter(status_code, domain_code="BUSINESS_UNIT_STATUS"),
        )
        return [_serialize_business_unit(business_unit) for business_unit in business_units]

    @staticmethod
    @transaction.atomic
    def create_business_unit(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        current_office = _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        if BusinessUnitManagementService.CONFIG_FIELD_NAMES.intersection(payload):
            raise AuthError(
                "BUSINESS_UNIT_CONFIGURATION_INHERITED",
                "Business Unit configuration is inherited from the parent "
                "Office and cannot be set here.",
                400,
            )

        bu_code = str(payload.get("bu_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not bu_code:
            raise AuthError(
                "BUSINESS_UNIT_CODE_REQUIRED",
                "Business Unit code is required.",
                400,
            )
        if not name:
            raise AuthError(
                "BUSINESS_UNIT_NAME_REQUIRED",
                "Business Unit name is required.",
                400,
            )

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _ensure_business_unit_code_available(
            office_id=current_office.id,
            bu_code=bu_code,
            message="Business Unit code must be unique within the active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="BUSINESS_UNIT",
            expected_office_id=current_office.id,
            mismatch_message="Business Unit office must match your active office.",
        )

        try:
            business_unit = BusinessUnit.objects.create(
                bu_code=bu_code,
                name=name,
                description=description,
                office=current_office,
                status=_ref_value("BUSINESS_UNIT_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "BUSINESS_UNIT_CODE_NOT_UNIQUE",
                "Business Unit code must be unique within the active office.",
                400,
            ) from exc

        BusinessUnitManagementService._sync_office_ts_admin_scope_assignments(
            current_user,
            business_unit,
            actor_employee=actor_employee,
        )

        write_audit_event(
            action_code="CREATE",
            entity_name="business_unit",
            entity_id=business_unit.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            reason_text="Business Unit created by Timesheet Administrator.",
        )
        created_business_unit = (
            BusinessUnit.objects.select_related(
                "office",
                "office__configuration__approval_mode",
                "status",
            )
            .annotate(
                employee_count=Count("primary_employees", distinct=True),
                project_count=Count("projects", distinct=True),
            )
            .get(id=business_unit.id)
        )
        return _serialize_business_unit(created_business_unit, include_configuration=True)

    @staticmethod
    def get_business_unit(current_user: CurrentUser, business_unit_id: int) -> dict:
        _ensure_ts_admin(current_user)
        business_unit = BusinessUnitManagementService._get_scoped_business_unit_with_counts(
            current_user,
            business_unit_id,
        )
        return _serialize_business_unit(business_unit, include_configuration=True)

    @staticmethod
    @transaction.atomic
    def update_business_unit(
        current_user: CurrentUser,
        business_unit_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            business_unit.office,
            out_of_scope_message="Business Unit is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="BUSINESS_UNIT",
            expected_office_id=business_unit.office_id,
            immutable_office_id=business_unit.office_id,
            mismatch_message="Business Unit office must match the Business Unit office.",
            immutable_message="Business Unit office cannot be changed.",
        )

        changed_fields: list[tuple[str, str, str]] = []

        if "bu_code" in payload:
            new_bu_code = str(payload.get("bu_code", "")).strip()
            if not new_bu_code:
                raise AuthError(
                    "BUSINESS_UNIT_CODE_REQUIRED",
                    "Business Unit code is required.",
                    400,
                )
            if new_bu_code != business_unit.bu_code:
                _ensure_business_unit_code_available(
                    office_id=business_unit.office_id,
                    bu_code=new_bu_code,
                    exclude_business_unit_id=business_unit.id,
                    message="Business Unit code must be unique within the Business Unit office.",
                )
                changed_fields.append(("bu_code", business_unit.bu_code, new_bu_code))
                business_unit.bu_code = new_bu_code

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError(
                    "BUSINESS_UNIT_NAME_REQUIRED",
                    "Business Unit name is required.",
                    400,
                )
            if new_name != business_unit.name:
                changed_fields.append(("name", business_unit.name, new_name))
                business_unit.name = new_name

        if "description" in payload:
            new_description = str(payload.get("description", "")).strip()
            if new_description != business_unit.description:
                changed_fields.append(
                    ("description", business_unit.description, new_description)
                )
                business_unit.description = new_description

        if "status_code" in payload:
            new_status = _ref_value(
                "BUSINESS_UNIT_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != business_unit.status_id:
                changed_fields.append(
                    ("status", business_unit.status.value_code, new_status.value_code)
                )
                business_unit.status = new_status

        if changed_fields:
            try:
                business_unit.updated_by = current_user.email
                business_unit.save()
            except IntegrityError as exc:
                raise AuthError(
                    "BUSINESS_UNIT_CODE_NOT_UNIQUE",
                    "Business Unit code must be unique within the Business Unit office.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="business_unit",
                entity_id=business_unit.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Business Unit updated by Timesheet Administrator.",
            )

        if BusinessUnitManagementService.CONFIG_FIELD_NAMES.intersection(payload):
            raise AuthError(
                "BUSINESS_UNIT_CONFIGURATION_INHERITED",
                "Business Unit configuration is inherited from the parent "
                "Office and cannot be changed here.",
                400,
            )

        return BusinessUnitManagementService.get_business_unit(current_user, business_unit.id)

    @staticmethod
    @transaction.atomic
    def delete_business_unit(current_user: CurrentUser, business_unit_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            business_unit.office,
            out_of_scope_message="Business Unit is outside your active office.",
        )

        BusinessUnitManagementService._delete_scope_assignments_for_deleted_business_unit(
            current_user,
            business_unit,
            actor_employee=actor_employee,
        )
        BusinessUnitManagementService._delete_role_assignments_for_deleted_business_unit(
            current_user,
            business_unit,
            actor_employee=actor_employee,
        )
        AuditLog.objects.filter(business_unit=business_unit).update(business_unit=None)

        try:
            business_unit_code = business_unit.bu_code
            business_unit_record_id = business_unit.id
            business_unit.delete()
        except ProtectedError as exc:
            raise AuthError(
                "BUSINESS_UNIT_DELETE_BLOCKED",
                "Business Unit cannot be deleted because it is still referenced by "
                "employees, projects, calendars, timesheets, audit history, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="business_unit",
            entity_id=business_unit_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=business_unit_code,
            reason_text="Business Unit deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _delete_scope_assignments_for_deleted_business_unit(
        current_user: CurrentUser,
        business_unit: BusinessUnit,
        *,
        actor_employee: Employee | None,
    ) -> None:
        removable_assignments = list(
            EmployeeBusinessUnit.objects.select_related("employee", "business_unit")
            .filter(business_unit=business_unit)
            .exclude(employee__primary_business_unit=business_unit)
        )
        for assignment in removable_assignments:
            write_audit_event(
                action_code="DELETE",
                entity_name="employee_business_unit",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=assignment.employee.primary_business_unit,
                old_value=assignment.business_unit.bu_code,
                reason_text="Business Unit scope assignment deleted with Business Unit deletion.",
            )
            assignment.delete()

    @staticmethod
    def _delete_role_assignments_for_deleted_business_unit(
        current_user: CurrentUser,
        business_unit: BusinessUnit,
        *,
        actor_employee: Employee | None,
    ) -> None:
        removable_assignments = list(
            EmployeeRole.objects.select_related("employee", "role")
            .filter(business_unit=business_unit)
            .exclude(employee__primary_business_unit=business_unit)
        )
        for assignment in removable_assignments:
            write_audit_event(
                action_code="DELETE",
                entity_name="employee_role",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=assignment.employee.primary_business_unit,
                old_value=assignment.role.value_code,
                reason_text="Business Unit-scoped role deleted with Business Unit deletion.",
            )
            assignment.delete()

    @staticmethod
    def _get_scoped_business_unit_with_counts(
        current_user: CurrentUser,
        business_unit_id: int,
    ) -> BusinessUnit:
        _ensure_business_units_in_scope(current_user, {business_unit_id})
        try:
            business_unit = (
                BusinessUnit.objects.select_related(
                    "office",
                    "office__configuration__approval_mode",
                    "status",
                )
                .annotate(
                    employee_count=Count("primary_employees", distinct=True),
                    project_count=Count("projects", distinct=True),
                )
                .get(id=business_unit_id)
            )
        except BusinessUnit.DoesNotExist as exc:
            raise AuthError("BUSINESS_UNIT_NOT_FOUND", "Business Unit not found.", 404) from exc
        _ensure_office_in_scope(
            current_user,
            business_unit.office_id,
            message="Business Unit is outside your active office.",
        )
        return business_unit

    @staticmethod
    def _sync_office_ts_admin_scope_assignments(
        current_user: CurrentUser,
        business_unit: BusinessUnit,
        *,
        actor_employee: Employee | None,
    ) -> None:
        office_admins = (
            Employee.objects.select_related("primary_business_unit")
            .filter(
                office_id=business_unit.office_id,
                role_assignments__role__domain__domain_code="ROLE_CODE",
                role_assignments__role__value_code="TS_ADMIN",
                role_assignments__status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                role_assignments__status__value_code="ACTIVE",
                role_assignments__valid_to__isnull=True,
            )
            .distinct()
        )
        for office_admin in office_admins:
            EmployeeManagementService._replace_business_unit_assignments(
                current_user,
                office_admin,
                actor_employee=actor_employee,
                primary_business_unit_id=office_admin.primary_business_unit_id,
                business_unit_ids={office_admin.primary_business_unit_id},
                reason="Employee BU scope synchronized after Business Unit creation.",
                force_full_office_scope=True,
            )


class CountryManagementService:
    @staticmethod
    def list_countries(current_user: CurrentUser, *, status_code: str | None = None) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        countries = _apply_status_filter(
            Country.objects.select_related("status")
            .annotate(office_count=Count("offices"))
            .order_by("country_name"),
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
        country_code = str(payload.get("country_code", "")).strip()
        country_name = str(payload.get("country_name", "")).strip()
        if not country_code:
            raise AuthError("COUNTRY_CODE_REQUIRED", "Country code is required.", 400)
        if not country_name:
            raise AuthError("COUNTRY_NAME_REQUIRED", "Country name is required.", 400)
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        try:
            country = Country.objects.create(
                country_code=country_code,
                country_name=country_name,
                status=_ref_value("COUNTRY_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "COUNTRY_NOT_UNIQUE",
                "Country code and country name must be unique.",
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

        if "country_code" in payload:
            new_country_code = str(payload.get("country_code", "")).strip()
            if not new_country_code:
                raise AuthError("COUNTRY_CODE_REQUIRED", "Country code is required.", 400)
            if new_country_code != country.country_code:
                changed_fields.append(("country_code", country.country_code, new_country_code))
                country.country_code = new_country_code

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
                    "COUNTRY_NOT_UNIQUE",
                    "Country code and country name must be unique.",
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
    @transaction.atomic
    def delete_country(current_user: CurrentUser, country_id: int) -> None:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country = CountryManagementService._refresh_country(country_id)
        try:
            country_name = country.country_name
            country_record_id = country.id
            country.delete()
        except ProtectedError as exc:
            raise AuthError(
                "COUNTRY_DELETE_BLOCKED",
                "Country cannot be deleted because it is still referenced by Offices "
                "or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="country",
            entity_id=country_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=country_name,
            reason_text="Country deleted by Timesheet Master Administrator.",
        )

    @staticmethod
    def _refresh_country(country_id: int) -> Country:
        try:
            return (
                Country.objects.select_related("status")
                .annotate(office_count=Count("offices"))
                .get(id=country_id)
            )
        except Country.DoesNotExist as exc:
            raise AuthError("COUNTRY_NOT_FOUND", "Country not found.", 404) from exc


class OfficeManagementService:
    CONFIG_FIELD_NAMES = BusinessUnitManagementService.CONFIG_FIELD_NAMES

    @staticmethod
    def list_offices(current_user: CurrentUser, *, status_code: str | None = None) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        offices = _apply_status_filter(
            Office.objects.select_related(
                "country",
                "country__status",
                "status",
                "configuration",
                "configuration__approval_mode",
            )
            .annotate(
                active_employee_count=Count(
                    "employees",
                    filter=Q(employees__status__value_code="ACTIVE"),
                    distinct=True,
                )
            )
            .order_by("office_name"),
            status_code,
        )
        return [_serialize_office(office) for office in offices]

    @staticmethod
    def get_office(current_user: CurrentUser, office_id: int) -> dict:
        _ensure_ts_admin_master(current_user)
        return _serialize_office(OfficeManagementService._refresh_office(office_id))

    @staticmethod
    @transaction.atomic
    def create_office(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country_id = _parse_required_int(
            payload.get("country_id"),
            code="COUNTRY_REQUIRED",
            message="country_id is required.",
        )
        country = CountryManagementService._refresh_country(country_id)
        office_name = str(payload.get("office_name", "")).strip()
        if not office_name:
            raise AuthError("COUNTRY_NAME_REQUIRED", "Office name is required.", 400)
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        bootstrap_business_unit_code = str(payload.get("bootstrap_bu_code", "")).strip()
        bootstrap_business_unit_name = str(payload.get("bootstrap_bu_name", "")).strip()
        bootstrap_business_unit_description = str(
            payload.get("bootstrap_bu_description", "")
        ).strip()
        bootstrap_admin_employee_code = str(
            payload.get("bootstrap_admin_employee_code", "")
        ).strip()
        bootstrap_admin_full_name = str(payload.get("bootstrap_admin_full_name", "")).strip()
        bootstrap_admin_email = str(payload.get("bootstrap_admin_email", "")).strip()
        if not bootstrap_business_unit_code:
            raise AuthError(
                "BUSINESS_UNIT_CODE_REQUIRED",
                "Initial Business Unit code is required.",
                400,
            )
        if not bootstrap_business_unit_name:
            raise AuthError(
                "BUSINESS_UNIT_NAME_REQUIRED",
                "Initial Business Unit name is required.",
                400,
            )
        if not bootstrap_admin_employee_code:
            raise AuthError(
                "EMPLOYEE_CODE_REQUIRED",
                "Initial admin employee code is required.",
                400,
            )
        if not bootstrap_admin_full_name:
            raise AuthError(
                "EMPLOYEE_NAME_REQUIRED",
                "Initial admin full name is required.",
                400,
            )
        if not bootstrap_admin_email:
            raise AuthError(
                "EMPLOYEE_EMAIL_REQUIRED",
                "Initial admin email is required.",
                400,
            )
        try:
            office = Office.objects.create(
                country=country,
                office_name=office_name,
                status=_ref_value("COUNTRY_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "COUNTRY_NAME_NOT_UNIQUE",
                "Office name must be unique.",
                400,
            ) from exc

        OfficeManagementService._upsert_configuration(
            current_user,
            office,
            payload,
            actor_employee=actor_employee,
            create_if_missing=True,
        )
        bootstrap_business_unit = OfficeManagementService._create_bootstrap_business_unit(
            current_user,
            office,
            bu_code=bootstrap_business_unit_code,
            name=bootstrap_business_unit_name,
            description=bootstrap_business_unit_description,
            actor_employee=actor_employee,
        )
        OfficeManagementService._create_bootstrap_admin_employee(
            current_user,
            office,
            business_unit=bootstrap_business_unit,
            employee_code=bootstrap_admin_employee_code,
            full_name=bootstrap_admin_full_name,
            email=bootstrap_admin_email,
            actor_employee=actor_employee,
        )
        write_audit_event(
            action_code="CREATE",
            entity_name="office",
            entity_id=office.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Office created by Timesheet Master Administrator.",
        )
        return _serialize_office(OfficeManagementService._refresh_office(office.id))

    @staticmethod
    @transaction.atomic
    def update_office(current_user: CurrentUser, office_id: int, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        office = OfficeManagementService._refresh_office(office_id)
        changed_fields: list[tuple[str, str, str]] = []

        if "country_id" in payload:
            new_country_id = _parse_required_int(
                payload.get("country_id"),
                code="COUNTRY_REQUIRED",
                message="country_id is required.",
            )
            if new_country_id != office.country_id:
                new_country = CountryManagementService._refresh_country(new_country_id)
                changed_fields.append(
                    ("country", office.country.country_code, new_country.country_code)
                )
                office.country = new_country

        if "office_name" in payload:
            new_office_name = str(payload.get("office_name", "")).strip()
            if not new_office_name:
                raise AuthError("COUNTRY_NAME_REQUIRED", "Office name is required.", 400)
            if new_office_name != office.office_name:
                changed_fields.append(("office_name", office.office_name, new_office_name))
                office.office_name = new_office_name

        if "status_code" in payload:
            new_status = _ref_value("COUNTRY_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != office.status_id:
                changed_fields.append(("status", office.status.value_code, new_status.value_code))
                office.status = new_status

        if changed_fields:
            try:
                office.updated_by = current_user.email
                office.save()
            except IntegrityError as exc:
                raise AuthError(
                    "COUNTRY_NAME_NOT_UNIQUE",
                    "Office name must be unique.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="office",
                entity_id=office.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Office updated by Timesheet Master Administrator.",
            )

        if changed_fields or OfficeManagementService.CONFIG_FIELD_NAMES.intersection(payload):
            OfficeManagementService._upsert_configuration(
                current_user,
                office,
                payload,
                actor_employee=actor_employee,
                create_if_missing=True,
            )

        return _serialize_office(OfficeManagementService._refresh_office(office.id))

    @staticmethod
    @transaction.atomic
    def delete_office(current_user: CurrentUser, office_id: int) -> None:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        office = OfficeManagementService._refresh_office(office_id)
        configuration = OfficeConfiguration.objects.filter(office=office).first()

        if configuration is not None:
            write_audit_event(
                action_code="DELETE",
                entity_name="office_configuration",
                entity_id=configuration.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                reason_text="Office configuration deleted with Office deletion.",
            )
            configuration.delete()

        try:
            office_name = office.office_name
            office_record_id = office.id
            office.delete()
        except ProtectedError as exc:
            raise AuthError(
                "COUNTRY_DELETE_BLOCKED",
                "Office cannot be deleted because it is still referenced by "
                "Business Units or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="office",
            entity_id=office_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=office_name,
            reason_text="Office deleted by Timesheet Master Administrator.",
        )

    @staticmethod
    def _refresh_office(office_id: int) -> Office:
        try:
            office = (
                Office.objects.select_related(
                    "country",
                    "country__status",
                    "status",
                    "configuration",
                    "configuration__approval_mode",
                )
                .annotate(
                    active_employee_count=Count(
                        "employees",
                        filter=Q(employees__status__value_code="ACTIVE"),
                        distinct=True,
                    )
                )
                .get(id=office_id)
            )
        except Office.DoesNotExist as exc:
            raise AuthError("COUNTRY_NOT_FOUND", "Office not found.", 404) from exc
        office._administrators_cache = list(
            Employee.objects.select_related("primary_business_unit", "status")
            .filter(
                office_id=office.id,
                role_assignments__role__domain__domain_code="ROLE_CODE",
                role_assignments__role__value_code="TS_ADMIN",
                role_assignments__status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                role_assignments__status__value_code="ACTIVE",
                role_assignments__valid_to__isnull=True,
            )
            .order_by("employee_code")
            .distinct()
        )
        return office

    @staticmethod
    def _upsert_configuration(
        current_user: CurrentUser,
        office: Office,
        payload: dict,
        *,
        actor_employee: Employee | None,
        create_if_missing: bool,
    ) -> None:
        configuration = OfficeConfiguration.objects.select_related("approval_mode").filter(
            office=office
        ).first()
        defaults = _default_office_configuration_data()

        approval_mode_code = str(
            payload.get(
                "approval_mode_code",
                configuration.approval_mode.value_code
                if configuration
                else defaults["approval_mode"],
            )
        ).strip()
        if not approval_mode_code:
            raise AuthError(
                "OFFICE_APPROVAL_MODE_REQUIRED",
                "approval_mode_code is required.",
                400,
            )

        archive_after_years = _parse_required_int(
            payload.get(
                "archive_after_years",
                configuration.archive_after_years
                if configuration
                else defaults["archive_after_years"],
            ),
            code="OFFICE_ARCHIVE_YEARS_REQUIRED",
            message="archive_after_years is required.",
        )
        if archive_after_years <= 0:
            raise AuthError(
                "OFFICE_ARCHIVE_YEARS_INVALID",
                "archive_after_years must be greater than 0.",
                400,
            )

        timesheet_cutoff_date = _parse_optional_iso_date(
            payload.get(
                "timesheet_cutoff_date",
                configuration.timesheet_cutoff_date if configuration else None,
            ),
            code="OFFICE_CUTOFF_DATE_INVALID",
            message="timesheet_cutoff_date must be a valid ISO date.",
        )

        allow_employee_withdraw_flag = _parse_bool(
            payload.get(
                "allow_employee_withdraw_flag",
                configuration.allow_employee_withdraw_flag
                if configuration
                else defaults["allow_employee_withdraw_flag"],
            )
        )
        count_non_billable_in_daily_limit_flag = _parse_bool(
            payload.get(
                "count_non_billable_in_daily_limit_flag",
                configuration.count_non_billable_in_daily_limit_flag
                if configuration
                else defaults["count_non_billable_in_daily_limit_flag"],
            )
        )
        enable_timer_flag = _parse_bool(
            payload.get(
                "enable_timer_flag",
                configuration.enable_timer_flag if configuration else defaults["enable_timer_flag"],
            )
        )
        enable_leave_integration_flag = _parse_bool(
            payload.get(
                "enable_leave_integration_flag",
                configuration.enable_leave_integration_flag
                if configuration
                else defaults["enable_leave_integration_flag"],
            )
        )
        enable_copy_previous_week_flag = _parse_bool(
            payload.get(
                "enable_copy_previous_week_flag",
                configuration.enable_copy_previous_week_flag
                if configuration
                else defaults["enable_copy_previous_week_flag"],
            )
        )

        approval_mode = _ref_value("APPROVAL_MODE", approval_mode_code)

        if configuration is None:
            if not create_if_missing:
                return
            configuration = OfficeConfiguration.objects.create(
                office=office,
                approval_mode=approval_mode,
                allow_employee_withdraw_flag=allow_employee_withdraw_flag,
                timesheet_cutoff_date=timesheet_cutoff_date,
                count_non_billable_in_daily_limit_flag=count_non_billable_in_daily_limit_flag,
                archive_after_years=archive_after_years,
                enable_timer_flag=enable_timer_flag,
                enable_leave_integration_flag=enable_leave_integration_flag,
                enable_copy_previous_week_flag=enable_copy_previous_week_flag,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
            write_audit_event(
                action_code="CREATE",
                entity_name="office_configuration",
                entity_id=configuration.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name="office_configuration",
                new_value="created",
                reason_text="Office configuration created by Timesheet Master Administrator.",
            )
            return

        changed_fields: list[tuple[str, str, str]] = []
        if approval_mode.id != configuration.approval_mode_id:
            changed_fields.append(
                ("approval_mode", configuration.approval_mode.value_code, approval_mode.value_code)
            )
            configuration.approval_mode = approval_mode
        if allow_employee_withdraw_flag != configuration.allow_employee_withdraw_flag:
            changed_fields.append(
                (
                    "allow_employee_withdraw_flag",
                    str(configuration.allow_employee_withdraw_flag),
                    str(allow_employee_withdraw_flag),
                )
            )
            configuration.allow_employee_withdraw_flag = allow_employee_withdraw_flag
        old_cutoff_date = (
            configuration.timesheet_cutoff_date.isoformat()
            if configuration.timesheet_cutoff_date
            else ""
        )
        new_cutoff_date = timesheet_cutoff_date.isoformat() if timesheet_cutoff_date else ""
        if old_cutoff_date != new_cutoff_date:
            changed_fields.append(("timesheet_cutoff_date", old_cutoff_date, new_cutoff_date))
            configuration.timesheet_cutoff_date = timesheet_cutoff_date
        if (
            count_non_billable_in_daily_limit_flag
            != configuration.count_non_billable_in_daily_limit_flag
        ):
            changed_fields.append(
                (
                    "count_non_billable_in_daily_limit_flag",
                    str(configuration.count_non_billable_in_daily_limit_flag),
                    str(count_non_billable_in_daily_limit_flag),
                )
            )
            configuration.count_non_billable_in_daily_limit_flag = (
                count_non_billable_in_daily_limit_flag
            )
        if archive_after_years != configuration.archive_after_years:
            changed_fields.append(
                (
                    "archive_after_years",
                    str(configuration.archive_after_years),
                    str(archive_after_years),
                )
            )
            configuration.archive_after_years = archive_after_years
        if enable_timer_flag != configuration.enable_timer_flag:
            changed_fields.append(
                ("enable_timer_flag", str(configuration.enable_timer_flag), str(enable_timer_flag))
            )
            configuration.enable_timer_flag = enable_timer_flag
        if enable_leave_integration_flag != configuration.enable_leave_integration_flag:
            changed_fields.append(
                (
                    "enable_leave_integration_flag",
                    str(configuration.enable_leave_integration_flag),
                    str(enable_leave_integration_flag),
                )
            )
            configuration.enable_leave_integration_flag = enable_leave_integration_flag
        if enable_copy_previous_week_flag != configuration.enable_copy_previous_week_flag:
            changed_fields.append(
                (
                    "enable_copy_previous_week_flag",
                    str(configuration.enable_copy_previous_week_flag),
                    str(enable_copy_previous_week_flag),
                )
            )
            configuration.enable_copy_previous_week_flag = enable_copy_previous_week_flag

        if changed_fields:
            configuration.updated_by = current_user.email
            configuration.save()
            for field_name, old_value, new_value in changed_fields:
                write_audit_event(
                    action_code="UPDATE",
                    entity_name="office_configuration",
                    entity_id=configuration.id,
                    actor_employee=actor_employee,
                    actor_email=current_user.email,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    reason_text="Office configuration updated by Timesheet Master Administrator.",
                )

    @staticmethod
    def _create_bootstrap_business_unit(
        current_user: CurrentUser,
        office: Office,
        *,
        bu_code: str,
        name: str,
        description: str,
        actor_employee: Employee | None,
    ) -> BusinessUnit:
        _ensure_business_unit_code_available(
            office_id=office.id,
            bu_code=bu_code,
            message="Initial Business Unit code must be unique within the Office.",
        )
        try:
            business_unit = BusinessUnit.objects.create(
                bu_code=bu_code,
                name=name,
                description=description,
                office=office,
                status=_ref_value("BUSINESS_UNIT_STATUS", "ACTIVE"),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "BUSINESS_UNIT_CODE_NOT_UNIQUE",
                "Initial Business Unit code must be unique within the Office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="business_unit",
            entity_id=business_unit.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            reason_text="Initial Business Unit created with Office creation.",
        )
        return business_unit

    @staticmethod
    def _create_bootstrap_admin_employee(
        current_user: CurrentUser,
        office: Office,
        *,
        business_unit: BusinessUnit,
        employee_code: str,
        full_name: str,
        email: str,
        actor_employee: Employee | None,
    ) -> Employee:
        try:
            employee = Employee.objects.create(
                employee_code=employee_code,
                full_name=full_name,
                email=email,
                canonical_email=canonicalize_email(email),
                office=office,
                status=_ref_value("EMPLOYEE_STATUS", "ACTIVE"),
                primary_business_unit=business_unit,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "EMPLOYEE_EMAIL_NOT_UNIQUE",
                "Initial admin employee email must be unique.",
                400,
            ) from exc

        EmployeeManagementService._replace_business_unit_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            primary_business_unit_id=business_unit.id,
            business_unit_ids={business_unit.id},
            reason="Initial Office administrator created with initial BU assignments.",
            enforce_current_office_scope=False,
        )
        EmployeeManagementService._replace_role_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            role_codes=["TS_ADMIN", "USER"],
            reason="Initial Office administrator created with initial role assignments.",
        )

        write_audit_event(
            action_code="CREATE",
            entity_name="employee",
            entity_id=employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            reason_text="Initial Office administrator created with Office creation.",
        )
        return employee


class EmployeeManagementService:
    @staticmethod
    def list_employees(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        employees = _apply_status_filter(
            Employee.objects.select_related("primary_business_unit", "office", "status")
            .prefetch_related(
                "business_unit_assignments__business_unit",
                "business_unit_assignments__status__domain",
                "role_assignments__role",
                "role_assignments__status__domain",
            )
            .filter(
                primary_business_unit_id__in=current_user.scoped_business_unit_ids,
                office_id=current_user.office_id,
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
        _ensure_current_office_active_for_write(current_user)
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
        _ensure_scoped_active_office_for_write(
            current_user,
            primary_business_unit.office,
            out_of_scope_message="Primary Business Unit is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="EMPLOYEE",
            expected_office_id=primary_business_unit.office_id,
            mismatch_message=(
                "Employee office must match the selected primary Business Unit office."
            ),
        )

        try:
            employee = Employee.objects.create(
                employee_code=employee_code,
                full_name=full_name,
                email=email,
                canonical_email=canonicalize_email(email),
                office=primary_business_unit.office,
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
            force_full_office_scope="TS_ADMIN" in role_codes,
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            employee.office,
            out_of_scope_message="Employee is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="EMPLOYEE",
            expected_office_id=employee.office_id,
            immutable_office_id=employee.office_id,
            mismatch_message="Employee office must match the employee office.",
            immutable_message="Employee office cannot be changed.",
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
        if "TS_ADMIN" in role_codes:
            EmployeeManagementService._replace_business_unit_assignments(
                current_user,
                employee,
                actor_employee=actor_employee,
                primary_business_unit_id=employee.primary_business_unit_id,
                business_unit_ids={employee.primary_business_unit_id},
                reason="Employee BU scope synchronized after TS_ADMIN role assignment.",
                force_full_office_scope=True,
            )
        return _serialize_employee(_refresh_employee(employee.id))

    @staticmethod
    @transaction.atomic
    def replace_business_units(current_user: CurrentUser, employee_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        actor_employee = _actor_employee(current_user)
        primary_business_unit_id, business_unit_ids = _parse_business_unit_scope(payload)
        _ensure_business_units_in_scope(current_user, business_unit_ids)
        _validate_optional_office_payload(
            payload,
            code_prefix="EMPLOYEE",
            expected_office_id=employee.office_id,
            immutable_office_id=employee.office_id,
            mismatch_message="Employee office must match the employee office.",
            immutable_message="Employee office cannot be changed.",
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
    @transaction.atomic
    def delete_employee(current_user: CurrentUser, employee_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        if current_user.employee_id == employee_id:
            raise AuthError(
                "EMPLOYEE_DELETE_SELF_BLOCKED",
                "You cannot delete your own employee record.",
                400,
            )

        actor_employee = _actor_employee(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            employee.office,
            out_of_scope_message="Employee is outside your active office.",
        )

        EmployeeManagementService._delete_role_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
        )
        EmployeeManagementService._delete_business_unit_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
        )

        try:
            employee_name = employee.full_name
            employee_record_id = employee.id
            employee.delete()
        except ProtectedError as exc:
            raise AuthError(
                "EMPLOYEE_DELETE_BLOCKED",
                "Employee cannot be deleted because it is still referenced by "
                "timesheets, approvals, management relationships, audit history, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="employee",
            entity_id=employee_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=employee.primary_business_unit,
            old_value=employee_name,
            reason_text="Employee deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _delete_role_assignments(
        current_user: CurrentUser,
        employee: Employee,
        *,
        actor_employee: Employee | None,
    ) -> None:
        assignments = list(employee.role_assignments.select_related("role"))
        for assignment in assignments:
            write_audit_event(
                action_code="DELETE",
                entity_name="employee_role",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=employee.primary_business_unit,
                old_value=assignment.role.value_code,
                reason_text="Employee role deleted with Employee deletion.",
            )
            assignment.delete()

    @staticmethod
    def _delete_business_unit_assignments(
        current_user: CurrentUser,
        employee: Employee,
        *,
        actor_employee: Employee | None,
    ) -> None:
        assignments = list(
            employee.business_unit_assignments.select_related("business_unit").all()
        )
        for assignment in assignments:
            write_audit_event(
                action_code="DELETE",
                entity_name="employee_business_unit",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=employee.primary_business_unit,
                old_value=assignment.business_unit.bu_code,
                reason_text="Employee Business Unit scope deleted with Employee deletion.",
            )
            assignment.delete()

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
        enforce_current_office_scope: bool = True,
        force_full_office_scope: bool = False,
    ) -> None:
        active_status = _ref_value("EMPLOYEE_BU_STATUS", "ACTIVE")
        inactive_status = _ref_value("EMPLOYEE_BU_STATUS", "INACTIVE")
        full_office_scope_required = force_full_office_scope or _employee_has_active_role(
            employee.id,
            role_code="TS_ADMIN",
        )
        desired_business_units = (
            _office_business_units(employee.office_id)
            if full_office_scope_required
            else {
                business_unit.id: business_unit
                for business_unit in BusinessUnit.objects.select_related("office", "office__status")
                .filter(id__in=business_unit_ids)
                .order_by("bu_code")
            }
        )
        if primary_business_unit_id not in desired_business_units:
            raise AuthError(
                "EMPLOYEE_PRIMARY_BU_OUT_OF_SCOPE",
                "Primary Business Unit must be included in the employee scope.",
                400,
            )
        if employee.office_id != desired_business_units[primary_business_unit_id].office_id:
            raise AuthError(
                "EMPLOYEE_COUNTRY_IMMUTABLE",
                "Employee office cannot be changed.",
                400,
            )
        desired_office_ids = {
            business_unit.office_id for business_unit in desired_business_units.values()
        }
        if len(desired_office_ids) != 1:
            raise AuthError(
                "EMPLOYEE_BUSINESS_UNIT_COUNTRY_MISMATCH",
                "All employee Business Units must belong to the same office.",
                400,
            )
        desired_office = next(iter(desired_business_units.values())).office
        if enforce_current_office_scope:
            _ensure_scoped_active_office_for_write(
                current_user,
                desired_office,
                out_of_scope_message="Employee Business Units must stay inside your active office.",
            )
        else:
            _ensure_office_active_for_write(
                desired_office,
                message="Records in inactive offices cannot be created or edited.",
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
                existing_inactive = (
                    employee.business_unit_assignments.select_related("status", "status__domain")
                    .filter(
                        business_unit=business_unit,
                        status__domain__domain_code="EMPLOYEE_BU_STATUS",
                        status__value_code="INACTIVE",
                        valid_to=date.today(),
                    )
                    .order_by("-id")
                    .first()
                )
                if existing_inactive is not None:
                    existing_inactive.is_primary_flag = is_primary
                    existing_inactive.status = active_status
                    existing_inactive.valid_to = None
                    existing_inactive.updated_by = current_user.email
                    existing_inactive.save(
                        update_fields=[
                            "is_primary_flag",
                            "status",
                            "valid_to",
                            "updated_by",
                            "updated_at",
                        ]
                    )
                else:
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
                "office",
                "parent_client",
                "status",
            )
            .filter(
                office_id=current_user.office_id,
            )
            .order_by("client_code"),
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        current_office = _ensure_current_office_active_for_write(current_user)

        client_code = str(payload.get("client_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not client_code:
            raise AuthError("CLIENT_CODE_REQUIRED", "Client code is required.", 400)
        if not name:
            raise AuthError("CLIENT_NAME_REQUIRED", "Client name is required.", 400)

        parent_client = ClientManagementService._resolve_parent_client(
            current_user,
            office_id=current_office.id,
            parent_client_id=payload.get("parent_client_id"),
        )
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_office_payload(
            payload,
            code_prefix="CLIENT",
            expected_office_id=current_office.id,
            mismatch_message="Client office must match your active office.",
        )

        try:
            client = ClientRecord.objects.create(
                office=current_office,
                parent_client=parent_client,
                client_code=client_code,
                name=name,
                status=_ref_value("CLIENT_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            error_text = str(exc).lower()
            if "business_unit_id" in error_text and "not null" in error_text:
                raise AuthError(
                    "CLIENT_SCHEMA_OUTDATED",
                    "Client schema is outdated. Run the latest database migrations and try again.",
                    500,
                ) from exc
            raise AuthError(
                "CLIENT_CODE_NOT_UNIQUE",
                "Client code must be unique within the Office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="client",
            entity_id=client.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Client created by Timesheet Administrator.",
        )
        return _serialize_client(ClientManagementService._refresh_client(client.id))

    @staticmethod
    @transaction.atomic
    def update_client(current_user: CurrentUser, client_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        client = ClientManagementService._get_scoped_client(current_user, client_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            client.office,
            out_of_scope_message="Client is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="CLIENT",
            expected_office_id=client.office_id,
            immutable_office_id=client.office_id,
            mismatch_message="Client office must match the client office.",
            immutable_message="Client office cannot be changed.",
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
                office_id=client.office_id,
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
                    "Client code must be unique within the Office.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="client",
                entity_id=client.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Client updated by Timesheet Administrator.",
            )

        return _serialize_client(ClientManagementService._refresh_client(client.id))

    @staticmethod
    @transaction.atomic
    def delete_client(current_user: CurrentUser, client_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        client = ClientManagementService._get_scoped_client(current_user, client_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            client.office,
            out_of_scope_message="Client is outside your active office.",
        )

        try:
            client_code = client.client_code
            client_record_id = client.id
            client.delete()
        except ProtectedError as exc:
            raise AuthError(
                "CLIENT_DELETE_BLOCKED",
                "Client cannot be deleted because it is still referenced by "
                "Projects, child Clients, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="client",
            entity_id=client_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=client_code,
            reason_text="Client deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _get_scoped_client(current_user: CurrentUser, client_id: int) -> ClientRecord:
        try:
            client = ClientRecord.objects.select_related(
                "office", "parent_client", "status"
            ).get(id=client_id)
        except ClientRecord.DoesNotExist as exc:
            raise AuthError("CLIENT_NOT_FOUND", "Client not found.", 404) from exc

        _ensure_office_in_scope(
            current_user,
            client.office_id,
            message="Client is outside your active office.",
        )
        return client

    @staticmethod
    def _refresh_client(client_id: int) -> ClientRecord:
        return ClientRecord.objects.select_related(
            "office", "parent_client", "status"
        ).get(id=client_id)

    @staticmethod
    def _resolve_parent_client(
        current_user: CurrentUser,
        *,
        office_id: int,
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
            parent_client = ClientRecord.objects.select_related("office").get(
                id=resolved_parent_client_id
            )
        except ClientRecord.DoesNotExist as exc:
            raise AuthError("CLIENT_PARENT_NOT_FOUND", "Parent client not found.", 404) from exc

        _ensure_office_in_scope(
            current_user,
            parent_client.office_id,
            message="Parent client is outside your active office.",
        )
        if parent_client.office_id != office_id:
            raise AuthError(
                "CLIENT_PARENT_OFFICE_MISMATCH",
                "Parent client must belong to the same Office.",
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
            InternalCategoryRecord.objects.select_related("business_unit", "office", "status")
            .filter(
                business_unit_id__in=current_user.scoped_business_unit_ids,
                office_id=current_user.office_id,
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="INTERNAL_CATEGORY_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            business_unit.office,
            out_of_scope_message="Internal category Business Unit is outside your active office.",
        )

        category_code = str(payload.get("category_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not category_code:
            raise AuthError("INTERNAL_CATEGORY_CODE_REQUIRED", "Category code is required.", 400)
        if not name:
            raise AuthError("INTERNAL_CATEGORY_NAME_REQUIRED", "Category name is required.", 400)

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_office_payload(
            payload,
            code_prefix="INTERNAL_CATEGORY",
            expected_office_id=business_unit.office_id,
            mismatch_message=(
                "Internal category office must match the selected Business Unit office."
            ),
        )

        try:
            category = InternalCategoryRecord.objects.create(
                business_unit=business_unit,
                office=business_unit.office,
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        category = InternalCategoryManagementService._get_scoped_category(current_user, category_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            category.office,
            out_of_scope_message="Internal category is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="INTERNAL_CATEGORY",
            expected_office_id=category.office_id,
            immutable_office_id=category.office_id,
            mismatch_message="Internal category office must match the internal category office.",
            immutable_message="Internal category office cannot be changed.",
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
    @transaction.atomic
    def delete_category(current_user: CurrentUser, category_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        category = InternalCategoryManagementService._get_scoped_category(current_user, category_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            category.office,
            out_of_scope_message="Internal category is outside your active office.",
        )

        try:
            category_code = category.category_code
            category_record_id = category.id
            category.delete()
        except ProtectedError as exc:
            raise AuthError(
                "INTERNAL_CATEGORY_DELETE_BLOCKED",
                "Internal category cannot be deleted because it is still referenced by "
                "Projects or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="internal_category",
            entity_id=category_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=category.business_unit,
            old_value=category_code,
            reason_text="Internal category deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _get_scoped_category(
        current_user: CurrentUser,
        category_id: int,
    ) -> InternalCategoryRecord:
        try:
            category = InternalCategoryRecord.objects.select_related(
                "business_unit", "office", "status"
            ).get(id=category_id)
        except InternalCategoryRecord.DoesNotExist as exc:
            raise AuthError(
                "INTERNAL_CATEGORY_NOT_FOUND", "Internal category not found.", 404
            ) from exc

        _ensure_business_units_in_scope(current_user, {category.business_unit_id})
        _ensure_office_in_scope(
            current_user,
            category.office_id,
            message="Internal category is outside your active office.",
        )
        return category

    @staticmethod
    def _refresh_category(category_id: int) -> InternalCategoryRecord:
        return InternalCategoryRecord.objects.select_related(
            "business_unit",
            "office",
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
            CostCenterRecord.objects.select_related("office", "status")
            .filter(
                office_id=current_user.office_id,
            )
            .order_by("cost_center_code"),
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        current_office = _ensure_current_office_active_for_write(current_user)

        cost_center_code = str(payload.get("cost_center_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not cost_center_code:
            raise AuthError("COST_CENTER_CODE_REQUIRED", "Cost center code is required.", 400)
        if not name:
            raise AuthError("COST_CENTER_NAME_REQUIRED", "Cost center name is required.", 400)

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        _validate_optional_office_payload(
            payload,
            code_prefix="COST_CENTER",
            expected_office_id=current_office.id,
            mismatch_message="Cost center office must match your active office.",
        )

        try:
            cost_center = CostCenterRecord.objects.create(
                office=current_office,
                cost_center_code=cost_center_code,
                name=name,
                description=description,
                status=_ref_value("COST_CENTER_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            error_text = str(exc).lower()
            if "business_unit_id" in error_text and "not null" in error_text:
                raise AuthError(
                    "COST_CENTER_SCHEMA_OUTDATED",
                    "Cost center schema is outdated. Run the latest database "
                    "migrations and try again.",
                    500,
                ) from exc
            raise AuthError(
                "COST_CENTER_CODE_NOT_UNIQUE",
                "Cost center code must be unique within the Office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="cost_center",
            entity_id=cost_center.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Cost center created by Timesheet Administrator.",
        )
        return _serialize_cost_center(
            CostCenterManagementService._refresh_cost_center(cost_center.id)
        )

    @staticmethod
    @transaction.atomic
    def update_cost_center(current_user: CurrentUser, cost_center_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user, cost_center_id
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            cost_center.office,
            out_of_scope_message="Cost center is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="COST_CENTER",
            expected_office_id=cost_center.office_id,
            immutable_office_id=cost_center.office_id,
            mismatch_message="Cost center office must match the cost center office.",
            immutable_message="Cost center office cannot be changed.",
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
                    "Cost center code must be unique within the Office.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="cost_center",
                entity_id=cost_center.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Cost center updated by Timesheet Administrator.",
            )

        return _serialize_cost_center(
            CostCenterManagementService._refresh_cost_center(cost_center.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_cost_center(current_user: CurrentUser, cost_center_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user, cost_center_id
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            cost_center.office,
            out_of_scope_message="Cost center is outside your active office.",
        )

        try:
            cost_center_code = cost_center.cost_center_code
            cost_center_record_id = cost_center.id
            cost_center.delete()
        except ProtectedError as exc:
            raise AuthError(
                "COST_CENTER_DELETE_BLOCKED",
                "Cost center cannot be deleted because it is still referenced by "
                "Projects or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="cost_center",
            entity_id=cost_center_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=cost_center_code,
            reason_text="Cost center deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _get_scoped_cost_center(
        current_user: CurrentUser,
        cost_center_id: int,
    ) -> CostCenterRecord:
        try:
            cost_center = CostCenterRecord.objects.select_related("office", "status").get(
                id=cost_center_id
            )
        except CostCenterRecord.DoesNotExist as exc:
            raise AuthError("COST_CENTER_NOT_FOUND", "Cost center not found.", 404) from exc

        _ensure_office_in_scope(
            current_user,
            cost_center.office_id,
            message="Cost center is outside your active office.",
        )
        return cost_center

    @staticmethod
    def _refresh_cost_center(cost_center_id: int) -> CostCenterRecord:
        return CostCenterRecord.objects.select_related("office", "status").get(id=cost_center_id)


class PricingModelManagementService:
    @staticmethod
    def list_pricing_models(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        pricing_models = PricingModelRecord.objects.select_related("office").filter(
            office_id=current_user.office_id
        ).order_by("name")
        return [_serialize_pricing_model(pricing_model) for pricing_model in pricing_models]

    @staticmethod
    def get_pricing_model(current_user: CurrentUser, pricing_model_id: int) -> dict:
        _ensure_ts_admin(current_user)
        pricing_model = PricingModelManagementService._get_scoped_pricing_model(
            current_user,
            pricing_model_id,
        )
        return _serialize_pricing_model(pricing_model)

    @staticmethod
    @transaction.atomic
    def create_pricing_model(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        current_office = _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not name:
            raise AuthError("PRICING_MODEL_NAME_REQUIRED", "Pricing model name is required.", 400)

        _validate_optional_office_payload(
            payload,
            code_prefix="PRICING_MODEL",
            expected_office_id=current_office.id,
            mismatch_message="Pricing model office must match your active office.",
        )

        pricing_model = PricingModelRecord.objects.create(
            office=current_office,
            name=name,
            description=description,
            created_by=current_user.email,
            updated_by=current_user.email,
        )

        write_audit_event(
            action_code="CREATE",
            entity_name="pricing_model",
            entity_id=pricing_model.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Pricing model created by Timesheet Administrator.",
        )
        return _serialize_pricing_model(
            PricingModelManagementService._refresh_pricing_model(pricing_model.id)
        )

    @staticmethod
    @transaction.atomic
    def update_pricing_model(
        current_user: CurrentUser,
        pricing_model_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        pricing_model = PricingModelManagementService._get_scoped_pricing_model(
            current_user,
            pricing_model_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            pricing_model.office,
            out_of_scope_message="Pricing model is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="PRICING_MODEL",
            expected_office_id=pricing_model.office_id,
            immutable_office_id=pricing_model.office_id,
            mismatch_message="Pricing model office must match the pricing model office.",
            immutable_message="Pricing model office cannot be changed.",
        )

        changed_fields: list[tuple[str, str, str]] = []

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError(
                    "PRICING_MODEL_NAME_REQUIRED",
                    "Pricing model name is required.",
                    400,
                )
            if new_name != pricing_model.name:
                changed_fields.append(("name", pricing_model.name, new_name))
                pricing_model.name = new_name

        if "description" in payload:
            new_description = str(payload.get("description", "")).strip()
            if new_description != pricing_model.description:
                changed_fields.append(("description", pricing_model.description, new_description))
                pricing_model.description = new_description

        if changed_fields:
            pricing_model.updated_by = current_user.email
            pricing_model.save(update_fields=["name", "description", "updated_by", "updated_at"])

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="pricing_model",
                entity_id=pricing_model.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Pricing model updated by Timesheet Administrator.",
            )

        return _serialize_pricing_model(
            PricingModelManagementService._refresh_pricing_model(pricing_model.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_pricing_model(current_user: CurrentUser, pricing_model_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        pricing_model = PricingModelManagementService._get_scoped_pricing_model(
            current_user,
            pricing_model_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            pricing_model.office,
            out_of_scope_message="Pricing model is outside your active office.",
        )

        try:
            pricing_model_name = pricing_model.name
            pricing_model_record_id = pricing_model.id
            pricing_model.delete()
        except ProtectedError as exc:
            raise AuthError(
                "PRICING_MODEL_DELETE_BLOCKED",
                "Pricing model cannot be deleted because it is still referenced by "
                "Projects or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="pricing_model",
            entity_id=pricing_model_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=pricing_model_name,
            reason_text="Pricing model deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _get_scoped_pricing_model(
        current_user: CurrentUser,
        pricing_model_id: int,
    ) -> PricingModelRecord:
        try:
            pricing_model = PricingModelRecord.objects.select_related("office").get(
                id=pricing_model_id
            )
        except PricingModelRecord.DoesNotExist as exc:
            raise AuthError("PRICING_MODEL_NOT_FOUND", "Pricing model not found.", 404) from exc

        _ensure_office_in_scope(
            current_user,
            pricing_model.office_id,
            message="Pricing model is outside your active office.",
        )
        return pricing_model

    @staticmethod
    def _refresh_pricing_model(pricing_model_id: int) -> PricingModelRecord:
        return PricingModelRecord.objects.select_related("office").get(id=pricing_model_id)


class GeneralChargeCodeApprovalRoleManagementService:
    @staticmethod
    def list_approval_roles(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        approval_roles = _apply_status_filter(
            GeneralChargeCodeApprovalRole.objects.select_related("office", "status")
            .prefetch_related(
                "member_assignments__employee__status",
                "member_assignments__status__domain",
                "general_charge_code_assignments__general_charge_code__business_unit",
                "general_charge_code_assignments__general_charge_code__status",
            )
            .filter(office_id=current_user.office_id)
            .order_by("role_code"),
            _parse_status_filter(
                status_code,
                domain_code="GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
            ),
        )
        return [
            _serialize_general_charge_code_approval_role(approval_role)
            for approval_role in approval_roles
        ]

    @staticmethod
    def get_approval_role(current_user: CurrentUser, approval_role_id: int) -> dict:
        _ensure_ts_admin(current_user)
        approval_role = GeneralChargeCodeApprovalRoleManagementService._get_scoped_approval_role(
            current_user,
            approval_role_id,
        )
        return _serialize_general_charge_code_approval_role(approval_role)

    @staticmethod
    @transaction.atomic
    def create_approval_role(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        current_office = _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)

        role_code = str(payload.get("role_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not role_code:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_CODE_REQUIRED",
                "role_code is required.",
                400,
            )
        if not name:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_NAME_REQUIRED",
                "name is required.",
                400,
            )

        _validate_optional_office_payload(
            payload,
            code_prefix="GENERAL_CHARGE_CODE_APPROVAL_ROLE",
            expected_office_id=current_office.id,
            mismatch_message=(
                "General Charge Code approval role office must match your active "
                "office."
            ),
        )

        member_employee_ids = (
            GeneralChargeCodeApprovalRoleManagementService._parse_member_employee_ids(payload)
        )
        GeneralChargeCodeApprovalRoleManagementService._ensure_member_employees_are_assignable(
            current_user,
            member_employee_ids,
        )

        try:
            approval_role = GeneralChargeCodeApprovalRole.objects.create(
                office=current_office,
                role_code=role_code,
                name=name,
                description=description,
                status=_ref_value(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
                    str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_NOT_UNIQUE",
                "Ad-hoc approval role code must be unique within the active office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="general_charge_code_approval_role",
            entity_id=approval_role.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="General Charge Code approval role created by Timesheet Administrator.",
        )

        GeneralChargeCodeApprovalRoleManagementService._replace_member_assignments(
            current_user,
            approval_role,
            actor_employee=actor_employee,
            member_employee_ids=member_employee_ids,
            reason="General Charge Code approval role members updated by Timesheet Administrator.",
        )
        return _serialize_general_charge_code_approval_role(
            GeneralChargeCodeApprovalRoleManagementService._refresh_approval_role(approval_role.id)
        )

    @staticmethod
    @transaction.atomic
    def update_approval_role(
        current_user: CurrentUser,
        approval_role_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        approval_role = GeneralChargeCodeApprovalRoleManagementService._get_scoped_approval_role(
            current_user,
            approval_role_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            approval_role.office,
            out_of_scope_message=(
                "General Charge Code approval role is outside your active office."
            ),
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="GENERAL_CHARGE_CODE_APPROVAL_ROLE",
            expected_office_id=approval_role.office_id,
            immutable_office_id=approval_role.office_id,
            mismatch_message=(
                "General Charge Code approval role office must match the existing office."
            ),
            immutable_message="General Charge Code approval role office cannot be changed.",
        )

        changed_fields: list[tuple[str, str, str]] = []
        is_referenced = approval_role.general_charge_code_assignments.exists()

        if "role_code" in payload:
            new_role_code = str(payload.get("role_code", "")).strip()
            if not new_role_code:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_CODE_REQUIRED",
                    "role_code is required.",
                    400,
                )
            if new_role_code != approval_role.role_code:
                changed_fields.append(("role_code", approval_role.role_code, new_role_code))
                approval_role.role_code = new_role_code

        if "name" in payload:
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_NAME_REQUIRED",
                    "name is required.",
                    400,
                )
            if new_name != approval_role.name:
                changed_fields.append(("name", approval_role.name, new_name))
                approval_role.name = new_name

        if "description" in payload:
            new_description = str(payload.get("description", "")).strip()
            if new_description != approval_role.description:
                changed_fields.append(("description", approval_role.description, new_description))
                approval_role.description = new_description

        if "status_code" in payload:
            new_status = _ref_value(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.value_code != "ACTIVE" and is_referenced:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_INACTIVE_BLOCKED",
                    "Ad-hoc approval roles referenced by General Charge Codes cannot "
                    "be set inactive.",
                    400,
                )
            if new_status.id != approval_role.status_id:
                changed_fields.append(
                    ("status", approval_role.status.value_code, new_status.value_code)
                )
                approval_role.status = new_status

        if changed_fields:
            try:
                approval_role.updated_by = current_user.email
                approval_role.save()
            except IntegrityError as exc:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_NOT_UNIQUE",
                    "Ad-hoc approval role code must be unique within the active office.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="general_charge_code_approval_role",
                entity_id=approval_role.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="General Charge Code approval role updated by Timesheet Administrator.",
            )

        if "member_employee_ids" in payload:
            member_employee_ids = (
                GeneralChargeCodeApprovalRoleManagementService._parse_member_employee_ids(payload)
            )
            GeneralChargeCodeApprovalRoleManagementService._ensure_member_employees_are_assignable(
                current_user,
                member_employee_ids,
            )
            if is_referenced and not member_employee_ids:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBERS_REQUIRED",
                    "Ad-hoc approval roles referenced by General Charge Codes must "
                    "keep at least one active member.",
                    400,
                )
            GeneralChargeCodeApprovalRoleManagementService._replace_member_assignments(
                current_user,
                approval_role,
                actor_employee=actor_employee,
                member_employee_ids=member_employee_ids,
                reason=(
                    "General Charge Code approval role members updated by Timesheet "
                    "Administrator."
                ),
            )

        return _serialize_general_charge_code_approval_role(
            GeneralChargeCodeApprovalRoleManagementService._refresh_approval_role(
                approval_role.id
            )
        )

    @staticmethod
    @transaction.atomic
    def delete_approval_role(current_user: CurrentUser, approval_role_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        approval_role = GeneralChargeCodeApprovalRoleManagementService._get_scoped_approval_role(
            current_user,
            approval_role_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            approval_role.office,
            out_of_scope_message=(
                "General Charge Code approval role is outside your active office."
            ),
        )

        try:
            approval_role_code = approval_role.role_code
            approval_role_record_id = approval_role.id
            approval_role.delete()
        except ProtectedError as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_DELETE_BLOCKED",
                "General Charge Code approval role cannot be deleted because it is still "
                "referenced by General Charge Codes, pending approvals, or approval history.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="general_charge_code_approval_role",
            entity_id=approval_role_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=approval_role_code,
            reason_text="General Charge Code approval role deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _get_scoped_approval_role(
        current_user: CurrentUser,
        approval_role_id: int,
    ) -> GeneralChargeCodeApprovalRole:
        try:
            approval_role = (
                GeneralChargeCodeApprovalRole.objects.select_related("office", "status")
                .prefetch_related(
                    "member_assignments__employee__status",
                    "member_assignments__status__domain",
                    "general_charge_code_assignments__general_charge_code__business_unit",
                    "general_charge_code_assignments__general_charge_code__status",
                )
                .get(id=approval_role_id)
            )
        except GeneralChargeCodeApprovalRole.DoesNotExist as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_NOT_FOUND",
                "General Charge Code approval role not found.",
                404,
            ) from exc

        _ensure_office_in_scope(
            current_user,
            approval_role.office_id,
            message="General Charge Code approval role is outside your active office.",
        )
        return approval_role

    @staticmethod
    def _refresh_approval_role(approval_role_id: int) -> GeneralChargeCodeApprovalRole:
        return (
            GeneralChargeCodeApprovalRole.objects.select_related("office", "status")
            .prefetch_related(
                "member_assignments__employee__status",
                "member_assignments__status__domain",
                "general_charge_code_assignments__general_charge_code__business_unit",
                "general_charge_code_assignments__general_charge_code__status",
            )
            .get(id=approval_role_id)
        )

    @staticmethod
    def _parse_member_employee_ids(payload: dict) -> list[int]:
        values = payload.get("member_employee_ids", [])
        if values in (None, ""):
            return []
        if not isinstance(values, list):
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBER_INVALID",
                "member_employee_ids must be a list of employee identifiers.",
                400,
            )
        try:
            return sorted({int(value) for value in values if str(value).strip()})
        except (TypeError, ValueError) as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBER_INVALID",
                "member_employee_ids must contain valid employee identifiers.",
                400,
            ) from exc

    @staticmethod
    def _ensure_member_employees_are_assignable(
        current_user: CurrentUser,
        member_employee_ids: list[int],
    ) -> None:
        if not member_employee_ids:
            return
        employees = list(
            Employee.objects.select_related("office", "status").filter(id__in=member_employee_ids)
        )
        if len(employees) != len(member_employee_ids):
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBER_INVALID",
                "One or more selected employees could not be found.",
                400,
            )
        for employee in employees:
            if employee.office_id != current_user.office_id:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBER_OUT_OF_SCOPE",
                    "Selected employees must belong to the active office.",
                    403,
                )
            if employee.status.value_code != "ACTIVE":
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBER_INACTIVE",
                    "Selected employees must be active.",
                    400,
                )

    @staticmethod
    def _replace_member_assignments(
        current_user: CurrentUser,
        approval_role: GeneralChargeCodeApprovalRole,
        *,
        actor_employee: Employee | None,
        member_employee_ids: list[int],
        reason: str,
    ) -> None:
        desired_employee_ids = set(member_employee_ids)
        active_status = _ref_value("ROLE_ASSIGNMENT_STATUS", "ACTIVE")
        inactive_status = _ref_value("ROLE_ASSIGNMENT_STATUS", "INACTIVE")
        active_assignments = list(
            approval_role.member_assignments.select_related("employee", "status", "status__domain")
            .filter(valid_to__isnull=True)
        )
        current_active_employee_ids = {
            assignment.employee_id
            for assignment in active_assignments
            if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
            and assignment.status.value_code == "ACTIVE"
        }

        for assignment in active_assignments:
            if (
                assignment.employee_id not in desired_employee_ids
                and assignment.status.value_code == "ACTIVE"
            ):
                assignment.status = inactive_status
                assignment.valid_to = date.today()
                assignment.updated_by = current_user.email
                assignment.save(update_fields=["status", "valid_to", "updated_by", "updated_at"])
                write_audit_event(
                    action_code="UPDATE",
                    entity_name="general_charge_code_approval_role_assignment",
                    entity_id=assignment.id,
                    actor_employee=actor_employee,
                    actor_email=current_user.email,
                    field_name="employee_id",
                    old_value=assignment.employee.employee_code,
                    new_value="",
                    reason_text=reason,
                )

        for employee_id in sorted(desired_employee_ids - current_active_employee_ids):
            existing_inactive = (
                approval_role.member_assignments.filter(
                    employee_id=employee_id,
                    valid_to=date.today(),
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
                assignment = GeneralChargeCodeApprovalRoleAssignment.objects.create(
                    approval_role=approval_role,
                    employee_id=employee_id,
                    valid_from=date.today(),
                    status=active_status,
                    created_by=current_user.email,
                    updated_by=current_user.email,
                )
            employee = Employee.objects.get(id=employee_id)
            write_audit_event(
                action_code="UPDATE",
                entity_name="general_charge_code_approval_role_assignment",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name="employee_id",
                old_value="",
                new_value=employee.employee_code,
                reason_text=reason,
            )

    @staticmethod
    def _ensure_routing_ready_for_general_charge_code_assignment(
        approval_role: GeneralChargeCodeApprovalRole,
    ) -> None:
        if approval_role.status.value_code != "ACTIVE":
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVER_ROLE_INACTIVE",
                "Selected ad-hoc approver roles must be active.",
                400,
            )
        if not _active_general_charge_code_role_assignments(approval_role):
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVER_ROLE_UNMANNED",
                "Selected ad-hoc approver roles must have at least one active member.",
                400,
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
                "office",
                "charge_type",
                "cost_center",
                "status",
            )
            .prefetch_related(
                "approver_roles__existing_role",
                "approver_roles__approval_role",
                "approver_roles__approval_role__status",
                "approver_roles__approval_role__member_assignments__employee__status",
                "approver_roles__approval_role__member_assignments__status__domain",
            )
            .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
            .filter(office_id=current_user.office_id)
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="GENERAL_CHARGE_CODE_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            business_unit.office,
            out_of_scope_message=(
                "General charge code Business Unit is outside your active office."
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
        _validate_optional_office_payload(
            payload,
            code_prefix="GENERAL_CHARGE_CODE",
            expected_office_id=business_unit.office_id,
            mismatch_message=(
                "General charge code office must match the selected Business Unit office."
            ),
        )
        cost_center = GeneralChargeCodeManagementService._resolve_cost_center(
            current_user,
            business_unit=business_unit,
            cost_center_id=payload.get("cost_center_id"),
            required=True,
        )
        requires_approval_flag = bool(payload.get("requires_approval_flag", False))
        approver_keys = _parse_general_charge_code_approver_keys(payload)
        if requires_approval_flag and not approver_keys:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVER_ROLE_REQUIRED",
                "At least one approver role is required when Requires Approval is enabled.",
                400,
            )

        try:
            general_charge_code = GeneralChargeCodeRecord.objects.create(
                business_unit=business_unit,
                office=business_unit.office,
                code=code,
                name=name,
                charge_type=_ref_value("GENERAL_CHARGE_CODE_TYPE", charge_type_code),
                cost_center=cost_center,
                billable_flag=bool(payload.get("billable_flag", False)),
                requires_approval_flag=requires_approval_flag,
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
        GeneralChargeCodeManagementService._replace_approver_roles(
            current_user,
            general_charge_code,
            actor_employee=actor_employee,
            approver_keys=approver_keys if requires_approval_flag else [],
            reason="General charge code approver roles updated by Timesheet Administrator.",
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
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            general_charge_code_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            general_charge_code.office,
            out_of_scope_message="General charge code is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="GENERAL_CHARGE_CODE",
            expected_office_id=general_charge_code.office_id,
            immutable_office_id=general_charge_code.office_id,
            mismatch_message="General charge code office must match the existing office.",
            immutable_message="General charge code office cannot be changed.",
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

        if "cost_center_id" in payload:
            new_cost_center = GeneralChargeCodeManagementService._resolve_cost_center(
                current_user,
                business_unit=general_charge_code.business_unit,
                cost_center_id=payload.get("cost_center_id"),
                required=True,
            )
            if new_cost_center.id != general_charge_code.cost_center_id:
                changed_fields.append(
                    (
                        "cost_center",
                        general_charge_code.cost_center.cost_center_code,
                        new_cost_center.cost_center_code,
                    )
                )
                general_charge_code.cost_center = new_cost_center

        current_approver_keys = [
            _serialize_general_charge_code_approver_role(approver_role)["key"]
            for approver_role in general_charge_code.approver_roles.all()
        ]
        requested_approver_keys = None
        if "approver_keys" in payload:
            requested_approver_keys = _parse_general_charge_code_approver_keys(payload)

        for field_name in (
            "billable_flag",
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

        final_requires_approval = general_charge_code.requires_approval_flag
        effective_approver_keys = (
            requested_approver_keys
            if requested_approver_keys is not None
            else current_approver_keys
        )
        if final_requires_approval and not effective_approver_keys:
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVER_ROLE_REQUIRED",
                "At least one approver role is required when Requires Approval is enabled.",
                400,
            )

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

        if requested_approver_keys is not None or not final_requires_approval:
            GeneralChargeCodeManagementService._replace_approver_roles(
                current_user,
                general_charge_code,
                actor_employee=actor_employee,
                approver_keys=effective_approver_keys if final_requires_approval else [],
                reason="General charge code approver roles updated by Timesheet Administrator.",
            )

        return _serialize_general_charge_code(
            GeneralChargeCodeManagementService._refresh_general_charge_code(general_charge_code.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_general_charge_code(
        current_user: CurrentUser,
        general_charge_code_id: int,
    ) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            general_charge_code_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            general_charge_code.office,
            out_of_scope_message="General charge code is outside your active office.",
        )

        try:
            general_charge_code_value = general_charge_code.code
            general_charge_code_record_id = general_charge_code.id
            business_unit = general_charge_code.business_unit
            general_charge_code.delete()
        except ProtectedError as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_DELETE_BLOCKED",
                "General charge code cannot be deleted because it is still referenced by "
                "timesheets, approvals, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="general_charge_code",
            entity_id=general_charge_code_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            old_value=general_charge_code_value,
            reason_text="General charge code deleted by Timesheet Administrator.",
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
                "business_unit", "office", "charge_type", "cost_center", "status"
            ).prefetch_related(
                "approver_roles__existing_role",
                "approver_roles__approval_role",
                "approver_roles__approval_role__status",
                "approver_roles__approval_role__member_assignments__employee__status",
                "approver_roles__approval_role__member_assignments__status__domain",
            ).get(id=general_charge_code_id)
        except GeneralChargeCodeRecord.DoesNotExist as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_NOT_FOUND",
                "General charge code not found.",
                404,
            ) from exc

        _ensure_business_units_in_scope(current_user, {general_charge_code.business_unit_id})
        _ensure_office_in_scope(
            current_user,
            general_charge_code.office_id,
            message="General charge code is outside your active office.",
        )
        return general_charge_code

    @staticmethod
    def _refresh_general_charge_code(
        general_charge_code_id: int,
    ) -> GeneralChargeCodeRecord:
        return GeneralChargeCodeRecord.objects.select_related(
            "business_unit", "office", "charge_type", "cost_center", "status"
        ).prefetch_related(
            "approver_roles__existing_role",
            "approver_roles__approval_role",
            "approver_roles__approval_role__status",
            "approver_roles__approval_role__member_assignments__employee__status",
            "approver_roles__approval_role__member_assignments__status__domain",
        ).get(id=general_charge_code_id)

    @staticmethod
    def _replace_approver_roles(
        current_user: CurrentUser,
        general_charge_code: GeneralChargeCodeRecord,
        *,
        actor_employee: Employee | None,
        approver_keys: list[str],
        reason: str,
    ) -> None:
        desired_existing_roles, desired_ad_hoc_roles = (
            GeneralChargeCodeManagementService._resolve_approver_roles(
                current_user,
                office_id=general_charge_code.office_id,
                approver_keys=approver_keys,
            )
        )
        current_mappings = list(
            general_charge_code.approver_roles.select_related("existing_role", "approval_role")
        )
        current_existing_role_codes = {
            mapping.existing_role.value_code
            for mapping in current_mappings
            if mapping.existing_role_id is not None
        }
        current_ad_hoc_role_ids = {
            mapping.approval_role_id
            for mapping in current_mappings
            if mapping.approval_role_id is not None
        }

        desired_existing_role_codes = {role.value_code for role in desired_existing_roles}
        desired_ad_hoc_role_ids = {role.id for role in desired_ad_hoc_roles}

        for mapping in current_mappings:
            if mapping.existing_role_id is not None:
                if mapping.existing_role.value_code in desired_existing_role_codes:
                    continue
                old_value = mapping.existing_role.value_code
            else:
                if mapping.approval_role_id in desired_ad_hoc_role_ids:
                    continue
                old_value = mapping.approval_role.role_code
            mapping_id = mapping.id
            mapping.delete()
            write_audit_event(
                action_code="DELETE",
                entity_name="general_charge_code_approver_role",
                entity_id=mapping_id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=general_charge_code.business_unit,
                old_value=old_value,
                reason_text=reason,
            )

        for role in sorted(
            desired_existing_roles,
            key=lambda existing_role: existing_role.value_code,
        ):
            if role.value_code in current_existing_role_codes:
                continue
            mapping = GeneralChargeCodeApproverRole.objects.create(
                general_charge_code=general_charge_code,
                existing_role=role,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
            write_audit_event(
                action_code="CREATE",
                entity_name="general_charge_code_approver_role",
                entity_id=mapping.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=general_charge_code.business_unit,
                new_value=role.value_code,
                reason_text=reason,
            )

        for approval_role in sorted(desired_ad_hoc_roles, key=lambda role: role.role_code):
            if approval_role.id in current_ad_hoc_role_ids:
                continue
            mapping = GeneralChargeCodeApproverRole.objects.create(
                general_charge_code=general_charge_code,
                approval_role=approval_role,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
            write_audit_event(
                action_code="CREATE",
                entity_name="general_charge_code_approver_role",
                entity_id=mapping.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=general_charge_code.business_unit,
                new_value=approval_role.role_code,
                reason_text=reason,
            )

    @staticmethod
    def _resolve_approver_roles(
        current_user: CurrentUser,
        *,
        office_id: int,
        approver_keys: list[str] | None,
    ) -> tuple[list[RefValue], list[GeneralChargeCodeApprovalRole]]:
        if not approver_keys:
            return [], []

        existing_role_codes: set[str] = set()
        ad_hoc_role_ids: set[int] = set()
        for approver_key in approver_keys:
            key_type, raw_identifier = _decode_general_charge_code_approver_key(approver_key)
            if key_type == "ROLE":
                existing_role_codes.add(raw_identifier)
                continue
            try:
                ad_hoc_role_ids.add(int(raw_identifier))
            except ValueError as exc:
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVER_ROLE_INVALID",
                    f"Unknown approver role identifier: {approver_key}.",
                    400,
                ) from exc

        existing_roles = [
            _ref_value("ROLE_CODE", role_code)
            for role_code in sorted(existing_role_codes)
        ]
        ad_hoc_roles = list(
            GeneralChargeCodeApprovalRole.objects.select_related("status")
            .prefetch_related(
                "member_assignments__employee__status",
                "member_assignments__status__domain",
            )
            .filter(id__in=ad_hoc_role_ids)
        )
        if len(ad_hoc_roles) != len(ad_hoc_role_ids):
            raise AuthError(
                "GENERAL_CHARGE_CODE_APPROVER_ROLE_INVALID",
                "One or more selected ad-hoc approver roles could not be found.",
                400,
            )
        for approval_role in ad_hoc_roles:
            if (
                approval_role.office_id != office_id
                or approval_role.office_id != current_user.office_id
            ):
                raise AuthError(
                    "GENERAL_CHARGE_CODE_APPROVER_ROLE_OUT_OF_SCOPE",
                    "Ad-hoc approver roles must belong to the active office.",
                    403,
                )
            GeneralChargeCodeApprovalRoleManagementService._ensure_routing_ready_for_general_charge_code_assignment(
                approval_role
            )
        return existing_roles, sorted(ad_hoc_roles, key=lambda role: role.role_code)

    @staticmethod
    def _resolve_cost_center(
        current_user: CurrentUser,
        *,
        business_unit: BusinessUnit,
        cost_center_id: object,
        required: bool,
    ) -> CostCenterRecord:
        if not required and cost_center_id in (None, ""):
            raise AuthError(
                "GENERAL_CHARGE_CODE_COST_CENTER_REQUIRED",
                "cost_center_id is required.",
                400,
            )
        parsed_cost_center_id = _parse_required_int(
            cost_center_id,
            code="GENERAL_CHARGE_CODE_COST_CENTER_REQUIRED",
            message="cost_center_id is required.",
        )

        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user,
            parsed_cost_center_id,
        )
        if cost_center.office_id != business_unit.office_id:
            raise AuthError(
                "GENERAL_CHARGE_CODE_COST_CENTER_OFFICE_MISMATCH",
                "Cost Center must belong to the same Office as the selected Business Unit.",
                400,
            )
        return cost_center


class YearlyCalendarManagementService:
    @staticmethod
    def list_yearly_calendars(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        calendars = _apply_status_filter(
            YearlyCalendar.objects.select_related("office", "status")
            .filter(office_id=current_user.office_id)
            .order_by("calendar_year", "calendar_name"),
            _parse_status_filter(status_code, domain_code="CALENDAR_STATUS"),
        )
        return [_serialize_yearly_calendar(calendar) for calendar in calendars]

    @staticmethod
    def get_yearly_calendar(current_user: CurrentUser, yearly_calendar_id: int) -> dict:
        _ensure_ts_admin(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
        return YearlyCalendarManagementService._serialize_yearly_calendar_detail(yearly_calendar)

    @staticmethod
    @transaction.atomic
    def create_yearly_calendar(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        office = _get_current_office(current_user)
        _ensure_scoped_active_office_for_write(
            current_user,
            office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        calendar_year = _parse_required_int(
            payload.get("calendar_year"),
            code="YEARLY_CALENDAR_YEAR_REQUIRED",
            message="calendar_year is required.",
        )
        calendar_name = str(payload.get("calendar_name", "")).strip()
        if not calendar_name:
            raise AuthError(
                "YEARLY_CALENDAR_NAME_REQUIRED",
                "Calendar name is required.",
                400,
            )
        _validate_optional_office_payload(
            payload,
            code_prefix="YEARLY_CALENDAR",
            expected_office_id=office.id,
            mismatch_message="Yearly calendar office must match the active office.",
        )

        try:
            yearly_calendar = YearlyCalendar.objects.create(
                office=office,
                calendar_year=calendar_year,
                calendar_name=calendar_name,
                status=_ref_value(
                    "CALENDAR_STATUS",
                    str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "YEARLY_CALENDAR_NOT_UNIQUE",
                "Only one yearly calendar can exist for the same year within the Office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="yearly_calendar",
            entity_id=yearly_calendar.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Yearly calendar created by Timesheet Administrator.",
        )
        return _serialize_yearly_calendar(
            YearlyCalendarManagementService._refresh_yearly_calendar(yearly_calendar.id)
        )

    @staticmethod
    @transaction.atomic
    def update_yearly_calendar(
        current_user: CurrentUser,
        yearly_calendar_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="YEARLY_CALENDAR",
            expected_office_id=yearly_calendar.office_id,
            immutable_office_id=yearly_calendar.office_id,
            mismatch_message="Yearly calendar office must match the existing office.",
            immutable_message="Yearly calendar office cannot be changed.",
        )

        changed_fields: list[tuple[str, str, str]] = []

        if "calendar_year" in payload:
            new_calendar_year = _parse_required_int(
                payload.get("calendar_year"),
                code="YEARLY_CALENDAR_YEAR_REQUIRED",
                message="calendar_year is required.",
            )
            if new_calendar_year != yearly_calendar.calendar_year:
                changed_fields.append(
                    ("calendar_year", str(yearly_calendar.calendar_year), str(new_calendar_year))
                )
                yearly_calendar.calendar_year = new_calendar_year

        if "calendar_name" in payload:
            new_calendar_name = str(payload.get("calendar_name", "")).strip()
            if not new_calendar_name:
                raise AuthError(
                    "YEARLY_CALENDAR_NAME_REQUIRED",
                    "Calendar name is required.",
                    400,
                )
            if new_calendar_name != yearly_calendar.calendar_name:
                changed_fields.append(
                    ("calendar_name", yearly_calendar.calendar_name, new_calendar_name)
                )
                yearly_calendar.calendar_name = new_calendar_name

        if "status_code" in payload:
            new_status = _ref_value("CALENDAR_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != yearly_calendar.status_id:
                changed_fields.append(
                    ("status", yearly_calendar.status.value_code, new_status.value_code)
                )
                yearly_calendar.status = new_status

        if changed_fields:
            try:
                yearly_calendar.updated_by = current_user.email
                yearly_calendar.save()
            except IntegrityError as exc:
                raise AuthError(
                    "YEARLY_CALENDAR_NOT_UNIQUE",
                    "Only one yearly calendar can exist for the same year within the Office.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="yearly_calendar",
                entity_id=yearly_calendar.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Yearly calendar updated by Timesheet Administrator.",
            )
        return _serialize_yearly_calendar(
            YearlyCalendarManagementService._refresh_yearly_calendar(yearly_calendar.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_yearly_calendar(current_user: CurrentUser, yearly_calendar_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )

        try:
            calendar_label = f"{yearly_calendar.calendar_year} - {yearly_calendar.calendar_name}"
            calendar_id = yearly_calendar.id
            yearly_calendar.delete()
        except ProtectedError as exc:
            raise AuthError(
                "YEARLY_CALENDAR_DELETE_BLOCKED",
                "Yearly calendar cannot be deleted because it is still referenced by "
                "employees, period rules, special days, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="yearly_calendar",
            entity_id=calendar_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=calendar_label,
            reason_text="Yearly calendar deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _serialize_yearly_calendar_detail(yearly_calendar: YearlyCalendar) -> dict:
        special_days = list(
            CalendarSpecialDayRecord.objects.select_related(
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "day_type",
                "default_general_charge_code",
                "status",
            )
            .filter(yearly_calendar_id=yearly_calendar.id)
            .order_by("special_date")
        )
        active_special_days = [
            special_day for special_day in special_days if special_day.status.value_code == "ACTIVE"
        ]
        active_holiday_codes = {"NATIONAL_HOLIDAY", "LOCAL_HOLIDAY"}
        weekday_count = 0
        week_starts: set[date] = set()
        first_day = date(yearly_calendar.calendar_year, 1, 1)
        last_day = date(yearly_calendar.calendar_year, 12, 31)
        current_day = first_day
        while current_day <= last_day:
            if current_day.weekday() < 5:
                weekday_count += 1
                week_starts.add(current_day - timedelta(days=current_day.weekday()))
            current_day += timedelta(days=1)

        active_weekday_special_days = sum(
            1 for special_day in active_special_days if special_day.special_date.weekday() < 5
        )

        return {
            **_serialize_yearly_calendar(yearly_calendar),
            "special_days": [
                _serialize_calendar_special_day(special_day) for special_day in special_days
            ],
            "summary": {
                "week_count": len(week_starts),
                "weekday_count": weekday_count,
                "active_holiday_count": sum(
                    1
                    for special_day in active_special_days
                    if special_day.day_type.value_code in active_holiday_codes
                ),
                "active_timia_other_count": sum(
                    1
                    for special_day in active_special_days
                    if special_day.day_type.value_code not in active_holiday_codes
                ),
                "net_working_day_count": weekday_count - active_weekday_special_days,
            },
            "period_rule_count": yearly_calendar.period_rules.count(),
        }

    @staticmethod
    def _get_scoped_yearly_calendar(
        current_user: CurrentUser, yearly_calendar_id: int
    ) -> YearlyCalendar:
        try:
            yearly_calendar = YearlyCalendar.objects.select_related(
                "office",
                "office__status",
                "status",
            ).get(id=yearly_calendar_id)
        except YearlyCalendar.DoesNotExist as exc:
            raise AuthError("YEARLY_CALENDAR_NOT_FOUND", "Yearly calendar not found.", 404) from exc
        _ensure_office_in_scope(
            current_user,
            yearly_calendar.office_id,
            message="Yearly calendar is outside your active office.",
        )
        return yearly_calendar

    @staticmethod
    def _refresh_yearly_calendar(yearly_calendar_id: int) -> YearlyCalendar:
        return YearlyCalendar.objects.select_related("office", "status").get(id=yearly_calendar_id)


class CalendarSpecialDayManagementService:
    @staticmethod
    def list_special_days(
        current_user: CurrentUser,
        *,
        yearly_calendar_id: int | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        special_days = CalendarSpecialDayRecord.objects.select_related(
            "yearly_calendar",
            "yearly_calendar__office",
            "yearly_calendar__status",
            "day_type",
            "default_general_charge_code",
            "status",
        ).filter(yearly_calendar__office_id=current_user.office_id)
        if yearly_calendar_id is not None:
            special_days = special_days.filter(yearly_calendar_id=yearly_calendar_id)
        special_days = special_days.order_by("yearly_calendar__calendar_year", "special_date")
        return [_serialize_calendar_special_day(special_day) for special_day in special_days]

    @staticmethod
    def get_special_day(current_user: CurrentUser, special_day_id: int) -> dict:
        _ensure_ts_admin(current_user)
        special_day = CalendarSpecialDayManagementService._get_scoped_special_day(
            current_user,
            special_day_id,
        )
        return _serialize_calendar_special_day(special_day)

    @staticmethod
    @transaction.atomic
    def create_special_day(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_SPECIAL_DAY_CALENDAR_REQUIRED",
                message="yearly_calendar_id is required.",
            ),
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        special_date = _parse_iso_date(
            payload.get("special_date"),
            code="CALENDAR_SPECIAL_DAY_DATE_REQUIRED",
            message="special_date must be a valid ISO date.",
        )
        CalendarSpecialDayManagementService._validate_calendar_year(
            yearly_calendar.calendar_year,
            special_date=special_date,
        )
        day_type = _ref_value(
            "SPECIAL_DAY_TYPE",
            str(payload.get("day_type_code", "")).strip(),
        )
        default_general_charge_code = (
            CalendarSpecialDayManagementService._resolve_default_general_charge_code(
                current_user,
                yearly_calendar=yearly_calendar,
                default_general_charge_code_id=payload.get("default_general_charge_code_id"),
            )
        )
        try:
            special_day = CalendarSpecialDay.objects.create(
                yearly_calendar=yearly_calendar,
                special_date=special_date,
                day_type=day_type,
                name=_build_special_day_name(day_type, special_date),
                default_general_charge_code=default_general_charge_code,
                status=_ref_value(
                    "SPECIAL_DAY_STATUS",
                    str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_NOT_UNIQUE",
                "A special day already exists for that date in the selected calendar.",
                400,
            ) from exc
        write_audit_event(
            action_code="CREATE",
            entity_name="calendar_special_day",
            entity_id=special_day.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Calendar special day created by Timesheet Administrator.",
        )
        return _serialize_calendar_special_day(
            CalendarSpecialDayManagementService._refresh_special_day(special_day.id)
        )

    @staticmethod
    @transaction.atomic
    def update_special_day(current_user: CurrentUser, special_day_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        special_day = CalendarSpecialDayManagementService._get_scoped_special_day(
            current_user,
            special_day_id,
        )
        yearly_calendar = special_day.yearly_calendar
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Calendar special day is outside your active office.",
        )
        if (
            "yearly_calendar_id" in payload
            and _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_SPECIAL_DAY_CALENDAR_REQUIRED",
                message="yearly_calendar_id must be a valid calendar identifier.",
            )
            != special_day.yearly_calendar_id
        ):
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_CALENDAR_IMMUTABLE",
                "Calendar special day calendar cannot be changed.",
                400,
            )

        changed_fields: list[tuple[str, str, str]] = []
        updated_day_type = special_day.day_type
        updated_special_date = special_day.special_date

        if "special_date" in payload:
            updated_special_date = _parse_iso_date(
                payload.get("special_date"),
                code="CALENDAR_SPECIAL_DAY_DATE_REQUIRED",
                message="special_date must be a valid ISO date.",
            )
            CalendarSpecialDayManagementService._validate_calendar_year(
                yearly_calendar.calendar_year,
                special_date=updated_special_date,
            )
            if updated_special_date != special_day.special_date:
                changed_fields.append(
                    (
                        "special_date",
                        special_day.special_date.isoformat(),
                        updated_special_date.isoformat(),
                    )
                )
                special_day.special_date = updated_special_date

        if "day_type_code" in payload:
            updated_day_type = _ref_value(
                "SPECIAL_DAY_TYPE",
                str(payload.get("day_type_code", "")).strip(),
            )
            if updated_day_type.id != special_day.day_type_id:
                changed_fields.append(
                    (
                        "day_type",
                        special_day.day_type.value_code,
                        updated_day_type.value_code,
                    )
                )
                special_day.day_type = updated_day_type

        if "status_code" in payload:
            new_status = _ref_value(
                "SPECIAL_DAY_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != special_day.status_id:
                changed_fields.append(
                    ("status", special_day.status.value_code, new_status.value_code)
                )
                special_day.status = new_status

        if "default_general_charge_code_id" in payload:
            new_default_general_charge_code = (
                CalendarSpecialDayManagementService._resolve_default_general_charge_code(
                    current_user,
                    yearly_calendar=yearly_calendar,
                    default_general_charge_code_id=payload.get("default_general_charge_code_id"),
                )
            )
            old_code = (
                special_day.default_general_charge_code.code
                if special_day.default_general_charge_code_id is not None
                else ""
            )
            new_code = (
                new_default_general_charge_code.code
                if new_default_general_charge_code is not None
                else ""
            )
            if special_day.default_general_charge_code_id != (
                new_default_general_charge_code.id if new_default_general_charge_code else None
            ):
                changed_fields.append(("default_general_charge_code", old_code, new_code))
                special_day.default_general_charge_code = new_default_general_charge_code

        updated_name = _build_special_day_name(updated_day_type, updated_special_date)
        if updated_name != special_day.name:
            changed_fields.append(("name", special_day.name, updated_name))
            special_day.name = updated_name

        if changed_fields:
            try:
                special_day.updated_by = current_user.email
                special_day.save()
            except IntegrityError as exc:
                raise AuthError(
                    "CALENDAR_SPECIAL_DAY_NOT_UNIQUE",
                    "A special day already exists for that date in the selected calendar.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="calendar_special_day",
                entity_id=special_day.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Calendar special day updated by Timesheet Administrator.",
            )
        return _serialize_calendar_special_day(
            CalendarSpecialDayManagementService._refresh_special_day(special_day.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_special_day(current_user: CurrentUser, special_day_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        special_day = CalendarSpecialDayManagementService._get_scoped_special_day(
            current_user,
            special_day_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            special_day.yearly_calendar.office,
            out_of_scope_message="Calendar special day is outside your active office.",
        )
        try:
            special_day_label = (
                f"{special_day.special_date.isoformat()} {special_day.day_type.value_code}"
            )
            special_day_record_id = special_day.id
            special_day.delete()
        except ProtectedError as exc:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_DELETE_BLOCKED",
                "Calendar special day cannot be deleted because it is still referenced by "
                "other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="calendar_special_day",
            entity_id=special_day_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=special_day_label,
            reason_text="Calendar special day deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _validate_calendar_year(calendar_year: int, *, special_date: date) -> None:
        if special_date.year != calendar_year:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_YEAR_MISMATCH",
                "Special day date must belong to the selected calendar year.",
                400,
            )

    @staticmethod
    def _resolve_default_general_charge_code(
        current_user: CurrentUser,
        *,
        yearly_calendar: YearlyCalendar,
        default_general_charge_code_id: object,
    ) -> GeneralChargeCodeRecord | None:
        if default_general_charge_code_id in (None, ""):
            return None
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            _parse_required_int(
                default_general_charge_code_id,
                code="CALENDAR_SPECIAL_DAY_GENERAL_CHARGE_CODE_INVALID",
                message=(
                    "default_general_charge_code_id must be a valid general charge code identifier."
                ),
            ),
        )
        if general_charge_code.office_id != yearly_calendar.office_id:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_GENERAL_CHARGE_CODE_OFFICE_MISMATCH",
                "Default general charge code must belong to the same Office.",
                400,
            )
        return general_charge_code

    @staticmethod
    def _get_scoped_special_day(
        current_user: CurrentUser,
        special_day_id: int,
    ) -> CalendarSpecialDayRecord:
        try:
            special_day = CalendarSpecialDayRecord.objects.select_related(
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "day_type",
                "default_general_charge_code",
                "status",
            ).get(id=special_day_id)
        except CalendarSpecialDayRecord.DoesNotExist as exc:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_NOT_FOUND",
                "Calendar special day not found.",
                404,
            ) from exc
        _ensure_office_in_scope(
            current_user,
            special_day.yearly_calendar.office_id,
            message="Calendar special day is outside your active office.",
        )
        return special_day

    @staticmethod
    def _refresh_special_day(special_day_id: int) -> CalendarSpecialDayRecord:
        return CalendarSpecialDayRecord.objects.select_related(
            "yearly_calendar",
            "yearly_calendar__office",
            "yearly_calendar__status",
            "day_type",
            "default_general_charge_code",
            "status",
        ).get(id=special_day_id)


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
                "business_unit",
                "office",
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "status",
            )
            .filter(office_id=current_user.office_id)
            .filter(
                Q(business_unit_id__in=current_user.scoped_business_unit_ids)
                | Q(business_unit_id__isnull=True)
            )
            .order_by(
                "yearly_calendar__calendar_year",
                "yearly_calendar__calendar_name",
                "business_unit__bu_code",
                "effective_from",
            ),
            _parse_status_filter(status_code, domain_code="CALENDAR_PERIOD_STATUS"),
        )
        return [_serialize_calendar_period_rule(period_rule) for period_rule in period_rules]

    @staticmethod
    def list_yearly_calendars(current_user: CurrentUser) -> list[dict]:
        return YearlyCalendarManagementService.list_yearly_calendars(current_user)

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
    def delete_period_rule(current_user: CurrentUser, period_rule_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            period_rule.office,
            out_of_scope_message="Calendar Period Rule is outside your active office.",
        )

        try:
            period_rule_label = (
                f"{period_rule.yearly_calendar.calendar_name} "
                f"{period_rule.effective_from.isoformat()} - {period_rule.effective_to.isoformat()}"
            )
            period_rule_record_id = period_rule.id
            period_rule.delete()
        except ProtectedError as exc:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_DELETE_BLOCKED",
                "Calendar Period Rule cannot be deleted because it is still referenced by "
                "other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="calendar_period_rule",
            entity_id=period_rule_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=period_rule_label,
            reason_text="Calendar period rule deleted by Timesheet Administrator.",
        )

    @staticmethod
    @transaction.atomic
    def create_period_rule(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = CalendarPeriodRuleManagementService._get_scoped_yearly_calendar(
            current_user,
            _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED",
                message="yearly_calendar_id is required.",
            ),
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        business_unit = _get_scoped_business_unit(
            current_user,
            _parse_required_int(
                payload.get("business_unit_id"),
                code="CALENDAR_PERIOD_RULE_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id is required.",
            ),
        )
        if business_unit.office_id != yearly_calendar.office_id:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_BUSINESS_UNIT_OFFICE_MISMATCH",
                "Business Unit must belong to the same Office as the selected yearly calendar.",
                400,
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
            business_unit.id,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        saturday_max_hours, sunday_max_hours = _validate_weekend_hours(None, payload)
        _validate_optional_office_payload(
            payload,
            code_prefix="CALENDAR_PERIOD_RULE",
            expected_office_id=yearly_calendar.office_id,
            mismatch_message=(
                "Calendar Period Rule office must match the selected yearly calendar office."
            ),
        )
        period_rule = CalendarPeriodRule.objects.create(
            yearly_calendar=yearly_calendar,
            business_unit=business_unit,
            office=yearly_calendar.office,
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
            working_on_saturdays_flag=_parse_bool(payload.get("working_on_saturdays_flag")),
            working_on_sundays_flag=_parse_bool(payload.get("working_on_sundays_flag")),
            saturday_max_hours=saturday_max_hours,
            sunday_max_hours=sunday_max_hours,
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
            reason_text="Calendar period rule created by Timesheet Administrator.",
        )
        return _serialize_calendar_period_rule(
            CalendarPeriodRuleManagementService._refresh_period_rule(period_rule.id)
        )

    @staticmethod
    @transaction.atomic
    def update_period_rule(current_user: CurrentUser, period_rule_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            period_rule.office,
            out_of_scope_message="Calendar Period Rule is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="CALENDAR_PERIOD_RULE",
            expected_office_id=period_rule.office_id,
            immutable_office_id=period_rule.office_id,
            mismatch_message="Calendar Period Rule office must match the existing office.",
            immutable_message="Calendar Period Rule office cannot be changed.",
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
        proposed_business_unit = period_rule.business_unit
        if "business_unit_id" in payload:
            proposed_business_unit = _get_scoped_business_unit(
                current_user,
                _parse_required_int(
                    payload.get("business_unit_id"),
                    code="CALENDAR_PERIOD_RULE_BUSINESS_UNIT_REQUIRED",
                    message="business_unit_id must be a valid Business Unit identifier.",
                ),
            )
        if proposed_business_unit is None:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_BUSINESS_UNIT_REQUIRED",
                "business_unit_id is required.",
                400,
            )
        if proposed_business_unit.office_id != period_rule.office_id:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_BUSINESS_UNIT_OFFICE_MISMATCH",
                "Business Unit must belong to the same Office as the selected yearly calendar.",
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
            proposed_business_unit.id,
            effective_from=proposed_effective_from,
            effective_to=proposed_effective_to,
            exclude_rule_id=period_rule.id,
        )
        saturday_max_hours, sunday_max_hours = _validate_weekend_hours(period_rule, payload)
        changed_fields: list[tuple[str, str, str]] = []
        if period_rule.business_unit_id != proposed_business_unit.id:
            changed_fields.append(
                (
                    "business_unit",
                    period_rule.business_unit.bu_code if period_rule.business_unit_id else "",
                    proposed_business_unit.bu_code,
                )
            )
            period_rule.business_unit = proposed_business_unit
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
        for flag_name in ("working_on_saturdays_flag", "working_on_sundays_flag"):
            if flag_name in payload:
                new_flag_value = _parse_bool(payload.get(flag_name))
                if getattr(period_rule, flag_name) != new_flag_value:
                    changed_fields.append(
                        (
                            flag_name,
                            str(getattr(period_rule, flag_name)),
                            str(new_flag_value),
                        )
                    )
                    setattr(period_rule, flag_name, new_flag_value)
        for field_name, new_value in (
            ("saturday_max_hours", saturday_max_hours),
            ("sunday_max_hours", sunday_max_hours),
        ):
            if getattr(period_rule, field_name) != new_value:
                changed_fields.append(
                    (field_name, str(getattr(period_rule, field_name)), str(new_value))
                )
                setattr(period_rule, field_name, new_value)
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
        business_unit_id: int | None,
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
        if business_unit_id is None:
            overlaps = overlaps.filter(business_unit_id__isnull=True)
        else:
            overlaps = overlaps.filter(business_unit_id=business_unit_id)
        if exclude_rule_id is not None:
            overlaps = overlaps.exclude(id=exclude_rule_id)
        if overlaps.exists():
            raise AuthError(
                "CALENDAR_PERIOD_RULE_OVERLAP",
                (
                    "Calendar Period Rules cannot overlap within the same "
                    "Business Unit and yearly calendar."
                ),
                400,
            )

    @staticmethod
    def _get_scoped_yearly_calendar(
        current_user: CurrentUser, yearly_calendar_id: int
    ) -> YearlyCalendar:
        return YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )

    @staticmethod
    def _get_scoped_period_rule(
        current_user: CurrentUser, period_rule_id: int
    ) -> CalendarPeriodRule:
        try:
            period_rule = CalendarPeriodRule.objects.select_related(
                "business_unit",
                "office",
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "status",
            ).get(id=period_rule_id)
        except CalendarPeriodRule.DoesNotExist as exc:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_NOT_FOUND", "Calendar Period Rule not found.", 404
            ) from exc
        _ensure_office_in_scope(
            current_user,
            period_rule.office_id,
            message="Calendar Period Rule is outside your active office.",
        )
        if period_rule.business_unit_id is not None:
            _ensure_business_units_in_scope(current_user, {period_rule.business_unit_id})
        return period_rule

    @staticmethod
    def _refresh_period_rule(period_rule_id: int) -> CalendarPeriodRule:
        return CalendarPeriodRule.objects.select_related(
            "business_unit",
            "office",
            "yearly_calendar",
            "yearly_calendar__office",
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
        _ensure_ts_admin_or_project_owner(current_user)
        projects = Project.objects.select_related(
            "business_unit",
            "office",
            "project_owner_employee",
            "project_manager_employee",
            "client",
            "internal_category",
            "cost_center",
            "pricing_model",
            "status",
        ).filter(
            business_unit_id__in=current_user.scoped_business_unit_ids,
            office_id=current_user.office_id,
        )
        if not current_user.is_ts_admin:
            projects = projects.filter(project_owner_employee_id=current_user.employee_id)
        projects = _apply_status_filter(
            projects.order_by("business_unit__bu_code", "project_code"),
            _parse_status_filter(status_code, domain_code="PROJECT_STATUS"),
        )
        return [_serialize_project(project) for project in projects]

    @staticmethod
    def get_project(current_user: CurrentUser, project_id: int) -> dict:
        _ensure_ts_admin_or_project_owner(current_user)
        project = ProjectManagementService._get_scoped_project(current_user, project_id)
        return _serialize_project(project)

    @staticmethod
    @transaction.atomic
    def create_project(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin_or_project_owner(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        business_unit = _get_scoped_business_unit(
            current_user,
            _parse_required_int(
                payload.get("business_unit_id"),
                code="PROJECT_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id is required.",
            ),
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            business_unit.office,
            out_of_scope_message="Project Business Unit is outside your active office.",
        )
        project_code = str(payload.get("project_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not project_code:
            raise AuthError("PROJECT_CODE_REQUIRED", "Project code is required.", 400)
        if not name:
            raise AuthError("PROJECT_NAME_REQUIRED", "Project name is required.", 400)
        project_owner = ProjectManagementService._resolve_project_owner_for_write(
            current_user,
            employee_id=payload.get("project_owner_employee_id"),
            business_unit_id=business_unit.id,
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
        pricing_model = ProjectManagementService._resolve_project_pricing_model(
            current_user,
            business_unit_id=business_unit.id,
            pricing_model_id=payload.get("pricing_model_id"),
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
        _validate_optional_office_payload(
            payload,
            code_prefix="PROJECT",
            expected_office_id=business_unit.office_id,
            mismatch_message="Project office must match the selected Business Unit office.",
        )
        try:
            project = Project.objects.create(
                business_unit=business_unit,
                office=business_unit.office,
                project_code=project_code,
                name=name,
                description=description,
                project_owner_employee=project_owner,
                project_manager_employee=project_manager,
                client=client,
                internal_category=internal_category,
                cost_center=cost_center,
                pricing_model=pricing_model,
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
            reason_text="Project created by authorized project administration.",
        )
        return _serialize_project(ProjectManagementService._refresh_project(project.id))

    @staticmethod
    @transaction.atomic
    def update_project(current_user: CurrentUser, project_id: int, payload: dict) -> dict:
        _ensure_ts_admin_or_project_owner(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        project = ProjectManagementService._get_scoped_project(current_user, project_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            project.office,
            out_of_scope_message="Project is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="PROJECT",
            expected_office_id=project.office_id,
            immutable_office_id=project.office_id,
            mismatch_message="Project office must match the project office.",
            immutable_message="Project office cannot be changed.",
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
        if current_user.is_ts_admin and "project_owner_employee_id" in payload:
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
        if "pricing_model_id" in payload:
            new_pricing_model = ProjectManagementService._resolve_project_pricing_model(
                current_user,
                business_unit_id=project.business_unit_id,
                pricing_model_id=payload.get("pricing_model_id"),
            )
            if new_pricing_model.id != project.pricing_model_id:
                changed_fields.append(
                    ("pricing_model", project.pricing_model.name, new_pricing_model.name)
                )
                project.pricing_model = new_pricing_model
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
                reason_text="Project updated by authorized project administration.",
            )
        return _serialize_project(ProjectManagementService._refresh_project(project.id))

    @staticmethod
    @transaction.atomic
    def delete_project(current_user: CurrentUser, project_id: int) -> None:
        _ensure_ts_admin_or_project_owner(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        project = ProjectManagementService._get_scoped_project(current_user, project_id)
        _ensure_scoped_active_office_for_write(
            current_user,
            project.office,
            out_of_scope_message="Project is outside your active office.",
        )

        try:
            project_code = project.project_code
            project_record_id = project.id
            business_unit = project.business_unit
            project.delete()
        except ProtectedError as exc:
            raise AuthError(
                "PROJECT_DELETE_BLOCKED",
                "Project cannot be deleted because it is still referenced by "
                "assignments, timesheets, approvals, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="project",
            entity_id=project_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            old_value=project_code,
            reason_text="Project deleted by authorized project administration.",
        )

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
        try:
            employee = Employee.objects.select_related("office", "status").get(
                id=resolved_employee_id
            )
        except Employee.DoesNotExist as exc:
            raise AuthError("EMPLOYEE_NOT_FOUND", "Employee not found.", 404) from exc
        _ensure_office_in_scope(
            current_user,
            employee.office_id,
            message="Selected employee is outside your active office.",
        )
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
    def _resolve_project_owner_for_write(
        current_user: CurrentUser,
        *,
        employee_id: object,
        business_unit_id: int,
    ) -> Employee:
        if current_user.is_ts_admin:
            return ProjectManagementService._resolve_project_employee(
                current_user,
                employee_id=employee_id,
                business_unit_id=business_unit_id,
                required_role_code="PROJECT_OWNER",
                code_prefix="PROJECT_OWNER",
            )
        return ProjectManagementService._resolve_project_employee(
            current_user,
            employee_id=current_user.employee_id,
            business_unit_id=business_unit_id,
            required_role_code="PROJECT_OWNER",
            code_prefix="PROJECT_OWNER",
        )

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
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        if client.office_id != business_unit.office_id:
            raise AuthError(
                "PROJECT_CLIENT_OFFICE_MISMATCH",
                "Project client must belong to the same Office.",
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
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        if cost_center.office_id != business_unit.office_id:
            raise AuthError(
                "PROJECT_COST_CENTER_OFFICE_MISMATCH",
                "Project cost center must belong to the same Office.",
                400,
            )
        return cost_center

    @staticmethod
    def _resolve_project_pricing_model(
        current_user: CurrentUser,
        *,
        business_unit_id: int,
        pricing_model_id: object,
    ) -> PricingModelRecord:
        pricing_model = PricingModelManagementService._get_scoped_pricing_model(
            current_user,
            _parse_required_int(
                pricing_model_id,
                code="PROJECT_PRICING_MODEL_REQUIRED",
                message="pricing_model_id is required.",
            ),
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)
        if pricing_model.office_id != business_unit.office_id:
            raise AuthError(
                "PROJECT_PRICING_MODEL_OFFICE_MISMATCH",
                "Project pricing model must belong to the same Office.",
                400,
            )
        return pricing_model

    @staticmethod
    def _get_scoped_project(current_user: CurrentUser, project_id: int) -> Project:
        try:
            project = Project.objects.select_related(
                "business_unit",
                "office",
                "project_owner_employee",
                "project_manager_employee",
                "client",
                "internal_category",
                "cost_center",
                "pricing_model",
                "status",
            ).get(id=project_id)
        except Project.DoesNotExist as exc:
            raise AuthError("PROJECT_NOT_FOUND", "Project not found.", 404) from exc
        _ensure_business_units_in_scope(current_user, {project.business_unit_id})
        _ensure_office_in_scope(
            current_user,
            project.office_id,
            message="Project is outside your active office.",
        )
        if current_user.is_ts_admin:
            return project
        if (
            current_user.has_role("PROJECT_OWNER")
            and project.project_owner_employee_id == current_user.employee_id
        ):
            return project
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "Project is outside your owned-project scope.",
            403,
        )
        return project

    @staticmethod
    def _refresh_project(project_id: int) -> Project:
        return Project.objects.select_related(
            "business_unit",
            "office",
            "project_owner_employee",
            "project_manager_employee",
            "client",
            "internal_category",
            "cost_center",
            "pricing_model",
            "status",
        ).get(id=project_id)


class ProjectAssignmentManagementService:
    @staticmethod
    def list_assignments(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        assignments = ProjectAssignment.objects.select_related(
            "project",
            "project__office",
            "project__business_unit",
            "employee",
            "employee__primary_business_unit",
            "status",
        ).filter(
            project__business_unit_id__in=current_user.scoped_business_unit_ids,
            project__office_id=current_user.office_id,
        )
        if not current_user.is_ts_admin:
            assignments = assignments.filter(
                Q(project__project_owner_employee_id=current_user.employee_id)
                | Q(project__project_manager_employee_id=current_user.employee_id)
            )
        assignments = _apply_status_filter(
            assignments.order_by(
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
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        assignment = ProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        return _serialize_project_assignment(assignment)

    @staticmethod
    @transaction.atomic
    def create_assignment(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        project = ProjectAssignmentManagementService._get_scoped_project_for_assignment_management(
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
            reason_text="Project assignment created by authorized project administration.",
        )
        return _serialize_project_assignment(
            ProjectAssignmentManagementService._refresh_assignment(assignment.id)
        )

    @staticmethod
    @transaction.atomic
    def update_assignment(current_user: CurrentUser, assignment_id: int, payload: dict) -> dict:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        assignment = ProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            assignment.project.office,
            out_of_scope_message="Project assignment is outside your active office.",
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
                reason_text="Project assignment updated by authorized project administration.",
            )
        return _serialize_project_assignment(
            ProjectAssignmentManagementService._refresh_assignment(assignment.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_assignment(current_user: CurrentUser, assignment_id: int) -> None:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        assignment = ProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            assignment.project.office,
            out_of_scope_message="Project assignment is outside your active office.",
        )

        try:
            assignment_record_id = assignment.id
            assignment_label = (
                f"{assignment.project.project_code}:{assignment.employee.employee_code}:"
                f"{assignment.assignment_start_date.isoformat()}"
            )
            business_unit = assignment.project.business_unit
            assignment.delete()
        except ProtectedError as exc:
            raise AuthError(
                "PROJECT_ASSIGNMENT_DELETE_BLOCKED",
                "Project assignment cannot be deleted because it is still referenced by "
                "other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="project_assignment",
            entity_id=assignment_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            old_value=assignment_label,
            reason_text="Project assignment deleted by authorized project administration.",
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
                "project__office",
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
        _ensure_office_in_scope(
            current_user,
            assignment.project.office_id,
            message="Project assignment is outside your active office.",
        )
        if current_user.is_ts_admin:
            return assignment
        if (
            current_user.has_role("PROJECT_OWNER")
            and assignment.project.project_owner_employee_id == current_user.employee_id
        ):
            return assignment
        if (
            current_user.has_role("PROJECT_MANAGER")
            and assignment.project.project_manager_employee_id == current_user.employee_id
        ):
            return assignment
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "Project assignment is outside your owned or managed project scope.",
            403,
        )
        return assignment

    @staticmethod
    def _get_scoped_project_for_assignment_management(
        current_user: CurrentUser,
        project_id: int,
    ) -> Project:
        try:
            project = Project.objects.select_related(
                "business_unit",
                "office",
                "project_owner_employee",
                "project_manager_employee",
                "status",
            ).get(id=project_id)
        except Project.DoesNotExist as exc:
            raise AuthError("PROJECT_NOT_FOUND", "Project not found.", 404) from exc
        _ensure_business_units_in_scope(current_user, {project.business_unit_id})
        _ensure_office_in_scope(
            current_user,
            project.office_id,
            message="Project is outside your active office.",
        )
        if current_user.is_ts_admin:
            return project
        if (
            current_user.has_role("PROJECT_OWNER")
            and project.project_owner_employee_id == current_user.employee_id
        ):
            return project
        if (
            current_user.has_role("PROJECT_MANAGER")
            and project.project_manager_employee_id == current_user.employee_id
        ):
            return project
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "Project is outside your owned or managed project scope.",
            403,
        )

    @staticmethod
    def _refresh_assignment(assignment_id: int) -> ProjectAssignment:
        return ProjectAssignment.objects.select_related(
            "project",
            "project__office",
            "project__business_unit",
            "employee",
            "employee__primary_business_unit",
            "status",
        ).get(id=assignment_id)
