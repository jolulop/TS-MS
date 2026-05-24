import json
import logging
from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.common.logging import JsonLogFormatter
from apps.master_data.models import Employee
from apps.timesheets.services import TimesheetService
from tests.helpers import (
    assign_calendar,
    assign_employee_to_business_unit,
    assign_role,
    create_employee,
)
from tests.test_reports_ui import _setup_reports_context


@pytest.mark.django_db
def test_phase8_key_pages_have_query_count_guardrails() -> None:
    context = _setup_reports_context()
    employee_id = Employee.objects.get(employee_code="EMP-RPT-USER").id

    page_checks = (
        (context["user_client"], "/ts/", {}, 80),
        (context["pm_client"], "/approvals/", {}, 90),
        (context["owner_client"], "/reports/project-time/", {}, 90),
        (context["admin_client"], "/reports/office-bu-time-summary/", {}, 90),
        (
            context["admin_client"],
            "/reports/employee-utilization/",
            {"employee_id": str(employee_id)},
            90,
        ),
    )

    for client, path, query_params, max_queries in page_checks:
        with CaptureQueriesContext(connection) as captured_queries:
            response = client.get(path, data=query_params)

        assert response.status_code == 200
        assert len(captured_queries) <= max_queries, (
            f"{path} used {len(captured_queries)} queries; expected at most {max_queries}."
        )


@pytest.mark.django_db
def test_employee_utilization_expected_capacity_uses_bulk_calendar_lookup() -> None:
    context = _setup_reports_context()
    business_unit = context["project"].business_unit
    calendar = Employee.objects.get(employee_code="EMP-RPT-USER").assigned_calendar
    for index in range(5):
        employee = create_employee(
            employee_code=f"EMP-RPT-PERF-{index}",
            full_name=f"Reports Performance {index}",
            email=f"reports-performance-{index}@example.com",
            primary_business_unit=business_unit,
        )
        assign_calendar(employee=employee, yearly_calendar=calendar)
        assign_employee_to_business_unit(
            employee=employee,
            business_unit=business_unit,
            is_primary_flag=True,
        )
        assign_role(employee=employee, role_code="USER")

    employees = list(
        Employee.objects.filter(
            primary_business_unit=business_unit,
            status__value_code="ACTIVE",
        ).order_by("employee_code")
    )

    with CaptureQueriesContext(connection) as captured_queries:
        expected_hours = TimesheetService.expected_capacity_hours_by_employee(
            employees,
            date(2026, 5, 1),
            date(2026, 5, 31),
        )

    assert expected_hours
    assert all(hours >= 0 for hours in expected_hours.values())
    assert len(captured_queries) <= 2


def test_structured_observability_formatter_outputs_json_fields() -> None:
    record = logging.LogRecord(
        name="tsms.observability",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="report_export",
        args=(),
        exc_info=None,
    )
    record.event = "report_export"
    record.report_code = "employee-utilization"
    record.actor_email = "reports-admin@example.com"
    record.row_count = 3

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event"] == "report_export"
    assert payload["report_code"] == "employee-utilization"
    assert payload["actor_email"] == "reports-admin@example.com"
    assert payload["row_count"] == 3
