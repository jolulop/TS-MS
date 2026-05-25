import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import Employee, EmployeeBusinessUnit
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_employee,
    create_office,
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
    holding_country = create_office(office_name="Test Holding Office")
    other_country = create_office(office_name="Test Other Office")
    primary_bu = create_business_unit(
        bu_code="BU-ADMIN",
        name="Admin BU",
        office=holding_country,
    )
    foreign_bu = create_business_unit(
        bu_code="BU-OTHER-COUNTRY",
        name="Other Office BU",
        office=other_country,
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
                "full_name": "Cross Office Scope",
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
def test_creating_ts_admin_employee_expands_scope_to_all_office_business_units() -> None:
    seed_reference_data()
    primary_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    hidden_bu = create_business_unit(bu_code="BU-HIDDEN", name="Hidden BU")
    admin_employee = create_employee(
        employee_code="EMP-704A",
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
    assign_role(employee=admin_employee, role_code="TS_ADMIN")
    assign_role(employee=admin_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.post(
        "/api/v1/admin/employees/",
        data=json.dumps(
            {
                "employee_code": "EMP-704B",
                "full_name": "New Office Admin",
                "email": "new-office-admin@example.com",
                "status_code": "ACTIVE",
                "primary_business_unit_id": primary_bu.id,
                "business_unit_ids": [primary_bu.id],
                "role_codes": ["TS_ADMIN", "USER"],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()["employee"]
    assert [business_unit["bu_code"] for business_unit in payload["business_units"]] == [
        "BU-ADMIN",
        "BU-HIDDEN",
        "BU-OPS",
    ]
    assert payload["role_codes"] == ["TS_ADMIN", "USER"]
    assert EmployeeBusinessUnit.objects.filter(
        employee__employee_code="EMP-704B",
        business_unit=hidden_bu,
        valid_to__isnull=True,
    ).exists()


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


@pytest.mark.django_db
def test_assigning_ts_admin_role_expands_employee_scope_to_full_office() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    hidden_bu = create_business_unit(bu_code="BU-HIDDEN", name="Hidden BU")
    admin_employee = create_employee(
        employee_code="EMP-903",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-904",
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
    assign_role(employee=admin_employee, role_code="TS_ADMIN")
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=target_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.put(
        f"/api/v1/admin/employees/{target_employee.id}/roles/",
        data=json.dumps({"role_codes": ["TS_ADMIN", "USER"]}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()["employee"]
    assert payload["role_codes"] == ["TS_ADMIN", "USER"]
    assert [business_unit["bu_code"] for business_unit in payload["business_units"]] == [
        "BU-ADMIN",
        "BU-HIDDEN",
        "BU-OPS",
    ]
    assert EmployeeBusinessUnit.objects.filter(
        employee=target_employee,
        business_unit=hidden_bu,
        valid_to__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_ts_admin_employee_scope_cannot_be_narrowed_below_full_office() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    hidden_bu = create_business_unit(bu_code="BU-HIDDEN", name="Hidden BU")
    admin_employee = create_employee(
        employee_code="EMP-905",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-906",
        full_name="Target Admin",
        email="target-admin@example.com",
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
    assign_employee_to_business_unit(employee=target_employee, business_unit=secondary_bu)
    assign_employee_to_business_unit(employee=target_employee, business_unit=hidden_bu)
    assign_role(employee=admin_employee, role_code="TS_ADMIN")
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=target_employee, role_code="TS_ADMIN")
    assign_role(employee=target_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.put(
        f"/api/v1/admin/employees/{target_employee.id}/business-units/",
        data=json.dumps(
            {
                "primary_business_unit_id": secondary_bu.id,
                "business_unit_ids": [secondary_bu.id],
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()["employee"]
    assert payload["primary_business_unit"]["bu_code"] == "BU-OPS"
    assert [business_unit["bu_code"] for business_unit in payload["business_units"]] == [
        "BU-ADMIN",
        "BU-HIDDEN",
        "BU-OPS",
    ]


@pytest.mark.django_db
def test_ts_admin_can_list_scoped_employees_with_status_filter() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    foreign_office = create_office(office_name="Foreign Office")
    foreign_bu = create_business_unit(
        bu_code="BU-FOREIGN",
        name="Foreign BU",
        office=foreign_office,
    )
    admin_employee = create_employee(
        employee_code="EMP-LIST-ADMIN",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    active_target = create_employee(
        employee_code="EMP-LIST-ACTIVE",
        full_name="Active Target",
        email="active.target@example.com",
        primary_business_unit=secondary_bu,
    )
    inactive_target = create_employee(
        employee_code="EMP-LIST-INACTIVE",
        full_name="Inactive Target",
        email="inactive.target@example.com",
        primary_business_unit=admin_bu,
        active=False,
    )
    foreign_target = create_employee(
        employee_code="EMP-LIST-FOREIGN",
        full_name="Foreign Target",
        email="foreign.target@example.com",
        primary_business_unit=foreign_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=admin_employee, business_unit=secondary_bu)
    assign_employee_to_business_unit(
        employee=active_target,
        business_unit=secondary_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=inactive_target,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=foreign_target,
        business_unit=foreign_bu,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=active_target, role_code="USER")
    assign_role(employee=inactive_target, role_code="USER")
    assign_role(employee=foreign_target, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get("/api/v1/admin/employees/")
    inactive_response = client.get("/api/v1/admin/employees/?status=INACTIVE")

    assert response.status_code == 200
    assert [employee["employee_code"] for employee in response.json()["employees"]] == [
        "EMP-LIST-ACTIVE",
        "EMP-LIST-ADMIN",
        "EMP-LIST-INACTIVE",
    ]
    assert inactive_response.status_code == 200
    assert [employee["employee_code"] for employee in inactive_response.json()["employees"]] == [
        "EMP-LIST-INACTIVE"
    ]


@pytest.mark.django_db
def test_ts_admin_can_get_scoped_employee_detail() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    secondary_bu = create_business_unit(bu_code="BU-OPS", name="Operations BU")
    admin_employee = create_employee(
        employee_code="EMP-DETAIL-ADMIN",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-DETAIL-TARGET",
        full_name="Detail Target",
        email="detail.target@example.com",
        primary_business_unit=secondary_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=admin_employee, business_unit=secondary_bu)
    assign_employee_to_business_unit(
        employee=target_employee,
        business_unit=secondary_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(employee=target_employee, business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=target_employee, role_code="PROJECT_MANAGER")
    assign_role(employee=target_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get(f"/api/v1/admin/employees/{target_employee.id}/")

    assert response.status_code == 200
    payload = response.json()["employee"]
    assert payload["employee_code"] == "EMP-DETAIL-TARGET"
    assert payload["primary_business_unit"]["bu_code"] == "BU-OPS"
    assert payload["role_codes"] == ["PROJECT_MANAGER", "USER"]
    assert [business_unit["bu_code"] for business_unit in payload["business_units"]] == [
        "BU-ADMIN",
        "BU-OPS",
    ]


@pytest.mark.django_db
def test_ts_admin_can_delete_unreferenced_scoped_employee_via_api() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-DELETE-ADMIN",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-DELETE-TARGET",
        full_name="Delete Target",
        email="delete.target@example.com",
        primary_business_unit=admin_bu,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
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

    response = client.delete(f"/api/v1/admin/employees/{target_employee.id}/")

    assert response.status_code == 200
    assert response.json() == {
        "deleted": True,
        "entity": "employee",
        "id": target_employee.id,
    }
    assert not Employee.objects.filter(id=target_employee.id).exists()


@pytest.mark.django_db
def test_ts_admin_employee_delete_returns_structured_blocked_error_and_audits() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-BLOCK-ADMIN",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=admin_bu,
    )
    target_employee = create_employee(
        employee_code="EMP-BLOCK-TARGET",
        full_name="Blocked Target",
        email="blocked.target@example.com",
        primary_business_unit=admin_bu,
    )
    direct_report = create_employee(
        employee_code="EMP-BLOCK-REPORT",
        full_name="Direct Report",
        email="direct.report@example.com",
        primary_business_unit=admin_bu,
    )
    direct_report.manager_employee = target_employee
    direct_report.save(update_fields=["manager_employee"])
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=target_employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=direct_report,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=admin_bu)
    assign_role(employee=admin_employee, role_code="USER")
    assign_role(employee=target_employee, role_code="USER")
    assign_role(employee=direct_report, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.delete(f"/api/v1/admin/employees/{target_employee.id}/")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPLOYEE_DELETE_BLOCKED"
    assert AuditLog.objects.filter(
        entity_name="employee",
        entity_id=target_employee.id,
        action_type__value_code="DENY",
    ).exists()
