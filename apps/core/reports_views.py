import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from apps.audit.services import write_audit_event
from apps.audit.models import AuditLog
from apps.auth.context import CurrentUser
from apps.auth.policies import AuthorizationPolicyService
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.integrations.models import IntegrationJob
from apps.master_data.models import BusinessUnit, Employee, Project, ProjectAssignment
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


def _first_monday_on_or_after(start_date: date) -> date:
    return start_date + timedelta(days=(7 - start_date.weekday()) % 7)


def _monday_on_or_before(end_date: date) -> date:
    return end_date - timedelta(days=end_date.weekday())


def _selected_project_values(request: HttpRequest) -> list[str]:
    return _selected_values(request, "project_ids")


def _project_filter_options(current_user: CurrentUser, *, selected_values: set[str] | None = None) -> list[dict]:
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

    assignments = list(
        ProjectAssignment.objects.select_related("employee", "project")
        .filter(
            project_id__in=effective_project_ids,
            employee__status__value_code="ACTIVE",
            status__value_code="ACTIVE",
        )
        .order_by(
            "employee__full_name",
            "assignment_start_date",
            "project__project_code",
        )
    )
    if not assignments:
        return [], project_options, selected_project_ids

    current_week_start = _current_monday()
    assignment_windows: list[tuple[ProjectAssignment, date, date]] = []
    employee_ids: set[int] = set()
    global_start: date | None = None
    global_end: date | None = None

    for assignment in assignments:
        effective_start = max(
            assignment.employee.created_at.date(),
            assignment.assignment_start_date,
            assignment.project.start_date,
        )
        end_candidates = [current_week_start]
        if assignment.assignment_end_date is not None:
            end_candidates.append(assignment.assignment_end_date)
        if assignment.project.end_date is not None:
            end_candidates.append(assignment.project.end_date)
        if assignment.project.close_date is not None:
            end_candidates.append(assignment.project.close_date)
        if assignment.employee.employment_end_date is not None:
            end_candidates.append(assignment.employee.employment_end_date)
        effective_end = min(end_candidates)

        first_week_start = _first_monday_on_or_after(effective_start)
        last_week_start = _monday_on_or_before(effective_end)
        if first_week_start > last_week_start:
            continue

        assignment_windows.append((assignment, first_week_start, last_week_start))
        employee_ids.add(assignment.employee_id)
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
    for assignment, first_week_start, last_week_start in assignment_windows:
        existing_week_starts = existing_timesheets_by_employee.get(assignment.employee_id, set())
        week_start = first_week_start
        while week_start <= last_week_start:
            if week_start not in existing_week_starts:
                key = (assignment.employee_id, week_start)
                missing_rows_by_employee_week.setdefault(
                    key,
                    [
                        assignment.project.name,
                        assignment.employee.full_name,
                        assignment.employee.email,
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
    return 0


def _report_cards(current_user: CurrentUser) -> list[dict]:
    cards = []
    for report_code, definition in REPORT_DEFINITIONS.items():
        if report_code == "my-timesheet-history":
            continue
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
    active_ad_hoc_role_ids = AuthorizationPolicyService._active_general_charge_code_approval_role_ids(
        current_user
    )
    queryset = ApprovalItem.objects.select_related(
        "status",
        "project",
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
        queryset = queryset.filter(
            submission_cycle__weekly_timesheet__business_unit_id__in=current_user.scoped_business_unit_ids
        )
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
            (
                item.project.name
                if item.project
                else item.general_charge_code.code
                if item.general_charge_code
                else ""
            ),
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
            "Target Code",
            "Target",
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
    rows, project_options, selected_project_ids = _project_missing_timesheet_rows(
        current_user,
        _selected_project_values(request),
    )
    return {
        "definition": REPORT_DEFINITIONS["missing-timesheets"],
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
        "split_grid_class": "split-grid split-grid-primary-wide",
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
            "table_headers": payload["headers"],
            "table_rows": payload["rows"],
            "totals": payload["totals"],
            "empty_message": payload["empty_message"],
            "back_href": back_href,
            "back_label": back_label,
            "export_path": payload.get("export_path", ""),
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
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if not AuthorizationPolicyService.can_run_report(current_user, "missing-timesheets"):
        return _render_access_denied(
            request,
            message="You do not have permission to export this report.",
            status=403,
        )

    payload = REPORT_BUILDERS["missing-timesheets"](current_user, request)
    selected_project_ids = [
        int(project_id)
        for project_id in _selected_project_values(request)
        if project_id.isdigit()
    ]
    _audit_missing_timesheets_report(
        current_user,
        action_code="EXPORT",
        selected_project_ids=selected_project_ids,
        row_count=len(payload["rows"]),
        reason_prefix="Exported project missing timesheets CSV",
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="missing-timesheets-{_current_monday().isoformat()}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(payload["headers"])
    writer.writerows(payload["rows"])
    return response


def build_missing_timesheets_export_query(project_ids: list[int]) -> str:
    if not project_ids:
        return ""
    return urlencode([("project_ids", project_id) for project_id in project_ids], doseq=True)
