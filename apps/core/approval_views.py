from datetime import datetime
from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.common.urls import safe_local_path
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.timesheets.models import ApprovalItem
from apps.timesheets.services import TimesheetService

STALLED_APPROVAL_DAYS = 7


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


def _approval_target_label(approval_item: dict) -> str:
    project = approval_item.get("project")
    if project:
        return f"{project['project_code']} - {project['name']}"
    general_charge_code = approval_item.get("general_charge_code")
    if general_charge_code:
        return f"{general_charge_code['code']} - {general_charge_code['name']}"
    return "General scope"


def _approval_target_kind(approval_item: dict) -> str:
    if approval_item.get("project") is not None:
        return "PROJECT"
    if approval_item.get("general_charge_code") is not None:
        return "GENERAL_CHARGE_CODE"
    return "GENERAL"


def _employee_label(approval_item: dict) -> str:
    employee = approval_item["timesheet_employee"]
    return employee["full_name"]


def _approver_label(approval_item: dict) -> str:
    approver_employee = approval_item.get("approver_employee")
    if approver_employee is not None:
        return approver_employee["full_name"]
    approver_roles = approval_item.get("approver_roles", [])
    if approver_roles:
        return ", ".join(
            f"{approver_role['code']} - {approver_role['name']}" for approver_role in approver_roles
        )
    return "Unassigned"


def _submission_date_label(approval_item: dict) -> str:
    value = approval_item["timesheet"].get("submission_datetime")
    if not value:
        return "Not submitted"
    normalized_value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized_value).strftime("%m/%d/%Y")


def _pending_age_label(approval_item: dict) -> str:
    return f"{approval_item['pending_age_days']}d"


def _stalled_label(approval_item: dict) -> str:
    return "Stalled" if approval_item["stalled_flag"] else "Active"


def _approval_detail_href(approval_item_id: int, *, back_href: str) -> str:
    query = urlencode({"back": back_href})
    return f"/approvals/{approval_item_id}/?{query}"


def _approval_rows(
    approval_items: list[dict],
    *,
    back_href: str,
    admin_oversight: bool,
) -> list[dict]:
    rows: list[dict] = []
    for approval_item in approval_items:
        cells = (
            [
                _employee_label(approval_item),
                _approval_target_label(approval_item),
                approval_item["business_unit"]["bu_code"],
                _approver_label(approval_item),
                _submission_date_label(approval_item),
                _pending_age_label(approval_item),
                _stalled_label(approval_item),
            ]
            if admin_oversight
            else [
                _employee_label(approval_item),
                _approval_target_label(approval_item),
                str(approval_item["submission_no"]),
                approval_item["status"],
                approval_item["rejection_reason"] or "Pending review",
            ]
        )
        rows.append(
            {
                "href": _approval_detail_href(approval_item["id"], back_href=back_href),
                "cells": cells,
            }
        )
    return rows


def _line_target_label(line: dict) -> str:
    if line["project"] is not None:
        return f"{line['project']['project_code']} - {line['project']['name']}"
    if line["general_charge_code"] is not None:
        return f"{line['general_charge_code']['code']} - {line['general_charge_code']['name']}"
    return "None"


def _oversight_filter_value(request: HttpRequest, name: str, default: str = "") -> str:
    return str(request.GET.get(name, default)).strip()


def _oversight_filter_options(
    approval_items: list[dict],
    *,
    option_type: str,
    selected_value: str,
) -> list[dict]:
    option_map: dict[str, str] = {}
    for approval_item in approval_items:
        if option_type == "business_unit":
            option_map[str(approval_item["business_unit"]["id"])] = (
                f"{approval_item['business_unit']['bu_code']} - "
                f"{approval_item['business_unit']['name']}"
            )
        elif option_type == "employee":
            option_map[str(approval_item["timesheet_employee"]["id"])] = _employee_label(
                approval_item
            )
        elif option_type == "project":
            project = approval_item.get("project")
            if project is not None:
                option_map[str(project["id"])] = f"{project['project_code']} - {project['name']}"
    options = [{"value": "", "label": "All", "selected": selected_value == ""}]
    options.extend(
        {
            "value": option_value,
            "label": option_label,
            "selected": selected_value == option_value,
        }
        for option_value, option_label in sorted(
            option_map.items(),
            key=lambda item: item[1],
        )
    )
    return options


def _apply_admin_oversight_filters(
    request: HttpRequest,
    approval_items: list[dict],
) -> tuple[list[dict], list[dict]]:
    search_query = _oversight_filter_value(request, "q").lower()
    business_unit_id = _oversight_filter_value(request, "business_unit_id")
    employee_id = _oversight_filter_value(request, "employee_id")
    project_id = _oversight_filter_value(request, "project_id")
    target_kind = _oversight_filter_value(request, "target_kind", "ALL").upper() or "ALL"
    aging = _oversight_filter_value(request, "aging", "ALL").upper() or "ALL"

    filtered_items = approval_items
    if business_unit_id.isdigit():
        filtered_items = [
            item for item in filtered_items if item["business_unit"]["id"] == int(business_unit_id)
        ]
    if employee_id.isdigit():
        filtered_items = [
            item for item in filtered_items if item["timesheet_employee"]["id"] == int(employee_id)
        ]
    if project_id.isdigit():
        filtered_items = [
            item
            for item in filtered_items
            if item.get("project") is not None and item["project"]["id"] == int(project_id)
        ]
    if target_kind != "ALL":
        filtered_items = [
            item for item in filtered_items if _approval_target_kind(item) == target_kind
        ]
    if aging == "STALLED":
        filtered_items = [item for item in filtered_items if item["stalled_flag"]]
    if search_query:
        filtered_items = [
            item
            for item in filtered_items
            if search_query
            in " ".join(
                [
                    item["timesheet_employee"]["employee_code"],
                    item["timesheet_employee"]["full_name"],
                    item["business_unit"]["bu_code"],
                    item["business_unit"]["name"],
                    _approval_target_label(item),
                    _approver_label(item),
                ]
            ).lower()
        ]

    filters = [
        {
            "label": "Search",
            "name": "q",
            "type": "text",
            "value": _oversight_filter_value(request, "q"),
        },
        {
            "label": "Business Unit",
            "name": "business_unit_id",
            "type": "select",
            "value": business_unit_id,
            "options": _oversight_filter_options(
                approval_items,
                option_type="business_unit",
                selected_value=business_unit_id,
            ),
        },
        {
            "label": "Employee",
            "name": "employee_id",
            "type": "select",
            "value": employee_id,
            "options": _oversight_filter_options(
                approval_items,
                option_type="employee",
                selected_value=employee_id,
            ),
        },
        {
            "label": "Project",
            "name": "project_id",
            "type": "select",
            "value": project_id,
            "options": _oversight_filter_options(
                approval_items,
                option_type="project",
                selected_value=project_id,
            ),
        },
        {
            "label": "Target Type",
            "name": "target_kind",
            "type": "select",
            "value": target_kind,
            "options": [
                {
                    "value": "ALL",
                    "label": "All",
                    "selected": target_kind == "ALL",
                },
                {
                    "value": "PROJECT",
                    "label": "Project",
                    "selected": target_kind == "PROJECT",
                },
                {
                    "value": "GENERAL_CHARGE_CODE",
                    "label": "General Charge Code",
                    "selected": target_kind == "GENERAL_CHARGE_CODE",
                },
            ],
        },
        {
            "label": "Aging",
            "name": "aging",
            "type": "select",
            "value": aging,
            "options": [
                {"value": "ALL", "label": "All", "selected": aging == "ALL"},
                {
                    "value": "STALLED",
                    "label": f"Stalled ({STALLED_APPROVAL_DAYS}+ days)",
                    "selected": aging == "STALLED",
                },
            ],
        },
    ]
    return filtered_items, filters


@require_GET
def approval_worklist(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    admin_oversight = current_user.is_ts_admin

    try:
        approval_items = TimesheetService.list_approval_items(current_user)
    except AuthError as error:
        return _render_approval_auth_error(
            request,
            current_user,
            title="Approval Worklist",
            eyebrow="SCR-305" if admin_oversight else "SCR-205",
            intro=(
                "Scoped pending approvals, aging visibility, and related timesheet "
                "exception handling."
                if admin_oversight
                else "Routed approval items waiting for your decision."
            ),
            error=error,
        )

    if admin_oversight:
        filtered_items, filters = _apply_admin_oversight_filters(request, approval_items)
        pending_items = [item for item in filtered_items if item["status"] == "PENDING"]
        pending_items.sort(
            key=lambda item: (
                0 if item["stalled_flag"] else 1,
                -item["pending_age_days"],
                item["timesheet"]["week_start_date"],
                item["id"],
            )
        )
        decided_items = [item for item in filtered_items if item["status"] != "PENDING"]
        title = "Approval Worklist"
        eyebrow = "SCR-305"
        intro = (
            "Monitor pending approvals across your scoped Business Units, inspect "
            "aging and approver context, and follow through into related timesheet "
            "exception actions when operational cleanup is needed."
        )
        pending_headers = (
            "Employee",
            "Target",
            "BU",
            "Approver",
            "TS Submission Date",
            "Pending Age",
            "Queue State",
        )
        decided_headers = (
            "Employee",
            "Target",
            "BU",
            "Approver",
            "TS Submission Date",
            "Timesheet Status",
            "Outcome",
        )
        pending_rows = _approval_rows(
            pending_items,
            back_href=safe_local_path(
                f"{request.path}?{request.GET.urlencode()}" if request.GET else request.path,
                default="/approvals/",
            ),
            admin_oversight=True,
        )
        decided_rows = [
            {
                "href": _approval_detail_href(
                    approval_item["id"],
                    back_href=safe_local_path(
                        f"{request.path}?{request.GET.urlencode()}"
                        if request.GET
                        else request.path,
                        default="/approvals/",
                    ),
                ),
                "cells": [
                    _employee_label(approval_item),
                    _approval_target_label(approval_item),
                    approval_item["business_unit"]["bu_code"],
                    _approver_label(approval_item),
                    _submission_date_label(approval_item),
                    approval_item["timesheet"]["status"],
                    approval_item["status"],
                ],
            }
            for approval_item in decided_items
        ]
        context = _approval_context(
            request,
            title=title,
            eyebrow=eyebrow,
            intro=intro,
        )
        context.update(
            {
                "is_admin_oversight": True,
                "filters": filters,
                "pending_headers": pending_headers,
                "decided_headers": decided_headers,
                "pending_rows": pending_rows,
                "decided_rows": decided_rows,
                "pending_action_label": "Open Detail",
                "decided_action_label": "Review Item",
                "pending_empty_message": (
                    "No pending approval items match the current oversight filters."
                ),
                "decided_empty_message": (
                    "No recent non-pending approval items match the current oversight filters."
                ),
                "pending_section_intro": (
                    f"{len(pending_items)} pending item(s), "
                    f"{sum(1 for item in pending_items if item['stalled_flag'])} "
                    "stalled for 7 or more days."
                ),
                "decided_section_intro": (
                    "Recently completed items stay visible here for audit-friendly "
                    "follow-up and related timesheet exception handling."
                ),
            }
        )
        return render(request, "core/approval_collection.html", context)

    selected_project_id = request.GET.get("project_id", "").strip()
    if selected_project_id.isdigit():
        project_id = int(selected_project_id)
        approval_items = [
            item
            for item in approval_items
            if item.get("project") is not None and item["project"]["id"] == project_id
        ]

    pending_items = [item for item in approval_items if item["status"] == "PENDING"]
    decided_items = [item for item in approval_items if item["status"] != "PENDING"]
    back_href = safe_local_path(
        f"{request.path}?{request.GET.urlencode()}" if request.GET else request.path,
        default="/approvals/",
    )

    context = _approval_context(
        request,
        title="Approval Worklist",
        eyebrow="SCR-205",
        intro=(
            "Routed approval items waiting for your review or decision, with "
            "completed items kept visible for audit-friendly follow-up."
        ),
    )
    context.update(
        {
            "is_admin_oversight": False,
            "pending_headers": (
                "Employee",
                "Project Scope",
                "Submission No.",
                "Status",
                "Decision Context",
            ),
            "decided_headers": (
                "Employee",
                "Project Scope",
                "Submission No.",
                "Status",
                "Reason",
            ),
            "pending_rows": _approval_rows(
                pending_items,
                back_href=back_href,
                admin_oversight=False,
            ),
            "decided_rows": _approval_rows(
                decided_items,
                back_href=back_href,
                admin_oversight=False,
            ),
            "pending_action_label": "Open Review",
            "decided_action_label": "View Detail",
            "pending_empty_message": (
                "No pending approval items are waiting in your current approval scope."
            ),
            "decided_empty_message": (
                "No completed approval decisions exist yet in your current scope."
            ),
            "pending_section_intro": (
                "Open a work item to review the routed project lines and record the final decision."
            ),
            "decided_section_intro": (
                "Approved and rejected items stay visible here for follow-up and "
                "audit-friendly context."
            ),
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
    back_href = safe_local_path(request.GET.get("back"), default="/approvals/")

    if request.method == "POST":
        active_form = request.POST.get("form_name", "approve")
        approve_comment = request.POST.get("comment_text", "")
        reject_reason = request.POST.get("reason_text", "")
        back_href = safe_local_path(request.POST.get("back"), default=back_href)

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
                    intro="Review the routed timesheet lines before recording a decision.",
                    error=error,
                )
            form_error = error.message
        else:
            query = urlencode({"back": back_href}) if back_href else ""
            return redirect(f"{request.path}?{query}" if query else request.path)

    try:
        approval_item = TimesheetService.get_approval_item(current_user, approval_item_id)
    except AuthError as error:
        return _render_approval_auth_error(
            request,
            current_user,
            title=f"Approval Item #{approval_item_id}",
            eyebrow="SCR-206",
            intro="Review the routed timesheet lines before recording a decision.",
            error=error,
        )

    approval_item_record = (
        ApprovalItem.objects.select_related(
            "project",
            "submission_cycle",
            "submission_cycle__weekly_timesheet",
        )
        .prefetch_related(
            "approver_roles__existing_role",
            "approver_roles__approval_role",
        )
        .get(id=approval_item_id)
    )
    related_timesheet_href = f"/ts/timesheets/{approval_item['timesheet_id']}/"
    if back_href:
        related_timesheet_href = f"{related_timesheet_href}?{urlencode({'next': back_href})}"
    related_project_href = (
        f"/system/projects/{approval_item['project']['id']}/"
        if approval_item.get("project") is not None
        else ""
    )
    context = _approval_context(
        request,
        title=f"Approval Item #{approval_item_id}",
        eyebrow="SCR-206",
        intro=(
            "Review the routed timesheet lines and related context. Approval "
            "authority still comes only from the routed approver assignment."
        ),
    )
    context.update(
        {
            "approval_item": approval_item,
            "approval_project_label": _approval_target_label(approval_item),
            "approval_approver_label": _approver_label(approval_item),
            "timesheet_employee_label": _employee_label(approval_item),
            "timesheet_submission_date_label": _submission_date_label(approval_item),
            "can_decide": AuthorizationPolicyService.can_approve_approval_item(
                current_user,
                approval_item_record,
            ),
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
            "back_href": back_href,
            "related_timesheet_href": related_timesheet_href,
            "related_project_href": related_project_href,
            "is_admin_oversight": current_user.is_ts_admin,
            "pending_age_label": _pending_age_label(approval_item),
            "queue_state_label": _stalled_label(approval_item),
        }
    )
    return render(request, "core/approval_detail.html", context)
