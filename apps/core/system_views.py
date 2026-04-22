from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.core.views import _page_context, _render_access_denied, _require_user
from apps.master_data.models import BusinessUnit, Employee, Project, YearlyCalendar
from apps.master_data.models import Client as ClientRecord
from apps.master_data.models import CostCenter as CostCenterRecord
from apps.master_data.models import InternalCategory as InternalCategoryRecord
from apps.master_data.services import (
    CalendarPeriodRuleManagementService,
    ClientManagementService,
    CostCenterManagementService,
    EmployeeManagementService,
    GeneralChargeCodeManagementService,
    InternalCategoryManagementService,
    ProjectAssignmentManagementService,
    ProjectManagementService,
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


def _system_section_links(current_user: CurrentUser, current_path: str) -> list[dict]:
    if not current_user.is_ts_admin:
        return []

    sections = [
        ("overview", "Overview", "/system/"),
        ("employees", "Employees", "/system/employees/"),
        ("clients", "Clients", "/system/clients/"),
        ("internal-categories", "Internal Categories", "/system/internal-categories/"),
        ("cost-centers", "Cost Centers", "/system/cost-centers/"),
        ("general-charge-codes", "General Charge Codes", "/system/general-charge-codes/"),
        ("projects", "Projects", "/system/projects/"),
        ("project-assignments", "Project Assignments", "/system/project-assignments/"),
        ("calendar-period-rules", "Calendar Period Rules", "/system/calendar-period-rules/"),
    ]
    return [
        {
            "key": key,
            "label": label,
            "href": href,
            "active": current_path == href
            or (href != "/system/" and current_path.startswith(href)),
        }
        for key, label, href in sections
    ]


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
        id__in=current_user.scoped_business_unit_ids
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


def _parent_client_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    exclude_client_id: int | None = None,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = [_option("", "No parent client", selected_values=selected_values)]
    clients = ClientRecord.objects.filter(
        business_unit_id__in=current_user.scoped_business_unit_ids
    ).select_related("business_unit")
    if exclude_client_id is not None:
        clients = clients.exclude(id=exclude_client_id)
    clients = clients.order_by("business_unit__bu_code", "client_code")
    options.extend(
        _option(
            client.id,
            f"{client.business_unit.bu_code} - {client.client_code} - {client.name}",
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
    }


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
    links = [{"label": "All", "href": request.path, "active": selected_code == "ALL"}]
    links.extend(
        {
            "label": ref_value.value_label,
            "href": f"{request.path}?status={ref_value.value_code}",
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
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Client", selected_values=selected_values))
    clients = ClientRecord.objects.filter(
        business_unit_id__in=current_user.scoped_business_unit_ids
    ).select_related("business_unit")
    if business_unit_id is not None:
        clients = clients.filter(business_unit_id=business_unit_id)
    clients = clients.order_by("business_unit__bu_code", "client_code")
    options.extend(
        _option(
            client.id,
            f"{client.business_unit.bu_code} - {client.client_code} - {client.name}",
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
        business_unit_id__in=current_user.scoped_business_unit_ids
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
        business_unit_id__in=current_user.scoped_business_unit_ids
    ).select_related("business_unit")
    if business_unit_id is not None:
        cost_centers = cost_centers.filter(business_unit_id=business_unit_id)
    cost_centers = cost_centers.order_by("business_unit__bu_code", "cost_center_code")
    options.extend(
        _option(
            cost_center.id,
            (
                f"{cost_center.business_unit.bu_code} - "
                f"{cost_center.cost_center_code} - {cost_center.name}"
            ),
            selected_values=selected_values,
        )
        for cost_center in cost_centers
    )
    return options


def _scoped_employee_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    include_blank: bool = False,
    required_role_code: str | None = None,
    business_unit_id: int | None = None,
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
        .filter(
            business_unit_assignments__business_unit_id__in=current_user.scoped_business_unit_ids
        )
        .distinct()
        .order_by("primary_business_unit__bu_code", "employee_code")
    )
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


def _scoped_project_options(
    current_user: CurrentUser,
    *,
    selected: object = None,
    include_blank: bool = False,
) -> list[dict]:
    selected_values = _selected_values(selected)
    options = []
    if include_blank:
        options.append(_option("", "Select a Project", selected_values=selected_values))
    projects = (
        Project.objects.select_related("business_unit", "status")
        .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
        .order_by("business_unit__bu_code", "project_code")
    )
    options.extend(
        _option(
            project.id,
            f"{project.business_unit.bu_code} - {project.project_code} - {project.name}",
            selected_values=selected_values,
        )
        for project in projects
    )
    return options


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
        YearlyCalendar.objects.select_related("business_unit")
        .filter(business_unit_id__in=current_user.scoped_business_unit_ids)
        .order_by("business_unit__bu_code", "calendar_year", "calendar_name")
    )
    options.extend(
        _option(
            calendar.id,
            (
                f"{calendar.business_unit.bu_code} - "
                f"{calendar.calendar_year} - {calendar.calendar_name}"
            ),
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
        else [str(current_user.primary_business_unit_id)]
    )
    return [
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
            label="Business Unit Scope",
            kind="multiselect",
            options=_scoped_business_unit_options(
                current_user,
                selected=selected_business_units,
            ),
            help_text="Select every Business Unit this employee may operate in.",
            required=True,
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
    selected_primary = (
        post_data.get("primary_business_unit_id", employee["primary_business_unit"]["id"])
        if post_data is not None
        else employee["primary_business_unit"]["id"]
    )
    selected_scope = (
        post_data.getlist("business_unit_ids")
        if post_data is not None
        else [business_unit["id"] for business_unit in employee["business_units"]]
    )
    return [
        _field(
            name="primary_business_unit_id",
            label="Primary Business Unit",
            kind="select",
            options=_scoped_business_unit_options(current_user, selected=selected_primary),
            required=True,
        ),
        _field(
            name="business_unit_ids",
            label="Business Unit Scope",
            kind="multiselect",
            options=_scoped_business_unit_options(current_user, selected=selected_scope),
            help_text="The primary Business Unit must also be part of the employee scope.",
            required=True,
        ),
    ]


def _client_form_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    selected_business_unit = post_data.get("business_unit_id", "") if post_data is not None else ""
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])

    selected_parent = post_data.get("parent_client_id", "") if post_data is not None else ""
    if entity is not None and post_data is None and entity["parent_client"] is not None:
        selected_parent = str(entity["parent_client"]["id"])

    return [
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
            name="client_code",
            label="Client Code",
            kind="text",
            value=post_data.get("client_code", entity["client_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Client Name",
            kind="text",
            value=post_data.get("name", entity["name"] if entity else "")
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
                selected=post_data.get("status_code", entity["status"] if entity else "ACTIVE")
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
    selected_business_unit = post_data.get("business_unit_id", "") if post_data is not None else ""
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])

    description_value = ""
    if entity is not None:
        description_value = entity["description"]
    if post_data is not None:
        description_value = post_data.get("description", description_value)

    return [
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
            value=post_data.get(code_name, entity[code_name] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label=name_label,
            kind="text",
            value=post_data.get("name", entity["name"] if entity else "")
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
                selected=post_data.get("status_code", entity["status"] if entity else "ACTIVE")
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
    selected_business_unit = post_data.get("business_unit_id", "") if post_data is not None else ""
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])

    valid_from_value = ""
    if entity is not None:
        valid_from_value = entity["valid_from"]
    if post_data is not None:
        valid_from_value = post_data.get("valid_from", valid_from_value)

    valid_to_value = ""
    if entity is not None and entity["valid_to"] is not None:
        valid_to_value = entity["valid_to"]
    if post_data is not None:
        valid_to_value = post_data.get("valid_to", valid_to_value)

    return [
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
            value=post_data.get("code", entity["code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Name",
            kind="text",
            value=post_data.get("name", entity["name"] if entity else "")
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
                selected=post_data.get(
                    "charge_type_code",
                    entity["charge_type"] if entity else "STANDARD",
                )
                if post_data is not None or entity is not None
                else "STANDARD",
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
            name="common_code_flag",
            label="Common Code",
            kind="checkbox",
            checked=_bool_from_post(post_data, "common_code_flag")
            if post_data is not None
            else bool(entity["common_code_flag"])
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
                selected=post_data.get("status_code", entity["status"] if entity else "ACTIVE")
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
    selected_business_unit = post_data.get("business_unit_id", "") if post_data is not None else ""
    if entity is not None and post_data is None:
        selected_business_unit = str(entity["business_unit"]["id"])
    scoped_business_unit_id = (
        int(selected_business_unit) if str(selected_business_unit).isdigit() else None
    )
    return [
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
            value=post_data.get("project_code", entity["project_code"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="name",
            label="Project Name",
            kind="text",
            value=post_data.get("name", entity["name"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="description",
            label="Description",
            kind="textarea",
            value=post_data.get("description", entity["description"] if entity else "")
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="project_owner_employee_id",
            label="Project Owner",
            kind="select",
            options=_scoped_employee_options(
                current_user,
                selected=post_data.get(
                    "project_owner_employee_id",
                    entity["project_owner_employee"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
                required_role_code="PROJECT_OWNER",
                business_unit_id=scoped_business_unit_id,
            ),
            required=True,
        ),
        _field(
            name="project_manager_employee_id",
            label="Project Manager",
            kind="select",
            options=_scoped_employee_options(
                current_user,
                selected=post_data.get(
                    "project_manager_employee_id",
                    entity["project_manager_employee"]["id"] if entity else "",
                )
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
                required_role_code="PROJECT_MANAGER",
                business_unit_id=scoped_business_unit_id,
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
                selected=post_data.get("client_id", entity["client"]["id"] if entity else "")
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
                selected=post_data.get(
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
                selected=post_data.get(
                    "cost_center_id", entity["cost_center"]["id"] if entity else ""
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
            value=post_data.get("start_date", entity["start_date"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="end_date",
            label="End Date",
            kind="date",
            value=post_data.get(
                "end_date", entity["end_date"] if entity and entity["end_date"] else ""
            )
            if post_data is not None or entity is not None
            else "",
        ),
        _field(
            name="close_date",
            label="Close Date",
            kind="date",
            value=post_data.get(
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
                selected=post_data.get("status_code", entity["status"] if entity else "DRAFT")
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
    return [
        _field(
            name="project_id",
            label="Project",
            kind="select",
            options=_scoped_project_options(
                current_user,
                selected=post_data.get("project_id", entity["project"]["id"] if entity else "")
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
                selected=post_data.get("employee_id", entity["employee"]["id"] if entity else "")
                if post_data is not None or entity is not None
                else "",
                include_blank=entity is None,
            ),
            required=True,
        ),
        _field(
            name="assignment_start_date",
            label="Assignment Start Date",
            kind="date",
            value=post_data.get(
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
            value=post_data.get(
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
                selected=post_data.get("status_code", entity["status"] if entity else "ACTIVE")
                if post_data is not None or entity is not None
                else "ACTIVE",
            ),
            required=True,
        ),
    ]


def _calendar_period_rule_fields(
    current_user: CurrentUser,
    *,
    post_data: QueryDict | None = None,
    entity: dict | None = None,
) -> list[dict]:
    return [
        _field(
            name="yearly_calendar_id",
            label="Yearly Calendar",
            kind="select",
            options=_scoped_yearly_calendar_options(
                current_user,
                selected=post_data.get(
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
            value=post_data.get("effective_from", entity["effective_from"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="effective_to",
            label="Effective To",
            kind="date",
            value=post_data.get("effective_to", entity["effective_to"] if entity else "")
            if post_data is not None or entity is not None
            else "",
            required=True,
        ),
        _field(
            name="monday_max_hours",
            label="Monday Max Hours",
            kind="number",
            value=post_data.get(
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
            value=post_data.get(
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
            value=post_data.get(
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
            value=post_data.get(
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
            value=post_data.get(
                "friday_max_hours", entity["friday_max_hours"] if entity else "8.00"
            )
            if post_data is not None or entity is not None
            else "8.00",
            required=True,
        ),
        _field(
            name="status_code",
            label="Status",
            kind="select",
            options=_ref_options(
                "CALENDAR_PERIOD_STATUS",
                selected=post_data.get("status_code", entity["status"] if entity else "ACTIVE")
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
    form_title: str,
    form_intro: str,
    form_fields: list[dict],
    submit_label: str,
    form_error: str = "",
    filter_links: list[dict] | None = None,
    filter_title: str = "Filters",
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
            "form_title": form_title,
            "form_intro": form_intro,
            "form_fields": form_fields,
            "submit_label": submit_label,
            "form_error": form_error,
            "filter_links": filter_links or [],
            "filter_title": filter_title,
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
        }
    )
    return render(request, "core/system_detail.html", context)


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


def _client_rows(clients: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/clients/{client['id']}/",
            "cells": [
                client["business_unit"]["bu_code"],
                client["client_code"],
                client["name"],
                client["status"],
                client["parent_client"]["client_code"] if client["parent_client"] else "None",
            ],
        }
        for client in clients
    ]


def _client_detail_rows(client: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", client["business_unit"]["bu_code"]),
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
                cost_center["business_unit"]["bu_code"],
                cost_center["cost_center_code"],
                cost_center["name"],
                cost_center["status"],
            ],
        }
        for cost_center in cost_centers
    ]


def _cost_center_detail_rows(cost_center: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", cost_center["business_unit"]["bu_code"]),
        ("Cost Center Code", cost_center["cost_center_code"]),
        ("Name", cost_center["name"]),
        ("Description", cost_center["description"] or "None"),
        ("Status", cost_center["status"]),
    ]


def _general_charge_code_rows(general_charge_codes: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/general-charge-codes/{general_charge_code['id']}/",
            "cells": [
                general_charge_code["business_unit"]["bu_code"],
                general_charge_code["code"],
                general_charge_code["name"],
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
        ("Charge Type", general_charge_code["charge_type"]),
        (
            "Flags",
            ", ".join(
                label
                for label, enabled in (
                    ("Billable", general_charge_code["billable_flag"]),
                    ("Common Code", general_charge_code["common_code_flag"]),
                    ("Requires Approval", general_charge_code["requires_approval_flag"]),
                    ("Description Required", general_charge_code["description_required_flag"]),
                )
                if enabled
            )
            or "None",
        ),
        ("Valid From", general_charge_code["valid_from"]),
        ("Valid To", general_charge_code["valid_to"] or "Open-ended"),
        ("Status", general_charge_code["status"]),
    ]


def _project_rows(projects: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/projects/{project['id']}/",
            "cells": [
                project["business_unit"]["bu_code"],
                project["project_code"],
                project["name"],
                project["status"],
                project["project_owner_employee"]["employee_code"],
                project["project_manager_employee"]["employee_code"],
            ],
        }
        for project in projects
    ]


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
                assignment["project"]["business_unit"]["bu_code"],
                assignment["project"]["project_code"],
                assignment["employee"]["employee_code"],
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
        ("Employee", assignment["employee"]["employee_code"]),
        ("Assignment Start Date", assignment["assignment_start_date"]),
        ("Assignment End Date", assignment["assignment_end_date"] or "Open-ended"),
        ("Status", assignment["status"]),
    ]


def _calendar_period_rule_rows(period_rules: list[dict]) -> list[dict]:
    return [
        {
            "href": f"/system/calendar-period-rules/{period_rule['id']}/",
            "cells": [
                period_rule["yearly_calendar"]["business_unit"]["bu_code"],
                str(period_rule["yearly_calendar"]["calendar_year"]),
                period_rule["yearly_calendar"]["calendar_name"],
                period_rule["effective_from"],
                period_rule["effective_to"],
                period_rule["status"],
            ],
        }
        for period_rule in period_rules
    ]


def _calendar_period_rule_detail_rows(period_rule: dict) -> list[tuple[str, str]]:
    return [
        ("Business Unit", period_rule["yearly_calendar"]["business_unit"]["bu_code"]),
        ("Calendar", period_rule["yearly_calendar"]["name"]),
        ("Effective From", period_rule["effective_from"]),
        ("Effective To", period_rule["effective_to"]),
        ("Monday Max Hours", period_rule["monday_max_hours"]),
        ("Tuesday Max Hours", period_rule["tuesday_max_hours"]),
        ("Wednesday Max Hours", period_rule["wednesday_max_hours"]),
        ("Thursday Max Hours", period_rule["thursday_max_hours"]),
        ("Friday Max Hours", period_rule["friday_max_hours"]),
        ("Status", period_rule["status"]),
    ]


CLIENT_CONFIG = MasterUiConfig(
    section_key="clients",
    list_title="Client Management",
    list_eyebrow="SCR-130",
    list_intro="Scoped client list with server-rendered create form for Timesheet Administrators.",
    detail_title="Client Detail",
    detail_eyebrow="SCR-131",
    detail_intro=(
        "Update client identity and lifecycle fields within your assigned Business Unit scope."
    ),
    singular_label="Client",
    plural_label="Clients",
    collection_path="/system/clients/",
    detail_path_prefix="/system/clients/",
    table_headers=("Business Unit", "Client Code", "Name", "Status", "Parent"),
    empty_message="No clients are available in your assigned Business Units yet.",
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
    list_intro="Scoped cost center list with create form for Timesheet Administrators.",
    detail_title="Cost Center Detail",
    detail_eyebrow="SCR-151",
    detail_intro="Update cost center attributes while keeping Business Unit scope server-side.",
    singular_label="Cost Center",
    plural_label="Cost Centers",
    collection_path="/system/cost-centers/",
    detail_path_prefix="/system/cost-centers/",
    table_headers=("Business Unit", "Cost Center Code", "Name", "Status"),
    empty_message="No cost centers are available in your assigned Business Units yet.",
)

GENERAL_CHARGE_CODE_CONFIG = MasterUiConfig(
    section_key="general-charge-codes",
    list_title="General Charge Code Management",
    list_eyebrow="SCR-170",
    list_intro="Scoped general charge code list with create form and lifecycle fields.",
    detail_title="General Charge Code Detail",
    detail_eyebrow="SCR-171",
    detail_intro=(
        "Update charge-code validity, flags, and lifecycle fields inside the shared shell."
    ),
    singular_label="General Charge Code",
    plural_label="General Charge Codes",
    collection_path="/system/general-charge-codes/",
    detail_path_prefix="/system/general-charge-codes/",
    table_headers=("Business Unit", "Code", "Name", "Charge Type", "Status"),
    empty_message="No general charge codes are available in your assigned Business Units yet.",
)

PROJECT_CONFIG = MasterUiConfig(
    section_key="projects",
    list_title="Project Management",
    list_eyebrow="SCR-180",
    list_intro="Scoped project list with create form for Timesheet Administrators.",
    detail_title="Project Detail",
    detail_eyebrow="SCR-181",
    detail_intro="Update project ownership, classification, dates, and lifecycle fields.",
    singular_label="Project",
    plural_label="Projects",
    collection_path="/system/projects/",
    detail_path_prefix="/system/projects/",
    table_headers=("Business Unit", "Project Code", "Name", "Status", "Owner", "Manager"),
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
    table_headers=("Business Unit", "Project", "Employee", "Start", "End", "Status"),
    empty_message="No project assignments are available in your assigned Business Units yet.",
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
    table_headers=("Business Unit", "Year", "Calendar", "Effective From", "Effective To", "Status"),
    empty_message="No calendar period rules are available in your assigned Business Units yet.",
)


@require_http_methods(["GET", "POST"])
def employees_collection(request: HttpRequest) -> HttpResponse:
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
        form_title="Create Employee",
        form_intro=(
            "Create a new internal employee record with its initial roles and Business Unit scope."
        ),
        form_fields=_employee_create_fields(current_user, post_data=post_data),
        submit_label="Create Employee",
        form_error=form_error,
        filter_links=filter_links,
        filter_title="Employee Status",
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
            else:
                raise AuthError(
                    "UI_FORM_UNKNOWN",
                    "Unknown employee form submission.",
                    400,
                )
        except AuthError as error:
            form_error = error.message
        else:
            return redirect(f"/system/employees/{employee_id}/")

    try:
        employee = EmployeeManagementService.get_employee(current_user, employee_id)
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
            "fields": _employee_business_unit_fields(
                current_user,
                employee,
                post_data=post_data if active_form == "business_units" else None,
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
) -> HttpResponse:
    return _render_collection_page(
        request,
        current_user,
        title=config.list_title,
        eyebrow=config.list_eyebrow,
        intro=config.list_intro,
        table_headers=config.table_headers,
        table_rows=table_rows,
        empty_message=config.empty_message,
        form_title=f"Create {config.singular_label}",
        form_intro=(
            f"Create a new {config.singular_label.lower()} in your assigned Business Unit scope."
        ),
        form_fields=form_fields,
        submit_label=f"Create {config.singular_label}",
        form_error=form_error,
        filter_links=filter_links,
        filter_title=f"{config.singular_label} Status",
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
) -> HttpResponse:
    return _render_detail_page(
        request,
        current_user,
        title=entity["name"],
        eyebrow=config.detail_eyebrow,
        intro=config.detail_intro,
        detail_rows=detail_rows,
        form_sections=[
            {
                "form_name": "edit",
                "title": f"Edit {config.singular_label}",
                "intro": (
                    f"Update the selected {config.singular_label.lower()} "
                    "without leaving the shared shell."
                ),
                "submit_label": f"Save {config.singular_label}",
                "form_error": form_error,
                "fields": form_fields,
            }
        ],
        back_href=config.collection_path,
        back_label=f"Back to {config.plural_label}",
        entity_status=entity["status"],
    )


@require_http_methods(["GET", "POST"])
def clients_collection(request: HttpRequest) -> HttpResponse:
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
                    "business_unit_id": request.POST.get("business_unit_id", ""),
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

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="CLIENT_STATUS",
        default_code="ACTIVE",
    )
    clients = ClientManagementService.list_clients(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=CLIENT_CONFIG,
        entities=clients,
        form_fields=_client_form_fields(current_user, post_data=post_data),
        table_rows=_client_rows(clients),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def client_detail(request: HttpRequest, client_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
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
        except AuthError as error:
            form_error = error.message
        else:
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
        form_fields=_client_form_fields(current_user, post_data=post_data, entity=client),
        form_error=form_error,
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
def internal_category_detail(request: HttpRequest, category_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
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
        except AuthError as error:
            form_error = error.message
        else:
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
            post_data=post_data,
            entity=category,
            business_unit_label="Business Unit",
            code_name="category_code",
            code_label="Category Code",
            name_label="Category Name",
            description_label="Description",
            status_domain="INTERNAL_CATEGORY_STATUS",
        ),
        form_error=form_error,
    )


@require_http_methods(["GET", "POST"])
def cost_centers_collection(request: HttpRequest) -> HttpResponse:
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
                    "business_unit_id": request.POST.get("business_unit_id", ""),
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

    selected_status_code, filter_links = _status_filter_links(
        request,
        domain_code="COST_CENTER_STATUS",
        default_code="ACTIVE",
    )
    cost_centers = CostCenterManagementService.list_cost_centers(
        current_user,
        status_code=_service_status_code(selected_status_code),
    )
    return _render_master_collection(
        request,
        current_user,
        config=COST_CENTER_CONFIG,
        entities=cost_centers,
        form_fields=_simple_master_fields(
            current_user,
            post_data=post_data,
            entity=None,
            business_unit_label="Business Unit",
            code_name="cost_center_code",
            code_label="Cost Center Code",
            name_label="Cost Center Name",
            description_label="Description",
            status_domain="COST_CENTER_STATUS",
        ),
        table_rows=_cost_center_rows(cost_centers),
        form_error=form_error,
        filter_links=filter_links,
    )


@require_http_methods(["GET", "POST"])
def cost_center_detail(request: HttpRequest, cost_center_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
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
        except AuthError as error:
            form_error = error.message
        else:
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
        form_fields=_simple_master_fields(
            current_user,
            post_data=post_data,
            entity=cost_center,
            business_unit_label="Business Unit",
            code_name="cost_center_code",
            code_label="Cost Center Code",
            name_label="Cost Center Name",
            description_label="Description",
            status_domain="COST_CENTER_STATUS",
        ),
        form_error=form_error,
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
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "common_code_flag": _bool_from_post(request.POST, "common_code_flag"),
                    "requires_approval_flag": _bool_from_post(
                        request.POST, "requires_approval_flag"
                    ),
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
def general_charge_code_detail(
    request: HttpRequest,
    general_charge_code_id: int,
) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            GeneralChargeCodeManagementService.update_general_charge_code(
                current_user,
                general_charge_code_id,
                {
                    "code": request.POST.get("code", ""),
                    "name": request.POST.get("name", ""),
                    "charge_type_code": request.POST.get("charge_type_code", ""),
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "common_code_flag": _bool_from_post(request.POST, "common_code_flag"),
                    "requires_approval_flag": _bool_from_post(
                        request.POST, "requires_approval_flag"
                    ),
                    "description_required_flag": _bool_from_post(
                        request.POST, "description_required_flag"
                    ),
                    "valid_from": request.POST.get("valid_from", ""),
                    "valid_to": request.POST.get("valid_to", ""),
                    "status_code": request.POST.get("status_code", ""),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
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
            post_data=post_data,
            entity=general_charge_code,
        ),
        form_error=form_error,
    )


@require_http_methods(["GET", "POST"])
def projects_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
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
    projects = ProjectManagementService.list_projects(
        current_user,
        status_code=_service_status_code(selected_status_code),
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
    )


@require_http_methods(["GET", "POST"])
def project_detail(request: HttpRequest, project_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
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
                    "start_date": request.POST.get("start_date", ""),
                    "end_date": request.POST.get("end_date", ""),
                    "close_date": request.POST.get("close_date", ""),
                    "billable_flag": _bool_from_post(request.POST, "billable_flag"),
                    "status_code": request.POST.get("status_code", ""),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
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
        form_fields=_project_form_fields(current_user, post_data=post_data, entity=project),
        form_error=form_error,
    )


@require_http_methods(["GET", "POST"])
def project_assignments_collection(request: HttpRequest) -> HttpResponse:
    current_user = _require_ts_admin(request)
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
    assignments = ProjectAssignmentManagementService.list_assignments(
        current_user,
        status_code=_service_status_code(selected_status_code),
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
    )


@require_http_methods(["GET", "POST"])
def project_assignment_detail(request: HttpRequest, assignment_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            ProjectAssignmentManagementService.update_assignment(
                current_user,
                assignment_id,
                {
                    "assignment_start_date": request.POST.get("assignment_start_date", ""),
                    "assignment_end_date": request.POST.get("assignment_end_date", ""),
                    "status_code": request.POST.get("status_code", ""),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
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
            post_data=post_data,
            entity=assignment,
        ),
        form_error=form_error,
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
                    "yearly_calendar_id": request.POST.get("yearly_calendar_id", ""),
                    "effective_from": request.POST.get("effective_from", ""),
                    "effective_to": request.POST.get("effective_to", ""),
                    "monday_max_hours": request.POST.get("monday_max_hours", ""),
                    "tuesday_max_hours": request.POST.get("tuesday_max_hours", ""),
                    "wednesday_max_hours": request.POST.get("wednesday_max_hours", ""),
                    "thursday_max_hours": request.POST.get("thursday_max_hours", ""),
                    "friday_max_hours": request.POST.get("friday_max_hours", ""),
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
def calendar_period_rule_detail(request: HttpRequest, period_rule_id: int) -> HttpResponse:
    current_user = _require_ts_admin(request)
    if not isinstance(current_user, CurrentUser):
        return current_user

    form_error = ""
    post_data = request.POST if request.method == "POST" else None
    if request.method == "POST":
        try:
            CalendarPeriodRuleManagementService.update_period_rule(
                current_user,
                period_rule_id,
                {
                    "effective_from": request.POST.get("effective_from", ""),
                    "effective_to": request.POST.get("effective_to", ""),
                    "monday_max_hours": request.POST.get("monday_max_hours", ""),
                    "tuesday_max_hours": request.POST.get("tuesday_max_hours", ""),
                    "wednesday_max_hours": request.POST.get("wednesday_max_hours", ""),
                    "thursday_max_hours": request.POST.get("thursday_max_hours", ""),
                    "friday_max_hours": request.POST.get("friday_max_hours", ""),
                    "status_code": request.POST.get("status_code", ""),
                },
            )
        except AuthError as error:
            form_error = error.message
        else:
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
            post_data=post_data,
            entity=period_rule,
        ),
        form_error=form_error,
    )
