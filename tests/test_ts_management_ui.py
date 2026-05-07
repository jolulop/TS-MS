from datetime import date, timedelta

import pytest
from django.test import Client

from apps.master_data.models import Employee
from apps.timesheets.models import WeeklyTimesheet
from tests.helpers import (
    assign_calendar,
    assign_employee_to_business_unit,
    assign_project,
    assign_role,
    create_business_unit,
    create_calendar_period_rule,
    create_client,
    create_cost_center,
    create_employee,
    create_general_charge_code,
    create_internal_category,
    create_office,
    create_project,
    create_yearly_calendar,
    initialize_ui_session,
    seed_reference_data,
)


def _current_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _build_timesheet_ui_client(
    *,
    employee_email: str = "timesheet-user@example.com",
    employee_code: str = "EMP-TS-001",
) -> tuple[Client, Employee, dict]:
    seed_reference_data()
    suffix = employee_code.replace("EMP-", "").replace("-", "")
    business_unit = create_business_unit(bu_code=f"BU-{suffix}", name="TS BU")
    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=_current_monday().year,
        calendar_name="TS Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(_current_monday().year, 1, 1),
        effective_to=date(_current_monday().year, 12, 31),
    )
    employee = create_employee(
        employee_code=employee_code,
        full_name="Timesheet User",
        email=employee_email,
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    project_owner = create_employee(
        employee_code=f"{employee_code}-PO",
        full_name="Project Owner",
        email=f"owner-{employee_email}",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=project_owner, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")

    project_manager = create_employee(
        employee_code=f"{employee_code}-PM",
        full_name="Project Manager",
        email=f"manager-{employee_email}",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=project_manager, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="USER")
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    client_record = create_client(
        business_unit=business_unit,
        client_code=f"CLI-{suffix}",
        name="Timesheet Client",
    )
    internal_category = create_internal_category(
        business_unit=business_unit,
        category_code=f"IC-{suffix}",
        name="Timesheet Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code=f"CC-{suffix}",
        name="Timesheet Cost Center",
    )
    project = create_project(
        business_unit=business_unit,
        project_code=f"PRJ-{suffix}",
        name="Timesheet Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=_current_monday() - timedelta(days=7),
    )
    assign_project(
        project=project,
        employee=employee,
        assignment_start_date=_current_monday() - timedelta(days=7),
    )
    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code=f"GCC-{suffix}",
        name="Timesheet General Code",
        valid_from=_current_monday() - timedelta(days=7),
    )

    client = Client()
    initialize_ui_session(client, employee.email)
    return (
        client,
        employee,
        {
            "project": project,
            "general_charge_code": general_charge_code,
            "project_owner_email": project_owner.email,
            "project_manager_email": project_manager.email,
            "week_start": _current_monday(),
        },
    )


@pytest.mark.django_db
def test_my_timesheets_page_creates_weekly_timesheet_from_html() -> None:
    client, _, fixtures = _build_timesheet_ui_client()

    response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )

    assert response.status_code == 302
    timesheet = WeeklyTimesheet.objects.get(employee__email="timesheet-user@example.com")
    assert response.headers["Location"] == f"/ts/timesheets/{timesheet.id}/"


@pytest.mark.django_db
def test_timesheet_editor_saves_lines_and_submits_via_html() -> None:
    client, employee, fixtures = _build_timesheet_ui_client()
    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    line_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": fixtures["week_start"].isoformat(),
            "line_0_hours": "4.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Project delivery",
            "line_1_work_date": (fixtures["week_start"] + timedelta(days=1)).isoformat(),
            "line_1_hours": "2.50",
            "line_1_project_id": "",
            "line_1_general_charge_code_id": str(fixtures["general_charge_code"].id),
            "line_1_comment_text": "Admin support",
        },
        follow=False,
    )
    assert line_response.status_code == 302

    submit_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "submit",
            "comment_text": "Ready for approval",
        },
        follow=False,
    )
    assert submit_response.status_code == 302

    detail_response = client.get(f"/ts/timesheets/{timesheet.id}/")
    content = detail_response.content.decode()

    timesheet.refresh_from_db()
    assert timesheet.status.value_code == "SUBMITTED"
    assert "Timesheet Lines" in content
    assert "Withdraw Timesheet" in content
    assert "Weekly Timesheet Editor" not in content


@pytest.mark.django_db
def test_timesheet_editor_lists_assigned_project_from_other_country() -> None:
    seed_reference_data()
    home_country = create_office(office_name="TS UI Project Office")
    foreign_country = create_office(office_name="TS UI Worker Office")
    project_business_unit = create_business_unit(
        bu_code="BU-TS-PROJ",
        name="TS UI Project BU",
        office=home_country,
    )
    worker_business_unit = create_business_unit(
        bu_code="BU-TS-WORKER",
        name="TS UI Worker BU",
        office=foreign_country,
    )
    calendar = create_yearly_calendar(
        business_unit=worker_business_unit,
        calendar_year=_current_monday().year,
        calendar_name="Worker Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(_current_monday().year, 1, 1),
        effective_to=date(_current_monday().year, 12, 31),
    )
    employee = create_employee(
        employee_code="EMP-TS-CC",
        full_name="Cross Office UI User",
        email="timesheet-cross-country@example.com",
        primary_business_unit=worker_business_unit,
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=worker_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    project_owner = create_employee(
        employee_code="EMP-TS-CC-PO",
        full_name="Cross Office Owner",
        email="timesheet-cross-country-owner@example.com",
        primary_business_unit=project_business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=project_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")

    project_manager = create_employee(
        employee_code="EMP-TS-CC-PM",
        full_name="Cross Office Manager",
        email="timesheet-cross-country-manager@example.com",
        primary_business_unit=project_business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=project_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    client_record = create_client(
        business_unit=project_business_unit,
        client_code="CLI-TS-CC",
        name="TS UI Client",
    )
    internal_category = create_internal_category(
        business_unit=project_business_unit,
        category_code="IC-TS-CC",
        name="TS UI Category",
    )
    cost_center = create_cost_center(
        business_unit=project_business_unit,
        cost_center_code="CC-TS-CC",
        name="TS UI Cost Center",
    )
    project = create_project(
        business_unit=project_business_unit,
        project_code="PRJ-TS-CC",
        name="TS UI Cross Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=_current_monday() - timedelta(days=7),
    )
    assign_project(
        project=project,
        employee=employee,
        assignment_start_date=_current_monday() - timedelta(days=7),
    )

    client = Client()
    initialize_ui_session(client, employee.email)
    create_response = client.post(
        "/ts/",
        data={"week_start_date": _current_monday().isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    detail_response = client.get(create_response.headers["Location"])

    assert detail_response.status_code == 200
    content = detail_response.content.decode()
    assert "PRJ-TS-CC" in content


@pytest.mark.django_db
def test_submitted_timesheet_can_be_withdrawn_from_ui() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="withdraw-user@example.com"
    )
    client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": fixtures["week_start"].isoformat(),
            "line_0_hours": "8.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Full day project work",
        },
        follow=False,
    )
    client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={"form_name": "submit", "comment_text": "Submit before withdraw"},
        follow=False,
    )

    withdraw_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={"form_name": "withdraw", "comment_text": "Need one more correction"},
        follow=False,
    )

    assert withdraw_response.status_code == 302
    timesheet.refresh_from_db()
    assert timesheet.status.value_code == "CREATED"

    detail_response = client.get(f"/ts/timesheets/{timesheet.id}/")
    assert "Weekly Timesheet Editor" in detail_response.content.decode()


@pytest.mark.django_db
def test_my_history_lists_timesheets_in_read_only_view() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="history-user@example.com"
    )
    client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    timesheet = WeeklyTimesheet.objects.get(employee=employee)

    history_response = client.get("/ts/history/")

    assert history_response.status_code == 200
    content = history_response.content.decode()
    assert "My History" in content
    assert fixtures["week_start"].isoformat() in content
    assert f"/ts/timesheets/{timesheet.id}/" in content


@pytest.mark.django_db
def test_project_owner_can_open_live_project_time_inquiry() -> None:
    employee_client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="inquiry-user@example.com",
        employee_code="EMP-TS-INQ",
    )
    employee_client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    employee_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": fixtures["week_start"].isoformat(),
            "line_0_hours": "6.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Inquiry project work",
            "line_1_work_date": (fixtures["week_start"] + timedelta(days=1)).isoformat(),
            "line_1_hours": "2.00",
            "line_1_project_id": "",
            "line_1_general_charge_code_id": str(fixtures["general_charge_code"].id),
            "line_1_comment_text": "General support work",
        },
        follow=False,
    )

    owner_client = Client()
    initialize_ui_session(owner_client, fixtures["project_owner_email"])
    response = owner_client.get("/ts/inquiry/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Project Time Inquiry" in content
    assert "Filter Panel" in content
    assert "EMP-TS-INQ" in content
    assert fixtures["project"].project_code in content
    assert "General support work" not in content
    assert 'href="/ts/inquiry/"' in content
    assert "Back to My Timesheets" in content


@pytest.mark.django_db
def test_regular_user_cannot_open_project_time_inquiry() -> None:
    client, _, _ = _build_timesheet_ui_client(
        employee_email="inquiry-denied@example.com",
        employee_code="EMP-TS-DENIED",
    )

    response = client.get("/ts/inquiry/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()


@pytest.mark.django_db
def test_user_cannot_open_another_users_timesheet_detail() -> None:
    owner_client, _, fixtures = _build_timesheet_ui_client(employee_email="owner-ui@example.com")
    owner_client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    owner_timesheet = WeeklyTimesheet.objects.get(employee__email="owner-ui@example.com")

    other_client, _, _ = _build_timesheet_ui_client(
        employee_email="other-ui@example.com",
        employee_code="EMP-TS-OTHER",
    )
    response = other_client.get(f"/ts/timesheets/{owner_timesheet.id}/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()
