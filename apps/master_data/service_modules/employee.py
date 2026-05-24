from datetime import date

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.services import canonicalize_email
from apps.master_data.models import (
    BusinessUnit,
    CrossOfficeProjectAssignment,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    Office,
    ProjectAssignment,
)


def _master_services():
    from apps.master_data import services

    return services


def _active_transfer_candidate_queryset():
    return _master_services()._active_transfer_candidate_queryset()


def _actor_employee(current_user):
    return _master_services()._actor_employee(current_user)


def _apply_status_filter(queryset, status_code):
    return _master_services()._apply_status_filter(queryset, status_code)


def _build_archived_email(email: str, employee_id: int) -> str:
    return _master_services()._build_archived_email(email, employee_id)


def _employee_has_active_role(
    employee_id: int,
    *,
    role_code: str,
    business_unit_id: int | None = None,
) -> bool:
    return _master_services()._employee_has_active_role(
        employee_id,
        role_code=role_code,
        business_unit_id=business_unit_id,
    )


def _employee_transfer_blockers(employee: Employee) -> list[dict]:
    return _master_services()._employee_transfer_blockers(employee)


def _ensure_business_units_in_scope(
    current_user: CurrentUser,
    business_unit_ids: set[int],
) -> None:
    return _master_services()._ensure_business_units_in_scope(
        current_user,
        business_unit_ids,
    )


def _ensure_current_office_active_for_write(current_user: CurrentUser):
    return _master_services()._ensure_current_office_active_for_write(current_user)


def _ensure_employee_calendar_setup(employee: Employee, *, actor_email: str) -> None:
    return _master_services()._ensure_employee_calendar_setup(
        employee,
        actor_email=actor_email,
    )


def _ensure_office_active_for_write(office: Office, *, message: str) -> None:
    return _master_services()._ensure_office_active_for_write(office, message=message)


def _ensure_scoped_active_office_for_write(
    current_user: CurrentUser,
    office,
    *,
    out_of_scope_message: str,
) -> None:
    return _master_services()._ensure_scoped_active_office_for_write(
        current_user,
        office,
        out_of_scope_message=out_of_scope_message,
    )


def _ensure_ts_admin(current_user: CurrentUser) -> None:
    return _master_services()._ensure_ts_admin(current_user)


def _ensure_ts_admin_master(current_user: CurrentUser) -> None:
    return _master_services()._ensure_ts_admin_master(current_user)


def _get_employee_for_transfer(employee_id: int) -> Employee:
    return _master_services()._get_employee_for_transfer(employee_id)


def _get_scoped_employee_for_management(
    current_user: CurrentUser,
    employee_id: int,
) -> Employee:
    return _master_services()._get_scoped_employee_for_management(current_user, employee_id)


def _office_business_units(office_id: int) -> dict[int, BusinessUnit]:
    return _master_services()._office_business_units(office_id)


def _parse_business_unit_scope(payload: dict) -> tuple[int, set[int]]:
    return _master_services()._parse_business_unit_scope(payload)


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    return _master_services()._parse_required_int(value, code=code, message=message)


def _parse_role_codes(payload: dict) -> list[str]:
    return _master_services()._parse_role_codes(payload)


def _parse_status_filter(status_code, *, domain_code: str):
    return _master_services()._parse_status_filter(status_code, domain_code=domain_code)


def _ref_value(domain_code: str, value_code: str):
    return _master_services()._ref_value(domain_code, value_code)


def _refresh_employee(employee_id: int) -> Employee:
    return _master_services()._refresh_employee(employee_id)


def _serialize_cross_office_project_assignment(assignment: CrossOfficeProjectAssignment) -> dict:
    return _master_services()._serialize_cross_office_project_assignment(assignment)


def _serialize_employee(employee: Employee) -> dict:
    return _master_services()._serialize_employee(employee)


def _serialize_employee_transfer_summary(employee: Employee) -> dict:
    return _master_services()._serialize_employee_transfer_summary(employee)


def _serialize_project_assignment(assignment: ProjectAssignment) -> dict:
    return _master_services()._serialize_project_assignment(assignment)


def _validate_optional_office_payload(payload: dict, **kwargs) -> None:
    return _master_services()._validate_optional_office_payload(payload, **kwargs)


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
    def list_employee_project_assignments(
        current_user: CurrentUser,
        employee_id: int,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        employee = _get_scoped_employee_for_management(current_user, employee_id)
        assignments = list(
            ProjectAssignment.objects.select_related(
                "project",
                "project__office",
                "project__business_unit",
                "employee",
                "employee__primary_business_unit",
                "status",
            )
            .filter(
                employee_id=employee.id,
                project__business_unit_id__in=current_user.scoped_business_unit_ids,
                project__office_id=current_user.office_id,
                status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
                status__value_code="ACTIVE",
            )
            .order_by(
                "project__business_unit__bu_code",
                "project__project_code",
                "-assignment_start_date",
            )
        )
        cross_office_assignments = list(
            CrossOfficeProjectAssignment.objects.select_related(
                "project",
                "project__office",
                "project__business_unit",
                "project__client",
                "employee",
                "employee__office",
                "employee__primary_business_unit",
                "origin_office",
                "origin_business_unit",
                "status",
            )
            .filter(
                employee_id=employee.id,
                origin_office_id=current_user.office_id,
                status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
                status__value_code="ACTIVE",
            )
            .order_by(
                "project__office__office_name",
                "project__business_unit__bu_code",
                "project__project_code",
                "-assignment_start_date",
            )
        )
        serialized_assignments = [
            _serialize_project_assignment(assignment) for assignment in assignments
        ]
        serialized_assignments.extend(
            _serialize_cross_office_project_assignment(assignment)
            for assignment in cross_office_assignments
        )
        serialized_assignments.sort(
            key=lambda assignment: (
                assignment["project"]["business_unit"]["bu_code"],
                assignment["project"]["project_code"],
                assignment["assignment_type"] != "PROJECT_ASSIGNMENT",
                assignment["assignment_start_date"],
            )
        )
        return serialized_assignments

    @staticmethod
    def list_transfer_candidates(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        employees = _active_transfer_candidate_queryset().exclude(id=current_user.employee_id)
        return [_serialize_employee_transfer_summary(employee) for employee in employees]

    @staticmethod
    def list_transfer_candidates_filtered(
        current_user: CurrentUser,
        *,
        office_id: object = None,
        primary_business_unit_id: object = None,
        full_name_query: str = "",
    ) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        employees = _active_transfer_candidate_queryset().exclude(id=current_user.employee_id)
        if office_id not in (None, ""):
            employees = employees.filter(
                office_id=_parse_required_int(
                    office_id,
                    code="EMPLOYEE_TRANSFER_FILTER_OFFICE_INVALID",
                    message="Office filter must be a valid Office identifier.",
                )
            )
        if primary_business_unit_id not in (None, ""):
            employees = employees.filter(
                primary_business_unit_id=_parse_required_int(
                    primary_business_unit_id,
                    code="EMPLOYEE_TRANSFER_FILTER_PRIMARY_BU_INVALID",
                    message="Primary BU filter must be a valid Business Unit identifier.",
                )
            )
        normalized_query = full_name_query.strip()
        if normalized_query:
            employees = employees.filter(full_name__icontains=normalized_query)
        return [_serialize_employee_transfer_summary(employee) for employee in employees]

    @staticmethod
    def get_transfer_candidate(current_user: CurrentUser, employee_id: int) -> dict:
        _ensure_ts_admin_master(current_user)
        employee = _get_employee_for_transfer(employee_id)
        return _serialize_employee_transfer_summary(employee)

    @staticmethod
    @transaction.atomic
    def transfer_employee_to_office(
        current_user: CurrentUser,
        source_employee_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)

        if current_user.employee_id == source_employee_id:
            raise AuthError(
                "EMPLOYEE_TRANSFER_SELF_BLOCKED",
                "You cannot transfer your own current employee record.",
                400,
            )

        source_employee = _get_employee_for_transfer(source_employee_id)
        if source_employee.status.value_code != "ACTIVE":
            raise AuthError(
                "EMPLOYEE_TRANSFER_SOURCE_INACTIVE",
                "Only active employees can be transferred.",
                400,
            )

        blockers = _employee_transfer_blockers(source_employee)
        if blockers:
            blocker_summary = "; ".join(
                f"{blocker['label']}: {blocker['count']}" for blocker in blockers
            )
            raise AuthError(
                "EMPLOYEE_TRANSFER_BLOCKED",
                f"Employee transfer is blocked until these active dependencies are resolved: "
                f"{blocker_summary}.",
                400,
            )

        new_employee_code = str(payload.get("new_employee_code", "")).strip()
        if not new_employee_code:
            raise AuthError(
                "EMPLOYEE_TRANSFER_CODE_REQUIRED",
                "New employee code is required for the target Office record.",
                400,
            )
        if Employee.objects.filter(employee_code=new_employee_code).exists():
            raise AuthError(
                "EMPLOYEE_CODE_NOT_UNIQUE",
                "Employee code must be unique.",
                400,
            )

        target_office_id = _parse_required_int(
            payload.get("target_office_id"),
            code="EMPLOYEE_TRANSFER_TARGET_OFFICE_REQUIRED",
            message="target_office_id is required.",
        )
        try:
            target_office = Office.objects.select_related("status").get(id=target_office_id)
        except Office.DoesNotExist as exc:
            raise AuthError("COUNTRY_NOT_FOUND", "Target Office not found.", 404) from exc
        if target_office.id == source_employee.office_id:
            raise AuthError(
                "EMPLOYEE_TRANSFER_SAME_OFFICE",
                "Source and target Offices must be different.",
                400,
            )
        _ensure_office_active_for_write(
            target_office,
            message="Target Office must be active before an employee can be transferred into it.",
        )

        primary_business_unit_id, business_unit_ids = _parse_business_unit_scope(
            {
                "primary_business_unit_id": payload.get("target_primary_business_unit_id"),
                "business_unit_ids": payload.get("target_business_unit_ids", []),
            }
        )
        role_codes = _parse_role_codes({"role_codes": payload.get("target_role_codes", [])})

        try:
            target_primary_business_unit = BusinessUnit.objects.select_related("office").get(
                id=primary_business_unit_id
            )
        except BusinessUnit.DoesNotExist as exc:
            raise AuthError(
                "BUSINESS_UNIT_NOT_FOUND",
                "Target primary Business Unit not found.",
                404,
            ) from exc
        if target_primary_business_unit.office_id != target_office.id:
            raise AuthError(
                "EMPLOYEE_TRANSFER_TARGET_OFFICE_MISMATCH",
                "Target primary Business Unit must belong to the selected target Office.",
                400,
            )

        archived_email = _build_archived_email(source_employee.email, source_employee.id)
        source_email = source_employee.email
        serialized_source_employee = _serialize_employee(source_employee)
        source_role_codes = serialized_source_employee["role_codes"]
        source_scope_codes = [
            business_unit["bu_code"]
            for business_unit in serialized_source_employee["business_units"]
        ]

        source_employee.email = archived_email
        source_employee.canonical_email = canonicalize_email(archived_email)
        source_employee.status = _ref_value("EMPLOYEE_STATUS", "INACTIVE")
        source_employee.updated_by = current_user.email
        source_employee.save(
            update_fields=["email", "canonical_email", "status", "updated_by", "updated_at"]
        )

        write_audit_event(
            action_code="UPDATE",
            entity_name="employee",
            entity_id=source_employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=source_employee.primary_business_unit,
            field_name="email",
            old_value=source_email,
            new_value=archived_email,
            reason_text="Employee source record email archived during Office transfer.",
        )
        write_audit_event(
            action_code="UPDATE",
            entity_name="employee",
            entity_id=source_employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=source_employee.primary_business_unit,
            field_name="status",
            old_value="ACTIVE",
            new_value="INACTIVE",
            reason_text="Employee source record deactivated during Office transfer.",
        )

        EmployeeManagementService._replace_role_assignments(
            current_user,
            source_employee,
            actor_employee=actor_employee,
            role_codes=[],
            reason="Employee roles closed on source record during Office transfer.",
        )
        EmployeeManagementService._deactivate_business_unit_assignments(
            current_user,
            source_employee,
            actor_employee=actor_employee,
            reason="Employee Business Unit scope closed on source record during Office transfer.",
        )

        target_employee = Employee.objects.create(
            employee_code=new_employee_code,
            full_name=source_employee.full_name,
            email=source_email,
            canonical_email=canonicalize_email(source_email),
            office=target_office,
            status=_ref_value("EMPLOYEE_STATUS", "ACTIVE"),
            primary_business_unit=target_primary_business_unit,
            created_by=current_user.email,
            updated_by=current_user.email,
        )

        EmployeeManagementService._replace_business_unit_assignments(
            current_user,
            target_employee,
            actor_employee=actor_employee,
            primary_business_unit_id=primary_business_unit_id,
            business_unit_ids=business_unit_ids,
            reason="Employee Business Unit scope created during Office transfer.",
            enforce_current_office_scope=False,
            force_full_office_scope="TS_ADMIN" in role_codes,
        )
        EmployeeManagementService._replace_role_assignments(
            current_user,
            target_employee,
            actor_employee=actor_employee,
            role_codes=role_codes,
            reason="Employee roles created during Office transfer.",
        )
        _ensure_employee_calendar_setup(target_employee, actor_email=current_user.email)

        write_audit_event(
            action_code="CREATE",
            entity_name="employee",
            entity_id=target_employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=target_employee.primary_business_unit,
            reason_text="Employee target record created during Office transfer.",
        )
        write_audit_event(
            action_code="CREATE",
            entity_name="employee_transfer",
            entity_id=target_employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=target_employee.primary_business_unit,
            old_value=(
                f"{source_employee.employee_code}|{source_email}|"
                f"{source_employee.office.office_name}|{','.join(source_scope_codes)}|"
                f"{','.join(source_role_codes)}"
            ),
            new_value=(
                f"{target_employee.employee_code}|{target_employee.email}|"
                f"{target_employee.office.office_name}"
            ),
            reason_text=(
                "Employee transferred across Offices using archive-and-recreate workflow."
            ),
        )

        refreshed_source_employee = _get_employee_for_transfer(source_employee.id)
        refreshed_target_employee = _refresh_employee(target_employee.id)
        return {
            "source_employee": _serialize_employee(refreshed_source_employee),
            "target_employee": _serialize_employee(refreshed_target_employee),
            "archived_email": archived_email,
        }

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
        _ensure_employee_calendar_setup(employee, actor_email=current_user.email)

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
    def _deactivate_business_unit_assignments(
        current_user: CurrentUser,
        employee: Employee,
        *,
        actor_employee: Employee | None,
        reason: str,
    ) -> None:
        active_assignments = list(
            employee.business_unit_assignments.select_related(
                "business_unit",
                "status",
                "status__domain",
            ).filter(valid_to__isnull=True)
        )
        if not active_assignments:
            return

        inactive_status = _ref_value("EMPLOYEE_BU_STATUS", "INACTIVE")
        previous_scope_codes = sorted(
            assignment.business_unit.bu_code
            for assignment in active_assignments
            if assignment.status.domain.domain_code == "EMPLOYEE_BU_STATUS"
            and assignment.status.value_code == "ACTIVE"
        )
        for assignment in active_assignments:
            if (
                assignment.status.domain.domain_code != "EMPLOYEE_BU_STATUS"
                or assignment.status.value_code != "ACTIVE"
            ):
                continue
            assignment.is_primary_flag = False
            assignment.status = inactive_status
            assignment.valid_to = date.today()
            assignment.updated_by = current_user.email
            assignment.save(
                update_fields=[
                    "is_primary_flag",
                    "status",
                    "valid_to",
                    "updated_by",
                    "updated_at",
                ]
            )

        write_audit_event(
            action_code="UPDATE",
            entity_name="employee_business_unit",
            entity_id=employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=employee.primary_business_unit,
            field_name="business_unit_scope",
            old_value=",".join(previous_scope_codes),
            new_value="",
            reason_text=reason,
        )

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
        _ensure_employee_calendar_setup(employee, actor_email=current_user.email)

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
