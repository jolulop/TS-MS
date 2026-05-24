from django.db import IntegrityError, transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError

from apps.audit.models import AuditLog
from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.master_data.models import BusinessUnit, Employee, EmployeeBusinessUnit, EmployeeRole


def _master_services():
    from apps.master_data import services

    return services


def _actor_employee(current_user):
    return _master_services()._actor_employee(current_user)


def _apply_status_filter(queryset, status_code):
    return _master_services()._apply_status_filter(queryset, status_code)


def _ensure_business_unit_code_available(**kwargs) -> None:
    return _master_services()._ensure_business_unit_code_available(**kwargs)


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


def _ensure_office_in_scope(current_user: CurrentUser, office_id: int, *, message: str) -> None:
    return _master_services()._ensure_office_in_scope(
        current_user,
        office_id,
        message=message,
    )


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


def _get_scoped_business_unit(
    current_user: CurrentUser,
    business_unit_id: int,
) -> BusinessUnit:
    return _master_services()._get_scoped_business_unit(current_user, business_unit_id)


def _parse_status_filter(status_code, *, domain_code: str):
    return _master_services()._parse_status_filter(status_code, domain_code=domain_code)


def _ref_value(domain_code: str, value_code: str):
    return _master_services()._ref_value(domain_code, value_code)


def _serialize_business_unit(
    business_unit: BusinessUnit,
    *,
    include_configuration: bool = False,
) -> dict:
    return _master_services()._serialize_business_unit(
        business_unit,
        include_configuration=include_configuration,
    )


def _validate_optional_office_payload(**kwargs) -> None:
    return _master_services()._validate_optional_office_payload(**kwargs)


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
            payload=payload,
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
            payload=payload,
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
            _master_services().EmployeeManagementService._replace_business_unit_assignments(
                current_user,
                office_admin,
                actor_employee=actor_employee,
                primary_business_unit_id=office_admin.primary_business_unit_id,
                business_unit_ids={office_admin.primary_business_unit_id},
                reason="Employee BU scope synchronized after Business Unit creation.",
                force_full_office_scope=True,
            )
