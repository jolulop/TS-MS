import json
from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_cost_center,
    create_employee,
    create_general_charge_code,
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
def test_ts_admin_general_charge_code_list_is_limited_to_assigned_business_units() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-1301",
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

    create_general_charge_code(
        business_unit=admin_bu,
        code="GCC-1",
        name="Scoped General Charge Code",
        valid_from=date(2026, 1, 1),
    )
    create_general_charge_code(
        business_unit=other_bu,
        code="GCC-2",
        name="Other General Charge Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get("/api/v1/admin/general-charge-codes/")

    assert response.status_code == 200
    assert [item["code"] for item in response.json()["general_charge_codes"]] == ["GCC-1"]


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_general_charge_code_with_audit() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-GCC-1",
        name="General Charge Cost Center",
        description="Cost center for General Charge Code tests.",
    )
    replacement_cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-GCC-2",
        name="Replacement Cost Center",
        description="Replacement cost center for General Charge Code tests.",
    )
    admin_employee = create_employee(
        employee_code="EMP-1302",
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
        "/api/v1/admin/general-charge-codes/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "code": "GCC-NEW",
                "name": "New General Charge Code",
                "charge_type_code": "STANDARD",
                "cost_center_id": cost_center.id,
                "billable_flag": True,
                "requires_approval_flag": True,
                "description_required_flag": True,
                "valid_from": "2026-01-01",
                "valid_to": "2026-12-31",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_general_charge_code = create_response.json()["general_charge_code"]
    assert created_general_charge_code["code"] == "GCC-NEW"
    assert created_general_charge_code["billable_flag"] is True
    assert created_general_charge_code["requires_approval_flag"] is True

    update_response = client.patch(
        f"/api/v1/admin/general-charge-codes/{created_general_charge_code['id']}/",
        data=json.dumps(
            {
                "code": "GCC-UPD",
                "name": "Updated General Charge Code",
                "cost_center_id": replacement_cost_center.id,
                "billable_flag": False,
                "requires_approval_flag": False,
                "description_required_flag": False,
                "valid_to": None,
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_general_charge_code = update_response.json()["general_charge_code"]
    assert updated_general_charge_code["code"] == "GCC-UPD"
    assert updated_general_charge_code["name"] == "Updated General Charge Code"
    assert updated_general_charge_code["cost_center"]["id"] == replacement_cost_center.id
    assert updated_general_charge_code["billable_flag"] is False
    assert updated_general_charge_code["requires_approval_flag"] is False
    assert updated_general_charge_code["description_required_flag"] is False
    assert updated_general_charge_code["valid_to"] is None
    assert updated_general_charge_code["status"] == "INACTIVE"

    assert (
        AuditLog.objects.filter(
            entity_name="general_charge_code",
            action_type__value_code="CREATE",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="general_charge_code", field_name="code").count() == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="general_charge_code", field_name="name").count() == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="general_charge_code", field_name="billable_flag"
        ).count()
        == 1
    )
    assert AuditLog.objects.filter(
        entity_name="general_charge_code", field_name="cost_center"
    ).count() == 1
    assert (
        AuditLog.objects.filter(
            entity_name="general_charge_code",
            field_name="requires_approval_flag",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="general_charge_code",
            field_name="description_required_flag",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="general_charge_code", field_name="valid_to").count()
        == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="general_charge_code", field_name="status").count() == 1
    )


@pytest.mark.django_db
def test_general_charge_code_rejects_invalid_date_range() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-GCC-BAD",
        name="General Charge Cost Center",
        description="Cost center for General Charge Code tests.",
    )
    admin_employee = create_employee(
        employee_code="EMP-1303",
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

    response = client.post(
        "/api/v1/admin/general-charge-codes/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "code": "GCC-BAD",
                "name": "Bad General Charge Code",
                "cost_center_id": cost_center.id,
                "valid_from": "2026-12-31",
                "valid_to": "2026-01-01",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "GENERAL_CHARGE_CODE_DATE_RANGE_INVALID"


@pytest.mark.django_db
def test_general_charge_code_requires_cost_center_on_create() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-1303B",
        full_name="Admin User",
        email="admin-cost-center@example.com",
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
    initialize_session(client, "admin-cost-center@example.com")

    response = client.post(
        "/api/v1/admin/general-charge-codes/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "code": "GCC-NO-CC",
                "name": "No Cost Center",
                "valid_from": "2026-01-01",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "GENERAL_CHARGE_CODE_COST_CENTER_REQUIRED"


@pytest.mark.django_db
def test_non_admin_is_denied_general_charge_code_admin_endpoints() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-1304",
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

    response = client.get("/api/v1/admin/general-charge-codes/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_cannot_view_or_create_out_of_scope_general_charge_code() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_cost_center = create_cost_center(
        business_unit=admin_bu,
        cost_center_code="CC-ADMIN",
        name="Admin Cost Center",
        description="Admin office cost center.",
    )
    create_cost_center(
        business_unit=other_bu,
        cost_center_code="CC-OTHER",
        name="Other Cost Center",
        description="Other office cost center.",
    )
    admin_employee = create_employee(
        employee_code="EMP-1305",
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

    other_general_charge_code = create_general_charge_code(
        business_unit=other_bu,
        code="GCC-OTHER",
        name="Other General Charge Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    detail_response = client.get(
        f"/api/v1/admin/general-charge-codes/{other_general_charge_code.id}/"
    )
    create_response = client.post(
        "/api/v1/admin/general-charge-codes/",
        data=json.dumps(
            {
                "business_unit_id": other_bu.id,
                "code": "GCC-DENIED",
                "name": "Denied General Charge Code",
                "cost_center_id": admin_cost_center.id,
                "valid_from": "2026-01-01",
            }
        ),
        content_type="application/json",
    )

    assert detail_response.status_code == 403
    assert detail_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
    assert create_response.status_code == 403
    assert create_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
