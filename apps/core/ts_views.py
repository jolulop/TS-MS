from datetime import date, timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.timesheets.services import TimesheetService

EDITOR_ROW_COUNT = 8


def _timesheet_section_links(current_user: CurrentUser, current_path: str) -> list[dict]:
    links = [
        {
            "label": "My Timesheets",
            "href": "/ts/",
            "active": current_path == "/ts/",
        },
        {
            "label": "My History",
            "href": "/ts/history/",
            "active": current_path == "/ts/history/",
        },
    ]
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


def _timesheet_rows(timesheets: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/ts/timesheets/{timesheet['id']}/",
            "cells": [
                timesheet["week_start_date"],
                timesheet["week_end_date"],
                timesheet["status"],
                str(timesheet["line_count"]),
                str(timesheet["current_submission_no"]),
            ],
        }
        for timesheet in timesheets
    ]


def _history_rows(timesheets: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/ts/timesheets/{timesheet['id']}/",
            "cells": [
                timesheet["week_start_date"],
                timesheet["week_end_date"],
                timesheet["status"],
                timesheet["submission_datetime"] or "Not submitted",
                timesheet["final_approval_datetime"] or "Not approved",
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
    available_projects: list[dict],
    available_general_charge_codes: list[dict],
    post_data=None,
) -> list[dict]:
    existing_lines = timesheet["lines"]
    row_count = max(EDITOR_ROW_COUNT, len(existing_lines) + 3)
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
            "value": (
                date.fromisoformat(timesheet["week_start_date"]) + timedelta(days=offset)
            ).isoformat(),
            "label": (
                date.fromisoformat(timesheet["week_start_date"]) + timedelta(days=offset)
            ).strftime("%a %Y-%m-%d"),
        }
        for offset in range(5)
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
        row_count = int(request.POST.get("row_count", str(EDITOR_ROW_COUNT)))
    except ValueError:
        return EDITOR_ROW_COUNT
    return max(EDITOR_ROW_COUNT, row_count)


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
            "Create a weekly timesheet, open editable weeks, and track the current lifecycle state."
        ),
    )
    context.update(
        {
            "table_headers": ("Week Start", "Week End", "Status", "Lines", "Submission No."),
            "table_rows": _timesheet_rows(timesheets),
            "empty_message": "No weekly timesheets exist yet. Create your first week to begin.",
            "default_week_start_date": request.POST.get(
                "week_start_date",
                _current_monday().isoformat(),
            ),
            "create_error": create_error,
        }
    )
    return render(request, "core/ts_collection.html", context)


@require_GET
def my_history(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    timesheets = TimesheetService.list_timesheets(current_user)
    context = _ts_context(
        request,
        current_user,
        title="My History",
        eyebrow="SCR-220",
        intro=(
            "Read-only history of your weekly timesheets across submitted, "
            "approved, rejected, and archived states."
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
            "table_rows": _history_rows(timesheets),
            "empty_message": "Your timesheet history is empty.",
        }
    )
    return render(request, "core/ts_history.html", context)


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
    context = _ts_context(
        request,
        current_user,
        title=f"Week Of {timesheet['week_start_date']}",
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
                available_projects=editor_context["available_projects"],
                available_general_charge_codes=editor_context["available_general_charge_codes"],
                post_data=request.POST
                if request.method == "POST" and active_form == "lines"
                else None,
            ),
            "row_count": max(EDITOR_ROW_COUNT, len(timesheet["lines"]) + 3),
            "can_edit": can_edit,
            "can_submit": editor_context["can_submit"],
            "can_withdraw": editor_context["can_withdraw"],
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
def project_time_inquiry_placeholder(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not (current_user.has_role("PROJECT_OWNER") or current_user.has_role("PROJECT_MANAGER")):
        return _render_access_denied(
            request,
            message="You do not have permission to open project time inquiry.",
        )

    context = _ts_context(
        request,
        current_user,
        title="Project Time Inquiry",
        eyebrow="SCR-210",
        intro=(
            "Project-scoped inquiry remains deferred while Milestone 3 focuses "
            "on self-service timesheet screens."
        ),
    )
    context["section_cards"] = [
        {
            "title": "Inquiry UI Deferred",
            "summary": (
                "Project-owner and project-manager inquiry screens will be added "
                "after the core self-service timesheet pages."
            ),
            "status": "Planned",
        }
    ]
    return render(request, "core/section_overview.html", context)
