from datetime import date

import pytest
from django.test import Client

from apps.master_data.models import (
    Client as ClientRecord,
)
from apps.master_data.models import (
    CostCenter as CostCenterRecord,
)
from apps.master_data.models import (
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
)
from apps.master_data.models import (
    GeneralChargeCode as GeneralChargeCodeRecord,
)
from apps.master_data.models import (
    InternalCategory as InternalCategoryRecord,
)
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_client,
    create_employee,
    initialize_ui_session,
    seed_reference_data,
)


def _build_ts_admin_client() -> tuple[Client, Employee, list]:
    seed_reference_data()
    primary_business_unit = create_business_unit(bu_code="BU-SYS-1", name="System BU 1")
    secondary_business_unit = create_business_unit(bu_code="BU-SYS-2", name="System BU 2")
    employee = create_employee(
        employee_code="EMP-SYS-ADMIN",
        full_name="System Admin",
        email="system-admin@example.com",
        primary_business_unit=primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=primary_business_unit,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=secondary_business_unit,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="TS_ADMIN")

    client = Client()
    initialize_ui_session(client, employee.email)
    return client, employee, [primary_business_unit, secondary_business_unit]


@pytest.mark.django_db
def test_system_management_hub_shows_real_admin_screen_links() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ready now" in content
    assert "/system/employees/" in content
    assert "/system/clients/" in content
    assert "/system/general-charge-codes/" in content


@pytest.mark.django_db
def test_non_admin_cannot_open_employee_management_screen() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-NON-1", name="Non Admin BU")
    employee = create_employee(
        employee_code="EMP-NON-1",
        full_name="Regular User",
        email="regular-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_ui_session(client, employee.email)

    response = client.get("/system/employees/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()


@pytest.mark.django_db
def test_employee_management_create_and_update_flows_render_through_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_employee = create_employee(
        employee_code="EMP-MANAGED-1",
        full_name="Managed Employee",
        email="managed-employee@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=managed_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=managed_employee, role_code="USER")

    create_response = client.post(
        "/system/employees/",
        data={
            "employee_code": "EMP-NEW-1",
            "full_name": "New Employee",
            "email": "new-employee@example.com",
            "status_code": "ACTIVE",
            "primary_business_unit_id": str(business_units[0].id),
            "business_unit_ids": [str(business_units[0].id), str(business_units[1].id)],
            "role_codes": ["USER", "PROJECT_MANAGER"],
        },
        follow=False,
    )

    assert create_response.status_code == 302
    created_employee = Employee.objects.get(employee_code="EMP-NEW-1")
    assert created_employee.primary_business_unit_id == business_units[0].id

    core_response = client.post(
        f"/system/employees/{managed_employee.id}/",
        data={
            "form_name": "core",
            "full_name": "Managed Employee Updated",
            "email": "managed-employee-updated@example.com",
            "status_code": "INACTIVE",
        },
        follow=False,
    )
    assert core_response.status_code == 302

    managed_employee.refresh_from_db()
    assert managed_employee.full_name == "Managed Employee Updated"
    assert managed_employee.email == "managed-employee-updated@example.com"
    assert managed_employee.status.value_code == "INACTIVE"

    roles_response = client.post(
        f"/system/employees/{managed_employee.id}/",
        data={
            "form_name": "roles",
            "role_codes": ["USER", "PROJECT_OWNER"],
        },
        follow=False,
    )
    assert roles_response.status_code == 302
    active_roles = sorted(
        assignment.role.value_code
        for assignment in EmployeeRole.objects.select_related(
            "role", "status", "status__domain"
        ).filter(employee=managed_employee, valid_to__isnull=True)
        if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
        and assignment.status.value_code == "ACTIVE"
    )
    assert active_roles == ["PROJECT_OWNER", "USER"]

    business_unit_response = client.post(
        f"/system/employees/{managed_employee.id}/",
        data={
            "form_name": "business_units",
            "primary_business_unit_id": str(business_units[1].id),
            "business_unit_ids": [str(business_units[1].id)],
        },
        follow=False,
    )
    assert business_unit_response.status_code == 302

    managed_employee.refresh_from_db()
    assert managed_employee.primary_business_unit_id == business_units[1].id
    active_business_units = sorted(
        assignment.business_unit.bu_code
        for assignment in EmployeeBusinessUnit.objects.select_related(
            "business_unit",
            "status",
            "status__domain",
        ).filter(employee=managed_employee, valid_to__isnull=True)
        if assignment.status.domain.domain_code == "EMPLOYEE_BU_STATUS"
        and assignment.status.value_code == "ACTIVE"
    )
    assert active_business_units == ["BU-SYS-2"]


@pytest.mark.django_db
def test_client_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    existing_parent = create_client(
        business_unit=business_units[0],
        client_code="CLI-PARENT",
        name="Parent Client",
    )

    create_response = client.post(
        "/system/clients/",
        data={
            "business_unit_id": str(business_units[0].id),
            "client_code": "CLI-NEW",
            "name": "New Client",
            "status_code": "ACTIVE",
            "parent_client_id": str(existing_parent.id),
        },
        follow=False,
    )

    assert create_response.status_code == 302
    created_client = ClientRecord.objects.get(client_code="CLI-NEW")
    assert created_client.parent_client_id == existing_parent.id

    update_response = client.post(
        f"/system/clients/{created_client.id}/",
        data={
            "client_code": "CLI-NEW-UPDATED",
            "name": "New Client Updated",
            "status_code": "INACTIVE",
            "parent_client_id": "",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    created_client.refresh_from_db()
    assert created_client.client_code == "CLI-NEW-UPDATED"
    assert created_client.name == "New Client Updated"
    assert created_client.status.value_code == "INACTIVE"
    assert created_client.parent_client_id is None


@pytest.mark.django_db
def test_internal_category_and_cost_center_create_pages_work_through_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    category_response = client.post(
        "/system/internal-categories/",
        data={
            "business_unit_id": str(business_units[0].id),
            "category_code": "CAT-NEW",
            "name": "New Category",
            "description": "Category description",
            "status_code": "ACTIVE",
        },
        follow=False,
    )
    assert category_response.status_code == 302
    category = InternalCategoryRecord.objects.get(category_code="CAT-NEW")

    category_update_response = client.post(
        f"/system/internal-categories/{category.id}/",
        data={
            "category_code": "CAT-UPDATED",
            "name": "Updated Category",
            "description": "Updated description",
            "status_code": "INACTIVE",
        },
        follow=False,
    )
    assert category_update_response.status_code == 302
    category.refresh_from_db()
    assert category.category_code == "CAT-UPDATED"
    assert category.status.value_code == "INACTIVE"

    cost_center_response = client.post(
        "/system/cost-centers/",
        data={
            "business_unit_id": str(business_units[0].id),
            "cost_center_code": "CC-NEW",
            "name": "New Cost Center",
            "description": "Cost center description",
            "status_code": "ACTIVE",
        },
        follow=False,
    )
    assert cost_center_response.status_code == 302
    cost_center = CostCenterRecord.objects.get(cost_center_code="CC-NEW")

    cost_center_update_response = client.post(
        f"/system/cost-centers/{cost_center.id}/",
        data={
            "cost_center_code": "CC-UPDATED",
            "name": "Updated Cost Center",
            "description": "Updated cost center description",
            "status_code": "INACTIVE",
        },
        follow=False,
    )
    assert cost_center_update_response.status_code == 302
    cost_center.refresh_from_db()
    assert cost_center.cost_center_code == "CC-UPDATED"
    assert cost_center.status.value_code == "INACTIVE"


@pytest.mark.django_db
def test_general_charge_code_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    create_response = client.post(
        "/system/general-charge-codes/",
        data={
            "business_unit_id": str(business_units[0].id),
            "code": "GCC-NEW",
            "name": "New General Charge Code",
            "charge_type_code": "STANDARD",
            "billable_flag": "on",
            "common_code_flag": "on",
            "valid_from": date(2026, 4, 1).isoformat(),
            "valid_to": date(2026, 12, 31).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    general_charge_code = GeneralChargeCodeRecord.objects.get(code="GCC-NEW")
    assert general_charge_code.billable_flag is True
    assert general_charge_code.common_code_flag is True

    update_response = client.post(
        f"/system/general-charge-codes/{general_charge_code.id}/",
        data={
            "code": "GCC-UPDATED",
            "name": "Updated General Charge Code",
            "charge_type_code": "STANDARD",
            "requires_approval_flag": "on",
            "description_required_flag": "on",
            "valid_from": date(2026, 5, 1).isoformat(),
            "valid_to": "",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    general_charge_code.refresh_from_db()
    assert general_charge_code.code == "GCC-UPDATED"
    assert general_charge_code.requires_approval_flag is True
    assert general_charge_code.description_required_flag is True
    assert general_charge_code.valid_to is None
    assert general_charge_code.status.value_code == "INACTIVE"
