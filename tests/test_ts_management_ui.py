from datetime import UTC, date, datetime, timedelta

import pytest
from django.test import Client

from apps.master_data.models import Employee, OfficeConfiguration
from apps.timesheets.models import ApprovalItem, TimesheetLine, WeeklyTimesheet
from tests.helpers import (
    assign_calendar,
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
    initialize_ui_session,
    ref_value,
    seed_reference_data,
)


def _current_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _build_timesheet_ui_client(
    *,
    employee_email: str = "timesheet-user@example.com",
    employee_code: str = "EMP-TS-001",
    enable_copy_previous_week: bool = False,
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
    create_business_unit_configuration(business_unit=business_unit)
    OfficeConfiguration.objects.filter(office=business_unit.office).update(
        enable_copy_previous_week_flag=enable_copy_previous_week
    )

    client = Client()
    initialize_ui_session(client, employee.email)
    return (
        client,
        employee,
        {
            "business_unit": business_unit,
            "calendar": calendar,
            "project": project,
            "general_charge_code": general_charge_code,
            "project_owner_email": project_owner.email,
            "project_manager_email": project_manager.email,
            "week_start": _current_monday(),
        },
    )


def _build_ts_admin_client(*, business_unit, calendar, suffix: str) -> Client:
    admin = create_employee(
        employee_code=f"EMP-TS-ADMIN-{suffix}-ADMIN",
        full_name="Timesheet Admin",
        email=f"ts-admin-{suffix.lower()}@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=admin, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=admin,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=admin, role_code="USER")
    assign_role(employee=admin, role_code="TS_ADMIN")

    client = Client()
    initialize_ui_session(client, admin.email)
    return client


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
def test_my_timesheets_page_uses_header_create_controls_and_no_inline_create_panel() -> None:
    client, _, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-list@example.com",
        employee_code="EMP-TS-LIST",
    )
    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    response = client.get("/ts/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'action="/ts/"' in content
    assert "Filter Panel" in content
    assert "Create Weekly Timesheet" not in content
    assert "Weekly Timesheets" not in content
    assert "My History" not in content
    assert "Submitted At" in content
    assert "Approved At" in content
    assert "Copy Prev. Week" not in content
    assert "Lines" not in content
    assert "Submission No." not in content
    assert fixtures["week_start"].strftime("%m/%d/%Y") in content


@pytest.mark.django_db
def test_my_timesheets_page_can_copy_previous_approved_week_when_office_flag_enabled() -> None:
    client, _, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-copy@example.com",
        employee_code="EMP-TS-COPY",
        enable_copy_previous_week=True,
    )
    previous_week = fixtures["week_start"] - timedelta(days=7)

    create_response = client.post(
        "/ts/",
        data={"week_start_date": previous_week.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    source_timesheet = WeeklyTimesheet.objects.get(week_start_date=previous_week)
    save_response = client.post(
        f"/ts/timesheets/{source_timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": previous_week.isoformat(),
            "line_0_hours": "4.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Copied project work",
            "line_1_work_date": (previous_week + timedelta(days=1)).isoformat(),
            "line_1_hours": "2.50",
            "line_1_project_id": "",
            "line_1_general_charge_code_id": str(fixtures["general_charge_code"].id),
            "line_1_comment_text": "Copied admin work",
        },
        follow=False,
    )
    assert save_response.status_code == 302
    WeeklyTimesheet.objects.filter(id=source_timesheet.id).update(
        status=ref_value("TIMESHEET_STATUS", "APPROVED"),
        current_submission_no=1,
        submission_datetime=datetime.combine(previous_week, datetime.min.time(), tzinfo=UTC),
        final_approval_datetime=datetime.combine(
            previous_week + timedelta(days=2),
            datetime.min.time(),
            tzinfo=UTC,
        ),
    )

    page_response = client.get("/ts/")
    assert page_response.status_code == 200
    assert "Copy Prev. Week" in page_response.content.decode()

    copy_response = client.post(
        "/ts/",
        data={
            "week_start_date": fixtures["week_start"].isoformat(),
            "create_mode": "copy_previous_week",
        },
        follow=False,
    )

    assert copy_response.status_code == 302
    copied_timesheet = WeeklyTimesheet.objects.get(week_start_date=fixtures["week_start"])
    copied_lines = list(copied_timesheet.lines.order_by("work_date", "id"))
    assert len(copied_lines) == 2
    assert copied_lines[0].work_date == fixtures["week_start"]
    assert copied_lines[0].project_id == fixtures["project"].id
    assert str(copied_lines[0].hours) == "4.00"
    assert copied_lines[0].comment_text == "Copied project work"
    assert copied_lines[1].work_date == fixtures["week_start"] + timedelta(days=1)
    assert copied_lines[1].general_charge_code_id == fixtures["general_charge_code"].id
    assert str(copied_lines[1].hours) == "2.50"
    assert copied_lines[1].comment_text == "Copied admin work"


@pytest.mark.django_db
def test_my_timesheets_page_shows_missing_weeks_and_links_to_preselected_create_date() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-missing@example.com",
        employee_code="EMP-TS-MISSING",
    )
    previous_week = fixtures["week_start"] - timedelta(days=7)
    two_weeks_ago = fixtures["week_start"] - timedelta(days=14)
    Employee.objects.filter(id=employee.id).update(
        created_at=datetime.combine(two_weeks_ago, datetime.min.time(), tzinfo=UTC)
    )

    create_response = client.post(
        "/ts/",
        data={"week_start_date": previous_week.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    response = client.get("/ts/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Missing" in content
    assert two_weeks_ago.strftime("%m/%d/%Y") in content
    assert fixtures["week_start"].strftime("%m/%d/%Y") in content
    assert (
        f'href="/ts/?week_start_date={fixtures["week_start"].isoformat()}#create-timesheet"'
        in content
    )
    assert f'href="/ts/?week_start_date={two_weeks_ago.isoformat()}#create-timesheet"' in content
    assert f"/ts/timesheets/{WeeklyTimesheet.objects.get(employee=employee).id}/" in content

    preselected_response = client.get(f"/ts/?week_start_date={two_weeks_ago.isoformat()}")

    assert preselected_response.status_code == 200
    assert f'value="{two_weeks_ago.isoformat()}"' in preselected_response.content.decode()


@pytest.mark.django_db
def test_my_timesheets_page_filters_real_and_missing_rows() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-filtered@example.com",
        employee_code="EMP-TS-FILTER",
    )
    previous_week = fixtures["week_start"] - timedelta(days=7)
    two_weeks_ago = fixtures["week_start"] - timedelta(days=14)
    Employee.objects.filter(id=employee.id).update(
        created_at=datetime.combine(two_weeks_ago, datetime.min.time(), tzinfo=UTC)
    )

    create_response = client.post(
        "/ts/",
        data={"week_start_date": previous_week.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302
    timesheet = WeeklyTimesheet.objects.get(employee=employee, week_start_date=previous_week)
    lines_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": previous_week.isoformat(),
            "line_0_hours": "4.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Submitted filter work",
        },
        follow=False,
    )
    assert lines_response.status_code == 302
    submit_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={"form_name": "submit", "comment_text": "Filter test submit"},
        follow=False,
    )
    assert submit_response.status_code == 302

    missing_only_response = client.get("/ts/", data={"status": "Missing"})
    submitted_only_response = client.get(
        "/ts/",
        data={
            "status": "SUBMITTED",
            "week_start_from": previous_week.isoformat(),
            "week_start_to": previous_week.isoformat(),
        },
    )

    missing_content = missing_only_response.content.decode()
    submitted_content = submitted_only_response.content.decode()
    submitted_rows = submitted_only_response.context["table_rows"]

    assert missing_only_response.status_code == 200
    assert two_weeks_ago.strftime("%m/%d/%Y") in missing_content
    assert previous_week.strftime("%m/%d/%Y") not in missing_content
    assert fixtures["week_start"].strftime("%m/%d/%Y") in missing_content
    assert submitted_only_response.status_code == 200
    assert previous_week.strftime("%m/%d/%Y") in submitted_content
    assert two_weeks_ago.strftime("%m/%d/%Y") not in submitted_content
    assert [row["cells"][0] for row in submitted_rows] == [previous_week.strftime("%m/%d/%Y")]


@pytest.mark.django_db
def test_missing_timesheets_start_from_first_monday_after_employee_creation_date() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-missing-start@example.com",
        employee_code="EMP-TS-MISS-START",
    )
    last_tuesday = fixtures["week_start"] - timedelta(days=6)
    previous_monday = fixtures["week_start"] - timedelta(days=7)
    Employee.objects.filter(id=employee.id).update(
        created_at=datetime.combine(last_tuesday, datetime.min.time(), tzinfo=UTC)
    )

    response = client.get("/ts/")

    assert response.status_code == 200
    content = response.content.decode()
    assert (
        f'href="/ts/?week_start_date={fixtures["week_start"].isoformat()}#create-timesheet"'
        in content
    )
    assert (
        f'href="/ts/?week_start_date={previous_monday.isoformat()}#create-timesheet"' not in content
    )


@pytest.mark.django_db
def test_timesheet_detail_uses_compact_metadata_editable_row_controls_and_five_empty_rows() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-detail-ui@example.com",
        employee_code="EMP-TS-DETAIL",
    )
    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    response = client.get(f"/ts/timesheets/{timesheet.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Timesheet Context" not in content
    assert "Available Charge Targets" not in content
    assert "Assigned Calendar" in content
    assert "Submission No" in content
    assert "Submitted At" in content
    assert "Approved At" in content
    assert "Period Override" in content
    assert 'aria-label="Remove line"' in content
    assert 'aria-label="Add line"' in content
    assert 'name="row_count" value="5"' in content
    assert "Delete Timesheet" in content


@pytest.mark.django_db
def test_timesheet_detail_shows_short_dates_for_submission_and_approval_metadata() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-detail-dates@example.com",
        employee_code="EMP-TS-DETAIL-DATES",
    )
    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    submitted_at = datetime(2026, 5, 4, 9, 30, tzinfo=UTC)
    approved_at = datetime(2026, 5, 5, 17, 45, tzinfo=UTC)
    WeeklyTimesheet.objects.filter(id=timesheet.id).update(
        submission_datetime=submitted_at,
        final_approval_datetime=approved_at,
    )

    response = client.get(f"/ts/timesheets/{timesheet.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "05/04/2026" in content
    assert "05/05/2026" in content
    assert submitted_at.isoformat() not in content
    assert approved_at.isoformat() not in content


@pytest.mark.django_db
def test_created_timesheet_can_be_deleted_from_editor() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-delete-ui@example.com",
        employee_code="EMP-TS-DELETE",
    )
    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    delete_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == "/ts/"
    assert not WeeklyTimesheet.objects.filter(id=timesheet.id).exists()


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
def test_timesheet_editor_shows_submission_blocker_for_legacy_general_code_requiring_approval() -> (
    None
):
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-blocked@example.com",
        employee_code="EMP-TS-BLOCKED",
    )
    fixtures["general_charge_code"].requires_approval_flag = True
    fixtures["general_charge_code"].updated_by = "system@test.local"
    fixtures["general_charge_code"].save(
        update_fields=["requires_approval_flag", "updated_by", "updated_at"]
    )

    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    TimesheetLine.objects.create(
        weekly_timesheet=timesheet,
        work_date=fixtures["week_start"],
        general_charge_code=fixtures["general_charge_code"],
        hours="2.00",
        comment_text="Legacy unsupported general code line",
        billable_flag=fixtures["general_charge_code"].billable_flag,
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    detail_response = client.get(f"/ts/timesheets/{timesheet.id}/")

    assert detail_response.status_code == 200
    content = detail_response.content.decode()
    assert "Submission Blocked" in content
    assert "General charge code approval routing does not currently resolve" in content
    assert fixtures["general_charge_code"].code in content
    assert "Submit Timesheet" not in content


@pytest.mark.django_db
def test_timesheet_editor_shows_working_weekend_dates_only() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="weekend-ui@example.com",
        employee_code="EMP-TS-WEEKEND",
    )
    employee.assigned_calendar.period_rules.all().update(
        working_on_saturdays_flag=True,
        working_on_sundays_flag=True,
        saturday_max_hours="4.00",
        sunday_max_hours="4.00",
    )
    create_calendar_special_day(
        yearly_calendar=employee.assigned_calendar,
        special_date=fixtures["week_start"] + timedelta(days=6),
        day_type_code="OTHER",
    )

    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    detail_response = client.get(create_response.headers["Location"])
    content = detail_response.content.decode()

    assert detail_response.status_code == 200
    assert f'value="{(fixtures["week_start"] + timedelta(days=5)).isoformat()}"' in content
    assert f'value="{(fixtures["week_start"] + timedelta(days=6)).isoformat()}"' not in content


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
def test_ts_admin_can_reopen_approved_timesheet_from_detail_ui() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-admin-reopen@example.com",
        employee_code="EMP-TS-ADMIN-REOPEN",
    )
    admin_client = _build_ts_admin_client(
        business_unit=fixtures["business_unit"],
        calendar=fixtures["calendar"],
        suffix="REOPEN",
    )

    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    save_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": fixtures["week_start"].isoformat(),
            "line_0_hours": "4.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Needs admin reopen test",
        },
        follow=False,
    )
    assert save_response.status_code == 302
    submit_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={"form_name": "submit", "comment_text": "Submit for reopen UI"},
        follow=False,
    )
    assert submit_response.status_code == 302

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet=timesheet)
    pm_client = Client()
    initialize_ui_session(pm_client, fixtures["project_manager_email"])
    approve_response = pm_client.post(
        f"/approvals/{approval_item.id}/",
        data={"form_name": "approve", "comment_text": "Approved for admin reopen"},
        follow=False,
    )
    assert approve_response.status_code == 302

    detail_response = admin_client.get(
        f"/ts/timesheets/{timesheet.id}/",
        data={"next": "/approvals/"},
    )
    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert "Admin Exception Actions" in detail_content
    assert "Reopen Timesheet" in detail_content
    assert 'name="next" value="/approvals/"' in detail_content

    reopen_response = admin_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "reopen",
            "reason_text": "Need to correct coding",
            "next": "/approvals/",
        },
        follow=False,
    )

    assert reopen_response.status_code == 302
    assert (
        reopen_response.headers["Location"]
        == f"/ts/timesheets/{timesheet.id}/?next=%2Fapprovals%2F"
    )
    timesheet.refresh_from_db()
    assert timesheet.status.value_code == "CREATED"
    assert timesheet.final_approval_datetime is None


@pytest.mark.django_db
def test_ts_admin_can_archive_and_restore_from_detail_ui() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="timesheet-admin-archive@example.com",
        employee_code="EMP-TS-ADMIN-ARCHIVE",
    )
    admin_client = _build_ts_admin_client(
        business_unit=fixtures["business_unit"],
        calendar=fixtures["calendar"],
        suffix="ARCHIVE",
    )

    create_response = client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    save_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": fixtures["week_start"].isoformat(),
            "line_0_hours": "4.00",
            "line_0_project_id": str(fixtures["project"].id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Needs archive test",
        },
        follow=False,
    )
    assert save_response.status_code == 302
    submit_response = client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={"form_name": "submit", "comment_text": "Submit for archive UI"},
        follow=False,
    )
    assert submit_response.status_code == 302

    approval_item = ApprovalItem.objects.get(submission_cycle__weekly_timesheet=timesheet)
    pm_client = Client()
    initialize_ui_session(pm_client, fixtures["project_manager_email"])
    approve_response = pm_client.post(
        f"/approvals/{approval_item.id}/",
        data={"form_name": "approve", "comment_text": "Approved for archive"},
        follow=False,
    )
    assert approve_response.status_code == 302

    WeeklyTimesheet.objects.filter(id=timesheet.id).update(
        archive_eligible_date=_current_monday() - timedelta(days=1)
    )
    timesheet.refresh_from_db()

    archive_response = admin_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "archive",
            "comment_text": "Archive from UI",
            "next": "/approvals/",
        },
        follow=False,
    )

    assert archive_response.status_code == 302
    timesheet.refresh_from_db()
    assert timesheet.status.value_code == "ARCHIVED"

    archived_detail_response = admin_client.get(
        f"/ts/timesheets/{timesheet.id}/",
        data={"next": "/approvals/"},
    )
    archived_content = archived_detail_response.content.decode()
    assert archived_detail_response.status_code == 200
    assert "Restore Timesheet" in archived_content

    restore_response = admin_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "restore",
            "comment_text": "Restore from UI",
            "next": "/approvals/",
        },
        follow=False,
    )

    assert restore_response.status_code == 302
    timesheet.refresh_from_db()
    assert timesheet.status.value_code == "APPROVED"


@pytest.mark.django_db
def test_my_history_redirects_to_the_merged_my_timesheets_view() -> None:
    client, employee, fixtures = _build_timesheet_ui_client(
        employee_email="history-user@example.com"
    )
    client.post(
        "/ts/",
        data={"week_start_date": fixtures["week_start"].isoformat()},
        follow=False,
    )
    timesheet = WeeklyTimesheet.objects.get(employee=employee)

    history_response = client.get("/ts/history/", follow=False)

    assert history_response.status_code == 302
    assert history_response.headers["Location"] == "/ts/"

    merged_response = client.get("/ts/")

    assert merged_response.status_code == 200
    content = merged_response.content.decode()
    assert "My History" not in content
    assert fixtures["week_start"].strftime("%m/%d/%Y") in content
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
