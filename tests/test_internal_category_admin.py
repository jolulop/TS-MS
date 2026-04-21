import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_employee,
    create_internal_category,
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
def test_ts_admin_internal_category_list_is_limited_to_assigned_business_units() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1101",
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

    create_internal_category(
        business_unit=admin_bu,
        category_code="CAT-1",
        name="Scoped Category",
    )
    create_internal_category(
        business_unit=other_bu,
        category_code="CAT-2",
        name="Other Category",
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get("/api/v1/admin/internal-categories/")

    assert response.status_code == 200
    assert [item["category_code"] for item in response.json()["internal_categories"]] == ["CAT-1"]


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_internal_category_with_audit() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-1102",
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
        "/api/v1/admin/internal-categories/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "category_code": "CAT-NEW",
                "name": "New Category",
                "description": "Initial description",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_category = create_response.json()["internal_category"]
    assert created_category["category_code"] == "CAT-NEW"
    assert created_category["description"] == "Initial description"

    update_response = client.patch(
        f"/api/v1/admin/internal-categories/{created_category['id']}/",
        data=json.dumps(
            {
                "category_code": "CAT-UPD",
                "name": "Updated Category",
                "description": "Updated description",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_category = update_response.json()["internal_category"]
    assert updated_category["category_code"] == "CAT-UPD"
    assert updated_category["name"] == "Updated Category"
    assert updated_category["description"] == "Updated description"
    assert updated_category["status"] == "INACTIVE"

    assert (
        AuditLog.objects.filter(
            entity_name="internal_category",
            action_type__value_code="CREATE",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="internal_category", field_name="category_code").count()
        == 1
    )
    assert AuditLog.objects.filter(entity_name="internal_category", field_name="name").count() == 1
    assert (
        AuditLog.objects.filter(entity_name="internal_category", field_name="description").count()
        == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="internal_category", field_name="status").count() == 1
    )


@pytest.mark.django_db
def test_non_admin_is_denied_internal_category_admin_endpoints() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-1103",
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

    response = client.get("/api/v1/admin/internal-categories/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_cannot_view_or_create_out_of_scope_internal_category() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1104",
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

    other_category = create_internal_category(
        business_unit=other_bu,
        category_code="CAT-OTHER",
        name="Other Category",
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    detail_response = client.get(f"/api/v1/admin/internal-categories/{other_category.id}/")
    create_response = client.post(
        "/api/v1/admin/internal-categories/",
        data=json.dumps(
            {
                "business_unit_id": other_bu.id,
                "category_code": "CAT-DENIED",
                "name": "Denied Category",
            }
        ),
        content_type="application/json",
    )

    assert detail_response.status_code == 403
    assert detail_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
    assert create_response.status_code == 403
    assert create_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
