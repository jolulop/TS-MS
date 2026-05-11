import json
from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import EmployeeBusinessUnit, OfficeConfiguration
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_business_unit_configuration,
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
def test_ts_admin_business_unit_list_is_limited_to_assigned_scope() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    admin_employee = create_employee(
        employee_code="EMP-BU-1001",
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

    response = client.get("/api/v1/admin/business-units/")

    assert response.status_code == 200
    assert [item["bu_code"] for item in response.json()["business_units"]] == ["BU-ADMIN"]
    assert all(item["bu_code"] != other_bu.bu_code for item in response.json()["business_units"])


@pytest.mark.django_db
def test_ts_admin_can_create_business_unit_and_gain_scope_to_it() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    create_business_unit_configuration(
        business_unit=business_unit,
        allow_employee_withdraw_flag=True,
        timesheet_cutoff_date=date(2026, 5, 31),
    )
    office_configuration = OfficeConfiguration.objects.get(office=business_unit.office)
    office_configuration.archive_after_years = 7
    office_configuration.enable_timer_flag = True
    office_configuration.enable_leave_integration_flag = True
    office_configuration.enable_copy_previous_week_flag = True
    office_configuration.updated_by = "system@test.local"
    office_configuration.save(
        update_fields=[
            "archive_after_years",
            "enable_timer_flag",
            "enable_leave_integration_flag",
            "enable_copy_previous_week_flag",
            "updated_by",
            "updated_at",
        ]
    )
    admin_employee = create_employee(
        employee_code="EMP-BU-1000",
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
        "/api/v1/admin/business-units/",
        data=json.dumps(
            {
                "bu_code": "BU-NEW",
                "name": "New Admin BU",
                "description": "Created from API",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    payload = create_response.json()["business_unit"]
    assert payload["bu_code"] == "BU-NEW"
    assert payload["configuration"]["approval_mode"] == "PROJECT"
    assert payload["configuration"]["allow_employee_withdraw_flag"] is True
    assert payload["configuration"]["timesheet_cutoff_date"] == "2026-05-31"
    assert payload["configuration"]["archive_after_years"] == 7
    assert payload["configuration"]["enable_timer_flag"] is True
    assert EmployeeBusinessUnit.objects.filter(
        employee=admin_employee,
        business_unit__bu_code="BU-NEW",
        valid_to__isnull=True,
    ).exists()

    list_response = client.get("/api/v1/admin/business-units/")
    assert list_response.status_code == 200
    assert [item["bu_code"] for item in list_response.json()["business_units"]] == [
        "BU-ADMIN",
        "BU-NEW",
    ]


@pytest.mark.django_db
def test_ts_admin_can_reuse_business_unit_code_from_different_office() -> None:
    seed_reference_data()
    other_office = create_office(office_name="Other Office")
    create_business_unit(
        bu_code="DELIVERY",
        name="Delivery",
        office=other_office,
    )
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-BU-1000C",
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
        "/api/v1/admin/business-units/",
        data=json.dumps(
            {
                "bu_code": "DELIVERY",
                "name": "Delivery BU",
                "description": "Created from API",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    assert create_response.json()["business_unit"]["bu_code"] == "DELIVERY"
    assert EmployeeBusinessUnit.objects.filter(
        employee=admin_employee,
        business_unit__office=business_unit.office,
        business_unit__bu_code="DELIVERY",
        valid_to__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_ts_admin_cannot_reuse_business_unit_code_in_same_office() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="DELIVERY", name="Delivery")
    admin_employee = create_employee(
        employee_code="EMP-BU-1000D",
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
        "/api/v1/admin/business-units/",
        data=json.dumps(
            {
                "bu_code": "DELIVERY",
                "name": "Delivery BU",
                "description": "Created from API",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 400
    assert create_response.json()["error"]["code"] == "BUSINESS_UNIT_CODE_NOT_UNIQUE"
    assert (
        create_response.json()["error"]["message"]
        == "Business Unit code must be unique within the active office."
    )


@pytest.mark.django_db
def test_creating_business_unit_syncs_all_office_ts_admins_to_new_scope() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_admin = create_employee(
        employee_code="EMP-BU-1000B",
        full_name="Second Admin",
        email="second-admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=other_admin,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=other_admin, role_code="TS_ADMIN")
    assign_role(employee=other_admin, role_code="USER")

    admin_employee = create_employee(
        employee_code="EMP-BU-1000A",
        full_name="Admin User",
        email="admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN")
    assign_role(employee=admin_employee, role_code="USER")

    client = Client()
    initialize_session(client, "admin@example.com")

    create_response = client.post(
        "/api/v1/admin/business-units/",
        data=json.dumps(
            {
                "bu_code": "BU-NEW",
                "name": "New Admin BU",
                "description": "Created from API",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    assert EmployeeBusinessUnit.objects.filter(
        employee=admin_employee,
        business_unit__bu_code="BU-NEW",
        valid_to__isnull=True,
    ).exists()
    assert EmployeeBusinessUnit.objects.filter(
        employee=other_admin,
        business_unit__bu_code="BU-NEW",
        valid_to__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_existing_business_unit_reads_updated_parent_office_configuration() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    create_business_unit_configuration(business_unit=business_unit)
    admin_employee = create_employee(
        employee_code="EMP-BU-1001A",
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

    office_configuration = OfficeConfiguration.objects.get(office=business_unit.office)
    office_configuration.allow_employee_withdraw_flag = True
    office_configuration.archive_after_years = 9
    office_configuration.updated_by = "system@test.local"
    office_configuration.save(
        update_fields=[
            "allow_employee_withdraw_flag",
            "archive_after_years",
            "updated_by",
            "updated_at",
        ]
    )

    client = Client()
    initialize_session(client, "admin@example.com")

    response = client.get(f"/api/v1/admin/business-units/{business_unit.id}/")

    assert response.status_code == 200
    payload = response.json()["business_unit"]
    assert payload["configuration"]["allow_employee_withdraw_flag"] is True
    assert payload["configuration"]["archive_after_years"] == 9


@pytest.mark.django_db
def test_ts_admin_can_update_business_unit_core_and_configuration_with_audit() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    create_business_unit_configuration(business_unit=business_unit)
    admin_employee = create_employee(
        employee_code="EMP-BU-1002",
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

    response = client.patch(
        f"/api/v1/admin/business-units/{business_unit.id}/",
        data=json.dumps(
            {
                "bu_code": "BU-UPDATED",
                "name": "Updated Admin BU",
                "description": "Updated description",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()["business_unit"]
    assert payload["bu_code"] == "BU-UPDATED"
    assert payload["name"] == "Updated Admin BU"
    assert payload["description"] == "Updated description"
    assert payload["status"] == "INACTIVE"
    assert payload["configuration"]["allow_employee_withdraw_flag"] is False
    assert payload["configuration"]["timesheet_cutoff_date"] is None
    assert payload["configuration"]["archive_after_years"] == 5
    assert (
        AuditLog.objects.filter(entity_name="business_unit", field_name="bu_code").count() == 1
    )
    assert (
        AuditLog.objects.filter(entity_name="business_unit", field_name="status").count() == 1
    )


@pytest.mark.django_db
def test_ts_admin_cannot_update_inherited_business_unit_configuration() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    create_business_unit_configuration(business_unit=business_unit)
    admin_employee = create_employee(
        employee_code="EMP-BU-1002A",
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

    response = client.patch(
        f"/api/v1/admin/business-units/{business_unit.id}/",
        data=json.dumps(
            {
                "archive_after_years": 7,
                "timesheet_cutoff_date": "2026-05-31",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BUSINESS_UNIT_CONFIGURATION_INHERITED"
    configuration = OfficeConfiguration.objects.get(office=business_unit.office)
    assert configuration.archive_after_years == 5
    assert (
        AuditLog.objects.filter(
            entity_name="office_configuration",
            field_name="archive_after_years",
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_non_admin_is_denied_business_unit_admin_endpoints() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-BU-1003",
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

    response = client.get("/api/v1/admin/business-units/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"


@pytest.mark.django_db
def test_ts_admin_cannot_view_or_update_out_of_scope_business_unit() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    other_bu = create_business_unit(bu_code="BU-OTHER", name="Other BU")
    create_business_unit_configuration(business_unit=other_bu)
    admin_employee = create_employee(
        employee_code="EMP-BU-1004",
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

    detail_response = client.get(f"/api/v1/admin/business-units/{other_bu.id}/")
    update_response = client.patch(
        f"/api/v1/admin/business-units/{other_bu.id}/",
        data=json.dumps({"name": "Denied Update"}),
        content_type="application/json",
    )

    assert detail_response.status_code == 403
    assert detail_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
    assert update_response.status_code == 403
    assert update_response.json()["error"]["code"] == "BUSINESS_UNIT_OUT_OF_SCOPE"
