import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import Employee
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_country,
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
def test_ts_admin_can_create_employee_with_scoped_assignments() -> None:
    seed_reference_data()
    primary_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    admin_employee = create_employee(
        employee_code="EMP-501",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=primary_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=primary_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=admin_employee, business_unit=secondary_bu)
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=primary_bu)
    assign_role(employee=admin_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.post(
        "/api/v1/admin/employees/",
        data=json.dumps(
            {
                "employee_code": "EMP-502",
                "full_name": "New Employee",
                "email": "New.Employee@Example.com",
                "status_code": "ACTIVE",
                "primary_business_unit_id": secondary_bu.id,
                "business_unit_ids": [primary_bu.id, secondary_bu.id],
                "role_codes": ["USER"],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()["employee"]
    assert payload["employee_code"] == "EMP-502"
    assert payload["primary_business_unit"]["bu_code"] == "BU-OPS"
    assert payload["role_codes"] == ["USER"]
    assert [business_unit["bu_code"] for business_unit in payload["business_units"]] == [
        "BU-ADMIN",
        "BU-OPS",
    ]

    employee = Employee.objects.get(employee_code="EMP-502")
    assert employee.canonical_email == "new.employee@example.com"
    assert (
        AuditLog.objects.filter(entity_name="employee", action_type__value_code="CREATE").count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="employee_business_unit",
            field_name="business_unit_scope",
            new_value="BU-ADMIN,BU-OPS",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="employee_role",
            field_name="role_code",
            new_value="USER",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_non_admin_is_denied_employee_create() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-601",
        full_name="Regular User",
        email="user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_session(client, "user@example.com")

    response = client.post(
        "/api/v1/admin/employees/",
        data=json.dumps(
            {
                "employee_code": "EMP-602",
                "full_name": "Blocked Employee",
                "email": "blocked@example.com",
                "primary_business_unit_id": business_unit.id,
                "business_unit_ids": [business_unit.id],
                "role_codes": ["USER"],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_cannot_create_employee_with_out_of_scope_business_unit() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-701",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.post(
        "/api/v1/admin/employees/",
        data=json.dumps(
            {
                "employee_code": "EMP-702",
                "full_name": "Out Scope",
                "email": "out-scope@example.com",
                "primary_business_unit_id": other_bu.id,
                "business_unit_ids": [other_bu.id],
                "role_codes": ["USER"],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"


@pytest.mark.django_db
def test_ts_admin_cannot_create_employee_with_business_units_from_multiple_countries() -> None:
    seed_reference_data()
    holding_country = create_country(country_name="Test Holding Country")
    other_country = create_country(country_name="Test Other Country")
    primary_bu = create_business_unit(
        bu_code="BU-ADMIN",
        name="Admin BU",
        country=holding_country,
    )
    foreign_bu = create_business_unit(
        bu_code="BU-OTHER-COUNTRY",
        name="Other Country BU",
        country=other_country,
    )
    admin_employee = create_employee(
        employee_code="EMP-703",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=primary_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=primary_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=admin_employee, business_unit=foreign_bu)
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=primary_bu)
    assign_role(employee=admin_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.post(
        "/api/v1/admin/employees/",
        data=json.dumps(
            {
                "employee_code": "EMP-704",
                "full_name": "Cross Country Scope",
                "email": "cross-country@example.com",
                "primary_business_unit_id": primary_bu.id,
                "business_unit_ids": [primary_bu.id, foreign_bu.id],
                "role_codes": ["USER"],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPLOYEE_BUSINESS_UNIT_COUNTRY_MISMATCH"


@pytest.mark.django_db
def test_ts_admin_cannot_update_employee_outside_scope() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-801",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-802",
        full_name="Other Scope",
        email="target@example.com",
        primary_business_unit=other_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=target_employee,
        business_unit=other_bu,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=target_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.patch(
        f"/api/v1/admin/employees/{target_employee.id}/",
        data=json.dumps({"full_name": "Blocked Update"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_can_update_employee_roles_and_business_units_with_audit() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    admin_employee = create_employee(
        employee_code="EMP-901",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-902",
        full_name="Target User",
        email="target@example.com",
        primary_business_unit=admin_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=admin_employee, business_unit=secondary_bu)
    assign_employee_to_business_unit(
        employee=target_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=target_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    update_response = client.patch(
        f"/api/v1/admin/employees/{target_employee.id}/",
        data=json.dumps(
            {
                "full_name": "Updated Target User",
                "email": "updated.target@example.com",
            }
        ),
        content_type="application/json",
    )
    roles_response = client.put(
        f"/api/v1/admin/employees/{target_employee.id}/roles/",
        data=json.dumps({"role_codes": ["PROJECT_MANAGER"]}),
        content_type="application/json",
    )
    business_units_response = client.put(
        f"/api/v1/admin/employees/{target_employee.id}/business-units/",
        data=json.dumps(
            {
                "primary_business_unit_id": secondary_bu.id,
                "business_unit_ids": [admin_bu.id, secondary_bu.id],
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    assert roles_response.status_code == 200
    assert business_units_response.status_code == 200
    assert (
        business_units_response.json()["employee"]["primary_business_unit"]["bu_code"] == "BU-OPS"
    )
    assert business_units_response.json()["employee"]["role_codes"] == ["PROJECT_MANAGER"]

    target_employee.refresh_from_db()
    assert target_employee.full_name == "Updated Target User"
    assert target_employee.email == "updated.target@example.com"
    assert target_employee.canonical_email == "updated.target@example.com"
    assert target_employee.primary_business_unit_id == secondary_bu.id

    assert AuditLog.objects.filter(entity_name="employee", field_name="email").count() == 1
    assert AuditLog.objects.filter(entity_name="employee", field_name="full_name").count() == 1
    assert (
        AuditLog.objects.filter(
            entity_name="employee_role",
            field_name="role_code",
            old_value="USER",
            new_value="",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="employee_role",
            field_name="role_code",
            old_value="",
            new_value="PROJECT_MANAGER",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="employee",
            field_name="primary_business_unit",
            old_value="BU-ADMIN",
            new_value="BU-OPS",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="employee_business_unit",
            field_name="business_unit_scope",
            old_value="BU-ADMIN",
            new_value="BU-ADMIN,BU-OPS",
        ).count()
        == 1
    )
