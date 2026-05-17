from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Sum, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.core.reports_views import render_report_view
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.master_data.models import Project, ProjectAssignment
from apps.timesheets.models import TimesheetLine, WeeklyTimesheet
from apps.timesheets.services import TimesheetService

INITIAL_EMPTY_EDITOR_ROWS = 5


def _timesheet_section_links(current_user: CurrentUser, current_path: str) -> list[dict]:
    links = [
        {
            "label": "My Timesheets",
            "href": "/ts/",
            "active": current_path == "/ts/",
        },
    ]
    if _can_open_project_management(current_user):
        links.append(
            {
                "label": "Project Management",
                "href": "/ts/projects/",
                "active": current_path == "/ts/projects/",
            }
        )
    if current_user.has_role("PROJECT_OWNER") or current_user.has_role("PROJECT_MANAGER"):
        links.append(
            {
                "label": "Project Time Inquiry",
                "href": "/ts/inquiry/",
                "active": current_path == "/ts/inquiry/",
            }
        )
    return links


def _ts_context(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    title: str,
    eyebrow: str,
    intro: str,
) -> dict:
    context = _page_context(
        request,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )
    context["ts_section_links"] = _timesheet_section_links(current_user, request.path)
    return context


def _render_timesheet_auth_error(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    title: str,
    eyebrow: str,
    intro: str,
    error: AuthError,
) -> HttpResponse:
    if error.status == 403:
        return _render_access_denied(request, message=error.message, status=403)

    context = _ts_context(
        request,
        current_user,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )
    context["denied_message"] = error.message
    return render(request, "core/access_denied.html", context, status=error.status)


def _current_monday(today: date | None = None) -> date:
    current_date = today or date.today()
    return current_date - timedelta(days=current_date.weekday())


def _first_monday_on_or_after(start_date: date) -> date:
    return start_date + timedelta(days=(7 - start_date.weekday()) % 7)


def _monday_on_or_before(end_date: date) -> date:
    return end_date - timedelta(days=end_date.weekday())


def _can_open_project_management(current_user: CurrentUser) -> bool:
    return (
        current_user.is_ts_admin
        or current_user.has_role("PROJECT_OWNER")
        or current_user.has_role("PROJECT_MANAGER")
    )


def _scoped_project_queryset(current_user: CurrentUser):
    queryset = Project.objects.select_related(
        "business_unit",
        "project_owner_employee",
        "project_manager_employee",
        "status",
    ).filter(office_id=current_user.office_id)
    if current_user.is_ts_admin:
        return queryset.filter(business_unit_id__in=current_user.scoped_business_unit_ids)

    project_scope = Q()
    if current_user.has_role("PROJECT_OWNER"):
        project_scope |= Q(project_owner_employee_id=current_user.employee_id)
    if current_user.has_role("PROJECT_MANAGER"):
        project_scope |= Q(project_manager_employee_id=current_user.employee_id)
    return queryset.filter(project_scope)


def _project_management_status_links(request: HttpRequest) -> tuple[str, list[dict]]:
    allowed_codes = ("ALL", "ACTIVE", "CLOSED", "DRAFT")
    selected_code = str(request.GET.get("status", "ALL")).strip().upper() or "ALL"
    if selected_code not in allowed_codes:
        selected_code = "ALL"
    links = []
    for status_code, label in (
        ("ALL", "All"),
        ("ACTIVE", "Active"),
        ("CLOSED", "Closed"),
        ("DRAFT", "Draft"),
    ):
        href = request.path if status_code == "ALL" else f"{request.path}?status={status_code}"
        links.append(
            {
                "label": label,
                "href": href,
                "active": selected_code == status_code,
            }
        )
    return selected_code, links


def _format_hours(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return f"{value:.2f}"


def _project_missing_timesheet_counts(project_ids: list[int]) -> dict[int, int]:
    if not project_ids:
        return {}

    assignments = list(
        ProjectAssignment.objects.select_related("employee", "project")
        .filter(
            project_id__in=project_ids,
            employee__status__value_code="ACTIVE",
            status__value_code="ACTIVE",
        )
        .order_by(
            "project__project_code",
            "employee__employee_code",
            "assignment_start_date",
        )
    )
    if not assignments:
        return {}

    current_week_start = _current_monday()
    employee_ids: set[int] = set()
    assignment_windows: list[tuple[int, int, date, date]] = []
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

        assignment_windows.append(
            (
                assignment.project_id,
                assignment.employee_id,
                first_week_start,
                last_week_start,
            )
        )
        employee_ids.add(assignment.employee_id)
        global_start = (
            first_week_start if global_start is None else min(global_start, first_week_start)
        )
        global_end = last_week_start if global_end is None else max(global_end, last_week_start)

    if not assignment_windows or global_start is None or global_end is None:
        return {}

    qualifying_weeks_by_employee: dict[int, set[date]] = defaultdict(set)
    for employee_id, week_start_date in WeeklyTimesheet.objects.filter(
        employee_id__in=employee_ids,
        week_start_date__gte=global_start,
        week_start_date__lte=global_end,
        status__value_code__in=("SUBMITTED", "APPROVED"),
    ).values_list("employee_id", "week_start_date"):
        qualifying_weeks_by_employee[employee_id].add(week_start_date)

    missing_employee_weeks_by_project: dict[int, set[tuple[int, date]]] = defaultdict(set)
    for project_id, employee_id, first_week_start, last_week_start in assignment_windows:
        qualifying_weeks = qualifying_weeks_by_employee.get(employee_id, set())
        week_start = first_week_start
        while week_start <= last_week_start:
            if week_start not in qualifying_weeks:
                missing_employee_weeks_by_project[project_id].add((employee_id, week_start))
            week_start += timedelta(days=7)

    return {
        project_id: len(missing_employee_weeks_by_project.get(project_id, set()))
        for project_id in project_ids
    }


def _project_management_rows(current_user: CurrentUser, projects: list[Project]) -> list[dict]:
    project_ids = [project.id for project in projects]
    approved_hours_by_project = {
        row["project_id"]: row["approved_hours"] or Decimal("0.00")
        for row in TimesheetLine.objects.filter(
            project_id__in=project_ids,
            weekly_timesheet__status__value_code="APPROVED",
        )
        .values("project_id")
        .annotate(approved_hours=Sum("hours"))
    }
    pending_timesheets_by_project = {
        row["lines__project_id"]: row["pending_timesheet_count"]
        for row in WeeklyTimesheet.objects.filter(
            status__value_code="SUBMITTED",
            lines__project_id__in=project_ids,
        )
        .values("lines__project_id")
        .annotate(pending_timesheet_count=Count("id", distinct=True))
    }
    missing_counts_by_project = _project_missing_timesheet_counts(project_ids)

    rows = []
    for project in projects:
        can_open_detail = current_user.is_ts_admin or (
            current_user.has_role("PROJECT_OWNER")
            and project.project_owner_employee_id == current_user.employee_id
        )
        can_open_pending = (
            current_user.has_role("PROJECT_OWNER")
            and project.project_owner_employee_id == current_user.employee_id
        )
        rows.append(
            {
                "name": project.name,
                "name_href": f"/system/projects/{project.id}/" if can_open_detail else "",
                "status": project.status.value_code,
                "approved_hours": _format_hours(approved_hours_by_project.get(project.id)),
                "approved_hours_href": f"/reports/project-time/?project_id={project.id}",
                "pending_timesheets": str(pending_timesheets_by_project.get(project.id, 0)),
                "pending_timesheets_href": (
                    f"/approvals/?project_id={project.id}" if can_open_pending else ""
                ),
                "missing_timesheets": str(missing_counts_by_project.get(project.id, 0)),
                "missing_timesheets_href": f"/reports/missing-timesheets/?project_ids={project.id}",
            }
        )
    return rows


def _default_week_start_date_value() -> str:
    return _current_monday().isoformat()


def _selected_week_start_date_value(request: HttpRequest) -> str:
    if request.method == "POST":
        candidate = request.POST.get("week_start_date", "")
    else:
        candidate = request.GET.get("week_start_date", "")
    if candidate:
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError:
            pass
    return _default_week_start_date_value()


def _editor_row_count(existing_line_count: int) -> int:
    return max(INITIAL_EMPTY_EDITOR_ROWS, existing_line_count + 1)


def _timesheet_rows(timesheets: list[dict]) -> list[dict]:
    def _short_date(value: str | None) -> str:
        if not value:
            return ""
        return date.fromisoformat(value).strftime("%m/%d/%Y")

    def _short_datetime(value: str | None, *, empty_label: str) -> str:
        if not value:
            return empty_label
        normalized_value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized_value).strftime("%m/%d/%Y")

    return [
        {
            "href": (
                f"/ts/?week_start_date={timesheet['week_start_date']}#create-timesheet"
                if timesheet.get("is_missing")
                else f"/ts/timesheets/{timesheet['id']}/"
            ),
            "cells": [
                _short_date(timesheet["week_start_date"]),
                _short_date(timesheet["week_end_date"]),
                timesheet["status"],
                (
                    "-"
                    if timesheet.get("is_missing")
                    else _short_datetime(
                        timesheet["submission_datetime"],
                        empty_label="Not submitted",
                    )
                ),
                (
                    "-"
                    if timesheet.get("is_missing")
                    else _short_datetime(
                        timesheet["final_approval_datetime"],
                        empty_label="Not approved",
                    )
                ),
            ],
        }
        for timesheet in timesheets
    ]


def _line_options(items: list[dict], *, id_key: str, label_keys: tuple[str, ...]) -> list[dict]:
    options = [{"value": "", "label": "None"}]
    options.extend(
        {
            "value": str(item[id_key]),
            "label": " - ".join(str(item[key]) for key in label_keys if item.get(key)),
        }
        for item in items
    )
    return options


def _line_rows(
    *,
    timesheet: dict,
    row_count: int,
    available_work_dates: list[str],
    available_projects: list[dict],
    available_general_charge_codes: list[dict],
    post_data=None,
) -> list[dict]:
    existing_lines = timesheet["lines"]
    project_options = _line_options(
        available_projects,
        id_key="id",
        label_keys=("project_code", "name"),
    )
    general_charge_code_options = _line_options(
        available_general_charge_codes,
        id_key="id",
        label_keys=("code", "name"),
    )
    date_options = [
        {
            "value": work_date,
            "label": date.fromisoformat(work_date).strftime("%a %Y-%m-%d"),
        }
        for work_date in available_work_dates
    ]

    rows = []
    for index in range(row_count):
        line = existing_lines[index] if index < len(existing_lines) and post_data is None else None
        if post_data is not None:
            work_date = post_data.get(f"line_{index}_work_date", "")
            hours = post_data.get(f"line_{index}_hours", "")
            project_id = post_data.get(f"line_{index}_project_id", "")
            general_charge_code_id = post_data.get(f"line_{index}_general_charge_code_id", "")
            comment_text = post_data.get(f"line_{index}_comment_text", "")
        else:
            work_date = line["work_date"] if line else ""
            hours = line["hours"] if line else ""
            project_id = str(line["project"]["id"]) if line and line["project"] else ""
            general_charge_code_id = (
                str(line["general_charge_code"]["id"])
                if line and line["general_charge_code"]
                else ""
            )
            comment_text = line["comment_text"] if line else ""

        rows.append(
            {
                "index": index,
                "work_date": work_date,
                "hours": hours,
                "project_id": project_id,
                "general_charge_code_id": general_charge_code_id,
                "comment_text": comment_text,
                "date_options": [
                    {
                        **option,
                        "selected": option["value"] == work_date,
                    }
                    for option in date_options
                ],
                "project_options": [
                    {
                        **option,
                        "selected": option["value"] == project_id,
                    }
                    for option in project_options
                ],
                "general_charge_code_options": [
                    {
                        **option,
                        "selected": option["value"] == general_charge_code_id,
                    }
                    for option in general_charge_code_options
                ],
            }
        )
    return rows


def _lines_payload_from_post(request: HttpRequest, *, row_count: int) -> list[dict]:
    lines = []
    for index in range(row_count):
        work_date = request.POST.get(f"line_{index}_work_date", "").strip()
        hours = request.POST.get(f"line_{index}_hours", "").strip()
        project_id = request.POST.get(f"line_{index}_project_id", "").strip()
        general_charge_code_id = request.POST.get(
            f"line_{index}_general_charge_code_id", ""
        ).strip()
        comment_text = request.POST.get(f"line_{index}_comment_text", "").strip()
        if not any([work_date, hours, project_id, general_charge_code_id, comment_text]):
            continue
        lines.append(
            {
                "work_date": work_date,
                "hours": hours,
                "project_id": project_id or None,
                "general_charge_code_id": general_charge_code_id or None,
                "comment_text": comment_text,
            }
        )
    return lines


def _row_count_from_post(request: HttpRequest) -> int:
    try:
        row_count = int(request.POST.get("row_count", str(INITIAL_EMPTY_EDITOR_ROWS)))
    except ValueError:
        return INITIAL_EMPTY_EDITOR_ROWS
    return max(INITIAL_EMPTY_EDITOR_ROWS, row_count)


@require_http_methods(["GET", "POST"])
def my_timesheets(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    create_error = ""
    if request.method == "POST":
        try:
            timesheet = TimesheetService.create_timesheet(
                current_user,
                {"week_start_date": request.POST.get("week_start_date", "")},
            )
        except AuthError as error:
            create_error = error.message
        else:
            return redirect(f"/ts/timesheets/{timesheet['id']}/")

    timesheets = TimesheetService.list_timesheets(current_user)
    context = _ts_context(
        request,
        current_user,
        title="My Timesheets",
        eyebrow="SCR-200",
        intro=(
            "Create a weekly timesheet, open editable weeks, and review your personal week history in one list."
        ),
    )
    context.update(
        {
            "table_headers": (
                "Week Start",
                "Week End",
                "Status",
                "Submitted At",
                "Approved At",
            ),
            "table_rows": _timesheet_rows(timesheets),
            "empty_message": "No weekly timesheets exist yet. Create your first week to begin.",
            "create_week_start_date": _selected_week_start_date_value(request),
            "create_error": create_error,
        }
    )
    return render(request, "core/ts_collection.html", context)


@require_GET
def my_history(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    return redirect("/ts/")


@require_GET
def project_management(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not _can_open_project_management(current_user):
        return _render_access_denied(
            request,
            message="You do not have permission to open project management.",
        )

    selected_status_code, status_links = _project_management_status_links(request)
    queryset = _scoped_project_queryset(current_user).order_by(
        "business_unit__bu_code",
        "project_code",
    )
    if selected_status_code != "ALL":
        queryset = queryset.filter(status__value_code=selected_status_code)
    projects = list(queryset)

    context = _ts_context(
        request,
        current_user,
        title="Project Management",
        eyebrow="SCR-211",
        intro=(
            "Role-aware project summary with drill-down access into project "
            "details, approval worklists, and scoped reports."
        ),
    )
    context.update(
        {
            "filter_links": status_links,
            "table_rows": _project_management_rows(current_user, projects),
        }
    )
    return render(request, "core/project_management.html", context)


@require_http_methods(["GET", "POST"])
def timesheet_detail(request: HttpRequest, timesheet_id: int) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "lines"
    form_error = ""
    if request.method == "POST":
        active_form = request.POST.get("form_name", "lines")
        row_count = _row_count_from_post(request)
        try:
            if active_form == "lines":
                TimesheetService.replace_lines(
                    current_user,
                    timesheet_id,
                    {"lines": _lines_payload_from_post(request, row_count=row_count)},
                )
            elif active_form == "submit":
                TimesheetService.submit_timesheet(
                    current_user,
                    timesheet_id,
                    {"comment_text": request.POST.get("comment_text", "")},
                )
            elif active_form == "withdraw":
                TimesheetService.withdraw_timesheet(
                    current_user,
                    timesheet_id,
                    {"comment_text": request.POST.get("comment_text", "")},
                )
            elif active_form == "delete":
                TimesheetService.delete_timesheet(current_user, timesheet_id)
                return redirect("/ts/")
            else:
                raise AuthError("UI_FORM_UNKNOWN", "Unknown timesheet form submission.", 400)
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/ts/timesheets/{timesheet_id}/")

    try:
        editor_context = TimesheetService.get_timesheet_editor_context(current_user, timesheet_id)
    except AuthError as error:
        return _render_timesheet_auth_error(
            request,
            current_user,
            title="Timesheet Detail",
            eyebrow="SCR-202",
            intro="Requested timesheet could not be loaded in the current session scope.",
            error=error,
        )

    timesheet = editor_context["timesheet"]
    can_edit = editor_context["can_edit"]
    row_count = (
        _row_count_from_post(request)
        if request.method == "POST" and active_form == "lines"
        else _editor_row_count(len(timesheet["lines"]))
    )
    context = _ts_context(
        request,
        current_user,
        title=f"Week of {timesheet['week_start_date']}",
        eyebrow="SCR-201" if can_edit else "SCR-202",
        intro=(
            "Edit line entries and manage submission for this weekly timesheet."
            if can_edit
            else "Read-only timesheet detail for the selected weekly record."
        ),
    )
    context.update(
        {
            "timesheet": timesheet,
            "employee": editor_context["employee"],
            "line_rows": _line_rows(
                timesheet=timesheet,
                row_count=row_count,
                available_work_dates=editor_context["available_work_dates"],
                available_projects=editor_context["available_projects"],
                available_general_charge_codes=editor_context["available_general_charge_codes"],
                post_data=request.POST
                if request.method == "POST" and active_form == "lines"
                else None,
            ),
            "row_count": row_count,
            "can_edit": can_edit,
            "can_submit": editor_context["can_submit"],
            "submit_blockers": editor_context["submit_blockers"],
            "can_withdraw": editor_context["can_withdraw"],
            "can_delete": editor_context["can_delete"],
            "available_projects": editor_context["available_projects"],
            "available_general_charge_codes": editor_context["available_general_charge_codes"],
            "active_form": active_form,
            "form_error": form_error,
            "submit_comment": request.POST.get("comment_text", "")
            if request.method == "POST" and active_form == "submit"
            else "",
            "withdraw_comment": request.POST.get("comment_text", "")
            if request.method == "POST" and active_form == "withdraw"
            else "",
        }
    )
    return render(request, "core/ts_detail.html", context)


@require_GET
def project_time_inquiry(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not (current_user.has_role("PROJECT_OWNER") or current_user.has_role("PROJECT_MANAGER")):
        return _render_access_denied(
            request,
            message="You do not have permission to open project time inquiry.",
        )

    return render_report_view(
        request,
        current_user,
        "project-time",
        title="Project Time Inquiry",
        eyebrow="SCR-210",
        intro=(
            "Project-scoped inquiry for owned or managed projects, using the same "
            "row-level scope rules as the live project-time report."
        ),
        report_path="/ts/inquiry/",
        back_href="/ts/",
        back_label="Back to My Timesheets",
    )
