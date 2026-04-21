import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_employee,
    seed_reference_data,
)


@pytest.mark.django_db
def test_initialize_session_creates_internal_session_from_validated_email() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-001",
        full_name="Alice Example",
        email="alice@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": "Alice@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()["session"]
    assert payload["employee"]["employee_code"] == "EMP-001"
    assert payload["roles"] == ["USER"]
    assert payload["business_units"][0]["bu_code"] == "BU-1"
    assert AuditLog.objects.filter(entity_name="internal_session").count() == 1

    session_response = client.get("/api/v1/auth/session")

    assert session_response.status_code == 200
    assert session_response.json()["session"]["employee"]["email"] == "alice@example.com"


@pytest.mark.django_db
def test_initialize_session_denies_unknown_validated_email() -> None:
    seed_reference_data()
    client = Client()

    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": "missing@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_EMPLOYEE_NOT_FOUND"
    assert AuditLog.objects.filter(entity_name="internal_session").count() == 1


@pytest.mark.django_db
def test_initialize_session_denies_employee_without_active_role() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-002",
        full_name="Bob Example",
        email="bob@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )

    client = Client()
    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": "bob@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_NO_ACTIVE_ROLE"
    assert AuditLog.objects.filter(entity_name="internal_session").count() == 1


@pytest.mark.django_db
def test_logout_clears_internal_session() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-003",
        full_name="Cara Example",
        email="cara@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": "cara@example.com"}),
        content_type="application/json",
    )

    logout_response = client.post("/api/v1/auth/logout")
    session_response = client.get("/api/v1/auth/session")

    assert logout_response.status_code == 200
    assert session_response.status_code == 401
    assert session_response.json()["error"]["code"] == "AUTH_SESSION_REQUIRED"
