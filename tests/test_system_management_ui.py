from datetime import date

import pytest
from django.test import Client

from apps.audit.models import AuditLog
from apps.master_data.models import (
    BusinessUnit,
    BusinessUnitConfiguration,
    CalendarPeriodRule,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    Office,
    Project,
    ProjectAssignment,
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
from tests.helpers import (
    assign_calendar,
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_business_unit_configuration,
    create_calendar_period_rule,
    create_client,
    create_cost_center,
    create_employee,
    create_internal_category,
    create_office,
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


def _build_project_management_context(
    business_unit,
) -> tuple[Employee, Employee, ClientRecord, InternalCategoryRecord, CostCenterRecord]:
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
    return project_owner, project_manager, client, category, cost_center


@pytest.mark.django_db
def test_system_management_hub_shows_real_admin_screen_links() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Ready now" in content
    assert "/system/business-units/" in content
    assert "/system/employees/" in content
    assert "/system/clients/" in content
    assert "/system/general-charge-codes/" in content
    assert "/system/projects/" in content
    assert "/system/project-assignments/" in content
    assert "/system/calendar-period-rules/" in content


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

    configuration_response = client.post(
        f"/system/business-units/{managed_business_unit.id}/",
        data={
            "form_name": "configuration",
            "approval_mode_code": "PROJECT",
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

    assert configuration_response.status_code == 302
    configuration = BusinessUnitConfiguration.objects.get(business_unit=managed_business_unit)
    assert configuration.approval_mode.value_code == "PROJECT"
    assert configuration.allow_employee_withdraw_flag is True
    assert configuration.timesheet_cutoff_date == date(2026, 5, 31)
    assert configuration.count_non_billable_in_daily_limit_flag is True
    assert configuration.archive_after_years == 7
    assert configuration.enable_timer_flag is True
    assert configuration.enable_leave_integration_flag is True
    assert configuration.enable_copy_previous_week_flag is True

    detail_response = client.get(f"/system/business-units/{managed_business_unit.id}/")
    detail_content = detail_response.content.decode()
    assert detail_response.status_code == 200
    assert "Configuration" in detail_content
    assert "Back to Business Units" in detail_content
    assert "System BU 1 Updated" in detail_content
    assert "Defines how submitted time is routed for approval." in detail_content


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
def test_ts_admin_cannot_open_country_management_screen() -> None:
    client, _, _ = _build_ts_admin_client()

    response = client.get("/system/offices/")

    assert response.status_code == 403
    assert "Access Denied" in response.content.decode()


@pytest.mark.django_db
def test_employee_management_create_and_update_flows_render_through_html() -> None:
    client, _, business_units = _build_ts_admin_client()
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
        "/system/employees/",
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
            "business_unit_id": str(business_units[0].id),
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

    collection_response = client.get("/system/clients/")
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
    client, _, business_units = _build_ts_admin_client()
    holding_country = get_office()
    holding_country.status = ref_value("COUNTRY_STATUS", "INACTIVE")
    holding_country.save(update_fields=["status", "updated_at"])

    response = client.post(
        "/system/clients/",
        data={
            "business_unit_id": str(business_units[0].id),
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
            "business_unit_id": str(business_units[0].id),
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


@pytest.mark.django_db
def test_general_charge_code_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()

    create_response = client.post(
        "/system/general-charge-codes/",
        data={
            "business_unit_id": str(business_units[0].id),
            "code": "GCC-NEW",
            "name": "New General Charge Code",
            "charge_type_code": "STANDARD",
            "billable_flag": "on",
            "common_code_flag": "on",
            "valid_from": date(2026, 4, 1).isoformat(),
            "valid_to": date(2026, 12, 31).isoformat(),
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    general_charge_code = GeneralChargeCodeRecord.objects.get(code="GCC-NEW")
    assert general_charge_code.billable_flag is True
    assert general_charge_code.common_code_flag is True

    update_response = client.post(
        f"/system/general-charge-codes/{general_charge_code.id}/",
        data={
            "code": "GCC-UPDATED",
            "name": "Updated General Charge Code",
            "charge_type_code": "STANDARD",
            "requires_approval_flag": "on",
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
    assert general_charge_code.requires_approval_flag is True
    assert general_charge_code.description_required_flag is True
    assert general_charge_code.valid_to is None
    assert general_charge_code.status.value_code == "INACTIVE"


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
def test_project_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center = (
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
def test_project_assignment_management_create_and_update_via_html() -> None:
    client, _, business_units = _build_ts_admin_client()
    project_owner, project_manager, project_client, category, cost_center = (
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
        primary_business_unit=foreign_business_unit,
    )
    assign_employee_to_business_unit(
        employee=assigned_employee,
        business_unit=foreign_business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=assigned_employee, role_code="USER")
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

    collection_response = client.get("/system/project-assignments/")
    assert collection_response.status_code == 200
    assert "EMP-ASSIGN-1" in collection_response.content.decode()

    create_response = client.post(
        "/system/project-assignments/",
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

    update_response = client.post(
        f"/system/project-assignments/{assignment.id}/",
        data={
            "assignment_start_date": date(2026, 4, 7).isoformat(),
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

    create_response = client.post(
        "/system/calendar-period-rules/",
        data={
            "yearly_calendar_id": str(yearly_calendar.id),
            "effective_from": date(2026, 1, 1).isoformat(),
            "effective_to": date(2026, 3, 31).isoformat(),
            "monday_max_hours": "8.00",
            "tuesday_max_hours": "8.00",
            "wednesday_max_hours": "8.00",
            "thursday_max_hours": "8.00",
            "friday_max_hours": "6.00",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    period_rule = CalendarPeriodRule.objects.get(
        yearly_calendar=yearly_calendar,
        effective_from=date(2026, 1, 1),
    )

    update_response = client.post(
        f"/system/calendar-period-rules/{period_rule.id}/",
        data={
            "effective_from": date(2026, 1, 1).isoformat(),
            "effective_to": date(2026, 4, 30).isoformat(),
            "monday_max_hours": "7.50",
            "tuesday_max_hours": "7.50",
            "wednesday_max_hours": "7.50",
            "thursday_max_hours": "7.50",
            "friday_max_hours": "6.00",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    period_rule.refresh_from_db()
    assert period_rule.effective_to == date(2026, 4, 30)
    assert str(period_rule.monday_max_hours) == "7.50"
    assert period_rule.status.value_code == "INACTIVE"


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
def test_country_management_create_and_update_via_html() -> None:
    client, _, _ = _build_ts_admin_master_client()

    create_response = client.post(
        "/system/offices/",
        data={
            "office_name": "Chile",
            "status_code": "ACTIVE",
        },
        follow=False,
    )

    assert create_response.status_code == 302
    country = Office.objects.get(office_name="Chile")

    update_response = client.post(
        f"/system/offices/{country.id}/",
        data={
            "office_name": "Chile Updated",
            "status_code": "INACTIVE",
        },
        follow=False,
    )

    assert update_response.status_code == 302
    country.refresh_from_db()
    assert country.office_name == "Chile Updated"
    assert country.status.value_code == "INACTIVE"
    assert AuditLog.objects.filter(entity_name="office", entity_id=country.id).count() == 3


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
