import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_client,
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
def test_ts_admin_client_list_is_limited_to_assigned_business_units() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1001",
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

    create_client(business_unit=admin_bu, client_code="CLIENT-1", name="Scoped Client")
    create_client(business_unit=other_bu, client_code="CLIENT-2", name="Other Client")

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get("/api/v1/admin/clients/")

    assert response.status_code == 200
    assert [item["client_code"] for item in response.json()["clients"]] == ["CLIENT-1"]


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_client_with_audit() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-1002",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=business_unit)
    assign_role(employee=admin_employee, role_code="USER")

    parent_client = create_client(
        business_unit=business_unit,
        client_code="CLIENT-PARENT",
        name="Parent Client",
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    create_response = client.post(
        "/api/v1/admin/clients/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "client_code": "CLIENT-NEW",
                "name": "New Client",
                "parent_client_id": parent_client.id,
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_client = create_response.json()["client"]
    assert created_client["client_code"] == "CLIENT-NEW"
    assert created_client["parent_client"]["client_code"] == "CLIENT-PARENT"

    update_response = client.patch(
        f"/api/v1/admin/clients/{created_client['id']}/",
        data=json.dumps(
            {
                "client_code": "CLIENT-UPDATED",
                "name": "Updated Client",
                "status_code": "INACTIVE",
                "parent_client_id": None,
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_client = update_response.json()["client"]
    assert updated_client["client_code"] == "CLIENT-UPDATED"
    assert updated_client["name"] == "Updated Client"
    assert updated_client["status"] == "INACTIVE"
    assert updated_client["parent_client"] is None

    assert (
        AuditLog.objects.filter(entity_name="client", action_type__value_code="CREATE").count() == 1
    )
    assert AuditLog.objects.filter(entity_name="client", field_name="client_code").count() == 1
    assert AuditLog.objects.filter(entity_name="client", field_name="name").count() == 1
    assert AuditLog.objects.filter(entity_name="client", field_name="status").count() == 1
    assert (
        AuditLog.objects.filter(
            entity_name="client",
            field_name="parent_client",
            old_value="CLIENT-PARENT",
            new_value="",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_non_admin_is_denied_client_admin_endpoints() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-1003",
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

    response = client.get("/api/v1/admin/clients/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_cannot_view_or_create_out_of_scope_client() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1004",
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

    other_client = create_client(
        business_unit=other_bu,
        client_code="CLIENT-OTHER",
        name="Other Client",
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    detail_response = client.get(f"/api/v1/admin/clients/{other_client.id}/")
    create_response = client.post(
        "/api/v1/admin/clients/",
        data=json.dumps(
            {
                "business_unit_id": other_bu.id,
                "client_code": "CLIENT-DENIED",
                "name": "Denied Client",
            }
        ),
        content_type="application/json",
    )

    assert detail_response.status_code == 403
    assert detail_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
    assert create_response.status_code == 403
    assert create_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
