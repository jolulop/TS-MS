import json
from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_client,
    create_cost_center,
    create_employee,
    create_internal_category,
    create_office,
    create_pricing_model,
    create_project,
    create_yearly_calendar,
    seed_reference_data,
)


def initialize_session(client: Client, validated_email: str) -> None:
    response = client.post(
        "/api/v1/auth/session/initialize",
        data=json.dumps({"validated_email": validated_email}),
        content_type="application/json",
    )
    assert response.status_code == 201


def _build_admin_context():
    business_unit = create_business_unit(bu_code="BU-ADMIN", name="Admin BU")
    admin_employee = create_employee(
        employee_code="EMP-ADMIN-EXT",
        full_name="Admin User",
        email="admin-ext@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin_employee, role_code="TS_ADMIN", business_unit=business_unit)
    assign_role(employee=admin_employee, role_code="USER")

    project_owner = create_employee(
        employee_code="EMP-PO-EXT",
        full_name="Project Owner",
        email="project-owner-ext@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")

    project_manager = create_employee(
        employee_code="EMP-PM-EXT",
        full_name="Project Manager",
        email="project-manager-ext@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="USER")
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    foreign_country = create_office(office_name="Assignment Worker Office")
    foreign_business_unit = create_business_unit(
        bu_code="BU-WORKER-FOREIGN",
        name="Worker Foreign BU",
        office=foreign_country,
    )
    worker = create_employee(
        employee_code="EMP-WORKER-EXT",
        full_name="Worker User",
        email="worker-ext@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_employee_to_business_unit(
        employee=worker,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=worker, role_code="USER")

    project_client = create_client(
        business_unit=business_unit,
        client_code="CLI-EXT",
        name="Extension Client",
    )
    category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT-EXT",
        name="Extension Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-EXT",
        name="Extension Cost Center",
    )
    pricing_model = create_pricing_model(
        business_unit=business_unit,
        name="Fixed Fee",
        description="Extension pricing model",
    )
    return (
        business_unit,
        admin_employee,
        project_owner,
        project_manager,
        worker,
        project_client,
        category,
        cost_center,
        pricing_model,
    )


@pytest.mark.django_db
def test_ts_admin_can_create_update_and_filter_projects_via_api() -> None:
    seed_reference_data()
    (
        business_unit,
        admin_employee,
        project_owner,
        project_manager,
        _worker,
        project_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_admin_context()
    client = Client()
    initialize_session(client, admin_employee.email)

    create_response = client.post(
        "/api/v1/admin/projects/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "project_code": "PRJ-EXT",
                "name": "Extension Project",
                "description": "Project created by API",
                "project_owner_employee_id": project_owner.id,
                "project_manager_employee_id": project_manager.id,
                "client_id": project_client.id,
                "internal_category_id": category.id,
                "cost_center_id": cost_center.id,
                "pricing_model_id": pricing_model.id,
                "start_date": "2026-04-01",
                "status_code": "ACTIVE",
                "billable_flag": True,
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_project = create_response.json()["project"]
    assert created_project["project_code"] == "PRJ-EXT"
    assert created_project["status"] == "ACTIVE"
    assert created_project["pricing_model"]["id"] == pricing_model.id

    update_response = client.patch(
        f"/api/v1/admin/projects/{created_project['id']}/",
        data=json.dumps(
            {
                "project_code": "PRJ-EXT-UPD",
                "name": "Extension Project Updated",
                "status_code": "CLOSED",
                "close_date": "2026-09-30",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    assert update_response.json()["project"]["status"] == "CLOSED"

    active_list_response = client.get("/api/v1/admin/projects/?status=ACTIVE")
    closed_list_response = client.get("/api/v1/admin/projects/?status=CLOSED")

    assert active_list_response.status_code == 200
    assert active_list_response.json()["projects"] == []
    assert closed_list_response.status_code == 200
    assert [item["project_code"] for item in closed_list_response.json()["projects"]] == [
        "PRJ-EXT-UPD"
    ]
    assert (
        AuditLog.objects.filter(entity_name="project", action_type__value_code="CREATE").count()
        == 1
    )


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_pricing_models_via_api() -> None:
    seed_reference_data()
    (
        _business_unit,
        admin_employee,
        _project_owner,
        _project_manager,
        _worker,
        _project_client,
        _category,
        _cost_center,
        _pricing_model,
    ) = _build_admin_context()
    client = Client()
    initialize_session(client, admin_employee.email)

    create_response = client.post(
        "/api/v1/admin/pricing-models/",
        data=json.dumps(
            {
                "name": "Retainer",
                "description": "Monthly retainer pricing.",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_pricing_model = create_response.json()["pricing_model"]
    assert created_pricing_model["name"] == "Retainer"

    update_response = client.patch(
        f"/api/v1/admin/pricing-models/{created_pricing_model['id']}/",
        data=json.dumps(
            {
                "name": "Retainer Updated",
                "description": "Updated monthly retainer pricing.",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    assert update_response.json()["pricing_model"]["name"] == "Retainer Updated"

    list_response = client.get("/api/v1/admin/pricing-models/")

    assert list_response.status_code == 200
    assert {item["name"] for item in list_response.json()["pricing_models"]} >= {
        "Fixed Fee",
        "Retainer Updated",
    }


@pytest.mark.django_db
def test_ts_admin_can_create_update_and_list_yearly_calendars_via_api() -> None:
    seed_reference_data()
    (
        business_unit,
        admin_employee,
        _project_owner,
        _project_manager,
        _worker,
        _project_client,
        _category,
        _cost_center,
        _pricing_model,
    ) = _build_admin_context()
    client = Client()
    initialize_session(client, admin_employee.email)

    create_response = client.post(
        "/api/v1/admin/yearly-calendars/",
        data=json.dumps(
            {
                "calendar_year": 2026,
                "calendar_name": "API Calendar",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    yearly_calendar = create_response.json()["yearly_calendar"]
    assert yearly_calendar["calendar_name"] == "API Calendar"

    update_response = client.patch(
        f"/api/v1/admin/yearly-calendars/{yearly_calendar['id']}/",
        data=json.dumps(
            {
                "calendar_name": "API Calendar Updated",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    assert update_response.json()["yearly_calendar"]["status"] == "INACTIVE"

    list_response = client.get("/api/v1/admin/yearly-calendars/?status=ALL")

    assert list_response.status_code == 200
    assert [item["calendar_name"] for item in list_response.json()["yearly_calendars"]] == [
        "API Calendar Updated"
    ]


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_calendar_special_days_via_api() -> None:
    seed_reference_data()
    (
        business_unit,
        admin_employee,
        _project_owner,
        _project_manager,
        _worker,
        _project_client,
        _category,
        _cost_center,
        _pricing_model,
    ) = _build_admin_context()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="API Holiday Calendar",
    )
    client = Client()
    initialize_session(client, admin_employee.email)

    create_response = client.post(
        "/api/v1/admin/calendar-special-days/",
        data=json.dumps(
            {
                "yearly_calendar_id": yearly_calendar.id,
                "special_date": "2026-05-01",
                "day_type_code": "NATIONAL_HOLIDAY",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    special_day = create_response.json()["calendar_special_day"]
    assert special_day["day_type"]["value_code"] == "NATIONAL_HOLIDAY"

    update_response = client.patch(
        f"/api/v1/admin/calendar-special-days/{special_day['id']}/",
        data=json.dumps(
            {
                "special_date": "2026-05-04",
                "day_type_code": "LOCAL_HOLIDAY",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_special_day = update_response.json()["calendar_special_day"]
    assert updated_special_day["special_date"] == "2026-05-04"
    assert updated_special_day["day_type"]["value_code"] == "LOCAL_HOLIDAY"

    list_response = client.get(
        f"/api/v1/admin/calendar-special-days/?yearly_calendar_id={yearly_calendar.id}"
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["calendar_special_days"]] == [
        special_day["id"]
    ]


@pytest.mark.django_db
def test_ts_admin_can_create_and_update_project_assignment_via_api() -> None:
    seed_reference_data()
    (
        business_unit,
        admin_employee,
        project_owner,
        project_manager,
        worker,
        project_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_admin_context()
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-ASN-EXT",
        name="Assignment API Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    client = Client()
    initialize_session(client, admin_employee.email)

    create_response = client.post(
        "/api/v1/admin/project-assignments/",
        data=json.dumps(
            {
                "project_id": project.id,
                "employee_id": worker.id,
                "assignment_start_date": "2026-04-07",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert create_response.status_code == 201
    created_assignment = create_response.json()["project_assignment"]
    assert created_assignment["project"]["project_code"] == "PRJ-ASN-EXT"
    assert created_assignment["employee"]["employee_code"] == "EMP-WORKER-EXT"

    update_response = client.patch(
        f"/api/v1/admin/project-assignments/{created_assignment['id']}/",
        data=json.dumps(
            {
                "assignment_end_date": "2026-08-31",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    assert update_response.json()["project_assignment"]["status"] == "INACTIVE"
    assert (
        AuditLog.objects.filter(
            entity_name="project_assignment", action_type__value_code="CREATE"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_calendar_period_rule_api_rejects_overlap_and_supports_update() -> None:
    seed_reference_data()
    (
        business_unit,
        admin_employee,
        _project_owner,
        _project_manager,
        _worker,
        _project_client,
        _category,
        _cost_center,
        _pricing_model,
    ) = _build_admin_context()
    second_business_unit = create_business_unit(
        bu_code="BU-ADMIN-2",
        name="Admin BU 2",
        office=business_unit.office,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=second_business_unit,
    )
    yearly_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Extension Calendar",
    )
    client = Client()
    initialize_session(client, admin_employee.email)

    first_response = client.post(
        "/api/v1/admin/calendar-period-rules/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "yearly_calendar_id": yearly_calendar.id,
                "effective_from": "2026-01-01",
                "effective_to": "2026-03-31",
                "monday_max_hours": "8.00",
                "tuesday_max_hours": "8.00",
                "wednesday_max_hours": "8.00",
                "thursday_max_hours": "8.00",
                "friday_max_hours": "6.00",
                "working_on_saturdays_flag": True,
                "saturday_max_hours": "5.00",
                "sunday_max_hours": "0.00",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert first_response.status_code == 201
    created_period_rule = first_response.json()["calendar_period_rule"]
    assert created_period_rule["working_on_saturdays_flag"] is True
    assert created_period_rule["working_on_sundays_flag"] is False
    assert created_period_rule["saturday_max_hours"] == "5.00"
    assert created_period_rule["sunday_max_hours"] == "0.00"

    overlap_response = client.post(
        "/api/v1/admin/calendar-period-rules/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "yearly_calendar_id": yearly_calendar.id,
                "effective_from": "2026-03-01",
                "effective_to": "2026-04-30",
                "monday_max_hours": "8.00",
                "tuesday_max_hours": "8.00",
                "wednesday_max_hours": "8.00",
                "thursday_max_hours": "8.00",
                "friday_max_hours": "8.00",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert overlap_response.status_code == 400
    assert overlap_response.json()["error"]["code"] == "CALENDAR_PERIOD_RULE_OVERLAP"

    cross_bu_response = client.post(
        "/api/v1/admin/calendar-period-rules/",
        data=json.dumps(
            {
                "business_unit_id": second_business_unit.id,
                "yearly_calendar_id": yearly_calendar.id,
                "effective_from": "2026-03-01",
                "effective_to": "2026-04-30",
                "monday_max_hours": "7.50",
                "tuesday_max_hours": "7.50",
                "wednesday_max_hours": "7.50",
                "thursday_max_hours": "7.50",
                "friday_max_hours": "7.50",
                "status_code": "ACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert cross_bu_response.status_code == 201

    update_response = client.patch(
        f"/api/v1/admin/calendar-period-rules/{created_period_rule['id']}/",
        data=json.dumps(
            {
                "business_unit_id": business_unit.id,
                "effective_to": "2026-04-30",
                "monday_max_hours": "7.50",
                "working_on_sundays_flag": True,
                "saturday_max_hours": "5.50",
                "sunday_max_hours": "4.50",
                "status_code": "INACTIVE",
            }
        ),
        content_type="application/json",
    )

    assert update_response.status_code == 200
    updated_period_rule = update_response.json()["calendar_period_rule"]
    assert updated_period_rule["effective_to"] == "2026-04-30"
    assert updated_period_rule["monday_max_hours"] == "7.50"
    assert updated_period_rule["status"] == "INACTIVE"
    assert updated_period_rule["working_on_saturdays_flag"] is True
    assert updated_period_rule["working_on_sundays_flag"] is True
    assert updated_period_rule["saturday_max_hours"] == "5.50"
    assert updated_period_rule["sunday_max_hours"] == "4.50"
