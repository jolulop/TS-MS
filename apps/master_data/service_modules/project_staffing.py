from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.master_data.models import Client as ClientRecord
from apps.master_data.models import CostCenter as CostCenterRecord
from apps.master_data.models import (
    CrossOfficeProjectAssignment,
    Employee,
    Project,
    ProjectAssignment,
)
from apps.master_data.models import InternalCategory as InternalCategoryRecord
from apps.master_data.models import PricingModel as PricingModelRecord
from apps.master_data.service_modules.reference_master import (
    ClientManagementService,
    CostCenterManagementService,
    InternalCategoryManagementService,
    PricingModelManagementService,
)


def _master_services():
    from apps.master_data import services

    return services


def _actor_employee(current_user):
    return _master_services()._actor_employee(current_user)


def _apply_status_filter(queryset, status_code):
    return _master_services()._apply_status_filter(queryset, status_code)


def _employee_has_active_business_unit_scope(employee_id: int, business_unit_id: int) -> bool:
    return _master_services()._employee_has_active_business_unit_scope(
        employee_id,
        business_unit_id,
    )


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


def _ensure_ts_admin_or_project_assignment_manager(current_user: CurrentUser) -> None:
    return _master_services()._ensure_ts_admin_or_project_assignment_manager(current_user)


def _ensure_ts_admin_or_project_owner(current_user: CurrentUser) -> None:
    return _master_services()._ensure_ts_admin_or_project_owner(current_user)


def _get_employee_for_project_assignment(employee_id: int) -> Employee:
    return _master_services()._get_employee_for_project_assignment(employee_id)


def _get_scoped_business_unit(current_user: CurrentUser, business_unit_id: int):
    return _master_services()._get_scoped_business_unit(current_user, business_unit_id)


def _parse_optional_iso_date(value: object, *, code: str, message: str) -> date | None:
    return _master_services()._parse_optional_iso_date(value, code=code, message=message)


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    return _master_services()._parse_required_int(value, code=code, message=message)


def _parse_iso_date(value: object, *, code: str, message: str) -> date:
    return _master_services()._parse_iso_date(value, code=code, message=message)


def _parse_status_filter(status_code, *, domain_code: str):
    return _master_services()._parse_status_filter(status_code, domain_code=domain_code)


def _ref_value(domain_code: str, value_code: str):
    return _master_services()._ref_value(domain_code, value_code)


def _serialize_cross_office_project_assignment(assignment: CrossOfficeProjectAssignment) -> dict:
    return _master_services()._serialize_cross_office_project_assignment(assignment)


def _serialize_project(project: Project) -> dict:
    return _master_services()._serialize_project(project)


def _serialize_project_assignment(assignment: ProjectAssignment) -> dict:
    return _master_services()._serialize_project_assignment(assignment)


def _validate_optional_office_payload(payload: dict, **kwargs) -> None:
    return _master_services()._validate_optional_office_payload(payload, **kwargs)


class ProjectManagementService:
    @staticmethod
    def list_projects(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
        client_id: int | None = None,
        business_unit_id: int | None = None,
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
        ).annotate(employee_count=Count("assignments__employee_id", distinct=True))
        if not current_user.is_ts_admin:
            projects = projects.filter(project_owner_employee_id=current_user.employee_id)
        if client_id is not None:
            projects = projects.filter(client_id=client_id)
        if business_unit_id is not None:
            projects = projects.filter(business_unit_id=business_unit_id)
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


def _active_staffing_overlap_queryset(
    queryset,
    *,
    assignment_start_date: date,
    assignment_end_date: date | None,
    exclude_id: int | None = None,
):
    queryset = queryset.filter(
        status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
        status__value_code="ACTIVE",
    )
    if exclude_id is not None:
        queryset = queryset.exclude(id=exclude_id)
    if assignment_end_date is not None:
        queryset = queryset.filter(assignment_start_date__lte=assignment_end_date)
    return queryset.filter(
        Q(assignment_end_date__isnull=True) | Q(assignment_end_date__gte=assignment_start_date)
    )


def _lock_project_staffing_overlap_scope(*, project_id: int, employee_id: int) -> None:
    Project.objects.select_for_update(of=("self",)).get(id=project_id)
    Employee.objects.select_for_update(of=("self",)).get(id=employee_id)


def _validate_project_staffing_overlap(
    *,
    project: Project,
    employee: Employee,
    assignment_start_date: date,
    assignment_end_date: date | None,
    error_code: str,
    error_message: str,
    exclude_project_assignment_id: int | None = None,
    exclude_cross_office_assignment_id: int | None = None,
) -> None:
    overlapping_project_assignment_exists = _active_staffing_overlap_queryset(
        ProjectAssignment.objects.filter(
            project_id=project.id,
            employee_id=employee.id,
        ),
        assignment_start_date=assignment_start_date,
        assignment_end_date=assignment_end_date,
        exclude_id=exclude_project_assignment_id,
    ).exists()
    if overlapping_project_assignment_exists:
        raise AuthError(error_code, error_message, 400)

    overlapping_cross_office_exists = _active_staffing_overlap_queryset(
        CrossOfficeProjectAssignment.objects.filter(
            project_id=project.id,
            employee_id=employee.id,
        ),
        assignment_start_date=assignment_start_date,
        assignment_end_date=assignment_end_date,
        exclude_id=exclude_cross_office_assignment_id,
    ).exists()
    if overlapping_cross_office_exists:
        raise AuthError(error_code, error_message, 400)


class ProjectAssignmentManagementService:
    @staticmethod
    def list_assignments(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
        client_id: object = None,
        project_id: object = None,
    ) -> list[dict]:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        assignments = ProjectAssignment.objects.select_related(
            "project",
            "project__office",
            "project__business_unit",
            "project__client",
            "employee",
            "employee__primary_business_unit",
            "status",
        ).filter(
            project__business_unit_id__in=current_user.scoped_business_unit_ids,
            project__office_id=current_user.office_id,
        )
        if client_id not in (None, ""):
            assignments = assignments.filter(
                project__client_id=_parse_required_int(
                    client_id,
                    code="PROJECT_ASSIGNMENT_FILTER_CLIENT_INVALID",
                    message="Client filter must be a valid Client identifier.",
                )
            )
        if project_id not in (None, ""):
            assignments = assignments.filter(
                project_id=_parse_required_int(
                    project_id,
                    code="PROJECT_ASSIGNMENT_FILTER_PROJECT_INVALID",
                    message="Project filter must be a valid Project identifier.",
                )
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
        if not _employee_has_active_business_unit_scope(employee.id, project.business_unit_id):
            raise AuthError(
                "PROJECT_ASSIGNMENT_EMPLOYEE_BU_SCOPE_INVALID",
                "Project assignment employee must be active in the project Business Unit.",
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
        status = _ref_value(
            "PROJECT_ASSIGNMENT_STATUS",
            str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
        )
        ProjectAssignmentManagementService._validate_assignment_dates(
            project=project,
            assignment_start_date=assignment_start_date,
            assignment_end_date=assignment_end_date,
        )
        if status.value_code == "ACTIVE":
            _lock_project_staffing_overlap_scope(project_id=project.id, employee_id=employee.id)
            _validate_project_staffing_overlap(
                project=project,
                employee=employee,
                assignment_start_date=assignment_start_date,
                assignment_end_date=assignment_end_date,
                error_code="PROJECT_ASSIGNMENT_OVERLAP",
                error_message=(
                    "Project assignment overlaps an active staffing window for this "
                    "employee and project."
                ),
            )
        try:
            assignment = ProjectAssignment.objects.create(
                project=project,
                employee=employee,
                assignment_start_date=assignment_start_date,
                assignment_end_date=assignment_end_date,
                status=status,
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
        if assignment.status.value_code == "ACTIVE":
            _lock_project_staffing_overlap_scope(
                project_id=assignment.project_id,
                employee_id=assignment.employee_id,
            )
            _validate_project_staffing_overlap(
                project=assignment.project,
                employee=assignment.employee,
                assignment_start_date=assignment.assignment_start_date,
                assignment_end_date=assignment.assignment_end_date,
                error_code="PROJECT_ASSIGNMENT_OVERLAP",
                error_message=(
                    "Project assignment overlaps an active staffing window for this "
                    "employee and project."
                ),
                exclude_project_assignment_id=assignment.id,
            )
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
                "project__client",
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
            "project__client",
            "employee",
            "employee__primary_business_unit",
            "status",
        ).get(id=assignment_id)


class CrossOfficeProjectAssignmentManagementService:
    @staticmethod
    def list_assignments(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
        target_office_id: object = None,
        client_id: object = None,
        project_id: object = None,
        origin_office_id: object = None,
        employee_id: object = None,
    ) -> list[dict]:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        assignments = CrossOfficeProjectAssignment.objects.select_related(
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
        ).filter(
            project__business_unit_id__in=current_user.scoped_business_unit_ids,
            project__office_id=current_user.office_id,
        )
        if target_office_id not in (None, ""):
            assignments = assignments.filter(
                project__office_id=_parse_required_int(
                    target_office_id,
                    code="CROSS_OFFICE_PROJECT_ASSIGNMENT_FILTER_TARGET_OFFICE_INVALID",
                    message="Target Office filter must be a valid Office identifier.",
                )
            )
        if client_id not in (None, ""):
            assignments = assignments.filter(
                project__client_id=_parse_required_int(
                    client_id,
                    code="CROSS_OFFICE_PROJECT_ASSIGNMENT_FILTER_CLIENT_INVALID",
                    message="Client filter must be a valid Client identifier.",
                )
            )
        if project_id not in (None, ""):
            assignments = assignments.filter(
                project_id=_parse_required_int(
                    project_id,
                    code="CROSS_OFFICE_PROJECT_ASSIGNMENT_FILTER_PROJECT_INVALID",
                    message="Project filter must be a valid Project identifier.",
                )
            )
        if origin_office_id not in (None, ""):
            assignments = assignments.filter(
                origin_office_id=_parse_required_int(
                    origin_office_id,
                    code="CROSS_OFFICE_PROJECT_ASSIGNMENT_FILTER_ORIGIN_OFFICE_INVALID",
                    message="Origin Office filter must be a valid Office identifier.",
                )
            )
        if employee_id not in (None, ""):
            assignments = assignments.filter(
                employee_id=_parse_required_int(
                    employee_id,
                    code="CROSS_OFFICE_PROJECT_ASSIGNMENT_FILTER_EMPLOYEE_INVALID",
                    message="Employee filter must be a valid Employee identifier.",
                )
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
                "origin_office__office_name",
                "employee__employee_code",
                "assignment_start_date",
            ),
            _parse_status_filter(status_code, domain_code="PROJECT_ASSIGNMENT_STATUS"),
        )
        return [
            _serialize_cross_office_project_assignment(assignment) for assignment in assignments
        ]

    @staticmethod
    def get_assignment(current_user: CurrentUser, assignment_id: int) -> dict:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        assignment = CrossOfficeProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        return _serialize_cross_office_project_assignment(assignment)

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
                code="CROSS_OFFICE_PROJECT_ASSIGNMENT_PROJECT_REQUIRED",
                message="project_id is required.",
            ),
        )
        if project.status.value_code == "CLOSED":
            raise AuthError(
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_PROJECT_CLOSED",
                "Closed projects cannot receive new assignments.",
                400,
            )
        employee = _get_employee_for_project_assignment(
            _parse_required_int(
                payload.get("employee_id"),
                code="CROSS_OFFICE_PROJECT_ASSIGNMENT_EMPLOYEE_REQUIRED",
                message="employee_id is required.",
            ),
        )
        if employee.status.value_code != "ACTIVE":
            raise AuthError(
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_EMPLOYEE_INACTIVE",
                "Cross-office staffing employee must be active.",
                400,
            )
        submitted_origin_office_id = _parse_required_int(
            payload.get("origin_office_id"),
            code="CROSS_OFFICE_PROJECT_ASSIGNMENT_ORIGIN_OFFICE_REQUIRED",
            message="origin_office_id is required.",
        )
        if employee.office_id != submitted_origin_office_id:
            raise AuthError(
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_ORIGIN_OFFICE_MISMATCH",
                "Selected employee must belong to the selected origin Office.",
                400,
            )
        if employee.office_id == project.office_id:
            raise AuthError(
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_SAME_OFFICE_INVALID",
                (
                    "Cross-office staffing requires the employee Office to differ "
                    "from the target project Office."
                ),
                400,
            )
        assignment_start_date = _parse_iso_date(
            payload.get("assignment_start_date"),
            code="CROSS_OFFICE_PROJECT_ASSIGNMENT_START_REQUIRED",
            message="assignment_start_date must be a valid ISO date.",
        )
        assignment_end_date = _parse_optional_iso_date(
            payload.get("assignment_end_date"),
            code="CROSS_OFFICE_PROJECT_ASSIGNMENT_END_INVALID",
            message="assignment_end_date must be a valid ISO date.",
        )
        status = _ref_value(
            "PROJECT_ASSIGNMENT_STATUS",
            str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
        )
        ProjectAssignmentManagementService._validate_assignment_dates(
            project=project,
            assignment_start_date=assignment_start_date,
            assignment_end_date=assignment_end_date,
        )
        if status.value_code == "ACTIVE":
            _lock_project_staffing_overlap_scope(project_id=project.id, employee_id=employee.id)
            _validate_project_staffing_overlap(
                project=project,
                employee=employee,
                assignment_start_date=assignment_start_date,
                assignment_end_date=assignment_end_date,
                error_code="CROSS_OFFICE_PROJECT_ASSIGNMENT_OVERLAP",
                error_message=(
                    "Cross-office staffing overlaps an active staffing window for "
                    "this employee and project."
                ),
            )
        try:
            assignment = CrossOfficeProjectAssignment.objects.create(
                project=project,
                employee=employee,
                origin_office=employee.office,
                origin_business_unit=employee.primary_business_unit,
                assignment_start_date=assignment_start_date,
                assignment_end_date=assignment_end_date,
                justification_text=str(payload.get("justification_text", "")).strip(),
                status=status,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_NOT_UNIQUE",
                (
                    "Cross-office staffing start date must be unique for the "
                    "employee within the project."
                ),
                400,
            ) from exc
        write_audit_event(
            action_code="CREATE",
            entity_name="cross_office_project_assignment",
            entity_id=assignment.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=project.business_unit,
            reason_text="Cross-office staffing created by authorized project administration.",
        )
        return _serialize_cross_office_project_assignment(
            CrossOfficeProjectAssignmentManagementService._refresh_assignment(assignment.id)
        )

    @staticmethod
    @transaction.atomic
    def update_assignment(current_user: CurrentUser, assignment_id: int, payload: dict) -> dict:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        assignment = CrossOfficeProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            assignment.project.office,
            out_of_scope_message="Cross-office staffing is outside your active office.",
        )
        immutable_checks = [
            (
                "project_id",
                assignment.project_id,
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_PROJECT_IMMUTABLE",
                "Cross-office staffing project cannot be changed.",
                "project_id must be a valid project identifier.",
            ),
            (
                "employee_id",
                assignment.employee_id,
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_EMPLOYEE_IMMUTABLE",
                "Cross-office staffing employee cannot be changed.",
                "employee_id must be a valid employee identifier.",
            ),
            (
                "origin_office_id",
                assignment.origin_office_id,
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_ORIGIN_OFFICE_IMMUTABLE",
                "Cross-office staffing origin Office cannot be changed.",
                "origin_office_id must be a valid Office identifier.",
            ),
            (
                "origin_business_unit_id",
                assignment.origin_business_unit_id,
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_ORIGIN_BU_IMMUTABLE",
                "Cross-office staffing origin Business Unit cannot be changed.",
                "origin_business_unit_id must be a valid Business Unit identifier.",
            ),
        ]
        for field_name, expected_id, error_code, message, parse_message in immutable_checks:
            if (
                field_name in payload
                and _parse_required_int(
                    payload.get(field_name),
                    code=error_code,
                    message=parse_message,
                )
                != expected_id
            ):
                raise AuthError(error_code, message, 400)
        proposed_start_date = assignment.assignment_start_date
        proposed_end_date = assignment.assignment_end_date
        if "assignment_start_date" in payload:
            proposed_start_date = _parse_iso_date(
                payload.get("assignment_start_date"),
                code="CROSS_OFFICE_PROJECT_ASSIGNMENT_START_REQUIRED",
                message="assignment_start_date must be a valid ISO date.",
            )
        if "assignment_end_date" in payload:
            proposed_end_date = _parse_optional_iso_date(
                payload.get("assignment_end_date"),
                code="CROSS_OFFICE_PROJECT_ASSIGNMENT_END_INVALID",
                message="assignment_end_date must be a valid ISO date.",
            )
        proposed_status = assignment.status
        if "status_code" in payload:
            proposed_status = _ref_value(
                "PROJECT_ASSIGNMENT_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
        ProjectAssignmentManagementService._validate_assignment_dates(
            project=assignment.project,
            assignment_start_date=proposed_start_date,
            assignment_end_date=proposed_end_date,
        )
        if proposed_status.value_code == "ACTIVE":
            _lock_project_staffing_overlap_scope(
                project_id=assignment.project_id,
                employee_id=assignment.employee_id,
            )
            _validate_project_staffing_overlap(
                project=assignment.project,
                employee=assignment.employee,
                assignment_start_date=proposed_start_date,
                assignment_end_date=proposed_end_date,
                error_code="CROSS_OFFICE_PROJECT_ASSIGNMENT_OVERLAP",
                error_message=(
                    "Cross-office staffing overlaps an active staffing window for "
                    "this employee and project."
                ),
                exclude_cross_office_assignment_id=assignment.id,
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
        if "justification_text" in payload:
            proposed_justification = str(payload.get("justification_text", "")).strip()
            if proposed_justification != assignment.justification_text:
                changed_fields.append(
                    (
                        "justification_text",
                        assignment.justification_text,
                        proposed_justification,
                    )
                )
                assignment.justification_text = proposed_justification
        if proposed_status.id != assignment.status_id:
            changed_fields.append(
                ("status", assignment.status.value_code, proposed_status.value_code)
            )
            assignment.status = proposed_status
        if changed_fields:
            try:
                assignment.updated_by = current_user.email
                assignment.save()
            except IntegrityError as exc:
                raise AuthError(
                    "CROSS_OFFICE_PROJECT_ASSIGNMENT_NOT_UNIQUE",
                    (
                        "Cross-office staffing start date must be unique for the "
                        "employee within the project."
                    ),
                    400,
                ) from exc
        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="cross_office_project_assignment",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=assignment.project.business_unit,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Cross-office staffing updated by authorized project administration.",
            )
        return _serialize_cross_office_project_assignment(
            CrossOfficeProjectAssignmentManagementService._refresh_assignment(assignment.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_assignment(current_user: CurrentUser, assignment_id: int) -> None:
        _ensure_ts_admin_or_project_assignment_manager(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        assignment = CrossOfficeProjectAssignmentManagementService._get_scoped_assignment(
            current_user,
            assignment_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            assignment.project.office,
            out_of_scope_message="Cross-office staffing is outside your active office.",
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
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_DELETE_BLOCKED",
                (
                    "Cross-office staffing cannot be deleted because it is still "
                    "referenced by other records."
                ),
                400,
            ) from exc
        write_audit_event(
            action_code="DELETE",
            entity_name="cross_office_project_assignment",
            entity_id=assignment_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            old_value=assignment_label,
            reason_text="Cross-office staffing deleted by authorized project administration.",
        )

    @staticmethod
    def _get_scoped_assignment(
        current_user: CurrentUser,
        assignment_id: int,
    ) -> CrossOfficeProjectAssignment:
        try:
            assignment = CrossOfficeProjectAssignment.objects.select_related(
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
            ).get(id=assignment_id)
        except CrossOfficeProjectAssignment.DoesNotExist as exc:
            raise AuthError(
                "CROSS_OFFICE_PROJECT_ASSIGNMENT_NOT_FOUND",
                "Cross-office staffing not found.",
                404,
            ) from exc
        _ensure_business_units_in_scope(current_user, {assignment.project.business_unit_id})
        _ensure_office_in_scope(
            current_user,
            assignment.project.office_id,
            message="Cross-office staffing is outside your active office.",
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
            "Cross-office staffing is outside your owned or managed project scope.",
            403,
        )

    @staticmethod
    def _refresh_assignment(assignment_id: int) -> CrossOfficeProjectAssignment:
        return CrossOfficeProjectAssignment.objects.select_related(
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
        ).get(id=assignment_id)
