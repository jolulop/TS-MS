import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_employee,
    create_office,
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
    assert payload["employee"]["office"]["office_name"] == "Holding"
    assert payload["employee"]["office"]["status"] == "ACTIVE"
    assert payload["roles"] == ["USER"]
    assert payload["business_units"][0]["bu_code"] == "BU-1"
    assert AuditLog.objects.filter(entity_name="internal_session").count() == 1

    session_response = client.get("/api/v1/auth/session")

    assert session_response.status_code == 200
    assert session_response.json()["session"]["employee"]["email"] == "alice@example.com"
    assert session_response.json()["session"]["employee"]["office"]["office_name"] == "Holding"


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
def test_initialize_session_denies_non_admin_user_from_inactive_country() -> None:
    seed_reference_data()
    inactive_country = create_office(office_name="Inactive Test Office", active=False)
    business_unit = create_business_unit(
        bu_code="BU-INACTIVE-1",
        name="Inactive Office BU",
        office=inactive_country,
    )
    employee = create_employee(
        employee_code="EMP-004",
        full_name="Inactive Office User",
        email="inactive-user@example.com",
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
        data=json.dumps({"validated_email": "inactive-user@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_COUNTRY_INACTIVE"


@pytest.mark.django_db
def test_initialize_session_allows_ts_admin_master_from_inactive_country() -> None:
    seed_reference_data()
    inactive_country = create_office(office_name="Inactive Admin Office", active=False)
    business_unit = create_business_unit(
        bu_code="BU-INACTIVE-2",
        name="Inactive Office Admin BU",
        office=inactive_country,
    )
    employee = create_employee(
        employee_code="EMP-005",
        full_name="Inactive Office Master Admin",
        email="inactive-master@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="TS_ADMIN_MASTER")

    client = Client()
    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": "inactive-master@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()["session"]
    assert payload["employee"]["office"]["office_name"] == "Inactive Admin Office"
    assert payload["employee"]["office"]["status"] == "INACTIVE"
    assert payload["roles"] == ["TS_ADMIN_MASTER"]


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
