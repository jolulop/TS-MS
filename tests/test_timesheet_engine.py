import json
from datetime import date

import pytest
from django.db.models.query import QuerySet
from django.test import Client

from apps.audit.models import AuditLog
from apps.auth.services import CurrentUserService
from apps.master_data.models import OfficeConfiguration
from apps.timesheets.models import (
    ApprovalAction,
    ApprovalItem,
    TimesheetLine,
    TimesheetSubmissionCycle,
    WeeklyTimesheet,
)
from apps.timesheets.services import TimesheetService
from tests.helpers import (
    assign_calendar,
    assign_cross_office_project,
    assign_employee_to_business_unit,
    assign_project,
    assign_role,
    create_business_unit,
    create_business_unit_configuration,
    create_calendar_period_rule,
    create_calendar_special_day,
    create_client,
    create_cost_center,
    create_employee,
    create_general_charge_code,
    create_internal_category,
    create_office,
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


def create_timesheet(
    client: Client,
    week_start_date: str,
    *,
    copy_previous_week: bool = False,
) -> dict:
    response = client.post(
        "/api/v1/timesheets/",
        data=json.dumps(
            {
                "week_start_date": week_start_date,
                "copy_previous_week": copy_previous_week,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()["timesheet"]


def record_select_for_update_models(monkeypatch: pytest.MonkeyPatch) -> list[type]:
    locked_models = []
    original_select_for_update = QuerySet.select_for_update

    def recording_select_for_update(self, *args, **kwargs):
        locked_models.append(self.model)
        return original_select_for_update(self, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "select_for_update", recording_select_for_update)
    return locked_models


def setup_project_approval_context(*, email: str, employee_code: str, full_name: str) -> dict:
    business_unit = create_business_unit(bu_code=f"BU-{employee_code}", name=f"{full_name} BU")
    create_business_unit_configuration(business_unit=business_unit, approval_mode_code="PROJECT")

    employee = create_employee(
        employee_code=employee_code,
        full_name=full_name,
        email=email,
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    project_owner = create_employee(
        employee_code=f"{employee_code}-OWNER",
        full_name=f"{full_name} Owner",
        email=f"owner-{email}",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")

    project_manager = create_employee(
        employee_code=f"{employee_code}-PM",
        full_name=f"{full_name} PM",
        email=f"pm-{email}",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Default 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    client_record = create_client(
        business_unit=business_unit,
        client_code=f"C-{employee_code}",
        name="Client 1",
    )
    category = create_internal_category(
        business_unit=business_unit,
        category_code=f"CAT-{employee_code}",
        name="Category 1",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code=f"CC-{employee_code}",
        name="Cost Center 1",
    )
    project = create_project(
        business_unit=business_unit,
        project_code=f"PRJ-{employee_code}",
        name="Project 1",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 1, 1),
        billable_flag=True,
    )
    assign_project(project=project, employee=employee, assignment_start_date=date(2026, 1, 1))

    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code=f"GCC-{employee_code}",
        name="General Code",
        valid_from=date(2026, 1, 1),
        billable_flag=False,
    )

    return {
        "business_unit": business_unit,
        "employee": employee,
        "project_owner": project_owner,
        "project_manager": project_manager,
        "project": project,
        "general_charge_code": general_charge_code,
    }


def create_ts_admin_for_business_unit(
    *,
    business_unit,
    email: str,
    employee_code: str,
    full_name: str,
):
    admin = create_employee(
        employee_code=employee_code,
        full_name=full_name,
        email=email,
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=admin,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin, role_code="TS_ADMIN")
    return admin


def setup_cross_country_project_approval_context() -> dict:
    home_country = create_office(office_name="Project Office")
    foreign_country = create_office(office_name="Worker Office")
    project_business_unit = create_business_unit(
        bu_code="BU-PROJECT-CC",
        name="Project Office BU",
        office=home_country,
    )
    worker_business_unit = create_business_unit(
        bu_code="BU-WORKER-CC",
        name="Worker Office BU",
        office=foreign_country,
    )
    create_business_unit_configuration(
        business_unit=worker_business_unit,
        approval_mode_code="PROJECT",
    )

    worker = create_employee(
        employee_code="EMP-CC-WORKER",
        full_name="Cross Office Worker",
        email="cross-country-worker@example.com",
        primary_business_unit=worker_business_unit,
    )
    assign_employee_to_business_unit(
        employee=worker,
        business_unit=worker_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=worker, role_code="USER")

    project_owner = create_employee(
        employee_code="EMP-CC-OWNER",
        full_name="Cross Office Owner",
        email="cross-country-owner@example.com",
        primary_business_unit=project_business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=project_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")

    project_manager = create_employee(
        employee_code="EMP-CC-PM",
        full_name="Cross Office PM",
        email="cross-country-pm@example.com",
        primary_business_unit=project_business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=project_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    worker_calendar = create_yearly_calendar(
        business_unit=worker_business_unit,
        calendar_year=2026,
        calendar_name="Worker 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=worker_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    assign_calendar(employee=worker, yearly_calendar=worker_calendar)

    client_record = create_client(
        business_unit=project_business_unit,
        client_code="CLI-CC",
        name="Cross Office Client",
    )
    category = create_internal_category(
        business_unit=project_business_unit,
        category_code="CAT-CC",
        name="Cross Office Category",
    )
    cost_center = create_cost_center(
        business_unit=project_business_unit,
        cost_center_code="CC-CC",
        name="Cross Office Cost Center",
    )
    project = create_project(
        business_unit=project_business_unit,
        project_code="PRJ-CC",
        name="Cross Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 1, 1),
        billable_flag=True,
    )
    assign_cross_office_project(
        project=project,
        employee=worker,
        assignment_start_date=date(2026, 1, 1),
    )

    return {
        "project_business_unit": project_business_unit,
        "worker_business_unit": worker_business_unit,
        "worker": worker,
        "project_owner": project_owner,
        "project_manager": project_manager,
        "project": project,
    }


@pytest.mark.django_db
def test_user_can_create_list_and_view_own_weekly_timesheet() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-2001",
        full_name="User One",
        email="user1@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_session(client, "user1@example.com")

    created = create_timesheet(client, "2026-05-04")
    list_response = client.get("/api/v1/timesheets/")
    detail_response = client.get(f"/api/v1/timesheets/{created['id']}/")

    assert created["week_start_date"] == "2026-05-04"
    assert created["week_end_date"] == "2026-05-10"
    assert created["status"] == "CREATED"
    assert list_response.status_code == 200
    assert len(list_response.json()["timesheets"]) == 1
    assert detail_response.status_code == 200
    assert detail_response.json()["timesheet"]["id"] == created["id"]


@pytest.mark.django_db
def test_timesheet_creation_rejects_duplicate_week_or_non_monday_start() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-2002",
        full_name="User Two",
        email="user2@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_session(client, "user2@example.com")

    first_response = client.post(
        "/api/v1/timesheets/",
        data=json.dumps({"week_start_date": "2026-05-04"}),
        content_type="application/json",
    )
    duplicate_response = client.post(
        "/api/v1/timesheets/",
        data=json.dumps({"week_start_date": "2026-05-04"}),
        content_type="application/json",
    )
    invalid_start_response = client.post(
        "/api/v1/timesheets/",
        data=json.dumps({"week_start_date": "2026-05-05"}),
        content_type="application/json",
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["error"]["code"] == "TIMESHEET_ALREADY_EXISTS"
    assert invalid_start_response.status_code == 400
    assert invalid_start_response.json()["error"]["code"] == "TIMESHEET_WEEK_START_INVALID"


@pytest.mark.django_db
def test_copy_previous_week_requires_an_approved_source_timesheet() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-COPY-1", name="Business Unit Copy")
    create_business_unit_configuration(business_unit=business_unit)
    OfficeConfiguration.objects.filter(office=business_unit.office).update(
        enable_copy_previous_week_flag=True
    )
    employee = create_employee(
        employee_code="EMP-COPY-1",
        full_name="Copy User",
        email="copy-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_session(client, "copy-user@example.com")

    response = client.post(
        "/api/v1/timesheets/",
        data=json.dumps(
            {
                "week_start_date": "2026-05-11",
                "copy_previous_week": True,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TIMESHEET_COPY_PREVIOUS_WEEK_SOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_user_can_replace_timesheet_lines_when_targets_and_day_limits_are_valid() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-2003",
        full_name="User Three",
        email="user3@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Default 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        monday_max_hours="8.00",
        tuesday_max_hours="8.00",
        wednesday_max_hours="8.00",
        thursday_max_hours="8.00",
        friday_max_hours="8.00",
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    client_record = create_client(business_unit=business_unit, client_code="C1", name="Client 1")
    category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT1",
        name="Category 1",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC1",
        name="Cost Center 1",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-1",
        name="Project 1",
        project_owner_employee=employee,
        project_manager_employee=employee,
        client=client_record,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 1, 1),
        billable_flag=True,
    )
    assign_project(project=project, employee=employee, assignment_start_date=date(2026, 1, 1))
    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-1",
        name="General Code",
        valid_from=date(2026, 1, 1),
        billable_flag=False,
    )

    client = Client()
    initialize_session(client, "user3@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": project.id,
                        "hours": "4.00",
                        "comment_text": "Project work",
                    },
                    {
                        "work_date": "2026-05-05",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "2.50",
                        "comment_text": "Admin work",
                    },
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()["timesheet"]
    assert len(payload["lines"]) == 2
    assert payload["lines"][0]["billable_flag"] is True
    assert payload["lines"][1]["billable_flag"] is False


@pytest.mark.django_db
def test_replace_lines_rejects_weekend_or_daily_limit_exceeded() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-2004",
        full_name="User Four",
        email="user4@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Default 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        monday_max_hours="8.00",
        tuesday_max_hours="8.00",
        wednesday_max_hours="8.00",
        thursday_max_hours="8.00",
        friday_max_hours="8.00",
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-2",
        name="General Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "user4@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    weekend_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-09",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "1.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    limit_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "9.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert weekend_response.status_code == 400
    assert weekend_response.json()["error"]["code"] == "TIMESHEET_WEEKEND_NOT_ALLOWED"
    assert limit_response.status_code == 400
    assert limit_response.json()["error"]["code"] == "TIMESHEET_DAILY_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_replace_lines_allows_working_saturday_when_period_rule_enables_it() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-SAT", name="Saturday BU")
    employee = create_employee(
        employee_code="EMP-SAT-1",
        full_name="Saturday User",
        email="saturday-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Saturday Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        business_unit=business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        working_on_saturdays_flag=True,
        saturday_max_hours="4.00",
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-SAT",
        name="Saturday Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "saturday-user@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-09",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["timesheet"]["lines"][0]["work_date"] == "2026-05-09"

    over_limit_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-09",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "4.50",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert over_limit_response.status_code == 400
    assert over_limit_response.json()["error"]["code"] == "TIMESHEET_DAILY_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_replace_lines_allows_working_sunday_when_period_rule_enables_it() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-SUN", name="Sunday BU")
    employee = create_employee(
        employee_code="EMP-SUN-1",
        full_name="Sunday User",
        email="sunday-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Sunday Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        business_unit=business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        working_on_sundays_flag=True,
        sunday_max_hours="3.50",
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-SUN",
        name="Sunday Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "sunday-user@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-10",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "3.50",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["timesheet"]["lines"][0]["work_date"] == "2026-05-10"

    over_limit_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-10",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert over_limit_response.status_code == 400
    assert over_limit_response.json()["error"]["code"] == "TIMESHEET_DAILY_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_special_day_overrides_working_weekend_and_blocks_time_entry() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-SPD", name="Special Day BU")
    employee = create_employee(
        employee_code="EMP-SPD-1",
        full_name="Special Day User",
        email="special-day-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Special Day Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        business_unit=business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        working_on_saturdays_flag=True,
        working_on_sundays_flag=True,
    )
    create_calendar_special_day(
        yearly_calendar=calendar,
        special_date=date(2026, 5, 10),
        day_type_code="OTHER",
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-SPD",
        name="Special Day Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "special-day-user@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-10",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TIMESHEET_NON_WORKING_DAY"


@pytest.mark.django_db
def test_daily_limit_uses_business_unit_specific_period_rule() -> None:
    seed_reference_data()
    office = create_office(office_name="Shared Calendar Office")
    first_business_unit = create_business_unit(
        bu_code="BU-CAL-1",
        name="Calendar BU 1",
        office=office,
    )
    second_business_unit = create_business_unit(
        bu_code="BU-CAL-2",
        name="Calendar BU 2",
        office=office,
    )
    employee = create_employee(
        employee_code="EMP-CAL-BU",
        full_name="Calendar Scoped User",
        email="calendar-bu@example.com",
        primary_business_unit=second_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=second_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=first_business_unit,
        calendar_year=2026,
        calendar_name="Shared 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        business_unit=first_business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        monday_max_hours="8.00",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        business_unit=second_business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        monday_max_hours="6.00",
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    general_charge_code = create_general_charge_code(
        business_unit=second_business_unit,
        code="GCC-CAL-2",
        name="Calendar Scoped Code",
        valid_from=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, employee.email)
    timesheet = create_timesheet(client, "2026-05-04")

    response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "general_charge_code_id": general_charge_code.id,
                        "hours": "7.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TIMESHEET_DAILY_LIMIT_EXCEEDED"


@pytest.mark.django_db
def test_replace_lines_rejects_unassigned_project() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-1", name="Business Unit 1")
    employee = create_employee(
        employee_code="EMP-2005",
        full_name="User Five",
        email="user5@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee, business_unit=business_unit, is_primary_flag=True
    )
    assign_role(employee=employee, role_code="USER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Default 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    client_record = create_client(business_unit=business_unit, client_code="C1", name="Client 1")
    category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT1",
        name="Category 1",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC1",
        name="Cost Center 1",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-2",
        name="Project 2",
        project_owner_employee=employee,
        project_manager_employee=employee,
        client=client_record,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 1, 1),
    )

    client = Client()
    initialize_session(client, "user5@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": project.id,
                        "hours": "1.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TIMESHEET_PROJECT_NOT_ASSIGNED"


@pytest.mark.django_db
def test_user_can_submit_and_withdraw_timesheet() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user6@example.com",
        employee_code="EMP-2006",
        full_name="User Six",
    )

    client = Client()
    initialize_session(client, "user6@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    save_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "3.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    submit_response = client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({"comment_text": "Ready for approval"}),
        content_type="application/json",
    )
    assert save_response.status_code == 200
    assert submit_response.status_code == 200
    assert submit_response.json()["timesheet"]["status"] == "SUBMITTED"
    assert submit_response.json()["timesheet"]["current_submission_no"] == 1
    assert submit_response.json()["timesheet"]["submission_datetime"] is not None

    submission_cycle = TimesheetSubmissionCycle.objects.get(
        weekly_timesheet_id=timesheet["id"], submission_no=1
    )
    assert submission_cycle.cycle_status.value_code == "OPEN"
    assert submission_cycle.outcome_status.value_code == "PENDING"
    assert ApprovalItem.objects.filter(submission_cycle=submission_cycle).count() == 1

    withdraw_response = client.post(
        f"/api/v1/timesheets/{timesheet['id']}/withdraw/",
        data=json.dumps({"comment_text": "Need one more edit"}),
        content_type="application/json",
    )

    assert withdraw_response.status_code == 200
    assert withdraw_response.json()["timesheet"]["status"] == "CREATED"
    assert withdraw_response.json()["timesheet"]["submission_datetime"] is None
    assert withdraw_response.json()["timesheet"]["current_submission_no"] == 1

    submission_cycle.refresh_from_db()
    assert submission_cycle.cycle_status.value_code == "COMPLETED"
    assert submission_cycle.outcome_status.value_code == "CANCELLED"
    assert (
        ApprovalItem.objects.get(submission_cycle=submission_cycle).status.value_code == "CANCELLED"
    )
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet", action_type__value_code="SUBMIT"
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet", action_type__value_code="WITHDRAW"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_submit_timesheet_requests_timesheet_row_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="submit-lock@example.com",
        employee_code="EMP-SUBMIT-LOCK",
        full_name="Submit Lock User",
    )

    client = Client()
    initialize_session(client, "submit-lock@example.com")
    timesheet = create_timesheet(client, "2026-05-04")
    save_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "3.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    assert save_response.status_code == 200

    locked_models = record_select_for_update_models(monkeypatch)
    submit_response = client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({"comment_text": "Ready for approval"}),
        content_type="application/json",
    )

    assert submit_response.status_code == 200
    assert WeeklyTimesheet in locked_models


@pytest.mark.django_db
def test_timesheet_submit_requires_lines_and_submitted_timesheet_is_not_editable() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user7@example.com",
        employee_code="EMP-2007",
        full_name="User Seven",
    )

    client = Client()
    initialize_session(client, "user7@example.com")
    timesheet = create_timesheet(client, "2026-05-04")

    empty_submit_response = client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    save_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "2.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    submit_response = client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    edit_after_submit_response = client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-05",
                        "project_id": context["project"].id,
                        "hours": "1.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert empty_submit_response.status_code == 400
    assert empty_submit_response.json()["error"]["code"] == "TIMESHEET_SUBMIT_EMPTY"
    assert save_response.status_code == 200
    assert submit_response.status_code == 200
    assert edit_after_submit_response.status_code == 400
    assert edit_after_submit_response.json()["error"]["code"] == "TIMESHEET_NOT_EDITABLE"


@pytest.mark.django_db
def test_submit_creates_project_approval_items_and_pm_worklist() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user8@example.com",
        employee_code="EMP-2008",
        full_name="User Eight",
    )

    employee_client = Client()
    initialize_session(employee_client, "user8@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")

    save_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "5.00",
                        "comment_text": "Project delivery",
                    },
                    {
                        "work_date": "2026-05-05",
                        "general_charge_code_id": context["general_charge_code"].id,
                        "hours": "2.00",
                        "comment_text": "Internal admin",
                    },
                ]
            }
        ),
        content_type="application/json",
    )
    submit_response = employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({"comment_text": "Ready for review"}),
        content_type="application/json",
    )

    assert save_response.status_code == 200
    assert submit_response.status_code == 200
    assert submit_response.json()["timesheet"]["status"] == "SUBMITTED"

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])
    assert approval_item.scope_type.value_code == "PROJECT"
    assert approval_item.status.value_code == "PENDING"
    assert approval_item.project_id == context["project"].id
    assert approval_item.approver_employee_id == context["project_manager"].id

    project_line = TimesheetLine.objects.get(
        weekly_timesheet_id=timesheet["id"], project_id=context["project"].id
    )
    general_code_line = TimesheetLine.objects.get(
        weekly_timesheet_id=timesheet["id"],
        general_charge_code_id=context["general_charge_code"].id,
    )
    assert project_line.approval_state.value_code == "PENDING"
    assert general_code_line.approval_state.value_code == "APPROVED"

    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    worklist_response = pm_client.get("/api/v1/approvals/")
    detail_response = pm_client.get(f"/api/v1/approvals/{approval_item.id}/")

    assert worklist_response.status_code == 200
    assert len(worklist_response.json()["approval_items"]) == 1
    assert worklist_response.json()["approval_items"][0]["id"] == approval_item.id
    assert detail_response.status_code == 200
    assert len(detail_response.json()["approval_item"]["lines"]) == 1
    assert (
        detail_response.json()["approval_item"]["lines"][0]["project"]["id"]
        == context["project"].id
    )


@pytest.mark.django_db
def test_cross_office_staffing_supports_timesheet_submit_and_pm_review() -> None:
    seed_reference_data()
    context = setup_cross_country_project_approval_context()

    employee_client = Client()
    initialize_session(employee_client, context["worker"].email)
    timesheet = create_timesheet(employee_client, "2026-05-04")
    editor_context = TimesheetService.get_timesheet_editor_context(
        CurrentUserService.build_for_employee(context["worker"]),
        timesheet["id"],
    )

    assert editor_context["available_projects"] == [
        {
            "id": context["project"].id,
            "project_code": context["project"].project_code,
            "name": context["project"].name,
        }
    ]

    save_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "5.00",
                        "comment_text": "Cross-country project work",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    submit_response = employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({"comment_text": "Submit cross-country project time"}),
        content_type="application/json",
    )

    assert save_response.status_code == 200
    assert submit_response.status_code == 200
    assert submit_response.json()["timesheet"]["status"] == "SUBMITTED"

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])
    timesheet_record = WeeklyTimesheet.objects.get(id=timesheet["id"])
    assert timesheet_record.business_unit_id == context["worker_business_unit"].id
    assert approval_item.project_id == context["project"].id
    assert approval_item.approver_employee_id == context["project_manager"].id

    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    worklist_response = pm_client.get("/api/v1/approvals/")
    detail_response = pm_client.get(f"/api/v1/approvals/{approval_item.id}/")

    assert worklist_response.status_code == 200
    assert worklist_response.json()["approval_items"][0]["timesheet_employee"]["employee_code"] == (
        "EMP-CC-WORKER"
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["approval_item"]["project"]["project_code"] == "PRJ-CC"
    assert detail_response.json()["approval_item"]["lines"][0]["comment_text"] == (
        "Cross-country project work"
    )


@pytest.mark.django_db
def test_project_manager_can_approve_final_pending_item_and_finalize_timesheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user9@example.com",
        employee_code="EMP-2009",
        full_name="User Nine",
    )

    employee_client = Client()
    initialize_session(employee_client, "user9@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    save_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    submit_response = employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert save_response.status_code == 200
    assert submit_response.status_code == 200

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])

    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    locked_models = record_select_for_update_models(monkeypatch)
    approve_response = pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/approve/",
        data=json.dumps({"comment_text": "Looks good"}),
        content_type="application/json",
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["approval_item"]["status"] == "APPROVED"
    assert WeeklyTimesheet in locked_models
    assert TimesheetSubmissionCycle in locked_models
    assert ApprovalItem in locked_models

    approval_item.refresh_from_db()
    submission_cycle = approval_item.submission_cycle
    submission_cycle.refresh_from_db()
    timesheet_record = submission_cycle.weekly_timesheet
    timesheet_record.refresh_from_db()

    assert approval_item.status.value_code == "APPROVED"
    assert submission_cycle.cycle_status.value_code == "COMPLETED"
    assert submission_cycle.outcome_status.value_code == "APPROVED"
    assert timesheet_record.status.value_code == "APPROVED"
    assert timesheet_record.final_approval_datetime is not None
    assert (
        TimesheetLine.objects.get(
            weekly_timesheet=timesheet_record,
            project=context["project"],
        ).approval_state.value_code
        == "APPROVED"
    )
    assert (
        ApprovalAction.objects.filter(
            approval_item=approval_item,
            action_type__value_code="APPROVE",
        ).count()
        == 1
    )

    second_approve_response = pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/approve/",
        data=json.dumps({"comment_text": "Duplicate click"}),
        content_type="application/json",
    )

    assert second_approve_response.status_code == 400
    assert second_approve_response.json()["error"]["code"] == "APPROVAL_ACTION_NOT_ALLOWED"
    assert (
        ApprovalAction.objects.filter(
            approval_item=approval_item,
            action_type__value_code="APPROVE",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_project_manager_reject_requires_reason_and_rejects_timesheet() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user10@example.com",
        employee_code="EMP-2010",
        full_name="User Ten",
    )

    employee_client = Client()
    initialize_session(employee_client, "user10@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "6.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])
    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)

    missing_reason_response = pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/reject/",
        data=json.dumps({}),
        content_type="application/json",
    )
    reject_response = pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/reject/",
        data=json.dumps({"reason_text": "Please split the hours by day"}),
        content_type="application/json",
    )

    assert missing_reason_response.status_code == 400
    assert missing_reason_response.json()["error"]["code"] == "APPROVAL_REJECTION_REASON_REQUIRED"
    assert reject_response.status_code == 200
    assert reject_response.json()["approval_item"]["status"] == "REJECTED"

    approval_item.refresh_from_db()
    submission_cycle = approval_item.submission_cycle
    submission_cycle.refresh_from_db()
    timesheet_record = submission_cycle.weekly_timesheet
    timesheet_record.refresh_from_db()

    assert approval_item.status.value_code == "REJECTED"
    assert approval_item.rejection_reason == "Please split the hours by day"
    assert submission_cycle.cycle_status.value_code == "COMPLETED"
    assert submission_cycle.outcome_status.value_code == "REJECTED"
    assert timesheet_record.status.value_code == "REJECTED"
    assert (
        TimesheetLine.objects.get(
            weekly_timesheet=timesheet_record,
            project=context["project"],
        ).approval_state.value_code
        == "REJECTED"
    )
    assert (
        ApprovalAction.objects.filter(
            approval_item=approval_item,
            action_type__value_code="REJECT",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_approved_timesheet_is_locked_until_admin_reopen() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user11@example.com",
        employee_code="EMP-2011",
        full_name="User Eleven",
    )
    admin = create_ts_admin_for_business_unit(
        business_unit=context["business_unit"],
        email="admin11@example.com",
        employee_code="EMP-ADMIN-11",
        full_name="Admin Eleven",
    )

    employee_client = Client()
    initialize_session(employee_client, "user11@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])
    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/approve/",
        data=json.dumps({"comment_text": "Approved"}),
        content_type="application/json",
    )

    locked_edit_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-05",
                        "project_id": context["project"].id,
                        "hours": "2.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    employee_reopen_response = employee_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/reopen/",
        data=json.dumps({"reason_text": "Need to correct coding"}),
        content_type="application/json",
    )

    admin_client = Client()
    initialize_session(admin_client, admin.email)
    missing_reason_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/reopen/",
        data=json.dumps({}),
        content_type="application/json",
    )
    reopen_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/reopen/",
        data=json.dumps({"reason_text": "Need to correct coding"}),
        content_type="application/json",
    )

    assert locked_edit_response.status_code == 400
    assert locked_edit_response.json()["error"]["code"] == "TIMESHEET_NOT_EDITABLE"
    assert employee_reopen_response.status_code == 400
    assert employee_reopen_response.json()["error"]["code"] == "TIMESHEET_REOPEN_NOT_ALLOWED"
    assert missing_reason_response.status_code == 400
    assert missing_reason_response.json()["error"]["code"] == "TIMESHEET_REOPEN_REASON_REQUIRED"
    assert reopen_response.status_code == 200
    assert reopen_response.json()["timesheet"]["status"] == "CREATED"
    assert reopen_response.json()["timesheet"]["final_approval_datetime"] is None
    assert reopen_response.json()["timesheet"]["archive_eligible_date"] is None
    assert reopen_response.json()["timesheet"]["lines"][0]["approval_state"] is None

    edit_after_reopen_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-05",
                        "project_id": context["project"].id,
                        "hours": "2.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert edit_after_reopen_response.status_code == 200
    assert (
        ApprovalAction.objects.filter(
            approval_item=approval_item,
            action_type__value_code="APPROVE",
        ).count()
        == 1
    )
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet",
            action_type__value_code="REOPEN",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_admin_can_withdraw_approved_timesheet_back_to_submitted() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user12a@example.com",
        employee_code="EMP-2012A",
        full_name="User Twelve A",
    )
    admin = create_ts_admin_for_business_unit(
        business_unit=context["business_unit"],
        email="admin12a@example.com",
        employee_code="EMP-ADMIN-12A",
        full_name="Admin Twelve A",
    )

    employee_client = Client()
    initialize_session(employee_client, "user12a@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])

    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/approve/",
        data=json.dumps({"comment_text": "Approved"}),
        content_type="application/json",
    )

    employee_withdraw_response = employee_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/withdraw/",
        data=json.dumps({"reason_text": "Recall final approval"}),
        content_type="application/json",
    )

    admin_client = Client()
    initialize_session(admin_client, admin.email)
    missing_reason_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/withdraw/",
        data=json.dumps({}),
        content_type="application/json",
    )
    admin_withdraw_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/withdraw/",
        data=json.dumps({"reason_text": "Recall final approval"}),
        content_type="application/json",
    )

    locked_edit_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-05",
                        "project_id": context["project"].id,
                        "hours": "2.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert employee_withdraw_response.status_code == 400
    assert (
        employee_withdraw_response.json()["error"]["code"] == "TIMESHEET_ADMIN_WITHDRAW_NOT_ALLOWED"
    )
    assert missing_reason_response.status_code == 400
    assert missing_reason_response.json()["error"]["code"] == "TIMESHEET_WITHDRAW_REASON_REQUIRED"
    assert admin_withdraw_response.status_code == 200
    assert admin_withdraw_response.json()["timesheet"]["status"] == "SUBMITTED"
    assert admin_withdraw_response.json()["timesheet"]["final_approval_datetime"] is None
    assert admin_withdraw_response.json()["timesheet"]["lines"][0]["approval_state"] == "APPROVED"
    assert locked_edit_response.status_code == 400
    assert locked_edit_response.json()["error"]["code"] == "TIMESHEET_NOT_EDITABLE"
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet",
            action_type__value_code="WITHDRAW",
        ).count()
        >= 1
    )


@pytest.mark.django_db
def test_admin_can_archive_only_eligible_approved_timesheet() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user12@example.com",
        employee_code="EMP-2012",
        full_name="User Twelve",
    )
    admin = create_ts_admin_for_business_unit(
        business_unit=context["business_unit"],
        email="admin12@example.com",
        employee_code="EMP-ADMIN-12",
        full_name="Admin Twelve",
    )

    employee_client = Client()
    initialize_session(employee_client, "user12@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])

    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/approve/",
        data=json.dumps({"comment_text": "Approved"}),
        content_type="application/json",
    )

    admin_client = Client()
    initialize_session(admin_client, admin.email)
    not_eligible_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/archive/",
        data=json.dumps({"comment_text": "Archive after retention"}),
        content_type="application/json",
    )

    timesheet_record = WeeklyTimesheet.objects.get(id=timesheet["id"])
    timesheet_record.archive_eligible_date = date.today()
    timesheet_record.updated_by = "system@test.local"
    timesheet_record.save(update_fields=["archive_eligible_date", "updated_by", "updated_at"])

    archive_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/archive/",
        data=json.dumps({"comment_text": "Archive after retention"}),
        content_type="application/json",
    )

    locked_edit_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-05",
                        "project_id": context["project"].id,
                        "hours": "2.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert not_eligible_response.status_code == 400
    assert not_eligible_response.json()["error"]["code"] == "TIMESHEET_NOT_ARCHIVE_ELIGIBLE"
    assert archive_response.status_code == 200
    assert archive_response.json()["timesheet"]["status"] == "ARCHIVED"
    assert archive_response.json()["timesheet"]["archive_eligible_date"] == date.today().isoformat()
    assert locked_edit_response.status_code == 400
    assert locked_edit_response.json()["error"]["code"] == "TIMESHEET_NOT_EDITABLE"
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet",
            action_type__value_code="ARCHIVE",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_admin_can_restore_archived_timesheet() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user13@example.com",
        employee_code="EMP-2013",
        full_name="User Thirteen",
    )
    admin = create_ts_admin_for_business_unit(
        business_unit=context["business_unit"],
        email="admin13@example.com",
        employee_code="EMP-ADMIN-13",
        full_name="Admin Thirteen",
    )

    employee_client = Client()
    initialize_session(employee_client, "user13@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet_id=timesheet["id"])

    pm_client = Client()
    initialize_session(pm_client, context["project_manager"].email)
    pm_client.post(
        f"/api/v1/approvals/{approval_item.id}/approve/",
        data=json.dumps({"comment_text": "Approved"}),
        content_type="application/json",
    )

    timesheet_record = WeeklyTimesheet.objects.get(id=timesheet["id"])
    timesheet_record.archive_eligible_date = date.today()
    timesheet_record.updated_by = "system@test.local"
    timesheet_record.save(update_fields=["archive_eligible_date", "updated_by", "updated_at"])

    admin_client = Client()
    initialize_session(admin_client, admin.email)
    archive_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/archive/",
        data=json.dumps({"comment_text": "Archive after retention"}),
        content_type="application/json",
    )
    employee_restore_response = employee_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/restore/",
        data=json.dumps({"comment_text": "Bring back online"}),
        content_type="application/json",
    )
    restore_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/restore/",
        data=json.dumps({"comment_text": "Bring back online"}),
        content_type="application/json",
    )

    assert archive_response.status_code == 200
    assert employee_restore_response.status_code == 400
    assert employee_restore_response.json()["error"]["code"] == "TIMESHEET_RESTORE_NOT_ALLOWED"
    assert restore_response.status_code == 200
    assert restore_response.json()["timesheet"]["status"] == "APPROVED"
    assert restore_response.json()["timesheet"]["final_approval_datetime"] is not None
    assert restore_response.json()["timesheet"]["archive_eligible_date"] == date.today().isoformat()
    assert restore_response.json()["timesheet"]["lines"][0]["approval_state"] == "APPROVED"
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet",
            action_type__value_code="RESTORE",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_period_cutoff_blocks_edit_and_submit_until_admin_override() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user14@example.com",
        employee_code="EMP-2014",
        full_name="User Fourteen",
    )
    admin = create_ts_admin_for_business_unit(
        business_unit=context["business_unit"],
        email="admin14@example.com",
        employee_code="EMP-ADMIN-14",
        full_name="Admin Fourteen",
    )

    employee_client = Client()
    initialize_session(employee_client, "user14@example.com")
    timesheet = create_timesheet(employee_client, "2026-05-04")
    save_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": context["project"].id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    assert save_response.status_code == 200

    configuration = context["business_unit"].office.configuration
    configuration.timesheet_cutoff_date = date(2026, 5, 11)
    configuration.updated_by = "system@test.local"
    configuration.save(update_fields=["timesheet_cutoff_date", "updated_by", "updated_at"])

    blocked_edit_response = employee_client.put(
        f"/api/v1/timesheets/{timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-05",
                        "project_id": context["project"].id,
                        "hours": "5.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    blocked_submit_response = employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )
    employee_override_response = employee_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/override-period-lock/",
        data=json.dumps({"reason_text": "Need late correction"}),
        content_type="application/json",
    )

    admin_client = Client()
    initialize_session(admin_client, admin.email)
    missing_reason_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/override-period-lock/",
        data=json.dumps({}),
        content_type="application/json",
    )
    override_response = admin_client.post(
        f"/api/v1/admin/timesheets/{timesheet['id']}/override-period-lock/",
        data=json.dumps({"reason_text": "Need late correction"}),
        content_type="application/json",
    )
    submit_after_override_response = employee_client.post(
        f"/api/v1/timesheets/{timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert blocked_edit_response.status_code == 400
    assert blocked_edit_response.json()["error"]["code"] == "TIMESHEET_PERIOD_LOCKED"
    assert blocked_submit_response.status_code == 400
    assert blocked_submit_response.json()["error"]["code"] == "TIMESHEET_PERIOD_LOCKED"
    assert employee_override_response.status_code == 400
    assert (
        employee_override_response.json()["error"]["code"]
        == "TIMESHEET_PERIOD_OVERRIDE_NOT_ALLOWED"
    )
    assert missing_reason_response.status_code == 400
    assert (
        missing_reason_response.json()["error"]["code"]
        == "TIMESHEET_PERIOD_OVERRIDE_REASON_REQUIRED"
    )
    assert override_response.status_code == 200
    assert override_response.json()["timesheet"]["period_lock_override_flag"] is True
    assert submit_after_override_response.status_code == 200
    assert submit_after_override_response.json()["timesheet"]["status"] == "SUBMITTED"
    assert (
        AuditLog.objects.filter(
            entity_name="weekly_timesheet",
            field_name="period_lock_override_flag",
            action_type__value_code="UPDATE",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_submit_blocks_self_approval_and_general_code_required_approval() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-SELF", name="Self Approval BU")
    create_business_unit_configuration(business_unit=business_unit, approval_mode_code="PROJECT")

    employee = create_employee(
        employee_code="EMP-SELF",
        full_name="Self Manager",
        email="self@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="PROJECT_MANAGER")
    assign_role(employee=employee, role_code="PROJECT_OWNER")

    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Default 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)

    client_record = create_client(
        business_unit=business_unit,
        client_code="C-SELF",
        name="Client Self",
    )
    category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT-SELF",
        name="Category Self",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-SELF",
        name="Cost Center Self",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-SELF",
        name="Project Self",
        project_owner_employee=employee,
        project_manager_employee=employee,
        client=client_record,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 1, 1),
    )
    assign_project(project=project, employee=employee, assignment_start_date=date(2026, 1, 1))

    requiring_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-REQ",
        name="Requires Approval",
        valid_from=date(2026, 1, 1),
        requires_approval_flag=True,
        approver_role_codes=["PROJECT_MANAGER"],
    )

    client = Client()
    initialize_session(client, "self@example.com")

    project_timesheet = create_timesheet(client, "2026-05-04")
    client.put(
        f"/api/v1/timesheets/{project_timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-04",
                        "project_id": project.id,
                        "hours": "4.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )
    self_approval_submit_response = client.post(
        f"/api/v1/timesheets/{project_timesheet['id']}/submit/",
        data=json.dumps({}),
        content_type="application/json",
    )

    general_code_timesheet = create_timesheet(client, "2026-05-11")
    general_code_save_response = client.put(
        f"/api/v1/timesheets/{general_code_timesheet['id']}/lines/",
        data=json.dumps(
            {
                "lines": [
                    {
                        "work_date": "2026-05-11",
                        "general_charge_code_id": requiring_code.id,
                        "hours": "2.00",
                    }
                ]
            }
        ),
        content_type="application/json",
    )

    assert self_approval_submit_response.status_code == 400
    assert (
        self_approval_submit_response.json()["error"]["code"]
        == "TIMESHEET_SELF_APPROVAL_NOT_ALLOWED"
    )
    assert general_code_save_response.status_code == 200


@pytest.mark.django_db
def test_timesheet_editor_context_keeps_general_charge_codes_with_routed_approval() -> None:
    seed_reference_data()
    context = setup_project_approval_context(
        email="user-hidden-gcc@example.com",
        employee_code="EMP-2012",
        full_name="User Hidden GCC",
    )
    context["general_charge_code"].requires_approval_flag = True
    context["general_charge_code"].updated_by = "system@test.local"
    context["general_charge_code"].save(
        update_fields=["requires_approval_flag", "updated_by", "updated_at"]
    )

    client = Client()
    initialize_session(client, "user-hidden-gcc@example.com")
    timesheet = create_timesheet(client, "2026-05-11")

    current_user = CurrentUserService.build_for_employee(context["employee"])
    editor_context = TimesheetService.get_timesheet_editor_context(
        current_user=current_user,
        timesheet_id=timesheet["id"],
    )

    assert [item["id"] for item in editor_context["available_general_charge_codes"]] == [
        context["general_charge_code"].id
    ]
