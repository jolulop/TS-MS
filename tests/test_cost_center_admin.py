import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_cost_center,
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
def test_ts_admin_cost_center_list_is_limited_to_assigned_business_units() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1201",
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

    create_cost_center(
        business_unit=admin_bu,
        cost_center_code="CC-1",
        name="Scoped Cost Center",
    )
    create_cost_center(
        business_unit=other_bu,
        cost_center_code="CC-2",
        name="Other Cost Center",
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get("/api/v1/admin/cost-centers/")

    assert response.status_code == 200
    assert [item["cost_center_code"] for item in response.json()["cost_centers"]] == ["CC-1"]


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_cost_center_with_audit() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-1202",
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

    client = Client()
    initialize_session(client, "admin@example.com")

    create_response = client.post(
        "/api/v1/admin/cost-centers/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "cost_center_code": "CC-NEW",
                "name": "New Cost Center",
                "description": "Initial description",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_cost_center = create_response.json()["cost_center"]
    assert created_cost_center["cost_center_code"] == "CC-NEW"
    assert created_cost_center["description"] == "Initial description"

    update_response = client.patch(
        f"/api/v1/admin/cost-centers/{created_cost_center['id']}/",
        data=json.dumps(
            {
                "cost_center_code": "CC-UPD",
                "name": "Updated Cost Center",
                "description": "Updated description",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_cost_center = update_response.json()["cost_center"]
    assert updated_cost_center["cost_center_code"] == "CC-UPD"
    assert updated_cost_center["name"] == "Updated Cost Center"
    assert updated_cost_center["description"] == "Updated description"
    assert updated_cost_center["status"] == "INACTIVE"

    assert (
        AuditLog.objects.filter(
            entity_name="cost_center",
            action_type__value_code="CREATE",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="cost_center", field_name="cost_center_code").count()
        == 1
    )
    assert AuditLog.objects.filter(entity_name="cost_center", field_name="name").count() == 1
    assert AuditLog.objects.filter(entity_name="cost_center", field_name="description").count() == 1
    assert AuditLog.objects.filter(entity_name="cost_center", field_name="status").count() == 1


@pytest.mark.django_db
def test_non_admin_is_denied_cost_center_admin_endpoints() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-1203",
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

    response = client.get("/api/v1/admin/cost-centers/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_cannot_view_or_create_out_of_scope_cost_center() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1204",
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

    other_cost_center = create_cost_center(
        business_unit=other_bu,
        cost_center_code="CC-OTHER",
        name="Other Cost Center",
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    detail_response = client.get(f"/api/v1/admin/cost-centers/{other_cost_center.id}/")
    create_response = client.post(
        "/api/v1/admin/cost-centers/",
        data=json.dumps(
            {
                "business_unit_id": other_bu.id,
                "cost_center_code": "CC-DENIED",
                "name": "Denied Cost Center",
            }
        ),
        content_type="application/json",
    )

    assert detail_response.status_code == 403
    assert detail_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
    assert create_response.status_code == 403
    assert create_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
