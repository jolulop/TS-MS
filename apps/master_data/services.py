from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from apps.audit.services import write_audit_event
from apps.auth.constants import ACTIVE_COUNTRY_STATUS
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import canonicalize_email
from apps.common.parsing import (
    apply_status_filter as _apply_status_filter,
)
from apps.common.parsing import (
    parse_bool as _parse_bool,
)
from apps.common.parsing import (
    parse_decimal as _parse_decimal,
)
from apps.common.parsing import (
    parse_iso_date as _parse_iso_date,
)
from apps.common.parsing import (
    parse_optional_iso_date as _parse_optional_iso_date,
)
from apps.common.parsing import (
    parse_required_int as _parse_required_int,
)
from apps.common.parsing import (
    parse_status_filter as _parse_status_filter,
)
from apps.common.reference_data import get_ref_value as _ref_value
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    Country,
    CrossOfficeProjectAssignment,
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
from apps.timesheets.models import ApprovalItem, WeeklyTimesheet


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


def _refresh_employee_for_transfer(employee_id: int) -> Employee:
    return (
        Employee.objects.select_related(
            "primary_business_unit",
            "office",
            "office__status",
            "status",
        )
        .prefetch_related(
            "business_unit_assignments__business_unit",
            "business_unit_assignments__status__domain",
            "role_assignments__role",
            "role_assignments__status__domain",
        )
        .get(id=employee_id)
    )


def _get_employee_for_transfer(employee_id: int) -> Employee:
    try:
        return _refresh_employee_for_transfer(employee_id)
    except Employee.DoesNotExist as exc:
        raise AuthError("EMPLOYEE_NOT_FOUND", "Employee not found.", 404) from exc


def _build_archived_email(email: str, employee_id: int) -> str:
    normalized_email = email.strip()
    local_part, separator, domain_part = normalized_email.partition("@")
    if not separator:
        local_part = local_part or f"employee-{employee_id}"
        domain_part = "archived.local"
    archived_local = local_part or f"employee-{employee_id}"
    base_email = f"{archived_local}+archived-{employee_id}@{domain_part}"
    candidate = base_email
    counter = 1
    while Employee.objects.filter(canonical_email=canonicalize_email(candidate)).exists():
        candidate = f"{archived_local}+archived-{employee_id}-{counter}@{domain_part}"
        counter += 1
    return candidate


def _active_transfer_candidate_queryset():
    return (
        Employee.objects.select_related(
            "primary_business_unit",
            "office",
            "office__status",
            "status",
        )
        .prefetch_related(
            "business_unit_assignments__business_unit",
            "business_unit_assignments__status__domain",
            "role_assignments__role",
            "role_assignments__status__domain",
        )
        .filter(status__value_code="ACTIVE")
        .order_by("office__office_name", "employee_code")
    )


def _employee_transfer_blockers(employee: Employee) -> list[dict]:
    today = date.today()
    blockers: list[dict] = []

    def add_blocker(code: str, label: str, count: int, message: str) -> None:
        if count <= 0:
            return
        blockers.append(
            {
                "code": code,
                "label": label,
                "count": count,
                "message": message,
            }
        )

    add_blocker(
        "OPEN_TIMESHEETS",
        "Open Timesheets",
        WeeklyTimesheet.objects.filter(employee_id=employee.id)
        .exclude(status__value_code__in={"APPROVED", "ARCHIVED"})
        .count(),
        "Close, submit, or resolve the employee's non-final timesheets before transfer.",
    )
    add_blocker(
        "DIRECT_REPORTS",
        "Active Direct Reports",
        Employee.objects.filter(
            manager_employee_id=employee.id,
            status__value_code="ACTIVE",
        ).count(),
        "Reassign or clear active direct-report relationships before transfer.",
    )
    add_blocker(
        "OWNED_PROJECTS",
        "Active Owned Projects",
        Project.objects.filter(
            project_owner_employee_id=employee.id,
            status__value_code="ACTIVE",
        ).count(),
        "Reassign active project ownership before transfer.",
    )
    add_blocker(
        "MANAGED_PROJECTS",
        "Active Managed Projects",
        Project.objects.filter(
            project_manager_employee_id=employee.id,
            status__value_code="ACTIVE",
        ).count(),
        "Reassign active project management before transfer.",
    )
    add_blocker(
        "PROJECT_ASSIGNMENTS",
        "Active Project Assignments",
        ProjectAssignment.objects.filter(
            employee_id=employee.id,
            status__value_code="ACTIVE",
            assignment_start_date__lte=today,
        )
        .filter(Q(assignment_end_date__isnull=True) | Q(assignment_end_date__gte=today))
        .count(),
        "Close or reassign active project staffing before transfer.",
    )
    add_blocker(
        "CROSS_OFFICE_PROJECT_ASSIGNMENTS",
        "Active Cross-Office Staffing",
        CrossOfficeProjectAssignment.objects.filter(
            employee_id=employee.id,
            status__value_code="ACTIVE",
            assignment_start_date__lte=today,
        )
        .filter(Q(assignment_end_date__isnull=True) | Q(assignment_end_date__gte=today))
        .count(),
        "Close or reassign active cross-office staffing before transfer.",
    )
    add_blocker(
        "GCC_APPROVAL_ROLE_ASSIGNMENTS",
        "Active GCC Approval Memberships",
        GeneralChargeCodeApprovalRoleAssignment.objects.filter(
            employee_id=employee.id,
            status__value_code="ACTIVE",
            valid_from__lte=today,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        .count(),
        "Remove or reassign active General Charge Code approval-role memberships before transfer.",
    )
    add_blocker(
        "PENDING_APPROVAL_ITEMS",
        "Pending Approval Items",
        ApprovalItem.objects.filter(
            approver_employee_id=employee.id,
            status__value_code="PENDING",
        ).count(),
        "Resolve or reroute pending approval items before transfer.",
    )
    return blockers


def _serialize_employee_transfer_summary(employee: Employee) -> dict:
    payload = _serialize_employee(employee)
    blockers = _employee_transfer_blockers(employee)
    payload["transfer_blockers"] = blockers
    payload["can_transfer"] = not blockers
    payload["archived_email_preview"] = _build_archived_email(employee.email, employee.id)
    return payload


def _serialize_client(
    client: ClientRecord,
    *,
    project_business_unit_summaries: list[dict] | None = None,
) -> dict:
    return {
        "id": client.id,
        "client_code": client.client_code,
        "name": client.name,
        "status": client.status.value_code,
        "project_business_unit_summaries": project_business_unit_summaries or [],
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


def _preferred_assigned_calendar_for_office(office_id: int) -> YearlyCalendar | None:
    current_year = date.today().year
    calendars = list(
        YearlyCalendar.objects.select_related("status")
        .filter(office_id=office_id)
        .order_by("-calendar_year", "id")
    )
    if not calendars:
        return None
    calendars.sort(
        key=lambda calendar: (
            calendar.status.value_code != "ACTIVE",
            calendar.calendar_year != current_year,
            abs(calendar.calendar_year - current_year),
            -calendar.calendar_year,
            calendar.id,
        )
    )
    return calendars[0]


def _clone_default_calendar_rules_to_business_unit(
    yearly_calendar: YearlyCalendar,
    business_unit: BusinessUnit,
    *,
    actor_email: str,
) -> None:
    if yearly_calendar.office_id != business_unit.office_id:
        return
    if CalendarPeriodRule.objects.filter(
        yearly_calendar=yearly_calendar,
        business_unit=business_unit,
    ).exists():
        return
    if CalendarPeriodRule.objects.filter(
        yearly_calendar=yearly_calendar,
        business_unit__isnull=True,
    ).exists():
        return

    donor_rules = list(
        CalendarPeriodRule.objects.filter(
            yearly_calendar=yearly_calendar,
            business_unit_id__isnull=False,
        )
        .order_by("business_unit_id", "effective_from", "id")
    )
    donor_business_unit_ids = sorted({rule.business_unit_id for rule in donor_rules})
    if len(donor_business_unit_ids) != 1:
        return

    for donor_rule in donor_rules:
        if CalendarPeriodRule.objects.filter(
            yearly_calendar=yearly_calendar,
            business_unit=business_unit,
            effective_from=donor_rule.effective_from,
            effective_to=donor_rule.effective_to,
        ).exists():
            continue
        CalendarPeriodRule.objects.create(
            yearly_calendar=yearly_calendar,
            business_unit=business_unit,
            office=yearly_calendar.office,
            effective_from=donor_rule.effective_from,
            effective_to=donor_rule.effective_to,
            monday_max_hours=donor_rule.monday_max_hours,
            tuesday_max_hours=donor_rule.tuesday_max_hours,
            wednesday_max_hours=donor_rule.wednesday_max_hours,
            thursday_max_hours=donor_rule.thursday_max_hours,
            friday_max_hours=donor_rule.friday_max_hours,
            working_on_saturdays_flag=donor_rule.working_on_saturdays_flag,
            working_on_sundays_flag=donor_rule.working_on_sundays_flag,
            saturday_max_hours=donor_rule.saturday_max_hours,
            sunday_max_hours=donor_rule.sunday_max_hours,
            status=donor_rule.status,
            created_by=actor_email,
            updated_by=actor_email,
        )


def _ensure_employee_calendar_setup(employee: Employee, *, actor_email: str) -> None:
    if employee.assigned_calendar_id is None:
        preferred_calendar = _preferred_assigned_calendar_for_office(employee.office_id)
        if preferred_calendar is not None:
            employee.assigned_calendar = preferred_calendar
            employee.updated_by = actor_email
            employee.save(update_fields=["assigned_calendar", "updated_by", "updated_at"])
    if employee.assigned_calendar_id is None:
        return
    _clone_default_calendar_rules_to_business_unit(
        employee.assigned_calendar,
        employee.primary_business_unit,
        actor_email=actor_email,
    )


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
        "employee_count": getattr(project, "employee_count", 0),
    }


def _serialize_project_assignment(assignment: ProjectAssignment) -> dict:
    return {
        "id": assignment.id,
        "assignment_type": "PROJECT_ASSIGNMENT",
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
            "client": {
                "id": assignment.project.client_id,
                "client_code": assignment.project.client.client_code,
                "name": assignment.project.client.name,
            },
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


def _serialize_cross_office_project_assignment(
    assignment: CrossOfficeProjectAssignment,
) -> dict:
    return {
        "id": assignment.id,
        "assignment_type": "CROSS_OFFICE",
        "name": (
            f"{assignment.project.project_code} -> "
            f"{assignment.employee.employee_code} ({assignment.assignment_start_date.isoformat()})"
        ),
        "assignment_start_date": assignment.assignment_start_date.isoformat(),
        "assignment_end_date": assignment.assignment_end_date.isoformat()
        if assignment.assignment_end_date
        else None,
        "justification_text": assignment.justification_text,
        "status": assignment.status.value_code,
        "project": {
            "id": assignment.project_id,
            "project_code": assignment.project.project_code,
            "name": assignment.project.name,
            "client": {
                "id": assignment.project.client_id,
                "client_code": assignment.project.client.client_code,
                "name": assignment.project.client.name,
            },
            "office": {
                "id": assignment.project.office_id,
                "office_name": assignment.project.office.office_name,
            },
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
            "office": {
                "id": assignment.employee.office_id,
                "office_name": assignment.employee.office.office_name,
            },
            "primary_business_unit": {
                "id": assignment.employee.primary_business_unit_id,
                "bu_code": assignment.employee.primary_business_unit.bu_code,
                "name": assignment.employee.primary_business_unit.name,
            },
        },
        "origin_office": {
            "id": assignment.origin_office_id,
            "office_name": assignment.origin_office.office_name,
        },
        "origin_business_unit": {
            "id": assignment.origin_business_unit_id,
            "bu_code": assignment.origin_business_unit.bu_code,
            "name": assignment.origin_business_unit.name,
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


from apps.master_data.service_modules.business_unit import (  # noqa: E402
    BusinessUnitManagementService,
)
from apps.master_data.service_modules.calendar import (  # noqa: E402
    CalendarPeriodRuleManagementService,
    CalendarSpecialDayManagementService,
    YearlyCalendarManagementService,
)
from apps.master_data.service_modules.country_office import (  # noqa: E402
    CountryManagementService,
    OfficeManagementService,
)
from apps.master_data.service_modules.employee import (  # noqa: E402
    EmployeeManagementService,
)
from apps.master_data.service_modules.project_staffing import (  # noqa: E402
    CrossOfficeProjectAssignmentManagementService,
    ProjectAssignmentManagementService,
    ProjectManagementService,
)
from apps.master_data.service_modules.reference_master import (  # noqa: E402
    ClientManagementService,
    CostCenterManagementService,
    InternalCategoryManagementService,
    PricingModelManagementService,
)

__all__ = [
    "BusinessUnitManagementService",
    "CalendarPeriodRuleManagementService",
    "CalendarSpecialDayManagementService",
    "ClientManagementService",
    "CostCenterManagementService",
    "CountryManagementService",
    "CrossOfficeProjectAssignmentManagementService",
    "EmployeeManagementService",
    "GeneralChargeCodeApprovalRoleManagementService",
    "GeneralChargeCodeManagementService",
    "InternalCategoryManagementService",
    "OfficeManagementService",
    "PricingModelManagementService",
    "ProjectAssignmentManagementService",
    "ProjectManagementService",
    "YearlyCalendarManagementService",
]
