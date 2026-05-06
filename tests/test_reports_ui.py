from datetime import date, timedelta

import pytest
from django.test import Client

from apps.audit.services import write_audit_event
from apps.integrations.models import IntegrationJob
from apps.master_data.models import Project
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
    create_country,
    create_employee,
    create_general_charge_code,
    create_internal_category,
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
    }


@pytest.mark.django_db
def test_reports_hub_is_role_aware() -> None:
    context = _setup_reports_context()

    user_response = context["user_client"].get("/reports/")
    pm_response = context["pm_client"].get("/reports/")
    admin_response = context["admin_client"].get("/reports/")

    user_content = user_response.content.decode()
    pm_content = pm_response.content.decode()
    admin_content = admin_response.content.decode()

    assert "My Timesheet History" in user_content
    assert "Project Time Report" not in user_content
    assert "Pending Approvals" in pm_content
    assert "Project Time Report" in pm_content
    assert "Missing Timesheets" in admin_content
    assert "Audit History" in admin_content
    assert "Integration Jobs" in admin_content


@pytest.mark.django_db
def test_user_can_open_only_own_timesheet_history_report() -> None:
    context = _setup_reports_context()

    history_response = context["user_client"].get("/reports/my-timesheet-history/")
    project_time_response = context["user_client"].get("/reports/project-time/")

    history_content = history_response.content.decode()
    assert history_response.status_code == 200
    assert "My Timesheet History" in history_content
    assert context["week_start"].isoformat() in history_content
    assert project_time_response.status_code == 403
    assert "Access Denied" in project_time_response.content.decode()


@pytest.mark.django_db
def test_project_owner_project_time_report_is_scoped() -> None:
    context = _setup_reports_context()

    response = context["owner_client"].get("/reports/project-time/")

    content = response.content.decode()
    assert response.status_code == 200
    assert "Project Time Report" in content
    assert "PRJ-RPT" in content
    assert "Billable delivery" in content
    assert "Admin support" not in content


@pytest.mark.django_db
def test_project_manager_pending_approvals_report_is_available() -> None:
    context = _setup_reports_context()

    response = context["pm_client"].get("/reports/pending-approvals/")

    content = response.content.decode()
    assert response.status_code == 200
    assert "Pending Approvals" in content
    assert "PRJ-RPT" in content
    assert "EMP-RPT-USER" in content


@pytest.mark.django_db
def test_cross_country_project_reports_include_foreign_employee_time() -> None:
    context = _setup_reports_context()
    project = Project.objects.get(project_code="PRJ-RPT")

    foreign_country = create_country(country_name="Reports Worker Country")
    foreign_business_unit = create_business_unit(
        bu_code="BU-RPT-FGN",
        name="Reports Foreign BU",
        country=foreign_country,
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
    assign_project(
        project=project,
        employee=foreign_employee,
        assignment_start_date=context["week_start"] - timedelta(days=7),
    )

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
    pm_response = context["pm_client"].get("/reports/pending-approvals/")

    assert owner_response.status_code == 200
    owner_content = owner_response.content.decode()
    assert "EMP-RPT-FGN" in owner_content
    assert "Foreign worker delivery" in owner_content

    assert pm_response.status_code == 200
    pm_content = pm_response.content.decode()
    assert "EMP-RPT-FGN" in pm_content
    assert "PRJ-RPT" in pm_content


@pytest.mark.django_db
def test_ts_admin_can_open_admin_reports() -> None:
    context = _setup_reports_context()

    missing_response = context["admin_client"].get(
        "/reports/missing-timesheets/",
        data={"week_start_date": context["week_start"].isoformat()},
    )
    audit_response = context["admin_client"].get("/reports/audit-history/")
    integration_response = context["admin_client"].get("/reports/integration-jobs/")

    assert missing_response.status_code == 200
    assert "Reports Project Owner" in missing_response.content.decode()
    assert audit_response.status_code == 200
    assert "Nightly export validation" in audit_response.content.decode()
    assert integration_response.status_code == 200
    assert "EMPLOYEE_IMPORT" in integration_response.content.decode()
