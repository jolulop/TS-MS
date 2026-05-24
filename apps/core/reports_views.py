import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, F, Max, Min, Q, Sum
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from apps.audit.models import AuditLog
from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.policies import AuthorizationPolicyService
from apps.common.approval_scope import (
    approval_item_effective_business_unit,
    ts_admin_approval_business_unit_filter_q,
    ts_admin_visible_approval_items_q,
)
from apps.common.logging import log_report_export
from apps.common.parsing import parse_optional_date_query as _parse_date_query
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.integrations.models import IntegrationJob
from apps.master_data.models import (
    BusinessUnit,
    Employee,
    GeneralChargeCode,
    Project,
)
from apps.master_data.staffing import project_staffing_windows
from apps.timesheets.models import ApprovalAction, ApprovalItem, TimesheetLine, WeeklyTimesheet
from apps.timesheets.services import TimesheetService


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
        title="Missing Timesheets by Project",
        summary=(
            "Assigned employees with missing weekly timesheets across the selected project scope."
        ),
        audience="PROJECT_OWNER, PROJECT_MANAGER, TS_ADMIN",
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
    "employee-utilization": ReportDefinition(
        code="employee-utilization",
        title="Employee Utilization",
        summary=(
            "Worked versus expected capacity by employee inside the current "
            "TS admin scope."
        ),
        audience="TS_ADMIN",
    ),
    "office-bu-time-summary": ReportDefinition(
        code="office-bu-time-summary",
        title="Office / BU Time Summary",
        summary=(
            "Aggregated worked hours by Office and Business Unit inside the "
            "current TS admin scope."
        ),
        audience="TS_ADMIN",
    ),
    "general-charge-code-usage": ReportDefinition(
        code="general-charge-code-usage",
        title="General Charge Code (GCC) Usage",
        summary="Usage analytics for internal charging codes inside the current TS admin scope.",
        audience="TS_ADMIN",
    ),
    "approval-turnaround": ReportDefinition(
        code="approval-turnaround",
        title="Approval Turnaround",
        summary=(
            "Elapsed approval timing and stalled-item visibility inside the "
            "current TS admin scope."
        ),
        audience="TS_ADMIN",
    ),
}

EXPORTABLE_REPORT_CODES = {
    "project-time",
    "pending-approvals",
    "missing-timesheets",
    "archived-timesheets",
    "audit-history",
    "integration-jobs",
    "employee-utilization",
    "office-bu-time-summary",
    "general-charge-code-usage",
    "approval-turnaround",
}

REPORT_CARD_ORDER = (
    "project-time",
    "pending-approvals",
    "missing-timesheets",
    "employee-utilization",
    "office-bu-time-summary",
    "general-charge-code-usage",
    "approval-turnaround",
    "archived-timesheets",
    "audit-history",
    "integration-jobs",
)


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


def _date_display(value) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _decimal_display(value: Decimal | None) -> str:
    decimal_value = value if value is not None else Decimal("0.00")
    return f"{decimal_value:.2f}"


def _percent_display(numerator: Decimal, denominator: Decimal) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{((numerator / denominator) * Decimal('100')):.2f}%"


def _report_url(report_code: str) -> str:
    return f"/reports/{report_code}/"


def _report_export_url(report_code: str) -> str:
    return f"/reports/{report_code}/export/"


def _selected_values(request: HttpRequest, name: str) -> list[str]:
    return [value.strip() for value in request.GET.getlist(name) if value.strip()]


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


def _coerce_date_value(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value


def _aggregate_date_bounds(queryset, field_name: str) -> tuple[date | None, date | None]:
    bounds = queryset.aggregate(
        min_value=Min(field_name),
        max_value=Max(field_name),
    )
    return _coerce_date_value(bounds["min_value"]), _coerce_date_value(bounds["max_value"])


def _resolved_date_range(
    raw_start: str,
    raw_end: str,
    *,
    default_start: date | None,
    default_end: date | None,
) -> tuple[date | None, date | None, str, str]:
    resolved_start = _parse_date_query(raw_start) or default_start
    resolved_end = _parse_date_query(raw_end) or default_end
    return (
        resolved_start,
        resolved_end,
        resolved_start.isoformat() if resolved_start is not None else raw_start,
        resolved_end.isoformat() if resolved_end is not None else raw_end,
    )


def _first_monday_on_or_after(start_date: date) -> date:
    return start_date + timedelta(days=(7 - start_date.weekday()) % 7)


def _monday_on_or_before(end_date: date) -> date:
    return end_date - timedelta(days=end_date.weekday())


def _selected_project_values(request: HttpRequest) -> list[str]:
    return _selected_values(request, "project_ids")


def _project_filter_options(
    current_user: CurrentUser, *, selected_values: set[str] | None = None
) -> list[dict]:
    selected = selected_values or set()
    return [
        {
            "value": str(project.id),
            "label": f"{project.project_code} - {project.name}",
            "selected": str(project.id) in selected,
        }
        for project in _scoped_project_queryset(current_user).order_by("project_code")
    ]


def _resolved_project_selection(
    current_user: CurrentUser,
    raw_project_ids: list[str],
) -> tuple[list[int], list[dict], list[str]]:
    project_options = _project_filter_options(
        current_user,
        selected_values=set(raw_project_ids),
    )
    accessible_project_ids = {int(option["value"]) for option in project_options}
    selected_project_ids = [
        int(raw_project_id)
        for raw_project_id in raw_project_ids
        if raw_project_id.isdigit() and int(raw_project_id) in accessible_project_ids
    ]
    if raw_project_ids:
        effective_project_ids = selected_project_ids
    else:
        effective_project_ids = [int(option["value"]) for option in project_options]
    return effective_project_ids, project_options, raw_project_ids


def _project_missing_timesheet_rows(
    current_user: CurrentUser,
    raw_project_ids: list[str],
) -> tuple[list[list[str]], list[dict], list[int]]:
    effective_project_ids, project_options, selected_project_ids = _resolved_project_selection(
        current_user,
        raw_project_ids,
    )
    if not effective_project_ids:
        return [], project_options, []

    staffing_windows = project_staffing_windows(effective_project_ids)
    if not staffing_windows:
        return [], project_options, selected_project_ids

    current_week_start = _current_monday()
    assignment_windows: list[tuple[object, date, date]] = []
    employee_ids: set[int] = set()
    global_start: date | None = None
    global_end: date | None = None

    for staffing_window in staffing_windows:
        effective_start = max(
            staffing_window.employee_created_at.date(),
            staffing_window.staffing_start_date,
            staffing_window.project_start_date,
        )
        end_candidates = [current_week_start]
        if staffing_window.staffing_end_date is not None:
            end_candidates.append(staffing_window.staffing_end_date)
        if staffing_window.project_end_date is not None:
            end_candidates.append(staffing_window.project_end_date)
        if staffing_window.project_close_date is not None:
            end_candidates.append(staffing_window.project_close_date)
        if staffing_window.employee_employment_end_date is not None:
            end_candidates.append(staffing_window.employee_employment_end_date)
        effective_end = min(end_candidates)

        first_week_start = _first_monday_on_or_after(effective_start)
        last_week_start = _monday_on_or_before(effective_end)
        if first_week_start > last_week_start:
            continue

        assignment_windows.append((staffing_window, first_week_start, last_week_start))
        employee_ids.add(staffing_window.employee_id)
        global_start = (
            first_week_start if global_start is None else min(global_start, first_week_start)
        )
        global_end = last_week_start if global_end is None else max(global_end, last_week_start)

    if not assignment_windows or global_start is None or global_end is None:
        return [], project_options, selected_project_ids

    existing_timesheets_by_employee: dict[int, set[date]] = {}
    for employee_id, week_start_date in WeeklyTimesheet.objects.filter(
        employee_id__in=employee_ids,
        week_start_date__gte=global_start,
        week_start_date__lte=global_end,
    ).values_list("employee_id", "week_start_date"):
        existing_timesheets_by_employee.setdefault(employee_id, set()).add(week_start_date)

    missing_rows_by_employee_week: dict[tuple[int, date], list[str]] = {}
    for staffing_window, first_week_start, last_week_start in assignment_windows:
        existing_week_starts = existing_timesheets_by_employee.get(
            staffing_window.employee_id,
            set(),
        )
        week_start = first_week_start
        while week_start <= last_week_start:
            if week_start not in existing_week_starts:
                key = (staffing_window.employee_id, week_start)
                missing_rows_by_employee_week.setdefault(
                    key,
                    [
                        staffing_window.project_name,
                        staffing_window.employee_full_name,
                        staffing_window.employee_email,
                        week_start.isoformat(),
                    ],
                )
            week_start += timedelta(days=7)

    rows = [
        missing_rows_by_employee_week[key]
        for key in sorted(
            missing_rows_by_employee_week,
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
    ]
    return rows, project_options, selected_project_ids


def _primary_business_unit_for_audit(current_user: CurrentUser) -> BusinessUnit | None:
    return BusinessUnit.objects.filter(id=current_user.primary_business_unit_id).first()


def _audit_missing_timesheets_report(
    current_user: CurrentUser,
    *,
    action_code: str,
    selected_project_ids: list[int],
    row_count: int,
    reason_prefix: str,
) -> None:
    project_list = ",".join(str(project_id) for project_id in selected_project_ids) or "ALL"
    write_audit_event(
        action_code=action_code,
        entity_name="project_missing_timesheets_report",
        actor_employee=Employee.objects.filter(id=current_user.employee_id).first(),
        actor_email=current_user.email,
        business_unit=_primary_business_unit_for_audit(current_user),
        reason_text=f"{reason_prefix}; projects={project_list}; rows={row_count}",
    )
    if action_code == "EXPORT":
        log_report_export(
            report_code="missing-timesheets",
            actor_email=current_user.email,
            row_count=row_count,
            filters=f"projects={project_list}",
            channel="csv",
        )


def _report_audit_entity_name(report_code: str) -> str:
    if report_code == "missing-timesheets":
        return "project_missing_timesheets_report"
    return f"{report_code.replace('-', '_')}_report"


def _report_filter_summary(request: HttpRequest) -> str:
    return request.GET.urlencode() or "default-scope"


def _audit_report_export(
    current_user: CurrentUser,
    *,
    report_code: str,
    request: HttpRequest,
    row_count: int,
) -> None:
    if report_code == "missing-timesheets":
        selected_project_ids = [
            int(project_id)
            for project_id in _selected_project_values(request)
            if project_id.isdigit()
        ]
        _audit_missing_timesheets_report(
            current_user,
            action_code="EXPORT",
            selected_project_ids=selected_project_ids,
            row_count=row_count,
            reason_prefix="Exported project missing timesheets CSV",
        )
        return

    write_audit_event(
        action_code="EXPORT",
        entity_name=_report_audit_entity_name(report_code),
        actor_employee=Employee.objects.filter(id=current_user.employee_id).first(),
        actor_email=current_user.email,
        business_unit=_primary_business_unit_for_audit(current_user),
        reason_text=(
            f"Exported {REPORT_DEFINITIONS[report_code].title} CSV; "
            f"filters={_report_filter_summary(request)}; rows={row_count}"
        ),
    )
    log_report_export(
        report_code=report_code,
        actor_email=current_user.email,
        row_count=row_count,
        filters=_report_filter_summary(request),
        channel="csv",
    )


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
                ts_admin_visible_approval_items_q(current_user),
                status__value_code="PENDING",
            ).count()
        return ApprovalItem.objects.filter(
            Q(approver_employee_id=current_user.employee_id)
            | Q(project__project_manager_employee_id=current_user.employee_id),
            status__value_code="PENDING",
        ).count()
    if report_code == "missing-timesheets":
        rows, _, _ = _project_missing_timesheet_rows(current_user, [])
        return len(rows)
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
    if report_code == "employee-utilization":
        return Employee.objects.filter(
            primary_business_unit_id__in=current_user.scoped_business_unit_ids,
            status__value_code="ACTIVE",
        ).count()
    if report_code == "office-bu-time-summary":
        return (
            TimesheetLine.objects.filter(
                weekly_timesheet__business_unit_id__in=current_user.scoped_business_unit_ids
            )
            .values("weekly_timesheet__business_unit_id")
            .distinct()
            .count()
        )
    if report_code == "general-charge-code-usage":
        return (
            TimesheetLine.objects.filter(
                weekly_timesheet__business_unit_id__in=current_user.scoped_business_unit_ids,
                general_charge_code_id__isnull=False,
            )
            .values("general_charge_code_id")
            .distinct()
            .count()
        )
    if report_code == "approval-turnaround":
        return ApprovalItem.objects.filter(ts_admin_visible_approval_items_q(current_user)).count()
    return 0


def _report_cards(current_user: CurrentUser) -> list[dict]:
    cards = []
    for report_code in REPORT_CARD_ORDER:
        definition = REPORT_DEFINITIONS[report_code]
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


def _general_charge_code_filter_options(current_user: CurrentUser) -> list[dict]:
    queryset = GeneralChargeCode.objects.filter(
        business_unit_id__in=current_user.scoped_business_unit_ids
    ).order_by("code")
    return [
        {
            "value": str(code.id),
            "label": f"{code.code} - {code.name}",
        }
        for code in queryset
    ]


def _approval_approver_filter_options(current_user: CurrentUser) -> list[dict]:
    approver_ids = list(
        ApprovalItem.objects.filter(
            ts_admin_visible_approval_items_q(current_user),
            approver_employee_id__isnull=False,
        )
        .values_list("approver_employee_id", flat=True)
        .distinct()
    )
    queryset = Employee.objects.filter(id__in=approver_ids).order_by("employee_code")
    return [
        {
            "value": str(employee.id),
            "label": f"{employee.employee_code} - {employee.full_name}",
        }
        for employee in queryset
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


def _parse_business_unit_filter_id(raw_business_unit_id: str) -> int | None:
    if not raw_business_unit_id.isdigit():
        return None
    return int(raw_business_unit_id)


def _scoped_business_unit_filter_ids(
    current_user: CurrentUser,
    raw_business_unit_id: str,
) -> list[int]:
    scoped_business_unit_ids = list(current_user.scoped_business_unit_ids)
    if not raw_business_unit_id:
        return scoped_business_unit_ids

    selected_business_unit_id = _parse_business_unit_filter_id(raw_business_unit_id)
    if selected_business_unit_id is None:
        return []
    if selected_business_unit_id not in scoped_business_unit_ids:
        return []
    return [selected_business_unit_id]


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
        .order_by(
            "weekly_timesheet__business_unit__bu_code",
            "project__project_code",
            "-work_date",
            "weekly_timesheet__employee__employee_code",
            "id",
        )
    )

    business_unit_id = _selected_value(request, "business_unit_id")
    project_id = _selected_value(request, "project_id")
    employee_id = _selected_value(request, "employee_id")
    work_date_from = _selected_value(request, "work_date_from")
    work_date_to = _selected_value(request, "work_date_to")

    if business_unit_id and current_user.is_ts_admin:
        queryset = queryset.filter(
            project__business_unit_id__in=_scoped_business_unit_filter_ids(
                current_user,
                business_unit_id,
            )
        )
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

    lines = list(queryset)
    grouped_rows: list[dict[str, object]] = []
    export_rows = [
        [
            line.weekly_timesheet.business_unit.bu_code,
            line.project.project_code if line.project else "",
            line.project.name if line.project else "",
            line.weekly_timesheet.week_start_date.isoformat(),
            line.weekly_timesheet.employee.employee_code,
            line.weekly_timesheet.employee.full_name,
            line.work_date.isoformat(),
            _decimal_display(line.hours),
            "Billable" if line.billable_flag else "Non-billable",
            line.approval_state.value_code if line.approval_state_id else "Not routed",
            line.comment_text or "",
        ]
        for line in lines
    ]

    project_groups: dict[tuple[str, int], list[TimesheetLine]] = {}
    for line in lines:
        bu_code = line.weekly_timesheet.business_unit.bu_code
        project_groups.setdefault((bu_code, line.project_id), []).append(line)

    for group_index, project_lines in enumerate(project_groups.values(), start=1):
        first_line = project_lines[0]
        bu_code = first_line.weekly_timesheet.business_unit.bu_code
        project_code = first_line.project.project_code if first_line.project else ""
        project_name = first_line.project.name if first_line.project else ""
        group_id = f"project-time-group-{group_index}"
        total_hours = sum((line.hours for line in project_lines), start=Decimal("0.00"))
        billable_hours = sum(
            (line.hours for line in project_lines if line.billable_flag),
            start=Decimal("0.00"),
        )
        week_groups: dict[date, list[TimesheetLine]] = {}
        for line in project_lines:
            week_groups.setdefault(line.weekly_timesheet.week_start_date, []).append(line)
        grouped_rows.append(
            {
                "kind": "project_group",
                "row_id": group_id,
                "project_label": f"{project_code} - {project_name}",
                "detail_count": len(project_lines),
                "week_count": len(week_groups),
                "cells": [
                    bu_code,
                    project_code,
                    project_name,
                    "",
                    "",
                    "",
                    "",
                    _decimal_display(total_hours),
                    _decimal_display(billable_hours),
                    "",
                    "",
                ],
            }
        )

        for week_index, (week_start, week_lines) in enumerate(week_groups.items(), start=1):
            week_row_id = f"{group_id}-week-{week_index}"
            week_total_hours = sum((line.hours for line in week_lines), start=Decimal("0.00"))
            week_billable_hours = sum(
                (line.hours for line in week_lines if line.billable_flag),
                start=Decimal("0.00"),
            )
            grouped_rows.append(
                {
                    "kind": "week_group",
                    "row_id": week_row_id,
                    "parent_id": group_id,
                    "week_label": week_start.isoformat(),
                    "detail_count": len(week_lines),
                    "cells": [
                        "",
                        "",
                        "",
                        week_start.isoformat(),
                        "",
                        "",
                        "",
                        _decimal_display(week_total_hours),
                        _decimal_display(week_billable_hours),
                        "",
                        "",
                    ],
                }
            )

            for line in week_lines:
                grouped_rows.append(
                    {
                        "kind": "detail",
                        "parent_id": week_row_id,
                        "cells": [
                            "",
                            "",
                            "",
                            "",
                            line.weekly_timesheet.employee.employee_code,
                            line.weekly_timesheet.employee.full_name,
                            line.work_date.isoformat(),
                            _decimal_display(line.hours),
                            "Billable" if line.billable_flag else "Non-billable",
                            (
                                line.approval_state.value_code
                                if line.approval_state_id
                                else "Not routed"
                            ),
                            line.comment_text or "",
                        ],
                    }
                )

    totals = queryset.aggregate(
        total_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
    )
    return {
        "definition": REPORT_DEFINITIONS["project-time"],
        "split_grid_class": "report-panel-stack",
        "filters": [
            {
                "label": "BU",
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
                "label": "From",
                "name": "work_date_from",
                "type": "date",
                "value": work_date_from,
            },
            {
                "label": "To",
                "name": "work_date_to",
                "type": "date",
                "value": work_date_to,
            },
        ],
        "table_intro": (
            "Expand a BU / Project summary row to reveal grouped weeks, then "
            "expand a week row to view the detail lines."
        ),
        "row_objects": grouped_rows,
        "row_behavior": "project-time-nested-groups",
        "table_class": "data-table data-table-wide",
        "headers": (
            "BU",
            "Project Code",
            "Project",
            "Week Start",
            "Employee Code",
            "Employee",
            "Work Date",
            "Hours",
            "Billable",
            "Approval State",
            "Comment",
        ),
        "rows": export_rows,
        "totals": [
            {"label": "Projects Returned", "value": str(len(project_groups))},
            {"label": "Detail Lines", "value": str(len(lines))},
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
    active_ad_hoc_role_ids = (
        AuthorizationPolicyService._active_general_charge_code_approval_role_ids(
            current_user
        )
    )
    queryset = ApprovalItem.objects.select_related(
        "status",
        "project",
        "project__business_unit",
        "project__office",
        "general_charge_code",
        "approver_employee",
        "submission_cycle",
        "submission_cycle__weekly_timesheet",
        "submission_cycle__weekly_timesheet__employee",
        "submission_cycle__weekly_timesheet__business_unit",
    ).prefetch_related(
        "approver_roles__existing_role",
        "approver_roles__approval_role",
    ).filter(status__value_code="PENDING")
    if current_user.is_ts_admin:
        queryset = queryset.filter(ts_admin_visible_approval_items_q(current_user))
    else:
        queryset = queryset.filter(
            Q(approver_employee_id=current_user.employee_id)
            | Q(
                general_charge_code_id__isnull=False,
                approver_roles__existing_role__value_code__in=current_user.role_codes,
            )
            | Q(
                general_charge_code_id__isnull=False,
                approver_roles__approval_role_id__in=active_ad_hoc_role_ids,
            )
        )

    business_unit_id = _selected_value(request, "business_unit_id")
    project_id = _selected_value(request, "project_id")
    employee_id = _selected_value(request, "employee_id")

    if business_unit_id and current_user.is_ts_admin:
        scoped_business_unit_ids = _scoped_business_unit_filter_ids(
            current_user,
            business_unit_id,
        )
        if scoped_business_unit_ids:
            queryset = queryset.filter(
                ts_admin_approval_business_unit_filter_q(
                    current_user,
                    scoped_business_unit_ids[0],
                )
            )
        else:
            queryset = queryset.none()
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    if employee_id:
        queryset = queryset.filter(submission_cycle__weekly_timesheet__employee_id=employee_id)

    rows = [
        [
            item.submission_cycle.weekly_timesheet.week_start_date.isoformat(),
            item.submission_cycle.weekly_timesheet.employee.employee_code,
            item.submission_cycle.weekly_timesheet.employee.full_name,
            item.project.project_code if item.project else "",
            (
                item.project.name
                if item.project
                else item.general_charge_code.code
                if item.general_charge_code
                else ""
            ),
            approval_item_effective_business_unit(item)["bu_code"],
            str(item.submission_cycle.submission_no),
        ]
        for item in queryset.order_by("submission_cycle__weekly_timesheet__week_start_date", "id")
    ]
    return {
        "definition": REPORT_DEFINITIONS["pending-approvals"],
        "split_grid_class": "report-panel-stack",
        "filters": [
            {
                "label": "BU",
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
            "Week Start Date",
            "Employee Code",
            "Employee",
            "Target Code",
            "Target",
            "BU",
            "Submission No.",
        ),
        "rows": rows,
        "totals": [
            {"label": "Pending Items", "value": str(len(rows))},
        ],
        "empty_message": "No pending approval items match the current filters.",
    }


def _missing_timesheets_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    rows, project_options, selected_project_ids = _project_missing_timesheet_rows(
        current_user,
        _selected_project_values(request),
    )
    return {
        "definition": REPORT_DEFINITIONS["missing-timesheets"],
        "split_grid_class": "report-panel-stack",
        "filters": [
            {
                "label": "Projects",
                "name": "project_ids",
                "type": "multiselect",
                "values": selected_project_ids,
                "options": project_options,
                "size": min(max(len(project_options), 6), 12),
            }
        ],
        "headers": (
            "Project Name",
            "Employee Name",
            "Employee Email",
            "Missing TS Week Start",
        ),
        "rows": rows,
        "totals": [
            {"label": "Missing Timesheets", "value": str(len(rows))},
        ],
        "empty_message": "No missing project timesheets match the current project scope.",
        "export_path": _report_export_url("missing-timesheets"),
    }


def _archived_timesheets_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    employee_id = _selected_value(request, "employee_id")
    week_start_from = _selected_value(request, "week_start_from")
    week_start_to = _selected_value(request, "week_start_to")
    scoped_business_unit_ids = _scoped_business_unit_filter_ids(
        current_user,
        business_unit_id,
    )

    queryset = WeeklyTimesheet.objects.select_related(
        "employee",
        "business_unit",
        "status",
    ).filter(
        business_unit_id__in=scoped_business_unit_ids,
        status__value_code="ARCHIVED",
    )
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
        "split_grid_class": "report-panel-stack",
        "filters": [
            {
                "label": "BU",
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
                "label": "From",
                "name": "week_start_from",
                "type": "date",
                "value": week_start_from,
            },
            {
                "label": "To",
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
    scoped_business_unit_ids = _scoped_business_unit_filter_ids(
        current_user,
        business_unit_id,
    )

    queryset = AuditLog.objects.select_related(
        "business_unit",
        "actor_employee",
        "action_type",
    ).filter(business_unit_id__in=scoped_business_unit_ids)
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
        "split_grid_class": "report-panel-stack",
        "filter_grid_class": "report-filter-grid report-filter-grid-dense",
        "filters": [
            {
                "label": "BU",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "Entity",
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
                "label": "From",
                "name": "event_from",
                "type": "date",
                "value": event_from,
            },
            {
                "label": "To",
                "name": "event_to",
                "type": "date",
                "value": event_to,
            },
        ],
        "headers": (
            "Event Timestamp",
            "Business Unit",
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
    scoped_business_unit_ids = _scoped_business_unit_filter_ids(
        current_user,
        business_unit_id,
    )

    queryset = IntegrationJob.objects.select_related(
        "business_unit",
        "status",
        "requested_by_employee",
    ).filter(business_unit_id__in=scoped_business_unit_ids)
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
        "split_grid_class": "report-panel-stack",
        "filters": [
            {
                "label": "BU",
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


def _employee_utilization_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    employee_id = _selected_value(request, "employee_id")
    work_date_from = _selected_value(request, "work_date_from")
    work_date_to = _selected_value(request, "work_date_to")

    scope_business_unit_ids = _scoped_business_unit_filter_ids(
        current_user,
        business_unit_id,
    )

    line_queryset = TimesheetLine.objects.filter(
        weekly_timesheet__business_unit_id__in=scope_business_unit_ids
    )
    if employee_id:
        line_queryset = line_queryset.filter(weekly_timesheet__employee_id=employee_id)
    default_start, default_end = _aggregate_date_bounds(line_queryset, "work_date")
    (
        resolved_start,
        resolved_end,
        work_date_from_value,
        work_date_to_value,
    ) = _resolved_date_range(
        work_date_from,
        work_date_to,
        default_start=default_start,
        default_end=default_end,
    )

    employee_queryset = Employee.objects.select_related("office", "primary_business_unit").filter(
        primary_business_unit_id__in=scope_business_unit_ids,
        status__value_code="ACTIVE",
    )
    if employee_id:
        employee_queryset = employee_queryset.filter(id=employee_id)

    filtered_line_queryset = line_queryset
    if resolved_start is not None:
        filtered_line_queryset = filtered_line_queryset.filter(work_date__gte=resolved_start)
    if resolved_end is not None:
        filtered_line_queryset = filtered_line_queryset.filter(work_date__lte=resolved_end)

    summary_rows = filtered_line_queryset.values("weekly_timesheet__employee_id").annotate(
        worked_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
        timesheet_count=Count("weekly_timesheet", distinct=True),
    )
    line_summary_by_employee = {
        row["weekly_timesheet__employee_id"]: row for row in summary_rows
    }

    rows: list[list[str]] = []
    total_expected_hours = Decimal("0.00")
    total_worked_hours = Decimal("0.00")
    total_billable_hours = Decimal("0.00")
    total_non_billable_hours = Decimal("0.00")
    if resolved_start is not None and resolved_end is not None:
        employees = list(employee_queryset.order_by("employee_code"))
        expected_hours_by_employee = TimesheetService.expected_capacity_hours_by_employee(
            employees,
            resolved_start,
            resolved_end,
        )
        for employee in employees:
            summary = line_summary_by_employee.get(employee.id, {})
            expected_hours = expected_hours_by_employee.get(employee.id, Decimal("0.00"))
            worked_hours = summary.get("worked_hours") or Decimal("0.00")
            billable_hours = summary.get("billable_hours") or Decimal("0.00")
            non_billable_hours = summary.get("non_billable_hours") or Decimal("0.00")
            timesheet_count = summary.get("timesheet_count") or 0
            total_expected_hours += expected_hours
            total_worked_hours += worked_hours
            total_billable_hours += billable_hours
            total_non_billable_hours += non_billable_hours
            rows.append(
                [
                    employee.office.office_name,
                    employee.primary_business_unit.bu_code,
                    employee.employee_code,
                    employee.full_name,
                    _decimal_display(expected_hours),
                    _decimal_display(worked_hours),
                    _decimal_display(billable_hours),
                    _decimal_display(non_billable_hours),
                    _percent_display(worked_hours, expected_hours),
                    str(timesheet_count),
                ]
            )

    return {
        "definition": REPORT_DEFINITIONS["employee-utilization"],
        "split_grid_class": "report-panel-stack",
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
                "label": "From",
                "name": "work_date_from",
                "type": "date",
                "value": work_date_from_value,
            },
            {
                "label": "To",
                "name": "work_date_to",
                "type": "date",
                "value": work_date_to_value,
            },
        ],
        "headers": (
            "Office",
            "BU",
            "Employee Code",
            "Employee",
            "Expected Hours",
            "Worked Hours",
            "Billable Hours",
            "Non-billable Hours",
            "Utilization",
            "Timesheets",
        ),
        "rows": rows,
        "totals": [
            {"label": "Employees Returned", "value": str(len(rows))},
            {"label": "Expected Hours", "value": _decimal_display(total_expected_hours)},
            {"label": "Worked Hours", "value": _decimal_display(total_worked_hours)},
            {"label": "Billable Hours", "value": _decimal_display(total_billable_hours)},
            {
                "label": "Non-billable Hours",
                "value": _decimal_display(total_non_billable_hours),
            },
            {
                "label": "Overall Utilization",
                "value": _percent_display(total_worked_hours, total_expected_hours),
            },
        ],
        "empty_message": "No employee utilization rows match the current filters.",
    }


def _office_bu_time_summary_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    work_date_from = _selected_value(request, "work_date_from")
    work_date_to = _selected_value(request, "work_date_to")
    scoped_business_unit_ids = _scoped_business_unit_filter_ids(
        current_user,
        business_unit_id,
    )

    queryset = TimesheetLine.objects.filter(
        project_id__isnull=False,
    ).filter(
        Q(weekly_timesheet__business_unit_id__in=scoped_business_unit_ids)
        | Q(project__business_unit_id__in=scoped_business_unit_ids)
    )

    default_start, default_end = _aggregate_date_bounds(queryset, "work_date")
    (
        resolved_start,
        resolved_end,
        work_date_from_value,
        work_date_to_value,
    ) = _resolved_date_range(
        work_date_from,
        work_date_to,
        default_start=default_start,
        default_end=default_end,
    )
    if resolved_start is not None:
        queryset = queryset.filter(work_date__gte=resolved_start)
    if resolved_end is not None:
        queryset = queryset.filter(work_date__lte=resolved_end)

    queryset = queryset.annotate(
        effective_office_name=F("project__office__office_name"),
        effective_business_unit_id=F("project__business_unit_id"),
        effective_business_unit_name=F("project__business_unit__name"),
    )

    grouped_rows = queryset.values(
        "effective_office_name",
        "effective_business_unit_name",
        "project__project_code",
        "project__name",
    ).annotate(
        employee_count=Count("weekly_timesheet__employee", distinct=True),
        timesheet_count=Count("weekly_timesheet", distinct=True),
        line_count=Count("id"),
        total_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
    ).order_by(
        "effective_office_name",
        "effective_business_unit_name",
        "project__project_code",
    )

    rows = [
        [
            row["effective_office_name"],
            row["effective_business_unit_name"],
            f"{row['project__project_code']} - {row['project__name']}",
            str(row["employee_count"]),
            str(row["timesheet_count"]),
            str(row["line_count"]),
            _decimal_display(row["total_hours"]),
            _decimal_display(row["billable_hours"]),
            _decimal_display(row["non_billable_hours"]),
        ]
        for row in grouped_rows
    ]
    totals = queryset.aggregate(
        employee_count=Count("weekly_timesheet__employee", distinct=True),
        timesheet_count=Count("weekly_timesheet", distinct=True),
        total_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
    )
    return {
        "definition": REPORT_DEFINITIONS["office-bu-time-summary"],
        "split_grid_class": "report-panel-stack",
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
                "label": "Work Date From",
                "name": "work_date_from",
                "type": "date",
                "value": work_date_from_value,
            },
            {
                "label": "Work Date To",
                "name": "work_date_to",
                "type": "date",
                "value": work_date_to_value,
            },
        ],
        "headers": (
            "Office",
            "BU Name",
            "Project",
            "Employees",
            "Timesheets",
            "Lines",
            "Total Hours",
            "Billable Hours",
            "Non-billable Hours",
        ),
        "rows": rows,
        "totals": [
            {"label": "Rows Returned", "value": str(len(rows))},
            {"label": "Employees", "value": str(totals["employee_count"] or 0)},
            {"label": "Timesheets", "value": str(totals["timesheet_count"] or 0)},
            {"label": "Total Hours", "value": _decimal_display(totals["total_hours"])},
            {"label": "Billable Hours", "value": _decimal_display(totals["billable_hours"])},
            {
                "label": "Non-billable Hours",
                "value": _decimal_display(totals["non_billable_hours"]),
            },
        ],
        "empty_message": (
            "No Office, Business Unit, or project summary rows match the "
            "current filters."
        ),
    }


def _general_charge_code_usage_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    general_charge_code_id = _selected_value(request, "general_charge_code_id")
    employee_id = _selected_value(request, "employee_id")
    work_date_from = _selected_value(request, "work_date_from")
    work_date_to = _selected_value(request, "work_date_to")

    queryset = TimesheetLine.objects.select_related(
        "weekly_timesheet__business_unit__office",
        "general_charge_code",
    ).filter(
        weekly_timesheet__business_unit_id__in=_scoped_business_unit_filter_ids(
            current_user,
            business_unit_id,
        ),
        general_charge_code_id__isnull=False,
    )
    if general_charge_code_id:
        queryset = queryset.filter(general_charge_code_id=general_charge_code_id)
    if employee_id:
        queryset = queryset.filter(weekly_timesheet__employee_id=employee_id)

    default_start, default_end = _aggregate_date_bounds(queryset, "work_date")
    (
        resolved_start,
        resolved_end,
        work_date_from_value,
        work_date_to_value,
    ) = _resolved_date_range(
        work_date_from,
        work_date_to,
        default_start=default_start,
        default_end=default_end,
    )
    if resolved_start is not None:
        queryset = queryset.filter(work_date__gte=resolved_start)
    if resolved_end is not None:
        queryset = queryset.filter(work_date__lte=resolved_end)

    grouped_rows = queryset.values(
        "weekly_timesheet__business_unit__office__office_name",
        "weekly_timesheet__business_unit__bu_code",
        "general_charge_code__code",
        "general_charge_code__name",
    ).annotate(
        employee_count=Count("weekly_timesheet__employee", distinct=True),
        line_count=Count("id"),
        total_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
    ).order_by("general_charge_code__code")

    rows = [
        [
            row["weekly_timesheet__business_unit__office__office_name"],
            row["weekly_timesheet__business_unit__bu_code"],
            row["general_charge_code__code"],
            row["general_charge_code__name"],
            str(row["employee_count"]),
            str(row["line_count"]),
            _decimal_display(row["total_hours"]),
            _decimal_display(row["billable_hours"]),
            _decimal_display(row["non_billable_hours"]),
        ]
        for row in grouped_rows
    ]
    totals = queryset.aggregate(
        code_count=Count("general_charge_code", distinct=True),
        line_count=Count("id"),
        total_hours=Sum("hours"),
        billable_hours=Sum("hours", filter=Q(billable_flag=True)),
        non_billable_hours=Sum("hours", filter=Q(billable_flag=False)),
    )
    return {
        "definition": REPORT_DEFINITIONS["general-charge-code-usage"],
        "split_grid_class": "report-panel-stack",
        "filter_grid_class": "report-filter-grid report-filter-grid-dense",
        "filters": [
            {
                "label": "BU",
                "name": "business_unit_id",
                "type": "select",
                "value": business_unit_id,
                "options": _bu_filter_options(current_user),
            }
            if len(current_user.scoped_business_units) > 1
            else None,
            {
                "label": "GCC",
                "name": "general_charge_code_id",
                "type": "select",
                "value": general_charge_code_id,
                "options": _general_charge_code_filter_options(current_user),
            },
            {
                "label": "Employee",
                "name": "employee_id",
                "type": "select",
                "value": employee_id,
                "options": _employee_filter_options(current_user),
            },
            {
                "label": "From",
                "name": "work_date_from",
                "type": "date",
                "value": work_date_from_value,
            },
            {
                "label": "To",
                "name": "work_date_to",
                "type": "date",
                "value": work_date_to_value,
            },
        ],
        "headers": (
            "Office",
            "Business Unit",
            "GCC Code",
            "GCC Name",
            "Employees",
            "Lines",
            "Total Hours",
            "Billable Hours",
            "Non-billable Hours",
        ),
        "rows": rows,
        "totals": [
            {"label": "Codes Returned", "value": str(totals["code_count"] or 0)},
            {"label": "Lines", "value": str(totals["line_count"] or 0)},
            {"label": "Total Hours", "value": _decimal_display(totals["total_hours"])},
            {"label": "Billable Hours", "value": _decimal_display(totals["billable_hours"])},
            {
                "label": "Non-billable Hours",
                "value": _decimal_display(totals["non_billable_hours"]),
            },
        ],
        "empty_message": "No General Charge Code usage rows match the current filters.",
    }


def _approval_target_code(approval_item: ApprovalItem) -> str:
    if approval_item.project_id is not None:
        return approval_item.project.project_code
    if approval_item.general_charge_code_id is not None:
        return approval_item.general_charge_code.code
    return ""


def _approval_target_name(approval_item: ApprovalItem) -> str:
    if approval_item.project_id is not None:
        return approval_item.project.name
    if approval_item.general_charge_code_id is not None:
        return approval_item.general_charge_code.name
    return ""


def _approval_approver_label(approval_item: ApprovalItem) -> str:
    if approval_item.approver_employee_id is not None:
        return approval_item.approver_employee.employee_code
    role_labels = []
    for mapping in approval_item.approver_roles.all():
        if mapping.existing_role_id is not None:
            role_labels.append(mapping.existing_role.value_code)
        elif mapping.approval_role_id is not None:
            role_labels.append(mapping.approval_role.role_code)
    return ", ".join(role_labels)


def _approval_elapsed_hours(
    *,
    submitted_at: datetime,
    decision_at: datetime | None,
    status_code: str,
) -> Decimal:
    end_time = (
        decision_at
        if status_code in {"APPROVED", "REJECTED"} and decision_at is not None
        else datetime.now(tz=submitted_at.tzinfo)
    )
    elapsed_seconds = max((end_time - submitted_at).total_seconds(), 0)
    return Decimal(str(elapsed_seconds / 3600)).quantize(Decimal("0.01"))


def _approval_aging_bucket(*, status_code: str, elapsed_hours: Decimal) -> str:
    if status_code == "PENDING" and elapsed_hours >= Decimal("72"):
        return "Stalled (>72h)"
    if elapsed_hours < Decimal("24"):
        return "<24h"
    if elapsed_hours < Decimal("72"):
        return "24-72h"
    return ">72h"


def _approval_turnaround_report(current_user: CurrentUser, request: HttpRequest) -> dict:
    business_unit_id = _selected_value(request, "business_unit_id")
    project_id = _selected_value(request, "project_id")
    approver_employee_id = _selected_value(request, "approver_employee_id")
    status_code = _selected_value(request, "status")
    submitted_from = _selected_value(request, "submitted_from")
    submitted_to = _selected_value(request, "submitted_to")

    queryset = ApprovalItem.objects.select_related(
        "status",
        "project",
        "general_charge_code",
        "approver_employee",
        "submission_cycle",
        "submission_cycle__weekly_timesheet",
        "submission_cycle__weekly_timesheet__employee",
        "submission_cycle__weekly_timesheet__business_unit",
        "project__business_unit",
        "project__office",
    ).prefetch_related(
        "approver_roles__existing_role",
        "approver_roles__approval_role",
    ).filter(ts_admin_visible_approval_items_q(current_user))
    if business_unit_id:
        scoped_business_unit_ids = _scoped_business_unit_filter_ids(
            current_user,
            business_unit_id,
        )
        if scoped_business_unit_ids:
            queryset = queryset.filter(
                ts_admin_approval_business_unit_filter_q(
                    current_user,
                    scoped_business_unit_ids[0],
                )
            )
        else:
            queryset = queryset.none()
    if project_id:
        queryset = queryset.filter(project_id=project_id)
    if approver_employee_id:
        queryset = queryset.filter(approver_employee_id=approver_employee_id)
    if status_code:
        queryset = queryset.filter(status__value_code=status_code)

    default_start, default_end = _aggregate_date_bounds(queryset, "submission_cycle__submitted_at")
    (
        resolved_start,
        resolved_end,
        submitted_from_value,
        submitted_to_value,
    ) = _resolved_date_range(
        submitted_from,
        submitted_to,
        default_start=default_start,
        default_end=default_end,
    )
    if resolved_start is not None:
        queryset = queryset.filter(submission_cycle__submitted_at__date__gte=resolved_start)
    if resolved_end is not None:
        queryset = queryset.filter(submission_cycle__submitted_at__date__lte=resolved_end)

    approval_items = list(queryset.order_by("-submission_cycle__submitted_at", "id"))
    decision_timestamps = {
        row["approval_item_id"]: row["decision_at"]
        for row in ApprovalAction.objects.filter(
            approval_item_id__in=[item.id for item in approval_items],
            action_type__value_code__in=("APPROVE", "REJECT"),
        )
        .values("approval_item_id")
        .annotate(decision_at=Max("action_timestamp"))
    }

    rows: list[list[str]] = []
    approved_count = 0
    rejected_count = 0
    pending_count = 0
    stalled_pending_count = 0
    total_elapsed_hours = Decimal("0.00")
    for item in approval_items:
        decision_at = decision_timestamps.get(item.id)
        elapsed_hours = _approval_elapsed_hours(
            submitted_at=item.submission_cycle.submitted_at,
            decision_at=decision_at,
            status_code=item.status.value_code,
        )
        aging_bucket = _approval_aging_bucket(
            status_code=item.status.value_code,
            elapsed_hours=elapsed_hours,
        )
        total_elapsed_hours += elapsed_hours
        if item.status.value_code == "APPROVED":
            approved_count += 1
        elif item.status.value_code == "REJECTED":
            rejected_count += 1
        elif item.status.value_code == "PENDING":
            pending_count += 1
            if aging_bucket == "Stalled (>72h)":
                stalled_pending_count += 1
        rows.append(
            [
                str(item.id),
                approval_item_effective_business_unit(item)["bu_code"],
                item.submission_cycle.weekly_timesheet.employee.employee_code,
                item.submission_cycle.weekly_timesheet.employee.full_name,
                _approval_target_code(item),
                _approval_target_name(item),
                _approval_approver_label(item),
                _date_display(item.submission_cycle.submitted_at),
                _date_display(decision_at) if decision_at is not None else "Pending",
                item.status.value_code,
                _decimal_display(elapsed_hours),
                aging_bucket,
            ]
        )

    average_elapsed_hours = (
        (total_elapsed_hours / Decimal(len(rows))).quantize(Decimal("0.01"))
        if rows
        else Decimal("0.00")
    )
    return {
        "definition": REPORT_DEFINITIONS["approval-turnaround"],
        "split_grid_class": "report-panel-stack",
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
                "label": "Project",
                "name": "project_id",
                "type": "select",
                "value": project_id,
                "options": _project_filter_options(current_user),
            },
            {
                "label": "Approver",
                "name": "approver_employee_id",
                "type": "select",
                "value": approver_employee_id,
                "options": _approval_approver_filter_options(current_user),
            },
            {
                "label": "Status",
                "name": "status",
                "type": "select",
                "value": status_code,
                "options": _status_filter_options(queryset),
            },
            {
                "label": "Submitted From",
                "name": "submitted_from",
                "type": "date",
                "value": submitted_from_value,
            },
            {
                "label": "Submitted To",
                "name": "submitted_to",
                "type": "date",
                "value": submitted_to_value,
            },
        ],
        "headers": (
            "Approval Item",
            "BU",
            "Employee Code",
            "Employee",
            "Target Code",
            "Target",
            "Approver",
            "Submitted At",
            "Decision At",
            "Status",
            "Elapsed Hours",
            "Aging Bucket",
        ),
        "rows": rows,
        "totals": [
            {"label": "Rows Returned", "value": str(len(rows))},
            {"label": "Approved", "value": str(approved_count)},
            {"label": "Rejected", "value": str(rejected_count)},
            {"label": "Pending", "value": str(pending_count)},
            {"label": "Stalled Pending", "value": str(stalled_pending_count)},
            {"label": "Average Elapsed Hours", "value": _decimal_display(average_elapsed_hours)},
        ],
        "empty_message": "No approval turnaround rows match the current filters.",
    }


REPORT_BUILDERS = {
    "my-timesheet-history": _my_timesheet_history_report,
    "project-time": _project_time_report,
    "pending-approvals": _pending_approvals_report,
    "missing-timesheets": _missing_timesheets_report,
    "archived-timesheets": _archived_timesheets_report,
    "audit-history": _audit_history_report,
    "integration-jobs": _integration_jobs_report,
    "employee-utilization": _employee_utilization_report,
    "office-bu-time-summary": _office_bu_time_summary_report,
    "general-charge-code-usage": _general_charge_code_usage_report,
    "approval-turnaround": _approval_turnaround_report,
}


@require_GET
def reports_hub(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if current_user.is_basic_user:
        return _render_access_denied(
            request,
            message="You do not have permission to open the reports hub.",
            status=403,
        )

    context = _reports_context(
        request,
        title="Reports Hub",
        eyebrow="SCR-230",
        intro="",
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
    if report_code == "missing-timesheets":
        selected_project_ids = [
            int(project_id)
            for project_id in _selected_project_values(request)
            if project_id.isdigit()
        ]
        _audit_missing_timesheets_report(
            current_user,
            action_code="CREATE",
            selected_project_ids=selected_project_ids,
            row_count=len(payload["rows"]),
            reason_prefix="Generated project missing timesheets report",
        )
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
            "report_filter_grid_class": payload.get("filter_grid_class", "report-filter-grid"),
            "summary_table_title": payload.get("summary_title"),
            "summary_table_headers": payload.get("summary_headers"),
            "summary_table_rows": payload.get("summary_rows"),
            "table_intro": payload.get("table_intro"),
            "table_headers": payload["headers"],
            "table_rows": payload["rows"],
            "table_row_objects": payload.get("row_objects"),
            "table_class": payload.get("table_class", "data-table"),
            "table_row_behavior": payload.get("row_behavior", ""),
            "totals": payload["totals"],
            "empty_message": payload["empty_message"],
            "back_href": back_href,
            "back_label": back_label,
            "export_path": payload.get("export_path")
            or (_report_export_url(report_code) if report_code in EXPORTABLE_REPORT_CODES else ""),
            "report_split_grid_class": payload.get("split_grid_class", "split-grid"),
        }
    )
    return render(request, "core/report_viewer.html", context)


@require_GET
def report_viewer(request: HttpRequest, report_code: str) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if report_code == "my-timesheet-history":
        query_string = request.GET.urlencode()
        redirect_path = f"/ts/?{query_string}" if query_string else "/ts/"
        return redirect(redirect_path)

    return render_report_view(request, current_user, report_code)


@require_GET
def export_missing_timesheets_csv(request: HttpRequest) -> HttpResponse:
    return _export_report_csv_response(request, report_code="missing-timesheets")


def _export_report_csv_response(request: HttpRequest, *, report_code: str) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if report_code not in REPORT_BUILDERS or report_code not in EXPORTABLE_REPORT_CODES:
        raise Http404("Report export is not available.")

    if not AuthorizationPolicyService.can_run_report(current_user, report_code):
        return _render_access_denied(
            request,
            message="You do not have permission to export this report.",
            status=403,
        )

    payload = REPORT_BUILDERS[report_code](current_user, request)
    export_headers = payload.get("export_headers", payload["headers"])
    export_rows = payload.get("export_rows", payload["rows"])
    _audit_report_export(
        current_user,
        report_code=report_code,
        request=request,
        row_count=len(export_rows),
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{report_code}-{_current_monday().isoformat()}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(export_headers)
    writer.writerows(export_rows)
    return response


@require_GET
def export_report_csv(request: HttpRequest, report_code: str) -> HttpResponse:
    return _export_report_csv_response(request, report_code=report_code)


def build_missing_timesheets_export_query(project_ids: list[int]) -> str:
    if not project_ids:
        return ""
    return urlencode([("project_ids", project_id) for project_id in project_ids], doseq=True)
