import json

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import (
    BusinessUnit,
    Country,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    Office,
    OfficeConfiguration,
)
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_country,
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


def create_master_admin_client() -> Client:
    master_bu = create_business_unit(bu_code="BU-MASTER", name="Master BU")
    master_admin = create_employee(
        employee_code="EMP-MASTER-API",
        full_name="Master Admin",
        email="master-admin@example.com",
        primary_business_unit=master_bu,
    )
    assign_employee_to_business_unit(
        employee=master_admin,
        business_unit=master_bu,
        is_primary_flag=True,
    )
    assign_role(employee=master_admin, role_code="USER")
    assign_role(employee=master_admin, role_code="TS_ADMIN_MASTER")
    client = Client()
    initialize_session(client, master_admin.email)
    return client


@pytest.mark.django_db
def test_ts_admin_master_can_list_create_update_and_get_country_via_api() -> None:
    seed_reference_data()
    active_country = create_country(country_code="ESP", country_name="Spain", active=True)
    create_country(country_code="PRT", country_name="Portugal", active=False)
    client = create_master_admin_client()

    list_response = client.get("/api/v1/admin/countries/", data={"status": "INACTIVE"})

    assert list_response.status_code == 200
    assert "PRT" in [item["country_code"] for item in list_response.json()["countries"]]

    create_response = client.post(
        "/api/v1/admin/countries/",
        data=json.dumps(
            {
                "country_code": "FRA",
                "country_name": "France",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_country = create_response.json()["country"]
    assert created_country["country_code"] == "FRA"
    assert created_country["country_name"] == "France"
    assert created_country["status"] == "ACTIVE"

    detail_response = client.get(f"/api/v1/admin/countries/{active_country.id}/")

    assert detail_response.status_code == 200
    assert detail_response.json()["country"]["country_code"] == "ESP"

    update_response = client.patch(
        f"/api/v1/admin/countries/{active_country.id}/",
        data=json.dumps(
            {
                "country_name": "Spain Updated",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_country = update_response.json()["country"]
    assert updated_country["country_name"] == "Spain Updated"
    assert updated_country["status"] == "INACTIVE"
    assert AuditLog.objects.filter(entity_name="country", action_type__value_code="CREATE").exists()
    assert AuditLog.objects.filter(
        entity_name="country",
        field_name="country_name",
        old_value="Spain",
        new_value="Spain Updated",
    ).exists()


@pytest.mark.django_db
def test_ts_admin_master_country_delete_is_guarded_and_audits_denied_attempt() -> None:
    seed_reference_data()
    country = create_country(country_code="ITA", country_name="Italy")
    create_office(office_name="Italy Office", country=country)
    client = create_master_admin_client()

    response = client.delete(f"/api/v1/admin/countries/{country.id}/")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "COUNTRY_DELETE_BLOCKED"
    assert Country.objects.filter(id=country.id).exists()
    assert AuditLog.objects.filter(
        entity_name="country",
        entity_id=country.id,
        action_type__value_code="DENY",
        actor_email="master-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_ts_admin_master_can_delete_unused_country_via_api() -> None:
    seed_reference_data()
    country = create_country(country_code="DEU", country_name="Germany")
    client = create_master_admin_client()

    response = client.delete(f"/api/v1/admin/countries/{country.id}/")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "entity": "country", "id": country.id}
    assert not Country.objects.filter(id=country.id).exists()
    assert AuditLog.objects.filter(
        entity_name="country",
        entity_id=country.id,
        action_type__value_code="DELETE",
        actor_email="master-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_ts_admin_master_can_list_create_update_and_get_office_via_api() -> None:
    seed_reference_data()
    country = create_country(country_code="USA", country_name="United States")
    create_office(office_name="Inactive Office", country=country, active=False)
    client = create_master_admin_client()

    list_response = client.get("/api/v1/admin/offices/", data={"status": "INACTIVE"})

    assert list_response.status_code == 200
    assert "Inactive Office" in [item["office_name"] for item in list_response.json()["offices"]]

    create_response = client.post(
        "/api/v1/admin/offices/",
        data=json.dumps(
            {
                "country_id": country.id,
                "office_name": "New York Office",
                "status_code": "ACTIVE",
                "approval_mode_code": "PROJECT",
                "allow_employee_withdraw_flag": True,
                "timesheet_cutoff_date": "2026-05-31",
                "count_non_billable_in_daily_limit_flag": True,
                "archive_after_years": 7,
                "enable_timer_flag": False,
                "enable_leave_integration_flag": False,
                "enable_copy_previous_week_flag": True,
                "bootstrap_bu_code": "NY-BU",
                "bootstrap_bu_name": "New York BU",
                "bootstrap_bu_description": "Bootstrap BU",
                "bootstrap_admin_employee_code": "EMP-NY-ADM",
                "bootstrap_admin_full_name": "New York Admin",
                "bootstrap_admin_email": "ny-admin@example.com",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_office = create_response.json()["office"]
    assert created_office["office_name"] == "New York Office"
    assert created_office["country"]["country_code"] == "USA"
    assert created_office["configuration"]["allow_employee_withdraw_flag"] is True
    assert created_office["configuration"]["enable_copy_previous_week_flag"] is True

    office_id = created_office["id"]
    detail_response = client.get(f"/api/v1/admin/offices/{office_id}/")

    assert detail_response.status_code == 200
    office_detail = detail_response.json()["office"]
    assert office_detail["active_employee_count"] == 1
    assert office_detail["administrators"][0]["email"] == "ny-admin@example.com"
    assert office_detail["administrators"][0]["primary_business_unit"]["bu_code"] == "NY-BU"

    update_response = client.patch(
        f"/api/v1/admin/offices/{office_id}/",
        data=json.dumps(
            {
                "office_name": "New York Office Updated",
                "allow_employee_withdraw_flag": False,
                "archive_after_years": 9,
                "enable_copy_previous_week_flag": False,
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_office = update_response.json()["office"]
    assert updated_office["office_name"] == "New York Office Updated"
    assert updated_office["configuration"]["allow_employee_withdraw_flag"] is False
    assert updated_office["configuration"]["archive_after_years"] == 9
    assert updated_office["configuration"]["enable_copy_previous_week_flag"] is False
    assert AuditLog.objects.filter(entity_name="office", action_type__value_code="CREATE").exists()
    assert AuditLog.objects.filter(
        entity_name="office",
        field_name="office_name",
        old_value="New York Office",
        new_value="New York Office Updated",
    ).exists()


@pytest.mark.django_db
def test_ts_admin_master_office_delete_is_guarded_and_audits_denied_attempt() -> None:
    seed_reference_data()
    country = create_country(country_code="MEX", country_name="Mexico")
    office = create_office(office_name="Mexico Office", country=country)
    create_business_unit(bu_code="MEX-BU", name="Mexico BU", office=office)
    client = create_master_admin_client()

    response = client.delete(f"/api/v1/admin/offices/{office.id}/")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "COUNTRY_DELETE_BLOCKED"
    assert Office.objects.filter(id=office.id).exists()
    assert AuditLog.objects.filter(
        entity_name="office",
        entity_id=office.id,
        action_type__value_code="DENY",
        actor_email="master-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_ts_admin_master_can_delete_unused_office_via_api() -> None:
    seed_reference_data()
    country = create_country(country_code="CAN", country_name="Canada")
    office = create_office(office_name="Canada Office", country=country)
    client = create_master_admin_client()

    response = client.delete(f"/api/v1/admin/offices/{office.id}/")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "entity": "office", "id": office.id}
    assert not Office.objects.filter(id=office.id).exists()
    assert AuditLog.objects.filter(
        entity_name="office",
        entity_id=office.id,
        action_type__value_code="DELETE",
        actor_email="master-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_ts_admin_master_can_delete_setup_only_current_office_via_api() -> None:
    seed_reference_data()
    country = create_country(country_code="PER", country_name="Peru")
    office = create_office(office_name="Peru Office", country=country)
    business_unit = create_business_unit(
        bu_code="PER-ADMIN",
        name="Peru Admin",
        office=office,
    )
    admin = create_employee(
        employee_code="EMP-PER-ADMIN",
        full_name="Peru Office Admin",
        email="peru.admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=admin,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin, role_code="USER")
    assign_role(employee=admin, role_code="TS_ADMIN")
    assign_role(employee=admin, role_code="TS_ADMIN_MASTER")
    client = Client()
    initialize_session(client, admin.email)

    response = client.delete(f"/api/v1/admin/offices/{office.id}/")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "entity": "office", "id": office.id}
    assert not Office.objects.filter(id=office.id).exists()
    assert not OfficeConfiguration.objects.filter(office_id=office.id).exists()
    assert not Employee.objects.filter(id=admin.id).exists()
    assert not BusinessUnit.objects.filter(id=business_unit.id).exists()
    assert not EmployeeRole.objects.filter(employee_id=admin.id).exists()
    assert not EmployeeBusinessUnit.objects.filter(employee_id=admin.id).exists()
    office_delete = AuditLog.objects.get(
        entity_name="office",
        entity_id=office.id,
        action_type__value_code="DELETE",
        actor_email=admin.email,
    )
    assert office_delete.actor_employee_id is None


@pytest.mark.django_db
def test_non_master_admin_is_denied_country_and_office_admin_endpoints() -> None:
    seed_reference_data()
    admin_bu = create_business_unit(bu_code="BU-TS-ADMIN", name="TS Admin BU")
    employee = create_employee(
        employee_code="EMP-TS-ADMIN",
        full_name="TS Admin",
        email="ts-admin@example.com",
        primary_business_unit=admin_bu,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=admin_bu,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="TS_ADMIN", business_unit=admin_bu)
    client = Client()
    initialize_session(client, employee.email)

    country_response = client.get("/api/v1/admin/countries/")
    office_response = client.get("/api/v1/admin/offices/")

    assert country_response.status_code == 403
    assert country_response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"
    assert office_response.status_code == 403
    assert office_response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"
