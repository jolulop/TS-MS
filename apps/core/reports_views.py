from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.audit.models import AuditLog
from apps.auth.context import CurrentUser
from apps.auth.policies import AuthorizationPolicyService
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.integrations.models import IntegrationJob
from apps.master_data.models import Employee, Project
from apps.timesheets.models import ApprovalItem, TimesheetLine, WeeklyTimesheet


@dataclass(frozen=True)
class ReportDefinition:
    code: str
    title: str
    summary: str
    audience: str


REPORT_DEFINITIONS = {
    "my-timesheet-history": ReportDefinition(
        code="my-timesheet-history",
        title="My Timesheet History",
        summary="Read-only history of your own weekly timesheets across lifecycle states.",
        audience="All authenticated users",
    ),
    "project-time": ReportDefinition(
        code="project-time",
        title="Project Time Report",
        summary="Scoped project-charged time lines for owned, managed, or administrated projects.",
        audience="PROJECT_OWNER, PROJECT_MANAGER, TS_ADMIN",
    ),
    "pending-approvals": ReportDefinition(
        code="pending-approvals",
        title="Pending Approvals",
        summary="Pending approval items within the current managed-project or TS admin scope.",
        audience="PROJECT_MANAGER, TS_ADMIN",
    ),
    "missing-timesheets": ReportDefinition(
        code="missing-timesheets",
        title="Missing Timesheets",
        summary=(
            "Active employees in scope who do not have a weekly timesheet for the selected week."
        ),
        audience="TS_ADMIN",
    ),
    "archived-timesheets": ReportDefinition(
        code="archived-timesheets",
        title="Archived Timesheets",
        summary="Archived weekly timesheets visible inside the current Business Unit scope.",
        audience="TS_ADMIN",
    ),
    "audit-history": ReportDefinition(
        code="audit-history",
        title="Audit History",
        summary="Searchable audit trail for sensitive actions in the current Business Unit scope.",
        audience="TS_ADMIN",
    ),
    "integration-jobs": ReportDefinition(
        code="integration-jobs",
        title="Integration Jobs",
        summary="Import, export, and sync job history within the current Business Unit scope.",
        audience="TS_ADMIN",
    ),
}


def _reports_context(
    request: HttpRequest,
    *,
    title: str,
    eyebrow: str,
    intro: str,
) -> dict:
    return _page_context(
        request,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )


def _current_monday(today: date | None = None) -> date:
    current_date = today or date.today()
    return current_date - timedelta(days=current_date.weekday())


def _parse_date_query(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _date_display(value) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _report_url(report_code: str) -> str:
    return f"/reports/{report_code}/"


def _scoped_project_queryset(current_user: CurrentUser):
    queryset = Project.objects.select_related(
        "business_unit", "project_owner_employee", "project_manager_employee"
    )
    if current_user.is_ts_admin:
        return queryset.filter(business_unit_id__in=current_user.scoped_business_unit_ids)

    project_scope = Q()
    if current_user.has_role("PROJECT_OWNER"):
        project_scope |= Q(project_owner_employee_id=current_user.employee_id)
    if current_user.has_role("PROJECT_MANAGER"):
        project_scope |= Q(project_manager_employee_id=current_user.employee_id)
    return queryset.filter(project_scope)


def _scoped_project_ids(current_user: CurrentUser) -> list[int]:
    return list(_scoped_project_queryset(current_user).values_list("id", flat=True))


def _report_count(current_user: CurrentUser, report_code: str) -> int:
    if report_code == "my-timesheet-history":
        return WeeklyTimesheet.objects.filter(employee_id=current_user.employee_id).count()
    if report_code == "project-time":
        return TimesheetLine.objects.filter(
            project_id__in=_scoped_project_ids(current_user)
        ).count()
    if report_code == "pending-approvals":
        if current_user.is_ts_admin:
            return ApprovalItem.objects.filter(
                submission_cycle__weekly_timesheet__business_unit_id__in=current_user.scoped_business_unit_ids,
                status__value_code="PENDING",
            ).count()
        return ApprovalItem.objects.filter(
            Q(approver_employee_id=current_user.employee_id)
            | Q(project__project_manager_employee_id=current_user.employee_id),
            status__value_code="PENDING",
        ).count()
    if report_code == "missing-timesheets":
        week_start_date = _current_monday()
        employees = Employee.objects.filter(
            status__value_code="ACTIVE",
            primary_business_unit_id__in=current_user.scoped_business_unit_ids,
        )
        return (
            employees.exclude(weekly_timesheets__week_start_date=week_start_date).distinct().count()
        )
    if report_code == "archived-timesheets":
        return WeeklyTimesheet.objects.filter(
            business_unit_id__in=current_user.scoped_business_unit_ids,
            status__value_code="ARCHIVED",
        ).count()
    if report_code == "audit-history":
        return AuditLog.objects.filter(
            business_unit_id__in=current_user.scoped_business_unit_ids
        ).count()
    if report_code == "integration-jobs":
        return IntegrationJob.objects.filter(
            business_unit_id__in=current_user.scoped_business_unit_ids
        ).count()
    return 0


def _report_cards(current_user: CurrentUser) -> list[dict]:
    cards = []
    for report_code, definition in REPORT_DEFINITIONS.items():
        if not AuthorizationPolicyService.can_run_report(current_user, report_code):
            continue
        cards.append(
            {
                "title": definition.title,
                "summary": definition.summary,
                "audience": definition.audience,
                "count": _report_count(current_user, report_code),
                "href": _report_url(report_code),
            }
        )
    return cards


def _bu_filter_options(current_user: CurrentUser) -> list[dict]:
    return [
        {"value": str(unit.id), "label": f"{unit.bu_code} - {unit.name}"}
        for unit in current_user.scoped_business_units
    ]


def _project_filter_options(current_user: CurrentUser) -> list[dict]:
    return [
        {
            "value": str(project.id),
            "label": f"{project.project_code} - {project.name}",
        }
        for project in _scoped_project_queryset(current_user).order_by("project_code")
    ]


def _employee_filter_options(
    current_user: CurrentUser, *, project_scoped: bool = False
) -> list[dict]:
    queryset = Employee.objects.select_related("primary_business_unit")
    if project_scoped:
        queryset = queryset.filter(
            weekly_timesheets__lines__project_id__in=_scoped_project_ids(current_user)
        )
    elif current_user.is_ts_admin:
        queryset = queryset.filter(
            primary_business_unit_id__in=current_user.scoped_business_unit_ids
        )
    else:
        queryset = queryset.filter(id=current_user.employee_id)
    return [
        {
            "value": str(employee.id),
            "label": f"{employee.employee_code} - {employee.full_name}",
        }
        for employee in queryset.distinct().order_by("employee_code")
    ]


def _status_filter_options(queryset, *, related_field: str = "status__value_code") -> list[dict]:
    return [
        {"value": value, "label": value}
        for value in queryset.order_by(related_field)
        .values_list(related_field, flat=True)
        .distinct()
        if value
    ]


def _selected_value(request: HttpRequest, name: str) -> str:
    return request.GET.get(name, "").strip()


def _common_filter_fields(current_user: CurrentUser, *, include_bu: bool = False) -> list[dict]:
    fields: list[dict] = []
    if include_bu and current_user.is_ts_admin and len(current_user.scoped_business_units) > 1:
        fields.append(
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": _selected_value(current_user.request, "business_unit_id"),  # type: ignore[attr-defined]
                "options": _bu_filter_options(current_user),
            }
        )
    return fields


def _my_timesheet_history_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    queryset = WeeklyTimesheet.objects.filter(employee_id=current_user.employee_id).select_related(
        "status"
    )
    status_code = _selected_value(request, "status")
    week_start_from = _selected_value(request, "week_start_from")
    week_start_to = _selected_value(request, "week_start_to")

    if status_code:
        queryset = queryset.filter(status__value_code=status_code)
    parsed_start = _parse_date_query(week_start_from)
    parsed_end = _parse_date_query(week_start_to)
    if parsed_start is not None:
        queryset = queryset.filter(week_start_date__gte=parsed_start)
    if parsed_end is not None:
        queryset = queryset.filter(week_start_date__lte=parsed_end)

    rows = [
        [
            item.week_start_date.isoformat(),
            item.week_end_date.isoformat(),
            item.status.value_code,
            str(item.current_submission_no),
            _date_display(item.submission_datetime),
            _date_display(item.final_approval_datetime),
        ]
        for item in queryset.order_by("-week_start_date")
    ]
    return {
        "definition": REPORT_DEFINITIONS["my-timesheet-history"],
        "filters": [
            {
                "label": "Status",
                "name": "status",
                "type": "select",
                "value": status_code,
                "options": _status_filter_options(
                    WeeklyTimesheet.objects.filter(employee_id=current_user.employee_id)
                ),
            },
            {
                "label": "Week Start From",
                "name": "week_start_from",
                "type": "date",
                "value": week_start_from,
            },
            {
                "label": "Week Start To",
                "name": "week_start_to",
                "type": "date",
                "value": week_start_to,
            },
        ],
        "headers": (
            "Week Start",
            "Week End",
            "Status",
            "Submission No.",
            "Submitted At",
            "Approved At",
        ),
        "rows": rows,
        "totals": [
            {"label": "Weeks Returned", "value": str(len(rows))},
        ],
        "empty_message": "No timesheet history matches the current filters.",
    }


def _project_time_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    queryset = (
        TimesheetLine.objects.select_related(
            "weekly_timesheet",
            "weekly_timesheet__employee",
            "weekly_timesheet__business_unit",
            "project",
            "approval_state",
        )
        .filter(project_id__in=_scoped_project_ids(current_user))
        .order_by("-work_date", "weekly_timesheet__employee__employee_code", "id")
    )

    business_unit_id = _selected_value(request, "business_unit_id")
    project_id = _selected_value(request, "project_id")
    employee_id = _selected_value(request, "employee_id")
    work_date_from = _selected_value(request, "work_date_from")
    work_date_to = _selected_value(request, "work_date_to")

    if business_unit_id and current_user.is_ts_admin:
        queryset = queryset.filter(weekly_timesheet__business_unit_id=business_unit_id)
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    if employee_id:
        queryset = queryset.filter(weekly_timesheet__employee_id=employee_id)
    parsed_start = _parse_date_query(work_date_from)
    parsed_end = _parse_date_query(work_date_to)
    if parsed_start is not None:
        queryset = queryset.filter(work_date__gte=parsed_start)
    if parsed_end is not None:
        queryset = queryset.filter(work_date__lte=parsed_end)

    rows = [
        [
            line.work_date.isoformat(),
            line.weekly_timesheet.employee.employee_code,
            line.weekly_timesheet.employee.full_name,
            line.project.project_code if line.project else "",
            line.project.name if line.project else "",
            line.weekly_timesheet.business_unit.bu_code,
            line.weekly_timesheet.week_start_date.isoformat(),
            str(line.hours),
            "Billable" if line.billable_flag else "Non-billable",
            line.approval_state.value_code if line.approval_state_id else "Not routed",
            line.comment_text or "",
        ]
        for line in queryset
    ]
    totals = queryset.aggregate(
        total_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
    )
    return {
        "definition": REPORT_DEFINITIONS["project-time"],
        "filters": [
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if current_user.is_ts_admin and len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "Project",
                "name": "project_id",
                "type": "select",
                "value": project_id,
                "options": _project_filter_options(current_user),
            },
            {
                "label": "Employee",
                "name": "employee_id",
                "type": "select",
                "value": employee_id,
                "options": _employee_filter_options(current_user, project_scoped=True),
            },
            {
                "label": "Work Date From",
                "name": "work_date_from",
                "type": "date",
                "value": work_date_from,
            },
            {
                "label": "Work Date To",
                "name": "work_date_to",
                "type": "date",
                "value": work_date_to,
            },
        ],
        "headers": (
            "Work Date",
            "Employee Code",
            "Employee",
            "Project Code",
            "Project",
            "BU",
            "Week Start",
            "Hours",
            "Billable",
            "Approval State",
            "Comment",
        ),
        "rows": rows,
        "totals": [
            {"label": "Lines Returned", "value": str(len(rows))},
            {"label": "Total Hours", "value": str(totals["total_hours"] or Decimal("0.00"))},
            {"label": "Billable Hours", "value": str(totals["billable_hours"] or Decimal("0.00"))},
            {
                "label": "Non-billable Hours",
                "value": str(totals["non_billable_hours"] or Decimal("0.00")),
            },
        ],
        "empty_message": "No project time lines match the current filters.",
    }


def _pending_approvals_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    queryset = ApprovalItem.objects.select_related(
        "status",
        "project",
        "approver_employee",
        "submission_cycle",
        "submission_cycle__weekly_timesheet",
        "submission_cycle__weekly_timesheet__employee",
        "submission_cycle__weekly_timesheet__business_unit",
    ).filter(status__value_code="PENDING")
    if current_user.is_ts_admin:
        queryset = queryset.filter(
            submission_cycle__weekly_timesheet__business_unit_id__in=current_user.scoped_business_unit_ids
        )
    else:
        queryset = queryset.filter(
            Q(approver_employee_id=current_user.employee_id)
            | Q(project__project_manager_employee_id=current_user.employee_id)
        )

    business_unit_id = _selected_value(request, "business_unit_id")
    project_id = _selected_value(request, "project_id")
    employee_id = _selected_value(request, "employee_id")

    if business_unit_id and current_user.is_ts_admin:
        queryset = queryset.filter(
            submission_cycle__weekly_timesheet__business_unit_id=business_unit_id
        )
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    if employee_id:
        queryset = queryset.filter(submission_cycle__weekly_timesheet__employee_id=employee_id)

    rows = [
        [
            str(item.id),
            item.submission_cycle.weekly_timesheet.employee.employee_code,
            item.submission_cycle.weekly_timesheet.employee.full_name,
            item.project.project_code if item.project else "",
            item.project.name if item.project else "",
            item.submission_cycle.weekly_timesheet.business_unit.bu_code,
            str(item.submission_cycle.submission_no),
            item.status.value_code,
        ]
        for item in queryset.order_by("submission_cycle__weekly_timesheet__week_start_date", "id")
    ]
    return {
        "definition": REPORT_DEFINITIONS["pending-approvals"],
        "filters": [
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if current_user.is_ts_admin and len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "Project",
                "name": "project_id",
                "type": "select",
                "value": project_id,
                "options": _project_filter_options(current_user),
            },
            {
                "label": "Employee",
                "name": "employee_id",
                "type": "select",
                "value": employee_id,
                "options": _employee_filter_options(current_user, project_scoped=True),
            },
        ],
        "headers": (
            "Approval Item",
            "Employee Code",
            "Employee",
            "Project Code",
            "Project",
            "BU",
            "Submission No.",
            "Status",
        ),
        "rows": rows,
        "totals": [
            {"label": "Pending Items", "value": str(len(rows))},
        ],
        "empty_message": "No pending approval items match the current filters.",
    }


def _missing_timesheets_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    week_start_date_value = (
        _selected_value(request, "week_start_date") or _current_monday().isoformat()
    )
    business_unit_id = _selected_value(request, "business_unit_id")
    week_start_date = _parse_date_query(week_start_date_value) or _current_monday()

    employee_queryset = Employee.objects.select_related("primary_business_unit").filter(
        status__value_code="ACTIVE",
        primary_business_unit_id__in=current_user.scoped_business_unit_ids,
    )
    if business_unit_id:
        employee_queryset = employee_queryset.filter(primary_business_unit_id=business_unit_id)

    employees = employee_queryset.exclude(
        weekly_timesheets__week_start_date=week_start_date
    ).order_by(
        "primary_business_unit__bu_code",
        "employee_code",
    )
    rows = [
        [
            employee.primary_business_unit.bu_code,
            employee.employee_code,
            employee.full_name,
            week_start_date.isoformat(),
            "Missing",
        ]
        for employee in employees.distinct()
    ]
    return {
        "definition": REPORT_DEFINITIONS["missing-timesheets"],
        "filters": [
            {
                "label": "Week Start Date",
                "name": "week_start_date",
                "type": "date",
                "value": week_start_date.isoformat(),
            },
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if len(current_user.scoped_business_units) > 1
            else None,
        ],
        "headers": (
            "BU",
            "Employee Code",
            "Employee",
            "Week Start",
            "Status",
        ),
        "rows": rows,
        "totals": [
            {"label": "Employees Missing Timesheets", "value": str(len(rows))},
        ],
        "empty_message": "Every active employee in scope has a timesheet for the selected week.",
    }


def _archived_timesheets_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    employee_id = _selected_value(request, "employee_id")
    week_start_from = _selected_value(request, "week_start_from")
    week_start_to = _selected_value(request, "week_start_to")

    queryset = WeeklyTimesheet.objects.select_related(
        "employee",
        "business_unit",
        "status",
    ).filter(
        business_unit_id__in=current_user.scoped_business_unit_ids,
        status__value_code="ARCHIVED",
    )
    if business_unit_id:
        queryset = queryset.filter(business_unit_id=business_unit_id)
    if employee_id:
        queryset = queryset.filter(employee_id=employee_id)
    parsed_start = _parse_date_query(week_start_from)
    parsed_end = _parse_date_query(week_start_to)
    if parsed_start is not None:
        queryset = queryset.filter(week_start_date__gte=parsed_start)
    if parsed_end is not None:
        queryset = queryset.filter(week_start_date__lte=parsed_end)

    rows = [
        [
            item.business_unit.bu_code,
            item.employee.employee_code,
            item.employee.full_name,
            item.week_start_date.isoformat(),
            item.week_end_date.isoformat(),
            item.status.value_code,
            _date_display(item.archive_eligible_date),
        ]
        for item in queryset.order_by("-week_start_date", "employee__employee_code")
    ]
    return {
        "definition": REPORT_DEFINITIONS["archived-timesheets"],
        "filters": [
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "Employee",
                "name": "employee_id",
                "type": "select",
                "value": employee_id,
                "options": _employee_filter_options(current_user),
            },
            {
                "label": "Week Start From",
                "name": "week_start_from",
                "type": "date",
                "value": week_start_from,
            },
            {
                "label": "Week Start To",
                "name": "week_start_to",
                "type": "date",
                "value": week_start_to,
            },
        ],
        "headers": (
            "BU",
            "Employee Code",
            "Employee",
            "Week Start",
            "Week End",
            "Status",
            "Archive Eligible Date",
        ),
        "rows": rows,
        "totals": [
            {"label": "Archived Timesheets", "value": str(len(rows))},
        ],
        "empty_message": "No archived timesheets match the current filters.",
    }


def _audit_history_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    entity_name = _selected_value(request, "entity_name")
    action_code = _selected_value(request, "action_code")
    event_from = _selected_value(request, "event_from")
    event_to = _selected_value(request, "event_to")

    queryset = AuditLog.objects.select_related(
        "business_unit",
        "actor_employee",
        "action_type",
    ).filter(business_unit_id__in=current_user.scoped_business_unit_ids)
    if business_unit_id:
        queryset = queryset.filter(business_unit_id=business_unit_id)
    if entity_name:
        queryset = queryset.filter(entity_name__icontains=entity_name)
    if action_code:
        queryset = queryset.filter(action_type__value_code__icontains=action_code)
    parsed_start = _parse_date_query(event_from)
    parsed_end = _parse_date_query(event_to)
    if parsed_start is not None:
        queryset = queryset.filter(event_timestamp__date__gte=parsed_start)
    if parsed_end is not None:
        queryset = queryset.filter(event_timestamp__date__lte=parsed_end)

    rows = [
        [
            _date_display(item.event_timestamp),
            item.business_unit.bu_code if item.business_unit_id else "",
            item.actor_employee.employee_code if item.actor_employee_id else item.actor_email,
            item.action_type.value_code,
            item.entity_name,
            str(item.entity_id or ""),
            item.reason_text or "",
        ]
        for item in queryset[:200]
    ]
    return {
        "definition": REPORT_DEFINITIONS["audit-history"],
        "filters": [
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "Entity Name",
                "name": "entity_name",
                "type": "text",
                "value": entity_name,
            },
            {
                "label": "Action Code",
                "name": "action_code",
                "type": "text",
                "value": action_code,
            },
            {
                "label": "Event From",
                "name": "event_from",
                "type": "date",
                "value": event_from,
            },
            {
                "label": "Event To",
                "name": "event_to",
                "type": "date",
                "value": event_to,
            },
        ],
        "headers": (
            "Event Timestamp",
            "BU",
            "Actor",
            "Action",
            "Entity",
            "Entity ID",
            "Reason",
        ),
        "rows": rows,
        "totals": [
            {"label": "Rows Returned", "value": str(len(rows))},
            {"label": "Result Limit", "value": "200"},
        ],
        "empty_message": "No audit events match the current filters.",
    }


def _integration_jobs_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    interface_code = _selected_value(request, "interface_code")
    status_code = _selected_value(request, "status")

    queryset = IntegrationJob.objects.select_related(
        "business_unit",
        "status",
        "requested_by_employee",
    ).filter(business_unit_id__in=current_user.scoped_business_unit_ids)
    if business_unit_id:
        queryset = queryset.filter(business_unit_id=business_unit_id)
    if interface_code:
        queryset = queryset.filter(interface_code__icontains=interface_code)
    if status_code:
        queryset = queryset.filter(status__value_code=status_code)

    rows = [
        [
            _date_display(item.created_at),
            item.business_unit.bu_code,
            item.interface_code,
            item.direction,
            item.status.value_code,
            str(item.total_records),
            str(item.success_records),
            str(item.error_records),
            item.requested_by_employee.employee_code if item.requested_by_employee_id else "",
            item.summary_message or "",
        ]
        for item in queryset[:200]
    ]
    return {
        "definition": REPORT_DEFINITIONS["integration-jobs"],
        "filters": [
            {
                "label": "Business Unit",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "Interface Code",
                "name": "interface_code",
                "type": "text",
                "value": interface_code,
            },
            {
                "label": "Status",
                "name": "status",
                "type": "select",
                "value": status_code,
                "options": _status_filter_options(
                    IntegrationJob.objects.filter(
                        business_unit_id__in=current_user.scoped_business_unit_ids
                    )
                ),
            },
        ],
        "headers": (
            "Created At",
            "BU",
            "Interface",
            "Direction",
            "Status",
            "Total",
            "Success",
            "Errors",
            "Requested By",
            "Summary",
        ),
        "rows": rows,
        "totals": [
            {"label": "Rows Returned", "value": str(len(rows))},
        ],
        "empty_message": "No integration jobs match the current filters.",
    }


REPORT_BUILDERS = {
    "my-timesheet-history": _my_timesheet_history_report,
    "project-time": _project_time_report,
    "pending-approvals": _pending_approvals_report,
    "missing-timesheets": _missing_timesheets_report,
    "archived-timesheets": _archived_timesheets_report,
    "audit-history": _audit_history_report,
    "integration-jobs": _integration_jobs_report,
}


@require_GET
def reports_hub(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    context = _reports_context(
        request,
        title="Reports Hub",
        eyebrow="SCR-230",
        intro=(
            "Entry point for the reports currently supported by the live backend, "
            "with cards shown only when your TS role is allowed to run them."
        ),
    )
    context["report_cards"] = _report_cards(current_user)
    return render(request, "core/reports_hub.html", context)


def render_report_view(
    request: HttpRequest,
    current_user: CurrentUser,
    report_code: str,
    *,
    title: str | None = None,
    eyebrow: str = "SCR-231",
    intro: str | None = None,
    report_path: str | None = None,
    back_href: str = "/reports/",
    back_label: str = "Back to Reports Hub",
) -> HttpResponse:
    definition = REPORT_DEFINITIONS.get(report_code)
    if definition is None:
        return _render_access_denied(
            request, message="The requested report does not exist.", status=404
        )
    if not AuthorizationPolicyService.can_run_report(current_user, report_code):
        return _render_access_denied(
            request,
            message="You do not have permission to open this report.",
            status=403,
        )

    payload = REPORT_BUILDERS[report_code](current_user, request)
    filters = [field for field in payload["filters"] if field is not None]
    context = _reports_context(
        request,
        title=title or definition.title,
        eyebrow=eyebrow,
        intro=intro or definition.summary,
    )
    context.update(
        {
            "report_code": report_code,
            "report_path": report_path or _report_url(report_code),
            "report_definition": definition,
            "filter_fields": filters,
            "table_headers": payload["headers"],
            "table_rows": payload["rows"],
            "totals": payload["totals"],
            "empty_message": payload["empty_message"],
            "back_href": back_href,
            "back_label": back_label,
        }
    )
    return render(request, "core/report_viewer.html", context)


@require_GET
def report_viewer(request: HttpRequest, report_code: str) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    return render_report_view(request, current_user, report_code)
