from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.services import SessionInitializationService
from apps.core.ui import build_navigation
from apps.master_data.models import Employee, Project
from apps.timesheets.models import ApprovalItem, WeeklyTimesheet


def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok", "service": "tsms"})


def _require_user(request: HttpRequest) -> CurrentUser | HttpResponse:
    current_user = getattr(request, "ts_user", None)
    if current_user is None:
        return redirect("home")
    return current_user


def _page_context(
    request: HttpRequest,
    *,
    title: str,
    eyebrow: str,
    intro: str,
) -> dict:
    current_user = getattr(request, "ts_user", None)
    context = {
        "page_title": title,
        "page_eyebrow": eyebrow,
        "page_intro": intro,
        "current_user": current_user,
        "navigation_groups": (
            build_navigation(current_user, current_path=request.path) if current_user else ()
        ),
    }
    if current_user is not None:
        context["role_summary"] = ", ".join(current_user.role_codes)
        context["business_unit_summary"] = ", ".join(
            unit.bu_code for unit in current_user.scoped_business_units
        )
        context["office_summary"] = current_user.office_name
    return context


def _render_access_denied(
    request: HttpRequest,
    *,
    message: str,
    status: int = 403,
) -> HttpResponse:
    context = _page_context(
        request,
        title="Access Denied",
        eyebrow="Session",
        intro="The requested page is outside your current TS role and scope.",
    )
    context["denied_message"] = message
    return render(request, "core/access_denied.html", context, status=status)


def _dashboard_cards(current_user: CurrentUser) -> list[dict]:
    cards = [
        {
            "title": "My Timesheets",
            "value": WeeklyTimesheet.objects.filter(employee_id=current_user.employee_id).count(),
            "summary": "Weekly records available in your current TS history.",
            "href": "/ts/",
        },
        {
            "title": "Assigned Business Units",
            "value": len(current_user.scoped_business_units),
            "summary": "Business Unit scope loaded into the current internal session.",
            "href": "/profile/",
        },
    ]

    if current_user.has_role("PROJECT_MANAGER"):
        pending_count = ApprovalItem.objects.filter(
            approver_employee_id=current_user.employee_id,
            status__domain__domain_code="APPROVAL_STATUS",
            status__value_code="PENDING",
        ).count()
        cards.append(
            {
                "title": "Pending Approvals",
                "value": pending_count,
                "summary": "Approval items waiting in your managed-project scope.",
                "href": "/approvals/",
            }
        )

    if current_user.has_role("PROJECT_OWNER"):
        owned_projects = Project.objects.filter(
            project_owner_employee_id=current_user.employee_id
        ).count()
        cards.append(
            {
                "title": "Owned Projects",
                "value": owned_projects,
                "summary": "Projects where you are currently the owner.",
                "href": "/system/",
            }
        )

    if current_user.is_ts_admin:
        employee_count = Employee.objects.filter(
            primary_business_unit_id__in=current_user.scoped_business_unit_ids
        ).count()
        cards.append(
            {
                "title": "Admin Employee Scope",
                "value": employee_count,
                "summary": "Employees visible inside your assigned Business Units.",
                "href": "/system/",
            }
        )

    return cards


def _overview_cards(section: str, current_user: CurrentUser) -> list[dict]:
    if section == "system":
        cards = []
        if current_user.is_ts_admin_master:
            cards.append(
                {
                    "title": "Offices",
                    "summary": (
                        "Create offices and manage active or inactive lifecycle states "
                        "for office administration."
                    ),
                    "status": "Ready now",
                    "href": "/system/offices/",
                }
            )
        if current_user.is_ts_admin:
            cards.extend(
                [
                    {
                        "title": "Business Units",
                        "summary": (
                            "Review Business Unit identity, lifecycle status, and "
                            "BU-level configuration inside your admin scope."
                        ),
                        "status": "Ready now",
                        "href": "/system/business-units/",
                    },
                    {
                        "title": "Employees",
                        "summary": (
                            "Create and maintain employee identity, internal "
                            "roles, and Business Unit scope."
                        ),
                        "status": "Ready now",
                        "href": "/system/employees/",
                    },
                    {
                        "title": "Calendars",
                        "summary": (
                            "Manage calendar period rules and daily hour limits by calendar."
                        ),
                        "status": "Ready now",
                        "href": "/system/calendar-period-rules/",
                    },
                    {
                        "title": "Clients",
                        "summary": "Manage office-level clients inside the active Office.",
                        "status": "Ready now",
                        "href": "/system/clients/",
                    },
                    {
                        "title": "Internal Categories",
                        "summary": (
                            "Maintain internal category masters used by downstream project setup."
                        ),
                        "status": "Ready now",
                        "href": "/system/internal-categories/",
                    },
                    {
                        "title": "Cost Centers",
                        "summary": (
                            "Maintain office-level cost center masters inside "
                            "the shared admin shell."
                        ),
                        "status": "Ready now",
                        "href": "/system/cost-centers/",
                    },
                    {
                        "title": "General Charge Codes",
                        "summary": (
                            "Maintain general charge code validity, flags, and lifecycle fields."
                        ),
                        "status": "Ready now",
                        "href": "/system/general-charge-codes/",
                    },
                    {
                        "title": "Projects",
                        "summary": (
                            "Manage project ownership, classification, and lifecycle fields."
                        ),
                        "status": "Ready now",
                        "href": "/system/projects/",
                    },
                    {
                        "title": "Project Assignments",
                        "summary": (
                            "Manage project staffing windows and active/inactive assignment scope."
                        ),
                        "status": "Ready now",
                        "href": "/system/project-assignments/",
                    },
                ]
            )
        if current_user.has_role("PROJECT_OWNER"):
            cards.append(
                {
                    "title": "Project Management",
                    "summary": (
                        "TS Admin screens for project and assignment management are now available."
                    ),
                    "status": "Ready now",
                    "href": "/system/projects/",
                }
            )
        return cards

    if section == "ts":
        return [
            {
                "title": "My Timesheets",
                "summary": "Weekly timesheet list and editor UI are scheduled for Milestone 3.",
                "status": "Planned",
            },
            {
                "title": "My History",
                "summary": (
                    "Historical views and read-only timesheet detail will use "
                    "this navigation shell."
                ),
                "status": "Planned",
            },
            {
                "title": "Project Time Inquiry",
                "summary": (
                    "Project owner and manager inquiry screens arrive after core timesheet pages."
                ),
                "status": "Later in phase",
            },
        ]

    if section == "approvals":
        return [
            {
                "title": "Approval Worklist",
                "summary": (
                    "The approval worklist UI will connect to the existing "
                    "approval backend in a later milestone."
                ),
                "status": "Planned",
            },
            {
                "title": "Approval Item Detail",
                "summary": (
                    "Decision pages will be layered in after the core TS management pages exist."
                ),
                "status": "Planned",
            },
        ]

    return [
        {
            "title": "Reports Hub",
            "summary": (
                "Report navigation, filters, and viewers are intentionally "
                "deferred to the last UI milestone."
            ),
            "status": "Deferred",
        },
        {
            "title": "Role-Aware Reporting",
            "summary": (
                "Report visibility will follow internal TS roles and scope rules "
                "from the existing backend."
            ),
            "status": "Deferred",
        },
    ]


@require_http_methods(["GET", "POST"])
def home(request: HttpRequest) -> HttpResponse:
    current_user = getattr(request, "ts_user", None)
    if request.method == "POST":
        validated_email = str(request.POST.get("validated_email", "")).strip()
        if not validated_email:
            context = {
                "validated_email": "",
                "entry_error": "Validated email is required to initialize a local session.",
            }
            return render(request, "core/access_entry.html", context, status=400)
        try:
            SessionInitializationService.initialize(request, validated_email)
        except AuthError as exc:
            context = {
                "validated_email": validated_email,
                "entry_error": exc.message,
            }
            return render(request, "core/access_entry.html", context, status=exc.status)
        return redirect("home")

    if current_user is None:
        return render(request, "core/access_entry.html")

    context = _page_context(
        request,
        title="Dashboard",
        eyebrow="SCR-003",
        intro="Landing page after internal session initialization with role-aware quick actions.",
    )
    context["summary_cards"] = _dashboard_cards(current_user)
    context["quick_actions"] = [
        item
        for group in build_navigation(current_user, current_path=request.path)
        for item in group.items
        if item.href != request.path
    ]
    return render(request, "core/dashboard.html", context)


@require_POST
def logout(request: HttpRequest) -> HttpResponse:
    SessionInitializationService.logout(request)
    return redirect("home")


@require_GET
def profile(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    employee = Employee.objects.select_related(
        "assigned_calendar",
        "primary_business_unit",
        "office",
    ).get(id=current_user.employee_id)
    context = _page_context(
        request,
        title="Session Context",
        eyebrow="SCR-004",
        intro=(
            "Current employee identity, internal roles, and Business Unit "
            "scope loaded into this session."
        ),
    )
    context["profile_rows"] = [
        ("Employee Code", current_user.employee_code),
        ("Full Name", current_user.full_name),
        ("Email", current_user.email),
        ("Active Office", current_user.office_name),
        ("Roles", ", ".join(current_user.role_codes)),
        ("Primary Business Unit", current_user.primary_business_unit_code),
        (
            "Assigned Business Units",
            ", ".join(unit.bu_code for unit in current_user.scoped_business_units),
        ),
        (
            "Assigned Calendar",
            employee.assigned_calendar.calendar_name
            if employee.assigned_calendar
            else "Not assigned",
        ),
    ]
    return render(request, "core/profile.html", context)


@require_GET
def system_management(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not (
        current_user.is_ts_admin
        or current_user.is_ts_admin_master
        or current_user.has_role("PROJECT_OWNER")
    ):
        return _render_access_denied(
            request,
            message="You do not have permission to open System Management.",
        )

    context = _page_context(
        request,
        title="System Management",
        eyebrow="Phase 5 Milestone 2",
        intro=(
            "Role-aware overview for the current administrative screens, with "
            "project-oriented pages still deferred to later milestones."
        ),
    )
    context["section_cards"] = _overview_cards("system", current_user)
    return render(request, "core/section_overview.html", context)


@require_GET
def ts_management(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    context = _page_context(
        request,
        title="TS Management",
        eyebrow="Phase 5 Milestone 1",
        intro="Overview for user timesheets, history, and project-time inquiry screens.",
    )
    context["section_cards"] = _overview_cards("ts", current_user)
    return render(request, "core/section_overview.html", context)


@require_GET
def approval_worklist(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not current_user.has_role("PROJECT_MANAGER"):
        return _render_access_denied(
            request,
            message="You do not have permission to open the approval worklist.",
        )

    context = _page_context(
        request,
        title="Approval Worklist",
        eyebrow="SCR-205",
        intro="Placeholder worklist surface for managed-project approvals.",
    )
    context["section_cards"] = _overview_cards("approvals", current_user)
    return render(request, "core/section_overview.html", context)


@require_GET
def reports(request: HttpRequest) -> HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    context = _page_context(
        request,
        title="Reports",
        eyebrow="SCR-230",
        intro=(
            "Placeholder reporting hub with role-aware navigation reserved for "
            "the final UI milestone."
        ),
    )
    context["section_cards"] = _overview_cards("reports", current_user)
    return render(request, "core/section_overview.html", context)
