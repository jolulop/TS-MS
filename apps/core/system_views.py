import calendar as month_calendar
from dataclasses import dataclass
from datetime import date

from django.db.models import Q
from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.master_data.models import (
    BusinessUnit,
    Country,
    Employee,
    GeneralChargeCodeApprovalRole,
    Office,
    Project,
    YearlyCalendar,
)
from apps.master_data.models import Client as ClientRecord
from apps.master_data.models import CostCenter as CostCenterRecord
from apps.master_data.models import InternalCategory as InternalCategoryRecord
from apps.master_data.models import PricingModel as PricingModelRecord
from apps.master_data.services import (
    BusinessUnitManagementService,
    CalendarPeriodRuleManagementService,
    CalendarSpecialDayManagementService,
    ClientManagementService,
    CostCenterManagementService,
    CountryManagementService,
    EmployeeManagementService,
    GeneralChargeCodeApprovalRoleManagementService,
    GeneralChargeCodeManagementService,
    InternalCategoryManagementService,
    OfficeManagementService,
    PricingModelManagementService,
    ProjectAssignmentManagementService,
    ProjectManagementService,
    YearlyCalendarManagementService,
)
from apps.reference_data.models import RefValue


@dataclass(frozen=True)
class MasterUiConfig:
    section_key: str
    list_title: str
    list_eyebrow: str
    list_intro: str
    detail_title: str
    detail_eyebrow: str
    detail_intro: str
    singular_label: str
    plural_label: str
    collection_path: str
    detail_path_prefix: str
    table_headers: tuple[str, ...]
    empty_message: str


def _require_ts_admin(request: HttpRequest) -> CurrentUser | HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not current_user.is_ts_admin:
        return _render_access_denied(
            request,
            message="You do not have permission to open this System Management screen.",
        )
    return current_user


def _require_project_system_manager(request: HttpRequest) -> CurrentUser | HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not (current_user.is_ts_admin or current_user.has_role("PROJECT_OWNER")):
        return _render_access_denied(
            request,
            message="You do not have permission to open this System Management screen.",
        )
    return current_user


def _require_project_assignment_system_manager(request: HttpRequest) -> CurrentUser | HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not (
        current_user.is_ts_admin
        or current_user.has_role("PROJECT_OWNER")
        or current_user.has_role("PROJECT_MANAGER")
    ):
        return _render_access_denied(
            request,
            message="You do not have permission to open this System Management screen.",
        )
    return current_user


def _require_ts_admin_master(request: HttpRequest) -> CurrentUser | HttpResponse:
    current_user = _require_user(request)
    if not isinstance(current_user, CurrentUser):
        return current_user
    if not current_user.is_ts_admin_master:
        return _render_access_denied(
            request,
            message="You do not have permission to open this Office Management screen.",
        )
    return current_user


def _system_section_links(current_user: CurrentUser, current_path: str) -> list[dict]:
    if not (
        current_user.is_ts_admin
        or current_user.is_ts_admin_master
        or current_user.has_role("PROJECT_OWNER")
        or current_user.has_role("PROJECT_MANAGER")
    ):
        return []

    sections = [("overview", "Overview", "/system/")]
    if current_user.is_ts_admin_master:
        sections.extend(
            [
                ("countries", "Countries", "/system/countries/"),
                ("offices", "Offices", "/system/offices/"),
                ("employee-transfers", "Employee Transfers", "/system/employee-transfers/new/"),
            ]
        )
    if current_user.is_ts_admin:
        sections.extend(
            [
                ("employees", "Employees", "/system/employees/"),
                ("clients", "Clients", "/system/clients/"),
                ("projects", "Projects", "/system/projects/"),
                ("project-assignments", "Project Assignments", "/system/project-assignments/"),
                ("internal-categories", "Internal Categories", "/system/internal-categories/"),
                ("cost-centers", "Cost Centers", "/system/cost-centers/"),
                ("pricing-models", "Pricing Models", "/system/pricing-models/"),
                ("business-units", "Business Units", "/system/business-units/"),
                ("calendars", "Calendars", "/system/calendars/"),
                (
                    "calendar-period-rules",
                    "Calendar Period Rules",
                    "/system/calendar-period-rules/",
                ),
                (
                    "general-charge-code-approval-roles",
                    "GCC Approval Roles",
                    "/system/general-charge-code-approval-roles/",
                ),
                (
                    "general-charge-codes",
                    "General Charge Codes",
                    "/system/general-charge-codes/",
                ),
            ]
        )
    elif current_user.has_role("PROJECT_OWNER"):
        sections.extend(
            [
                ("projects", "Projects", "/system/projects/"),
                ("project-assignments", "Project Assignments", "/system/project-assignments/"),
            ]
        )
    elif current_user.has_role("PROJECT_MANAGER"):
        sections.extend(
            [("project-assignments", "Project Assignments", "/system/project-assignments/")]
        )
    links = []
    for key, label, href in sections:
        is_active = current_path == href or (href != "/system/" and current_path.startswith(href))
        if key == "calendars" and current_path.startswith("/system/calendar-special-days/"):
            is_active = True
        links.append(
            {
                "key": key,
                "label": label,
                "href": href,
                "active": is_active,
            }
        )
    return links


def _system_context(
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
    context["system_section_links"] = _system_section_links(current_user, request.path)
    return context


def _render_auth_error(
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

    context = _system_context(
        request,
        current_user,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )
    context["denied_message"] = error.message
    return render(request, "core/access_denied.html", context, status=error.status)


def _selected_values(raw_values: object) -> set[str]:
    if raw_values in (None, ""):
        return set()
    if isinstance(raw_values, list | tuple | set):
        return {str(value) for value in raw_values}
    return {str(raw_values)}


def _option(value: object, label: str, *, selected_values: set[str]) -> dict:
    string_value = str(value)
    return {
        "value": string_value,
        "label": label,
        "selected": string_value in selected_values,
    }


def _ref_options(
    domain_code: str,
    *,
    selected: object = None,
    include_blank: bool = False,
    blank_label: str = "Select an option",
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", blank_label, selected_values=selected_values))
    options.extend(
        _option(
            ref_value.value_code,
            ref_value.value_label,
            selected_values=selected_values,
        )
        for ref_value in RefValue.objects.filter(domain__domain_code=domain_code, active_flag=True)
    )
    return options


def _country_options(
    *,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Country", selected_values=selected_values))
    countries = Country.objects.order_by("country_name")
    options.extend(
        _option(
            country.id,
            f"{country.country_code} - {country.country_name}",
            selected_values=selected_values,
        )
        for country in countries
    )
    return options


def _active_office_options(
    *,
    selected: object = None,
    include_blank: bool = False,
    exclude_office_id: int | None = None,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select an Office", selected_values=selected_values))
    offices = Office.objects.filter(status__value_code="ACTIVE").order_by("office_name")
    if exclude_office_id is not None:
        offices = offices.exclude(id=exclude_office_id)
    options.extend(
        _option(
            office.id,
            office.office_name,
            selected_values=selected_values,
        )
        for office in offices
    )
    return options


def _scoped_business_unit_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Business Unit", selected_values=selected_values))
    business_units = BusinessUnit.objects.filter(
        id__in=current_user.scoped_business_unit_ids,
        office_id=current_user.office_id,
    ).order_by("bu_code")
    options.extend(
        _option(
            business_unit.id,
            f"{business_unit.bu_code} - {business_unit.name}",
            selected_values=selected_values,
        )
        for business_unit in business_units
    )
    return options


def _master_business_unit_options(
    *,
    selected: object = None,
    include_blank: bool = False,
    office_id: int | None = None,
    exclude_office_id: int | None = None,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Business Unit", selected_values=selected_values))
    business_units = BusinessUnit.objects.select_related("office").filter(
        office__status__value_code="ACTIVE"
    )
    if office_id is not None:
        business_units = business_units.filter(office_id=office_id)
    if exclude_office_id is not None:
        business_units = business_units.exclude(office_id=exclude_office_id)
    business_units = business_units.order_by("office__office_name", "bu_code")
    options.extend(
        _option(
            business_unit.id,
            f"{business_unit.office.office_name} / {business_unit.bu_code} - {business_unit.name}",
            selected_values=selected_values,
        )
        for business_unit in business_units
    )
    return options


def _employee_transfer_candidate_options(
    candidates: list[dict],
    *,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select an Employee", selected_values=selected_values))
    options.extend(
        _option(
            employee["id"],
            (
                f"{employee['employee_code']} - {employee['full_name']} / "
                f"{employee['office']['office_name']} / {employee['email']}"
            ),
            selected_values=selected_values,
        )
        for employee in candidates
    )
    return options


def _parent_client_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    exclude_client_id: int | None = None,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = [_option("", "No parent client", selected_values=selected_values)]
    clients = ClientRecord.objects.filter(
        office_id=current_user.office_id,
    ).select_related("office")
    if exclude_client_id is not None:
        clients = clients.exclude(id=exclude_client_id)
    clients = clients.order_by("client_code")
    options.extend(
        _option(
            client.id,
            f"{client.client_code} - {client.name}",
            selected_values=selected_values,
        )
        for client in clients
    )
    return options


def _field(
    *,
    name: str,
    label: str,
    kind: str,
    value: object = "",
    required: bool = False,
    help_text: str = "",
    options: list[dict] | None = None,
    checked: bool = False,
    readonly: bool = False,
    disabled: bool = False,
    size: int | None = None,
    width_mode: str = "auto",
) -> dict:
    return {
        "name": name,
        "label": label,
        "kind": kind,
        "value": value,
        "required": required,
        "help_text": help_text,
        "options": options or [],
        "checked": checked,
        "readonly": readonly,
        "disabled": disabled,
        "size": size,
        "width_mode": width_mode,
    }


def _office_display_field(office_name: str) -> dict:
    return _field(
        name="office_name_display",
        label="Office",
        kind="text",
        value=office_name,
        readonly=True,
    )


def _status_filter_links(
    request: HttpRequest,
    *,
    domain_code: str,
    default_code: str = "ALL",
) -> tuple[str, list[dict]]:
    raw_selected = str(request.GET.get("status", default_code)).strip().upper() or default_code
    available_values = list(
        RefValue.objects.filter(domain__domain_code=domain_code, active_flag=True).order_by(
            "sort_order",
            "value_code",
        )
    )
    allowed_codes = {"ALL", *(value.value_code for value in available_values)}
    selected_code = raw_selected if raw_selected in allowed_codes else default_code

    def _href_for(status_code: str) -> str:
        query_params = request.GET.copy()
        if status_code == "ALL" and default_code == "ALL":
            query_params.pop("status", None)
        else:
            query_params["status"] = status_code
        query_string = query_params.urlencode()
        return request.path if not query_string else f"{request.path}?{query_string}"

    all_href = _href_for("ALL")
    links = [{"label": "All", "href": all_href, "active": selected_code == "ALL"}]
    links.extend(
        {
            "label": ref_value.value_label,
            "href": _href_for(ref_value.value_code),
            "active": selected_code == ref_value.value_code,
        }
        for ref_value in available_values
    )
    return selected_code, links


def _service_status_code(selected_code: str) -> str | None:
    return None if selected_code == "ALL" else selected_code


def _bool_from_post(post_data: QueryDict, field_name: str) -> bool:
    return post_data.get(field_name) == "on"


def _scoped_client_options(
    current_user: CurrentUser,
    *,
    business_unit_id: int | None = None,
    selected: object = None,
    include_blank: bool = False,
    active_only: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Client", selected_values=selected_values))
    clients = ClientRecord.objects.filter(
        office_id=current_user.office_id,
    ).select_related("office")
    if active_only:
        clients = clients.filter(status__value_code="ACTIVE")
    clients = clients.order_by("client_code")
    options.extend(
        _option(
            client.id,
            f"{client.client_code} - {client.name}",
            selected_values=selected_values,
        )
        for client in clients
    )
    return options


def _scoped_internal_category_options(
    current_user: CurrentUser,
    *,
    business_unit_id: int | None = None,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select an Internal Category", selected_values=selected_values))
    categories = InternalCategoryRecord.objects.filter(
        business_unit_id__in=current_user.scoped_business_unit_ids,
        office_id=current_user.office_id,
    ).select_related("business_unit")
    if business_unit_id is not None:
        categories = categories.filter(business_unit_id=business_unit_id)
    categories = categories.order_by("business_unit__bu_code", "category_code")
    options.extend(
        _option(
            category.id,
            f"{category.business_unit.bu_code} - {category.category_code} - {category.name}",
            selected_values=selected_values,
        )
        for category in categories
    )
    return options


def _scoped_cost_center_options(
    current_user: CurrentUser,
    *,
    business_unit_id: int | None = None,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Cost Center", selected_values=selected_values))
    cost_centers = CostCenterRecord.objects.filter(
        office_id=current_user.office_id,
    ).select_related("office")
    cost_centers = cost_centers.order_by("cost_center_code")
    options.extend(
        _option(
            cost_center.id,
            f"{cost_center.cost_center_code} - {cost_center.name}",
            selected_values=selected_values,
        )
        for cost_center in cost_centers
    )
    return options


def _scoped_pricing_model_options(
    current_user: CurrentUser,
    *,
    business_unit_id: int | None = None,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Pricing Model", selected_values=selected_values))
    pricing_models = PricingModelRecord.objects.filter(
        office_id=current_user.office_id,
    ).order_by("name")
    options.extend(
        _option(
            pricing_model.id,
            pricing_model.name,
            selected_values=selected_values,
        )
        for pricing_model in pricing_models
    )
    return options


def _scoped_employee_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    include_blank: bool = False,
    required_role_code: str | None = None,
    business_unit_id: int | None = None,
    restrict_to_current_country: bool = False,
    include_all_employees: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select an Employee", selected_values=selected_values))
    employees = (
        Employee.objects.select_related("primary_business_unit")
        .prefetch_related(
            "role_assignments__role",
            "role_assignments__status__domain",
            "business_unit_assignments__status__domain",
        )
    )
    if include_all_employees:
        employees = employees.order_by("primary_business_unit__bu_code", "employee_code")
    else:
        employees = (
            employees.filter(
                business_unit_assignments__business_unit_id__in=current_user.scoped_business_unit_ids
            )
            .distinct()
            .order_by("primary_business_unit__bu_code", "employee_code")
        )
    if restrict_to_current_country:
        employees = employees.filter(office_id=current_user.office_id)
    if business_unit_id is not None:
        employees = employees.filter(
            business_unit_assignments__business_unit_id=business_unit_id,
            business_unit_assignments__status__domain__domain_code="EMPLOYEE_BU_STATUS",
            business_unit_assignments__status__value_code="ACTIVE",
            business_unit_assignments__valid_to__isnull=True,
        )
    employee_options = []
    for employee in employees:
        if required_role_code is not None:
            active_role_codes = {
                assignment.role.value_code
                for assignment in employee.role_assignments.all()
                if assignment.status.domain.domain_code == "ROLE_ASSIGNMENT_STATUS"
                and assignment.status.value_code == "ACTIVE"
                and assignment.valid_to is None
            }
            if required_role_code not in active_role_codes:
                continue
        employee_options.append(
            _option(
                employee.id,
                (
                    f"{employee.primary_business_unit.bu_code} - "
                    f"{employee.employee_code} - {employee.full_name}"
                ),
                selected_values=selected_values,
            )
        )
    options.extend(employee_options)
    return options


def _general_charge_code_approval_role_member_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
) -> list[dict]:
    return _scoped_employee_options(
        current_user,
        selected=selected,
        include_all_employees=True,
        restrict_to_current_country=True,
    )


def _member_count_label(count: int) -> str:
    return f"{count} active member" if count == 1 else f"{count} active members"


def _general_charge_code_approver_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = [
        _option(
            f"ROLE:{role.value_code}",
            f"[System] {role.value_code} - {role.value_label}",
            selected_values=selected_values,
        )
        for role in RefValue.objects.filter(domain__domain_code="ROLE_CODE").order_by("sort_order")
    ]
    options.extend(
        _option(
            f"ADHOC:{approval_role.id}",
            (
                f"[Ad hoc] {approval_role.role_code} - {approval_role.name}"
                f" ({_member_count_label(active_member_count)})"
                if approval_role.status.value_code == "ACTIVE" and active_member_count > 0
                else (
                    f"[Ad hoc] {approval_role.role_code} - {approval_role.name} "
                    "(inactive role)"
                    if approval_role.status.value_code != "ACTIVE"
                    else f"[Ad hoc] {approval_role.role_code} - {approval_role.name} "
                    "(no active members)"
                )
            ),
            selected_values=selected_values,
        )
        for approval_role in GeneralChargeCodeApprovalRole.objects.prefetch_related(
            "member_assignments__employee__status",
            "member_assignments__status__domain",
        )
        .select_related("status")
        .filter(office_id=current_user.office_id)
        .order_by("role_code")
        for active_member_count in [
            approval_role.member_assignments.filter(
                    status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                    status__value_code="ACTIVE",
                    valid_to__isnull=True,
                    employee__status__value_code="ACTIVE",
                ).count()
        ]
    )
    return options


def _scoped_project_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    include_blank: bool = False,
    client_id: int | None = None,
    active_only: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Project", selected_values=selected_values))
    projects = (
        Project.objects.select_related("business_unit", "status")
        .filter(
            business_unit_id__in=current_user.scoped_business_unit_ids,
            office_id=current_user.office_id,
        )
        .order_by("business_unit__bu_code", "project_code")
    )
    if client_id is not None:
        projects = projects.filter(client_id=client_id)
    if active_only:
        projects = projects.filter(status__value_code="ACTIVE")
    if not current_user.is_ts_admin:
        scoped_project_filter = None
        if current_user.has_role("PROJECT_OWNER"):
            scoped_project_filter = Q(project_owner_employee_id=current_user.employee_id)
        if current_user.has_role("PROJECT_MANAGER"):
            manager_filter = Q(project_manager_employee_id=current_user.employee_id)
            scoped_project_filter = (
                manager_filter
                if scoped_project_filter is None
                else scoped_project_filter | manager_filter
            )
        if scoped_project_filter is not None:
            projects = projects.filter(scoped_project_filter)
    options.extend(
        _option(
            project.id,
            f"{project.business_unit.bu_code} - {project.project_code} - {project.name}",
            selected_values=selected_values,
        )
        for project in projects
    )
    return options


def _project_owner_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    business_unit_id: int | None = None,
    include_blank: bool = False,
) -> list[dict]:
    if current_user.is_ts_admin:
        return _scoped_employee_options(
            current_user,
            selected=selected,
            include_blank=include_blank,
            required_role_code="PROJECT_OWNER",
            business_unit_id=business_unit_id,
            restrict_to_current_country=True,
        )
    return [
        _option(
            current_user.employee_id,
            (
                f"{current_user.primary_business_unit_code} - "
                f"{current_user.employee_code} - {current_user.full_name}"
            ),
            selected_values={str(current_user.employee_id)},
        )
    ]


def _scoped_yearly_calendar_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Calendar", selected_values=selected_values))
    calendars = (
        YearlyCalendar.objects.filter(office_id=current_user.office_id).order_by(
            "calendar_year",
            "calendar_name",
        )
    )
    options.extend(
        _option(
            calendar.id,
            f"{calendar.calendar_year} - {calendar.calendar_name}",
            selected_values=selected_values,
        )
        for calendar in calendars
    )
    return options


def _employee_create_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
) -> list[dict]:
    selected_business_units = (
        post_data.getlist("business_unit_ids")
        if post_data is not None
        else []
    )
    return [
        _office_display_field(current_user.office_name),
        _field(
            name="employee_code",
            label="Employee Code",
            kind="text",
            value=post_data.get("employee_code", "") if post_data is not None else "",
            required=True,
        ),
        _field(
            name="full_name",
            label="Full Name",
            kind="text",
            value=post_data.get("full_name", "") if post_data is not None else "",
            required=True,
        ),
        _field(
            name="email",
            label="Email",
            kind="email",
            value=post_data.get("email", "") if post_data is not None else "",
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "EMPLOYEE_STATUS",
                selected=post_data.get("status_code", "ACTIVE")
                if post_data is not None
                else "ACTIVE",
            ),
            required=True,
        ),
        _field(
            name="primary_business_unit_id",
            label="Primary Business Unit",
            kind="select",
            options=_scoped_business_unit_options(
                current_user,
                selected=post_data.get(
                    "primary_business_unit_id", str(current_user.primary_business_unit_id)
                )
                if post_data is not None
                else str(current_user.primary_business_unit_id),
            ),
            required=True,
        ),
        _field(
            name="business_unit_ids",
            label="Additional Business Units",
            kind="multiselect",
            options=_scoped_business_unit_options(
                current_user,
                selected=selected_business_units,
            ),
            help_text=(
                "Select any additional Business Units this employee may operate in. "
                "The selected primary Business Unit is always included automatically, "
                "so you can leave this empty when no extra scope is needed. "
                "Employees with an active TS_ADMIN role keep full Office Business Unit scope."
            ),
        ),
        _field(
            name="role_codes",
            label="Role Codes",
            kind="multiselect",
            options=_ref_options(
                "ROLE_CODE",
                selected=post_data.getlist("role_codes") if post_data is not None else ["USER"],
            ),
            help_text="Use Ctrl or Cmd to select multiple internal roles.",
        ),
    ]


def _employee_core_fields(employee: dict, *, post_data: QueryDict | None = None) -> list[dict]:
    return [
        _office_display_field(employee["office"]["office_name"]),
        _field(
            name="employee_code",
            label="Employee Code",
            kind="text",
            value=employee["employee_code"],
            readonly=True,
        ),
        _field(
            name="full_name",
            label="Full Name",
            kind="text",
            value=post_data.get("full_name", employee["full_name"])
            if post_data is not None
            else employee["full_name"],
            required=True,
        ),
        _field(
            name="email",
            label="Email",
            kind="email",
            value=post_data.get("email", employee["email"])
            if post_data is not None
            else employee["email"],
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "EMPLOYEE_STATUS",
                selected=post_data.get("status_code", employee["status"])
                if post_data is not None
                else employee["status"],
            ),
            required=True,
        ),
    ]


def _employee_role_fields(employee: dict, *, post_data: QueryDict | None = None) -> list[dict]:
    selected_roles = (
        post_data.getlist("role_codes") if post_data is not None else employee["role_codes"]
    )
    return [
        _field(
            name="role_codes",
            label="Role Codes",
            kind="multiselect",
            options=_ref_options("ROLE_CODE", selected=selected_roles),
            help_text="Replace the active internal role set for this employee.",
        )
    ]


def _employee_business_unit_fields(
    current_user: CurrentUser,
    employee: dict,
    *,
    post_data: QueryDict | None = None,
) -> list[dict]:
    has_ts_admin_role = "TS_ADMIN" in employee["role_codes"]
    selected_primary = (
        post_data.get("primary_business_unit_id", employee["primary_business_unit"]["id"])
        if post_data is not None
        else employee["primary_business_unit"]["id"]
    )
    selected_scope = (
        post_data.getlist("business_unit_ids")
        if post_data is not None
        else [
            business_unit["id"]
            for business_unit in employee["business_units"]
            if business_unit["id"] != employee["primary_business_unit"]["id"]
        ]
    )
    help_text = "The primary Business Unit must also be part of the employee scope."
    if has_ts_admin_role:
        help_text = (
            "Employees with an active TS_ADMIN role always keep all Business Units in the "
            "active Office scope. Saving this form can still change the primary Business Unit."
        )
    else:
        help_text = (
            "Select any additional Business Units this employee may operate in. "
            "The selected primary Business Unit is always included automatically, "
            "so leaving this empty keeps only the primary Business Unit."
        )
    return [
        _field(
            name="primary_business_unit_id",
            label="Primary Business Unit",
            kind="listbox",
            options=_scoped_business_unit_options(current_user, selected=selected_primary),
            required=True,
            size=max(4, len(current_user.scoped_business_units)),
        ),
        _field(
            name="business_unit_ids",
            label="Business Unit Scope",
            kind="multiselect",
            options=_scoped_business_unit_options(current_user, selected=selected_scope),
            help_text=help_text,
        ),
    ]


def _employee_transfer_source_fields(
    candidates: list[dict],
    *,
    office_filter_id: object = "",
    primary_business_unit_filter_id: object = "",
    full_name_filter: str = "",
    selected_source_id: object = "",
) -> list[dict]:
    filtered_office_id = None
    if str(office_filter_id).strip():
        try:
            filtered_office_id = int(str(office_filter_id).strip())
        except ValueError:
            filtered_office_id = None
    return [
        _field(
            name="filter_office_id",
            label="Office",
            kind="select",
            options=_active_office_options(
                selected=office_filter_id,
                include_blank=True,
            ),
        ),
        _field(
            name="filter_primary_business_unit_id",
            label="Primary BU",
            kind="select",
            options=_master_business_unit_options(
                selected=primary_business_unit_filter_id,
                include_blank=True,
                office_id=filtered_office_id,
            ),
        ),
        _field(
            name="filter_full_name",
            label="Full Name",
            kind="text",
            value=full_name_filter,
            help_text="Search source employees by full name text.",
        ),
        _field(
            name="source_employee_id",
            label="Source Employee",
            kind="select",
            options=_employee_transfer_candidate_options(
                candidates,
                selected=selected_source_id,
                include_blank=True,
            ),
            help_text=(
                "Choose the active source employee record that should be archived "
                "and recreated in another Office."
            ),
            width_mode="full",
        )
    ]


def _employee_transfer_fields(
    source_employee: dict,
    *,
    post_data: QueryDict | None = None,
) -> list[dict]:
    selected_target_roles = (
        post_data.getlist("target_role_codes")
        if post_data is not None
        else source_employee["role_codes"]
    )
    selected_target_business_units = (
        post_data.getlist("target_business_unit_ids") if post_data is not None else []
    )
    return [
        _field(
            name="source_employee_id",
            label="Source Employee",
            kind="hidden",
            value=source_employee["id"],
        ),
        _field(
            name="new_employee_code",
            label="New Employee Code",
            kind="text",
            value=(
                post_data.get("new_employee_code", f"{source_employee['employee_code']}-XFER")
                if post_data is not None
                else f"{source_employee['employee_code']}-XFER"
            ),
            required=True,
            help_text=(
                "The source employee code stays on the historical record. "
                "The target Office record needs a new unique employee code."
            ),
        ),
        _field(
            name="target_office_id",
            label="Target Office",
            kind="select",
            options=_active_office_options(
                selected=post_data.get("target_office_id", "") if post_data is not None else "",
                include_blank=True,
                exclude_office_id=source_employee["office"]["id"],
            ),
            required=True,
        ),
        _field(
            name="target_primary_business_unit_id",
            label="Target Primary Business Unit",
            kind="select",
            options=_master_business_unit_options(
                selected=(
                    post_data.get("target_primary_business_unit_id", "")
                    if post_data is not None
                    else ""
                ),
                include_blank=True,
                exclude_office_id=source_employee["office"]["id"],
            ),
            required=True,
        ),
        _field(
            name="target_business_unit_ids",
            label="Target Additional Business Units",
            kind="multiselect",
            options=_master_business_unit_options(
                selected=selected_target_business_units,
                exclude_office_id=source_employee["office"]["id"],
            ),
            help_text=(
                "Select any additional Business Units for the target record. "
                "Use only Business Units from the selected target Office. "
                "If the target roles include TS_ADMIN, full target-Office scope is applied "
                "automatically."
            ),
        ),
        _field(
            name="target_role_codes",
            label="Target Role Codes",
            kind="multiselect",
            options=_ref_options("ROLE_CODE", selected=selected_target_roles),
            help_text=(
                "The new target-Office employee starts with these active TS roles. "
                "The source employee roles are selected by default."
            ),
        ),
        _field(
            name="archived_email_preview",
            label="Archived Source Email",
            kind="email",
            value=source_employee["archived_email_preview"],
            readonly=True,
            help_text=(
                "The source record will be rewritten to this archival email so the real "
                "login email can move to the new target-Office employee."
            ),
            width_mode="full",
        ),
    ]


def _employee_transfer_source_rows(source_employee: dict) -> list[tuple[str, str]]:
    return [
        ("Employee Code", source_employee["employee_code"]),
        ("Full Name", source_employee["full_name"]),
        ("Email", source_employee["email"]),
        ("Office", source_employee["office"]["office_name"]),
        (
            "Primary Business Unit",
            source_employee["primary_business_unit"]["bu_code"],
        ),
        (
            "Business Unit Scope",
            (
                ", ".join(
                    business_unit["bu_code"]
                    for business_unit in source_employee["business_units"]
                )
                or "None"
            ),
        ),
        ("Role Codes", ", ".join(source_employee["role_codes"]) or "None"),
    ]


def _employee_transfer_readiness_rows(source_employee: dict) -> list[tuple[str, str]]:
    blockers = source_employee.get("transfer_blockers", [])
    if not blockers:
        return [
            ("Status", "READY"),
            (
                "Outcome",
                "No active cross-Office transfer blockers were detected for the source employee.",
            ),
        ]
    rows = [("Status", "BLOCKED")]
    rows.extend(
        (blocker["label"], f"{blocker['count']} — {blocker['message']}") for blocker in blockers
    )
    return rows


def _employee_transfer_result_rows(label: str, employee: dict) -> list[tuple[str, str]]:
    return [
        ("Record", label),
        ("Employee Id", str(employee["id"])),
        ("Employee Code", employee["employee_code"]),
        ("Full Name", employee["full_name"]),
        ("Email", employee["email"]),
        ("Status", employee["status"]),
        ("Office", employee["office"]["office_name"]),
        ("Primary Business Unit", employee["primary_business_unit"]["bu_code"]),
        (
            "Business Unit Scope",
            ", ".join(business_unit["bu_code"] for business_unit in employee["business_units"])
            or "None",
        ),
        ("Role Codes", ", ".join(employee["role_codes"]) or "None"),
    ]


def _client_form_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    selected_parent = submitted_data.get("parent_client_id", "")
    if entity is not None and post_data is None and entity["parent_client"] is not None:
        selected_parent = str(entity["parent_client"]["id"])

    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="client_code",
            label="Client Code",
            kind="text",
            value=submitted_data.get("client_code", entity["client_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Client Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "CLIENT_STATUS",
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "ACTIVE"
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
        _field(
            name="parent_client_id",
            label="Parent Client",
            kind="select",
            options=_parent_client_options(
                current_user,
                selected=selected_parent,
                exclude_client_id=entity["id"] if entity else None,
            ),
        ),
    ]


def _simple_master_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
    business_unit_label: str,
    code_name: str,
    code_label: str,
    name_label: str,
    description_label: str,
    status_domain: str,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    selected_business_unit = submitted_data.get("business_unit_id", "")
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])

    description_value = ""
    if entity is not None:
        description_value = entity["description"]
    if post_data is not None:
        description_value = submitted_data.get("description", description_value)

    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="business_unit_id",
            label=business_unit_label,
            kind="select",
            options=_scoped_business_unit_options(
                current_user,
                selected=selected_business_unit,
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name=code_name,
            label=code_label,
            kind="text",
            value=submitted_data.get(code_name, entity[code_name] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label=name_label,
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="description",
            label=description_label,
            kind="textarea",
            value=description_value,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                status_domain,
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "ACTIVE"
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _cost_center_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    description_value = ""
    if entity is not None:
        description_value = entity["description"]
    if post_data is not None:
        description_value = submitted_data.get("description", description_value)

    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="cost_center_code",
            label="Cost Center Code",
            kind="text",
            value=submitted_data.get(
                "cost_center_code", entity["cost_center_code"] if entity else ""
            )
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Cost Center Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="description",
            label="Description",
            kind="textarea",
            value=description_value,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "COST_CENTER_STATUS",
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "ACTIVE"
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _yearly_calendar_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    fields = [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        )
    ]

    fields.extend(
        [
            _field(
                name="calendar_year",
                label="Calendar Year",
                kind="number",
                value=submitted_data.get(
                    "calendar_year",
                    str(entity["calendar_year"]) if entity else str(date.today().year),
                )
                if post_data is not None or entity is not None
                else str(date.today().year),
                required=True,
            ),
            _field(
                name="calendar_name",
                label="Calendar Name",
                kind="text",
                value=submitted_data.get("calendar_name", entity["calendar_name"] if entity else "")
                if post_data is not None or entity is not None
                else "",
                required=True,
            ),
            _field(
                name="status_code",
                label="Status",
                kind="select",
                options=_ref_options(
                    "CALENDAR_STATUS",
                    selected=submitted_data.get(
                        "status_code",
                        entity["status"] if entity else "ACTIVE",
                    )
                    if post_data is not None or entity is not None
                    else "ACTIVE",
                ),
                required=True,
            ),
        ]
    )
    return fields


def _calendar_special_day_fields(
    current_user: CurrentUser,
    *,
    yearly_calendar: dict,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    return [
        _office_display_field(yearly_calendar["office"]["office_name"]),
        _field(
            name="yearly_calendar_display",
            label="Yearly Calendar",
            kind="text",
            value=f"{yearly_calendar['calendar_year']} - {yearly_calendar['calendar_name']}",
            readonly=True,
        ),
        _field(
            name="special_date",
            label="Special Day Date",
            kind="date",
            value=submitted_data.get(
                "special_date",
                entity["special_date"] if entity else "",
            )
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="day_type_code",
            label="Special Day Type",
            kind="select",
            options=_ref_options(
                "SPECIAL_DAY_TYPE",
                selected=submitted_data.get(
                    "day_type_code",
                    entity["day_type"]["value_code"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
                blank_label="Select a special day type",
            ),
            required=True,
        ),
    ]


def _pricing_model_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="name",
            label="Pricing Model Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="description",
            label="Description",
            kind="textarea",
            value=submitted_data.get("description", entity["description"] if entity else "")
            if post_data is not None or entity is not None
            else "",
        ),
    ]


def _general_charge_code_approval_role_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    selected_members = (
        submitted_data.getlist("member_employee_ids")
        if post_data is not None
        else [member["id"] for member in entity["member_employees"]]
        if entity is not None
        else []
    )
    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="role_code",
            label="Role Code",
            kind="text",
            value=submitted_data.get("role_code", entity["role_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="description",
            label="Description",
            kind="textarea",
            value=submitted_data.get("description", entity["description"] if entity else "")
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="member_employee_ids",
            label="Member Employees",
            kind="multiselect",
            options=_general_charge_code_approval_role_member_options(
                current_user,
                selected=selected_members,
            ),
            help_text=(
                "Assign any active employee from the current Office who may approve "
                "General Charge Code charges for this ad-hoc role."
            ),
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "ACTIVE"
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _general_charge_code_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    selected_business_unit = submitted_data.get("business_unit_id", "")
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])

    valid_from_value = ""
    if entity is not None:
        valid_from_value = entity["valid_from"]
    if post_data is not None:
        valid_from_value = submitted_data.get("valid_from", valid_from_value)

    valid_to_value = ""
    if entity is not None and entity["valid_to"] is not None:
        valid_to_value = entity["valid_to"]
    if post_data is not None:
        valid_to_value = submitted_data.get("valid_to", valid_to_value)

    selected_approver_keys = []
    if post_data is not None:
        selected_approver_keys = submitted_data.getlist("approver_keys")
    elif entity is not None:
        selected_approver_keys = [role["key"] for role in entity["approver_roles"]]

    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="business_unit_id",
            label="Business Unit",
            kind="select",
            options=_scoped_business_unit_options(
                current_user,
                selected=selected_business_unit,
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="code",
            label="Code",
            kind="text",
            value=submitted_data.get("code", entity["code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="charge_type_code",
            label="Charge Type",
            kind="select",
            options=_ref_options(
                "GENERAL_CHARGE_CODE_TYPE",
                selected=submitted_data.get(
                    "charge_type_code",
                    entity["charge_type"] if entity else "STANDARD",
                )
                if post_data is not None or entity is not None
                else "STANDARD",
            ),
            required=True,
        ),
        _field(
            name="cost_center_id",
            label="Cost Center",
            kind="select",
            options=_scoped_cost_center_options(
                current_user,
                selected=submitted_data.get(
                    "cost_center_id",
                    entity["cost_center"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="valid_from",
            label="Valid From",
            kind="date",
            value=valid_from_value,
            required=True,
        ),
        _field(
            name="valid_to",
            label="Valid To",
            kind="date",
            value=valid_to_value,
        ),
        _field(
            name="billable_flag",
            label="Billable",
            kind="checkbox",
            checked=_bool_from_post(post_data, "billable_flag")
            if post_data is not None
            else bool(entity["billable_flag"])
            if entity is not None
            else False,
        ),
        _field(
            name="requires_approval_flag",
            label="Requires Approval",
            kind="checkbox",
            checked=_bool_from_post(post_data, "requires_approval_flag")
            if post_data is not None
            else bool(entity["requires_approval_flag"])
            if entity is not None
            else False,
        ),
        _field(
            name="approver_keys",
            label="Approver Roles",
            kind="multiselect",
            options=_general_charge_code_approver_options(
                current_user,
                selected=selected_approver_keys,
            ),
            help_text=(
                "Required only when Requires Approval is enabled. Select one or more "
                "existing system roles and/or ad-hoc approval roles."
            ),
        ),
        _field(
            name="description_required_flag",
            label="Description Required",
            kind="checkbox",
            checked=_bool_from_post(post_data, "description_required_flag")
            if post_data is not None
            else bool(entity["description_required_flag"])
            if entity is not None
            else False,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "GENERAL_CHARGE_CODE_STATUS",
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "ACTIVE"
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _project_form_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    selected_business_unit = submitted_data.get("business_unit_id", "")
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])
    scoped_business_unit_id = (
        int(selected_business_unit) if str(selected_business_unit).isdigit() else None
    )
    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="business_unit_id",
            label="Business Unit",
            kind="select",
            options=_scoped_business_unit_options(
                current_user,
                selected=selected_business_unit,
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="project_code",
            label="Project Code",
            kind="text",
            value=submitted_data.get("project_code", entity["project_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Project Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="description",
            label="Description",
            kind="textarea",
            value=submitted_data.get("description", entity["description"] if entity else "")
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="project_owner_employee_id",
            label="Project Owner",
            kind="select",
            options=_project_owner_options(
                current_user,
                selected=submitted_data.get(
                    "project_owner_employee_id",
                    entity["project_owner_employee"]["id"] if entity else current_user.employee_id,
                )
                if post_data is not None or entity is not None
                else current_user.employee_id,
                include_blank=entity is None and current_user.is_ts_admin,
                business_unit_id=scoped_business_unit_id,
            ),
            required=True,
            help_text=""
            if current_user.is_ts_admin
            else "Projects created here always stay owned by your current employee profile.",
        ),
        _field(
            name="project_manager_employee_id",
            label="Project Manager",
            kind="select",
            options=_scoped_employee_options(
                current_user,
                selected=submitted_data.get(
                    "project_manager_employee_id",
                    entity["project_manager_employee"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
                required_role_code="PROJECT_MANAGER",
                business_unit_id=scoped_business_unit_id,
                restrict_to_current_country=True,
            ),
            required=True,
        ),
        _field(
            name="client_id",
            label="Client",
            kind="select",
            options=_scoped_client_options(
                current_user,
                business_unit_id=scoped_business_unit_id,
                selected=submitted_data.get(
                    "client_id", entity["client"]["id"] if entity else ""
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="internal_category_id",
            label="Internal Category",
            kind="select",
            options=_scoped_internal_category_options(
                current_user,
                business_unit_id=scoped_business_unit_id,
                selected=submitted_data.get(
                    "internal_category_id",
                    entity["internal_category"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="cost_center_id",
            label="Cost Center",
            kind="select",
            options=_scoped_cost_center_options(
                current_user,
                business_unit_id=scoped_business_unit_id,
                selected=submitted_data.get(
                    "cost_center_id", entity["cost_center"]["id"] if entity else ""
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="pricing_model_id",
            label="Pricing Model",
            kind="select",
            options=_scoped_pricing_model_options(
                current_user,
                business_unit_id=scoped_business_unit_id,
                selected=submitted_data.get(
                    "pricing_model_id",
                    entity["pricing_model"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="start_date",
            label="Start Date",
            kind="date",
            value=submitted_data.get("start_date", entity["start_date"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="end_date",
            label="End Date",
            kind="date",
            value=submitted_data.get(
                "end_date", entity["end_date"] if entity and entity["end_date"] else ""
            )
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="close_date",
            label="Close Date",
            kind="date",
            value=submitted_data.get(
                "close_date",
                entity["close_date"] if entity and entity["close_date"] else "",
            )
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="billable_flag",
            label="Billable",
            kind="checkbox",
            checked=_bool_from_post(post_data, "billable_flag")
            if post_data is not None
            else bool(entity["billable_flag"])
            if entity is not None
            else False,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "PROJECT_STATUS",
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "DRAFT"
                )
                if post_data is not None or entity is not None
                else "DRAFT",
            ),
            required=True,
        ),
    ]


def _project_assignment_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    return [
        _field(
            name="project_id",
            label="Project",
            kind="select",
            options=_scoped_project_options(
                current_user,
                selected=submitted_data.get(
                    "project_id",
                    entity["project"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="employee_id",
            label="Employee",
            kind="select",
            options=_scoped_employee_options(
                current_user,
                selected=submitted_data.get(
                    "employee_id",
                    entity["employee"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
                include_all_employees=True,
            ),
            required=True,
        ),
        _field(
            name="assignment_start_date",
            label="Assignment Start Date",
            kind="date",
            value=submitted_data.get(
                "assignment_start_date",
                entity["assignment_start_date"] if entity else "",
            )
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="assignment_end_date",
            label="Assignment End Date",
            kind="date",
            value=submitted_data.get(
                "assignment_end_date",
                entity["assignment_end_date"] if entity and entity["assignment_end_date"] else "",
            )
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "PROJECT_ASSIGNMENT_STATUS",
                selected=submitted_data.get(
                    "status_code",
                    entity["status"] if entity else "ACTIVE",
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _project_assignment_filter_fields(
    current_user: CurrentUser,
    *,
    selected_status_code: str,
    selected_client_id: object = "",
    selected_project_id: object = "",
) -> list[dict]:
    normalized_client_id = (
        int(str(selected_client_id)) if str(selected_client_id).isdigit() else None
    )
    return [
        _field(name="status", label="", kind="hidden", value=selected_status_code),
        _field(
            name="client_id",
            label="Client",
            kind="select",
            options=_scoped_client_options(
                current_user,
                selected=selected_client_id,
                include_blank=True,
                active_only=True,
            ),
        ),
        _field(
            name="project_id",
            label="Project",
            kind="select",
            options=_scoped_project_options(
                current_user,
                selected=selected_project_id,
                include_blank=True,
                client_id=normalized_client_id,
                active_only=True,
            ),
        ),
    ]


def _calendar_period_rule_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    selected_business_unit = submitted_data.get(
        "business_unit_id",
        str(entity["business_unit"]["id"])
        if entity and entity.get("business_unit") is not None
        else str(current_user.primary_business_unit_id),
    )
    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="business_unit_id",
            label="Business Unit",
            kind="select",
            options=_scoped_business_unit_options(
                current_user,
                selected=selected_business_unit,
                include_blank=entity is not None and entity.get("business_unit") is None,
            ),
            required=True,
            help_text=(
                "Business Unit that owns this period rule. The selected yearly calendar "
                "is still shared at Office level."
            ),
        ),
        _field(
            name="yearly_calendar_id",
            label="Yearly Calendar",
            kind="select",
            options=_scoped_yearly_calendar_options(
                current_user,
                selected=submitted_data.get(
                    "yearly_calendar_id",
                    entity["yearly_calendar"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="effective_from",
            label="Effective From",
            kind="date",
            value=submitted_data.get(
                "effective_from",
                entity["effective_from"] if entity else "",
            )
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="effective_to",
            label="Effective To",
            kind="date",
            value=submitted_data.get(
                "effective_to",
                entity["effective_to"] if entity else "",
            )
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="monday_max_hours",
            label="Monday Max Hours",
            kind="number",
            value=submitted_data.get(
                "monday_max_hours", entity["monday_max_hours"] if entity else "8.00"
            )
            if post_data is not None or entity is not None
            else "8.00",
            required=True,
        ),
        _field(
            name="tuesday_max_hours",
            label="Tuesday Max Hours",
            kind="number",
            value=submitted_data.get(
                "tuesday_max_hours", entity["tuesday_max_hours"] if entity else "8.00"
            )
            if post_data is not None or entity is not None
            else "8.00",
            required=True,
        ),
        _field(
            name="wednesday_max_hours",
            label="Wednesday Max Hours",
            kind="number",
            value=submitted_data.get(
                "wednesday_max_hours",
                entity["wednesday_max_hours"] if entity else "8.00",
            )
            if post_data is not None or entity is not None
            else "8.00",
            required=True,
        ),
        _field(
            name="thursday_max_hours",
            label="Thursday Max Hours",
            kind="number",
            value=submitted_data.get(
                "thursday_max_hours", entity["thursday_max_hours"] if entity else "8.00"
            )
            if post_data is not None or entity is not None
            else "8.00",
            required=True,
        ),
        _field(
            name="friday_max_hours",
            label="Friday Max Hours",
            kind="number",
            value=submitted_data.get(
                "friday_max_hours", entity["friday_max_hours"] if entity else "8.00"
            )
            if post_data is not None or entity is not None
            else "8.00",
            required=True,
        ),
        _field(
            name="working_on_saturdays_flag",
            label="Working On Saturdays",
            kind="checkbox",
            checked=(
                _bool_from_post(submitted_data, "working_on_saturdays_flag")
                if post_data is not None
                else (
                    entity["working_on_saturdays_flag"]
                    if entity is not None
                    else False
                )
            ),
            help_text="Treat Saturdays as normal working days for this Business Unit period.",
        ),
        _field(
            name="saturday_max_hours",
            label="Saturday Max Hours",
            kind="number",
            value=submitted_data.get(
                "saturday_max_hours", entity["saturday_max_hours"] if entity else "0.00"
            )
            if post_data is not None or entity is not None
            else "0.00",
            required=True,
        ),
        _field(
            name="working_on_sundays_flag",
            label="Working On Sundays",
            kind="checkbox",
            checked=(
                _bool_from_post(submitted_data, "working_on_sundays_flag")
                if post_data is not None
                else (
                    entity["working_on_sundays_flag"]
                    if entity is not None
                    else False
                )
            ),
            help_text="Treat Sundays as normal working days for this Business Unit period.",
        ),
        _field(
            name="sunday_max_hours",
            label="Sunday Max Hours",
            kind="number",
            value=submitted_data.get(
                "sunday_max_hours", entity["sunday_max_hours"] if entity else "0.00"
            )
            if post_data is not None or entity is not None
            else "0.00",
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "CALENDAR_PERIOD_STATUS",
                selected=submitted_data.get(
                    "status_code",
                    entity["status"] if entity else "ACTIVE",
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _render_collection_page(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    title: str,
    eyebrow: str,
    intro: str,
    table_headers: tuple[str, ...],
    table_rows: list[dict],
    empty_message: str,
    form_title: str | None = None,
    form_intro: str = "",
    form_fields: list[dict] | None = None,
    submit_label: str = "",
    form_error: str = "",
    filter_links: list[dict] | None = None,
    filter_title: str = "Filters",
    show_filter_panel: bool = True,
    inline_filter_links: list[dict] | None = None,
    inline_filter_title: str = "Filters",
    records_heading: str = "Current Records",
    split_grid_class: str = "split-grid",
    page_action: dict | None = None,
    title_filter_links: list[dict] | None = None,
    title_filter_title: str = "Filters",
    bottom_action: dict | None = None,
    filter_form_fields: list[dict] | None = None,
    filter_form_submit_label: str = "Apply Filters",
    filter_form_reset_pairs: list[dict] | None = None,
    inline_filter_form_fields: list[dict] | None = None,
    inline_filter_hidden_fields: list[dict] | None = None,
    inline_filter_form_submit_label: str = "Apply Filters",
) -> HttpResponse:
    context = _system_context(
        request,
        current_user,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )
    context.update(
        {
            "table_headers": table_headers,
            "table_rows": table_rows,
            "empty_message": empty_message,
            "form_title": form_title or "",
            "form_intro": form_intro,
            "form_fields": form_fields or [],
            "submit_label": submit_label,
            "form_error": form_error,
            "filter_links": filter_links or [],
            "filter_title": filter_title,
            "show_filter_panel": show_filter_panel,
            "inline_filter_links": inline_filter_links or [],
            "inline_filter_title": inline_filter_title,
            "records_heading": records_heading,
            "split_grid_class": split_grid_class,
            "page_action": page_action,
            "title_filter_links": title_filter_links or [],
            "title_filter_title": title_filter_title,
            "bottom_action": bottom_action,
            "filter_form_fields": filter_form_fields or [],
            "filter_form_submit_label": filter_form_submit_label,
            "filter_form_reset_pairs": filter_form_reset_pairs or [],
            "inline_filter_form_fields": inline_filter_form_fields or [],
            "inline_filter_hidden_fields": inline_filter_hidden_fields or [],
            "inline_filter_form_submit_label": inline_filter_form_submit_label,
        }
    )
    return render(request, "core/system_collection.html", context)


def _render_detail_page(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    title: str,
    eyebrow: str,
    intro: str,
    detail_rows: list[tuple[str, str]],
    form_sections: list[dict],
    back_href: str,
    back_label: str,
    entity_status: str,
    show_detail_panel: bool = True,
    detail_content_class: str = "content-stack",
    page_action: dict | None = None,
) -> HttpResponse:
    context = _system_context(
        request,
        current_user,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
    )
    context.update(
        {
            "detail_rows": detail_rows,
            "form_sections": form_sections,
            "back_href": back_href,
            "back_label": back_label,
            "entity_status": entity_status,
            "show_detail_panel": show_detail_panel,
            "detail_content_class": detail_content_class,
            "page_action": page_action,
        }
    )
    return render(request, "core/system_detail.html", context)


def _master_create_path(config: MasterUiConfig) -> str:
    return f"{config.collection_path}new/"


def _render_list_only_collection(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    title: str,
    eyebrow: str,
    intro: str,
    table_headers: tuple[str, ...],
    table_rows: list[dict],
    empty_message: str,
    create_label: str,
    create_href: str,
    filter_links: list[dict] | None = None,
    filter_title: str = "Filters",
    filter_form_fields: list[dict] | None = None,
    filter_form_submit_label: str = "Apply Filters",
    filter_form_reset_pairs: list[dict] | None = None,
    inline_filter_form_fields: list[dict] | None = None,
    inline_filter_hidden_fields: list[dict] | None = None,
    inline_filter_form_submit_label: str = "Apply Filters",
) -> HttpResponse:
    return _render_collection_page(
        request,
        current_user,
        title=title,
        eyebrow=eyebrow,
        intro=intro,
        table_headers=table_headers,
        table_rows=table_rows,
        empty_message=empty_message,
        form_title=None,
        filter_links=[],
        filter_title=filter_title,
        show_filter_panel=bool(filter_form_fields),
        inline_filter_links=filter_links or [],
        inline_filter_title=filter_title,
        records_heading="",
        page_action={"label": create_label, "href": create_href},
        filter_form_fields=filter_form_fields,
        filter_form_submit_label=filter_form_submit_label,
        filter_form_reset_pairs=filter_form_reset_pairs,
        inline_filter_form_fields=inline_filter_form_fields,
        inline_filter_hidden_fields=inline_filter_hidden_fields,
        inline_filter_form_submit_label=inline_filter_form_submit_label,
    )


def _render_master_create(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    config: MasterUiConfig,
    form_fields: list[dict],
    form_error: str,
    form_intro: str,
    setup_title: str | None = None,
    submit_label: str | None = None,
) -> HttpResponse:
    return _render_detail_page(
        request,
        current_user,
        title=f"Create {config.singular_label}",
        eyebrow=config.list_eyebrow,
        intro=(
            f"Standalone {config.singular_label.lower()} creation screen inside the "
            "shared system management shell."
        ),
        detail_rows=[],
        form_sections=[
            {
                "form_name": "create",
                "title": setup_title or f"{config.singular_label} Setup",
                "intro": form_intro,
                "submit_label": submit_label or f"Create {config.singular_label}",
                "form_error": form_error,
                "fields": form_fields,
            }
        ],
        back_href=config.collection_path,
        back_label=f"Back to {config.plural_label}",
        entity_status="New",
        show_detail_panel=False,
        page_action={"label": f"Back to {config.plural_label}", "href": config.collection_path},
    )


def _delete_action_section(
    *,
    form_name: str = "delete",
    submit_label: str,
    title: str | None = None,
    intro: str | None = None,
    form_error: str = "",
) -> dict:
    return {
        "form_name": form_name,
        "title": title or submit_label,
        "intro": intro
        or (
            "Delete this record only if it has no dependent references. "
            "If it is still in use, deletion will be blocked."
        ),
        "submit_label": submit_label,
        "form_error": form_error,
        "fields": [],
        "action_only": True,
        "button_class": "button danger",
    }


def _read_only_detail_section(
    *,
    title: str,
    intro: str,
    detail_rows: list[tuple[str, str]],
) -> dict:
    return {
        "title": title,
        "intro": intro,
        "detail_rows": detail_rows,
        "fields": [],
        "read_only": True,
    }


def _read_only_table_section(
    *,
    title: str,
    intro: str,
    table_headers: tuple[str, ...],
    table_rows: list[dict],
    empty_message: str,
) -> dict:
    return {
        "title": title,
        "intro": intro,
        "table_headers": table_headers,
        "table_rows": table_rows,
        "empty_message": empty_message,
        "fields": [],
        "read_only": True,
    }


def _employee_rows(employees: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/employees/{employee['id']}/",
            "cells": [
                employee["employee_code"],
                employee["full_name"],
                employee["email"],
                employee["status"],
                employee["primary_business_unit"]["bu_code"],
                ", ".join(employee["role_codes"]) or "No active roles",
            ],
        }
        for employee in employees
    ]


def _employee_detail_rows(employee: dict) -> list[tuple[str, str]]:
    return [
        ("Employee Code", employee["employee_code"]),
        ("Email", employee["email"]),
        ("Status", employee["status"]),
        (
            "Primary Business Unit",
            employee["primary_business_unit"]["bu_code"],
        ),
        ("Role Codes", ", ".join(employee["role_codes"]) or "No active roles"),
        (
            "Business Unit Scope",
            ", ".join(business_unit["bu_code"] for business_unit in employee["business_units"]),
        ),
    ]


def _employee_project_assignment_rows(
    project_assignments: list[dict],
) -> list[dict]:
    return [
        {
            "href": f"/system/projects/{assignment['project']['id']}/",
            "cells": [
                assignment["project"]["name"],
                assignment["project"]["business_unit"]["bu_code"],
                assignment["assignment_start_date"],
                assignment["assignment_end_date"] or "Open",
            ],
        }
        for assignment in project_assignments
    ]


def _client_rows(clients: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for client in clients:
        summaries = client["project_business_unit_summaries"]
        if summaries:
            for summary in summaries:
                rows.append(
                    {
                        "href": f"/system/clients/{client['id']}/",
                        "cells": [
                            client["client_code"],
                            client["name"],
                            summary["business_unit"]["name"],
                            {
                                "text": str(summary["active_project_count"]),
                                "href": (
                                    f"/system/clients/{client['id']}/projects/"
                                    f"{summary['business_unit']['id']}/"
                                ),
                            },
                            str(summary["active_employee_count"]),
                            client["status"],
                            (
                                client["parent_client"]["client_code"]
                                if client["parent_client"]
                                else "None"
                            ),
                        ],
                    }
                )
            continue
        rows.append(
            {
                "href": f"/system/clients/{client['id']}/",
                "cells": [
                    client["client_code"],
                    client["name"],
                    "None",
                    "0",
                    "0",
                    client["status"],
                    client["parent_client"]["client_code"] if client["parent_client"] else "None",
                ],
            }
        )
    return rows


def _client_detail_rows(client: dict) -> list[tuple[str, str]]:
    return [
        ("Client Code", client["client_code"]),
        ("Name", client["name"]),
        ("Status", client["status"]),
        (
            "Parent Client",
            client["parent_client"]["client_code"] if client["parent_client"] else "None",
        ),
    ]


def _internal_category_rows(categories: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/internal-categories/{category['id']}/",
            "cells": [
                category["business_unit"]["bu_code"],
                category["category_code"],
                category["name"],
                category["status"],
            ],
        }
        for category in categories
    ]


def _internal_category_detail_rows(category: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", category["business_unit"]["bu_code"]),
        ("Category Code", category["category_code"]),
        ("Name", category["name"]),
        ("Description", category["description"] or "None"),
        ("Status", category["status"]),
    ]


def _cost_center_rows(cost_centers: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/cost-centers/{cost_center['id']}/",
            "cells": [
                cost_center["cost_center_code"],
                cost_center["name"],
                cost_center["status"],
            ],
        }
        for cost_center in cost_centers
    ]


def _cost_center_detail_rows(cost_center: dict) -> list[tuple[str, str]]:
    return [
        ("Cost Center Code", cost_center["cost_center_code"]),
        ("Name", cost_center["name"]),
        ("Description", cost_center["description"] or "None"),
        ("Status", cost_center["status"]),
    ]


def _yearly_calendar_rows(calendars: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/calendars/{calendar['id']}/",
            "cells": [
                str(calendar["calendar_year"]),
                calendar["calendar_name"],
                calendar["status"],
            ],
        }
        for calendar in calendars
    ]


def _yearly_calendar_detail_rows(yearly_calendar: dict) -> list[tuple[str, str]]:
    return [
        ("Office", yearly_calendar["office"]["office_name"]),
        ("Calendar Year", str(yearly_calendar["calendar_year"])),
        ("Calendar Name", yearly_calendar["calendar_name"]),
        ("Status", yearly_calendar["status"]),
        ("Period Rules", str(yearly_calendar.get("period_rule_count", 0))),
    ]


def _calendar_special_day_detail_rows(special_day: dict) -> list[tuple[str, str]]:
    return [
        ("Special Day Date", special_day["special_date"]),
        ("Special Day Type", special_day["day_type"]["value_label"]),
        ("Status", special_day["status"]),
    ]


def _calendar_special_day_rows(special_days: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/calendar-special-days/{special_day['id']}/",
            "cells": [
                special_day["special_date"],
                special_day["day_type"]["value_label"],
                special_day["status"],
            ],
        }
        for special_day in special_days
    ]


def _calendar_month_state(yearly_calendar: dict, selected_month: int) -> dict:
    year = yearly_calendar["calendar_year"]
    month = min(12, max(1, selected_month))
    special_days_by_date = {
        special_day["special_date"]: special_day
        for special_day in yearly_calendar["special_days"]
        if special_day["status"] == "ACTIVE"
    }
    weekday_headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    month_matrix = month_calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    month_name = month_calendar.month_name[month]
    weeks = []
    for week in month_matrix:
        week_cells = []
        for weekday_index, day_number in enumerate(week):
            if day_number == 0:
                week_cells.append({"empty": True})
                continue
            current_day = date(year, month, day_number)
            current_day_key = current_day.isoformat()
            special_day = special_days_by_date.get(current_day_key)
            day_class = "working"
            label = "Working day"
            note = ""
            if special_day is not None:
                day_type_code = special_day["day_type"]["value_code"]
                if day_type_code == "NATIONAL_HOLIDAY":
                    day_class = "national-holiday"
                elif day_type_code == "LOCAL_HOLIDAY":
                    day_class = "local-holiday"
                elif day_type_code == "TIMIA_DAY":
                    day_class = "timia-day"
                else:
                    day_class = "other-day"
                label = special_day["day_type"]["value_label"]
                note = special_day["day_type"]["value_label"]
            elif weekday_index >= 5:
                day_class = "weekend"
                label = "Weekend"
                note = "Weekend"
            week_cells.append(
                {
                    "empty": False,
                    "day_number": day_number,
                    "iso_date": current_day_key,
                    "day_class": day_class,
                    "label": label,
                    "note": note,
                }
            )
        weeks.append(week_cells)

    prev_month = 12 if month == 1 else month - 1
    next_month = 1 if month == 12 else month + 1
    return {
        "year": year,
        "month": month,
        "month_name": month_name,
        "weekday_headers": weekday_headers,
        "weeks": weeks,
        "prev_month": prev_month,
        "next_month": next_month,
    }


def _calendar_summary_items(yearly_calendar: dict) -> list[dict]:
    summary = yearly_calendar["summary"]
    return [
        {"label": "Number of Weeks", "value": str(summary["week_count"])},
        {"label": "Weekday Working Days", "value": str(summary["weekday_count"])},
        {
            "label": "Active Holidays",
            "value": str(summary["active_holiday_count"]),
            "note": "National + local holidays",
        },
        {
            "label": "Timia Days / Other",
            "value": str(summary["active_timia_other_count"]),
        },
        {
            "label": "Net Working Days",
            "value": str(summary["net_working_day_count"]),
            "note": "Weekdays after active special days",
        },
    ]


def _pricing_model_rows(pricing_models: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/pricing-models/{pricing_model['id']}/",
            "cells": [
                pricing_model["name"],
                pricing_model["description"] or "None",
            ],
        }
        for pricing_model in pricing_models
    ]


def _pricing_model_detail_rows(pricing_model: dict) -> list[tuple[str, str]]:
    return [
        ("Pricing Model Name", pricing_model["name"]),
        ("Description", pricing_model["description"] or "None"),
    ]


def _general_charge_code_rows(general_charge_codes: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/general-charge-codes/{general_charge_code['id']}/",
            "cells": [
                general_charge_code["business_unit"]["bu_code"],
                general_charge_code["code"],
                general_charge_code["name"],
                general_charge_code["cost_center"]["cost_center_code"],
                (
                    ", ".join(role["code"] for role in general_charge_code["approver_roles"])
                    if general_charge_code["requires_approval_flag"]
                    else "Not required"
                ),
                general_charge_code["routing_health"]["status"],
                general_charge_code["charge_type"],
                general_charge_code["status"],
            ],
        }
        for general_charge_code in general_charge_codes
    ]


def _general_charge_code_detail_rows(general_charge_code: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", general_charge_code["business_unit"]["bu_code"]),
        ("Code", general_charge_code["code"]),
        ("Name", general_charge_code["name"]),
        (
            "Cost Center",
            (
                f"{general_charge_code['cost_center']['cost_center_code']} - "
                f"{general_charge_code['cost_center']['name']}"
            ),
        ),
        ("Charge Type", general_charge_code["charge_type"]),
        (
            "Flags",
            ", ".join(
                label
                for label, enabled in (
                    ("Billable", general_charge_code["billable_flag"]),
                    ("Requires Approval", general_charge_code["requires_approval_flag"]),
                    ("Description Required", general_charge_code["description_required_flag"]),
                )
                if enabled
            )
            or "None",
        ),
        (
            "Approver Roles",
            (
                ", ".join(
                    (
                        f"{role['code']} ({_member_count_label(role['active_member_count'])})"
                        if role["kind"] == "AD_HOC_ROLE"
                        else role["code"]
                    )
                    for role in general_charge_code["approver_roles"]
                )
                if general_charge_code["approver_roles"]
                else "None"
            ),
        ),
        ("Routing Status", general_charge_code["routing_health"]["status"]),
        (
            "Routing Warning",
            general_charge_code["routing_health"]["warning"] or "None",
        ),
        ("Valid From", general_charge_code["valid_from"]),
        ("Valid To", general_charge_code["valid_to"] or "Open-ended"),
        ("Status", general_charge_code["status"]),
    ]


def _general_charge_code_routing_detail_rows(
    general_charge_code: dict,
) -> list[tuple[str, str]]:
    return [
        (
            "Approver Roles",
            (
                ", ".join(
                    (
                        f"{role['code']} ({_member_count_label(role['active_member_count'])})"
                        if role["kind"] == "AD_HOC_ROLE"
                        else role["code"]
                    )
                    for role in general_charge_code["approver_roles"]
                )
                if general_charge_code["approver_roles"]
                else "None"
            ),
        ),
        ("Routing Status", general_charge_code["routing_health"]["status"]),
        (
            "Routing Warning",
            general_charge_code["routing_health"]["warning"] or "None",
        ),
    ]


def _general_charge_code_approval_role_rows(approval_roles: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/general-charge-code-approval-roles/{approval_role['id']}/",
            "cells": [
                approval_role["role_code"],
                approval_role["name"],
                str(approval_role["active_member_count"]),
                str(approval_role["dependent_general_charge_code_count"]),
                approval_role["routing_health"]["status"],
                approval_role["status"],
            ],
        }
        for approval_role in approval_roles
    ]


def _general_charge_code_approval_role_detail_rows(
    approval_role: dict,
) -> list[tuple[str, str]]:
    return [
        ("Role Code", approval_role["role_code"]),
        ("Name", approval_role["name"]),
        ("Description", approval_role["description"] or "None"),
        (
            "Members",
            (
                ", ".join(
                    f"{member['employee_code']} - {member['full_name']}"
                    for member in approval_role["member_employees"]
                )
                if approval_role["member_employees"]
                else "None"
            ),
        ),
        ("Active Member Count", str(approval_role["active_member_count"])),
        (
            "Referenced General Charge Codes",
            (
                ", ".join(
                    (
                        f"{general_charge_code['business_unit']['bu_code']} - "
                        f"{general_charge_code['code']} - {general_charge_code['name']}"
                    )
                    for general_charge_code in approval_role["dependent_general_charge_codes"]
                )
                if approval_role["dependent_general_charge_codes"]
                else "None"
            ),
        ),
        ("Routing Coverage", approval_role["routing_health"]["status"]),
        (
            "Coverage Warning",
            approval_role["routing_health"]["warning"] or "None",
        ),
        ("Status", approval_role["status"]),
    ]


def _general_charge_code_approval_role_coverage_detail_rows(
    approval_role: dict,
) -> list[tuple[str, str]]:
    return [
        ("Active Member Count", str(approval_role["active_member_count"])),
        (
            "Referenced General Charge Codes",
            (
                ", ".join(
                    (
                        f"{general_charge_code['business_unit']['bu_code']} - "
                        f"{general_charge_code['code']} - {general_charge_code['name']}"
                    )
                    for general_charge_code in approval_role["dependent_general_charge_codes"]
                )
                if approval_role["dependent_general_charge_codes"]
                else "None"
            ),
        ),
        ("Routing Coverage", approval_role["routing_health"]["status"]),
        (
            "Coverage Warning",
            approval_role["routing_health"]["warning"] or "None",
        ),
    ]


def _project_rows(projects: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/projects/{project['id']}/",
            "cells": [
                project["business_unit"]["name"],
                project["project_code"],
                project["name"],
                project["client"]["name"],
                project["status"],
                project["project_owner_employee"]["full_name"],
                project["project_manager_employee"]["full_name"],
                {
                    "text": str(project["employee_count"]),
                    "href": (
                        "/system/project-assignments/"
                        f"?status=ALL&client_id={project['client']['id']}"
                        f"&project_id={project['id']}"
                    ),
                },
            ],
        }
        for project in projects
    ]


def _project_collection_filter_fields(
    current_user: CurrentUser,
    *,
    selected_client_id: str = "",
) -> list[dict]:
    return [
        _field(
            name="client_id",
            label="Client",
            kind="select",
            value=selected_client_id,
            options=_scoped_client_options(
                current_user,
                selected=selected_client_id,
                include_blank=True,
                active_only=True,
            ),
        )
    ]


def _project_collection_hidden_filters(
    *,
    selected_status_code: str,
    selected_business_unit_id: str,
) -> list[dict]:
    hidden_fields = [{"name": "status", "value": selected_status_code}]
    if selected_business_unit_id:
        hidden_fields.append(
            {
                "name": "business_unit_id",
                "value": selected_business_unit_id,
            }
        )
    return hidden_fields


def _project_detail_rows(project: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", project["business_unit"]["bu_code"]),
        ("Project Code", project["project_code"]),
        ("Project Name", project["name"]),
        ("Description", project["description"] or "None"),
        ("Project Owner", project["project_owner_employee"]["employee_code"]),
        ("Project Manager", project["project_manager_employee"]["employee_code"]),
        ("Client", project["client"]["client_code"]),
        ("Internal Category", project["internal_category"]["category_code"]),
        ("Cost Center", project["cost_center"]["cost_center_code"]),
        ("Pricing Model", project["pricing_model"]["name"]),
        ("Start Date", project["start_date"]),
        ("End Date", project["end_date"] or "Open-ended"),
        ("Close Date", project["close_date"] or "Open"),
        ("Billable", "Yes" if project["billable_flag"] else "No"),
        ("Status", project["status"]),
    ]


def _project_assignment_rows(assignments: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/project-assignments/{assignment['id']}/",
            "cells": [
                assignment["project"]["client"]["name"],
                assignment["project"]["project_code"],
                assignment["project"]["name"],
                (
                    f"{assignment['employee']['employee_code']} - "
                    f"{assignment['employee']['full_name']}"
                ),
                assignment["assignment_start_date"],
                assignment["assignment_end_date"] or "Open-ended",
                assignment["status"],
            ],
        }
        for assignment in assignments
    ]


def _project_assignment_detail_rows(assignment: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", assignment["project"]["business_unit"]["bu_code"]),
        ("Project", assignment["project"]["project_code"]),
        (
            "Employee",
            f"{assignment['employee']['employee_code']} - {assignment['employee']['full_name']}",
        ),
        ("Assignment Start Date", assignment["assignment_start_date"]),
        ("Assignment End Date", assignment["assignment_end_date"] or "Open-ended"),
        ("Status", assignment["status"]),
    ]


def _calendar_period_rule_rows(period_rules: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/calendar-period-rules/{period_rule['id']}/",
            "cells": [
                str(period_rule["yearly_calendar"]["calendar_year"]),
                period_rule["yearly_calendar"]["calendar_name"],
                (
                    period_rule["business_unit"]["bu_code"]
                    if period_rule["business_unit"] is not None
                    else "Unassigned"
                ),
                period_rule["effective_from"],
                period_rule["effective_to"],
                period_rule["status"],
            ],
        }
        for period_rule in period_rules
    ]


def _calendar_period_rule_detail_rows(period_rule: dict) -> list[tuple[str, str]]:
    return [
        ("Office", period_rule["office"]["office_name"]),
        ("Calendar", period_rule["yearly_calendar"]["name"]),
        (
            "Business Unit",
            (
                period_rule["business_unit"]["bu_code"]
                if period_rule["business_unit"] is not None
                else "Unassigned"
            ),
        ),
        ("Effective From", period_rule["effective_from"]),
        ("Effective To", period_rule["effective_to"]),
        ("Monday Max Hours", period_rule["monday_max_hours"]),
        ("Tuesday Max Hours", period_rule["tuesday_max_hours"]),
        ("Wednesday Max Hours", period_rule["wednesday_max_hours"]),
        ("Thursday Max Hours", period_rule["thursday_max_hours"]),
        ("Friday Max Hours", period_rule["friday_max_hours"]),
        (
            "Working On Saturdays",
            "Yes" if period_rule["working_on_saturdays_flag"] else "No",
        ),
        ("Saturday Max Hours", period_rule["saturday_max_hours"]),
        (
            "Working On Sundays",
            "Yes" if period_rule["working_on_sundays_flag"] else "No",
        ),
        ("Sunday Max Hours", period_rule["sunday_max_hours"]),
        ("Status", period_rule["status"]),
    ]


def _office_form_fields(
    *, post_data: QueryDict | None = None, entity: dict | None = None
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    return [
        _field(
            name="country_id",
            label="Country",
            kind="select",
            options=_country_options(
                selected=submitted_data.get(
                    "country_id",
                    entity["country"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="office_name",
            label="Office Name",
            kind="text",
            value=submitted_data.get("office_name", entity["office_name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "COUNTRY_STATUS",
                selected=submitted_data.get("status_code", entity["status"] if entity else "ACTIVE")
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
            help_text="Only Timesheet Master Administrators can activate or deactivate offices.",
        ),
    ]


def _country_form_fields(
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    return [
        _field(
            name="country_code",
            label="Country Code",
            kind="text",
            value=submitted_data.get("country_code", entity["country_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="country_name",
            label="Country Name",
            kind="text",
            value=submitted_data.get("country_name", entity["country_name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "COUNTRY_STATUS",
                selected=submitted_data.get("status_code", entity["status"] if entity else "ACTIVE")
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
            help_text="Only Timesheet Master Administrators can activate or deactivate countries.",
        ),
    ]


def _office_bootstrap_fields(*, post_data: QueryDict | None = None) -> list[dict]:
    return [
        _field(
            name="bootstrap_bu_code",
            label="Initial Business Unit Code",
            kind="text",
            value=post_data.get("bootstrap_bu_code", "") if post_data is not None else "",
            required=True,
            help_text="Required starter Business Unit code for the new Office.",
        ),
        _field(
            name="bootstrap_bu_name",
            label="Initial Business Unit Name",
            kind="text",
            value=post_data.get("bootstrap_bu_name", "") if post_data is not None else "",
            required=True,
            help_text="Required starter Business Unit name for the new Office.",
        ),
        _field(
            name="bootstrap_bu_description",
            label="Initial Business Unit Description",
            kind="textarea",
            value=post_data.get("bootstrap_bu_description", "") if post_data is not None else "",
            help_text="Optional description for the starter Business Unit.",
        ),
        _field(
            name="bootstrap_admin_employee_code",
            label="Initial Admin Employee Code",
            kind="text",
            value=(
                post_data.get("bootstrap_admin_employee_code", "")
                if post_data is not None
                else ""
            ),
            required=True,
            help_text="Required employee code for the first Office administrator.",
        ),
        _field(
            name="bootstrap_admin_full_name",
            label="Initial Admin Full Name",
            kind="text",
            value=post_data.get("bootstrap_admin_full_name", "") if post_data is not None else "",
            required=True,
            help_text="Required full name for the first Office administrator.",
        ),
        _field(
            name="bootstrap_admin_email",
            label="Initial Admin Email",
            kind="email",
            value=post_data.get("bootstrap_admin_email", "") if post_data is not None else "",
            required=True,
            width_mode="full",
            help_text=(
                "Required email for the first Office administrator. The created "
                "employee receives USER and TS_ADMIN roles automatically."
            ),
        ),
    ]


def _configuration_fields(
    entity: dict,
    *,
    post_data: QueryDict | None = None,
    read_only: bool = False,
    scope_label: str,
    paired_layout: bool = False,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    configuration = entity["configuration"]
    help_scope = "the parent Office" if read_only else scope_label
    return [
        _field(
            name="approval_mode_code",
            label="Approval Mode",
            kind="select",
            options=_ref_options(
                "APPROVAL_MODE",
                selected=submitted_data.get(
                    "approval_mode_code",
                    configuration["approval_mode"],
                )
                if post_data is not None
                else configuration["approval_mode"],
            ),
            required=True,
            disabled=read_only,
            help_text=(
                "Defines how submitted time is routed for approval. The current "
                f"working option is project-based approval for {help_scope}."
            ),
            width_mode="column" if paired_layout else "auto",
        ),
        _field(
            name="enable_copy_previous_week_flag",
            label="Enable Copy Previous Week",
            kind="checkbox",
            checked=_bool_from_post(post_data, "enable_copy_previous_week_flag")
            if post_data is not None
            else bool(configuration["enable_copy_previous_week_flag"]),
            disabled=read_only,
            help_text=(
                "If enabled, the My Timesheets screen shows a user-initiated "
                "Copy Prev. Week action that creates the selected week from the "
                f"employee's most recent approved timesheet in {help_scope}."
            ),
            width_mode="column" if paired_layout else "auto",
        ),
        _field(
            name="allow_employee_withdraw_flag",
            label="Allow Employee Withdraw",
            kind="checkbox",
            checked=_bool_from_post(post_data, "allow_employee_withdraw_flag")
            if post_data is not None
            else bool(configuration["allow_employee_withdraw_flag"]),
            disabled=read_only,
            help_text=(
                "If enabled, employees may withdraw a submitted timesheet before "
                f"final approval for {help_scope}."
            ),
            width_mode="column" if paired_layout else "auto",
        ),
        _field(
            name="timesheet_cutoff_date",
            label="Timesheet Cutoff Date",
            kind="date",
            value=submitted_data.get(
                "timesheet_cutoff_date",
                configuration["timesheet_cutoff_date"] or "",
            )
            if post_data is not None
            else configuration["timesheet_cutoff_date"] or "",
            readonly=read_only,
            disabled=read_only,
            help_text=(
                "Optional date before which employee timesheets become locked for "
                f"edit or submit in {help_scope}."
            ),
        ),
        _field(
            name="count_non_billable_in_daily_limit_flag",
            label="Count Non-billable In Daily Limit",
            kind="checkbox",
            checked=_bool_from_post(post_data, "count_non_billable_in_daily_limit_flag")
            if post_data is not None
            else bool(configuration["count_non_billable_in_daily_limit_flag"]),
            disabled=read_only,
            help_text=(
                "If enabled, non-billable hours count toward the daily calendar "
                f"hour limit for {help_scope}."
            ),
            width_mode="column" if paired_layout else "auto",
        ),
        _field(
            name="archive_after_years",
            label="Archive After Years",
            kind="number",
            value=submitted_data.get(
                "archive_after_years",
                str(configuration["archive_after_years"]),
            )
            if post_data is not None
            else str(configuration["archive_after_years"]),
            required=True,
            readonly=read_only,
            disabled=read_only,
            help_text=(
                "Retention period, in years, before approved historical "
                f"timesheets become archive candidates for {help_scope}. Must be greater than 0."
            ),
        ),
        _field(
            name="enable_timer_flag",
            label="Enable Timer",
            kind="checkbox",
            checked=_bool_from_post(post_data, "enable_timer_flag")
            if post_data is not None
            else bool(configuration["enable_timer_flag"]),
            disabled=read_only,
            help_text=(
                "Reserved switch for future timer-based time capture within "
                f"{help_scope}."
            ),
            width_mode="column" if paired_layout else "auto",
        ),
        _field(
            name="enable_leave_integration_flag",
            label="Enable Leave Integration",
            kind="checkbox",
            checked=_bool_from_post(post_data, "enable_leave_integration_flag")
            if post_data is not None
            else bool(configuration["enable_leave_integration_flag"]),
            disabled=read_only,
            help_text=(
                "Reserved switch for future integration that imports leave or "
                f"absence data into timesheet behavior for {help_scope}."
            ),
            width_mode="column" if paired_layout else "auto",
        ),
    ]


def _business_unit_general_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    submitted_data = post_data or QueryDict("")
    return [
        _office_display_field(
            entity["office"]["office_name"] if entity else current_user.office_name
        ),
        _field(
            name="bu_code",
            label="Business Unit Code",
            kind="text",
            value=submitted_data.get("bu_code", entity["bu_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
            help_text="Short internal code used across projects, calendars, reports, and scope.",
        ),
        _field(
            name="name",
            label="Business Unit Name",
            kind="text",
            value=submitted_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
            help_text="Human-readable Business Unit name shown in the UI.",
        ),
        _field(
            name="description",
            label="Description",
            kind="textarea",
            value=submitted_data.get("description", entity["description"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            help_text="Optional context to describe what this Business Unit is used for.",
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "BUSINESS_UNIT_STATUS",
                selected=submitted_data.get(
                    "status_code", entity["status"] if entity else "ACTIVE"
                )
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
            help_text=(
                "Inactive Business Units stay visible for history but should not "
                "be used for new work."
            ),
        ),
    ]


def _business_unit_configuration_fields(
    entity: dict,
    *,
    post_data: QueryDict | None = None,
    read_only: bool = False,
) -> list[dict]:
    return _configuration_fields(
        entity,
        post_data=post_data,
        read_only=read_only,
        scope_label="this Business Unit",
    )


def _office_configuration_fields(
    entity: dict,
    *,
    post_data: QueryDict | None = None,
) -> list[dict]:
    return _configuration_fields(
        entity,
        post_data=post_data,
        scope_label="this Office",
        paired_layout=True,
    )


def _business_unit_rows(business_units: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/business-units/{business_unit['id']}/",
            "cells": [
                business_unit["bu_code"],
                business_unit["name"],
                business_unit["status"],
                business_unit["description"] or "None",
                str(business_unit["employee_count"]),
                str(business_unit["project_count"]),
            ],
        }
        for business_unit in business_units
    ]


def _business_unit_detail_rows(business_unit: dict) -> list[tuple[str, str]]:
    return [
        ("Office", business_unit["office"]["office_name"]),
        ("Business Unit Code", business_unit["bu_code"]),
        ("Business Unit Name", business_unit["name"]),
        ("Description", business_unit["description"] or "None"),
        ("Status", business_unit["status"]),
        ("Employee Count", str(business_unit["employee_count"])),
        ("Project Count", str(business_unit["project_count"])),
    ]


def _office_rows(offices: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/offices/{office['id']}/",
            "cells": [
                office["country"]["country_name"],
                office["office_name"],
                str(office["active_employee_count"]),
                office["status"],
            ],
        }
        for office in offices
    ]


def _office_detail_rows(office: dict) -> list[tuple[str, str]]:
    return [
        (
            "Country",
            f"{office['country']['country_code']} - {office['country']['country_name']}",
        ),
        ("Office Name", office["office_name"]),
        ("Status", office["status"]),
    ]


def _country_rows(countries: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/countries/{country['id']}/",
            "cells": [
                country["country_code"],
                country["country_name"],
                str(country["office_count"]),
                country["status"],
            ],
        }
        for country in countries
    ]


def _country_detail_rows(country: dict) -> list[tuple[str, str]]:
    return [
        ("Country Code", country["country_code"]),
        ("Country Name", country["country_name"]),
        ("Office Count", str(country["office_count"])),
        ("Status", country["status"]),
    ]


def _office_administrator_rows(office: dict) -> list[tuple[str, str]]:
    return [
        (
            f"Administrator {index}",
            (
                f"{administrator['employee_code']} - {administrator['full_name']} - "
                f"{administrator['email']} - Primary BU: "
                f"{administrator['primary_business_unit']['bu_code']} - "
                f"Status: {administrator['status']}"
            ),
        )
        for index, administrator in enumerate(office["administrators"], start=1)
    ]


BUSINESS_UNIT_CONFIG = MasterUiConfig(
    section_key="business-units",
    list_title="Business Unit Management",
    list_eyebrow="SCR-102",
    list_intro="Scoped Business Unit list for Timesheet Administrators in the active office.",
    detail_title="Business Unit Detail",
    detail_eyebrow="SCR-103",
    detail_intro=(
        "Maintain Business Unit identity while reviewing inherited Office "
        "configuration inside the shared shell."
    ),
    singular_label="Business Unit",
    plural_label="Business Units",
    collection_path="/system/business-units/",
    detail_path_prefix="/system/business-units/",
    table_headers=("BU Code", "Name", "Status", "Description", "Employees", "Projects"),
    empty_message="No Business Units are available in your assigned scope yet.",
)


OFFICE_CONFIG = MasterUiConfig(
    section_key="offices",
    list_title="Office Management",
    list_eyebrow="SCR-100",
    list_intro=(
        "Master administration list for Office lifecycle, identity, and "
        "inherited configuration management."
    ),
    detail_title="Office Detail",
    detail_eyebrow="SCR-101",
    detail_intro=(
        "Update Office identity, lifecycle state, and inherited operational "
        "configuration."
    ),
    singular_label="Office",
    plural_label="Offices",
    collection_path="/system/offices/",
    detail_path_prefix="/system/offices/",
    table_headers=("Country", "Office", "Employees", "Status"),
    empty_message="No offices are available yet.",
)

COUNTRY_CONFIG = MasterUiConfig(
    section_key="countries",
    list_title="Country Management",
    list_eyebrow="SCR-098",
    list_intro="Master administration list for Country lifecycle and identity management.",
    detail_title="Country Detail",
    detail_eyebrow="SCR-099",
    detail_intro="Update Country identity and lifecycle state.",
    singular_label="Country",
    plural_label="Countries",
    collection_path="/system/countries/",
    detail_path_prefix="/system/countries/",
    table_headers=("Country Code", "Country Name", "Offices", "Status"),
    empty_message="No countries are available yet.",
)


CLIENT_CONFIG = MasterUiConfig(
    section_key="clients",
    list_title="Client Management",
    list_eyebrow="SCR-130",
    list_intro=(
        "Office-scoped client list with server-rendered create form for "
        "Timesheet Administrators."
    ),
    detail_title="Client Detail",
    detail_eyebrow="SCR-131",
    detail_intro="Update client identity and lifecycle fields within your active Office.",
    singular_label="Client",
    plural_label="Clients",
    collection_path="/system/clients/",
    detail_path_prefix="/system/clients/",
    table_headers=(
        "Client Code",
        "Name",
        "Business Unit",
        "Projects",
        "Employees",
        "Status",
        "Parent",
    ),
    empty_message="No clients are available in your active Office yet.",
)

INTERNAL_CATEGORY_CONFIG = MasterUiConfig(
    section_key="internal-categories",
    list_title="Internal Category Management",
    list_eyebrow="SCR-140",
    list_intro="Scoped internal category list with create form for the current admin scope.",
    detail_title="Internal Category Detail",
    detail_eyebrow="SCR-141",
    detail_intro=(
        "Update the selected internal category without leaving the shared System Management shell."
    ),
    singular_label="Internal Category",
    plural_label="Internal Categories",
    collection_path="/system/internal-categories/",
    detail_path_prefix="/system/internal-categories/",
    table_headers=("Business Unit", "Category Code", "Name", "Status"),
    empty_message="No internal categories are available in your assigned Business Units yet.",
)

COST_CENTER_CONFIG = MasterUiConfig(
    section_key="cost-centers",
    list_title="Cost Center Management",
    list_eyebrow="SCR-150",
    list_intro="Office-scoped cost center list with create form for Timesheet Administrators.",
    detail_title="Cost Center Detail",
    detail_eyebrow="SCR-151",
    detail_intro="Update cost center attributes within your active Office.",
    singular_label="Cost Center",
    plural_label="Cost Centers",
    collection_path="/system/cost-centers/",
    detail_path_prefix="/system/cost-centers/",
    table_headers=("Cost Center Code", "Name", "Status"),
    empty_message="No cost centers are available in your active Office yet.",
)

PRICING_MODEL_CONFIG = MasterUiConfig(
    section_key="pricing-models",
    list_title="Pricing Model Management",
    list_eyebrow="SCR-155",
    list_intro="Office-scoped pricing model list with create, update, and delete flows.",
    detail_title="Pricing Model Detail",
    detail_eyebrow="SCR-156",
    detail_intro="Update office-level pricing models used by downstream project setup.",
    singular_label="Pricing Model",
    plural_label="Pricing Models",
    collection_path="/system/pricing-models/",
    detail_path_prefix="/system/pricing-models/",
    table_headers=("Pricing Model Name", "Description"),
    empty_message="No pricing models are available in your active Office yet.",
)

GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG = MasterUiConfig(
    section_key="general-charge-code-approval-roles",
    list_title="General Charge Code Approval Role Management",
    list_eyebrow="SCR-168",
    list_intro=(
        "Office-scoped ad-hoc approval roles for General Charge Code routing, "
        "including employee membership maintenance."
    ),
    detail_title="General Charge Code Approval Role Detail",
    detail_eyebrow="SCR-169",
    detail_intro=(
        "Update the selected ad-hoc approval role, member employees, and lifecycle "
        "status inside the shared shell."
    ),
    singular_label="General Charge Code Approval Role",
    plural_label="General Charge Code Approval Roles",
    collection_path="/system/general-charge-code-approval-roles/",
    detail_path_prefix="/system/general-charge-code-approval-roles/",
    table_headers=("Role Code", "Name", "Members", "GCCs", "Coverage", "Status"),
    empty_message=(
        "No ad-hoc General Charge Code approval roles are available in your active "
        "Office yet."
    ),
)

GENERAL_CHARGE_CODE_CONFIG = MasterUiConfig(
    section_key="general-charge-codes",
    list_title="General Charge Code Management",
    list_eyebrow="SCR-170",
    list_intro=(
        "Scoped general charge code list with create form, "
        "Office Cost Center link, and lifecycle fields."
    ),
    detail_title="General Charge Code Detail",
    detail_eyebrow="SCR-171",
    detail_intro=(
        "Update charge-code validity, Cost Center assignment, flags, "
        "and lifecycle fields inside the shared shell."
    ),
    singular_label="General Charge Code",
    plural_label="General Charge Codes",
    collection_path="/system/general-charge-codes/",
    detail_path_prefix="/system/general-charge-codes/",
    table_headers=(
        "Business Unit",
        "Code",
        "Name",
        "Cost Center",
        "Approvers",
        "Routing",
        "Charge Type",
        "Status",
    ),
    empty_message="No general charge codes are available in your assigned Business Units yet.",
)

PROJECT_CONFIG = MasterUiConfig(
    section_key="projects",
    list_title="Project Management",
    list_eyebrow="SCR-180",
    list_intro="Scoped project list with create form for Timesheet Administrators.",
    detail_title="Project Detail",
    detail_eyebrow="SCR-181",
    detail_intro="Update project ownership, pricing, classification, dates, and lifecycle fields.",
    singular_label="Project",
    plural_label="Projects",
    collection_path="/system/projects/",
    detail_path_prefix="/system/projects/",
    table_headers=(
        "Business Unit",
        "Project Code",
        "Project Name",
        "Client",
        "Status",
        "Owner",
        "Manager",
        "Employees",
    ),
    empty_message="No projects are available in your assigned Business Units yet.",
)

PROJECT_ASSIGNMENT_CONFIG = MasterUiConfig(
    section_key="project-assignments",
    list_title="Project Assignment Management",
    list_eyebrow="SCR-190",
    list_intro="Scoped project assignment list with lifecycle-aware create and update flows.",
    detail_title="Project Assignment Detail",
    detail_eyebrow="SCR-191",
    detail_intro="Update assignment window and active/inactive lifecycle fields.",
    singular_label="Project Assignment",
    plural_label="Project Assignments",
    collection_path="/system/project-assignments/",
    detail_path_prefix="/system/project-assignments/",
    table_headers=("Client", "Project", "Project Name", "Employee", "Start", "End", "Status"),
    empty_message="No project assignments are available in your assigned Business Units yet.",
)

YEARLY_CALENDAR_CONFIG = MasterUiConfig(
    section_key="calendars",
    list_title="Calendar Management",
    list_eyebrow="SCR-115",
    list_intro=(
        "Manage yearly calendars and navigate into each calendar's special-day workspace."
    ),
    detail_title="Calendar Detail",
    detail_eyebrow="SCR-116",
    detail_intro="Review yearly calendar summary, month view, and special-day configuration.",
    singular_label="Calendar",
    plural_label="Calendars",
    collection_path="/system/calendars/",
    detail_path_prefix="/system/calendars/",
    table_headers=("Year", "Calendar", "Status"),
    empty_message="No yearly calendars are available in your active Office yet.",
)

CALENDAR_PERIOD_RULE_CONFIG = MasterUiConfig(
    section_key="calendar-period-rules",
    list_title="Calendar Period Rule Management",
    list_eyebrow="SCR-120",
    list_intro="Scoped calendar period rule list with overlap-safe create and update flows.",
    detail_title="Calendar Period Rule Detail",
    detail_eyebrow="SCR-121",
    detail_intro="Update period-rule windows and daily hour limits inside the shared shell.",
    singular_label="Calendar Period Rule",
    plural_label="Calendar Period Rules",
    collection_path="/system/calendar-period-rules/",
    detail_path_prefix="/system/calendar-period-rules/",
    table_headers=("Year", "Calendar", "Business Unit", "Effective From", "Effective To", "Status"),
    empty_message="No calendar period rules are available in your active Office yet.",
)


@require_http_methods(["GET", "POST"])
def business_units_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if request.method == "POST":
        try:
            business_unit = BusinessUnitManagementService.create_business_unit(
                current_user,
                {
                    "bu_code": request.POST.get("bu_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError:
            pass
        else:
            return redirect(f"/system/business-units/{business_unit['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="BUSINESS_UNIT_STATUS",
        default_code="ACTIVE",
    )
    business_units = BusinessUnitManagementService.list_business_units(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_list_only_collection(
        request,
        current_user,
        title=BUSINESS_UNIT_CONFIG.list_title,
        eyebrow=BUSINESS_UNIT_CONFIG.list_eyebrow,
        intro=BUSINESS_UNIT_CONFIG.list_intro,
        table_headers=BUSINESS_UNIT_CONFIG.table_headers,
        table_rows=_business_unit_rows(business_units),
        empty_message=BUSINESS_UNIT_CONFIG.empty_message,
        create_label="Create Business Unit",
        create_href="/system/business-units/new/",
        filter_links=filter_links,
        filter_title="Business Unit Status",
    )


@require_http_methods(["GET", "POST"])
def business_unit_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            business_unit = BusinessUnitManagementService.create_business_unit(
                current_user,
                {
                    "bu_code": request.POST.get("bu_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/business-units/{business_unit['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=BUSINESS_UNIT_CONFIG,
        form_fields=_business_unit_general_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro=(
            "Create a new Business Unit in your active office. It will inherit its "
            "operational configuration from the parent Office, and your admin scope will "
            "be extended to include it."
        ),
    )


@require_http_methods(["GET", "POST"])
def business_unit_detail(request: HttpRequest, business_unit_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "general"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "general")
        if active_form == "general":
            payload = {
                "bu_code": request.POST.get("bu_code", ""),
                "name": request.POST.get("name", ""),
                "description": request.POST.get("description", ""),
                "status_code": request.POST.get("status_code", ""),
            }
        elif active_form == "delete":
            payload = {}
        else:
            return _render_access_denied(
                request,
                message="Unknown Business Unit form submission.",
                status=400,
            )
        try:
            if active_form == "delete":
                BusinessUnitManagementService.delete_business_unit(
                    current_user,
                    business_unit_id,
                )
            else:
                BusinessUnitManagementService.update_business_unit(
                    current_user,
                    business_unit_id,
                    payload,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(BUSINESS_UNIT_CONFIG.collection_path)
            return redirect(f"/system/business-units/{business_unit_id}/")

    try:
        business_unit = BusinessUnitManagementService.get_business_unit(
            current_user,
            business_unit_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=BUSINESS_UNIT_CONFIG.detail_title,
            eyebrow=BUSINESS_UNIT_CONFIG.detail_eyebrow,
            intro=BUSINESS_UNIT_CONFIG.detail_intro,
            error=error,
        )

    form_sections = [
        {
            "form_name": "general",
            "title": "General",
            "intro": "Update Business Unit identity, description, and lifecycle status.",
            "submit_label": "Save Business Unit",
            "form_error": form_error if active_form == "general" else "",
            "fields": _business_unit_general_fields(
                current_user,
                post_data=post_data if active_form == "general" else None,
                entity=business_unit,
            ),
        },
        {
            "form_name": "configuration",
            "title": "Inherited Configuration",
            "intro": (
                "These values come from the parent Office and are shown here for reference only."
            ),
            "read_only": True,
            "fields": _business_unit_configuration_fields(
                business_unit,
                read_only=True,
            ),
        },
        _delete_action_section(
            submit_label="Delete Business Unit",
            form_error=form_error if active_form == "delete" else "",
        ),
    ]
    return _render_detail_page(
        request,
        current_user,
        title=business_unit["name"],
        eyebrow=BUSINESS_UNIT_CONFIG.detail_eyebrow,
        intro=BUSINESS_UNIT_CONFIG.detail_intro,
        detail_rows=_business_unit_detail_rows(business_unit),
        form_sections=form_sections,
        back_href=BUSINESS_UNIT_CONFIG.collection_path,
        back_label="Back to Business Units",
        entity_status=business_unit["status"],
        show_detail_panel=False,
        page_action={
            "label": "Back to Business Units",
            "href": BUSINESS_UNIT_CONFIG.collection_path,
        },
    )


@require_http_methods(["GET"])
def countries_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="COUNTRY_STATUS",
        default_code="ACTIVE",
    )
    countries = CountryManagementService.list_countries(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_list_only_collection(
        request,
        current_user,
        title=COUNTRY_CONFIG.list_title,
        eyebrow=COUNTRY_CONFIG.list_eyebrow,
        intro=COUNTRY_CONFIG.list_intro,
        table_headers=COUNTRY_CONFIG.table_headers,
        table_rows=_country_rows(countries),
        empty_message=COUNTRY_CONFIG.empty_message,
        create_label="Create Country",
        create_href="/system/countries/new/",
        filter_links=filter_links,
        filter_title="Country Status",
    )


@require_http_methods(["GET", "POST"])
def country_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            country = CountryManagementService.create_country(
                current_user,
                {
                    "country_code": request.POST.get("country_code", ""),
                    "country_name": request.POST.get("country_name", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/countries/{country['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=COUNTRY_CONFIG,
        form_fields=_country_form_fields(post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Country that Offices can be assigned to.",
    )


@require_http_methods(["GET", "POST"])
def country_detail(request: HttpRequest, country_id: int) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "general"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "general")
        payload = {}
        if active_form == "general":
            payload = {
                "country_code": request.POST.get("country_code", ""),
                "country_name": request.POST.get("country_name", ""),
                "status_code": request.POST.get("status_code", ""),
            }
        elif active_form == "delete":
            payload = {}
        else:
            return _render_access_denied(
                request,
                message="Unknown Country form submission.",
                status=400,
            )
        try:
            if active_form == "delete":
                CountryManagementService.delete_country(current_user, country_id)
            else:
                CountryManagementService.update_country(current_user, country_id, payload)
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(COUNTRY_CONFIG.collection_path)
            return redirect(f"/system/countries/{country_id}/")

    try:
        country = CountryManagementService.get_country(current_user, country_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=COUNTRY_CONFIG.detail_title,
            eyebrow=COUNTRY_CONFIG.detail_eyebrow,
            intro=COUNTRY_CONFIG.detail_intro,
            error=error,
        )

    form_sections = [
        {
            "form_name": "general",
            "title": "General",
            "intro": "Update Country identity and lifecycle status.",
            "submit_label": "Save Country",
            "form_error": form_error if active_form == "general" else "",
            "fields": _country_form_fields(
                post_data=post_data if active_form == "general" else None,
                entity=country,
            ),
        },
        {
            "form_name": "delete",
            "title": "Delete Country",
            "intro": (
                "Delete this Country only if it has no Offices or other dependent records. "
                "If it is still in use, deletion will be blocked."
            ),
            "submit_label": "Delete Country",
            "form_error": form_error if active_form == "delete" else "",
            "fields": [],
        },
    ]
    return _render_detail_page(
        request,
        current_user,
        title=country["name"],
        eyebrow=COUNTRY_CONFIG.detail_eyebrow,
        intro=COUNTRY_CONFIG.detail_intro,
        detail_rows=_country_detail_rows(country),
        form_sections=form_sections,
        back_href=COUNTRY_CONFIG.collection_path,
        back_label=f"Back to {COUNTRY_CONFIG.plural_label}",
        entity_status=country["status"],
    )


@require_http_methods(["GET", "POST"])
def offices_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="COUNTRY_STATUS",
        default_code="ACTIVE",
    )
    offices = OfficeManagementService.list_offices(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_collection_page(
        request,
        current_user,
        title=OFFICE_CONFIG.list_title,
        eyebrow=OFFICE_CONFIG.list_eyebrow,
        intro=OFFICE_CONFIG.list_intro,
        table_headers=OFFICE_CONFIG.table_headers,
        table_rows=_office_rows(offices),
        empty_message=OFFICE_CONFIG.empty_message,
        filter_links=filter_links,
        filter_title="Office Status",
        show_filter_panel=False,
        records_heading="",
        title_filter_links=filter_links,
        title_filter_title="Office Status",
        bottom_action={"label": "Create Office", "href": "/system/offices/new/"},
    )


@require_http_methods(["GET", "POST"])
def office_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            office = OfficeManagementService.create_office(
                current_user,
                {
                    "country_id": request.POST.get("country_id", ""),
                    "office_name": request.POST.get("office_name", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                    "bootstrap_bu_code": request.POST.get("bootstrap_bu_code", ""),
                    "bootstrap_bu_name": request.POST.get("bootstrap_bu_name", ""),
                    "bootstrap_bu_description": request.POST.get(
                        "bootstrap_bu_description", ""
                    ),
                    "bootstrap_admin_employee_code": request.POST.get(
                        "bootstrap_admin_employee_code", ""
                    ),
                    "bootstrap_admin_full_name": request.POST.get(
                        "bootstrap_admin_full_name", ""
                    ),
                    "bootstrap_admin_email": request.POST.get("bootstrap_admin_email", ""),
                    "approval_mode_code": request.POST.get("approval_mode_code", ""),
                    "allow_employee_withdraw_flag": _bool_from_post(
                        request.POST, "allow_employee_withdraw_flag"
                    ),
                    "timesheet_cutoff_date": request.POST.get("timesheet_cutoff_date", ""),
                    "count_non_billable_in_daily_limit_flag": _bool_from_post(
                        request.POST,
                        "count_non_billable_in_daily_limit_flag",
                    ),
                    "archive_after_years": request.POST.get("archive_after_years", ""),
                    "enable_timer_flag": _bool_from_post(request.POST, "enable_timer_flag"),
                    "enable_leave_integration_flag": _bool_from_post(
                        request.POST,
                        "enable_leave_integration_flag",
                    ),
                    "enable_copy_previous_week_flag": _bool_from_post(
                        request.POST,
                        "enable_copy_previous_week_flag",
                    ),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/offices/{office['id']}/")

    return _render_detail_page(
        request,
        current_user,
        title="Create Office",
        eyebrow=OFFICE_CONFIG.list_eyebrow,
        intro=(
            "Create a new Office inside an existing Country, bootstrap its first "
            "Business Unit and Office administrator, and define the inherited "
            "configuration shared by the Office."
        ),
        detail_rows=[],
        form_sections=[
            {
                "form_name": "create",
                "title": "Office Setup",
                "intro": (
                    "Complete the Office identity, bootstrap Business Unit, "
                    "bootstrap administrator, and inherited configuration."
                ),
                "submit_label": "Create Office",
                "form_error": form_error,
                "fields": (
                    _office_form_fields(post_data=post_data)
                    + _office_bootstrap_fields(post_data=post_data)
                    + _office_configuration_fields(
                        {
                            "configuration": {
                                "approval_mode": "PROJECT",
                                "allow_employee_withdraw_flag": False,
                                "timesheet_cutoff_date": None,
                                "count_non_billable_in_daily_limit_flag": False,
                                "archive_after_years": 5,
                                "enable_timer_flag": False,
                                "enable_leave_integration_flag": False,
                                "enable_copy_previous_week_flag": False,
                            }
                        },
                        post_data=post_data,
                    )
                ),
                "fields_grid_class": "office-form-grid",
                "section_class": "office-detail-section",
            }
        ],
        back_href=OFFICE_CONFIG.collection_path,
        back_label=f"Back to {OFFICE_CONFIG.plural_label}",
        entity_status="New",
        show_detail_panel=False,
        detail_content_class="office-detail-layout",
        page_action={
            "label": f"Back to {OFFICE_CONFIG.plural_label}",
            "href": OFFICE_CONFIG.collection_path,
        },
    )


@require_http_methods(["GET", "POST"])
def office_detail(request: HttpRequest, office_id: int) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "general"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "general")
        payload = {}
        if active_form == "general":
            payload = {
                "country_id": request.POST.get("country_id", ""),
                "office_name": request.POST.get("office_name", ""),
                "status_code": request.POST.get("status_code", ""),
            }
        elif active_form == "configuration":
            payload = {
                "approval_mode_code": request.POST.get("approval_mode_code", ""),
                "allow_employee_withdraw_flag": _bool_from_post(
                    request.POST, "allow_employee_withdraw_flag"
                ),
                "timesheet_cutoff_date": request.POST.get("timesheet_cutoff_date", ""),
                "count_non_billable_in_daily_limit_flag": _bool_from_post(
                    request.POST,
                    "count_non_billable_in_daily_limit_flag",
                ),
                "archive_after_years": request.POST.get("archive_after_years", ""),
                "enable_timer_flag": _bool_from_post(request.POST, "enable_timer_flag"),
                "enable_leave_integration_flag": _bool_from_post(
                    request.POST,
                    "enable_leave_integration_flag",
                ),
                "enable_copy_previous_week_flag": _bool_from_post(
                    request.POST,
                    "enable_copy_previous_week_flag",
                ),
            }
        elif active_form == "delete":
            payload = {}
        else:
            return _render_access_denied(
                request,
                message="Unknown Office form submission.",
                status=400,
            )
        try:
            if active_form == "delete":
                OfficeManagementService.delete_office(current_user, office_id)
            else:
                OfficeManagementService.update_office(current_user, office_id, payload)
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(OFFICE_CONFIG.collection_path)
            return redirect(f"/system/offices/{office_id}/")

    try:
        office = OfficeManagementService.get_office(current_user, office_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=OFFICE_CONFIG.detail_title,
            eyebrow=OFFICE_CONFIG.detail_eyebrow,
            intro=OFFICE_CONFIG.detail_intro,
            error=error,
        )

    form_sections = [
        {
            "form_name": "general",
            "title": "General",
            "intro": "Update Office identity, parent Country, and lifecycle status.",
            "submit_label": "Save Office",
            "form_error": form_error if active_form == "general" else "",
            "fields": _office_form_fields(
                post_data=post_data if active_form == "general" else None,
                entity=office,
            ),
            "fields_grid_class": "office-form-grid",
            "section_class": "office-detail-section",
        },
        {
            "form_name": "configuration",
            "title": "Configuration",
            "intro": (
                "Update the inherited operational configuration shared by "
                "Business Units in this Office."
            ),
            "submit_label": "Save Configuration",
            "form_error": form_error if active_form == "configuration" else "",
            "fields": _office_configuration_fields(
                office,
                post_data=post_data if active_form == "configuration" else None,
            ),
            "fields_grid_class": "office-form-grid",
            "section_class": "office-detail-section",
        },
        {
            "form_name": "administrators",
            "title": "Office Administrators",
            "intro": (
                "Active Office administrators are shown here for reference. "
                "They cannot be edited from the Office screen."
            ),
            "read_only": True,
            "detail_rows": _office_administrator_rows(office),
            "empty_message": "No active Office administrators are assigned yet.",
            "fields": [],
            "section_class": "office-detail-section",
        },
        {
            "form_name": "delete",
            "title": "Delete Office",
            "intro": (
                "Delete this Office only if it has no Business Units or other "
                "dependent records. If it is still in use, deletion will be blocked."
            ),
            "submit_label": "Delete Office",
            "form_error": form_error if active_form == "delete" else "",
            "fields": [],
            "section_class": "office-detail-section",
        },
    ]

    return _render_detail_page(
        request,
        current_user,
        title=office["name"],
        eyebrow=OFFICE_CONFIG.detail_eyebrow,
        intro=OFFICE_CONFIG.detail_intro,
        detail_rows=_office_detail_rows(office),
        form_sections=form_sections,
        back_href=OFFICE_CONFIG.collection_path,
        back_label=f"Back to {OFFICE_CONFIG.plural_label}",
        entity_status=office["status"],
        show_detail_panel=False,
        detail_content_class="office-detail-layout",
        page_action={
            "label": f"Back to {OFFICE_CONFIG.plural_label}",
            "href": OFFICE_CONFIG.collection_path,
        },
    )


@require_http_methods(["GET", "POST"])
def employees_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="EMPLOYEE_STATUS",
        default_code="ACTIVE",
    )
    employees = EmployeeManagementService.list_employees(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_collection_page(
        request,
        current_user,
        title="Employee Management",
        eyebrow="SCR-110",
        intro=(
            "Manage employees, internal roles, and Business Unit scope within "
            "assigned admin boundaries."
        ),
        table_headers=("Employee Code", "Full Name", "Email", "Status", "Primary BU", "Roles"),
        table_rows=_employee_rows(employees),
        empty_message="No employees are available in your assigned Business Units yet.",
        form_title=None,
        filter_links=[],
        filter_title="Employee Status",
        show_filter_panel=False,
        inline_filter_links=filter_links,
        inline_filter_title="Employee Status",
        records_heading="",
        page_action={"label": "Create Employee", "href": "/system/employees/new/"},
    )


@require_http_methods(["GET", "POST"])
def employee_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            employee = EmployeeManagementService.create_employee(
                current_user,
                {
                    "employee_code": request.POST.get("employee_code", ""),
                    "full_name": request.POST.get("full_name", ""),
                    "email": request.POST.get("email", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                    "primary_business_unit_id": request.POST.get("primary_business_unit_id", ""),
                    "business_unit_ids": request.POST.getlist("business_unit_ids"),
                    "role_codes": request.POST.getlist("role_codes"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/employees/{employee['id']}/")

    detail_rows = [
        ("Office", current_user.office_name),
        (
            "Available Business Units",
            ", ".join(unit.bu_code for unit in current_user.scoped_business_units),
        ),
    ]
    form_sections = [
        {
            "form_name": "create",
            "title": "Employee Setup",
            "intro": (
                "Create a new internal employee record with its initial roles and Business Unit "
                "scope."
            ),
            "submit_label": "Create Employee",
            "form_error": form_error,
            "fields": _employee_create_fields(current_user, post_data=post_data),
        }
    ]
    return _render_detail_page(
        request,
        current_user,
        title="Create Employee",
        eyebrow="SCR-110",
        intro="Standalone employee creation screen for identity, role, and scope setup.",
        detail_rows=detail_rows,
        form_sections=form_sections,
        back_href="/system/employees/",
        back_label="Back to Employees",
        entity_status="New",
        show_detail_panel=False,
        page_action={"label": "Back to Employees", "href": "/system/employees/"},
    )


@require_http_methods(["GET", "POST"])
def employee_detail(request: HttpRequest, employee_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "core"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "core")
        try:
            if active_form == "core":
                EmployeeManagementService.update_employee(
                    current_user,
                    employee_id,
                    {
                        "full_name": request.POST.get("full_name", ""),
                        "email": request.POST.get("email", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            elif active_form == "roles":
                EmployeeManagementService.replace_roles(
                    current_user,
                    employee_id,
                    {"role_codes": request.POST.getlist("role_codes")},
                )
            elif active_form == "business_units":
                EmployeeManagementService.replace_business_units(
                    current_user,
                    employee_id,
                    {
                        "primary_business_unit_id": request.POST.get(
                            "primary_business_unit_id", ""
                        ),
                        "business_unit_ids": request.POST.getlist("business_unit_ids"),
                    },
                )
            elif active_form == "delete":
                EmployeeManagementService.delete_employee(current_user, employee_id)
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown employee form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect("/system/employees/")
            return redirect(f"/system/employees/{employee_id}/")

    try:
        employee = EmployeeManagementService.get_employee(current_user, employee_id)
        project_assignments = EmployeeManagementService.list_employee_project_assignments(
            current_user,
            employee_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title="Employee Detail",
            eyebrow="SCR-111",
            intro="Requested employee could not be loaded in the current admin scope.",
            error=error,
        )

    form_sections = [
        {
            "form_name": "core",
            "title": "Employee Core Data",
            "intro": "Update identity and lifecycle fields for the selected employee.",
            "submit_label": "Save Core Data",
            "form_error": form_error if active_form == "core" else "",
            "section_class": "employee-detail-section employee-detail-section-wide",
            "fields_grid_class": "employee-core-grid",
            "fields": _employee_core_fields(
                employee,
                post_data=post_data if active_form == "core" else None,
            ),
        },
        {
            "form_name": "roles",
            "title": "Role Assignments",
            "intro": "Replace the employee's active internal roles in one action.",
            "submit_label": "Save Roles",
            "form_error": form_error if active_form == "roles" else "",
            "section_class": "employee-detail-section",
            "fields": _employee_role_fields(
                employee,
                post_data=post_data if active_form == "roles" else None,
            ),
        },
        {
            "form_name": "business_units",
            "title": "Business Unit Scope",
            "intro": (
                "Replace the employee's active Business Unit assignments and primary Business Unit."
            ),
            "submit_label": "Save Business Units",
            "form_error": form_error if active_form == "business_units" else "",
            "section_class": "employee-detail-section",
            "fields": _employee_business_unit_fields(
                current_user,
                employee,
                post_data=post_data if active_form == "business_units" else None,
            ),
        },
        _read_only_table_section(
            title="Project Assignments",
            intro=(
                "Review the employee's active project assignments in your scoped "
                "administration area."
            ),
            table_headers=("Name", "BU", "From", "To"),
            table_rows=_employee_project_assignment_rows(project_assignments),
            empty_message="This employee has no active project assignments in your current scope.",
        ),
        {
            **_delete_action_section(
                title="Delete Employee",
                intro=(
                    "Delete this employee only if no protected references still depend on it. "
                    "If the employee is still in use, deletion will be blocked."
                ),
                submit_label="Delete Employee",
                form_error=form_error if active_form == "delete" else "",
            ),
        },
    ]
    return _render_detail_page(
        request,
        current_user,
        title=employee["full_name"],
        eyebrow="SCR-111",
        intro=(
            "Employee administration screen backed directly by the Phase II "
            "scoped management services."
        ),
        detail_rows=_employee_detail_rows(employee),
        form_sections=form_sections,
        back_href="/system/employees/",
        back_label="Back to Employee List",
        entity_status=employee["status"],
        show_detail_panel=False,
        detail_content_class="employee-detail-layout",
        page_action={"label": "Back to Employees", "href": "/system/employees/"},
    )


@require_http_methods(["GET", "POST"])
def employee_transfer_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin_master(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    selected_source_id = ""
    source_employee = None
    transfer_result = None
    form_error = ""
    active_form = "select_source"
    post_data = request.POST if request.method == "POST" else None
    filter_office_id = request.POST.get("filter_office_id", "").strip() if post_data else ""
    filter_primary_business_unit_id = (
        request.POST.get("filter_primary_business_unit_id", "").strip() if post_data else ""
    )
    filter_full_name = request.POST.get("filter_full_name", "").strip() if post_data else ""

    try:
        source_candidates = EmployeeManagementService.list_transfer_candidates_filtered(
            current_user,
            office_id=filter_office_id,
            primary_business_unit_id=filter_primary_business_unit_id,
            full_name_query=filter_full_name,
        )
    except AuthError as error:
        source_candidates = EmployeeManagementService.list_transfer_candidates(current_user)
        form_error = error.message

    if request.method == "POST":
        active_form = request.POST.get("form_action") or request.POST.get(
            "form_name", "select_source"
        )
        selected_source_id = request.POST.get("source_employee_id", "").strip()
        if active_form == "transfer":
            try:
                transfer_result = EmployeeManagementService.transfer_employee_to_office(
                    current_user,
                    int(selected_source_id),
                    {
                        "new_employee_code": request.POST.get("new_employee_code", ""),
                        "target_office_id": request.POST.get("target_office_id", ""),
                        "target_primary_business_unit_id": request.POST.get(
                            "target_primary_business_unit_id", ""
                        ),
                        "target_business_unit_ids": request.POST.getlist(
                            "target_business_unit_ids"
                        ),
                        "target_role_codes": request.POST.getlist("target_role_codes"),
                    },
                )
            except (AuthError, ValueError) as error:
                form_error = error.message if isinstance(error, AuthError) else (
                    "Select a valid source employee before starting the transfer."
                )
            else:
                selected_source_id = str(transfer_result["source_employee"]["id"])

    if selected_source_id and transfer_result is None:
        try:
            source_employee = EmployeeManagementService.get_transfer_candidate(
                current_user,
                int(selected_source_id),
            )
        except (AuthError, ValueError) as error:
            form_error = error.message if isinstance(error, AuthError) else (
                "Select a valid source employee to continue."
            )
            selected_source_id = ""

    form_sections = [
        {
            "form_name": "select_source",
            "title": "Source Employee",
            "intro": (
                "Load an active employee record before configuring the Office transfer workflow."
            ),
            "submit_label": "Load Transfer Setup",
            "extra_actions": [
                {
                    "form_name": "apply_filters",
                    "label": "Apply Filters",
                    "button_class": "button secondary",
                }
            ],
            "form_error": form_error if active_form in {"select_source", "apply_filters"} else "",
            "fields_grid_class": "three-column",
            "fields": _employee_transfer_source_fields(
                source_candidates,
                office_filter_id=filter_office_id,
                primary_business_unit_filter_id=filter_primary_business_unit_id,
                full_name_filter=filter_full_name,
                selected_source_id=selected_source_id,
            ),
        }
    ]

    if transfer_result is not None:
        form_sections.extend(
            [
                _read_only_detail_section(
                    title="Source Employee Archived",
                    intro=(
                        "The original employee record is preserved in the source Office as a "
                        "historical inactive record."
                    ),
                    detail_rows=_employee_transfer_result_rows(
                        "Archived Source",
                        transfer_result["source_employee"],
                    ),
                ),
                _read_only_detail_section(
                    title="Target Employee Created",
                    intro=(
                        "The new target-Office employee record now owns the live login email "
                        "and operational scope."
                    ),
                    detail_rows=_employee_transfer_result_rows(
                        "New Target",
                        transfer_result["target_employee"],
                    ),
                ),
            ]
        )
    elif source_employee is not None:
        form_sections.append(
            _read_only_detail_section(
                title="Source Employee Summary",
                intro="Review the source identity, scope, and roles before transferring it.",
                detail_rows=_employee_transfer_source_rows(source_employee),
            )
        )
        form_sections.append(
            {
                **_read_only_detail_section(
                    title="Transfer Readiness",
                    intro=(
                        "The source employee must be free of active operational dependencies "
                        "before the archive-and-recreate transfer can proceed."
                    ),
                    detail_rows=_employee_transfer_readiness_rows(source_employee),
                ),
                "form_error": form_error if active_form == "transfer" else "",
            }
        )
        if source_employee["can_transfer"]:
            form_sections.append(
                {
                    "form_name": "transfer",
                    "title": "Target Setup",
                    "intro": (
                        "Archive the source record and create a new active employee in the "
                        "target Office."
                    ),
                    "submit_label": "Transfer Employee",
                    "form_error": form_error if active_form == "transfer" else "",
                    "fields": _employee_transfer_fields(
                        source_employee,
                        post_data=post_data if active_form == "transfer" else None,
                    ),
                }
            )

    return _render_detail_page(
        request,
        current_user,
        title="Employee Transfer",
        eyebrow="SCR-112",
        intro=(
            "Cross-Office employee transfer screen for safely archiving the source record and "
            "creating a new target-Office employee."
        ),
        detail_rows=[],
        form_sections=form_sections,
        back_href="/system/",
        back_label="Back to System Management",
        entity_status="Ready",
        show_detail_panel=False,
        page_action={"label": "Back to System Management", "href": "/system/"},
    )


def _render_master_collection(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    config: MasterUiConfig,
    entities: list[dict],
    form_fields: list[dict],
    table_rows: list[dict],
    form_error: str,
    filter_links: list[dict],
    filter_form_fields: list[dict] | None = None,
    filter_form_submit_label: str = "Apply Filters",
    filter_form_reset_pairs: list[dict] | None = None,
    inline_filter_form_fields: list[dict] | None = None,
    inline_filter_hidden_fields: list[dict] | None = None,
    inline_filter_form_submit_label: str = "Apply Filters",
) -> HttpResponse:
    return _render_list_only_collection(
        request,
        current_user,
        title=config.list_title,
        eyebrow=config.list_eyebrow,
        intro=config.list_intro,
        table_headers=config.table_headers,
        table_rows=table_rows,
        empty_message=config.empty_message,
        create_label=f"Create {config.singular_label}",
        create_href=_master_create_path(config),
        filter_links=filter_links,
        filter_title=f"{config.singular_label} Status",
        filter_form_fields=filter_form_fields,
        filter_form_submit_label=filter_form_submit_label,
        filter_form_reset_pairs=filter_form_reset_pairs,
        inline_filter_form_fields=inline_filter_form_fields,
        inline_filter_hidden_fields=inline_filter_hidden_fields,
        inline_filter_form_submit_label=inline_filter_form_submit_label,
    )


def _render_master_detail(
    request: HttpRequest,
    current_user: CurrentUser,
    *,
    config: MasterUiConfig,
    entity: dict,
    detail_rows: list[tuple[str, str]],
    form_fields: list[dict],
    form_error: str,
    active_form: str = "edit",
    extra_form_sections: list[dict] | None = None,
) -> HttpResponse:
    form_sections = [
        {
            "form_name": "edit",
            "title": f"Edit {config.singular_label}",
            "intro": (
                f"Update the selected {config.singular_label.lower()} "
                "without leaving the shared shell."
            ),
            "submit_label": f"Save {config.singular_label}",
            "form_error": form_error if active_form == "edit" else "",
            "fields": form_fields,
        }
    ]
    if extra_form_sections:
        form_sections.extend(extra_form_sections)
    return _render_detail_page(
        request,
        current_user,
        title=entity["name"],
        eyebrow=config.detail_eyebrow,
        intro=config.detail_intro,
        detail_rows=detail_rows,
        form_sections=form_sections,
        back_href=config.collection_path,
        back_label=f"Back to {config.plural_label}",
        entity_status=entity["status"],
        show_detail_panel=False,
        page_action={"label": f"Back to {config.plural_label}", "href": config.collection_path},
    )


@require_http_methods(["GET", "POST"])
def clients_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if request.method == "POST":
        try:
            client = ClientManagementService.create_client(
                current_user,
                {
                    "client_code": request.POST.get("client_code", ""),
                    "name": request.POST.get("name", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                    "parent_client_id": request.POST.get("parent_client_id", ""),
                },
            )
        except AuthError:
            pass
        else:
            return redirect(f"/system/clients/{client['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="CLIENT_STATUS",
        default_code="ACTIVE",
    )
    clients = ClientManagementService.list_clients(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_list_only_collection(
        request,
        current_user,
        title=CLIENT_CONFIG.list_title,
        eyebrow=CLIENT_CONFIG.list_eyebrow,
        intro=CLIENT_CONFIG.list_intro,
        table_headers=CLIENT_CONFIG.table_headers,
        table_rows=_client_rows(clients),
        empty_message=CLIENT_CONFIG.empty_message,
        create_label="Create Client",
        create_href="/system/clients/new/",
        filter_links=filter_links,
        filter_title="Client Status",
    )


@require_http_methods(["GET"])
def client_projects_redirect(
    request: HttpRequest,
    client_id: int,
    business_unit_id: int,
) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    try:
        client = ClientManagementService.get_client(current_user, client_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=CLIENT_CONFIG.list_title,
            eyebrow=CLIENT_CONFIG.list_eyebrow,
            intro=CLIENT_CONFIG.list_intro,
            error=error,
        )

    if business_unit_id not in current_user.scoped_business_unit_ids:
        return _render_auth_error(
            request,
            current_user,
            title=PROJECT_CONFIG.list_title,
            eyebrow=PROJECT_CONFIG.list_eyebrow,
            intro=PROJECT_CONFIG.list_intro,
            error=AuthError(
                "AUTH_ACCESS_DENIED",
                "You are not assigned to the Business Unit for the selected client row.",
                403,
            ),
        )

    return redirect(
        "/system/projects/"
        f"?status=ALL&client_id={client['id']}&business_unit_id={business_unit_id}"
    )


@require_http_methods(["GET", "POST"])
def client_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            client = ClientManagementService.create_client(
                current_user,
                {
                    "client_code": request.POST.get("client_code", ""),
                    "name": request.POST.get("name", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                    "parent_client_id": request.POST.get("parent_client_id", ""),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/clients/{client['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=CLIENT_CONFIG,
        form_fields=_client_form_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Client in your active Office.",
    )


@require_http_methods(["GET", "POST"])
def client_detail(request: HttpRequest, client_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                ClientManagementService.delete_client(current_user, client_id)
            elif active_form == "edit":
                ClientManagementService.update_client(
                    current_user,
                    client_id,
                    {
                        "client_code": request.POST.get("client_code", ""),
                        "name": request.POST.get("name", ""),
                        "status_code": request.POST.get("status_code", ""),
                        "parent_client_id": request.POST.get("parent_client_id", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown client form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect("/system/clients/")
            return redirect(f"/system/clients/{client_id}/")

    try:
        client = ClientManagementService.get_client(current_user, client_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=CLIENT_CONFIG.detail_title,
            eyebrow=CLIENT_CONFIG.detail_eyebrow,
            intro=CLIENT_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=CLIENT_CONFIG,
        entity=client,
        detail_rows=_client_detail_rows(client),
        form_fields=_client_form_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=client,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Client",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def internal_categories_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            category = InternalCategoryManagementService.create_category(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "category_code": request.POST.get("category_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/internal-categories/{category['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="INTERNAL_CATEGORY_STATUS",
        default_code="ACTIVE",
    )
    categories = InternalCategoryManagementService.list_categories(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=INTERNAL_CATEGORY_CONFIG,
        entities=categories,
        form_fields=_simple_master_fields(
            current_user,
            post_data=post_data,
            entity=None,
            business_unit_label="Business Unit",
            code_name="category_code",
            code_label="Category Code",
            name_label="Category Name",
            description_label="Description",
            status_domain="INTERNAL_CATEGORY_STATUS",
        ),
        table_rows=_internal_category_rows(categories),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def internal_category_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            category = InternalCategoryManagementService.create_category(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "category_code": request.POST.get("category_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/internal-categories/{category['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=INTERNAL_CATEGORY_CONFIG,
        form_fields=_simple_master_fields(
            current_user,
            post_data=post_data,
            entity=None,
            business_unit_label="Business Unit",
            code_name="category_code",
            code_label="Category Code",
            name_label="Category Name",
            description_label="Description",
            status_domain="INTERNAL_CATEGORY_STATUS",
        ),
        form_error=form_error,
        form_intro="Create a new internal category in your assigned Business Unit scope.",
    )


@require_http_methods(["GET", "POST"])
def internal_category_detail(request: HttpRequest, category_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                InternalCategoryManagementService.delete_category(current_user, category_id)
            elif active_form == "edit":
                InternalCategoryManagementService.update_category(
                    current_user,
                    category_id,
                    {
                        "category_code": request.POST.get("category_code", ""),
                        "name": request.POST.get("name", ""),
                        "description": request.POST.get("description", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown internal category form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect("/system/internal-categories/")
            return redirect(f"/system/internal-categories/{category_id}/")

    try:
        category = InternalCategoryManagementService.get_category(current_user, category_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=INTERNAL_CATEGORY_CONFIG.detail_title,
            eyebrow=INTERNAL_CATEGORY_CONFIG.detail_eyebrow,
            intro=INTERNAL_CATEGORY_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=INTERNAL_CATEGORY_CONFIG,
        entity=category,
        detail_rows=_internal_category_detail_rows(category),
        form_fields=_simple_master_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=category,
            business_unit_label="Business Unit",
            code_name="category_code",
            code_label="Category Code",
            name_label="Category Name",
            description_label="Description",
            status_domain="INTERNAL_CATEGORY_STATUS",
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Internal Category",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def cost_centers_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if request.method == "POST":
        try:
            cost_center = CostCenterManagementService.create_cost_center(
                current_user,
                {
                    "cost_center_code": request.POST.get("cost_center_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError:
            pass
        else:
            return redirect(f"/system/cost-centers/{cost_center['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="COST_CENTER_STATUS",
        default_code="ACTIVE",
    )
    cost_centers = CostCenterManagementService.list_cost_centers(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_list_only_collection(
        request,
        current_user,
        title=COST_CENTER_CONFIG.list_title,
        eyebrow=COST_CENTER_CONFIG.list_eyebrow,
        intro=COST_CENTER_CONFIG.list_intro,
        table_headers=COST_CENTER_CONFIG.table_headers,
        table_rows=_cost_center_rows(cost_centers),
        empty_message=COST_CENTER_CONFIG.empty_message,
        create_label="Create Cost Center",
        create_href="/system/cost-centers/new/",
        filter_links=filter_links,
        filter_title="Cost Center Status",
    )


@require_http_methods(["GET", "POST"])
def cost_center_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            cost_center = CostCenterManagementService.create_cost_center(
                current_user,
                {
                    "cost_center_code": request.POST.get("cost_center_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/cost-centers/{cost_center['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=COST_CENTER_CONFIG,
        form_fields=_cost_center_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Cost Center in your active Office.",
    )


@require_http_methods(["GET", "POST"])
def cost_center_detail(request: HttpRequest, cost_center_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                CostCenterManagementService.delete_cost_center(current_user, cost_center_id)
            elif active_form == "edit":
                CostCenterManagementService.update_cost_center(
                    current_user,
                    cost_center_id,
                    {
                        "cost_center_code": request.POST.get("cost_center_code", ""),
                        "name": request.POST.get("name", ""),
                        "description": request.POST.get("description", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown cost center form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect("/system/cost-centers/")
            return redirect(f"/system/cost-centers/{cost_center_id}/")

    try:
        cost_center = CostCenterManagementService.get_cost_center(current_user, cost_center_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=COST_CENTER_CONFIG.detail_title,
            eyebrow=COST_CENTER_CONFIG.detail_eyebrow,
            intro=COST_CENTER_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=COST_CENTER_CONFIG,
        entity=cost_center,
        detail_rows=_cost_center_detail_rows(cost_center),
        form_fields=_cost_center_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=cost_center,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Cost Center",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def pricing_models_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    if request.method == "POST":
        try:
            pricing_model = PricingModelManagementService.create_pricing_model(
                current_user,
                {
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                },
            )
        except AuthError:
            pass
        else:
            return redirect(f"/system/pricing-models/{pricing_model['id']}/")

    pricing_models = PricingModelManagementService.list_pricing_models(current_user)
    return _render_list_only_collection(
        request,
        current_user,
        title=PRICING_MODEL_CONFIG.list_title,
        eyebrow=PRICING_MODEL_CONFIG.list_eyebrow,
        intro=PRICING_MODEL_CONFIG.list_intro,
        table_headers=PRICING_MODEL_CONFIG.table_headers,
        table_rows=_pricing_model_rows(pricing_models),
        empty_message=PRICING_MODEL_CONFIG.empty_message,
        create_label="Create Pricing Model",
        create_href="/system/pricing-models/new/",
        filter_links=[],
    )


@require_http_methods(["GET", "POST"])
def pricing_model_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            pricing_model = PricingModelManagementService.create_pricing_model(
                current_user,
                {
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/pricing-models/{pricing_model['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=PRICING_MODEL_CONFIG,
        form_fields=_pricing_model_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new pricing model in your active Office.",
    )


@require_http_methods(["GET", "POST"])
def pricing_model_detail(request: HttpRequest, pricing_model_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                PricingModelManagementService.delete_pricing_model(current_user, pricing_model_id)
            elif active_form == "edit":
                PricingModelManagementService.update_pricing_model(
                    current_user,
                    pricing_model_id,
                    {
                        "name": request.POST.get("name", ""),
                        "description": request.POST.get("description", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown pricing model form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(PRICING_MODEL_CONFIG.collection_path)
            return redirect(f"/system/pricing-models/{pricing_model_id}/")

    try:
        pricing_model = PricingModelManagementService.get_pricing_model(
            current_user,
            pricing_model_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=PRICING_MODEL_CONFIG.detail_title,
            eyebrow=PRICING_MODEL_CONFIG.detail_eyebrow,
            intro=PRICING_MODEL_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=PRICING_MODEL_CONFIG,
        entity={"name": pricing_model["name"], "status": "Managed", **pricing_model},
        detail_rows=_pricing_model_detail_rows(pricing_model),
        form_fields=_pricing_model_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=pricing_model,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Pricing Model",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def general_charge_code_approval_roles_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            approval_role = (
                GeneralChargeCodeApprovalRoleManagementService.create_approval_role(
                    current_user,
                    {
                        "role_code": request.POST.get("role_code", ""),
                        "name": request.POST.get("name", ""),
                        "description": request.POST.get("description", ""),
                        "member_employee_ids": request.POST.getlist("member_employee_ids"),
                        "status_code": request.POST.get("status_code", "ACTIVE"),
                    },
                )
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/general-charge-code-approval-roles/{approval_role['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
        default_code="ACTIVE",
    )
    approval_roles = GeneralChargeCodeApprovalRoleManagementService.list_approval_roles(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG,
        entities=approval_roles,
        form_fields=_general_charge_code_approval_role_fields(current_user, post_data=post_data),
        table_rows=_general_charge_code_approval_role_rows(approval_roles),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def general_charge_code_approval_role_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            approval_role = GeneralChargeCodeApprovalRoleManagementService.create_approval_role(
                current_user,
                {
                    "role_code": request.POST.get("role_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "member_employee_ids": request.POST.getlist("member_employee_ids"),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/general-charge-code-approval-roles/{approval_role['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG,
        form_fields=_general_charge_code_approval_role_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new ad-hoc General Charge Code approval role in your active Office.",
    )


@require_http_methods(["GET", "POST"])
def general_charge_code_approval_role_detail(
    request: HttpRequest,
    approval_role_id: int,
) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                GeneralChargeCodeApprovalRoleManagementService.delete_approval_role(
                    current_user,
                    approval_role_id,
                )
            elif active_form == "edit":
                GeneralChargeCodeApprovalRoleManagementService.update_approval_role(
                    current_user,
                    approval_role_id,
                    {
                        "role_code": request.POST.get("role_code", ""),
                        "name": request.POST.get("name", ""),
                        "description": request.POST.get("description", ""),
                        "member_employee_ids": request.POST.getlist("member_employee_ids"),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown General Charge Code approval role form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG.collection_path)
            return redirect(f"/system/general-charge-code-approval-roles/{approval_role_id}/")

    try:
        approval_role = GeneralChargeCodeApprovalRoleManagementService.get_approval_role(
            current_user,
            approval_role_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG.detail_title,
            eyebrow=GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG.detail_eyebrow,
            intro=GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=GENERAL_CHARGE_CODE_APPROVAL_ROLE_CONFIG,
        entity={"name": approval_role["name"], **approval_role},
        detail_rows=_general_charge_code_approval_role_detail_rows(approval_role),
        form_fields=_general_charge_code_approval_role_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=approval_role,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _read_only_detail_section(
                title="Routing Coverage",
                intro=(
                    "Review active members, referenced General Charge Codes, and "
                    "coverage warnings before changing this role."
                ),
                detail_rows=_general_charge_code_approval_role_coverage_detail_rows(
                    approval_role
                ),
            ),
            _delete_action_section(
                submit_label="Delete General Charge Code Approval Role",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def general_charge_codes_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            general_charge_code = GeneralChargeCodeManagementService.create_general_charge_code(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "code": request.POST.get("code", ""),
                    "name": request.POST.get("name", ""),
                    "charge_type_code": request.POST.get("charge_type_code", "STANDARD"),
                    "cost_center_id": request.POST.get("cost_center_id", ""),
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "requires_approval_flag": _bool_from_post(
                        request.POST, "requires_approval_flag"
                    ),
                    "approver_keys": request.POST.getlist("approver_keys"),
                    "description_required_flag": _bool_from_post(
                        request.POST, "description_required_flag"
                    ),
                    "valid_from": request.POST.get("valid_from", ""),
                    "valid_to": request.POST.get("valid_to", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/general-charge-codes/{general_charge_code['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="GENERAL_CHARGE_CODE_STATUS",
        default_code="ACTIVE",
    )
    general_charge_codes = GeneralChargeCodeManagementService.list_general_charge_codes(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=GENERAL_CHARGE_CODE_CONFIG,
        entities=general_charge_codes,
        form_fields=_general_charge_code_fields(current_user, post_data=post_data),
        table_rows=_general_charge_code_rows(general_charge_codes),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def general_charge_code_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            general_charge_code = GeneralChargeCodeManagementService.create_general_charge_code(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "code": request.POST.get("code", ""),
                    "name": request.POST.get("name", ""),
                    "charge_type_code": request.POST.get("charge_type_code", "STANDARD"),
                    "cost_center_id": request.POST.get("cost_center_id", ""),
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "requires_approval_flag": _bool_from_post(
                        request.POST, "requires_approval_flag"
                    ),
                    "approver_keys": request.POST.getlist("approver_keys"),
                    "description_required_flag": _bool_from_post(
                        request.POST, "description_required_flag"
                    ),
                    "valid_from": request.POST.get("valid_from", ""),
                    "valid_to": request.POST.get("valid_to", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/general-charge-codes/{general_charge_code['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=GENERAL_CHARGE_CODE_CONFIG,
        form_fields=_general_charge_code_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new General Charge Code in your assigned Business Unit scope.",
    )


@require_http_methods(["GET", "POST"])
def general_charge_code_detail(
    request: HttpRequest,
    general_charge_code_id: int,
) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                GeneralChargeCodeManagementService.delete_general_charge_code(
                    current_user,
                    general_charge_code_id,
                )
            elif active_form == "edit":
                GeneralChargeCodeManagementService.update_general_charge_code(
                    current_user,
                    general_charge_code_id,
                    {
                        "code": request.POST.get("code", ""),
                        "name": request.POST.get("name", ""),
                        "charge_type_code": request.POST.get("charge_type_code", ""),
                        "cost_center_id": request.POST.get("cost_center_id", ""),
                        "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                        "requires_approval_flag": _bool_from_post(
                            request.POST, "requires_approval_flag"
                        ),
                        "approver_keys": request.POST.getlist("approver_keys"),
                        "description_required_flag": _bool_from_post(
                            request.POST, "description_required_flag"
                        ),
                        "valid_from": request.POST.get("valid_from", ""),
                        "valid_to": request.POST.get("valid_to", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown general charge code form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(GENERAL_CHARGE_CODE_CONFIG.collection_path)
            return redirect(f"/system/general-charge-codes/{general_charge_code_id}/")

    try:
        general_charge_code = GeneralChargeCodeManagementService.get_general_charge_code(
            current_user,
            general_charge_code_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=GENERAL_CHARGE_CODE_CONFIG.detail_title,
            eyebrow=GENERAL_CHARGE_CODE_CONFIG.detail_eyebrow,
            intro=GENERAL_CHARGE_CODE_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=GENERAL_CHARGE_CODE_CONFIG,
        entity=general_charge_code,
        detail_rows=_general_charge_code_detail_rows(general_charge_code),
        form_fields=_general_charge_code_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=general_charge_code,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _read_only_detail_section(
                title="Routing Overview",
                intro=(
                    "Review the effective approval routing health before updating "
                    "this General Charge Code."
                ),
                detail_rows=_general_charge_code_routing_detail_rows(
                    general_charge_code
                ),
            ),
            _delete_action_section(
                submit_label="Delete General Charge Code",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def projects_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_project_system_manager(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            project = ProjectManagementService.create_project(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "project_code": request.POST.get("project_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "project_owner_employee_id": request.POST.get(
                        "project_owner_employee_id",
                        "",
                    ),
                    "project_manager_employee_id": request.POST.get(
                        "project_manager_employee_id",
                        "",
                    ),
                    "client_id": request.POST.get("client_id", ""),
                    "internal_category_id": request.POST.get("internal_category_id", ""),
                    "cost_center_id": request.POST.get("cost_center_id", ""),
                    "pricing_model_id": request.POST.get("pricing_model_id", ""),
                    "start_date": request.POST.get("start_date", ""),
                    "end_date": request.POST.get("end_date", ""),
                    "close_date": request.POST.get("close_date", ""),
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "status_code": request.POST.get("status_code", "DRAFT"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/projects/{project['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="PROJECT_STATUS",
        default_code="ACTIVE",
    )
    selected_client_id = request.GET.get("client_id", "").strip()
    selected_business_unit_id = request.GET.get("business_unit_id", "").strip()
    valid_business_unit_values = {
        str(option["value"])
        for option in _scoped_business_unit_options(current_user)
        if option["value"] != ""
    }
    if selected_business_unit_id and selected_business_unit_id not in valid_business_unit_values:
        selected_business_unit_id = ""
    client_options = _scoped_client_options(
        current_user,
        selected=selected_client_id,
        include_blank=True,
        active_only=True,
    )
    valid_client_values = {
        str(option["value"]) for option in client_options if option["value"] != ""
    }
    if selected_client_id and selected_client_id not in valid_client_values:
        selected_client_id = ""

    projects = ProjectManagementService.list_projects(
        current_user,
        status_code=_service_status_code(selected_status_code),
        client_id=int(selected_client_id) if selected_client_id.isdigit() else None,
        business_unit_id=(
            int(selected_business_unit_id)
            if selected_business_unit_id.isdigit()
            else None
        ),
    )
    return _render_master_collection(
        request,
        current_user,
        config=PROJECT_CONFIG,
        entities=projects,
        form_fields=_project_form_fields(current_user, post_data=post_data),
        table_rows=_project_rows(projects),
        form_error=form_error,
        filter_links=filter_links,
        inline_filter_form_fields=_project_collection_filter_fields(
            current_user,
            selected_client_id=selected_client_id,
        ),
        inline_filter_hidden_fields=_project_collection_hidden_filters(
            selected_status_code=selected_status_code,
            selected_business_unit_id=selected_business_unit_id,
        ),
        inline_filter_form_submit_label="Apply",
    )


@require_http_methods(["GET", "POST"])
def project_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_project_system_manager(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            project = ProjectManagementService.create_project(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "project_code": request.POST.get("project_code", ""),
                    "name": request.POST.get("name", ""),
                    "description": request.POST.get("description", ""),
                    "project_owner_employee_id": request.POST.get(
                        "project_owner_employee_id",
                        "",
                    ),
                    "project_manager_employee_id": request.POST.get(
                        "project_manager_employee_id",
                        "",
                    ),
                    "client_id": request.POST.get("client_id", ""),
                    "internal_category_id": request.POST.get("internal_category_id", ""),
                    "cost_center_id": request.POST.get("cost_center_id", ""),
                    "pricing_model_id": request.POST.get("pricing_model_id", ""),
                    "start_date": request.POST.get("start_date", ""),
                    "end_date": request.POST.get("end_date", ""),
                    "close_date": request.POST.get("close_date", ""),
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "status_code": request.POST.get("status_code", "DRAFT"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/projects/{project['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=PROJECT_CONFIG,
        form_fields=_project_form_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Project in your assigned Business Unit scope.",
    )


@require_http_methods(["GET", "POST"])
def project_detail(request: HttpRequest, project_id: int) -> HttpResponse:
    current_user = _require_project_system_manager(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                ProjectManagementService.delete_project(current_user, project_id)
            elif active_form == "edit":
                ProjectManagementService.update_project(
                    current_user,
                    project_id,
                    {
                        "project_code": request.POST.get("project_code", ""),
                        "name": request.POST.get("name", ""),
                        "description": request.POST.get("description", ""),
                        "project_owner_employee_id": request.POST.get(
                            "project_owner_employee_id",
                            "",
                        ),
                        "project_manager_employee_id": request.POST.get(
                            "project_manager_employee_id",
                            "",
                        ),
                        "client_id": request.POST.get("client_id", ""),
                        "internal_category_id": request.POST.get("internal_category_id", ""),
                        "cost_center_id": request.POST.get("cost_center_id", ""),
                        "pricing_model_id": request.POST.get("pricing_model_id", ""),
                        "start_date": request.POST.get("start_date", ""),
                        "end_date": request.POST.get("end_date", ""),
                        "close_date": request.POST.get("close_date", ""),
                        "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown project form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(PROJECT_CONFIG.collection_path)
            return redirect(f"/system/projects/{project_id}/")

    try:
        project = ProjectManagementService.get_project(current_user, project_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=PROJECT_CONFIG.detail_title,
            eyebrow=PROJECT_CONFIG.detail_eyebrow,
            intro=PROJECT_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=PROJECT_CONFIG,
        entity=project,
        detail_rows=_project_detail_rows(project),
        form_fields=_project_form_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=project,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Project",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def project_assignments_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_project_assignment_system_manager(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            assignment = ProjectAssignmentManagementService.create_assignment(
                current_user,
                {
                    "project_id": request.POST.get("project_id", ""),
                    "employee_id": request.POST.get("employee_id", ""),
                    "assignment_start_date": request.POST.get("assignment_start_date", ""),
                    "assignment_end_date": request.POST.get("assignment_end_date", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/project-assignments/{assignment['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="PROJECT_ASSIGNMENT_STATUS",
        default_code="ACTIVE",
    )
    selected_client_id = request.GET.get("client_id", "").strip()
    client_options = _scoped_client_options(
        current_user,
        selected=selected_client_id,
        include_blank=True,
        active_only=True,
    )
    valid_client_values = {
        str(option["value"]) for option in client_options if option["value"] != ""
    }
    if selected_client_id and selected_client_id not in valid_client_values:
        selected_client_id = ""

    normalized_client_id = int(selected_client_id) if selected_client_id.isdigit() else None
    selected_project_id = request.GET.get("project_id", "").strip()
    project_options = _scoped_project_options(
        current_user,
        selected=selected_project_id,
        include_blank=True,
        client_id=normalized_client_id,
        active_only=True,
    )
    valid_project_values = {
        str(option["value"]) for option in project_options if option["value"] != ""
    }
    if selected_project_id and selected_project_id not in valid_project_values:
        selected_project_id = ""

    assignments = ProjectAssignmentManagementService.list_assignments(
        current_user,
        status_code=_service_status_code(selected_status_code),
        client_id=selected_client_id or None,
        project_id=selected_project_id or None,
    )
    return _render_master_collection(
        request,
        current_user,
        config=PROJECT_ASSIGNMENT_CONFIG,
        entities=assignments,
        form_fields=_project_assignment_fields(current_user, post_data=post_data),
        table_rows=_project_assignment_rows(assignments),
        form_error=form_error,
        filter_links=filter_links,
        filter_form_fields=_project_assignment_filter_fields(
            current_user,
            selected_status_code=selected_status_code,
            selected_client_id=selected_client_id,
            selected_project_id=selected_project_id,
        ),
        filter_form_reset_pairs=[
            {
                "source_id": "client_id",
                "target_id": "project_id",
            }
        ],
    )


@require_http_methods(["GET", "POST"])
def project_assignment_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_project_assignment_system_manager(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            assignment = ProjectAssignmentManagementService.create_assignment(
                current_user,
                {
                    "project_id": request.POST.get("project_id", ""),
                    "employee_id": request.POST.get("employee_id", ""),
                    "assignment_start_date": request.POST.get("assignment_start_date", ""),
                    "assignment_end_date": request.POST.get("assignment_end_date", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/project-assignments/{assignment['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=PROJECT_ASSIGNMENT_CONFIG,
        form_fields=_project_assignment_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Project Assignment in your assigned Business Unit scope.",
    )


@require_http_methods(["GET", "POST"])
def project_assignment_detail(request: HttpRequest, assignment_id: int) -> HttpResponse:
    current_user = _require_project_assignment_system_manager(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                ProjectAssignmentManagementService.delete_assignment(
                    current_user,
                    assignment_id,
                )
            elif active_form == "edit":
                ProjectAssignmentManagementService.update_assignment(
                    current_user,
                    assignment_id,
                    {
                        "assignment_start_date": request.POST.get("assignment_start_date", ""),
                        "assignment_end_date": request.POST.get("assignment_end_date", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown project assignment form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(PROJECT_ASSIGNMENT_CONFIG.collection_path)
            return redirect(f"/system/project-assignments/{assignment_id}/")

    try:
        assignment = ProjectAssignmentManagementService.get_assignment(current_user, assignment_id)
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=PROJECT_ASSIGNMENT_CONFIG.detail_title,
            eyebrow=PROJECT_ASSIGNMENT_CONFIG.detail_eyebrow,
            intro=PROJECT_ASSIGNMENT_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=PROJECT_ASSIGNMENT_CONFIG,
        entity=assignment,
        detail_rows=_project_assignment_detail_rows(assignment),
        form_fields=_project_assignment_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=assignment,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Project Assignment",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )


@require_http_methods(["GET", "POST"])
def yearly_calendars_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            yearly_calendar = YearlyCalendarManagementService.create_yearly_calendar(
                current_user,
                {
                    "calendar_year": request.POST.get("calendar_year", ""),
                    "calendar_name": request.POST.get("calendar_name", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/calendars/{yearly_calendar['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="CALENDAR_STATUS",
        default_code="ACTIVE",
    )
    yearly_calendars = YearlyCalendarManagementService.list_yearly_calendars(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=YEARLY_CALENDAR_CONFIG,
        entities=yearly_calendars,
        form_fields=_yearly_calendar_fields(current_user, post_data=post_data),
        table_rows=_yearly_calendar_rows(yearly_calendars),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def yearly_calendar_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            yearly_calendar = YearlyCalendarManagementService.create_yearly_calendar(
                current_user,
                {
                    "calendar_year": request.POST.get("calendar_year", ""),
                    "calendar_name": request.POST.get("calendar_name", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/calendars/{yearly_calendar['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=YEARLY_CALENDAR_CONFIG,
        form_fields=_yearly_calendar_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Yearly Calendar in your active Office.",
        setup_title="Calendar Setup",
        submit_label="Create Calendar",
    )


@require_http_methods(["GET", "POST"])
def yearly_calendar_detail(request: HttpRequest, yearly_calendar_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "general"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "general")
        try:
            if active_form == "general":
                YearlyCalendarManagementService.update_yearly_calendar(
                    current_user,
                    yearly_calendar_id,
                    {
                        "calendar_year": request.POST.get("calendar_year", ""),
                        "calendar_name": request.POST.get("calendar_name", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
            elif active_form == "delete":
                YearlyCalendarManagementService.delete_yearly_calendar(
                    current_user,
                    yearly_calendar_id,
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown calendar form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(YEARLY_CALENDAR_CONFIG.collection_path)
            return redirect(f"/system/calendars/{yearly_calendar_id}/")

    try:
        yearly_calendar = YearlyCalendarManagementService.get_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=YEARLY_CALENDAR_CONFIG.detail_title,
            eyebrow=YEARLY_CALENDAR_CONFIG.detail_eyebrow,
            intro=YEARLY_CALENDAR_CONFIG.detail_intro,
            error=error,
        )

    default_month = (
        date.today().month if yearly_calendar["calendar_year"] == date.today().year else 1
    )
    try:
        selected_month = int(request.GET.get("month", default_month))
    except (TypeError, ValueError):
        selected_month = default_month
    selected_month = min(12, max(1, selected_month))

    context = _system_context(
        request,
        current_user,
        title=yearly_calendar["name"],
        eyebrow=YEARLY_CALENDAR_CONFIG.detail_eyebrow,
        intro=YEARLY_CALENDAR_CONFIG.detail_intro,
    )
    context.update(
        {
            "detail_rows": _yearly_calendar_detail_rows(yearly_calendar),
            "entity_status": yearly_calendar["status"],
            "back_href": YEARLY_CALENDAR_CONFIG.collection_path,
            "back_label": "Back to Calendars",
            "summary_items": _calendar_summary_items(yearly_calendar),
            "month_state": _calendar_month_state(yearly_calendar, selected_month),
            "special_day_rows": _calendar_special_day_rows(yearly_calendar["special_days"]),
            "special_day_empty_message": (
                "No special days have been created for this calendar yet."
            ),
            "special_day_create_href": (
                f"/system/calendars/{yearly_calendar['id']}/special-days/new/"
            ),
            "period_rule_href": "/system/calendar-period-rules/",
            "general_fields": _yearly_calendar_fields(
                current_user,
                post_data=post_data if active_form == "general" else None,
                entity=yearly_calendar,
            ),
            "general_form_error": form_error if active_form == "general" else "",
            "delete_form_error": form_error if active_form == "delete" else "",
        }
    )
    return render(request, "core/calendar_detail.html", context)


@require_http_methods(["GET", "POST"])
def calendar_special_day_create(
    request: HttpRequest,
    yearly_calendar_id: int,
) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    try:
        yearly_calendar = YearlyCalendarManagementService.get_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title="Create Special Day",
            eyebrow="SCR-117",
            intro="Create a special day inside the selected yearly calendar.",
            error=error,
        )

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            special_day = CalendarSpecialDayManagementService.create_special_day(
                current_user,
                {
                    "yearly_calendar_id": yearly_calendar_id,
                    "special_date": request.POST.get("special_date", ""),
                    "day_type_code": request.POST.get("day_type_code", ""),
                    "status_code": "ACTIVE",
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/calendar-special-days/{special_day['id']}/")

    context = _system_context(
        request,
        current_user,
        title="Create Special Day",
        eyebrow="SCR-117",
        intro="Add a new special day to the selected yearly calendar.",
    )
    context.update(
        {
            "detail_rows": _yearly_calendar_detail_rows(yearly_calendar),
            "back_href": f"/system/calendars/{yearly_calendar_id}/",
            "back_label": "Back to Calendar Detail",
            "form_title": "New Special Day",
            "form_intro": (
                "Choose a date inside the calendar year and assign one of the supported "
                "special-day types."
            ),
            "form_fields": _calendar_special_day_fields(
                current_user,
                yearly_calendar=yearly_calendar,
                post_data=post_data,
            ),
            "form_error": form_error,
            "submit_label": "Create Special Day",
        }
    )
    return render(request, "core/calendar_special_day_form.html", context)


@require_http_methods(["GET", "POST"])
def calendar_special_day_detail(request: HttpRequest, special_day_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    try:
        special_day = CalendarSpecialDayManagementService.get_special_day(
            current_user,
            special_day_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title="Calendar Special Day Detail",
            eyebrow="SCR-118",
            intro="Review or update the selected special day.",
            error=error,
        )

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "edit":
                CalendarSpecialDayManagementService.update_special_day(
                    current_user,
                    special_day_id,
                    {
                        "special_date": request.POST.get("special_date", ""),
                        "day_type_code": request.POST.get("day_type_code", ""),
                    },
                )
            elif active_form == "delete":
                CalendarSpecialDayManagementService.delete_special_day(
                    current_user,
                    special_day_id,
                )
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown special day form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(f"/system/calendars/{special_day['yearly_calendar']['id']}/")
            return redirect(f"/system/calendar-special-days/{special_day_id}/")

    return _render_detail_page(
        request,
        current_user,
        title=special_day["name"],
        eyebrow="SCR-118",
        intro="Update the selected special day inside the shared calendar management shell.",
        detail_rows=_calendar_special_day_detail_rows(special_day),
        form_sections=[
            {
                "form_name": "edit",
                "title": "Edit Special Day",
                "intro": "Update the selected date and special-day type.",
                "submit_label": "Save Special Day",
                "form_error": form_error if active_form == "edit" else "",
                "fields": _calendar_special_day_fields(
                    current_user,
                    yearly_calendar=special_day["yearly_calendar"],
                    post_data=post_data if active_form == "edit" else None,
                    entity=special_day,
                ),
            },
            {
                "form_name": "delete",
                "title": "Delete Special Day",
                "intro": (
                    "Delete this special day only if nothing else references it. "
                    "No cascade cleanup is performed."
                ),
                "submit_label": "Delete Special Day",
                "form_error": form_error if active_form == "delete" else "",
                "fields": [],
            },
        ],
        back_href=f"/system/calendars/{special_day['yearly_calendar']['id']}/",
        back_label="Back to Calendar Detail",
        entity_status=special_day["status"],
    )


@require_http_methods(["GET", "POST"])
def calendar_period_rules_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            period_rule = CalendarPeriodRuleManagementService.create_period_rule(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "yearly_calendar_id": request.POST.get("yearly_calendar_id", ""),
                    "effective_from": request.POST.get("effective_from", ""),
                    "effective_to": request.POST.get("effective_to", ""),
                    "monday_max_hours": request.POST.get("monday_max_hours", ""),
                    "tuesday_max_hours": request.POST.get("tuesday_max_hours", ""),
                    "wednesday_max_hours": request.POST.get("wednesday_max_hours", ""),
                    "thursday_max_hours": request.POST.get("thursday_max_hours", ""),
                    "friday_max_hours": request.POST.get("friday_max_hours", ""),
                    "working_on_saturdays_flag": _bool_from_post(
                        request.POST,
                        "working_on_saturdays_flag",
                    ),
                    "saturday_max_hours": request.POST.get("saturday_max_hours", ""),
                    "working_on_sundays_flag": _bool_from_post(
                        request.POST,
                        "working_on_sundays_flag",
                    ),
                    "sunday_max_hours": request.POST.get("sunday_max_hours", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/calendar-period-rules/{period_rule['id']}/")

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="CALENDAR_PERIOD_STATUS",
        default_code="ACTIVE",
    )
    period_rules = CalendarPeriodRuleManagementService.list_period_rules(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=CALENDAR_PERIOD_RULE_CONFIG,
        entities=period_rules,
        form_fields=_calendar_period_rule_fields(current_user, post_data=post_data),
        table_rows=_calendar_period_rule_rows(period_rules),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def calendar_period_rule_create(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            period_rule = CalendarPeriodRuleManagementService.create_period_rule(
                current_user,
                {
                    "business_unit_id": request.POST.get("business_unit_id", ""),
                    "yearly_calendar_id": request.POST.get("yearly_calendar_id", ""),
                    "effective_from": request.POST.get("effective_from", ""),
                    "effective_to": request.POST.get("effective_to", ""),
                    "monday_max_hours": request.POST.get("monday_max_hours", ""),
                    "tuesday_max_hours": request.POST.get("tuesday_max_hours", ""),
                    "wednesday_max_hours": request.POST.get("wednesday_max_hours", ""),
                    "thursday_max_hours": request.POST.get("thursday_max_hours", ""),
                    "friday_max_hours": request.POST.get("friday_max_hours", ""),
                    "working_on_saturdays_flag": _bool_from_post(
                        request.POST,
                        "working_on_saturdays_flag",
                    ),
                    "saturday_max_hours": request.POST.get("saturday_max_hours", ""),
                    "working_on_sundays_flag": _bool_from_post(
                        request.POST,
                        "working_on_sundays_flag",
                    ),
                    "sunday_max_hours": request.POST.get("sunday_max_hours", ""),
                    "status_code": request.POST.get("status_code", "ACTIVE"),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/calendar-period-rules/{period_rule['id']}/")

    return _render_master_create(
        request,
        current_user,
        config=CALENDAR_PERIOD_RULE_CONFIG,
        form_fields=_calendar_period_rule_fields(current_user, post_data=post_data),
        form_error=form_error,
        form_intro="Create a new Calendar Period Rule in your assigned Business Unit scope.",
    )


@require_http_methods(["GET", "POST"])
def calendar_period_rule_detail(request: HttpRequest, period_rule_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    active_form = "edit"
    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        active_form = request.POST.get("form_name", "edit")
        try:
            if active_form == "delete":
                CalendarPeriodRuleManagementService.delete_period_rule(
                    current_user,
                    period_rule_id,
                )
            else:
                CalendarPeriodRuleManagementService.update_period_rule(
                    current_user,
                    period_rule_id,
                    {
                        "business_unit_id": request.POST.get("business_unit_id", ""),
                        "effective_from": request.POST.get("effective_from", ""),
                        "effective_to": request.POST.get("effective_to", ""),
                        "monday_max_hours": request.POST.get("monday_max_hours", ""),
                        "tuesday_max_hours": request.POST.get("tuesday_max_hours", ""),
                    "wednesday_max_hours": request.POST.get("wednesday_max_hours", ""),
                    "thursday_max_hours": request.POST.get("thursday_max_hours", ""),
                        "friday_max_hours": request.POST.get("friday_max_hours", ""),
                        "working_on_saturdays_flag": _bool_from_post(
                            request.POST,
                            "working_on_saturdays_flag",
                        ),
                        "saturday_max_hours": request.POST.get("saturday_max_hours", ""),
                        "working_on_sundays_flag": _bool_from_post(
                            request.POST,
                            "working_on_sundays_flag",
                        ),
                        "sunday_max_hours": request.POST.get("sunday_max_hours", ""),
                        "status_code": request.POST.get("status_code", ""),
                    },
                )
        except AuthError as error:
            form_error = error.message
        else:
            if active_form == "delete":
                return redirect(CALENDAR_PERIOD_RULE_CONFIG.collection_path)
            return redirect(f"/system/calendar-period-rules/{period_rule_id}/")

    try:
        period_rule = CalendarPeriodRuleManagementService.get_period_rule(
            current_user,
            period_rule_id,
        )
    except AuthError as error:
        return _render_auth_error(
            request,
            current_user,
            title=CALENDAR_PERIOD_RULE_CONFIG.detail_title,
            eyebrow=CALENDAR_PERIOD_RULE_CONFIG.detail_eyebrow,
            intro=CALENDAR_PERIOD_RULE_CONFIG.detail_intro,
            error=error,
        )

    return _render_master_detail(
        request,
        current_user,
        config=CALENDAR_PERIOD_RULE_CONFIG,
        entity=period_rule,
        detail_rows=_calendar_period_rule_detail_rows(period_rule),
        form_fields=_calendar_period_rule_fields(
            current_user,
            post_data=post_data if active_form == "edit" else None,
            entity=period_rule,
        ),
        form_error=form_error,
        active_form=active_form,
        extra_form_sections=[
            _delete_action_section(
                submit_label="Delete Calendar Period Rule",
                form_error=form_error if active_form == "delete" else "",
            )
        ],
    )
