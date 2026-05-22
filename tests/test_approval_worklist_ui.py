from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.timesheets.models import ApprovalAction, ApprovalItem, WeeklyTimesheet
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
    seed_reference_data,
)


def _build_approval_ui_clients(
    *,
    employee_email: str = "approval-user@example.com",
    employee_code: str = "EMP-APR-001",
) -> dict:
    seed_reference_data()
    week_start = date(2026, 5, 4)
    suffix = employee_code.replace("EMP-", "").replace("-", "")
    business_unit = create_business_unit(bu_code=f"BU-{suffix}", name="Approval BU")
    create_business_unit_configuration(
        business_unit=business_unit,
        approval_mode_code="PROJECT",
    )
    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Approval Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )

    employee = create_employee(
        employee_code=employee_code,
        full_name="Approval Employee",
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
        full_name="Approval Project Owner",
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
        full_name="Approval Project Manager",
        email=f"pm-{employee_email}",
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
        name="Approval Client",
    )
    internal_category = create_internal_category(
        business_unit=business_unit,
        category_code=f"IC-{suffix}",
        name="Approval Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code=f"CC-{suffix}",
        name="Approval Cost Center",
    )
    project = create_project(
        business_unit=business_unit,
        project_code=f"PRJ-{suffix}",
        name="Approval Project",
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
        employee=employee,
        assignment_start_date=week_start - timedelta(days=7),
    )
    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code=f"GCC-{suffix}",
        name="Approval General Code",
        valid_from=week_start - timedelta(days=7),
    )

    employee_client = Client()
    pm_client = Client()
    initialize_ui_session(employee_client, employee.email)
    initialize_ui_session(pm_client, project_manager.email)

    create_response = employee_client.post(
        "/ts/",
        data={"week_start_date": week_start.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    lines_response = employee_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": week_start.isoformat(),
            "line_0_hours": "6.00",
            "line_0_project_id": str(project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Project delivery work",
            "line_1_work_date": (week_start + timedelta(days=1)).isoformat(),
            "line_1_hours": "2.00",
            "line_1_project_id": "",
            "line_1_general_charge_code_id": str(general_charge_code.id),
            "line_1_comment_text": "General admin support",
        },
        follow=False,
    )
    assert lines_response.status_code == 302

    submit_response = employee_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "submit",
            "comment_text": "Please review the project delivery line",
        },
        follow=False,
    )
    assert submit_response.status_code == 302

    approval_item = ApprovalItem.objects.get(
        approver_employee_id=project_manager.id,
        submission_cycle__weekly_timesheet=timesheet,
    )

    return {
        "week_start": week_start,
        "employee_client": employee_client,
        "pm_client": pm_client,
        "employee": employee,
        "business_unit": business_unit,
        "calendar": calendar,
        "project_manager": project_manager,
        "project": project,
        "timesheet": timesheet,
        "approval_item": approval_item,
    }


def _build_ts_admin_client(*, business_unit, calendar, suffix: str) -> Client:
    admin = create_employee(
        employee_code=f"EMP-ADMIN-{suffix}",
        full_name="Approval Admin",
        email=f"approval-admin-{suffix.lower()}@example.com",
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


def _build_general_charge_code_approval_ui_clients() -> dict:
    seed_reference_data()
    week_start = date(2026, 5, 18)
    business_unit = create_business_unit(bu_code="BU-GCC-APR", name="GCC Approval BU")
    create_business_unit_configuration(
        business_unit=business_unit,
        approval_mode_code="PROJECT",
    )
    calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="GCC Approval Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )

    employee = create_employee(
        employee_code="EMP-GCC-APR",
        full_name="GCC Approval Employee",
        email="gcc-approval-employee@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=employee, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    approver = create_employee(
        employee_code="EMP-GCC-PM",
        full_name="GCC Approval Manager",
        email="gcc-approval-manager@example.com",
        primary_business_unit=business_unit,
    )
    assign_calendar(employee=approver, yearly_calendar=calendar)
    assign_employee_to_business_unit(
        employee=approver,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=approver, role_code="USER")
    assign_role(employee=approver, role_code="PROJECT_MANAGER")

    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-APPROVAL",
        name="Approval General Code",
        valid_from=week_start - timedelta(days=7),
        requires_approval_flag=True,
        approver_role_codes=["PROJECT_MANAGER"],
    )

    employee_client = Client()
    approver_client = Client()
    initialize_ui_session(employee_client, employee.email)
    initialize_ui_session(approver_client, approver.email)

    create_response = employee_client.post(
        "/ts/",
        data={"week_start_date": week_start.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302

    timesheet = WeeklyTimesheet.objects.get(employee=employee)
    lines_response = employee_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": week_start.isoformat(),
            "line_0_hours": "8.00",
            "line_0_project_id": "",
            "line_0_general_charge_code_id": str(general_charge_code.id),
            "line_0_comment_text": "Sickness time",
        },
        follow=False,
    )
    assert lines_response.status_code == 302

    submit_response = employee_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "submit",
            "comment_text": "Please review the general charge code line",
        },
        follow=False,
    )
    assert submit_response.status_code == 302

    approval_item = ApprovalItem.objects.get(
        general_charge_code_id=general_charge_code.id,
        submission_cycle__weekly_timesheet=timesheet,
    )

    return {
        "approver_client": approver_client,
        "approval_item": approval_item,
        "timesheet": timesheet,
        "general_charge_code": general_charge_code,
    }


def _build_cross_office_approval_ui_context() -> dict:
    seed_reference_data()
    week_start = date(2026, 5, 4)
    target_office = create_office(office_name="Approval Target Office")
    origin_office = create_office(office_name="Approval Origin Office")
    target_business_unit = create_business_unit(
        bu_code="BU-APR-TGT",
        name="Approval Target BU",
        office=target_office,
    )
    origin_business_unit = create_business_unit(
        bu_code="BU-APR-ORG",
        name="Approval Origin BU",
        office=origin_office,
    )
    create_business_unit_configuration(
        business_unit=origin_business_unit,
        approval_mode_code="PROJECT",
    )
    origin_calendar = create_yearly_calendar(
        business_unit=origin_business_unit,
        calendar_year=2026,
        calendar_name="Approval Origin Calendar",
    )
    create_calendar_period_rule(
        yearly_calendar=origin_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )

    worker = create_employee(
        employee_code="EMP-APR-CO-WORKER",
        full_name="Approval Cross Office Worker",
        email="approval-cross-office-worker@example.com",
        primary_business_unit=origin_business_unit,
    )
    assign_calendar(employee=worker, yearly_calendar=origin_calendar)
    assign_employee_to_business_unit(
        employee=worker,
        business_unit=origin_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=worker, role_code="USER")

    project_owner = create_employee(
        employee_code="EMP-APR-CO-OWNER",
        full_name="Approval Cross Office Owner",
        email="approval-cross-office-owner@example.com",
        primary_business_unit=target_business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=target_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")

    project_manager = create_employee(
        employee_code="EMP-APR-CO-PM",
        full_name="Approval Cross Office PM",
        email="approval-cross-office-pm@example.com",
        primary_business_unit=target_business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=target_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="USER")
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    target_admin = create_employee(
        employee_code="EMP-APR-CO-TADM",
        full_name="Approval Target Admin",
        email="approval-target-admin@example.com",
        primary_business_unit=target_business_unit,
    )
    assign_employee_to_business_unit(
        employee=target_admin,
        business_unit=target_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=target_admin, role_code="USER")
    assign_role(employee=target_admin, role_code="TS_ADMIN")

    origin_admin = create_employee(
        employee_code="EMP-APR-CO-OADM",
        full_name="Approval Origin Admin",
        email="approval-origin-admin@example.com",
        primary_business_unit=origin_business_unit,
    )
    assign_calendar(employee=origin_admin, yearly_calendar=origin_calendar)
    assign_employee_to_business_unit(
        employee=origin_admin,
        business_unit=origin_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=origin_admin, role_code="USER")
    assign_role(employee=origin_admin, role_code="TS_ADMIN")

    client_record = create_client(
        business_unit=target_business_unit,
        client_code="CLI-APR-CO",
        name="Approval Cross Office Client",
    )
    internal_category = create_internal_category(
        business_unit=target_business_unit,
        category_code="IC-APR-CO",
        name="Approval Cross Office Category",
    )
    cost_center = create_cost_center(
        business_unit=target_business_unit,
        cost_center_code="CC-APR-CO",
        name="Approval Cross Office Cost Center",
    )
    project = create_project(
        business_unit=target_business_unit,
        project_code="PRJ-APR-CO",
        name="Approval Cross Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=week_start - timedelta(days=7),
        billable_flag=True,
    )
    assign_cross_office_project(
        project=project,
        employee=worker,
        assignment_start_date=week_start - timedelta(days=7),
    )

    worker_client = Client()
    target_admin_client = Client()
    origin_admin_client = Client()
    initialize_ui_session(worker_client, worker.email)
    initialize_ui_session(target_admin_client, target_admin.email)
    initialize_ui_session(origin_admin_client, origin_admin.email)

    create_response = worker_client.post(
        "/ts/",
        data={"week_start_date": week_start.isoformat()},
        follow=False,
    )
    assert create_response.status_code == 302
    timesheet = WeeklyTimesheet.objects.get(employee=worker, week_start_date=week_start)
    lines_response = worker_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "lines",
            "row_count": "8",
            "line_0_work_date": week_start.isoformat(),
            "line_0_hours": "6.00",
            "line_0_project_id": str(project.id),
            "line_0_general_charge_code_id": "",
            "line_0_comment_text": "Cross-office approval delivery work",
        },
        follow=False,
    )
    assert lines_response.status_code == 302
    submit_response = worker_client.post(
        f"/ts/timesheets/{timesheet.id}/",
        data={
            "form_name": "submit",
            "comment_text": "Please review the cross-office project line",
        },
        follow=False,
    )
    assert submit_response.status_code == 302

    approval_item = ApprovalItem.objects.get(
        approver_employee_id=project_manager.id,
        submission_cycle__weekly_timesheet=timesheet,
    )
    return {
        "target_admin_client": target_admin_client,
        "origin_admin_client": origin_admin_client,
        "approval_item": approval_item,
    }


@pytest.mark.django_db
def test_project_manager_worklist_shows_pending_approval_item() -> None:
    context = _build_approval_ui_clients()

    response = context["pm_client"].get("/approvals/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Approval Worklist" in content
    assert "Pending Approval Items" in content
    assert "Completed Decisions" not in content
    assert "Last actions" in content
    assert "Approval Employee" in content
    assert context["project"].project_code in content
    assert f"/approvals/{context['approval_item'].id}/" in content


@pytest.mark.django_db
def test_ts_admin_oversight_shows_scoped_pending_items_and_stalled_filters() -> None:
    context = _build_approval_ui_clients(
        employee_email="admin-oversight@example.com",
        employee_code="EMP-APR-ADMIN",
    )
    admin_client = _build_ts_admin_client(
        business_unit=context["business_unit"],
        calendar=context["calendar"],
        suffix="APR-ADMIN",
    )
    WeeklyTimesheet.objects.filter(id=context["timesheet"].id).update(
        submission_datetime=timezone.now() - timedelta(days=8)
    )

    response = admin_client.get(
        "/approvals/",
        data={"aging": "STALLED", "q": "Approval", "project_id": str(context["project"].id)},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Approval Oversight" in content
    assert "Oversight Filters" in content
    assert "Stalled" in content
    assert "Approval Employee" in content
    assert "Approver" in content
    assert context["business_unit"].bu_code in content
    assert f"/approvals/{context['approval_item'].id}/" in content


@pytest.mark.django_db
def test_ts_admin_can_open_approval_detail_in_read_only_oversight_mode() -> None:
    context = _build_approval_ui_clients(
        employee_email="admin-detail@example.com",
        employee_code="EMP-APR-DETAIL",
    )
    admin_client = _build_ts_admin_client(
        business_unit=context["business_unit"],
        calendar=context["calendar"],
        suffix="APR-DETAIL",
    )

    response = admin_client.get(
        f"/approvals/{context['approval_item'].id}/",
        data={"back": "/approvals/"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Open Related Timesheet" in content
    assert f"/system/projects/{context['project'].id}/" in content
    assert context["project_manager"].full_name in content
    assert "read-only for admin oversight" in content
    assert "Approve Item" not in content
    assert "Reject Item" not in content


@pytest.mark.django_db
def test_target_office_ts_admin_oversight_sees_cross_office_project_item() -> None:
    context = _build_cross_office_approval_ui_context()

    worklist_response = context["target_admin_client"].get("/approvals/")
    detail_response = context["target_admin_client"].get(
        f"/approvals/{context['approval_item'].id}/"
    )

    assert worklist_response.status_code == 200
    worklist_content = worklist_response.content.decode()
    assert "Approval Oversight" in worklist_content
    assert "EMP-APR-CO-WORKER" in worklist_content
    assert "PRJ-APR-CO" in worklist_content

    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert "Approval Cross Office Project" in detail_content
    assert "Cross-office approval delivery work" in detail_content


@pytest.mark.django_db
def test_origin_office_ts_admin_oversight_does_not_see_cross_office_project_item() -> None:
    context = _build_cross_office_approval_ui_context()

    worklist_response = context["origin_admin_client"].get("/approvals/")
    detail_response = context["origin_admin_client"].get(
        f"/approvals/{context['approval_item'].id}/"
    )

    assert worklist_response.status_code == 200
    worklist_content = worklist_response.content.decode()
    assert "EMP-APR-CO-WORKER" not in worklist_content
    assert "PRJ-APR-CO" not in worklist_content
    assert detail_response.status_code == 403


@pytest.mark.django_db
def test_project_manager_can_approve_item_from_detail_ui() -> None:
    context = _build_approval_ui_clients(
        employee_email="approve-ui@example.com",
        employee_code="EMP-APR-APPROVE",
    )

    detail_response = context["pm_client"].get(f"/approvals/{context['approval_item'].id}/")

    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert "Project delivery work" in detail_content
    assert "General admin support" not in detail_content

    approve_response = context["pm_client"].post(
        f"/approvals/{context['approval_item'].id}/",
        data={
            "form_name": "approve",
            "comment_text": "Looks good to me",
        },
        follow=False,
    )

    assert approve_response.status_code == 302
    context["approval_item"].refresh_from_db()
    context["timesheet"].refresh_from_db()
    assert context["approval_item"].status.value_code == "APPROVED"
    assert context["timesheet"].status.value_code == "APPROVED"
    assert context["timesheet"].final_approval_datetime is not None
    assert ApprovalAction.objects.get(approval_item=context["approval_item"]).comment_text == (
        "Looks good to me"
    )


@pytest.mark.django_db
def test_matching_role_user_can_approve_general_charge_code_item_from_ui() -> None:
    context = _build_general_charge_code_approval_ui_clients()

    worklist_response = context["approver_client"].get("/approvals/")

    assert worklist_response.status_code == 200
    worklist_content = worklist_response.content.decode()
    assert context["general_charge_code"].code in worklist_content

    approve_response = context["approver_client"].post(
        f"/approvals/{context['approval_item'].id}/",
        data={
            "form_name": "approve",
            "comment_text": "Approved GCC line",
        },
        follow=False,
    )

    assert approve_response.status_code == 302
    context["approval_item"].refresh_from_db()
    context["timesheet"].refresh_from_db()
    assert context["approval_item"].status.value_code == "APPROVED"
    assert context["timesheet"].status.value_code == "APPROVED"


@pytest.mark.django_db
def test_project_manager_reject_flow_requires_reason_and_updates_timesheet() -> None:
    context = _build_approval_ui_clients(
        employee_email="reject-ui@example.com",
        employee_code="EMP-APR-REJECT",
    )

    invalid_response = context["pm_client"].post(
        f"/approvals/{context['approval_item'].id}/",
        data={
            "form_name": "reject",
            "reason_text": "",
        },
        follow=False,
    )

    assert invalid_response.status_code == 200
    assert "A rejection reason is required." in invalid_response.content.decode()
    context["approval_item"].refresh_from_db()
    assert context["approval_item"].status.value_code == "PENDING"

    reject_response = context["pm_client"].post(
        f"/approvals/{context['approval_item'].id}/",
        data={
            "form_name": "reject",
            "reason_text": "Please split the hours by day",
        },
        follow=False,
    )

    assert reject_response.status_code == 302
    context["approval_item"].refresh_from_db()
    context["timesheet"].refresh_from_db()
    assert context["approval_item"].status.value_code == "REJECTED"
    assert context["approval_item"].rejection_reason == "Please split the hours by day"
    assert context["timesheet"].status.value_code == "REJECTED"

    confirmed_response = context["pm_client"].get(f"/approvals/{context['approval_item'].id}/")
    assert "Please split the hours by day" in confirmed_response.content.decode()


@pytest.mark.django_db
def test_project_manager_cannot_open_another_managers_approval_item() -> None:
    first_context = _build_approval_ui_clients(
        employee_email="first-pm-ui@example.com",
        employee_code="EMP-APR-FIRST",
    )
    second_context = _build_approval_ui_clients(
        employee_email="second-pm-ui@example.com",
        employee_code="EMP-APR-SECOND",
    )

    response = second_context["pm_client"].get(f"/approvals/{first_context['approval_item'].id}/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()
