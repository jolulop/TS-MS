from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.timesheets.services import TimesheetService


def _approval_context(
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


def _render_approval_auth_error(
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

    context = _approval_context(
        request,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )
    context["denied_message"] = error.message
    return render(request, "core/access_denied.html", context, status=error.status)


def _project_label(approval_item: dict) -> str:
    project = approval_item.get("project")
    if not project:
        return "General scope"
    return f"{project['project_code']} - {project['name']}"


def _employee_label(approval_item: dict) -> str:
    employee = approval_item["timesheet_employee"]
    return f"{employee['full_name']} ({employee['employee_code']})"


def _approval_rows(approval_items: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/approvals/{approval_item['id']}/",
            "cells": [
                _employee_label(approval_item),
                _project_label(approval_item),
                str(approval_item["submission_no"]),
                approval_item["status"],
                approval_item["rejection_reason"] or "Pending review",
            ],
        }
        for approval_item in approval_items
    ]


def _line_target_label(line: dict) -> str:
    if line["project"] is not None:
        return f"{line['project']['project_code']} - {line['project']['name']}"
    if line["general_charge_code"] is not None:
        return f"{line['general_charge_code']['code']} - {line['general_charge_code']['name']}"
    return "None"


@require_GET
def approval_worklist(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    try:
        approval_items = TimesheetService.list_approval_items(current_user)
    except AuthError as error:
        return _render_approval_auth_error(
            request,
            current_user,
            title="Approval Worklist",
            eyebrow="SCR-205",
            intro="Managed-project approvals waiting for your decision.",
            error=error,
        )

    pending_items = [item for item in approval_items if item["status"] == "PENDING"]
    decided_items = [item for item in approval_items if item["status"] != "PENDING"]

    context = _approval_context(
        request,
        title="Approval Worklist",
        eyebrow="SCR-205",
        intro=(
            "Managed-project approvals waiting for your decision, with completed "
            "items kept visible for audit-friendly follow-up."
        ),
    )
    context.update(
        {
            "pending_count": len(pending_items),
            "decided_count": len(decided_items),
            "pending_rows": _approval_rows(pending_items),
            "decided_rows": _approval_rows(decided_items),
        }
    )
    return render(request, "core/approval_collection.html", context)


@require_http_methods(["GET", "POST"])
def approval_detail(request: HttpRequest, approval_item_id: int) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "approve"
    form_error = ""
    approve_comment = ""
    reject_reason = ""

    if request.method == "POST":
        active_form = request.POST.get("form_name", "approve")
        approve_comment = request.POST.get("comment_text", "")
        reject_reason = request.POST.get("reason_text", "")

        try:
            if active_form == "approve":
                TimesheetService.approve_approval_item(
                    current_user,
                    approval_item_id,
                    {"comment_text": approve_comment},
                )
            elif active_form == "reject":
                TimesheetService.reject_approval_item(
                    current_user,
                    approval_item_id,
                    {"reason_text": reject_reason},
                )
            else:
                raise AuthError(
                    "APPROVAL_ACTION_UNKNOWN",
                    "Unsupported approval action.",
                    400,
                )
        except AuthError as error:
            if error.status == 403:
                return _render_approval_auth_error(
                    request,
                    current_user,
                    title=f"Approval Item #{approval_item_id}",
                    eyebrow="SCR-206",
                    intro="Review the routed project lines before recording a decision.",
                    error=error,
                )
            form_error = error.message
        else:
            return redirect(request.path)

    try:
        approval_item = TimesheetService.get_approval_item(current_user, approval_item_id)
    except AuthError as error:
        return _render_approval_auth_error(
            request,
            current_user,
            title=f"Approval Item #{approval_item_id}",
            eyebrow="SCR-206",
            intro="Review the routed project lines before recording a decision.",
            error=error,
        )

    context = _approval_context(
        request,
        title=f"Approval Item #{approval_item_id}",
        eyebrow="SCR-206",
        intro="Review the routed project lines before recording a decision.",
    )
    context.update(
        {
            "approval_item": approval_item,
            "approval_project_label": _project_label(approval_item),
            "timesheet_employee_label": _employee_label(approval_item),
            "can_decide": approval_item["status"] == "PENDING",
            "line_rows": [
                {
                    "work_date": line["work_date"],
                    "hours": line["hours"],
                    "charge_target": _line_target_label(line),
                    "approval_state": line["approval_state"] or "Not routed",
                    "comment_text": line["comment_text"] or "",
                }
                for line in approval_item.get("lines", [])
            ],
            "active_form": active_form,
            "form_error": form_error,
            "approve_comment": approve_comment,
            "reject_reason": reject_reason,
        }
    )
    return render(request, "core/approval_detail.html", context)
