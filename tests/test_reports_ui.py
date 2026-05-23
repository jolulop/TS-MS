from datetime import UTC, date, datetime, timedelta

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.audit.services import write_audit_event
from apps.integrations.models import IntegrationJob
from apps.master_data.models import Employee, Project
from apps.timesheets.models import (
    ApprovalItem,
    TimesheetLine,
    TimesheetSubmissionCycle,
    WeeklyTimesheet,
)
from tests.helpers import (
    assign_calendar,
    assign_cross_office_project,
    assign_employee_to_business_unit,
    assign_project,
    assign_role,
    create_business_unit,
    create_business_unit_configuration,
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
    ref_value,
    seed_reference_data,
)


def _setup_reports_context() -> dict:
    seed_reference_data()
    week_start = date(2026, 5, 4)
    business_unit = create_business_unit(bu_code="BU-RPT", name="Reports BU")
    create_business_unit_configuration(business_unit=business_unit, approval_mode_code="PROJECT")
    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Reports Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )

    user = create_employee(
        employee_code="EMP-RPT-USER",
        full_name="Reports User",
        email="reports-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=user, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=user,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=user, role_code="USER")

    project_owner = create_employee(
        employee_code="EMP-RPT-PO",
        full_name="Reports Project Owner",
        email="reports-owner@example.com",
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
        employee_code="EMP-RPT-PM",
        full_name="Reports Project Manager",
        email="reports-pm@example.com",
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
        employee_code="EMP-RPT-ADM",
        full_name="Reports Admin",
        email="reports-admin@example.com",
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
        client_code="CLI-RPT",
        name="Reports Client",
    )
    internal_category = create_internal_category(
        business_unit=business_unit,
        category_code="IC-RPT",
        name="Reports Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-RPT",
        name="Reports Cost Center",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-RPT",
        name="Reports Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=week_start - timedelta(days=7),
        billable_flag=True,
    )
    assign_project(
        project=project,
        employee=user,
        assignment_start_date=week_start - timedelta(days=7),
    )
    missing_employee = create_employee(
        employee_code="EMP-RPT-MISS",
        full_name="Reports Missing Employee",
        email="reports-missing@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=missing_employee, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=missing_employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=missing_employee, role_code="USER")
    assign_project(
        project=project,
        employee=missing_employee,
        assignment_start_date=week_start,
    )
    Employee.objects.filter(id=missing_employee.id).update(
        created_at=datetime(2026, 5, 4, tzinfo=UTC)
    )
    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-RPT",
        name="Reports General Code",
        valid_from=week_start - timedelta(days=7),
    )

    user_client = Client()
    owner_client = Client()
    pm_client = Client()
    admin_client = Client()
    initialize_ui_session(user_client, user.email)
    initialize_ui_session(owner_client, project_owner.email)
    initialize_ui_session(pm_client, project_manager.email)
    initialize_ui_session(admin_client, ts_admin.email)

    approved_week_start = week_start - timedelta(days=7)
    previous_create_response = user_client.post(
        "/ts/",
        data={"week_start_date": approved_week_start.isoformat()},
        follow=False,
    )
    assert previous_create_response.status_code == 302
    previous_timesheet = WeeklyTimesheet.objects.get(week_start_date=approved_week_start)
    previous_save_response = user_client.post(
        previous_create_response.headers["Location"],
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": approved_week_start.isoformat(),
            "line_0_hours": "7.00",
            "line_0_project_id": str(project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Approved delivery work",
            "line_1_work_date": (approved_week_start + timedelta(days=1)).isoformat(),
            "line_1_hours": "1.00",
            "line_1_project_id": "",
            "line_1_general_charge_code_id": str(general_charge_code.id),
            "line_1_comment_text": "Approved admin work",
        },
        follow=False,
    )
    assert previous_save_response.status_code == 302
    previous_submit_response = user_client.post(
        previous_create_response.headers["Location"],
        data={"form_name": "submit", "comment_text": "Submit approved seed week"},
        follow=False,
    )
    assert previous_submit_response.status_code == 302
    previous_approval_item = ApprovalItem.objects.get(
        approver_employee_id=project_manager.id,
        submission_cycle__weekly_timesheet=previous_timesheet,
    )
    approve_response = pm_client.post(
        f"/api/v1/approvals/{previous_approval_item.id}/approve/",
        data='{"comment_text":"Approved for analytics fixtures"}',
        content_type="application/json",
    )
    assert approve_response.status_code == 200
    approved_submitted_at = datetime(2026, 4, 28, 9, 0, tzinfo=UTC)
    approved_decision_at = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    previous_timesheet.refresh_from_db()
    WeeklyTimesheet.objects.filter(id=previous_timesheet.id).update(
        submission_datetime=approved_submitted_at,
        final_approval_datetime=approved_decision_at,
    )
    previous_cycle = previous_timesheet.submission_cycles.get(submission_no=1)
    previous_cycle.submitted_at = approved_submitted_at
    previous_cycle.completed_at = approved_decision_at
    previous_cycle.save(update_fields=["submitted_at", "completed_at", "updated_at"])
    previous_approval_item.actions.update(action_timestamp=approved_decision_at)

    create_response = user_client.post(
        "/ts/",
        data={"week_start_date": week_start.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    user_client.post(
        create_response.headers["Location"],
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": week_start.isoformat(),
            "line_0_hours": "5.00",
            "line_0_project_id": str(project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Billable delivery",
            "line_1_work_date": (week_start + timedelta(days=1)).isoformat(),
            "line_1_hours": "3.00",
            "line_1_project_id": "",
            "line_1_general_charge_code_id": str(general_charge_code.id),
            "line_1_comment_text": "Admin support",
        },
        follow=False,
    )

    user_client.post(
        create_response.headers["Location"],
        data={"form_name": "submit", "comment_text": "Submit for reporting tests"},
        follow=False,
    )
    current_timesheet = WeeklyTimesheet.objects.get(week_start_date=week_start, employee=user)
    pending_submitted_at = datetime(2026, 5, 5, 10, 0, tzinfo=UTC)
    WeeklyTimesheet.objects.filter(id=current_timesheet.id).update(
        submission_datetime=pending_submitted_at
    )
    current_cycle = current_timesheet.submission_cycles.get(submission_no=1)
    current_cycle.submitted_at = pending_submitted_at
    current_cycle.save(update_fields=["submitted_at", "updated_at"])

    write_audit_event(
        action_code="EXPORT",
        entity_name="weekly_timesheet",
        entity_id=1,
        actor_employee=ts_admin,
        actor_email=ts_admin.email,
        business_unit=business_unit,
        reason_text="Nightly export validation",
    )

    IntegrationJob.objects.create(
        business_unit=business_unit,
        interface_code="EMPLOYEE_IMPORT",
        direction="INBOUND",
        status=ref_value("INTEGRATION_JOB_STATUS", "COMPLETED"),
        requested_by_employee=ts_admin,
        total_records=10,
        success_records=10,
        error_records=0,
        summary_message="Employee import completed",
        created_by="system@test.local",
    )

    return {
        "week_start": week_start,
        "user_client": user_client,
        "owner_client": owner_client,
        "pm_client": pm_client,
        "admin_client": admin_client,
        "project": project,
        "general_charge_code_id": general_charge_code.id,
        "missing_employee_email": missing_employee.email,
        "missing_employee_name": missing_employee.full_name,
    }


def _create_out_of_scope_report_data(context: dict) -> dict:
    week_start = context["week_start"]
    business_unit = create_business_unit(
        bu_code="BU-RPT-OUT",
        name="Reports Out Of Scope BU",
    )
    create_business_unit_configuration(business_unit=business_unit, approval_mode_code="PROJECT")
    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Reports Out Scope Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        business_unit=business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    employee = create_employee(
        employee_code="EMP-RPT-OUT",
        full_name="Reports Out Scope Employee",
        email="reports-out@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    owner = create_employee(
        employee_code="EMP-RPT-OUT-PO",
        full_name="Reports Out Scope Owner",
        email="reports-out-owner@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=owner,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=owner, role_code="PROJECT_OWNER")
    manager = create_employee(
        employee_code="EMP-RPT-OUT-PM",
        full_name="Reports Out Scope Manager",
        email="reports-out-manager@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=manager,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=manager, role_code="PROJECT_MANAGER")
    client_record = create_client(
        business_unit=business_unit,
        client_code="CLI-RPT-OUT",
        name="Reports Out Scope Client",
    )
    internal_category = create_internal_category(
        business_unit=business_unit,
        category_code="IC-RPT-OUT",
        name="Reports Out Scope Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-RPT-OUT",
        name="Reports Out Scope Cost Center",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-RPT-OUT-GUARD",
        name="Reports Out Scope Project Guard",
        project_owner_employee=owner,
        project_manager_employee=manager,
        client=client_record,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=week_start,
        billable_flag=True,
    )
    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-RPT-OUT-GUARD",
        name="Reports Out Scope GCC Guard",
        cost_center=cost_center,
        valid_from=week_start,
    )
    submitted_status = ref_value("TIMESHEET_STATUS", "SUBMITTED")
    archived_status = ref_value("TIMESHEET_STATUS", "ARCHIVED")
    timesheet = WeeklyTimesheet.objects.create(
        employee=employee,
        business_unit=business_unit,
        week_start_date=week_start,
        week_end_date=week_start + timedelta(days=6),
        status=submitted_status,
        submission_datetime=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    TimesheetLine.objects.create(
        weekly_timesheet=timesheet,
        work_date=week_start,
        project=project,
        hours="4.00",
        comment_text="OUT-SCOPE-PROJECT-LINE-GUARD",
        billable_flag=True,
        approval_state=ref_value("APPROVAL_STATUS", "PENDING"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    TimesheetLine.objects.create(
        weekly_timesheet=timesheet,
        work_date=week_start + timedelta(days=1),
        general_charge_code=general_charge_code,
        hours="2.00",
        comment_text="OUT-SCOPE-GCC-LINE-GUARD",
        billable_flag=False,
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    archived_timesheet = WeeklyTimesheet.objects.create(
        employee=employee,
        business_unit=business_unit,
        week_start_date=week_start + timedelta(days=7),
        week_end_date=week_start + timedelta(days=13),
        status=archived_status,
        archive_eligible_date=date(2026, 5, 31),
        comment_text="OUT-SCOPE-ARCHIVED-GUARD",
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    submission_cycle = TimesheetSubmissionCycle.objects.create(
        weekly_timesheet=timesheet,
        submission_no=1,
        submitted_by_employee=employee,
        submitted_at=datetime(2026, 5, 6, 9, 0, tzinfo=UTC),
        cycle_status=ref_value("SUBMISSION_CYCLE_STATUS", "OPEN"),
        outcome_status=ref_value("APPROVAL_STATUS", "PENDING"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    ApprovalItem.objects.create(
        submission_cycle=submission_cycle,
        scope_type=ref_value("APPROVAL_SCOPE_TYPE", "PROJECT"),
        approver_employee=manager,
        project=project,
        status=ref_value("APPROVAL_STATUS", "PENDING"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    write_audit_event(
        action_code="EXPORT",
        entity_name="out_scope_report_guard",
        entity_id=archived_timesheet.id,
        actor_employee=employee,
        actor_email=employee.email,
        business_unit=business_unit,
        reason_text="OUT-SCOPE-AUDIT-GUARD",
    )
    IntegrationJob.objects.create(
        business_unit=business_unit,
        interface_code="OUT_SCOPE_JOB_GUARD",
        direction="INBOUND",
        status=ref_value("INTEGRATION_JOB_STATUS", "COMPLETED"),
        requested_by_employee=employee,
        total_records=1,
        success_records=1,
        error_records=0,
        summary_message="OUT-SCOPE-JOB-GUARD",
        created_by="system@test.local",
    )
    return {
        "business_unit": business_unit,
        "markers": (
            "BU-RPT-OUT",
            "Reports Out Scope Employee",
            "PRJ-RPT-OUT-GUARD",
            "GCC-RPT-OUT-GUARD",
            "OUT-SCOPE-PROJECT-LINE-GUARD",
            "OUT-SCOPE-GCC-LINE-GUARD",
            "OUT-SCOPE-ARCHIVED-GUARD",
            "out_scope_report_guard",
            "OUT-SCOPE-AUDIT-GUARD",
            "OUT_SCOPE_JOB_GUARD",
            "OUT-SCOPE-JOB-GUARD",
        ),
    }


@pytest.mark.django_db
def test_reports_hub_is_role_aware() -> None:
    context = _setup_reports_context()

    user_response = context["user_client"].get("/reports/")
    pm_response = context["pm_client"].get("/reports/")
    admin_response = context["admin_client"].get("/reports/")

    pm_content = pm_response.content.decode()
    admin_content = admin_response.content.decode()
    admin_card_titles = [card["title"] for card in admin_response.context["report_cards"]]

    assert user_response.status_code == 403
    assert "Access Denied" in user_response.content.decode()
    assert "Missing Timesheets by Project" in pm_content
    assert (
        "Missing Timesheets by Project"
        in context["owner_client"].get("/reports/").content.decode()
    )
    assert "Pending Approvals" in pm_content
    assert "Project Time Report" in pm_content
    assert "Open Report" not in pm_content
    assert '<a href="/reports/project-time/">Project Time Report' in pm_content
    assert '<span class="report-card-count">-> ' in pm_content
    assert "Entry point for the reports currently supported by the live backend" not in pm_content
    assert "Missing Timesheets by Project" in admin_content
    assert "Audit History" in admin_content
    assert "Integration Jobs" in admin_content
    assert "Employee Utilization" in admin_content
    assert "Office / BU Time Summary" in admin_content
    assert "General Charge Code (GCC) Usage" in admin_content
    assert "Approval Turnaround" in admin_content
    assert admin_card_titles[-3:] == [
        "Archived Timesheets",
        "Audit History",
        "Integration Jobs",
    ]


@pytest.mark.django_db
def test_user_can_open_only_own_timesheet_history_report() -> None:
    context = _setup_reports_context()

    history_response = context["user_client"].get(
        "/reports/my-timesheet-history/",
        data={
            "status": "SUBMITTED",
            "week_start_from": context["week_start"].isoformat(),
        },
        follow=False,
    )
    project_time_response = context["user_client"].get("/reports/project-time/")

    assert history_response.status_code == 302
    assert (
        history_response.headers["Location"]
        == f"/ts/?status=SUBMITTED&week_start_from={context['week_start'].isoformat()}"
    )
    assert project_time_response.status_code == 403
    assert "Access Denied" in project_time_response.content.decode()


@pytest.mark.django_db
def test_project_owner_project_time_report_is_scoped() -> None:
    context = _setup_reports_context()

    response = context["owner_client"].get("/reports/project-time/")

    content = response.content.decode()
    assert response.status_code == 200
    assert "Project Time Report" in content
    assert 'class="report-panel-stack"' in content
    assert '<label for="work_date_from">From</label>' in content
    assert '<label for="work_date_to">To</label>' in content
    assert "Weekly Summary Grid" not in content
    assert "Expand a BU / Project summary row to reveal grouped weeks" in content
    assert "data-project-time-grouped-table" in content
    assert 'data-project-time-toggle="project-time-group-1"' in content
    assert 'data-project-time-row-id="project-time-group-1"' in content
    assert 'data-project-time-row-id="project-time-group-1-week-1"' in content
    assert 'data-project-time-parent="project-time-group-1"' in content
    assert 'data-project-time-parent="project-time-group-1-week-1"' in content
    assert "Show" not in content
    assert "Hide" not in content
    assert "Projects Returned" in content
    assert "Detail Lines" in content
    assert "12.00" in content
    assert "<th>Project Code</th>" in content
    assert "<th>Week Start</th>" in content
    assert "<th>Employee Code</th>" in content
    assert "<th>Work Date</th>" in content
    assert "PRJ-RPT" in content
    assert "2026-05-04" in content
    assert "2026-04-27" in content
    assert "Reports User" in content
    assert "5.00" in content
    assert "Billable delivery" in content
    assert "Admin support" not in content


@pytest.mark.django_db
def test_project_manager_pending_approvals_report_is_available() -> None:
    context = _setup_reports_context()

    response = context["pm_client"].get("/reports/pending-approvals/")

    content = response.content.decode()
    assert response.status_code == 200
    assert "Pending Approvals" in content
    assert 'class="report-panel-stack"' in content
    assert "<th>Week Start Date</th>" in content
    assert "<th>Approval Item</th>" not in content
    assert "<th>Status</th>" not in content
    assert context["week_start"].isoformat() in content
    assert "PRJ-RPT" in content
    assert "EMP-RPT-USER" in content


@pytest.mark.django_db
def test_office_bu_time_summary_splits_rows_by_project() -> None:
    context = _setup_reports_context()
    project = context["project"]
    user = Employee.objects.get(email="reports-user@example.com")
    second_project = create_project(
        business_unit=project.business_unit,
        project_code="PRJ-RPT-2",
        name="Reports Project Two",
        project_owner_employee=project.project_owner_employee,
        project_manager_employee=project.project_manager_employee,
        client=project.client,
        internal_category=project.internal_category,
        cost_center=project.cost_center,
        pricing_model=project.pricing_model,
        start_date=project.start_date,
        billable_flag=False,
    )
    assign_project(
        project=second_project,
        employee=user,
        assignment_start_date=context["week_start"] + timedelta(days=7),
    )

    create_response = context["user_client"].post(
        "/ts/",
        data={"week_start_date": (context["week_start"] + timedelta(days=7)).isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302
    save_response = context["user_client"].post(
        create_response.headers["Location"],
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": (context["week_start"] + timedelta(days=7)).isoformat(),
            "line_0_hours": "4.00",
            "line_0_project_id": str(second_project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Second project delivery",
        },
        follow=False,
    )
    assert save_response.status_code == 302

    response = context["admin_client"].get("/reports/office-bu-time-summary/")

    content = response.content.decode()
    assert response.status_code == 200
    assert "PRJ-RPT - Reports Project" in content
    assert "PRJ-RPT-2 - Reports Project Two" in content


@pytest.mark.django_db
def test_cross_office_staffing_reports_include_foreign_employee_time() -> None:
    context = _setup_reports_context()
    project = Project.objects.get(project_code="PRJ-RPT")

    foreign_country = create_office(office_name="Reports Worker Office")
    foreign_business_unit = create_business_unit(
        bu_code="BU-RPT-FGN",
        name="Reports Foreign BU",
        office=foreign_country,
    )
    create_business_unit_configuration(
        business_unit=foreign_business_unit,
        approval_mode_code="PROJECT",
    )
    foreign_calendar = create_yearly_calendar(
        business_unit=foreign_business_unit,
        calendar_year=2026,
        calendar_name="Reports Foreign Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=foreign_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    foreign_employee = create_employee(
        employee_code="EMP-RPT-FGN",
        full_name="Reports Foreign Employee",
        email="reports-foreign@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_calendar(employee=foreign_employee, yearly_calendar=foreign_calendar)
    assign_employee_to_business_unit(
        employee=foreign_employee,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=foreign_employee, role_code="USER")
    assign_cross_office_project(
        project=project,
        employee=foreign_employee,
        assignment_start_date=context["week_start"] - timedelta(days=7),
    )
    home_admin = create_employee(
        employee_code="EMP-RPT-FGN-ADM",
        full_name="Reports Foreign Admin",
        email="reports-foreign-admin@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_calendar(employee=home_admin, yearly_calendar=foreign_calendar)
    assign_employee_to_business_unit(
        employee=home_admin,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=home_admin, role_code="USER")
    assign_role(employee=home_admin, role_code="TS_ADMIN")

    foreign_client = Client()
    foreign_admin_client = Client()
    initialize_ui_session(foreign_client, foreign_employee.email)
    initialize_ui_session(foreign_admin_client, home_admin.email)
    create_response = foreign_client.post(
        "/ts/",
        data={"week_start_date": context["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302
    foreign_client.post(
        create_response.headers["Location"],
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": context["week_start"].isoformat(),
            "line_0_hours": "6.00",
            "line_0_project_id": str(project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Foreign worker delivery",
        },
        follow=False,
    )
    foreign_client.post(
        create_response.headers["Location"],
        data={"form_name": "submit", "comment_text": "Cross-country report submission"},
        follow=False,
    )

    owner_response = context["owner_client"].get("/reports/project-time/")
    admin_project_time_response = context["admin_client"].get(
        "/reports/project-time/",
        data={"business_unit_id": str(project.business_unit_id)},
    )
    pm_response = context["pm_client"].get("/reports/pending-approvals/")
    admin_pending_response = context["admin_client"].get("/reports/pending-approvals/")
    admin_turnaround_response = context["admin_client"].get("/reports/approval-turnaround/")
    admin_office_summary_response = context["admin_client"].get(
        "/reports/office-bu-time-summary/"
    )
    foreign_admin_pending_response = foreign_admin_client.get("/reports/pending-approvals/")
    foreign_admin_office_summary_response = foreign_admin_client.get(
        "/reports/office-bu-time-summary/"
    )

    assert owner_response.status_code == 200
    owner_content = owner_response.content.decode()
    assert "EMP-RPT-FGN" in owner_content
    assert "Foreign worker delivery" in owner_content

    assert admin_project_time_response.status_code == 200
    admin_project_time_content = admin_project_time_response.content.decode()
    assert "EMP-RPT-FGN" in admin_project_time_content
    assert "Foreign worker delivery" in admin_project_time_content

    assert pm_response.status_code == 200
    pm_content = pm_response.content.decode()
    assert "EMP-RPT-FGN" in pm_content
    assert "PRJ-RPT" in pm_content

    assert admin_pending_response.status_code == 200
    admin_pending_content = admin_pending_response.content.decode()
    assert "EMP-RPT-FGN" in admin_pending_content
    assert "PRJ-RPT" in admin_pending_content
    assert "BU-RPT" in admin_pending_content
    assert "BU-RPT-FGN" not in admin_pending_content

    assert admin_turnaround_response.status_code == 200
    admin_turnaround_content = admin_turnaround_response.content.decode()
    assert "EMP-RPT-FGN" in admin_turnaround_content
    assert "PRJ-RPT" in admin_turnaround_content
    assert "BU-RPT" in admin_turnaround_content
    assert "BU-RPT-FGN" not in admin_turnaround_content

    assert admin_office_summary_response.status_code == 200
    admin_office_summary_content = admin_office_summary_response.content.decode()
    assert "Office / BU Time Summary" in admin_office_summary_content
    assert "Reports BU" in admin_office_summary_content
    assert "PRJ-RPT - Reports Project" in admin_office_summary_content
    assert "18.00" in admin_office_summary_content

    assert foreign_admin_pending_response.status_code == 200
    foreign_admin_pending_content = foreign_admin_pending_response.content.decode()
    assert "EMP-RPT-FGN" not in foreign_admin_pending_content
    assert "PRJ-RPT" not in foreign_admin_pending_content

    assert foreign_admin_office_summary_response.status_code == 200
    foreign_admin_office_summary_content = (
        foreign_admin_office_summary_response.content.decode()
    )
    assert "Office / BU Time Summary" in foreign_admin_office_summary_content
    assert "Reports BU" in foreign_admin_office_summary_content
    assert "Reports Foreign BU" not in foreign_admin_office_summary_content
    assert "PRJ-RPT - Reports Project" in foreign_admin_office_summary_content
    assert "6.00" in foreign_admin_office_summary_content


@pytest.mark.django_db
def test_office_bu_time_summary_filter_keeps_cross_office_origin_and_target_visibility() -> None:
    context = _setup_reports_context()
    project = Project.objects.get(project_code="PRJ-RPT")

    foreign_office = create_office(office_name="Reports Filter Worker Office")
    foreign_business_unit = create_business_unit(
        bu_code="BU-RPT-FLT-FGN",
        name="Reports Filter Foreign BU",
        office=foreign_office,
    )
    create_business_unit_configuration(
        business_unit=foreign_business_unit,
        approval_mode_code="PROJECT",
    )
    foreign_calendar = create_yearly_calendar(
        business_unit=foreign_business_unit,
        calendar_year=2026,
        calendar_name="Reports Filter Foreign Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=foreign_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    foreign_employee = create_employee(
        employee_code="EMP-RPT-FLT-FGN",
        full_name="Reports Filter Foreign Employee",
        email="reports-filter-foreign@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_calendar(employee=foreign_employee, yearly_calendar=foreign_calendar)
    assign_employee_to_business_unit(
        employee=foreign_employee,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=foreign_employee, role_code="USER")
    assign_cross_office_project(
        project=project,
        employee=foreign_employee,
        assignment_start_date=context["week_start"],
    )
    foreign_admin = create_employee(
        employee_code="EMP-RPT-FLT-ADM",
        full_name="Reports Filter Foreign Admin",
        email="reports-filter-foreign-admin@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_calendar(employee=foreign_admin, yearly_calendar=foreign_calendar)
    assign_employee_to_business_unit(
        employee=foreign_admin,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=foreign_admin, role_code="USER")
    assign_role(employee=foreign_admin, role_code="TS_ADMIN")

    foreign_client = Client()
    initialize_ui_session(foreign_client, foreign_employee.email)
    create_response = foreign_client.post(
        "/ts/",
        data={"week_start_date": context["week_start"].isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302
    foreign_client.post(
        create_response.headers["Location"],
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": context["week_start"].isoformat(),
            "line_0_hours": "6.00",
            "line_0_project_id": str(project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Filtered cross-office delivery",
        },
        follow=False,
    )

    foreign_admin_client = Client()
    initialize_ui_session(foreign_admin_client, foreign_admin.email)
    target_response = context["admin_client"].get(
        "/reports/office-bu-time-summary/",
        data={"business_unit_id": str(project.business_unit_id)},
    )
    origin_response = foreign_admin_client.get(
        "/reports/office-bu-time-summary/",
        data={"business_unit_id": str(foreign_business_unit.id)},
    )

    assert target_response.status_code == 200
    target_content = target_response.content.decode()
    assert "PRJ-RPT - Reports Project" in target_content
    assert "18.00" in target_content

    assert origin_response.status_code == 200
    origin_content = origin_response.content.decode()
    assert "PRJ-RPT - Reports Project" in origin_content
    assert "6.00" in origin_content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "report_path",
    [
        "/reports/employee-utilization/",
        "/reports/office-bu-time-summary/",
        "/reports/general-charge-code-usage/",
        "/reports/approval-turnaround/",
        "/reports/archived-timesheets/",
        "/reports/audit-history/",
        "/reports/integration-jobs/",
    ],
)
def test_ts_admin_report_business_unit_filter_cannot_widen_scope(report_path: str) -> None:
    context = _setup_reports_context()
    out_of_scope = _create_out_of_scope_report_data(context)

    response = context["admin_client"].get(
        report_path,
        data={"business_unit_id": str(out_of_scope["business_unit"].id)},
    )

    content = response.content.decode()
    assert response.status_code == 200
    for marker in out_of_scope["markers"]:
        assert marker not in content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "report_path",
    [
        "/reports/project-time/",
        "/reports/pending-approvals/",
        "/reports/employee-utilization/",
        "/reports/office-bu-time-summary/",
        "/reports/general-charge-code-usage/",
        "/reports/approval-turnaround/",
        "/reports/archived-timesheets/",
        "/reports/audit-history/",
        "/reports/integration-jobs/",
    ],
)
def test_ts_admin_report_invalid_business_unit_filter_returns_empty_scope(
    report_path: str,
) -> None:
    context = _setup_reports_context()

    response = context["admin_client"].get(
        report_path,
        data={"business_unit_id": "not-a-business-unit"},
    )

    assert response.status_code == 200
    assert response.context["table_rows"] == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "report_path",
    [
        "/reports/project-time/export/",
        "/reports/pending-approvals/export/",
        "/reports/employee-utilization/export/",
        "/reports/office-bu-time-summary/export/",
        "/reports/general-charge-code-usage/export/",
        "/reports/approval-turnaround/export/",
        "/reports/archived-timesheets/export/",
        "/reports/audit-history/export/",
        "/reports/integration-jobs/export/",
    ],
)
def test_ts_admin_report_csv_business_unit_filter_cannot_widen_scope(
    report_path: str,
) -> None:
    context = _setup_reports_context()
    out_of_scope = _create_out_of_scope_report_data(context)

    response = context["admin_client"].get(
        report_path,
        data={"business_unit_id": str(out_of_scope["business_unit"].id)},
    )

    content = response.content.decode()
    assert response.status_code == 200
    for marker in out_of_scope["markers"]:
        assert marker not in content


@pytest.mark.django_db
def test_missing_timesheets_report_includes_cross_office_staffed_employee() -> None:
    context = _setup_reports_context()
    project = Project.objects.get(project_code="PRJ-RPT")
    foreign_office = create_office(office_name="Reports Missing Foreign Office")
    foreign_business_unit = create_business_unit(
        bu_code="BU-RPT-MISS-FGN",
        name="Reports Missing Foreign BU",
        office=foreign_office,
    )
    create_business_unit_configuration(
        business_unit=foreign_business_unit,
        approval_mode_code="PROJECT",
    )
    foreign_calendar = create_yearly_calendar(
        business_unit=foreign_business_unit,
        calendar_year=2026,
        calendar_name="Reports Missing Foreign Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=foreign_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    foreign_employee = create_employee(
        employee_code="EMP-RPT-MISS-FGN",
        full_name="Reports Missing Foreign Employee",
        email="reports-missing-foreign@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_calendar(employee=foreign_employee, yearly_calendar=foreign_calendar)
    assign_employee_to_business_unit(
        employee=foreign_employee,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=foreign_employee, role_code="USER")
    Employee.objects.filter(id=foreign_employee.id).update(
        created_at=datetime(2026, 5, 4, tzinfo=UTC)
    )
    assign_cross_office_project(
        project=project,
        employee=foreign_employee,
        assignment_start_date=context["week_start"],
    )

    response = context["owner_client"].get(
        "/reports/missing-timesheets/",
        data={"project_ids": [str(project.id)]},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Reports Missing Foreign Employee" in content
    assert "reports-missing-foreign@example.com" in content
    assert context["week_start"].isoformat() in content


@pytest.mark.django_db
def test_ts_admin_can_open_admin_reports() -> None:
    context = _setup_reports_context()

    missing_response = context["admin_client"].get("/reports/missing-timesheets/")
    archived_response = context["admin_client"].get("/reports/archived-timesheets/")
    audit_response = context["admin_client"].get("/reports/audit-history/")
    integration_response = context["admin_client"].get("/reports/integration-jobs/")
    utilization_response = context["admin_client"].get(
        "/reports/employee-utilization/",
        data={"employee_id": str(Employee.objects.get(employee_code="EMP-RPT-USER").id)},
    )
    office_summary_response = context["admin_client"].get("/reports/office-bu-time-summary/")
    gcc_response = context["admin_client"].get(
        "/reports/general-charge-code-usage/",
        data={"general_charge_code_id": str(context["general_charge_code_id"])},
    )
    turnaround_response = context["admin_client"].get("/reports/approval-turnaround/")

    assert missing_response.status_code == 200
    missing_content = missing_response.content.decode()
    assert 'class="report-panel-stack"' in missing_content
    assert context["missing_employee_name"] in missing_content
    assert context["missing_employee_email"] in missing_content
    assert archived_response.status_code == 200
    archived_content = archived_response.content.decode()
    assert "Archived Timesheets" in archived_content
    assert 'class="report-panel-stack"' in archived_content
    assert audit_response.status_code == 200
    audit_content = audit_response.content.decode()
    assert 'class="report-panel-stack"' in audit_content
    assert "Nightly export validation" in audit_content
    assert '<label for="entity_name">Entity</label>' in audit_content
    assert '<label for="event_from">From</label>' in audit_content
    assert '<label for="event_to">To</label>' in audit_content
    assert "<th>Business Unit</th>" in audit_content
    assert integration_response.status_code == 200
    integration_content = integration_response.content.decode()
    assert 'class="report-panel-stack"' in integration_content
    assert "EMPLOYEE_IMPORT" in integration_content
    assert utilization_response.status_code == 200
    utilization_content = utilization_response.content.decode()
    assert "Employee Utilization" in utilization_content
    assert 'class="report-panel-stack"' in utilization_content
    assert 'class="report-filter-grid"' in utilization_content
    assert "Back to Reports Hub" in utilization_content
    assert "EMP-RPT-USER" in utilization_content
    assert "56.00" in utilization_content
    assert "16.00" in utilization_content
    assert "28.57%" in utilization_content
    assert office_summary_response.status_code == 200
    office_summary_content = office_summary_response.content.decode()
    assert "Office / BU Time Summary" in office_summary_content
    assert 'class="report-panel-stack"' in office_summary_content
    assert 'class="report-filter-grid"' in office_summary_content
    assert "Reports BU" in office_summary_content
    assert "PRJ-RPT - Reports Project" in office_summary_content
    assert "12.00" in office_summary_content
    assert gcc_response.status_code == 200
    gcc_content = gcc_response.content.decode()
    assert "General Charge Code (GCC) Usage" in gcc_content
    assert 'class="report-panel-stack"' in gcc_content
    assert 'class="report-filter-grid report-filter-grid-dense"' in gcc_content
    assert '<label for="general_charge_code_id">GCC</label>' in gcc_content
    assert '<label for="work_date_from">From</label>' in gcc_content
    assert '<label for="work_date_to">To</label>' in gcc_content
    assert "<th>Business Unit</th>" in gcc_content
    assert "GCC-RPT" in gcc_content
    assert "4.00" in gcc_content
    assert turnaround_response.status_code == 200
    turnaround_content = turnaround_response.content.decode()
    assert "Approval Turnaround" in turnaround_content
    assert 'class="report-panel-stack"' in turnaround_content
    assert 'class="report-filter-grid"' in turnaround_content
    assert "APPROVED" in turnaround_content
    assert "PENDING" in turnaround_content
    assert "27.00" in turnaround_content


@pytest.mark.django_db
def test_dense_admin_report_filters_render_bu_label_when_multiple_bus_exist() -> None:
    context = _setup_reports_context()
    ts_admin = Employee.objects.get(email="reports-admin@example.com")
    extra_business_unit = create_business_unit(
        bu_code="BU-RPT-2",
        name="Reports BU Two",
    )
    assign_employee_to_business_unit(
        employee=ts_admin,
        business_unit=extra_business_unit,
        is_primary_flag=False,
    )
    initialize_ui_session(context["admin_client"], ts_admin.email)

    gcc_response = context["admin_client"].get("/reports/general-charge-code-usage/")
    audit_response = context["admin_client"].get("/reports/audit-history/")

    assert gcc_response.status_code == 200
    gcc_content = gcc_response.content.decode()
    assert '<label for="business_unit_id">BU</label>' in gcc_content
    assert 'class="report-filter-grid report-filter-grid-dense"' in gcc_content

    assert audit_response.status_code == 200
    audit_content = audit_response.content.decode()
    assert '<label for="business_unit_id">BU</label>' in audit_content
    assert 'class="report-filter-grid report-filter-grid-dense"' in audit_content


@pytest.mark.django_db
def test_project_manager_cannot_open_ts_admin_only_advanced_reports() -> None:
    context = _setup_reports_context()

    for path in (
        "/reports/employee-utilization/",
        "/reports/office-bu-time-summary/",
        "/reports/general-charge-code-usage/",
        "/reports/approval-turnaround/",
    ):
        response = context["pm_client"].get(path)
        assert response.status_code == 403
        assert "Access Denied" in response.content.decode()


@pytest.mark.django_db
def test_ts_admin_advanced_report_csv_exports_download_and_audit() -> None:
    context = _setup_reports_context()

    utilization_response = context["admin_client"].get(
        "/reports/employee-utilization/export/",
        data={"employee_id": str(Employee.objects.get(employee_code="EMP-RPT-USER").id)},
    )
    office_summary_response = context["admin_client"].get("/reports/office-bu-time-summary/export/")
    gcc_response = context["admin_client"].get(
        "/reports/general-charge-code-usage/export/",
        data={"general_charge_code_id": str(context["general_charge_code_id"])},
    )
    turnaround_response = context["admin_client"].get("/reports/approval-turnaround/export/")

    assert utilization_response.status_code == 200
    assert utilization_response["Content-Type"].startswith("text/csv")
    assert (
        "Office,BU,Employee Code,Employee,Expected Hours,Worked Hours"
        in utilization_response.content.decode()
    )
    assert "EMP-RPT-USER" in utilization_response.content.decode()
    assert AuditLog.objects.filter(
        entity_name="employee_utilization_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()

    assert office_summary_response.status_code == 200
    assert (
        "Office,BU Name,Project,Employees,Timesheets,Lines,Total Hours"
        in office_summary_response.content.decode()
    )
    assert "PRJ-RPT - Reports Project" in office_summary_response.content.decode()
    assert AuditLog.objects.filter(
        entity_name="office_bu_time_summary_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()

    assert gcc_response.status_code == 200
    assert (
        "Office,Business Unit,GCC Code,GCC Name,Employees,Lines,Total Hours"
        in gcc_response.content.decode()
    )
    assert "GCC-RPT" in gcc_response.content.decode()
    assert AuditLog.objects.filter(
        entity_name="general_charge_code_usage_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()

    assert turnaround_response.status_code == 200
    assert (
        "Approval Item,BU,Employee Code,Employee,Target Code,Target,Approver"
        in turnaround_response.content.decode()
    )
    assert "APPROVED" in turnaround_response.content.decode()
    assert AuditLog.objects.filter(
        entity_name="approval_turnaround_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_project_missing_timesheets_report_uses_project_multiselect_and_audits_generation() -> None:
    context = _setup_reports_context()

    response = context["owner_client"].get(
        "/reports/missing-timesheets/",
        data={"project_ids": [str(context["project"].id)]},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Missing Timesheets by Project" in content
    assert 'name="project_ids"' in content
    assert "multiple" in content
    assert "Export CSV" in content
    assert context["project"].name in content
    assert context["missing_employee_name"] in content
    assert context["missing_employee_email"] in content
    assert context["week_start"].isoformat() in content
    assert "2026-05-11" in content
    assert AuditLog.objects.filter(
        entity_name="project_missing_timesheets_report",
        action_type__value_code="CREATE",
        actor_email="reports-owner@example.com",
    ).exists()


@pytest.mark.django_db
def test_project_missing_timesheets_csv_export_downloads_attachment_and_audits() -> None:
    context = _setup_reports_context()

    response = context["pm_client"].get(
        "/reports/missing-timesheets/export/",
        data={"project_ids": [str(context["project"].id)]},
    )

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment; filename=")
    assert response["Content-Type"].startswith("text/csv")
    content = response.content.decode()
    assert "Project Name,Employee Name,Employee Email,Missing TS Week Start" in content
    assert (
        "Reports Project,Reports Missing Employee,reports-missing@example.com,"
        "2026-05-04" in content
    )
    assert AuditLog.objects.filter(
        entity_name="project_missing_timesheets_report",
        action_type__value_code="EXPORT",
        actor_email="reports-pm@example.com",
    ).exists()


@pytest.mark.django_db
def test_project_time_report_csv_export_downloads_filtered_rows_and_audits() -> None:
    context = _setup_reports_context()

    response = context["owner_client"].get(
        "/reports/project-time/export/",
        data={"project_id": str(context["project"].id)},
    )

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment; filename=")
    assert response["Content-Type"].startswith("text/csv")
    content = response.content.decode()
    assert (
        "BU,Project Code,Project,Week Start,Employee Code,Employee,Work Date,Hours,"
        "Billable,Approval State,Comment" in content
    )
    assert (
        "BU-RPT,PRJ-RPT,Reports Project,2026-05-04,EMP-RPT-USER,Reports User,"
        "2026-05-04,5.00,Billable,PENDING,Billable delivery"
        in content
    )
    assert "BU-RPT,PRJ-RPT,Reports Project,,,,,12.00,12.00,," not in content
    assert AuditLog.objects.filter(
        entity_name="project_time_report",
        action_type__value_code="EXPORT",
        actor_email="reports-owner@example.com",
    ).exists()


@pytest.mark.django_db
def test_pending_approvals_report_csv_export_downloads_rows_and_audits() -> None:
    context = _setup_reports_context()

    response = context["pm_client"].get(
        "/reports/pending-approvals/export/",
        data={"project_id": str(context["project"].id)},
    )

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment; filename=")
    assert response["Content-Type"].startswith("text/csv")
    content = response.content.decode()
    assert (
        "Week Start Date,Employee Code,Employee,Target Code,Target,BU,Submission No."
        in content
    )
    assert "Approval Item" not in content
    assert "Status" not in content
    assert "EMP-RPT-USER" in content
    assert "PRJ-RPT" in content
    assert AuditLog.objects.filter(
        entity_name="pending_approvals_report",
        action_type__value_code="EXPORT",
        actor_email="reports-pm@example.com",
    ).exists()


@pytest.mark.django_db
def test_admin_report_csv_exports_download_and_audit() -> None:
    context = _setup_reports_context()
    timesheet = WeeklyTimesheet.objects.get(
        employee__email="reports-user@example.com",
        week_start_date=context["week_start"],
    )
    WeeklyTimesheet.objects.filter(id=timesheet.id).update(
        status=ref_value("TIMESHEET_STATUS", "ARCHIVED"),
        archive_eligible_date=date(2026, 5, 31),
    )

    archived_response = context["admin_client"].get("/reports/archived-timesheets/export/")
    audit_response = context["admin_client"].get(
        "/reports/audit-history/export/",
        data={"entity_name": "weekly_timesheet"},
    )
    integration_response = context["admin_client"].get(
        "/reports/integration-jobs/export/",
        data={"interface_code": "EMPLOYEE"},
    )

    assert archived_response.status_code == 200
    assert (
        "BU,Employee Code,Employee,Week Start,Week End,Status,Archive Eligible Date"
        in archived_response.content.decode()
    )
    assert (
        "BU-RPT,EMP-RPT-USER,Reports User,2026-05-04,2026-05-10,ARCHIVED,2026-05-31"
        in archived_response.content.decode()
    )
    assert audit_response.status_code == 200
    assert (
        "Event Timestamp,Business Unit,Actor,Action,Entity,Entity ID,Reason"
        in audit_response.content.decode()
    )
    assert "Nightly export validation" in audit_response.content.decode()
    assert integration_response.status_code == 200
    assert (
        "Created At,BU,Interface,Direction,Status,Total,Success,Errors,Requested By,Summary"
        in integration_response.content.decode()
    )
    assert "EMPLOYEE_IMPORT" in integration_response.content.decode()
    assert AuditLog.objects.filter(
        entity_name="archived_timesheets_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()
    assert AuditLog.objects.filter(
        entity_name="audit_history_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()
    assert AuditLog.objects.filter(
        entity_name="integration_jobs_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_project_missing_timesheets_export_api_returns_uri_and_downloads_csv() -> None:
    context = _setup_reports_context()

    create_response = context["admin_client"].post(
        "/api/v1/reports/missing-timesheets/exports/",
        data=f'{{"project_ids": [{context["project"].id}]}}',
        content_type="application/json",
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["report"]["code"] == "missing-timesheets"
    assert payload["report"]["row_count"] >= 1
    assert "project_ids=" in payload["export_uri"]

    download_response = context["admin_client"].get(payload["export_uri"])

    assert download_response.status_code == 200
    assert download_response["Content-Disposition"].startswith("attachment; filename=")
    csv_content = download_response.content.decode()
    assert (
        "Reports Project,Reports Missing Employee,reports-missing@example.com,"
        "2026-05-04"
        in csv_content
    )
    assert AuditLog.objects.filter(
        entity_name="project_missing_timesheets_report",
        action_type__value_code="CREATE",
        actor_email="reports-admin@example.com",
        reason_text__icontains="export URI",
    ).exists()
    assert AuditLog.objects.filter(
        entity_name="project_missing_timesheets_report",
        action_type__value_code="EXPORT",
        actor_email="reports-admin@example.com",
    ).exists()


@pytest.mark.django_db
def test_regular_user_cannot_create_project_missing_timesheets_export_api() -> None:
    context = _setup_reports_context()

    response = context["user_client"].post(
        "/api/v1/reports/missing-timesheets/exports/",
        data=f'{{"project_ids": [{context["project"].id}]}}',
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_ACCESS_DENIED"
