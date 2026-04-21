from datetime import date

from django.db import IntegrityError, transaction

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import canonicalize_email
from apps.master_data.models import (
    BusinessUnit,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
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
        return BusinessUnit.objects.get(id=business_unit_id)
    except BusinessUnit.DoesNotExist as exc:
        raise AuthError("BUSINESS_UNIT_NOT_FOUND", "Business Unit not found.", 404) from exc


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


def _serialize_client(client: ClientRecord) -> dict:
    return {
        "id": client.id,
        "client_code": client.client_code,
        "name": client.name,
        "status": client.status.value_code,
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
        "business_unit": {
            "id": general_charge_code.business_unit_id,
            "bu_code": general_charge_code.business_unit.bu_code,
            "name": general_charge_code.business_unit.name,
        },
    }


class EmployeeManagementService:
    @staticmethod
    def list_employees(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        employees = (
            Employee.objects.select_related("primary_business_unit", "status")
            .prefetch_related(
                "business_unit_assignments__business_unit",
                "business_unit_assignments__status__domain",
                "role_assignments__role",
                "role_assignments__status__domain",
            )
            .filter(primary_business_unit_id__in=current_user.scoped_business_unit_ids)
            .order_by("employee_code")
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


class ClientManagementService:
    @staticmethod
    def list_clients(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        clients = (
            ClientRecord.objects.select_related("business_unit", "parent_client", "status")
            .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
            .order_by("business_unit__bu_code", "client_code")
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
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="CLIENT_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)

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

        try:
            client = ClientRecord.objects.create(
                business_unit=business_unit,
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
        actor_employee = _actor_employee(current_user)
        client = ClientManagementService._get_scoped_client(current_user, client_id)

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
                "business_unit", "parent_client", "status"
            ).get(id=client_id)
        except ClientRecord.DoesNotExist as exc:
            raise AuthError("CLIENT_NOT_FOUND", "Client not found.", 404) from exc

        _ensure_business_units_in_scope(current_user, {client.business_unit_id})
        return client

    @staticmethod
    def _refresh_client(client_id: int) -> ClientRecord:
        return ClientRecord.objects.select_related("business_unit", "parent_client", "status").get(
            id=client_id
        )

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
    def list_categories(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        categories = (
            InternalCategoryRecord.objects.select_related("business_unit", "status")
            .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
            .order_by("business_unit__bu_code", "category_code")
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
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="INTERNAL_CATEGORY_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)

        category_code = str(payload.get("category_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not category_code:
            raise AuthError("INTERNAL_CATEGORY_CODE_REQUIRED", "Category code is required.", 400)
        if not name:
            raise AuthError("INTERNAL_CATEGORY_NAME_REQUIRED", "Category name is required.", 400)

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"

        try:
            category = InternalCategoryRecord.objects.create(
                business_unit=business_unit,
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
        actor_employee = _actor_employee(current_user)
        category = InternalCategoryManagementService._get_scoped_category(current_user, category_id)

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
            category = InternalCategoryRecord.objects.select_related("business_unit", "status").get(
                id=category_id
            )
        except InternalCategoryRecord.DoesNotExist as exc:
            raise AuthError(
                "INTERNAL_CATEGORY_NOT_FOUND", "Internal category not found.", 404
            ) from exc

        _ensure_business_units_in_scope(current_user, {category.business_unit_id})
        return category

    @staticmethod
    def _refresh_category(category_id: int) -> InternalCategoryRecord:
        return InternalCategoryRecord.objects.select_related("business_unit", "status").get(
            id=category_id
        )


class CostCenterManagementService:
    @staticmethod
    def list_cost_centers(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        cost_centers = (
            CostCenterRecord.objects.select_related("business_unit", "status")
            .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
            .order_by("business_unit__bu_code", "cost_center_code")
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
        actor_employee = _actor_employee(current_user)

        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="COST_CENTER_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)

        cost_center_code = str(payload.get("cost_center_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()
        if not cost_center_code:
            raise AuthError("COST_CENTER_CODE_REQUIRED", "Cost center code is required.", 400)
        if not name:
            raise AuthError("COST_CENTER_NAME_REQUIRED", "Cost center name is required.", 400)

        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"

        try:
            cost_center = CostCenterRecord.objects.create(
                business_unit=business_unit,
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
        actor_employee = _actor_employee(current_user)
        cost_center = CostCenterManagementService._get_scoped_cost_center(
            current_user, cost_center_id
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
            cost_center = CostCenterRecord.objects.select_related("business_unit", "status").get(
                id=cost_center_id
            )
        except CostCenterRecord.DoesNotExist as exc:
            raise AuthError("COST_CENTER_NOT_FOUND", "Cost center not found.", 404) from exc

        _ensure_business_units_in_scope(current_user, {cost_center.business_unit_id})
        return cost_center

    @staticmethod
    def _refresh_cost_center(cost_center_id: int) -> CostCenterRecord:
        return CostCenterRecord.objects.select_related("business_unit", "status").get(
            id=cost_center_id
        )


class GeneralChargeCodeManagementService:
    @staticmethod
    def list_general_charge_codes(current_user: CurrentUser) -> list[dict]:
        _ensure_ts_admin(current_user)
        general_charge_codes = (
            GeneralChargeCodeRecord.objects.select_related("business_unit", "charge_type", "status")
            .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
            .order_by("business_unit__bu_code", "code")
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
        actor_employee = _actor_employee(current_user)
        business_unit_id = _parse_required_int(
            payload.get("business_unit_id"),
            code="GENERAL_CHARGE_CODE_BUSINESS_UNIT_REQUIRED",
            message="business_unit_id is required.",
        )
        business_unit = _get_scoped_business_unit(current_user, business_unit_id)

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

        try:
            general_charge_code = GeneralChargeCodeRecord.objects.create(
                business_unit=business_unit,
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
        actor_employee = _actor_employee(current_user)
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            general_charge_code_id,
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
                "business_unit", "charge_type", "status"
            ).get(id=general_charge_code_id)
        except GeneralChargeCodeRecord.DoesNotExist as exc:
            raise AuthError(
                "GENERAL_CHARGE_CODE_NOT_FOUND",
                "General charge code not found.",
                404,
            ) from exc

        _ensure_business_units_in_scope(current_user, {general_charge_code.business_unit_id})
        return general_charge_code

    @staticmethod
    def _refresh_general_charge_code(
        general_charge_code_id: int,
    ) -> GeneralChargeCodeRecord:
        return GeneralChargeCodeRecord.objects.select_related(
            "business_unit", "charge_type", "status"
        ).get(id=general_charge_code_id)
