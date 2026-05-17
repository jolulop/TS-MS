import pytest
from django.test import Client

from tests.helpers import (
    assign_employee_to_business_unit,
    assign_role,
    create_business_unit,
    create_employee,
    initialize_ui_session,
    seed_reference_data,
)


@pytest.mark.django_db
def test_access_entry_page_is_shown_for_unauthenticated_user() -> None:
    client = Client()
    response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Access Entry" in content
    assert "Initialize Session" in content


@pytest.mark.django_db
def test_user_dashboard_hides_system_and_approval_navigation() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-UI-1", name="UI BU 1")
    employee = create_employee(
        employee_code="EMP-UI-1",
        full_name="UI User",
        email="ui-user@example.com",
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
    response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "My info" in content
    assert "TS/Project Management" in content
    assert "Profile" in content
    assert "Dashboard" in content
    assert "My Timesheets" in content
    assert "/ts/projects/" not in content
    assert "Reports" in content
    assert "My History" not in content
    assert "System Management" not in content
    assert "Approval Worklist" not in content


@pytest.mark.django_db
def test_project_owner_sees_project_management_and_approval_worklist() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-UI-2", name="UI BU 2")
    employee = create_employee(
        employee_code="EMP-UI-2",
        full_name="Project Owner User",
        email="project-owner@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="PROJECT_OWNER")

    client = Client()
    initialize_ui_session(client, employee.email)

    dashboard_response = client.get("/")
    system_response = client.get("/system/")
    project_management_response = client.get("/ts/projects/")
    approval_response = client.get("/approvals/")

    dashboard_content = dashboard_response.content.decode()
    assert dashboard_response.status_code == 200
    assert "System Management" in dashboard_content
    assert '/ts/projects/' in dashboard_content
    assert system_response.status_code == 200
    assert "Project Management" in system_response.content.decode()
    assert project_management_response.status_code == 200
    assert "Project Summary" in project_management_response.content.decode()
    assert approval_response.status_code == 200
    assert "Approval Worklist" in approval_response.content.decode()


@pytest.mark.django_db
def test_project_manager_sees_approval_worklist_and_profile_context() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-UI-3", name="UI BU 3")
    employee = create_employee(
        employee_code="EMP-UI-3",
        full_name="Project Manager User",
        email="project-manager@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="PROJECT_MANAGER")

    client = Client()
    initialize_ui_session(client, employee.email)

    dashboard_response = client.get("/")
    profile_response = client.get("/profile/")
    approval_response = client.get("/approvals/")
    inquiry_response = client.get("/ts/inquiry/")

    dashboard_content = dashboard_response.content.decode()
    profile_content = profile_response.content.decode()

    assert dashboard_response.status_code == 200
    assert "My info" in dashboard_content
    assert "TS/Project Management" in dashboard_content
    assert '/ts/projects/' in dashboard_content
    assert "Approval Worklist" in dashboard_content
    assert "Project Time Inquiry" in dashboard_content
    assert "System Management" not in dashboard_content
    assert profile_response.status_code == 200
    assert "Profile" in profile_content
    assert "Project Manager User" in profile_content
    assert "Active Office" in profile_content
    assert "Holding" in profile_content
    assert "PROJECT_MANAGER" in profile_content
    assert approval_response.status_code == 200
    assert "Pending Approval Items" in approval_response.content.decode()
    assert inquiry_response.status_code == 200
    assert "Project Time Inquiry" in inquiry_response.content.decode()


@pytest.mark.django_db
def test_ts_admin_can_open_system_management_and_reports() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-UI-4", name="UI BU 4")
    employee = create_employee(
        employee_code="EMP-UI-4",
        full_name="Admin User",
        email="ts-admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="TS_ADMIN")

    client = Client()
    initialize_ui_session(client, employee.email)

    dashboard_response = client.get("/")
    system_response = client.get("/system/")
    reports_response = client.get("/reports/")

    dashboard_content = dashboard_response.content.decode()
    assert dashboard_response.status_code == 200
    assert "Office: Holding" in dashboard_content
    assert "fixed to Holding" in dashboard_content
    assert '/ts/projects/' in dashboard_content
    assert "System Management" in dashboard_content
    assert system_response.status_code == 200
    assert "Business Units" in system_response.content.decode()
    assert "Employees" in system_response.content.decode()
    assert reports_response.status_code == 200
    assert "Available Reports" in reports_response.content.decode()


@pytest.mark.django_db
def test_ts_admin_master_sees_country_management_only() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-UI-5", name="UI BU 5")
    employee = create_employee(
        employee_code="EMP-UI-5",
        full_name="Master Admin User",
        email="ts-admin-master@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="TS_ADMIN_MASTER")

    client = Client()
    initialize_ui_session(client, employee.email)

    dashboard_response = client.get("/")
    system_response = client.get("/system/")
    countries_response = client.get("/system/countries/")
    offices_response = client.get("/system/offices/")
    employees_response = client.get("/system/employees/")

    dashboard_content = dashboard_response.content.decode()
    system_content = system_response.content.decode()

    assert dashboard_response.status_code == 200
    assert "System Management" in dashboard_content
    assert "Countries" in dashboard_content
    assert "Offices" in dashboard_content
    assert "Employees" not in dashboard_content
    assert system_response.status_code == 200
    assert "Countries" in system_content
    assert "Offices" in system_content
    assert "Employees" not in system_content
    assert countries_response.status_code == 200
    assert "Country Management" in countries_response.content.decode()
    assert offices_response.status_code == 200
    assert "Office Management" in offices_response.content.decode()
    assert employees_response.status_code == 403
    assert "Access Denied" in employees_response.content.decode()


@pytest.mark.django_db
def test_ts_admin_navigation_includes_pricing_models_link() -> None:
    seed_reference_data()
    business_unit = create_business_unit(bu_code="BU-UI-PRC", name="UI Pricing BU")
    employee = create_employee(
        employee_code="EMP-UI-PRC",
        full_name="Pricing Admin User",
        email="pricing-admin@example.com",
        primary_business_unit=business_unit,
    )
    assign_employee_to_business_unit(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=True,
    )
    assign_role(employee=employee, role_code="USER")
    assign_role(employee=employee, role_code="TS_ADMIN")

    client = Client()
    initialize_ui_session(client, employee.email)

    response = client.get("/")
    system_group = next(
        group
        for group in response.context["navigation_groups"]
        if group.label == "System Management"
    )
    navigation_labels = [group.label for group in response.context["navigation_groups"]]

    assert response.status_code == 200
    assert navigation_labels == ["My info", "TS/Project Management", "System Management"]
    assert "/system/pricing-models/" in response.content.decode()
    assert [item.label for item in system_group.items] == [
        "System Management",
        "Employees",
        "Clients",
        "Projects",
        "Project Assignments",
        "Internal Categories",
        "Cost Centers",
        "Pricing Models",
        "Business Units",
        "Calendars",
        "Calendar Period Rules",
        "GCC Approval Roles",
        "General Charge Codes",
    ]
