import re
from datetime import UTC, date, datetime, timedelta

import pytest
from django.test import Client

from apps.master_data.models import Employee
from apps.timesheets.models import ApprovalItem, WeeklyTimesheet
from tests.helpers import (
    assign_calendar,
    assign_employee_to_business_unit,
    assign_project,
    assign_role,
    create_business_unit,
    create_business_unit_configuration,
    create_calendar_period_rule,
    create_client,
    create_cost_center,
    create_employee,
    create_internal_category,
    create_project,
    create_yearly_calendar,
    initialize_ui_session,
    ref_value,
    seed_reference_data,
)


def _build_project_management_context() -> dict:
    seed_reference_data()
    missing_week = date(2026, 4, 27)
    approved_week = date(2026, 5, 4)
    pending_week = date(2026, 5, 11)
    business_unit = create_business_unit(bu_code="BU-PRJ-MGMT", name="Project Mgmt BU")
    create_business_unit_configuration(
        business_unit=business_unit,
        approval_mode_code="PROJECT",
    )
    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Project Mgmt Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )

    employee = create_employee(
        employee_code="EMP-PRJ-MGMT",
        full_name="Project Mgmt Employee",
        email="project-mgmt-employee@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    Employee.objects.filter(id=employee.id).update(created_at=datetime(2026, 4, 27, tzinfo=UTC))

    project_owner = create_employee(
        employee_code="EMP-PRJ-OWNER",
        full_name="Project Mgmt Owner",
        email="project-mgmt-owner@example.com",
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
        employee_code="EMP-PRJ-MANAGER",
        full_name="Project Mgmt Manager",
        email="project-mgmt-manager@example.com",
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

    ts_admin = create_employee(
        employee_code="EMP-PRJ-ADMIN",
        full_name="Project Mgmt Admin",
        email="project-mgmt-admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=ts_admin, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=ts_admin,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=ts_admin, role_code="USER")
    assign_role(employee=ts_admin, role_code="TS_ADMIN")

    client_record = create_client(
        business_unit=business_unit,
        client_code="CLI-PRJ-MGMT",
        name="Project Mgmt Client",
    )
    internal_category = create_internal_category(
        business_unit=business_unit,
        category_code="IC-PRJ-MGMT",
        name="Project Mgmt Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-PRJ-MGMT",
        name="Project Mgmt Cost Center",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-MGMT",
        name="Project Mgmt Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=missing_week,
        billable_flag=True,
    )
    assign_project(
        project=project,
        employee=employee,
        assignment_start_date=missing_week,
    )

    employee_client = Client()
    owner_client = Client()
    pm_client = Client()
    admin_client = Client()
    initialize_ui_session(employee_client, employee.email)
    initialize_ui_session(owner_client, project_owner.email)
    initialize_ui_session(pm_client, project_manager.email)
    initialize_ui_session(admin_client, ts_admin.email)

    def _create_and_submit_timesheet(week_start: date, hours: str, comment_text: str) -> WeeklyTimesheet:
        create_response = employee_client.post(
            "/ts/",
            data={"week_start_date": week_start.isoformat()},
            follow=False,
        )
        assert create_response.status_code == 302
        timesheet = WeeklyTimesheet.objects.get(employee=employee, week_start_date=week_start)
        save_response = employee_client.post(
            f"/ts/timesheets/{timesheet.id}/",
            data={
                "form_name": "lines",
                "row_count": "8",
                "line_0_work_date": week_start.isoformat(),
                "line_0_hours": hours,
                "line_0_project_id": str(project.id),
                "line_0_general_charge_code_id": "",
                "line_0_comment_text": comment_text,
            },
            follow=False,
        )
        assert save_response.status_code == 302
        submit_response = employee_client.post(
            f"/ts/timesheets/{timesheet.id}/",
            data={"form_name": "submit", "comment_text": comment_text},
            follow=False,
        )
        assert submit_response.status_code == 302
        timesheet.refresh_from_db()
        return timesheet

    approved_timesheet = _create_and_submit_timesheet(
        approved_week,
        "6.00",
        "Approved project delivery work",
    )
    pending_timesheet = _create_and_submit_timesheet(
        pending_week,
        "4.00",
        "Pending project review work",
    )

    approved_item = ApprovalItem.objects.get(
        submission_cycle__weekly_timesheet=approved_timesheet,
        project=project,
    )
    approve_response = pm_client.post(
        f"/approvals/{approved_item.id}/",
        data={"form_name": "approve", "comment_text": "Looks good"},
        follow=False,
    )
    assert approve_response.status_code == 302

    pending_item = ApprovalItem.objects.get(
        submission_cycle__weekly_timesheet=pending_timesheet,
        project=project,
    )

    return {
        "owner_client": owner_client,
        "pm_client": pm_client,
        "admin_client": admin_client,
        "business_unit": business_unit,
        "project_owner": project_owner,
        "project_manager": project_manager,
        "client": client_record,
        "project": project,
        "pending_item": pending_item,
    }


@pytest.mark.django_db
def test_project_owner_project_management_grid_shows_summary_links(monkeypatch) -> None:
    monkeypatch.setattr("apps.core.ts_views._current_monday", lambda today=None: date(2026, 5, 11))
    context = _build_project_management_context()

    response = context["owner_client"].get("/ts/projects/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Project Management" in content
    assert "<th>Client</th>" in content
    assert "Pend. Appr." in content
    assert "Pend. TS" not in content
    assert "Project Mgmt Client" in content
    assert '<a href="/system/projects/%d/">Project Mgmt Project</a>' % context["project"].id in content
    assert 'href="/reports/project-time/?project_id=%d">6.00</a>' % context["project"].id in content
    assert 'href="/approvals/?project_id=%d">1</a>' % context["project"].id in content
    assert 'href="/reports/missing-timesheets/?project_ids=%d">1</a>' % context["project"].id in content


@pytest.mark.django_db
def test_project_manager_project_management_hides_owner_only_links(monkeypatch) -> None:
    monkeypatch.setattr("apps.core.ts_views._current_monday", lambda today=None: date(2026, 5, 11))
    context = _build_project_management_context()

    response = context["pm_client"].get("/ts/projects/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'href="/system/projects/%d/"' % context["project"].id not in content
    assert 'href="/approvals/?project_id=%d">1</a>' % context["project"].id in content
    assert 'href="/reports/project-time/?project_id=%d">6.00</a>' % context["project"].id in content
    assert 'href="/reports/missing-timesheets/?project_ids=%d">1</a>' % context["project"].id in content


@pytest.mark.django_db
def test_ts_admin_project_management_links_to_project_and_approval_worklist(monkeypatch) -> None:
    monkeypatch.setattr("apps.core.ts_views._current_monday", lambda today=None: date(2026, 5, 11))
    context = _build_project_management_context()

    response = context["admin_client"].get("/ts/projects/")

    assert response.status_code == 200
    content = response.content.decode()
    assert '<a href="/system/projects/%d/">Project Mgmt Project</a>' % context["project"].id in content
    assert 'href="/approvals/?project_id=%d">1</a>' % context["project"].id in content


@pytest.mark.django_db
def test_project_owner_can_open_project_detail_and_filtered_approval_worklist() -> None:
    context = _build_project_management_context()

    detail_response = context["owner_client"].get(f"/system/projects/{context['project'].id}/")
    worklist_response = context["owner_client"].get(
        f"/approvals/?project_id={context['project'].id}"
    )

    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert "Edit Project" in detail_content
    assert worklist_response.status_code == 200
    worklist_content = worklist_response.content.decode()
    assert "Approval Worklist" in worklist_content
    assert "Project Mgmt Employee" in worklist_content
    assert "Project Mgmt Project" in worklist_content


@pytest.mark.django_db
def test_project_manager_and_ts_admin_can_open_filtered_project_approval_worklist() -> None:
    context = _build_project_management_context()

    pm_response = context["pm_client"].get(f"/approvals/?project_id={context['project'].id}")
    admin_response = context["admin_client"].get(
        f"/approvals/?project_id={context['project'].id}"
    )

    assert pm_response.status_code == 200
    pm_content = pm_response.content.decode()
    assert "Approval Worklist" in pm_content
    assert "Project Mgmt Employee" in pm_content
    assert "Project Mgmt Project" in pm_content

    assert admin_response.status_code == 200
    admin_content = admin_response.content.decode()
    assert "Approval Oversight" in admin_content
    assert "Project Mgmt Employee" in admin_content
    assert "Project Mgmt Project" in admin_content


@pytest.mark.django_db
def test_zero_pending_count_renders_as_plain_text(monkeypatch) -> None:
    monkeypatch.setattr("apps.core.ts_views._current_monday", lambda today=None: date(2026, 5, 11))
    context = _build_project_management_context()
    pending_item = context["pending_item"]
    pending_item.status = ref_value("APPROVAL_STATUS", "APPROVED")
    pending_item.save(update_fields=["status", "updated_at"])
    pending_timesheet = pending_item.submission_cycle.weekly_timesheet
    pending_timesheet.status = ref_value("TIMESHEET_STATUS", "APPROVED")
    pending_timesheet.save(update_fields=["status", "updated_at"])

    response = context["owner_client"].get("/ts/projects/")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'href="/approvals/?project_id=%d">0</a>' % context["project"].id not in content
    assert re.search(r"<td>\s*0\s*</td>", content) is not None


@pytest.mark.django_db
def test_project_management_client_filter_preserves_status_and_filters_rows(monkeypatch) -> None:
    monkeypatch.setattr("apps.core.ts_views._current_monday", lambda today=None: date(2026, 5, 11))
    context = _build_project_management_context()
    other_client = create_client(
        business_unit=context["business_unit"],
        client_code="CLI-PRJ-OTHER",
        name="Other Project Client",
    )
    other_project = create_project(
        business_unit=context["business_unit"],
        project_code="PRJ-MGMT-OTHER",
        name="Other Project",
        project_owner_employee=context["project_owner"],
        project_manager_employee=context["project_manager"],
        client=other_client,
        internal_category=context["project"].internal_category,
        cost_center=context["project"].cost_center,
        start_date=context["project"].start_date,
        billable_flag=True,
    )

    response = context["owner_client"].get(
        "/ts/projects/",
        data={"status": "ACTIVE", "client_id": str(context["client"].id)},
    )

    assert response.status_code == 200
    content = response.content.decode()
    filter_links = response.context["filter_links"]
    assert "Project Mgmt Project" in content
    assert 'href="/system/projects/%d/">Other Project</a>' % other_project.id not in content
    assert '<option value="%d" selected>Project Mgmt Client</option>' % context["client"].id in content
    assert [link["href"] for link in filter_links] == [
        "/ts/projects/?client_id=%d" % context["client"].id,
        "/ts/projects/?status=ACTIVE&client_id=%d" % context["client"].id,
        "/ts/projects/?status=CLOSED&client_id=%d" % context["client"].id,
        "/ts/projects/?status=DRAFT&client_id=%d" % context["client"].id,
    ]
