import json
from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    CalendarSpecialDay,
    Employee,
    GeneralChargeCode,
    GeneralChargeCodeApprovalRole,
    PricingModel,
    Project,
    ProjectAssignment,
    YearlyCalendar,
)
from apps.master_data.models import Client as ClientRecord
from apps.master_data.models import CostCenter as CostCenterRecord
from apps.master_data.models import InternalCategory as InternalCategoryRecord
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_project,
    assign_role,
    create_business_unit,
    create_calendar_period_rule,
    create_calendar_special_day,
    create_client,
    create_cost_center,
    create_employee,
    create_general_charge_code,
    create_general_charge_code_approval_role,
    create_internal_category,
    create_office,
    create_pricing_model,
    create_project,
    create_yearly_calendar,
    seed_reference_data,
)


def initialize_session(client: Client, validated_email: str) -> None:
    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": validated_email}),
        content_type="application/json",
    )
    assert response.status_code == 201


def create_ts_admin_client() -> tuple[Client, Employee, BusinessUnit]:
    office = create_office(office_name="Scoped API Office")
    business_unit = create_business_unit(
        bu_code="API-ADMIN-BU",
        name="API Admin BU",
        office=office,
    )
    admin = create_employee(
        employee_code="EMP-API-TS-ADMIN",
        full_name="Scoped API Admin",
        email="scoped-api-admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=admin,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin, role_code="USER")
    assign_role(employee=admin, role_code="TS_ADMIN", business_unit=business_unit)
    client = Client()
    initialize_session(client, admin.email)
    return client, admin, business_unit


def _create_project_context(
    *,
    business_unit: BusinessUnit,
    suffix: str,
) -> dict:
    owner = create_employee(
        employee_code=f"EMP-OWNER-{suffix}",
        full_name=f"Owner {suffix}",
        email=f"owner-{suffix.lower()}@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=owner,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=owner, role_code="USER")
    assign_role(employee=owner, role_code="PROJECT_OWNER")

    manager = create_employee(
        employee_code=f"EMP-MANAGER-{suffix}",
        full_name=f"Manager {suffix}",
        email=f"manager-{suffix.lower()}@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=manager,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=manager, role_code="USER")
    assign_role(employee=manager, role_code="PROJECT_MANAGER")

    client = create_client(
        business_unit=business_unit,
        client_code=f"CLI-{suffix}",
        name=f"Client {suffix}",
    )
    category = create_internal_category(
        business_unit=business_unit,
        category_code=f"CAT-{suffix}",
        name=f"Category {suffix}",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code=f"CC-{suffix}",
        name=f"Cost Center {suffix}",
    )
    pricing_model = create_pricing_model(
        business_unit=business_unit,
        name=f"Pricing Model {suffix}",
    )
    project = create_project(
        business_unit=business_unit,
        project_code=f"PRJ-{suffix}",
        name=f"Project {suffix}",
        project_owner_employee=owner,
        project_manager_employee=manager,
        client=client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 1, 1),
    )
    return {
        "project": project,
        "client": client,
        "category": category,
        "cost_center": cost_center,
        "pricing_model": pricing_model,
    }


@pytest.mark.django_db
def test_ts_admin_can_delete_unused_scoped_entities_via_api() -> None:
    seed_reference_data()
    client, admin, business_unit = create_ts_admin_client()

    delete_business_unit = create_business_unit(
        bu_code="API-DELETE-BU",
        name="Delete BU",
        office=business_unit.office,
    )
    assign_employee_to_business_unit(
        employee=admin,
        business_unit=delete_business_unit,
        is_primary_flag=False,
    )
    delete_client = create_client(
        business_unit=business_unit,
        client_code="CLI-DELETE-API",
        name="Delete Client",
    )
    delete_category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT-DELETE-API",
        name="Delete Category",
    )
    delete_cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-DELETE-API",
        name="Delete Cost Center",
    )
    delete_pricing_model = create_pricing_model(
        business_unit=business_unit,
        name="Delete Pricing Model",
    )
    delete_approval_role = create_general_charge_code_approval_role(
        office=business_unit.office,
        role_code="API-DEL-ROLE",
        name="Delete Approval Role",
    )
    delete_gcc = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-DELETE-API",
        name="Delete GCC",
        cost_center=delete_cost_center,
        valid_from=date(2026, 1, 1),
    )
    delete_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2028,
        calendar_name="Delete Calendar",
    )
    special_day_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2029,
        calendar_name="Special Day Calendar",
    )
    delete_special_day = create_calendar_special_day(
        yearly_calendar=special_day_calendar,
        special_date=date(2029, 5, 1),
    )
    period_rule_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2030,
        calendar_name="Rule Calendar",
    )
    delete_period_rule = create_calendar_period_rule(
        yearly_calendar=period_rule_calendar,
        business_unit=business_unit,
        effective_from=date(2030, 1, 1),
        effective_to=date(2030, 12, 31),
    )
    project_context = _create_project_context(business_unit=business_unit, suffix="DELETE")
    delete_project = project_context["project"]
    assignment_context = _create_project_context(business_unit=business_unit, suffix="ASSIGN")
    assignee = create_employee(
        employee_code="EMP-ASSIGNEE-DELETE-API",
        full_name="Delete Assignment Employee",
        email="delete-assignment-employee@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=assignee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=assignee, role_code="USER")
    delete_assignment = assign_project(
        project=assignment_context["project"],
        employee=assignee,
        assignment_start_date=date(2026, 1, 1),
    )

    cases = [
        (
            f"/api/v1/admin/business-units/{delete_business_unit.id}/",
            BusinessUnit,
            delete_business_unit.id,
            "business_unit",
        ),
        (
            f"/api/v1/admin/clients/{delete_client.id}/",
            ClientRecord,
            delete_client.id,
            "client",
        ),
        (
            f"/api/v1/admin/internal-categories/{delete_category.id}/",
            InternalCategoryRecord,
            delete_category.id,
            "internal_category",
        ),
        (
            f"/api/v1/admin/pricing-models/{delete_pricing_model.id}/",
            PricingModel,
            delete_pricing_model.id,
            "pricing_model",
        ),
        (
            f"/api/v1/admin/general-charge-code-approval-roles/{delete_approval_role.id}/",
            GeneralChargeCodeApprovalRole,
            delete_approval_role.id,
            "general_charge_code_approval_role",
        ),
        (
            f"/api/v1/admin/general-charge-codes/{delete_gcc.id}/",
            GeneralChargeCode,
            delete_gcc.id,
            "general_charge_code",
        ),
        (
            f"/api/v1/admin/cost-centers/{delete_cost_center.id}/",
            CostCenterRecord,
            delete_cost_center.id,
            "cost_center",
        ),
        (
            f"/api/v1/admin/yearly-calendars/{delete_calendar.id}/",
            YearlyCalendar,
            delete_calendar.id,
            "yearly_calendar",
        ),
        (
            f"/api/v1/admin/calendar-special-days/{delete_special_day.id}/",
            CalendarSpecialDay,
            delete_special_day.id,
            "calendar_special_day",
        ),
        (
            f"/api/v1/admin/calendar-period-rules/{delete_period_rule.id}/",
            CalendarPeriodRule,
            delete_period_rule.id,
            "calendar_period_rule",
        ),
        (
            f"/api/v1/admin/projects/{delete_project.id}/",
            Project,
            delete_project.id,
            "project",
        ),
        (
            f"/api/v1/admin/project-assignments/{delete_assignment.id}/",
            ProjectAssignment,
            delete_assignment.id,
            "project_assignment",
        ),
    ]

    for path, model_class, entity_id, entity_name in cases:
        response = client.delete(path)

        assert response.status_code == 200
        assert response.json() == {"deleted": True, "entity": entity_name, "id": entity_id}
        assert not model_class.objects.filter(id=entity_id).exists()
        assert AuditLog.objects.filter(
            entity_name=entity_name,
            entity_id=entity_id,
            action_type__value_code="DELETE",
            actor_email="scoped-api-admin@example.com",
        ).exists()


@pytest.mark.django_db
def test_ts_admin_delete_is_guarded_for_scoped_entities_via_api() -> None:
    seed_reference_data()
    client, admin, business_unit = create_ts_admin_client()

    blocked_business_unit = create_business_unit(
        bu_code="API-BLOCK-BU",
        name="Blocked BU",
        office=business_unit.office,
    )
    assign_employee_to_business_unit(
        employee=admin,
        business_unit=blocked_business_unit,
        is_primary_flag=False,
    )
    _create_project_context(
        business_unit=blocked_business_unit,
        suffix="BUBLOCK",
    )
    blocked_client_parent = create_client(
        business_unit=business_unit,
        client_code="CLI-PARENT-BLOCK-API",
        name="Blocked Parent Client",
    )
    create_client(
        business_unit=business_unit,
        client_code="CLI-CHILD-BLOCK-API",
        name="Blocked Child Client",
        parent_client=blocked_client_parent,
    )
    blocked_category_context = _create_project_context(
        business_unit=business_unit,
        suffix="CATBLOCK",
    )
    blocked_cost_center_context = _create_project_context(
        business_unit=business_unit,
        suffix="CCBLOCK",
    )
    blocked_pricing_context = _create_project_context(
        business_unit=business_unit,
        suffix="PMBLOCK",
    )
    blocked_approval_role = create_general_charge_code_approval_role(
        office=business_unit.office,
        role_code="API-BLOCK-ROLE",
        name="Blocked Approval Role",
    )
    blocked_gcc_for_role = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-BLOCK-ROLE-API",
        name="Blocked GCC Approval Role",
        cost_center=blocked_cost_center_context["cost_center"],
        valid_from=date(2026, 1, 1),
        ad_hoc_approval_roles=[blocked_approval_role],
    )
    blocked_gcc = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-BLOCK-API",
        name="Blocked GCC",
        cost_center=blocked_cost_center_context["cost_center"],
        valid_from=date(2026, 1, 1),
        approver_role_codes=["PROJECT_MANAGER"],
    )
    blocked_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2031,
        calendar_name="Blocked Calendar",
    )
    create_calendar_special_day(
        yearly_calendar=blocked_calendar,
        special_date=date(2031, 12, 25),
    )
    blocked_project_context = _create_project_context(
        business_unit=business_unit,
        suffix="PRJBLOCK",
    )
    blocked_assignment_employee = create_employee(
        employee_code="EMP-API-BLOCK-ASSIGN",
        full_name="Blocked Assignment Employee",
        email="blocked-assignment-employee@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=blocked_assignment_employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=blocked_assignment_employee, role_code="USER")
    create_assignment = assign_project(
        project=blocked_project_context["project"],
        employee=blocked_assignment_employee,
        assignment_start_date=date(2026, 1, 1),
    )

    cases = [
        (
            f"/api/v1/admin/business-units/{blocked_business_unit.id}/",
            "BUSINESS_UNIT_DELETE_BLOCKED",
            BusinessUnit,
            blocked_business_unit.id,
            "business_unit",
        ),
        (
            f"/api/v1/admin/clients/{blocked_client_parent.id}/",
            "CLIENT_DELETE_BLOCKED",
            ClientRecord,
            blocked_client_parent.id,
            "client",
        ),
        (
            f"/api/v1/admin/internal-categories/{blocked_category_context['category'].id}/",
            "INTERNAL_CATEGORY_DELETE_BLOCKED",
            InternalCategoryRecord,
            blocked_category_context["category"].id,
            "internal_category",
        ),
        (
            f"/api/v1/admin/cost-centers/{blocked_cost_center_context['cost_center'].id}/",
            "COST_CENTER_DELETE_BLOCKED",
            CostCenterRecord,
            blocked_cost_center_context["cost_center"].id,
            "cost_center",
        ),
        (
            f"/api/v1/admin/pricing-models/{blocked_pricing_context['pricing_model'].id}/",
            "PRICING_MODEL_DELETE_BLOCKED",
            PricingModel,
            blocked_pricing_context["pricing_model"].id,
            "pricing_model",
        ),
        (
            f"/api/v1/admin/general-charge-code-approval-roles/{blocked_approval_role.id}/",
            "GENERAL_CHARGE_CODE_APPROVAL_ROLE_DELETE_BLOCKED",
            GeneralChargeCodeApprovalRole,
            blocked_approval_role.id,
            "general_charge_code_approval_role",
        ),
        (
            f"/api/v1/admin/general-charge-codes/{blocked_gcc.id}/",
            "GENERAL_CHARGE_CODE_DELETE_BLOCKED",
            GeneralChargeCode,
            blocked_gcc.id,
            "general_charge_code",
        ),
        (
            f"/api/v1/admin/yearly-calendars/{blocked_calendar.id}/",
            "YEARLY_CALENDAR_DELETE_BLOCKED",
            YearlyCalendar,
            blocked_calendar.id,
            "yearly_calendar",
        ),
        (
            f"/api/v1/admin/projects/{blocked_project_context['project'].id}/",
            "PROJECT_DELETE_BLOCKED",
            Project,
            blocked_project_context["project"].id,
            "project",
        ),
    ]

    assert blocked_gcc_for_role.id is not None
    assert create_assignment.id is not None

    for path, error_code, model_class, entity_id, entity_name in cases:
        response = client.delete(path)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == error_code
        assert model_class.objects.filter(id=entity_id).exists()
        assert AuditLog.objects.filter(
            entity_name=entity_name,
            entity_id=entity_id,
            action_type__value_code="DENY",
            actor_email="scoped-api-admin@example.com",
        ).exists()
