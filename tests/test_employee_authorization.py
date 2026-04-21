import json

import pytest
from django.test import Client

from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_employee,
    seed_reference_data,
)


def initialize_session(client: Client, validated_email: str) -> None:
    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": validated_email}),
        content_type="application/json",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_user_can_view_own_employee_record_only() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-101",
        full_name="Self User",
        email="self@example.com",
        primary_business_unit=business_unit,
    )
    other_employee = create_employee(
        employee_code="EMP-102",
        full_name="Other User",
        email="other@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=other_employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=other_employee, role_code="USER")

    client = Client()
    initialize_session(client, "self@example.com")

    own_response = client.get(f"/api/v1/employees/{employee.id}/")
    denied_response = client.get(f"/api/v1/employees/{other_employee.id}/")

    assert own_response.status_code == 200
    assert own_response.json()["employee"]["employee_code"] == "EMP-101"
    assert denied_response.status_code == 403
    assert denied_response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_employee_list_is_limited_to_assigned_business_units() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")

    admin_employee = create_employee(
        employee_code="EMP-201",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    in_scope_employee = create_employee(
        employee_code="EMP-202",
        full_name="In Scope",
        email="in-scope@example.com",
        primary_business_unit=admin_bu,
    )
    out_of_scope_employee = create_employee(
        employee_code="EMP-203",
        full_name="Out of Scope",
        email="out-scope@example.com",
        primary_business_unit=other_bu,
    )

    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=in_scope_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=out_of_scope_employee,
        business_unit=other_bu,
        is_primary_flag=True,
    )

    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=in_scope_employee, role_code="USER")
    assign_role(employee=out_of_scope_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get("/api/v1/employees/")

    assert response.status_code == 200
    employee_codes = [employee["employee_code"] for employee in response.json()["employees"]]
    assert employee_codes == ["EMP-201", "EMP-202"]


@pytest.mark.django_db
def test_ts_admin_cannot_view_employee_outside_business_unit_scope() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")

    admin_employee = create_employee(
        employee_code="EMP-301",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    other_employee = create_employee(
        employee_code="EMP-302",
        full_name="Other User",
        email="other@example.com",
        primary_business_unit=other_bu,
    )

    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=other_employee,
        business_unit=other_bu,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=other_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get(f"/api/v1/employees/{other_employee.id}/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_business_unit_list_returns_current_internal_scope() -> None:
    seed_reference_data()
    primary_bu = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    secondary_bu = create_business_unit(bu_code="BU-2", name="Business Unit 2")
    employee = create_employee(
        employee_code="EMP-401",
        full_name="Scoped User",
        email="scope@example.com",
        primary_business_unit=primary_bu,
    )

    assign_employee_to_business_unit(
        employee=employee,
        business_unit=primary_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=employee, business_unit=secondary_bu)
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_session(client, "scope@example.com")

    response = client.get("/api/v1/business-units/")

    assert response.status_code == 200
    bu_codes = [business_unit["bu_code"] for business_unit in response.json()["business_units"]]
    assert bu_codes == ["BU-1", "BU-2"]
