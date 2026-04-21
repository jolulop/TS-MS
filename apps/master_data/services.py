from datetime import date

from django.db import IntegrityError, transaction

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import canonicalize_email
from apps.master_data.models import BusinessUnit, Employee, EmployeeBusinessUnit, EmployeeRole
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


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise AuthError(code, message, 400) from exc
    if parsed_value <= 0:
        raise AuthError(code, message, 400)
    return parsed_value


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


def _get_scoped_employee_for_management(current_user: CurrentUser, employee_id: int) -> Employee:
    try:
        employee = (
            Employee.objects.select_related("primary_business_unit", "status")
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
    return employee


def _refresh_employee(employee_id: int) -> Employee:
    return (
        Employee.objects.select_related("primary_business_unit", "status")
        .prefetch_related(
            "business_unit_assignments__business_unit",
            "business_unit_assignments__status__domain",
            "role_assignments__role",
            "role_assignments__status__domain",
        )
        .get(id=employee_id)
    )


def _actor_employee(current_user: CurrentUser) -> Employee | None:
    return Employee.objects.filter(id=current_user.employee_id).first()


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


class EmployeeManagementService:
    @staticmethod
    @transaction.atomic
    def create_employee(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
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

        try:
            employee = Employee.objects.create(
                employee_code=employee_code,
                full_name=full_name,
                email=email,
                canonical_email=canonicalize_email(email),
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
        actor_employee = _actor_employee(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)

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
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        actor_employee = _actor_employee(current_user)
        primary_business_unit_id, business_unit_ids = _parse_business_unit_scope(payload)
        _ensure_business_units_in_scope(current_user, business_unit_ids)

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
            for business_unit in BusinessUnit.objects.filter(id__in=business_unit_ids).order_by(
                "bu_code"
            )
        }
        if primary_business_unit_id not in desired_business_units:
            raise AuthError(
                "EMPLOYEE_PRIMARY_BU_OUT_OF_SCOPE",
                "Primary Business Unit must be included in the employee scope.",
                400,
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
