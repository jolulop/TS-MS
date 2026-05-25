import re
from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    Country,
    CrossOfficeProjectAssignment,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    GeneralChargeCodeApprovalRole,
    Office,
    OfficeConfiguration,
    Project,
    ProjectAssignment,
    YearlyCalendar,
)
from apps.master_data.models import (
    Client as ClientRecord,
)
from apps.master_data.models import (
    CostCenter as CostCenterRecord,
)
from apps.master_data.models import (
    GeneralChargeCode as GeneralChargeCodeRecord,
)
from apps.master_data.models import (
    InternalCategory as InternalCategoryRecord,
)
from apps.master_data.models import (
    PricingModel as PricingModelRecord,
)
from apps.timesheets.models import TimesheetLine, WeeklyTimesheet
from tests.helpers import (
    assign_calendar,
    assign_cross_office_project,
    assign_employee_to_business_unit,
    assign_general_charge_code_approval_role,
    assign_project,
    assign_role,
    create_business_unit,
    create_business_unit_configuration,
    create_calendar_period_rule,
    create_calendar_special_day,
    create_client,
    create_cost_center,
    create_country,
    create_employee,
    create_general_charge_code,
    create_general_charge_code_approval_role,
    create_internal_category,
    create_office,
    create_pricing_model,
    create_project,
    create_yearly_calendar,
    get_office,
    initialize_ui_session,
    ref_value,
    seed_reference_data,
)


def _build_ts_admin_client() -> tuple[Client, Employee, list]:
    seed_reference_data()
    primary_business_unit = create_business_unit(bu_code="BU-SYS-1", name="System BU 1")
    secondary_business_unit = create_business_unit(bu_code="BU-SYS-2", name="System BU 2")
    employee = create_employee(
        employee_code="EMP-SYS-ADMIN",
        full_name="System Admin",
        email="system-admin@example.com",
        primary_business_unit=primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=primary_business_unit,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=secondary_business_unit,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="TS_ADMIN")

    client = Client()
    initialize_ui_session(client, employee.email)
    return client, employee, [primary_business_unit, secondary_business_unit]


def _build_ts_admin_master_client() -> tuple[Client, Employee, list]:
    seed_reference_data()
    primary_business_unit = create_business_unit(bu_code="BU-MASTER-1", name="Master BU 1")
    employee = create_employee(
        employee_code="EMP-SYS-MASTER",
        full_name="System Master Admin",
        email="system-master-admin@example.com",
        primary_business_unit=primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="TS_ADMIN_MASTER")

    client = Client()
    initialize_ui_session(client, employee.email)
    return client, employee, [primary_business_unit]


def _build_project_owner_client(
    *,
    include_project_manager_role: bool = False,
) -> tuple[Client, Employee, list]:
    seed_reference_data()
    primary_business_unit = create_business_unit(bu_code="BU-OWNER-1", name="Owner BU 1")
    secondary_business_unit = create_business_unit(bu_code="BU-OWNER-2", name="Owner BU 2")
    employee = create_employee(
        employee_code="EMP-SYS-OWNER",
        full_name="Scoped Project Owner",
        email="scoped-project-owner@example.com",
        primary_business_unit=primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=primary_business_unit,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=secondary_business_unit,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="PROJECT_OWNER")
    if include_project_manager_role:
        assign_role(employee=employee, role_code="PROJECT_MANAGER")

    client = Client()
    initialize_ui_session(client, employee.email)
    return client, employee, [primary_business_unit, secondary_business_unit]


def _build_project_manager_client() -> tuple[Client, Employee, list]:
    seed_reference_data()
    primary_business_unit = create_business_unit(bu_code="BU-MGR-1", name="Manager BU 1")
    secondary_business_unit = create_business_unit(bu_code="BU-MGR-2", name="Manager BU 2")
    employee = create_employee(
        employee_code="EMP-SYS-MANAGER",
        full_name="Scoped Project Manager",
        email="scoped-project-manager@example.com",
        primary_business_unit=primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=primary_business_unit,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=secondary_business_unit,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="PROJECT_MANAGER")

    client = Client()
    initialize_ui_session(client, employee.email)
    return client, employee, [primary_business_unit, secondary_business_unit]


def _build_project_management_context(
    business_unit,
) -> tuple[
    Employee,
    Employee,
    ClientRecord,
    InternalCategoryRecord,
    CostCenterRecord,
    PricingModelRecord,
]:
    project_owner = create_employee(
        employee_code="EMP-PO-1",
        full_name="Project Owner",
        email="project-owner@example.com",
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
        employee_code="EMP-PM-1",
        full_name="Project Manager",
        email="project-manager@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="USER")
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")

    client = create_client(
        business_unit=business_unit,
        client_code="CLI-PROJ",
        name="Project Client",
    )
    category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT-PROJ",
        name="Project Category",
    )
    cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-PROJ",
        name="Project Cost Center",
    )
    pricing_model = create_pricing_model(
        business_unit=business_unit,
        name="Time and Materials",
        description="Project pricing model for management UI tests.",
    )
    return project_owner, project_manager, client, category, cost_center, pricing_model


@pytest.mark.django_db
def test_ts_admin_master_can_transfer_employee_to_another_office_via_ui() -> None:
    client, _, _ = _build_ts_admin_master_client()
    source_office = create_office(office_name="Source Office")
    target_office = create_office(office_name="Target Office")
    source_bu = create_business_unit(
        bu_code="SRC-BU",
        name="Source BU",
        office=source_office,
    )
    target_primary_bu = create_business_unit(
        bu_code="TGT-BU-1",
        name="Target Primary BU",
        office=target_office,
    )
    target_secondary_bu = create_business_unit(
        bu_code="TGT-BU-2",
        name="Target Secondary BU",
        office=target_office,
    )
    source_employee = create_employee(
        employee_code="EMP-SOURCE-1",
        full_name="Source Employee",
        email="source.employee@example.com",
        primary_business_unit=source_bu,
    )
    assign_employee_to_business_unit(
        employee=source_employee,
        business_unit=source_bu,
        is_primary_flag=True,
    )
    assign_role(employee=source_employee, role_code="USER")

    load_response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "select_source",
            "source_employee_id": str(source_employee.id),
        },
    )

    assert load_response.status_code == 200
    assert "Transfer Readiness" in load_response.content.decode()
    assert "READY" in load_response.content.decode()

    transfer_response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "transfer",
            "source_employee_id": str(source_employee.id),
            "new_employee_code": "EMP-TARGET-1",
            "target_office_id": str(target_office.id),
            "target_primary_business_unit_id": str(target_primary_bu.id),
            "target_business_unit_ids": [str(target_secondary_bu.id)],
            "target_role_codes": ["USER"],
        },
    )

    assert transfer_response.status_code == 200
    content = transfer_response.content.decode()
    assert "Source Employee Archived" in content
    assert "Target Employee Created" in content

    source_employee.refresh_from_db()
    assert source_employee.status.value_code == "INACTIVE"
    assert source_employee.email == f"source.employee+archived-{source_employee.id}@example.com"
    assert source_employee.canonical_email == source_employee.email
    assert not EmployeeRole.objects.filter(
        employee=source_employee,
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    ).exists()
    assert not EmployeeBusinessUnit.objects.filter(
        employee=source_employee,
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    ).exists()

    target_employee = Employee.objects.get(employee_code="EMP-TARGET-1")
    assert target_employee.full_name == "Source Employee"
    assert target_employee.email == "source.employee@example.com"
    assert target_employee.office_id == target_office.id
    assert target_employee.primary_business_unit_id == target_primary_bu.id
    assert EmployeeBusinessUnit.objects.filter(
        employee=target_employee,
        business_unit=target_primary_bu,
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    ).exists()
    assert EmployeeBusinessUnit.objects.filter(
        employee=target_employee,
        business_unit=target_secondary_bu,
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    ).exists()
    assert EmployeeRole.objects.filter(
        employee=target_employee,
        role__value_code="USER",
        status__value_code="ACTIVE",
        valid_to__isnull=True,
    ).exists()
    assert AuditLog.objects.filter(
        entity_name="employee_transfer",
        entity_id=target_employee.id,
        action_type__value_code="CREATE",
    ).exists()


@pytest.mark.django_db
def test_employee_transfer_source_filters_limit_visible_candidates() -> None:
    client, _, _ = _build_ts_admin_master_client()
    alpha_office = create_office(office_name="Alpha Office")
    beta_office = create_office(office_name="Beta Office")
    alpha_bu = create_business_unit(
        bu_code="ALPHA-BU",
        name="Alpha BU",
        office=alpha_office,
    )
    beta_bu = create_business_unit(
        bu_code="BETA-BU",
        name="Beta BU",
        office=beta_office,
    )
    alpha_employee = create_employee(
        employee_code="EMP-ALPHA-1",
        full_name="Alice Alpha",
        email="alice.alpha@example.com",
        primary_business_unit=alpha_bu,
    )
    beta_employee = create_employee(
        employee_code="EMP-BETA-1",
        full_name="Bob Beta",
        email="bob.beta@example.com",
        primary_business_unit=beta_bu,
    )
    assign_employee_to_business_unit(
        employee=alpha_employee,
        business_unit=alpha_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=beta_employee,
        business_unit=beta_bu,
        is_primary_flag=True,
    )
    assign_role(employee=alpha_employee, role_code="USER")
    assign_role(employee=beta_employee, role_code="USER")

    response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "select_source",
            "filter_office_id": str(alpha_office.id),
            "filter_primary_business_unit_id": str(alpha_bu.id),
            "filter_full_name": "alice",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'name="filter_office_id"' in content
    assert 'name="filter_primary_business_unit_id"' in content
    assert 'name="filter_full_name"' in content
    assert "Apply Filters" in content
    assert "Alice Alpha" in content
    assert "Bob Beta" not in content


@pytest.mark.django_db
def test_employee_transfer_apply_filters_button_uses_filter_action() -> None:
    client, _, _ = _build_ts_admin_master_client()
    alpha_office = create_office(office_name="Filter Alpha Office")
    beta_office = create_office(office_name="Filter Beta Office")
    alpha_bu = create_business_unit(
        bu_code="FILTER-ALPHA-BU",
        name="Filter Alpha BU",
        office=alpha_office,
    )
    beta_bu = create_business_unit(
        bu_code="FILTER-BETA-BU",
        name="Filter Beta BU",
        office=beta_office,
    )
    alpha_employee = create_employee(
        employee_code="EMP-FILTER-ALPHA",
        full_name="Alpha Filter Employee",
        email="alpha.filter@example.com",
        primary_business_unit=alpha_bu,
    )
    beta_employee = create_employee(
        employee_code="EMP-FILTER-BETA",
        full_name="Beta Filter Employee",
        email="beta.filter@example.com",
        primary_business_unit=beta_bu,
    )
    assign_employee_to_business_unit(
        employee=alpha_employee,
        business_unit=alpha_bu,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=beta_employee,
        business_unit=beta_bu,
        is_primary_flag=True,
    )
    assign_role(employee=alpha_employee, role_code="USER")
    assign_role(employee=beta_employee, role_code="USER")

    response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "select_source",
            "form_action": "apply_filters",
            "filter_office_id": str(alpha_office.id),
            "filter_full_name": "alpha",
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Alpha Filter Employee" in content
    assert "Beta Filter Employee" not in content


@pytest.mark.django_db
def test_employee_transfer_ui_blocks_source_employee_with_active_direct_reports() -> None:
    client, _, _ = _build_ts_admin_master_client()
    source_office = create_office(office_name="Blocked Source Office")
    target_office = create_office(office_name="Blocked Target Office")
    source_bu = create_business_unit(
        bu_code="SRC-BLOCK",
        name="Blocked Source BU",
        office=source_office,
    )
    target_bu = create_business_unit(
        bu_code="TGT-BLOCK",
        name="Blocked Target BU",
        office=target_office,
    )
    source_employee = create_employee(
        employee_code="EMP-BLOCK-1",
        full_name="Blocked Source Employee",
        email="blocked.source@example.com",
        primary_business_unit=source_bu,
    )
    assign_employee_to_business_unit(
        employee=source_employee,
        business_unit=source_bu,
        is_primary_flag=True,
    )
    assign_role(employee=source_employee, role_code="USER")
    direct_report = create_employee(
        employee_code="EMP-BLOCK-DR",
        full_name="Direct Report",
        email="direct.report@example.com",
        primary_business_unit=source_bu,
    )
    assign_employee_to_business_unit(
        employee=direct_report,
        business_unit=source_bu,
        is_primary_flag=True,
    )
    assign_role(employee=direct_report, role_code="USER")
    direct_report.manager_employee = source_employee
    direct_report.updated_by = "test"
    direct_report.save(update_fields=["manager_employee", "updated_by", "updated_at"])

    load_response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "select_source",
            "source_employee_id": str(source_employee.id),
        },
    )

    assert load_response.status_code == 200
    content = load_response.content.decode()
    assert "Transfer Readiness" in content
    assert "BLOCKED" in content
    assert "Active Direct Reports" in content
    assert "Target Setup" not in content

    transfer_response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "transfer",
            "source_employee_id": str(source_employee.id),
            "new_employee_code": "EMP-BLOCK-TARGET",
            "target_office_id": str(target_office.id),
            "target_primary_business_unit_id": str(target_bu.id),
            "target_role_codes": ["USER"],
        },
    )

    assert transfer_response.status_code == 200
    assert "Employee transfer is blocked" in transfer_response.content.decode()
    source_employee.refresh_from_db()
    assert source_employee.status.value_code == "ACTIVE"
    assert not Employee.objects.filter(employee_code="EMP-BLOCK-TARGET").exists()


@pytest.mark.django_db
def test_ts_admin_is_denied_employee_transfer_screen() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/employee-transfers/new/")

    assert response.status_code == 403
    assert "You do not have permission to open this Office Management screen." in (
        response.content.decode()
    )


@pytest.mark.django_db
def test_system_management_hub_shows_real_admin_screen_links() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ready now" not in content
    assert "Open Screen" not in content
    assert '<a href="/system/business-units/">Business Units</a>' in content
    assert '<a href="/system/employees/">Employees</a>' in content
    assert "/system/business-units/" in content
    assert "/system/employees/" in content
    assert "/system/clients/" in content
    assert "/system/calendars/" in content
    assert "/system/pricing-models/" in content
    assert "/system/general-charge-codes/" in content
    assert "/system/projects/" in content
    assert "/system/project-assignments/" in content
    assert "/system/cross-office-staffing/" in content
    assert "/system/calendar-period-rules/" in content
    card_hrefs = {card["href"] for card in response.context["section_cards"]}
    assert "/system/pricing-models/" in card_hrefs
    assert "/system/calendar-period-rules/" in card_hrefs
    assert [card["title"] for card in response.context["section_cards"]] == [
        "Employees",
        "Clients",
        "Projects",
        "Project Assignments",
        "Cross-Office Staffing",
        "Internal Categories",
        "Cost Centers",
        "Pricing Models",
        "Business Units",
        "Calendars",
        "Calendar Period Rules",
        "GCC Approval Roles",
        "General Charge Codes",
    ]


@pytest.mark.django_db
def test_system_management_section_links_follow_requested_order() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/employees/")

    assert response.status_code == 200
    assert [link["label"] for link in response.context["system_section_links"]] == [
        "Overview",
        "Employees",
        "Clients",
        "Projects",
        "Project Assignments",
        "Cross-Office Staffing",
        "Internal Categories",
        "Cost Centers",
        "Pricing Models",
        "Business Units",
        "Calendars",
        "Calendar Period Rules",
        "GCC Approval Roles",
        "General Charge Codes",
    ]


@pytest.mark.django_db
def test_system_management_hub_shows_country_and_office_links_for_master_admin() -> None:
    client, _, _ = _build_ts_admin_master_client()

    response = client.get("/system/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ready now" not in content
    assert "Open Screen" not in content
    assert '<a href="/system/countries/">Countries</a>' in content
    assert '<a href="/system/offices/">Offices</a>' in content
    assert '<a href="/system/employee-transfers/new/">Employee Transfers</a>' in content
    assert "Countries" in content
    assert "Offices" in content
    assert "Employee Transfers" in content
    card_hrefs = {card["href"] for card in response.context["section_cards"]}
    assert "/system/countries/" in card_hrefs
    assert "/system/offices/" in card_hrefs
    assert "/system/employee-transfers/new/" in card_hrefs


@pytest.mark.django_db
def test_non_admin_cannot_open_employee_management_screen() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-NON-1", name="Non Admin BU")
    employee = create_employee(
        employee_code="EMP-NON-1",
        full_name="Regular User",
        email="regular-user@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")

    client = Client()
    initialize_ui_session(client, employee.email)

    response = client.get("/system/employees/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()


@pytest.mark.django_db
def test_business_unit_management_list_and_detail_render_and_update_through_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_business_unit = business_units[0]
    create_business_unit_configuration(business_unit=managed_business_unit)

    list_response = client.get("/system/business-units/")

    assert list_response.status_code == 200
    list_content = list_response.content.decode()
    assert "Business Unit Management" in list_content
    assert managed_business_unit.bu_code in list_content
    assert "Create Business Unit" in list_content

    general_response = client.post(
        f"/system/business-units/{managed_business_unit.id}/",
        data={
            "form_name": "general",
            "bu_code": "BU-SYS-1-UPD",
            "name": "System BU 1 Updated",
            "description": "Updated description",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert general_response.status_code == 302
    managed_business_unit.refresh_from_db()
    assert managed_business_unit.bu_code == "BU-SYS-1-UPD"
    assert managed_business_unit.name == "System BU 1 Updated"
    assert managed_business_unit.description == "Updated description"
    assert managed_business_unit.status.value_code == "INACTIVE"

    detail_response = client.get(f"/system/business-units/{managed_business_unit.id}/")
    detail_content = detail_response.content.decode()
    assert detail_response.status_code == 200
    assert "Inherited Configuration" in detail_content
    assert "Back to Business Units" in detail_content
    assert "System BU 1 Updated" in detail_content
    assert "parent Office and are shown here for reference only" in detail_content
    assert "Only project-based approval is available." in detail_content
    assert detail_content.index('name="archive_after_years"') < detail_content.index(
        'name="timesheet_cutoff_date"'
    )
    assert detail_content.index('name="timesheet_cutoff_date"') < detail_content.index(
        'name="count_non_billable_in_daily_limit_flag"'
    )
    assert "Reserved switch. Set to always count all charged time" in detail_content
    assert (
        "Reserved switch for future integration that imports leave/absence data "
        "into timesheet for this Office"
    ) in detail_content


@pytest.mark.django_db
def test_business_unit_management_can_create_new_business_unit_through_html() -> None:
    client, employee, business_units = _build_ts_admin_client()

    response = client.post(
        "/system/business-units/",
        data={
            "bu_code": "BU-SYS-NEW",
            "name": "System BU New",
            "description": "Created from HTML",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 302
    created_business_unit = BusinessUnit.objects.get(bu_code="BU-SYS-NEW")
    assert response.headers["Location"] == f"/system/business-units/{created_business_unit.id}/"
    assert EmployeeBusinessUnit.objects.filter(
        employee=employee,
        business_unit=created_business_unit,
        valid_to__isnull=True,
    ).exists()
    assert business_units[0].office_id == created_business_unit.office_id


@pytest.mark.django_db
def test_system_management_collections_hide_action_column_but_keep_row_targets() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_business_unit = business_units[0]
    managed_employee = create_employee(
        employee_code="EMP-COLL-1",
        full_name="Collection Employee",
        email="collection-employee@example.com",
        primary_business_unit=managed_business_unit,
    )
    assign_employee_to_business_unit(
        employee=managed_employee,
        business_unit=managed_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=managed_employee, role_code="USER")

    project_owner, project_manager, client_record, category, cost_center, pricing_model = (
        _build_project_management_context(managed_business_unit)
    )
    project = create_project(
        business_unit=managed_business_unit,
        project_code="PRJ-COLL",
        name="Collection Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=client_record,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 1, 5),
    )
    assignment = assign_project(
        project=project,
        employee=managed_employee,
        assignment_start_date=date(2026, 1, 5),
    )
    calendar = create_yearly_calendar(
        business_unit=managed_business_unit,
        calendar_year=2026,
        calendar_name="Collection Calendar",
    )
    period_rule = create_calendar_period_rule(
        yearly_calendar=calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    approval_role = create_general_charge_code_approval_role(
        office=managed_business_unit.office,
        role_code="GCC-COLL",
        name="Collection GCC Role",
    )
    general_charge_code = create_general_charge_code(
        business_unit=managed_business_unit,
        code="GCC-COLL",
        name="Collection General Charge Code",
        valid_from=date(2026, 1, 1),
    )

    pages = [
        ("/system/employees/", f"/system/employees/{managed_employee.id}/"),
        ("/system/clients/", f"/system/clients/{client_record.id}/"),
        ("/system/projects/", f"/system/projects/{project.id}/"),
        ("/system/project-assignments/", f"/system/project-assignments/{assignment.id}/"),
        ("/system/internal-categories/", f"/system/internal-categories/{category.id}/"),
        ("/system/cost-centers/", f"/system/cost-centers/{cost_center.id}/"),
        ("/system/pricing-models/", f"/system/pricing-models/{pricing_model.id}/"),
        ("/system/business-units/", f"/system/business-units/{managed_business_unit.id}/"),
        ("/system/calendars/", f"/system/calendars/{calendar.id}/"),
        (
            "/system/calendar-period-rules/",
            f"/system/calendar-period-rules/{period_rule.id}/",
        ),
        (
            "/system/general-charge-code-approval-roles/",
            f"/system/general-charge-code-approval-roles/{approval_role.id}/",
        ),
        (
            "/system/general-charge-codes/",
            f"/system/general-charge-codes/{general_charge_code.id}/",
        ),
    ]

    for url, detail_url in pages:
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert '<th class="system-action-column" hidden>Action</th>' in content
        assert 'class="system-action-column" hidden><a href="' in content
        assert detail_url in content


@pytest.mark.django_db
def test_ts_admin_cannot_open_country_management_screen() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/countries/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()


@pytest.mark.django_db
def test_employee_management_create_and_update_flows_render_through_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        office=business_units[0].office,
        calendar_year=2026,
        calendar_name="Employee Setup 2026",
    )
    create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        business_unit=business_units[1],
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    managed_employee = create_employee(
        employee_code="EMP-MANAGED-1",
        full_name="Managed Employee",
        email="managed-employee@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=managed_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=managed_employee, role_code="USER")

    create_response = client.post(
        "/system/employees/new/",
        data={
            "employee_code": "EMP-NEW-1",
            "full_name": "New Employee",
            "email": "new-employee@example.com",
            "status_code": "ACTIVE",
            "primary_business_unit_id": str(business_units[0].id),
            "business_unit_ids": [str(business_units[0].id), str(business_units[1].id)],
            "role_codes": ["USER", "PROJECT_MANAGER"],
        },
        follow=False,
    )

    assert create_response.status_code == 302
    created_employee = Employee.objects.get(employee_code="EMP-NEW-1")
    assert created_employee.primary_business_unit_id == business_units[0].id
    assert created_employee.assigned_calendar_id == yearly_calendar.id
    assert CalendarPeriodRule.objects.filter(
        yearly_calendar=yearly_calendar,
        business_unit=business_units[0],
    ).exists()

    core_response = client.post(
        f"/system/employees/{managed_employee.id}/",
        data={
            "form_name": "core",
            "full_name": "Managed Employee Updated",
            "email": "managed-employee-updated@example.com",
            "status_code": "INACTIVE",
        },
        follow=False,
    )
    assert core_response.status_code == 302

    managed_employee.refresh_from_db()
    assert managed_employee.full_name == "Managed Employee Updated"
    assert managed_employee.email == "managed-employee-updated@example.com"
    assert managed_employee.status.value_code == "INACTIVE"

    roles_response = client.post(
        f"/system/employees/{managed_employee.id}/",
        data={
            "form_name": "roles",
            "role_codes": ["USER", "PROJECT_OWNER"],
        },
        follow=False,
    )
    assert roles_response.status_code == 302
    active_roles = sorted(
        assignment.role.value_code
        for assignment in EmployeeRole.objects.select_related(
            "role", "status", "status__domain"
        ).filter(employee=managed_employee, valid_to__isnull=True)
        if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
        and assignment.status.value_code == "ACTIVE"
    )
    assert active_roles == ["PROJECT_OWNER", "USER"]

    business_unit_response = client.post(
        f"/system/employees/{managed_employee.id}/",
        data={
            "form_name": "business_units",
            "primary_business_unit_id": str(business_units[1].id),
            "business_unit_ids": [str(business_units[1].id)],
        },
        follow=False,
    )
    assert business_unit_response.status_code == 302

    managed_employee.refresh_from_db()
    assert managed_employee.primary_business_unit_id == business_units[1].id
    active_business_units = sorted(
        assignment.business_unit.bu_code
        for assignment in EmployeeBusinessUnit.objects.select_related(
            "business_unit",
            "status",
            "status__domain",
        ).filter(employee=managed_employee, valid_to__isnull=True)
        if assignment.status.domain.domain_code == "EMPLOYEE_BU_STATUS"
        and assignment.status.value_code == "ACTIVE"
    )
    assert active_business_units == ["BU-SYS-2"]


@pytest.mark.django_db
def test_employee_management_collection_hides_create_form_until_requested() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/employees/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Current Records" not in content
    assert "Create Employee" in content
    assert 'href="/system/employees/new/"' in content
    assert '<form class="form-stack" method="post" action="">' not in content
    assert 'aria-label="Employee Status"' in content
    assert 'href="/system/employees/?status=ACTIVE"' in content
    assert 'href="/system/employees/?status=ALL"' in content
    assert ">Filters<" not in content


@pytest.mark.django_db
def test_employee_create_form_does_not_preselect_business_unit_scope() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/employees/new/")

    assert response.status_code == 200
    content = response.content.decode()
    match = re.search(
        r'<select\s+id="business_unit_ids"\s+name="business_unit_ids"\s+multiple.*?>(.*?)</select>',
        content,
        re.S,
    )
    assert match is not None
    assert "required" not in match.group(0)
    assert "selected" not in match.group(1)
    assert "Additional Business Units" in content
    assert "The selected primary Business Unit is always included automatically" in content


@pytest.mark.django_db
def test_employee_create_form_is_shown_when_requested() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/employees/new/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Create Employee" in content
    assert '<form class="form-stack" method="post" action="">' in content
    assert "Back to Employees" in content
    assert "Employee Setup" in content
    assert "Current State" not in content
    assert ">Filters<" not in content


@pytest.mark.django_db
def test_employee_create_route_renders_standalone_screen() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/employees/new/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Standalone employee creation screen" in content
    assert "Back to Employees" in content
    assert 'name="form_name" value="create"' in content
    assert "Current State" not in content


@pytest.mark.parametrize(
    ("collection_path", "create_path", "filter_label", "setup_title"),
    [
        (
            "/system/business-units/",
            "/system/business-units/new/",
            "Business Unit Status",
            "Business Unit Setup",
        ),
        ("/system/clients/", "/system/clients/new/", "Client Status", "Client Setup"),
        ("/system/projects/", "/system/projects/new/", "Project Status", "Project Setup"),
        (
            "/system/project-assignments/",
            "/system/project-assignments/new/",
            "Project Assignment Status",
            "Project Assignment Setup",
        ),
        (
            "/system/internal-categories/",
            "/system/internal-categories/new/",
            "Internal Category Status",
            "Internal Category Setup",
        ),
        (
            "/system/cost-centers/",
            "/system/cost-centers/new/",
            "Cost Center Status",
            "Cost Center Setup",
        ),
        ("/system/pricing-models/", "/system/pricing-models/new/", None, "Pricing Model Setup"),
        ("/system/calendars/", "/system/calendars/new/", "Calendar Status", "Calendar Setup"),
        (
            "/system/calendar-period-rules/",
            "/system/calendar-period-rules/new/",
            "Calendar Period Rule Status",
            "Calendar Period Rule Setup",
        ),
        (
            "/system/general-charge-code-approval-roles/",
            "/system/general-charge-code-approval-roles/new/",
            "General Charge Code Approval Role Status",
            "General Charge Code Approval Role Setup",
        ),
        (
            "/system/general-charge-codes/",
            "/system/general-charge-codes/new/",
            "General Charge Code Status",
            "General Charge Code Setup",
        ),
    ],
)
@pytest.mark.django_db
def test_system_management_collection_pages_use_standalone_create_screen_layout(
    collection_path: str,
    create_path: str,
    filter_label: str | None,
    setup_title: str,
) -> None:
    client, _, _ = _build_ts_admin_client()

    collection_response = client.get(collection_path)
    create_response = client.get(create_path)

    assert collection_response.status_code == 200
    collection_content = collection_response.content.decode()
    assert "Current Records" not in collection_content
    assert ">Filters<" not in collection_content
    assert f'href="{create_path}"' in collection_content
    assert '<form class="form-stack" method="post" action="">' not in collection_content
    if filter_label is None:
        assert 'aria-label="' not in collection_content or filter_label is None
    else:
        assert f'aria-label="{filter_label}"' in collection_content

    assert create_response.status_code == 200
    create_content = create_response.content.decode()
    assert "Current State" not in create_content
    assert setup_title in create_content
    assert 'name="form_name" value="create"' in create_content


@pytest.mark.django_db
def test_shared_system_management_detail_screens_use_standalone_edit_layout() -> None:
    client, _, business_units = _build_ts_admin_client()
    business_unit = business_units[0]
    project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_unit)
    )
    managed_client = create_client(
        business_unit=business_unit,
        client_code="CLI-LAYOUT",
        name="Layout Client",
    )
    managed_category = create_internal_category(
        business_unit=business_unit,
        category_code="CAT-LAYOUT",
        name="Layout Category",
    )
    managed_cost_center = create_cost_center(
        business_unit=business_unit,
        cost_center_code="CC-LAYOUT",
        name="Layout Cost Center",
    )
    managed_pricing_model = create_pricing_model(
        business_unit=business_unit,
        name="Layout Pricing Model",
    )
    project = create_project(
        business_unit=business_unit,
        project_code="PRJ-LAYOUT",
        name="Layout Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 1, 1),
    )
    assignee = create_employee(
        employee_code="EMP-ASN-LAYOUT",
        full_name="Layout Assignee",
        email="layout-assignee@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=assignee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=assignee, role_code="USER")
    assignment = ProjectAssignment.objects.create(
        project=project,
        employee=assignee,
        assignment_start_date=date(2026, 1, 1),
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    approval_role = create_general_charge_code_approval_role(
        office=business_unit.office,
        role_code="GCC-LAYOUT",
        name="Layout GCC Role",
    )
    general_charge_code = create_general_charge_code(
        business_unit=business_unit,
        code="GCC-LAYOUT",
        name="Layout General Charge Code",
        cost_center=managed_cost_center,
        valid_from=date(2026, 1, 1),
    )
    yearly_calendar = create_yearly_calendar(
        business_unit=business_unit,
        calendar_year=2026,
        calendar_name="Layout Calendar",
    )
    period_rule = create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        business_unit=business_unit,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )

    cases = [
        (
            f"/system/clients/{managed_client.id}/",
            "Edit Client",
            "Delete Client",
            "Back to Clients",
        ),
        (f"/system/projects/{project.id}/", "Edit Project", "Delete Project", "Back to Projects"),
        (
            f"/system/project-assignments/{assignment.id}/",
            "Edit Project Assignment",
            "Delete Project Assignment",
            "Back to Project Assignments",
        ),
        (
            f"/system/internal-categories/{managed_category.id}/",
            "Edit Internal Category",
            "Delete Internal Category",
            "Back to Internal Categories",
        ),
        (
            f"/system/cost-centers/{managed_cost_center.id}/",
            "Edit Cost Center",
            "Delete Cost Center",
            "Back to Cost Centers",
        ),
        (
            f"/system/pricing-models/{managed_pricing_model.id}/",
            "Edit Pricing Model",
            "Delete Pricing Model",
            "Back to Pricing Models",
        ),
        (
            f"/system/general-charge-code-approval-roles/{approval_role.id}/",
            "Edit General Charge Code Approval Role",
            "Delete General Charge Code Approval Role",
            "Back to General Charge Code Approval Roles",
        ),
        (
            f"/system/general-charge-codes/{general_charge_code.id}/",
            "Edit General Charge Code",
            "Delete General Charge Code",
            "Back to General Charge Codes",
        ),
        (
            f"/system/calendar-period-rules/{period_rule.id}/",
            "Edit Calendar Period Rule",
            "Delete Calendar Period Rule",
            "Back to Calendar Period Rules",
        ),
    ]

    for url, edit_heading, delete_label, back_label in cases:
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Current State" not in content
        assert edit_heading in content
        assert delete_label in content
        assert back_label in content
        assert 'class="detail-action-form"' in content


@pytest.mark.django_db
def test_employee_detail_business_unit_form_explains_primary_scope_is_automatic() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_employee = create_employee(
        employee_code="EMP-MANAGED-SCOPE-1",
        full_name="Managed Scope User",
        email="managed-scope@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=managed_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )

    response = client.get(f"/system/employees/{managed_employee.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Current State" not in content
    assert "employee-detail-layout" in content
    assert "Employee Core Data" in content
    assert "Role Assignments" in content
    assert "Business Unit Scope" in content
    assert "Project Assignments" in content
    assert "Delete Employee" in content
    assert "Delete this employee only if no protected references still depend on it." in content


@pytest.mark.django_db
def test_employee_detail_shows_assigned_projects_section() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_employee = create_employee(
        employee_code="EMP-MANAGED-PROJ-1",
        full_name="Managed Project User",
        email="managed-project@example.com",
        primary_business_unit=business_units[0],
    )
    project_owner = create_employee(
        employee_code="EMP-PROJ-OWNER-DET",
        full_name="Detail Owner",
        email="detail-owner@example.com",
        primary_business_unit=business_units[0],
    )
    project_manager = create_employee(
        employee_code="EMP-PROJ-MANAGER-DET",
        full_name="Detail Manager",
        email="detail-manager@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=managed_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=managed_employee, role_code="USER")
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")
    assign_role(employee=project_manager, role_code="USER")
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")
    project_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-EMP-DETAIL",
        name="Employee Detail Client",
    )
    category = create_internal_category(
        business_unit=business_units[0],
        category_code="CAT-EMP-DETAIL",
        name="Employee Detail Category",
    )
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-EMP-DETAIL",
        name="Employee Detail Cost Center",
    )
    pricing_model = create_pricing_model(
        business_unit=business_units[0],
        name="Employee Detail Pricing",
    )
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-EMP-DETAIL",
        name="Employee Detail Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 1, 1),
    )
    assign_project(
        project=project,
        employee=managed_employee,
        assignment_start_date=date(2026, 2, 1),
    )
    foreign_office = create_office(office_name="Employee Detail Foreign Office")
    foreign_business_unit = create_business_unit(
        bu_code="BU-EMP-DETAIL-FGN",
        name="Employee Detail Foreign BU",
        office=foreign_office,
    )
    foreign_project_owner = create_employee(
        employee_code="EMP-PROJ-OWNER-FGN",
        full_name="Foreign Detail Owner",
        email="foreign-detail-owner@example.com",
        primary_business_unit=foreign_business_unit,
    )
    foreign_project_manager = create_employee(
        employee_code="EMP-PROJ-MANAGER-FGN",
        full_name="Foreign Detail Manager",
        email="foreign-detail-manager@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_employee_to_business_unit(
        employee=foreign_project_owner,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_employee_to_business_unit(
        employee=foreign_project_manager,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=foreign_project_owner, role_code="USER")
    assign_role(employee=foreign_project_owner, role_code="PROJECT_OWNER")
    assign_role(employee=foreign_project_manager, role_code="USER")
    assign_role(employee=foreign_project_manager, role_code="PROJECT_MANAGER")
    foreign_client = create_client(
        business_unit=foreign_business_unit,
        client_code="CLI-EMP-DETAIL-FGN",
        name="Employee Detail Foreign Client",
    )
    foreign_category = create_internal_category(
        business_unit=foreign_business_unit,
        category_code="CAT-EMP-DETAIL-FGN",
        name="Employee Detail Foreign Category",
    )
    foreign_cost_center = create_cost_center(
        business_unit=foreign_business_unit,
        cost_center_code="CC-EMP-DETAIL-FGN",
        name="Employee Detail Foreign Cost Center",
    )
    foreign_pricing_model = create_pricing_model(
        business_unit=foreign_business_unit,
        name="Employee Detail Foreign Pricing",
    )
    foreign_project = create_project(
        business_unit=foreign_business_unit,
        project_code="PRJ-EMP-DETAIL-FGN",
        name="Employee Detail Foreign Project",
        project_owner_employee=foreign_project_owner,
        project_manager_employee=foreign_project_manager,
        client=foreign_client,
        internal_category=foreign_category,
        cost_center=foreign_cost_center,
        pricing_model=foreign_pricing_model,
        start_date=date(2026, 2, 1),
    )
    assign_cross_office_project(
        project=foreign_project,
        employee=managed_employee,
        assignment_start_date=date(2026, 2, 15),
    )
    archived_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-EMP-HIDDEN",
        name="Hidden Inactive Assignment",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 3, 1),
    )
    ProjectAssignment.objects.create(
        project=archived_project,
        employee=managed_employee,
        assignment_start_date=date(2026, 3, 1),
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "INACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    response = client.get(f"/system/employees/{managed_employee.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Project Assignments" in content
    assert "Employee Detail Project" in content
    assert 'href="/system/projects/' in content
    assert f'href="/system/projects/{project.id}/"' in content
    assert ">Employee Detail Project</a>" in content
    assert "[Cross-Office] Employee Detail Foreign Project" in content
    assert f'href="/system/projects/{foreign_project.id}/"' not in content
    assert "PRJ-EMP-HIDDEN" not in content
    assert "Hidden Inactive Assignment" not in content
    primary_match = re.search(
        r'<select\s+id="primary_business_unit_id"\s+name="primary_business_unit_id"\s+size="(\d+)".*?>(.*?)</select>',
        content,
        re.S,
    )
    assert primary_match is not None
    assert "selected" in primary_match.group(2)
    match = re.search(
        r'<select\s+id="business_unit_ids"\s+name="business_unit_ids"\s+multiple.*?>(.*?)</select>',
        content,
        re.S,
    )
    assert match is not None
    assert "required" not in match.group(0)
    assert "selected" not in match.group(1)
    assert "so leaving this empty keeps only the primary Business Unit" in content


@pytest.mark.django_db
def test_project_assignment_collection_shows_client_project_name_and_dependent_filters() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        project_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    second_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-PROJ-B",
        name="Second Project Client",
    )
    create_client(
        business_unit=business_units[0],
        client_code="CLI-PROJ-HIDDEN",
        name="Hidden Project Client",
        active=False,
    )
    assigned_employee = create_employee(
        employee_code="EMP-PA-FILTER",
        full_name="Project Assignment Filter Employee",
        email="project-assignment-filter@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    first_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-PA-FILTER-A",
        name="Project Filter Alpha",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 1, 1),
    )
    second_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-PA-FILTER-B",
        name="Project Filter Beta",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=second_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 1, 1),
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-PA-FILTER-HIDDEN",
        name="Project Filter Hidden",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 1, 1),
        active=False,
    )
    assign_project(
        project=first_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 2, 1),
    )
    assign_project(
        project=second_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 2, 8),
    )

    collection_response = client.get("/system/project-assignments/")
    collection_content = collection_response.content.decode()
    assert collection_response.status_code == 200
    assert "<th>Business Unit</th>" not in collection_content
    assert "<th>Client</th>" in collection_content
    assert "<th>Project Name</th>" in collection_content
    assert "Project Client" in collection_content
    assert "Second Project Client" in collection_content
    assert "Project Filter Alpha" in collection_content
    assert "Project Filter Beta" in collection_content
    assert "Hidden Project Client" not in collection_content
    assert "Project Filter Hidden" not in collection_content

    client_filtered_response = client.get(
        f"/system/project-assignments/?status=ACTIVE&client_id={project_client.id}"
    )
    client_filtered_content = client_filtered_response.content.decode()
    assert client_filtered_response.status_code == 200
    assert "Project Filter Alpha" in client_filtered_content
    assert "Project Filter Beta" not in client_filtered_content
    assert "Project Filter Hidden" not in client_filtered_content
    assert "PRJ-PA-FILTER-A - Project Filter Alpha" in client_filtered_content
    assert "PRJ-PA-FILTER-B - Project Filter Beta" not in client_filtered_content
    assert "PRJ-PA-FILTER-HIDDEN - Project Filter Hidden" not in client_filtered_content
    assert f"?status=ACTIVE&amp;client_id={project_client.id}" in client_filtered_content

    project_filtered_response = client.get(
        f"/system/project-assignments/?status=ACTIVE&client_id={project_client.id}"
        f"&project_id={first_project.id}"
    )
    project_filtered_content = project_filtered_response.content.decode()
    assert project_filtered_response.status_code == 200
    assert "Project Filter Alpha" in project_filtered_content
    assert "Project Filter Beta" not in project_filtered_content
    assert f'value="{first_project.id}" selected' in project_filtered_content

    reset_response = client.get(
        f"/system/project-assignments/?status=ACTIVE&client_id={second_client.id}"
        f"&project_id={first_project.id}"
    )
    reset_content = reset_response.content.decode()
    assert reset_response.status_code == 200
    assert f'value="{first_project.id}" selected' not in reset_content
    assert f'value="{second_project.id}"' in reset_content
    assert "source1.form.submit();" in reset_content


@pytest.mark.django_db
def test_business_unit_detail_uses_standalone_edit_layout() -> None:
    client, admin_employee, _ = _build_ts_admin_client()
    managed_business_unit = create_business_unit(bu_code="BU-LAYOUT", name="Layout BU")
    assign_employee_to_business_unit(employee=admin_employee, business_unit=managed_business_unit)

    response = client.get(f"/system/business-units/{managed_business_unit.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Current State" not in content
    assert "General" in content
    assert "Inherited Configuration" in content
    assert "Delete Business Unit" in content
    assert "Back to Business Units" in content
    assert 'class="detail-action-form"' in content


@pytest.mark.django_db
def test_employee_create_without_scope_selection_uses_only_primary_business_unit() -> None:
    client, _, business_units = _build_ts_admin_client()

    response = client.post(
        "/system/employees/new/",
        data={
            "employee_code": "EMP-NEW-PRIMARY-ONLY",
            "full_name": "Primary Only Employee",
            "email": "primary-only@example.com",
            "status_code": "ACTIVE",
            "primary_business_unit_id": str(business_units[1].id),
            "role_codes": ["USER"],
        },
        follow=False,
    )

    assert response.status_code == 302
    created_employee = Employee.objects.get(employee_code="EMP-NEW-PRIMARY-ONLY")
    active_business_units = sorted(
        assignment.business_unit.bu_code
        for assignment in EmployeeBusinessUnit.objects.select_related(
            "business_unit",
            "status",
            "status__domain",
        ).filter(employee=created_employee, valid_to__isnull=True)
        if assignment.status.domain.domain_code == "EMPLOYEE_BU_STATUS"
        and assignment.status.value_code == "ACTIVE"
    )
    assert created_employee.primary_business_unit_id == business_units[1].id
    assert active_business_units == ["BU-SYS-2"]


@pytest.mark.django_db
def test_employee_management_can_delete_unused_employee_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    create_response = client.post(
        "/system/employees/new/",
        data={
            "employee_code": "EMP-DELETE-1",
            "full_name": "Delete Me",
            "email": "delete-me@example.com",
            "status_code": "ACTIVE",
            "primary_business_unit_id": str(business_units[0].id),
            "business_unit_ids": [str(business_units[0].id)],
            "role_codes": ["USER"],
        },
        follow=False,
    )

    assert create_response.status_code == 302
    employee = Employee.objects.get(employee_code="EMP-DELETE-1")

    response = client.post(
        f"/system/employees/{employee.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/employees/"
    assert not Employee.objects.filter(id=employee.id).exists()
    assert not EmployeeRole.objects.filter(employee_id=employee.id).exists()
    assert not EmployeeBusinessUnit.objects.filter(employee_id=employee.id).exists()
    assert AuditLog.objects.filter(entity_name="employee", entity_id=employee.id).count() == 2


@pytest.mark.django_db
def test_employee_management_delete_is_blocked_when_employee_has_dependents() -> None:
    client, _, business_units = _build_ts_admin_client()
    employee = create_employee(
        employee_code="EMP-BLOCK-DELETE-1",
        full_name="Blocked Delete Employee",
        email="blocked-delete@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    direct_report = create_employee(
        employee_code="EMP-BLOCK-DELETE-2",
        full_name="Direct Report Employee",
        email="direct-report@example.com",
        primary_business_unit=business_units[0],
    )
    direct_report.manager_employee = employee
    direct_report.updated_by = "system@test.local"
    direct_report.save(update_fields=["manager_employee", "updated_by", "updated_at"])

    response = client.post(
        f"/system/employees/{employee.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Employee" in content
    assert "Employee cannot be deleted because it is still referenced" in content
    assert Employee.objects.filter(id=employee.id).exists()


@pytest.mark.django_db
def test_business_unit_management_can_delete_unused_business_unit_via_html() -> None:
    client, employee, _ = _build_ts_admin_client()

    create_response = client.post(
        "/system/business-units/",
        data={
            "bu_code": "BU-DELETE-1",
            "name": "Delete BU",
            "description": "Temporary BU",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    business_unit = BusinessUnit.objects.get(bu_code="BU-DELETE-1")
    assert EmployeeBusinessUnit.objects.filter(
        employee=employee,
        business_unit=business_unit,
        valid_to__isnull=True,
    ).exists()

    response = client.post(
        f"/system/business-units/{business_unit.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/business-units/"
    assert not BusinessUnit.objects.filter(id=business_unit.id).exists()
    assert not EmployeeBusinessUnit.objects.filter(
        employee=employee,
        business_unit_id=business_unit.id,
    ).exists()
    assert not AuditLog.objects.filter(business_unit_id=business_unit.id).exists()
    assert (
        AuditLog.objects.filter(
            entity_name="business_unit",
            entity_id=business_unit.id,
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_business_unit_management_delete_is_blocked_when_business_unit_has_employees() -> None:
    client, admin_employee, business_units = _build_ts_admin_client()
    target_business_unit = create_business_unit(
        bu_code="BU-BLOCK-DELETE",
        name="Blocked Delete BU",
        office=business_units[0].office,
    )
    assign_employee_to_business_unit(
        employee=admin_employee,
        business_unit=target_business_unit,
        is_primary_flag=False,
    )
    employee = create_employee(
        employee_code="EMP-BU-BLOCK-1",
        full_name="BU Block Employee",
        email="bu-block@example.com",
        primary_business_unit=target_business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=target_business_unit,
        is_primary_flag=True,
    )

    response = client.post(
        f"/system/business-units/{target_business_unit.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Business Unit" in content
    assert "Business Unit cannot be deleted because it is still referenced" in content
    assert BusinessUnit.objects.filter(id=target_business_unit.id).exists()


@pytest.mark.django_db
def test_client_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    existing_parent = create_client(
        business_unit=business_units[0],
        client_code="CLI-PARENT",
        name="Parent Client",
    )

    create_response = client.post(
        "/system/clients/",
        data={
            "client_code": "CLI-NEW",
            "name": "New Client",
            "status_code": "ACTIVE",
            "parent_client_id": str(existing_parent.id),
        },
        follow=False,
    )

    assert create_response.status_code == 302
    created_client = ClientRecord.objects.get(client_code="CLI-NEW")
    assert created_client.parent_client_id == existing_parent.id

    update_response = client.post(
        f"/system/clients/{created_client.id}/",
        data={
            "client_code": "CLI-NEW-UPDATED",
            "name": "New Client Updated",
            "status_code": "INACTIVE",
            "parent_client_id": "",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    created_client.refresh_from_db()
    assert created_client.client_code == "CLI-NEW-UPDATED"
    assert created_client.name == "New Client Updated"
    assert created_client.status.value_code == "INACTIVE"
    assert created_client.parent_client_id is None

    collection_response = client.get("/system/clients/new/")
    assert collection_response.status_code == 200
    assert 'name="business_unit_id"' not in collection_response.content.decode()


@pytest.mark.django_db
def test_client_management_can_delete_unused_client_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-DELETE",
        name="Delete Client",
    )

    response = client.post(
        f"/system/clients/{managed_client.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/clients/"
    assert not ClientRecord.objects.filter(id=managed_client.id).exists()
    assert AuditLog.objects.filter(entity_name="client", entity_id=managed_client.id).count() == 1


@pytest.mark.django_db
def test_client_management_delete_is_blocked_when_client_has_child_clients() -> None:
    client, _, business_units = _build_ts_admin_client()
    parent_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-PARENT-DELETE",
        name="Parent Client",
    )
    create_client(
        business_unit=business_units[0],
        client_code="CLI-CHILD-DELETE",
        name="Child Client",
        parent_client=parent_client,
    )

    response = client.post(
        f"/system/clients/{parent_client.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Client" in content
    assert "Client cannot be deleted because it is still referenced" in content
    assert ClientRecord.objects.filter(id=parent_client.id).exists()


@pytest.mark.django_db
def test_internal_category_management_can_delete_unused_category_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    category = create_internal_category(
        business_unit=business_units[0],
        category_code="CAT-DELETE",
        name="Delete Category",
    )

    response = client.post(
        f"/system/internal-categories/{category.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/internal-categories/"
    assert not InternalCategoryRecord.objects.filter(id=category.id).exists()
    assert (
        AuditLog.objects.filter(
            entity_name="internal_category",
            entity_id=category.id,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_internal_category_management_delete_is_blocked_when_category_has_projects() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, _ = (
        _build_project_management_context(business_units[0])
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-BLOCK-CAT",
        name="Blocked Category Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 5, 1),
    )

    response = client.post(
        f"/system/internal-categories/{category.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Internal Category" in content
    assert "Internal category cannot be deleted because it is still referenced" in content
    assert InternalCategoryRecord.objects.filter(id=category.id).exists()


@pytest.mark.django_db
def test_cost_center_management_can_delete_unused_cost_center_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-DELETE",
        name="Delete Cost Center",
    )

    response = client.post(
        f"/system/cost-centers/{cost_center.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/cost-centers/"
    assert not CostCenterRecord.objects.filter(id=cost_center.id).exists()
    assert AuditLog.objects.filter(entity_name="cost_center", entity_id=cost_center.id).count() == 1


@pytest.mark.django_db
def test_cost_center_management_delete_is_blocked_when_cost_center_has_projects() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, _ = (
        _build_project_management_context(business_units[0])
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-BLOCK-CC",
        name="Blocked Cost Center Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 5, 1),
    )

    response = client.post(
        f"/system/cost-centers/{cost_center.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Cost Center" in content
    assert "Cost center cannot be deleted because it is still referenced" in content
    assert CostCenterRecord.objects.filter(id=cost_center.id).exists()


@pytest.mark.django_db
def test_pricing_model_management_create_update_and_delete_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    create_response = client.post(
        "/system/pricing-models/",
        data={
            "name": "Fixed Fee",
            "description": "Fixed price engagements.",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    pricing_model = PricingModelRecord.objects.get(name="Fixed Fee")
    assert pricing_model.office_id == business_units[0].office_id

    update_response = client.post(
        f"/system/pricing-models/{pricing_model.id}/",
        data={
            "form_name": "edit",
            "name": "Fixed Fee Updated",
            "description": "Updated pricing model description.",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    pricing_model.refresh_from_db()
    assert pricing_model.name == "Fixed Fee Updated"
    assert pricing_model.description == "Updated pricing model description."

    delete_response = client.post(
        f"/system/pricing-models/{pricing_model.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == "/system/pricing-models/"
    assert not PricingModelRecord.objects.filter(id=pricing_model.id).exists()


@pytest.mark.django_db
def test_pricing_model_management_delete_is_blocked_when_pricing_model_has_projects() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-BLOCK-PM",
        name="Blocked Pricing Model Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )

    response = client.post(
        f"/system/pricing-models/{pricing_model.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Pricing Model" in content
    assert "Pricing model cannot be deleted because it is still referenced" in content
    assert PricingModelRecord.objects.filter(id=pricing_model.id).exists()


@pytest.mark.django_db
def test_country_bound_forms_show_read_only_country_context() -> None:
    client, _, business_units = _build_ts_admin_client()
    managed_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-READONLY",
        name="Read Only Client",
    )
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Readonly Calendar",
    )
    period_rule = create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 3, 31),
    )

    collection_response = client.get("/system/clients/new/")
    client_detail_response = client.get(f"/system/clients/{managed_client.id}/")
    period_rule_detail_response = client.get(f"/system/calendar-period-rules/{period_rule.id}/")

    for response in (
        collection_response,
        client_detail_response,
        period_rule_detail_response,
    ):
        assert response.status_code == 200
        content = response.content.decode()
        assert 'name="office_name_display"' in content
        assert 'value="Holding"' in content
        assert "readonly" in content


@pytest.mark.django_db
def test_html_country_bound_writes_are_blocked_when_active_country_becomes_inactive() -> None:
    client, _, _ = _build_ts_admin_client()
    holding_country = get_office()
    holding_country.status = ref_value("COUNTRY_STATUS", "INACTIVE")
    holding_country.save(update_fields=["status", "updated_at"])

    response = client.post(
        "/system/clients/",
        data={
            "client_code": "CLI-BLOCKED",
            "name": "Blocked Client",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert ClientRecord.objects.filter(client_code="CLI-BLOCKED").exists() is False


@pytest.mark.django_db
def test_internal_category_and_cost_center_create_pages_work_through_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    category_response = client.post(
        "/system/internal-categories/",
        data={
            "business_unit_id": str(business_units[0].id),
            "category_code": "CAT-NEW",
            "name": "New Category",
            "description": "Category description",
            "status_code": "ACTIVE",
        },
        follow=False,
    )
    assert category_response.status_code == 302
    category = InternalCategoryRecord.objects.get(category_code="CAT-NEW")

    category_update_response = client.post(
        f"/system/internal-categories/{category.id}/",
        data={
            "category_code": "CAT-UPDATED",
            "name": "Updated Category",
            "description": "Updated description",
            "status_code": "INACTIVE",
        },
        follow=False,
    )
    assert category_update_response.status_code == 302
    category.refresh_from_db()
    assert category.category_code == "CAT-UPDATED"
    assert category.status.value_code == "INACTIVE"

    cost_center_response = client.post(
        "/system/cost-centers/",
        data={
            "cost_center_code": "CC-NEW",
            "name": "New Cost Center",
            "description": "Cost center description",
            "status_code": "ACTIVE",
        },
        follow=False,
    )
    assert cost_center_response.status_code == 302
    cost_center = CostCenterRecord.objects.get(cost_center_code="CC-NEW")

    cost_center_update_response = client.post(
        f"/system/cost-centers/{cost_center.id}/",
        data={
            "cost_center_code": "CC-UPDATED",
            "name": "Updated Cost Center",
            "description": "Updated cost center description",
            "status_code": "INACTIVE",
        },
        follow=False,
    )
    assert cost_center_update_response.status_code == 302
    cost_center.refresh_from_db()
    assert cost_center.cost_center_code == "CC-UPDATED"
    assert cost_center.status.value_code == "INACTIVE"

    collection_response = client.get("/system/cost-centers/")
    assert collection_response.status_code == 200
    assert 'name="business_unit_id"' not in collection_response.content.decode()


@pytest.mark.django_db
def test_general_charge_code_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-GCC-HTML",
        name="HTML Cost Center",
        description="Cost center for General Charge Code HTML tests.",
    )
    replacement_cost_center = create_cost_center(
        business_unit=business_units[1],
        cost_center_code="CC-GCC-HTML-2",
        name="Replacement HTML Cost Center",
        description="Replacement cost center for General Charge Code HTML tests.",
    )

    create_response = client.post(
        "/system/general-charge-codes/",
        data={
            "business_unit_id": str(business_units[0].id),
            "code": "GCC-NEW",
            "name": "New General Charge Code",
            "charge_type_code": "STANDARD",
            "cost_center_id": str(cost_center.id),
            "billable_flag": "on",
            "valid_from": date(2026, 4, 1).isoformat(),
            "valid_to": date(2026, 12, 31).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    general_charge_code = GeneralChargeCodeRecord.objects.get(code="GCC-NEW")
    assert general_charge_code.billable_flag is True
    assert general_charge_code.cost_center_id == cost_center.id

    update_response = client.post(
        f"/system/general-charge-codes/{general_charge_code.id}/",
        data={
            "code": "GCC-UPDATED",
            "name": "Updated General Charge Code",
            "charge_type_code": "STANDARD",
            "cost_center_id": str(replacement_cost_center.id),
            "requires_approval_flag": "on",
            "approver_keys": ["ROLE:PROJECT_MANAGER"],
            "description_required_flag": "on",
            "valid_from": date(2026, 5, 1).isoformat(),
            "valid_to": "",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    general_charge_code.refresh_from_db()
    assert general_charge_code.code == "GCC-UPDATED"
    assert general_charge_code.cost_center_id == replacement_cost_center.id
    assert general_charge_code.requires_approval_flag is True
    assert general_charge_code.description_required_flag is True
    assert general_charge_code.valid_to is None
    assert general_charge_code.status.value_code == "INACTIVE"


@pytest.mark.django_db
def test_general_charge_code_approval_role_management_create_via_html() -> None:
    client, employee, _ = _build_ts_admin_client()
    member_employee = create_employee(
        employee_code="EMP-GCC-ROLE-MEMBER",
        full_name="GCC Role Member",
        email="gcc-role-member@example.com",
        primary_business_unit=employee.primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=member_employee,
        business_unit=employee.primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=member_employee, role_code="USER")

    response = client.post(
        "/system/general-charge-code-approval-roles/",
        data={
            "role_code": "HR_APPROVER",
            "name": "HR Approver",
            "description": "Reviews sickness charge codes.",
            "member_employee_ids": [str(member_employee.id)],
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 302
    approval_role = GeneralChargeCodeApprovalRole.objects.get(role_code="HR_APPROVER")
    assert approval_role.name == "HR Approver"
    assert approval_role.member_assignments.filter(employee=member_employee).exists()


@pytest.mark.django_db
def test_general_charge_code_approval_role_collection_shows_dependency_and_coverage_via_html() -> (
    None
):
    client, employee, business_units = _build_ts_admin_client()
    member_employee = create_employee(
        employee_code="EMP-GCC-ROLE-MEMBER-DETAIL",
        full_name="GCC Role Member Detail",
        email="gcc-role-member-detail@example.com",
        primary_business_unit=employee.primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=member_employee,
        business_unit=employee.primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=member_employee, role_code="USER")
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-GCC-ROLE-DETAIL",
        name="HTML Cost Center",
    )
    approval_role = create_general_charge_code_approval_role(
        office=business_units[0].office,
        role_code="HR_DETAIL",
        name="HR Detail Approver",
    )
    assign_general_charge_code_approval_role(
        employee=member_employee,
        approval_role=approval_role,
    )
    create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-DETAIL",
        name="Detail General Charge Code",
        cost_center=cost_center,
        valid_from=date(2026, 1, 1),
        requires_approval_flag=True,
        ad_hoc_approval_roles=[approval_role],
    )

    response = client.get("/system/general-charge-code-approval-roles/")

    assert response.status_code == 200
    content = response.content.decode()
    assert ">GCCs<" in content
    assert ">Coverage<" in content
    assert "HR_DETAIL" in content
    assert "HR Detail Approver" in content


@pytest.mark.django_db
def test_general_charge_code_collection_shows_routing_status_via_html() -> None:
    client, employee, business_units = _build_ts_admin_client()
    member_employee = create_employee(
        employee_code="EMP-GCC-DETAIL-MEMBER",
        full_name="GCC Detail Member",
        email="gcc-detail-member@example.com",
        primary_business_unit=employee.primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=member_employee,
        business_unit=employee.primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=member_employee, role_code="USER")
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-GCC-DETAIL",
        name="HTML Cost Center",
    )
    approval_role = create_general_charge_code_approval_role(
        office=business_units[0].office,
        role_code="HR_ROUTING",
        name="HR Routing Approver",
    )
    assign_general_charge_code_approval_role(
        employee=member_employee,
        approval_role=approval_role,
    )
    create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-ROUTING",
        name="Routing General Charge Code",
        cost_center=cost_center,
        valid_from=date(2026, 1, 1),
        requires_approval_flag=True,
        ad_hoc_approval_roles=[approval_role],
    )

    response = client.get("/system/general-charge-codes/")

    assert response.status_code == 200
    content = response.content.decode()
    assert ">Routing<" in content


@pytest.mark.django_db
def test_general_charge_code_detail_shows_routing_overview_via_html() -> None:
    client, employee, business_units = _build_ts_admin_client()
    member_employee = create_employee(
        employee_code="EMP-GCC-ROUTING-DETAIL",
        full_name="GCC Routing Detail Member",
        email="gcc-routing-detail@example.com",
        primary_business_unit=employee.primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=member_employee,
        business_unit=employee.primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=member_employee, role_code="USER")
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-GCC-ROUTING-DETAIL",
        name="HTML Cost Center",
    )
    approval_role = create_general_charge_code_approval_role(
        office=business_units[0].office,
        role_code="HR_ROUTING_DETAIL",
        name="HR Routing Detail Approver",
    )
    assign_general_charge_code_approval_role(
        employee=member_employee,
        approval_role=approval_role,
    )
    general_charge_code = create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-ROUTING-DETAIL",
        name="Routing Detail General Charge Code",
        cost_center=cost_center,
        valid_from=date(2026, 1, 1),
        requires_approval_flag=True,
        ad_hoc_approval_roles=[approval_role],
    )

    response = client.get(f"/system/general-charge-codes/{general_charge_code.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Routing Overview" in content
    assert "Routing Status" in content
    assert "Routing Warning" in content


@pytest.mark.django_db
def test_general_charge_code_approval_role_detail_shows_coverage_overview_via_html() -> None:
    client, employee, business_units = _build_ts_admin_client()
    member_employee = create_employee(
        employee_code="EMP-GCC-COVERAGE-DETAIL",
        full_name="GCC Coverage Detail Member",
        email="gcc-coverage-detail@example.com",
        primary_business_unit=employee.primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=member_employee,
        business_unit=employee.primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=member_employee, role_code="USER")
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-GCC-COVERAGE-DETAIL",
        name="HTML Cost Center",
    )
    approval_role = create_general_charge_code_approval_role(
        office=business_units[0].office,
        role_code="HR_COVERAGE_DETAIL",
        name="HR Coverage Detail Approver",
    )
    assign_general_charge_code_approval_role(
        employee=member_employee,
        approval_role=approval_role,
    )
    create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-COVERAGE-DETAIL",
        name="Coverage Detail General Charge Code",
        cost_center=cost_center,
        valid_from=date(2026, 1, 1),
        requires_approval_flag=True,
        ad_hoc_approval_roles=[approval_role],
    )

    response = client.get(f"/system/general-charge-code-approval-roles/{approval_role.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Routing Coverage" in content
    assert "Referenced General Charge Codes" in content
    assert "Coverage Warning" in content


@pytest.mark.django_db
def test_general_charge_code_collection_uses_attention_when_approval_route_is_missing() -> None:
    client, _, business_units = _build_ts_admin_client()
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-GCC-ATTN",
        name="HTML Cost Center",
    )
    create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-ATTN",
        name="Attention General Charge Code",
        cost_center=cost_center,
        valid_from=date(2026, 1, 1),
        requires_approval_flag=True,
    )

    response = client.get("/system/general-charge-codes/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "ATTENTION" in content
    assert "BROKEN" not in content


@pytest.mark.django_db
def test_general_charge_code_approval_role_detail_can_clear_unreferenced_last_member_via_html() -> (
    None
):
    client, employee, business_units = _build_ts_admin_client()
    member_employee = create_employee(
        employee_code="EMP-GCC-CLEAR-LAST",
        full_name="GCC Clear Last Member",
        email="gcc-clear-last@example.com",
        primary_business_unit=employee.primary_business_unit,
    )
    assign_employee_to_business_unit(
        employee=member_employee,
        business_unit=employee.primary_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=member_employee, role_code="USER")
    approval_role = create_general_charge_code_approval_role(
        office=business_units[0].office,
        role_code="HR_CLEAR_LAST",
        name="HR Clear Last Approver",
    )
    assign_general_charge_code_approval_role(
        employee=member_employee,
        approval_role=approval_role,
    )

    response = client.post(
        f"/system/general-charge-code-approval-roles/{approval_role.id}/",
        data={
            "form_name": "edit",
            "role_code": "HR_CLEAR_LAST",
            "name": "HR Clear Last Approver",
            "description": "",
            "member_employee_ids": [""],
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 302
    approval_role.refresh_from_db()
    active_members = [
        assignment
        for assignment in approval_role.member_assignments.filter(valid_to__isnull=True)
        if assignment.status.value_code == "ACTIVE"
    ]
    assert active_members == []


@pytest.mark.django_db
def test_general_charge_code_management_requires_cost_center_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    response = client.post(
        "/system/general-charge-codes/new/",
        data={
            "business_unit_id": str(business_units[0].id),
            "code": "GCC-NO-CC",
            "name": "No Cost Center",
            "charge_type_code": "STANDARD",
            "valid_from": date(2026, 4, 1).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "cost_center_id is required." in content
    assert not GeneralChargeCodeRecord.objects.filter(code="GCC-NO-CC").exists()


@pytest.mark.django_db
def test_general_charge_code_management_can_delete_unused_code_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    general_charge_code = create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-DELETE",
        name="Delete General Charge Code",
        valid_from=date(2026, 1, 1),
    )

    response = client.post(
        f"/system/general-charge-codes/{general_charge_code.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/general-charge-codes/"
    assert not GeneralChargeCodeRecord.objects.filter(id=general_charge_code.id).exists()
    assert (
        AuditLog.objects.filter(
            entity_name="general_charge_code",
            entity_id=general_charge_code.id,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_general_charge_code_management_delete_is_blocked_when_code_has_timesheet_usage() -> None:
    client, employee, business_units = _build_ts_admin_client()
    general_charge_code = create_general_charge_code(
        business_unit=business_units[0],
        code="GCC-BLOCK",
        name="Blocked General Charge Code",
        valid_from=date(2026, 1, 1),
    )
    timesheet = WeeklyTimesheet.objects.create(
        employee=employee,
        business_unit=business_units[0],
        week_start_date=date(2026, 5, 4),
        week_end_date=date(2026, 5, 10),
        status=ref_value("TIMESHEET_STATUS", "CREATED"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    TimesheetLine.objects.create(
        weekly_timesheet=timesheet,
        work_date=date(2026, 5, 4),
        general_charge_code=general_charge_code,
        hours="8.00",
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    response = client.post(
        f"/system/general-charge-codes/{general_charge_code.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete General Charge Code" in content
    assert "General charge code cannot be deleted because it is still referenced" in content
    assert GeneralChargeCodeRecord.objects.filter(id=general_charge_code.id).exists()


@pytest.mark.django_db
def test_system_management_collection_filter_can_show_active_or_inactive_records() -> None:
    client, _, business_units = _build_ts_admin_client()
    active_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-ACTIVE",
        name="Active Client",
        active=True,
    )
    inactive_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-INACTIVE",
        name="Inactive Client",
        active=False,
    )

    active_response = client.get("/system/clients/?status=ACTIVE")
    inactive_response = client.get("/system/clients/?status=INACTIVE")

    active_content = active_response.content.decode()
    inactive_content = inactive_response.content.decode()

    assert active_response.status_code == 200
    assert f"/system/clients/{active_client.id}/" in active_content
    assert f"/system/clients/{inactive_client.id}/" not in active_content
    assert inactive_response.status_code == 200
    assert f"/system/clients/{inactive_client.id}/" in inactive_content
    assert f"/system/clients/{active_client.id}/" not in inactive_content


@pytest.mark.django_db
def test_client_management_collection_shows_project_and_employee_counts() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        managed_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    other_client = create_client(
        office=business_units[0].office,
        client_code="CLI-OTHER",
        name="Other Client",
    )
    active_employee = create_employee(
        employee_code="EMP-CLI-ACT",
        full_name="Client Active Employee",
        email="client-active@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=active_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    inactive_employee = create_employee(
        employee_code="EMP-CLI-INACT",
        full_name="Client Inactive Employee",
        email="client-inactive@example.com",
        primary_business_unit=business_units[0],
        active=False,
    )
    assign_employee_to_business_unit(
        employee=inactive_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    inactive_assignment_employee = create_employee(
        employee_code="EMP-CLI-ASG",
        full_name="Client Inactive Assignment Employee",
        email="client-inactive-assignment@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=inactive_assignment_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    active_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CLI-ACT",
        name="Client Active Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=managed_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-CLI-ACT-2",
        name="Client Second Active Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=managed_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-CLI-CLOSED",
        name="Client Closed Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=managed_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
        active=False,
    )
    create_project(
        business_unit=business_units[0],
        project_code="PRJ-OTHER-CLIENT",
        name="Other Client Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=other_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )
    assign_project(
        project=active_project,
        employee=active_employee,
        assignment_start_date=date(2026, 5, 1),
    )
    assign_project(
        project=active_project,
        employee=inactive_employee,
        assignment_start_date=date(2026, 5, 1),
    )
    assign_project(
        project=active_project,
        employee=inactive_assignment_employee,
        assignment_start_date=date(2026, 5, 1),
        active=False,
    )

    response = client.get("/system/clients/")

    assert response.status_code == 200
    content = response.content.decode()
    table_rows = response.context["table_rows"]
    managed_row = next(
        row
        for row in table_rows
        if row["href"] == f"/system/clients/{managed_client.id}/"
        and row["cells"][2] == business_units[0].name
    )
    project_link = f"/system/clients/{managed_client.id}/projects/{business_units[0].id}/"
    assert "<th>Projects</th>" in content
    assert "<th>Employees</th>" in content
    assert "<th>Business Unit</th>" in content
    assert managed_row["cells"][3] == {
        "text": "2",
        "href": project_link,
    }
    assert managed_row["cells"][4] == "1"
    assert f'href="{project_link}">2</a>' in content

    projects_response = client.get(project_link, follow=False)

    assert projects_response.status_code == 302
    assert (
        projects_response.headers["Location"]
        == f"/system/projects/?status=ALL&client_id={managed_client.id}"
        f"&business_unit_id={business_units[0].id}"
    )

    projects_follow_response = client.get(projects_response.headers["Location"])
    assert projects_follow_response.status_code == 200
    projects_content = projects_follow_response.content.decode()
    assert "Client Active Project" in projects_content
    assert "Client Second Active Project" in projects_content
    assert "Client Closed Project" in projects_content
    assert "Other Client Project" not in projects_content


@pytest.mark.django_db
def test_client_management_project_link_requires_assignment_to_row_business_unit() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        managed_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    out_of_scope_business_unit = create_business_unit(
        office=business_units[0].office,
        bu_code="BU-OUT-SCOPE",
        name="Out Scope BU",
    )
    create_project(
        business_unit=out_of_scope_business_unit,
        project_code="PRJ-OUT-SCOPE",
        name="Out Scope Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=managed_client,
        internal_category=create_internal_category(
            business_unit=out_of_scope_business_unit,
            category_code="IC-OUT-SCOPE",
            name="Out Scope Category",
        ),
        cost_center=create_cost_center(
            office=business_units[0].office,
            cost_center_code="CC-OUT-SCOPE",
            name="Out Scope Cost Center",
        ),
        pricing_model=create_pricing_model(
            office=business_units[0].office,
            name="Out Scope Pricing",
        ),
        start_date=date(2026, 5, 1),
    )

    response = client.get("/system/clients/")

    assert response.status_code == 200
    table_rows = response.context["table_rows"]
    managed_row = next(
        row
        for row in table_rows
        if row["href"] == f"/system/clients/{managed_client.id}/"
        and row["cells"][2] == out_of_scope_business_unit.name
    )
    assert managed_row["cells"][3] == {
        "text": "1",
        "href": (f"/system/clients/{managed_client.id}/projects/{out_of_scope_business_unit.id}/"),
    }

    projects_response = client.get(managed_row["cells"][3]["href"])

    assert projects_response.status_code == 403
    assert "You are not assigned to the Business Unit for the selected client row." in (
        projects_response.content.decode()
    )


@pytest.mark.django_db
def test_project_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )

    create_response = client.post(
        "/system/projects/",
        data={
            "business_unit_id": str(business_units[0].id),
            "project_code": "PRJ-NEW",
            "name": "New Project",
            "description": "Project description",
            "project_owner_employee_id": str(project_owner.id),
            "project_manager_employee_id": str(project_manager.id),
            "client_id": str(project_client.id),
            "internal_category_id": str(category.id),
            "cost_center_id": str(cost_center.id),
            "pricing_model_id": str(pricing_model.id),
            "start_date": date(2026, 4, 1).isoformat(),
            "end_date": date(2026, 12, 31).isoformat(),
            "billable_flag": "on",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    project = Project.objects.get(project_code="PRJ-NEW")
    assert project.project_owner_employee_id == project_owner.id
    assert project.project_manager_employee_id == project_manager.id
    assert project.pricing_model_id == pricing_model.id
    assert project.billable_flag is True

    update_response = client.post(
        f"/system/projects/{project.id}/",
        data={
            "project_code": "PRJ-UPD",
            "name": "Updated Project",
            "description": "Updated description",
            "project_owner_employee_id": str(project_owner.id),
            "project_manager_employee_id": str(project_manager.id),
            "client_id": str(project_client.id),
            "internal_category_id": str(category.id),
            "cost_center_id": str(cost_center.id),
            "pricing_model_id": str(pricing_model.id),
            "start_date": date(2026, 4, 1).isoformat(),
            "end_date": "",
            "close_date": date(2026, 10, 31).isoformat(),
            "status_code": "CLOSED",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    project.refresh_from_db()
    assert project.project_code == "PRJ-UPD"
    assert project.name == "Updated Project"
    assert project.close_date == date(2026, 10, 31)
    assert project.status.value_code == "CLOSED"


@pytest.mark.django_db
def test_project_management_collection_shows_requested_grid_and_filter_updates() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        primary_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    secondary_client = create_client(
        office=business_units[0].office,
        client_code="CLI-SECONDARY",
        name="Secondary Client",
    )
    active_employee = create_employee(
        employee_code="EMP-PROJ-ACT",
        full_name="Assigned Employee Active",
        email="assigned-active@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=active_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    inactive_employee = create_employee(
        employee_code="EMP-PROJ-INACT",
        full_name="Assigned Employee Inactive",
        email="assigned-inactive@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=inactive_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-COLLECT",
        name="Collection Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=primary_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )
    other_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-OTHER",
        name="Other Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=secondary_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )
    assign_project(
        project=project,
        employee=active_employee,
        assignment_start_date=date(2026, 5, 1),
    )
    assign_project(
        project=project,
        employee=inactive_employee,
        assignment_start_date=date(2026, 5, 1),
        active=False,
    )

    response = client.get("/system/projects/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "<th>Client</th>" in content
    assert "<th>Project Name</th>" in content
    assert "<th>Employees</th>" in content
    assert '<a href="/system/projects/' in content
    assert ">System BU 1<" in content
    assert primary_client.name in content
    assert project_owner.full_name in content
    assert project_manager.full_name in content
    assert (
        f'href="/system/project-assignments/?status=ALL&amp;client_id={primary_client.id}'
        f'&amp;project_id={project.id}">2</a>'
    ) in content
    assert 'name="client_id"' in content
    assert 'type="hidden" name="status" value="ACTIVE"' in content

    filtered_response = client.get(f"/system/projects/?client_id={primary_client.id}")

    assert filtered_response.status_code == 200
    filtered_content = filtered_response.content.decode()
    assert "Collection Project" in filtered_content
    assert "Other Project" not in filtered_content
    assert f"/system/projects/?client_id={primary_client.id}&amp;status=ACTIVE" in filtered_content
    assert f'href="/system/projects/{project.id}/"' in filtered_content
    assert f'href="/system/projects/{other_project.id}/"' not in filtered_content


@pytest.mark.django_db
def test_project_owner_can_create_update_and_delete_owned_project_via_system_management() -> None:
    client, project_owner, business_units = _build_project_owner_client(
        include_project_manager_role=True
    )
    other_project_owner, _, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )

    create_response = client.post(
        "/system/projects/new/",
        data={
            "business_unit_id": str(business_units[0].id),
            "project_code": "PRJ-OWNER-NEW",
            "name": "Owned Project",
            "description": "Created by owner",
            "project_owner_employee_id": str(other_project_owner.id),
            "project_manager_employee_id": str(project_owner.id),
            "client_id": str(project_client.id),
            "internal_category_id": str(category.id),
            "cost_center_id": str(cost_center.id),
            "pricing_model_id": str(pricing_model.id),
            "start_date": date(2026, 5, 1).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    project = Project.objects.get(project_code="PRJ-OWNER-NEW")
    assert project.project_owner_employee_id == project_owner.id
    assert project.project_manager_employee_id == project_owner.id

    update_response = client.post(
        f"/system/projects/{project.id}/",
        data={
            "project_code": "PRJ-OWNER-UPD",
            "name": "Owned Project Updated",
            "description": "Updated by owner",
            "project_owner_employee_id": str(other_project_owner.id),
            "project_manager_employee_id": str(project_owner.id),
            "client_id": str(project_client.id),
            "internal_category_id": str(category.id),
            "cost_center_id": str(cost_center.id),
            "pricing_model_id": str(pricing_model.id),
            "start_date": date(2026, 5, 1).isoformat(),
            "end_date": date(2026, 12, 31).isoformat(),
            "close_date": "",
            "billable_flag": "on",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    project.refresh_from_db()
    assert project.project_code == "PRJ-OWNER-UPD"
    assert project.name == "Owned Project Updated"
    assert project.project_owner_employee_id == project_owner.id
    assert project.billable_flag is True

    delete_response = client.post(
        f"/system/projects/{project.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == "/system/projects/"
    assert not Project.objects.filter(id=project.id).exists()


@pytest.mark.django_db
def test_project_owner_cannot_open_project_outside_owned_scope() -> None:
    client, _, business_units = _build_project_owner_client()
    other_project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-NOT-OWNED",
        name="Not Owned Project",
        project_owner_employee=other_project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )

    response = client.get(f"/system/projects/{project.id}/")

    assert response.status_code == 403
    assert "owned-project scope" in response.content.decode()


@pytest.mark.django_db
def test_project_management_can_delete_unused_project_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-DELETE",
        name="Delete Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )

    response = client.post(
        f"/system/projects/{project.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/projects/"
    assert not Project.objects.filter(id=project.id).exists()
    assert AuditLog.objects.filter(entity_name="project", entity_id=project.id).count() == 1


@pytest.mark.django_db
def test_project_management_delete_is_blocked_when_project_has_assignments() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-BLOCK-DELETE",
        name="Blocked Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 5, 1),
    )
    ProjectAssignment.objects.create(
        project=project,
        employee=project_owner,
        assignment_start_date=date(2026, 5, 1),
        assignment_end_date=None,
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    response = client.post(
        f"/system/projects/{project.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Project" in content
    assert "Project cannot be deleted because it is still referenced" in content
    assert Project.objects.filter(id=project.id).exists()


@pytest.mark.django_db
def test_project_management_can_use_same_office_client_from_another_business_unit() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        _,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    office_level_client = create_client(
        business_unit=business_units[1],
        client_code="CLI-OFFICE-WIDE",
        name="Office Wide Client",
    )

    response = client.post(
        "/system/projects/",
        data={
            "business_unit_id": str(business_units[0].id),
            "project_code": "PRJ-OFFICE-CLIENT",
            "name": "Office Client Project",
            "description": "Uses client from another BU in same office",
            "project_owner_employee_id": str(project_owner.id),
            "project_manager_employee_id": str(project_manager.id),
            "client_id": str(office_level_client.id),
            "internal_category_id": str(category.id),
            "cost_center_id": str(cost_center.id),
            "pricing_model_id": str(pricing_model.id),
            "start_date": date(2026, 5, 1).isoformat(),
            "billable_flag": "on",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 302
    project = Project.objects.get(project_code="PRJ-OFFICE-CLIENT")
    assert project.client_id == office_level_client.id


@pytest.mark.django_db
def test_project_management_can_use_same_office_cost_center_from_another_business_unit() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        project_client,
        category,
        _,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    office_level_cost_center = create_cost_center(
        business_unit=business_units[1],
        cost_center_code="CC-OFFICE-WIDE",
        name="Office Wide Cost Center",
    )

    response = client.post(
        "/system/projects/",
        data={
            "business_unit_id": str(business_units[0].id),
            "project_code": "PRJ-OFFICE-CC",
            "name": "Office Cost Center Project",
            "description": "Uses cost center from another BU in same office",
            "project_owner_employee_id": str(project_owner.id),
            "project_manager_employee_id": str(project_manager.id),
            "client_id": str(project_client.id),
            "internal_category_id": str(category.id),
            "cost_center_id": str(office_level_cost_center.id),
            "pricing_model_id": str(pricing_model.id),
            "start_date": date(2026, 5, 1).isoformat(),
            "billable_flag": "on",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 302
    project = Project.objects.get(project_code="PRJ-OFFICE-CC")
    assert project.cost_center_id == office_level_cost_center.id


@pytest.mark.django_db
def test_project_assignment_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, _ = (
        _build_project_management_context(business_units[0])
    )
    foreign_country = create_office(office_name="Assignment UI Office")
    foreign_business_unit = create_business_unit(
        bu_code="BU-ASN-FOREIGN",
        name="Assignment Foreign BU",
        office=foreign_country,
    )
    assigned_employee = create_employee(
        employee_code="EMP-ASSIGN-1",
        full_name="Assigned Employee",
        email="assigned-employee@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    other_scoped_employee = create_employee(
        employee_code="EMP-ASSIGN-BU2",
        full_name="Other Scoped Assignment Employee",
        email="other-scoped-assignment@example.com",
        primary_business_unit=business_units[1],
    )
    assign_employee_to_business_unit(
        employee=other_scoped_employee,
        business_unit=business_units[1],
        is_primary_flag=True,
    )
    assign_role(employee=other_scoped_employee, role_code="USER")
    foreign_employee = create_employee(
        employee_code="EMP-ASSIGN-FOREIGN",
        full_name="Foreign Assignment Employee",
        email="foreign-assignment@example.com",
        primary_business_unit=foreign_business_unit,
    )
    assign_employee_to_business_unit(
        employee=foreign_employee,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=foreign_employee, role_code="USER")
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-ASN",
        name="Assignment Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        start_date=date(2026, 4, 1),
    )

    collection_response = client.get("/system/project-assignments/new/")
    collection_content = collection_response.content.decode()
    assert collection_response.status_code == 200
    assert "EMP-ASSIGN-1" in collection_content
    assert "EMP-ASSIGN-FOREIGN" not in collection_content
    selected_project_response = client.get(
        f"/system/project-assignments/new/?project_id={project.id}"
    )
    selected_project_content = selected_project_response.content.decode()
    assert selected_project_response.status_code == 200
    assert f'data-business-unit-id="{business_units[0].id}"' in selected_project_content
    assert "projectSelect.addEventListener" in selected_project_content
    assigned_option = re.search(
        rf'<option value="{assigned_employee.id}"(?P<attrs>[^>]*)>[^<]*EMP-ASSIGN-1',
        selected_project_content,
    )
    other_scoped_option = re.search(
        rf'<option value="{other_scoped_employee.id}"(?P<attrs>[^>]*)>[^<]*EMP-ASSIGN-BU2',
        selected_project_content,
    )
    assert assigned_option is not None
    assert other_scoped_option is not None
    assert "data-business-unit-ids" in assigned_option.group("attrs")
    assert "hidden" not in assigned_option.group("attrs")
    assert "disabled" not in assigned_option.group("attrs")
    assert "hidden" in other_scoped_option.group("attrs")
    assert "disabled" in other_scoped_option.group("attrs")

    foreign_create_response = client.post(
        "/system/project-assignments/new/",
        data={
            "project_id": str(project.id),
            "employee_id": str(foreign_employee.id),
            "assignment_start_date": date(2026, 4, 7).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert foreign_create_response.status_code == 200
    assert "employee must be active in the project Business Unit" in (
        foreign_create_response.content.decode()
    )
    assert not ProjectAssignment.objects.filter(project=project, employee=foreign_employee).exists()

    create_response = client.post(
        "/system/project-assignments/new/",
        data={
            "project_id": str(project.id),
            "employee_id": str(assigned_employee.id),
            "assignment_start_date": date(2026, 4, 7).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    assignment = ProjectAssignment.objects.get(project=project, employee=assigned_employee)

    detail_response = client.get(f"/system/project-assignments/{assignment.id}/")
    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert "Assignment Project" in detail_content
    assert "Assignment Start Date" in detail_content

    update_response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={
            "assignment_start_date": date(2026, 4, 21).isoformat(),
            "assignment_end_date": date(2026, 9, 30).isoformat(),
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.assignment_end_date == date(2026, 9, 30)
    assert assignment.status.value_code == "INACTIVE"


@pytest.mark.django_db
def test_project_owner_can_create_update_and_delete_assignments_for_owned_projects() -> None:
    client, project_owner, business_units = _build_project_owner_client()
    _, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    other_project_owner = create_employee(
        employee_code="EMP-OTHER-OWNER",
        full_name="Other Owner",
        email="other-owner@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=other_project_owner,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=other_project_owner, role_code="USER")
    assign_role(employee=other_project_owner, role_code="PROJECT_OWNER")
    assigned_employee = create_employee(
        employee_code="EMP-OWNER-ASN",
        full_name="Owner Assignment Employee",
        email="owner-assignment@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    owned_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-OWNER-ASN",
        name="Owned Assignment Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    foreign_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-FOREIGN-ASN",
        name="Foreign Assignment Project",
        project_owner_employee=other_project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )

    create_page = client.get("/system/project-assignments/new/")
    create_content = create_page.content.decode()
    assert create_page.status_code == 200
    assert "PRJ-OWNER-ASN" in create_content
    assert "PRJ-FOREIGN-ASN" not in create_content

    create_response = client.post(
        "/system/project-assignments/new/",
        data={
            "project_id": str(owned_project.id),
            "employee_id": str(assigned_employee.id),
            "assignment_start_date": date(2026, 4, 7).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    assignment = ProjectAssignment.objects.get(project=owned_project, employee=assigned_employee)

    update_response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={
            "assignment_start_date": date(2026, 4, 21).isoformat(),
            "assignment_end_date": date(2026, 9, 30).isoformat(),
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.assignment_end_date == date(2026, 9, 30)
    assert assignment.status.value_code == "INACTIVE"

    delete_response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == "/system/project-assignments/"
    assert not ProjectAssignment.objects.filter(id=assignment.id).exists()

    foreign_assignment = ProjectAssignment.objects.create(
        project=foreign_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 7),
        assignment_end_date=None,
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    forbidden_response = client.get(f"/system/project-assignments/{foreign_assignment.id}/")
    assert forbidden_response.status_code == 403
    assert "owned or managed project scope" in forbidden_response.content.decode()


@pytest.mark.django_db
def test_project_manager_can_manage_assignments_for_managed_projects_only() -> None:
    client, project_manager, business_units = _build_project_manager_client()
    project_owner = create_employee(
        employee_code="EMP-MGR-OWNER",
        full_name="Manager Test Owner",
        email="manager-test-owner@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")
    other_project_manager = create_employee(
        employee_code="EMP-OTHER-MGR",
        full_name="Other Project Manager",
        email="other-project-manager@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=other_project_manager,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=other_project_manager, role_code="USER")
    assign_role(employee=other_project_manager, role_code="PROJECT_MANAGER")
    project_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-MGR-ASN",
        name="Manager Assignment Client",
    )
    category = create_internal_category(
        business_unit=business_units[0],
        category_code="CAT-MGR-ASN",
        name="Manager Assignment Category",
    )
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-MGR-ASN",
        name="Manager Assignment Cost Center",
    )
    pricing_model = create_pricing_model(
        business_unit=business_units[0],
        name="Manager Assignment Pricing",
    )
    assigned_employee = create_employee(
        employee_code="EMP-MGR-ASN",
        full_name="Managed Assignment Employee",
        email="managed-assignment@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    managed_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-MANAGED-ASN",
        name="Managed Assignment Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    foreign_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-FOREIGN-MGR-ASN",
        name="Foreign Managed Assignment Project",
        project_owner_employee=project_owner,
        project_manager_employee=other_project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    managed_assignment = ProjectAssignment.objects.create(
        project=managed_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 7),
        assignment_end_date=date(2026, 4, 20),
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )
    ProjectAssignment.objects.create(
        project=foreign_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 14),
        assignment_end_date=None,
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    collection_response = client.get("/system/project-assignments/")
    collection_content = collection_response.content.decode()
    assert collection_response.status_code == 200
    assert "PRJ-MANAGED-ASN" in collection_content
    assert "PRJ-FOREIGN-MGR-ASN" not in collection_content
    assert "EMP-MGR-ASN - Managed Assignment Employee" in collection_content

    create_page = client.get("/system/project-assignments/new/")
    create_content = create_page.content.decode()
    assert create_page.status_code == 200
    assert "PRJ-MANAGED-ASN" in create_content
    assert "PRJ-FOREIGN-MGR-ASN" not in create_content
    assert "EMP-MGR-ASN - Managed Assignment Employee" in create_content

    create_response = client.post(
        "/system/project-assignments/new/",
        data={
            "project_id": str(managed_project.id),
            "employee_id": str(assigned_employee.id),
            "assignment_start_date": date(2026, 4, 21).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    assignment = ProjectAssignment.objects.get(
        project=managed_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 21),
    )

    update_response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={
            "assignment_start_date": date(2026, 4, 21).isoformat(),
            "assignment_end_date": date(2026, 9, 30).isoformat(),
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.assignment_end_date == date(2026, 9, 30)
    assert assignment.status.value_code == "INACTIVE"

    delete_response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == "/system/project-assignments/"
    assert not ProjectAssignment.objects.filter(id=assignment.id).exists()
    assert ProjectAssignment.objects.filter(id=managed_assignment.id).exists()

    foreign_assignment = ProjectAssignment.objects.create(
        project=foreign_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 7),
        assignment_end_date=None,
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    forbidden_response = client.get(f"/system/project-assignments/{foreign_assignment.id}/")
    assert forbidden_response.status_code == 403
    assert "owned or managed project scope" in forbidden_response.content.decode()


@pytest.mark.django_db
def test_project_assignment_management_can_delete_assignment_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    assigned_employee = create_employee(
        employee_code="EMP-ASSIGN-DELETE",
        full_name="Delete Assigned Employee",
        email="assigned-delete@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-ASN-DELETE",
        name="Assignment Delete Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    assignment = ProjectAssignment.objects.create(
        project=project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 7),
        assignment_end_date=None,
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by="system@test.local",
        updated_by="system@test.local",
    )

    response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/project-assignments/"
    assert not ProjectAssignment.objects.filter(id=assignment.id).exists()
    assert (
        AuditLog.objects.filter(
            entity_name="project_assignment",
            entity_id=assignment.id,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_cross_office_staffing_admin_can_create_update_and_delete_assignments() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        project_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    origin_office = create_office(office_name="Origin Staffing Office")
    origin_business_unit = create_business_unit(
        bu_code="BU-CO-ORIGIN",
        name="Origin Staffing BU",
        office=origin_office,
    )
    assigned_employee = create_employee(
        employee_code="EMP-CO-ASSIGN-1",
        full_name="Cross Office Employee",
        email="cross-office-employee@example.com",
        primary_business_unit=origin_business_unit,
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=origin_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CO-1",
        name="Cross Office Target Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )

    create_page = client.get("/system/cross-office-staffing/new/")

    assert create_page.status_code == 200
    create_content = create_page.content.decode()
    assert "Create Cross-Office Staffing" in create_content
    assert "current target-project scope" in create_content
    assert "PRJ-CO-1" in create_content
    assert "EMP-CO-ASSIGN-1" in create_content
    assert f'value="{project.office.office_name}"' in create_content
    assert (
        f'value="{project.business_unit.bu_code} - {project.business_unit.name}"' in create_content
    )
    assert f'data-office-name="{project.office.office_name}"' in create_content
    assert (
        f'data-bu-label="{project.business_unit.bu_code} - {project.business_unit.name}"'
        in create_content
    )
    assert f'data-office-id="{origin_office.id}"' in create_content
    assert (
        f'data-origin-bu-label="{origin_business_unit.bu_code} - {origin_business_unit.name}"'
        in create_content
    )

    create_response = client.post(
        "/system/cross-office-staffing/new/",
        data={
            "project_id": str(project.id),
            "origin_office_id": str(origin_office.id),
            "employee_id": str(assigned_employee.id),
            "assignment_start_date": date(2026, 4, 7).isoformat(),
            "assignment_end_date": date(2026, 9, 30).isoformat(),
            "justification_text": "Temporary staffing support for the target office.",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    assignment = CrossOfficeProjectAssignment.objects.get(
        project=project,
        employee=assigned_employee,
    )
    assert assignment.origin_office_id == origin_office.id
    assert assignment.origin_business_unit_id == origin_business_unit.id

    detail_response = client.get(f"/system/cross-office-staffing/{assignment.id}/")

    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert "Edit Cross-Office Staffing" in detail_content
    assert "Cross Office Target Project" in detail_content
    assert "Origin Staffing Office" in detail_content
    assert "Origin Staffing BU" in detail_content

    update_response = client.post(
        f"/system/cross-office-staffing/{assignment.id}/",
        data={
            "assignment_start_date": date(2026, 4, 14).isoformat(),
            "assignment_end_date": date(2026, 10, 31).isoformat(),
            "justification_text": "Extended coverage during delivery ramp-up.",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    assignment.refresh_from_db()
    assert assignment.assignment_start_date == date(2026, 4, 14)
    assert assignment.assignment_end_date == date(2026, 10, 31)
    assert assignment.justification_text == "Extended coverage during delivery ramp-up."
    assert assignment.status.value_code == "INACTIVE"

    delete_response = client.post(
        f"/system/cross-office-staffing/{assignment.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == "/system/cross-office-staffing/"
    assert not CrossOfficeProjectAssignment.objects.filter(id=assignment.id).exists()
    assert (
        AuditLog.objects.filter(
            entity_name="cross_office_project_assignment",
            entity_id=assignment.id,
        ).count()
        == 6
    )


@pytest.mark.django_db
def test_cross_office_staffing_rejects_same_office_employee() -> None:
    client, _, business_units = _build_ts_admin_client()
    (
        project_owner,
        project_manager,
        project_client,
        category,
        cost_center,
        pricing_model,
    ) = _build_project_management_context(business_units[0])
    local_employee = create_employee(
        employee_code="EMP-CO-LOCAL",
        full_name="Local Employee",
        email="local-cross-office@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=local_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=local_employee, role_code="USER")
    project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CO-LOCAL",
        name="Same Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )

    response = client.post(
        "/system/cross-office-staffing/new/",
        data={
            "project_id": str(project.id),
            "origin_office_id": str(local_employee.office_id),
            "employee_id": str(local_employee.id),
            "assignment_start_date": date(2026, 4, 7).isoformat(),
            "status_code": "ACTIVE",
        },
    )

    assert response.status_code == 200
    assert (
        "Cross-office staffing requires the employee Office to differ from the target "
        "project Office." in response.content.decode()
    )
    assert not CrossOfficeProjectAssignment.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_project_owner_can_manage_cross_office_staffing_for_owned_projects_only() -> None:
    client, project_owner, business_units = _build_project_owner_client()
    _, project_manager, project_client, category, cost_center, pricing_model = (
        _build_project_management_context(business_units[0])
    )
    other_project_owner = create_employee(
        employee_code="EMP-CO-OTHER-OWNER",
        full_name="Other Cross Office Owner",
        email="other-cross-office-owner@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=other_project_owner,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=other_project_owner, role_code="USER")
    assign_role(employee=other_project_owner, role_code="PROJECT_OWNER")
    origin_office = create_office(office_name="Owner Origin Office")
    origin_business_unit = create_business_unit(
        bu_code="BU-CO-OWNER",
        name="Owner Origin BU",
        office=origin_office,
    )
    assigned_employee = create_employee(
        employee_code="EMP-CO-OWNER-ASN",
        full_name="Owned Cross Office Employee",
        email="owned-cross-office@example.com",
        primary_business_unit=origin_business_unit,
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=origin_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    owned_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CO-OWNED",
        name="Owned Cross Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    foreign_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CO-FOREIGN",
        name="Foreign Cross Office Project",
        project_owner_employee=other_project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )

    create_page = client.get("/system/cross-office-staffing/new/")
    create_content = create_page.content.decode()
    assert create_page.status_code == 200
    assert "PRJ-CO-OWNED" in create_content
    assert "PRJ-CO-FOREIGN" not in create_content

    create_response = client.post(
        "/system/cross-office-staffing/new/",
        data={
            "project_id": str(owned_project.id),
            "origin_office_id": str(origin_office.id),
            "employee_id": str(assigned_employee.id),
            "assignment_start_date": date(2026, 4, 7).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    assignment = CrossOfficeProjectAssignment.objects.get(
        project=owned_project,
        employee=assigned_employee,
    )

    delete_response = client.post(
        f"/system/cross-office-staffing/{assignment.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert not CrossOfficeProjectAssignment.objects.filter(id=assignment.id).exists()

    foreign_assignment = assign_cross_office_project(
        project=foreign_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 7),
    )

    forbidden_response = client.get(f"/system/cross-office-staffing/{foreign_assignment.id}/")
    assert forbidden_response.status_code == 403
    assert "owned or managed project scope" in forbidden_response.content.decode()


@pytest.mark.django_db
def test_project_manager_can_manage_cross_office_staffing_for_managed_projects_only() -> None:
    client, project_manager, business_units = _build_project_manager_client()
    project_owner = create_employee(
        employee_code="EMP-CO-MGR-OWNER",
        full_name="Cross Office Manager Test Owner",
        email="cross-office-manager-owner@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")
    other_project_manager = create_employee(
        employee_code="EMP-CO-OTHER-MGR",
        full_name="Other Cross Office Manager",
        email="other-cross-office-manager@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=other_project_manager,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=other_project_manager, role_code="USER")
    assign_role(employee=other_project_manager, role_code="PROJECT_MANAGER")
    project_client = create_client(
        business_unit=business_units[0],
        client_code="CLI-CO-MGR",
        name="Cross Office Manager Client",
    )
    category = create_internal_category(
        business_unit=business_units[0],
        category_code="CAT-CO-MGR",
        name="Cross Office Manager Category",
    )
    cost_center = create_cost_center(
        business_unit=business_units[0],
        cost_center_code="CC-CO-MGR",
        name="Cross Office Manager Cost Center",
    )
    pricing_model = create_pricing_model(
        business_unit=business_units[0],
        name="Cross Office Manager Pricing",
    )
    origin_office = create_office(office_name="Manager Origin Office")
    origin_business_unit = create_business_unit(
        bu_code="BU-CO-MGR",
        name="Manager Origin BU",
        office=origin_office,
    )
    assigned_employee = create_employee(
        employee_code="EMP-CO-MGR-ASN",
        full_name="Managed Cross Office Employee",
        email="managed-cross-office@example.com",
        primary_business_unit=origin_business_unit,
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=origin_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
    managed_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CO-MANAGED",
        name="Managed Cross Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )
    foreign_project = create_project(
        business_unit=business_units[0],
        project_code="PRJ-CO-FOREIGN-MGR",
        name="Foreign Managed Cross Office Project",
        project_owner_employee=project_owner,
        project_manager_employee=other_project_manager,
        client=project_client,
        internal_category=category,
        cost_center=cost_center,
        pricing_model=pricing_model,
        start_date=date(2026, 4, 1),
    )

    collection_response = client.get("/system/cross-office-staffing/")
    create_page = client.get("/system/cross-office-staffing/new/")

    assert collection_response.status_code == 200
    assert create_page.status_code == 200
    create_content = create_page.content.decode()
    assert "PRJ-CO-MANAGED" in create_content
    assert "PRJ-CO-FOREIGN-MGR" not in create_content

    create_response = client.post(
        "/system/cross-office-staffing/new/",
        data={
            "project_id": str(managed_project.id),
            "origin_office_id": str(origin_office.id),
            "employee_id": str(assigned_employee.id),
            "assignment_start_date": date(2026, 4, 21).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    assignment = CrossOfficeProjectAssignment.objects.get(
        project=managed_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 21),
    )
    assert "PRJ-CO-MANAGED" in collection_response.content.decode()
    assert "PRJ-CO-FOREIGN-MGR" not in collection_response.content.decode()

    foreign_assignment = assign_cross_office_project(
        project=foreign_project,
        employee=assigned_employee,
        assignment_start_date=date(2026, 4, 7),
    )

    forbidden_response = client.get(f"/system/cross-office-staffing/{foreign_assignment.id}/")
    assert forbidden_response.status_code == 403
    assert "owned or managed project scope" in forbidden_response.content.decode()

    delete_response = client.post(
        f"/system/cross-office-staffing/{assignment.id}/",
        data={"form_name": "delete"},
        follow=False,
    )
    assert delete_response.status_code == 302
    assert not CrossOfficeProjectAssignment.objects.filter(id=assignment.id).exists()


@pytest.mark.django_db
def test_employee_transfer_ui_blocks_source_employee_with_active_cross_office_staffing() -> None:
    client, _, _ = _build_ts_admin_master_client()
    source_office = create_office(office_name="Cross Office Source")
    target_office = create_office(office_name="Cross Office Target")
    source_bu = create_business_unit(
        bu_code="SRC-CO-BLOCK",
        name="Cross Office Source BU",
        office=source_office,
    )
    target_bu = create_business_unit(
        bu_code="TGT-CO-BLOCK",
        name="Cross Office Target BU",
        office=target_office,
    )
    source_employee = create_employee(
        employee_code="EMP-CO-BLOCK-1",
        full_name="Blocked Cross Office Source Employee",
        email="blocked-cross-office-source@example.com",
        primary_business_unit=source_bu,
    )
    assign_employee_to_business_unit(
        employee=source_employee,
        business_unit=source_bu,
        is_primary_flag=True,
    )
    assign_role(employee=source_employee, role_code="USER")
    project_owner = create_employee(
        employee_code="EMP-CO-BLOCK-OWNER",
        full_name="Cross Office Block Owner",
        email="cross-office-block-owner@example.com",
        primary_business_unit=target_bu,
    )
    assign_employee_to_business_unit(
        employee=project_owner,
        business_unit=target_bu,
        is_primary_flag=True,
    )
    assign_role(employee=project_owner, role_code="USER")
    assign_role(employee=project_owner, role_code="PROJECT_OWNER")
    project_manager = create_employee(
        employee_code="EMP-CO-BLOCK-MGR",
        full_name="Cross Office Block Manager",
        email="cross-office-block-manager@example.com",
        primary_business_unit=target_bu,
    )
    assign_employee_to_business_unit(
        employee=project_manager,
        business_unit=target_bu,
        is_primary_flag=True,
    )
    assign_role(employee=project_manager, role_code="USER")
    assign_role(employee=project_manager, role_code="PROJECT_MANAGER")
    target_client = create_client(
        business_unit=target_bu,
        client_code="CLI-CO-BLOCK",
        name="Cross Office Block Client",
    )
    target_category = create_internal_category(
        business_unit=target_bu,
        category_code="CAT-CO-BLOCK",
        name="Cross Office Block Category",
    )
    target_cost_center = create_cost_center(
        business_unit=target_bu,
        cost_center_code="CC-CO-BLOCK",
        name="Cross Office Block Cost Center",
    )
    target_pricing_model = create_pricing_model(
        business_unit=target_bu,
        name="Cross Office Block Pricing",
    )
    target_project = create_project(
        business_unit=target_bu,
        project_code="PRJ-CO-BLOCK",
        name="Cross Office Block Project",
        project_owner_employee=project_owner,
        project_manager_employee=project_manager,
        client=target_client,
        internal_category=target_category,
        cost_center=target_cost_center,
        pricing_model=target_pricing_model,
        start_date=date(2026, 4, 1),
    )
    assign_cross_office_project(
        project=target_project,
        employee=source_employee,
        assignment_start_date=date(2026, 4, 7),
    )

    load_response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "select_source",
            "source_employee_id": str(source_employee.id),
        },
    )

    assert load_response.status_code == 200
    content = load_response.content.decode()
    assert "Transfer Readiness" in content
    assert "BLOCKED" in content
    assert "Active Cross-Office Staffing" in content
    assert "Target Setup" not in content

    transfer_response = client.post(
        "/system/employee-transfers/new/",
        data={
            "form_name": "transfer",
            "source_employee_id": str(source_employee.id),
            "new_employee_code": "EMP-CO-BLOCK-TARGET",
            "target_office_id": str(target_office.id),
            "target_primary_business_unit_id": str(target_bu.id),
            "target_role_codes": ["USER"],
        },
    )

    assert transfer_response.status_code == 200
    assert "Employee transfer is blocked" in transfer_response.content.decode()
    source_employee.refresh_from_db()
    assert source_employee.status.value_code == "ACTIVE"
    assert not Employee.objects.filter(employee_code="EMP-CO-BLOCK-TARGET").exists()


@pytest.mark.django_db
def test_calendar_period_rule_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Standard Calendar",
    )
    base_employee = create_employee(
        employee_code="EMP-CAL-1",
        full_name="Calendar Employee",
        email="calendar-employee@example.com",
        primary_business_unit=business_units[0],
    )
    assign_employee_to_business_unit(
        employee=base_employee,
        business_unit=business_units[0],
        is_primary_flag=True,
    )
    assign_role(employee=base_employee, role_code="USER")
    assign_calendar(employee=base_employee, yearly_calendar=yearly_calendar)

    collection_response = client.get("/system/calendar-period-rules/new/")
    assert collection_response.status_code == 200
    assert 'name="business_unit_id"' in collection_response.content.decode()

    create_response = client.post(
        "/system/calendar-period-rules/new/",
        data={
            "business_unit_id": str(business_units[0].id),
            "yearly_calendar_id": str(yearly_calendar.id),
            "effective_from": date(2026, 1, 1).isoformat(),
            "effective_to": date(2026, 3, 31).isoformat(),
            "monday_max_hours": "8.00",
            "tuesday_max_hours": "8.00",
            "wednesday_max_hours": "8.00",
            "thursday_max_hours": "8.00",
            "friday_max_hours": "6.00",
            "working_on_saturdays_flag": "on",
            "saturday_max_hours": "5.00",
            "sunday_max_hours": "0.00",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    period_rule = CalendarPeriodRule.objects.get(
        yearly_calendar=yearly_calendar,
        business_unit=business_units[0],
        effective_from=date(2026, 1, 1),
    )
    assert period_rule.business_unit_id == business_units[0].id
    assert period_rule.working_on_saturdays_flag is True
    assert period_rule.working_on_sundays_flag is False
    assert str(period_rule.saturday_max_hours) == "5.00"
    assert str(period_rule.sunday_max_hours) == "0.00"

    detail_response = client.get(f"/system/calendar-period-rules/{period_rule.id}/")
    assert detail_response.status_code == 200
    assert 'name="business_unit_id"' in detail_response.content.decode()

    update_response = client.post(
        f"/system/calendar-period-rules/{period_rule.id}/",
        data={
            "business_unit_id": str(business_units[0].id),
            "effective_from": date(2026, 1, 1).isoformat(),
            "effective_to": date(2026, 4, 30).isoformat(),
            "monday_max_hours": "7.50",
            "tuesday_max_hours": "7.50",
            "wednesday_max_hours": "7.50",
            "thursday_max_hours": "7.50",
            "friday_max_hours": "6.00",
            "working_on_saturdays_flag": "on",
            "saturday_max_hours": "5.50",
            "working_on_sundays_flag": "on",
            "sunday_max_hours": "4.50",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    period_rule.refresh_from_db()
    assert period_rule.effective_to == date(2026, 4, 30)
    assert str(period_rule.monday_max_hours) == "7.50"
    assert period_rule.status.value_code == "INACTIVE"
    assert period_rule.business_unit_id == business_units[0].id
    assert period_rule.working_on_saturdays_flag is True
    assert period_rule.working_on_sundays_flag is True
    assert str(period_rule.saturday_max_hours) == "5.50"
    assert str(period_rule.sunday_max_hours) == "4.50"


@pytest.mark.django_db
def test_calendar_period_rule_detail_renders_on_get() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Operations Calendar",
    )
    period_rule = create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 3, 31),
    )

    response = client.get(f"/system/calendar-period-rules/{period_rule.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Operations Calendar" in content
    assert date(2026, 1, 1).isoformat() in content


@pytest.mark.django_db
def test_calendar_period_rule_can_be_deleted_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Delete Period Rule Calendar",
    )
    period_rule = create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        business_unit=business_units[0],
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 3, 31),
    )

    response = client.post(
        f"/system/calendar-period-rules/{period_rule.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/calendar-period-rules/"
    assert CalendarPeriodRule.objects.filter(id=period_rule.id).exists() is False


@pytest.mark.django_db
def test_calendar_period_rule_management_all_filter_shows_active_and_inactive_records() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="All Calendars View",
    )
    active_rule = create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 3, 31),
    )
    inactive_rule = create_calendar_period_rule(
        yearly_calendar=yearly_calendar,
        effective_from=date(2026, 4, 1),
        effective_to=date(2026, 6, 30),
    )
    inactive_rule.status = ref_value("CALENDAR_PERIOD_STATUS", "INACTIVE")
    inactive_rule.save(update_fields=["status", "updated_at"])

    response = client.get("/system/calendar-period-rules/?status=ALL")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'href="/system/calendar-period-rules/?status=ALL"' in content
    assert f"/system/calendar-period-rules/{active_rule.id}/" in content
    assert f"/system/calendar-period-rules/{inactive_rule.id}/" in content


@pytest.mark.django_db
def test_calendar_period_rule_management_allows_overlap_for_different_business_units() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Shared Office Calendar",
    )

    first_response = client.post(
        "/system/calendar-period-rules/",
        data={
            "business_unit_id": str(business_units[0].id),
            "yearly_calendar_id": str(yearly_calendar.id),
            "effective_from": date(2026, 1, 1).isoformat(),
            "effective_to": date(2026, 3, 31).isoformat(),
            "monday_max_hours": "8.00",
            "tuesday_max_hours": "8.00",
            "wednesday_max_hours": "8.00",
            "thursday_max_hours": "8.00",
            "friday_max_hours": "8.00",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert first_response.status_code == 302

    overlap_response = client.post(
        "/system/calendar-period-rules/",
        data={
            "business_unit_id": str(business_units[1].id),
            "yearly_calendar_id": str(yearly_calendar.id),
            "effective_from": date(2026, 2, 1).isoformat(),
            "effective_to": date(2026, 4, 30).isoformat(),
            "monday_max_hours": "7.50",
            "tuesday_max_hours": "7.50",
            "wednesday_max_hours": "7.50",
            "thursday_max_hours": "7.50",
            "friday_max_hours": "7.50",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert overlap_response.status_code == 302
    assert (
        CalendarPeriodRule.objects.filter(
            yearly_calendar=yearly_calendar,
            business_unit=business_units[1],
            effective_from=date(2026, 2, 1),
        ).exists()
        is True
    )


@pytest.mark.django_db
def test_calendar_management_create_update_and_filter_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    create_response = client.post(
        "/system/calendars/",
        data={
            "calendar_year": "2027",
            "calendar_name": "Delivery Calendar",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    yearly_calendar = YearlyCalendar.objects.get(
        office=business_units[0].office,
        calendar_year=2027,
    )
    assert yearly_calendar.calendar_name == "Delivery Calendar"

    detail_response = client.get(f"/system/calendars/{yearly_calendar.id}/?month=5")

    assert detail_response.status_code == 200
    detail_content = detail_response.content.decode()
    assert 'name="business_unit_id"' not in detail_content
    assert "Year Summary" in detail_content
    assert "Month View" in detail_content
    assert "May 2027" in detail_content
    assert "Create Special Day" in detail_content

    update_response = client.post(
        f"/system/calendars/{yearly_calendar.id}/",
        data={
            "form_name": "general",
            "calendar_year": "2027",
            "calendar_name": "Delivery Calendar Updated",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    yearly_calendar.refresh_from_db()
    assert yearly_calendar.calendar_name == "Delivery Calendar Updated"
    assert yearly_calendar.status.value_code == "INACTIVE"

    filtered_response = client.get("/system/calendars/?status=ALL")

    assert filtered_response.status_code == 200
    filtered_content = filtered_response.content.decode()
    assert 'href="/system/calendars/?status=ALL"' in filtered_content


@pytest.mark.django_db
def test_calendar_detail_uses_standalone_edit_layout() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Layout Calendar",
    )

    response = client.get(f"/system/calendars/{yearly_calendar.id}/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Current State" not in content
    assert "Edit Calendar" in content
    assert "Delete Calendar" in content
    assert "Back to Calendars" in content
    assert "Year Summary" in content
    assert "Month View" in content
    assert 'class="detail-action-form"' in content


@pytest.mark.django_db
def test_calendar_management_rejects_second_calendar_for_same_office_year() -> None:
    client, _, business_units = _build_ts_admin_client()
    create_yearly_calendar(
        office=business_units[0].office,
        calendar_year=2027,
        calendar_name="First Office Calendar",
    )

    response = client.post(
        "/system/calendars/new/",
        data={
            "calendar_year": "2027",
            "calendar_name": "Second Office Calendar",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Only one yearly calendar can exist for the same year within the Office." in content
    assert (
        YearlyCalendar.objects.filter(
            office=business_units[0].office,
            calendar_year=2027,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_calendar_special_day_management_create_update_and_delete_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Holiday Calendar",
    )

    create_response = client.post(
        f"/system/calendars/{yearly_calendar.id}/special-days/new/",
        data={
            "special_date": date(2026, 5, 1).isoformat(),
            "day_type_code": "NATIONAL_HOLIDAY",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    special_day = yearly_calendar.special_days.get(special_date=date(2026, 5, 1))
    assert special_day.day_type.value_code == "NATIONAL_HOLIDAY"

    calendar_detail_response = client.get(f"/system/calendars/{yearly_calendar.id}/?month=5")

    assert calendar_detail_response.status_code == 200
    calendar_content = calendar_detail_response.content.decode()
    assert "National Holiday" in calendar_content
    assert "2026-05-01" in calendar_content
    assert f"/system/calendar-special-days/{special_day.id}/" in calendar_content

    update_response = client.post(
        f"/system/calendar-special-days/{special_day.id}/",
        data={
            "form_name": "edit",
            "special_date": date(2026, 5, 4).isoformat(),
            "day_type_code": "LOCAL_HOLIDAY",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    special_day.refresh_from_db()
    assert special_day.special_date == date(2026, 5, 4)
    assert special_day.day_type.value_code == "LOCAL_HOLIDAY"

    delete_response = client.post(
        f"/system/calendar-special-days/{special_day.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"] == f"/system/calendars/{yearly_calendar.id}/"
    assert yearly_calendar.special_days.filter(id=special_day.id).exists() is False


@pytest.mark.django_db
def test_calendar_special_day_create_rejects_dates_outside_the_calendar_year() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Year Bound Calendar",
    )

    response = client.post(
        f"/system/calendars/{yearly_calendar.id}/special-days/new/",
        data={
            "special_date": date(2027, 1, 1).isoformat(),
            "day_type_code": "OTHER",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Special day date must belong to the selected calendar year." in content
    assert yearly_calendar.special_days.exists() is False


@pytest.mark.django_db
def test_calendar_delete_is_blocked_when_special_days_still_reference_it() -> None:
    client, _, business_units = _build_ts_admin_client()
    yearly_calendar = create_yearly_calendar(
        business_unit=business_units[0],
        calendar_year=2026,
        calendar_name="Protected Calendar",
    )
    create_calendar_special_day(
        yearly_calendar=yearly_calendar,
        special_date=date(2026, 6, 15),
        day_type_code="TIMIA_DAY",
    )

    response = client.post(
        f"/system/calendars/{yearly_calendar.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Calendar" in content
    assert "Yearly calendar cannot be deleted because it is still referenced" in content
    assert YearlyCalendar.objects.filter(id=yearly_calendar.id).exists()


@pytest.mark.django_db
def test_country_master_management_create_and_update_via_html() -> None:
    client, _, _ = _build_ts_admin_master_client()

    collection_response = client.get("/system/countries/")
    collection_content = collection_response.content.decode()
    assert collection_response.status_code == 200
    assert "Current Records" not in collection_content
    assert 'href="/system/countries/new/"' in collection_content
    assert '<form class="form-stack" method="post" action="">' not in collection_content
    assert 'aria-label="Country Status"' in collection_content

    create_screen_response = client.get("/system/countries/new/")
    create_screen_content = create_screen_response.content.decode()
    assert create_screen_response.status_code == 200
    assert "Country Setup" in create_screen_content
    assert "Current State" not in create_screen_content
    assert 'name="form_name" value="create"' in create_screen_content
    assert 'name="country_code"' in create_screen_content

    create_response = client.post(
        "/system/countries/new/",
        data={
            "country_code": "CHL",
            "country_name": "Chile",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    country = Country.objects.get(country_code="CHL")

    update_response = client.post(
        f"/system/countries/{country.id}/",
        data={
            "form_name": "general",
            "country_code": "CHL-UPDATED",
            "country_name": "Chile Updated",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    country.refresh_from_db()
    assert country.country_code == "CHL-UPDATED"
    assert country.country_name == "Chile Updated"
    assert country.status.value_code == "INACTIVE"


@pytest.mark.django_db
def test_country_management_can_delete_unused_country_via_html() -> None:
    client, _, _ = _build_ts_admin_master_client()
    country = create_country(
        country_code="BRA",
        country_name="Brazil",
        active=True,
    )

    response = client.post(
        f"/system/countries/{country.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/countries/"
    assert not Country.objects.filter(id=country.id).exists()
    assert AuditLog.objects.filter(entity_name="country", entity_id=country.id).count() == 1


@pytest.mark.django_db
def test_country_management_delete_is_blocked_when_country_has_offices() -> None:
    client, _, _ = _build_ts_admin_master_client()
    country = create_country(
        country_code="URU",
        country_name="Uruguay",
        active=True,
    )
    create_office(office_name="Madrid", country=country, active=True)

    response = client.post(
        f"/system/countries/{country.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Country" in content
    assert "Country cannot be deleted because it is still referenced" in content
    assert Country.objects.filter(id=country.id).exists()


@pytest.mark.django_db
def test_office_management_create_and_update_via_html() -> None:
    client, _, _ = _build_ts_admin_master_client()
    country = create_country(
        country_code="PRT",
        country_name="Portugal",
        active=True,
    )

    collection_response = client.get("/system/offices/")
    collection_content = collection_response.content.decode()
    assert collection_response.status_code == 200
    assert "Employees" in collection_content
    assert "Current Records" not in collection_content
    assert 'href="/system/offices/new/"' in collection_content
    assert 'name="office_name"' not in collection_content

    create_screen_response = client.get("/system/offices/new/")
    create_screen_content = create_screen_response.content.decode()
    assert create_screen_response.status_code == 200
    assert "Office Setup" in create_screen_content
    assert "Current State" not in create_screen_content
    assert 'name="office_name"' in create_screen_content
    approval_mode_field = create_screen_content[
        create_screen_content.index('name="approval_mode_code"') : create_screen_content.index(
            'name="enable_copy_previous_week_flag"'
        )
    ]
    assert 'value="PROJECT"' in approval_mode_field
    assert 'value="LINE"' not in approval_mode_field
    assert 'value="MIXED"' not in approval_mode_field
    assert "Line and Mixed modes are reserved compatibility values" in create_screen_content
    assert create_screen_content.index('name="archive_after_years"') < (
        create_screen_content.index('name="timesheet_cutoff_date"')
    )
    assert create_screen_content.index('name="timesheet_cutoff_date"') < (
        create_screen_content.index('name="count_non_billable_in_daily_limit_flag"')
    )
    cutoff_field = create_screen_content[
        create_screen_content.index('name="timesheet_cutoff_date"') : create_screen_content.index(
            "Reserved date."
        )
    ]
    assert "disabled" in cutoff_field
    assert "muted-field" in create_screen_content
    assert 'name="count_non_billable_in_daily_limit_flag"' in create_screen_content
    non_billable_field = create_screen_content[
        create_screen_content.index(
            'name="count_non_billable_in_daily_limit_flag"'
        ) : create_screen_content.index("Reserved switch. Set to always count")
    ]
    assert "disabled" in non_billable_field
    assert "Reserved switch. Set to always count all charged time" in (create_screen_content)
    assert (
        "Reserved switch for future integration that imports leave/absence data "
        "into timesheet for this Office"
    ) in create_screen_content

    create_response = client.post(
        "/system/offices/new/",
        data={
            "country_id": str(country.id),
            "office_name": "Chile",
            "status_code": "ACTIVE",
            "bootstrap_bu_code": "CHI-ADMIN",
            "bootstrap_bu_name": "Chile Administration",
            "bootstrap_bu_description": "Starter BU for Chile Office",
            "bootstrap_admin_employee_code": "EMP-CHI-ADMIN-001",
            "bootstrap_admin_full_name": "Chile Office Admin",
            "bootstrap_admin_email": "chile.admin@example.com",
            "approval_mode_code": "LINE",
            "allow_employee_withdraw_flag": "on",
            "timesheet_cutoff_date": "2026-05-31",
            "count_non_billable_in_daily_limit_flag": "on",
            "archive_after_years": "7",
            "enable_timer_flag": "on",
            "enable_leave_integration_flag": "on",
            "enable_copy_previous_week_flag": "on",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    office = Office.objects.get(office_name="Chile")
    configuration = OfficeConfiguration.objects.get(office=office)
    bootstrap_business_unit = BusinessUnit.objects.get(bu_code="CHI-ADMIN")
    bootstrap_admin = Employee.objects.get(canonical_email="chile.admin@example.com")
    assert configuration.approval_mode.value_code == "PROJECT"
    assert configuration.allow_employee_withdraw_flag is True
    assert configuration.timesheet_cutoff_date is None
    assert configuration.count_non_billable_in_daily_limit_flag is False
    assert configuration.archive_after_years == 7
    assert configuration.enable_timer_flag is False
    assert configuration.enable_leave_integration_flag is False
    assert office.country_id == country.id
    assert bootstrap_business_unit.office_id == office.id
    assert bootstrap_business_unit.name == "Chile Administration"
    assert bootstrap_admin.office_id == office.id
    assert bootstrap_admin.primary_business_unit_id == bootstrap_business_unit.id
    assert EmployeeBusinessUnit.objects.filter(
        employee=bootstrap_admin,
        business_unit=bootstrap_business_unit,
        is_primary_flag=True,
        valid_to__isnull=True,
    ).exists()
    assert EmployeeRole.objects.filter(
        employee=bootstrap_admin,
        role__value_code="USER",
        valid_to__isnull=True,
    ).exists()
    assert EmployeeRole.objects.filter(
        employee=bootstrap_admin,
        role__value_code="TS_ADMIN",
        valid_to__isnull=True,
    ).exists()

    bootstrap_client = Client()
    initialize_ui_session(bootstrap_client, "chile.admin@example.com")
    bootstrap_system_response = bootstrap_client.get("/system/business-units/")
    assert bootstrap_system_response.status_code == 200
    assert "CHI-ADMIN" in bootstrap_system_response.content.decode()

    refreshed_collection_response = client.get("/system/offices/")
    refreshed_collection_content = refreshed_collection_response.content.decode()
    assert refreshed_collection_response.status_code == 200
    assert "Chile" in refreshed_collection_content
    assert re.search(r"Chile.*?>\s*1\s*<", refreshed_collection_content, re.S)

    office_detail_response = client.get(f"/system/offices/{office.id}/")
    office_detail_content = office_detail_response.content.decode()
    assert office_detail_response.status_code == 200
    assert "Current State" not in office_detail_content
    assert "Office Administrators" in office_detail_content
    assert "chile.admin@example.com" in office_detail_content
    assert "CHI-ADMIN" in office_detail_content

    update_response = client.post(
        f"/system/offices/{office.id}/",
        data={
            "form_name": "general",
            "country_id": str(country.id),
            "office_name": "Chile Updated",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    office.refresh_from_db()
    assert office.office_name == "Chile Updated"
    assert office.status.value_code == "INACTIVE"
    OfficeConfiguration.objects.filter(id=configuration.id).update(
        timesheet_cutoff_date=date(2026, 6, 30),
        count_non_billable_in_daily_limit_flag=True,
        enable_timer_flag=True,
        enable_leave_integration_flag=True,
    )
    configuration_update_response = client.post(
        f"/system/offices/{office.id}/",
        data={
            "form_name": "configuration",
            "approval_mode_code": "MIXED",
            "timesheet_cutoff_date": "2026-07-31",
            "count_non_billable_in_daily_limit_flag": "",
            "archive_after_years": "9",
            "enable_timer_flag": "",
            "enable_leave_integration_flag": "",
        },
        follow=False,
    )

    assert configuration_update_response.status_code == 302
    configuration.refresh_from_db()
    assert configuration.approval_mode.value_code == "PROJECT"
    assert configuration.archive_after_years == 9
    assert configuration.timesheet_cutoff_date == date(2026, 6, 30)
    assert configuration.count_non_billable_in_daily_limit_flag is True
    assert configuration.enable_timer_flag is True
    assert configuration.enable_leave_integration_flag is True
    assert AuditLog.objects.filter(entity_name="office", entity_id=office.id).count() == 3
    assert (
        AuditLog.objects.filter(
            entity_name="office_configuration",
            field_name="archive_after_years",
            entity_id=configuration.id,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_country_management_can_delete_unused_office_via_html() -> None:
    client, _, _ = _build_ts_admin_master_client()
    office = create_office(office_name="Delete Me", active=True)
    configuration = OfficeConfiguration.objects.get(office=office)

    response = client.post(
        f"/system/offices/{office.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/offices/"
    assert not Office.objects.filter(id=office.id).exists()
    assert not OfficeConfiguration.objects.filter(id=configuration.id).exists()
    assert AuditLog.objects.filter(entity_name="office", entity_id=office.id).count() == 1
    assert (
        AuditLog.objects.filter(
            entity_name="office_configuration",
            entity_id=configuration.id,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_office_management_can_delete_setup_only_current_office_via_html() -> None:
    seed_reference_data()
    country = create_country(country_code="ECU", country_name="Ecuador")
    office = create_office(office_name="Ecuador Office", country=country, active=True)
    business_unit = create_business_unit(
        bu_code="ECU-ADMIN",
        name="Ecuador Admin",
        office=office,
    )
    admin = create_employee(
        employee_code="EMP-ECU-ADMIN",
        full_name="Ecuador Office Admin",
        email="ecuador.admin@example.com",
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
    initialize_ui_session(client, admin.email)

    response = client.post(
        f"/system/offices/{office.id}/",
        data={"form_name": "delete"},
        follow=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/system/offices/"
    assert not Office.objects.filter(id=office.id).exists()
    assert not OfficeConfiguration.objects.filter(office_id=office.id).exists()
    assert not Employee.objects.filter(id=admin.id).exists()
    assert not BusinessUnit.objects.filter(id=business_unit.id).exists()
    assert AuditLog.objects.filter(
        entity_name="office",
        entity_id=office.id,
        action_type__value_code="DELETE",
        actor_email=admin.email,
        actor_employee_id__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_country_management_delete_is_blocked_when_office_has_business_units() -> None:
    client, _, _ = _build_ts_admin_master_client()
    office = create_office(office_name="Used Office", active=True)
    create_business_unit(
        bu_code="BU-USED-OFFICE",
        name="Used Office BU",
        office=office,
    )

    response = client.post(
        f"/system/offices/{office.id}/",
        data={
            "form_name": "delete",
        },
        follow=False,
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Delete Office" in content
    assert "Office cannot be deleted because it is still referenced" in content
    assert Office.objects.filter(id=office.id).exists()


@pytest.mark.django_db
def test_country_management_all_filter_shows_active_and_inactive_records() -> None:
    client, _, _ = _build_ts_admin_master_client()
    active_country = create_office(office_name="Uruguay", active=True)
    inactive_country = create_office(office_name="Brazil", active=False)

    response = client.get("/system/offices/?status=ALL")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'href="/system/offices/?status=ALL"' in content
    assert f"/system/offices/{active_country.id}/" in content
    assert f"/system/offices/{inactive_country.id}/" in content
