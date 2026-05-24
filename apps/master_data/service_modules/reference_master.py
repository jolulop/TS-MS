from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.master_data.models import Client as ClientRecord
from apps.master_data.models import CostCenter as CostCenterRecord
from apps.master_data.models import InternalCategory as InternalCategoryRecord
from apps.master_data.models import PricingModel as PricingModelRecord
from apps.master_data.models import Project


def _master_services():
    from apps.master_data import services

    return services


def _actor_employee(current_user):
    return _master_services()._actor_employee(current_user)


def _apply_status_filter(queryset, status_code):
    return _master_services()._apply_status_filter(queryset, status_code)


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


def _get_scoped_business_unit(current_user: CurrentUser, business_unit_id: int):
    return _master_services()._get_scoped_business_unit(current_user, business_unit_id)


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    return _master_services()._parse_required_int(value, code=code, message=message)


def _parse_status_filter(status_code, *, domain_code: str):
    return _master_services()._parse_status_filter(status_code, domain_code=domain_code)


def _ref_value(domain_code: str, value_code: str):
    return _master_services()._ref_value(domain_code, value_code)


def _serialize_client(
    client: ClientRecord,
    *,
    project_business_unit_summaries: list[dict] | None = None,
) -> dict:
    return _master_services()._serialize_client(
        client,
        project_business_unit_summaries=project_business_unit_summaries,
    )


def _serialize_cost_center(cost_center: CostCenterRecord) -> dict:
    return _master_services()._serialize_cost_center(cost_center)


def _serialize_internal_category(category: InternalCategoryRecord) -> dict:
    return _master_services()._serialize_internal_category(category)


def _serialize_pricing_model(pricing_model: PricingModelRecord) -> dict:
    return _master_services()._serialize_pricing_model(pricing_model)


def _validate_optional_office_payload(payload: dict, **kwargs) -> None:
    return _master_services()._validate_optional_office_payload(payload, **kwargs)


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
        client_ids = [client.id for client in clients]
        summary_map: dict[int, list[dict]] = {}
        if client_ids:
            summary_rows = (
                Project.objects.filter(
                    office_id=current_user.office_id,
                    status__value_code="ACTIVE",
                    client_id__in=client_ids,
                )
                .values(
                    "client_id",
                    "business_unit_id",
                    "business_unit__bu_code",
                    "business_unit__name",
                )
                .annotate(
                    active_project_count=Count("id", distinct=True),
                    active_employee_count=Count(
                        "assignments__employee_id",
                        filter=Q(
                            assignments__status__value_code="ACTIVE",
                            assignments__employee__status__value_code="ACTIVE",
                        ),
                        distinct=True,
                    ),
                )
                .order_by("client_id", "business_unit__bu_code")
            )
            for summary in summary_rows:
                summary_map.setdefault(summary["client_id"], []).append(
                    {
                        "business_unit": {
                            "id": summary["business_unit_id"],
                            "bu_code": summary["business_unit__bu_code"],
                            "name": summary["business_unit__name"],
                        },
                        "active_project_count": summary["active_project_count"],
                        "active_employee_count": summary["active_employee_count"],
                    }
                )
        return [
            _serialize_client(
                client,
                project_business_unit_summaries=summary_map.get(client.id, []),
            )
            for client in clients
        ]

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
