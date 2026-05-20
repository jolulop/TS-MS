from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.audit.services import write_audit_event
from apps.auth.errors import AuthError
from apps.auth.services import CurrentUserService, error_response, parse_json_request
from apps.master_data.models import Employee
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


def _handle_guarded_delete(
    request: HttpRequest,
    *,
    entity_name: str,
    entity_id: int,
    delete_callable,
    blocked_codes: set[str],
) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        delete_callable(current_user, entity_id)
    except AuthError as exc:
        if exc.code in blocked_codes:
            _audit_blocked_delete_attempt(
                request,
                entity_name=entity_name,
                entity_id=entity_id,
                reason_text=exc.message,
            )
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"deleted": True, "entity": entity_name, "id": entity_id})


def _audit_blocked_delete_attempt(
    request: HttpRequest,
    *,
    entity_name: str,
    entity_id: int,
    reason_text: str,
) -> None:
    current_user = CurrentUserService.get_from_request(request)
    actor_employee = Employee.objects.filter(id=current_user.employee_id).first()
    write_audit_event(
        action_code="DENY",
        entity_name=entity_name,
        entity_id=entity_id,
        actor_employee=actor_employee,
        actor_email=current_user.email,
        reason_text=reason_text,
    )


@require_http_methods(["GET", "POST"])
def countries_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            countries = CountryManagementService.list_countries(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"countries": countries})

        payload = parse_json_request(request)
        country = CountryManagementService.create_country(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"country": country}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def country_detail(request: HttpRequest, country_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            country = CountryManagementService.get_country(current_user, country_id)
            return JsonResponse({"country": country})
        if request.method == "PATCH":
            payload = parse_json_request(request)
            country = CountryManagementService.update_country(current_user, country_id, payload)
            return JsonResponse({"country": country})

        CountryManagementService.delete_country(current_user, country_id)
    except AuthError as exc:
        if request.method == "DELETE" and exc.code == "COUNTRY_DELETE_BLOCKED":
            _audit_blocked_delete_attempt(
                request,
                entity_name="country",
                entity_id=country_id,
                reason_text=exc.message,
            )
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"deleted": True, "entity": "country", "id": country_id})


@require_http_methods(["GET", "POST"])
def offices_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            offices = OfficeManagementService.list_offices(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"offices": offices})

        payload = parse_json_request(request)
        office = OfficeManagementService.create_office(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"office": office}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def office_detail(request: HttpRequest, office_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            office = OfficeManagementService.get_office(current_user, office_id)
            return JsonResponse({"office": office})
        if request.method == "PATCH":
            payload = parse_json_request(request)
            office = OfficeManagementService.update_office(current_user, office_id, payload)
            return JsonResponse({"office": office})

        OfficeManagementService.delete_office(current_user, office_id)
    except AuthError as exc:
        if request.method == "DELETE" and exc.code == "COUNTRY_DELETE_BLOCKED":
            _audit_blocked_delete_attempt(
                request,
                entity_name="office",
                entity_id=office_id,
                reason_text=exc.message,
            )
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"deleted": True, "entity": "office", "id": office_id})


@require_http_methods(["GET", "POST"])
def business_units_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            business_units = BusinessUnitManagementService.list_business_units(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"business_units": business_units})

        payload = parse_json_request(request)
        business_unit = BusinessUnitManagementService.create_business_unit(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"business_unit": business_unit}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def business_unit_detail(request: HttpRequest, business_unit_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="business_unit",
            entity_id=business_unit_id,
            delete_callable=BusinessUnitManagementService.delete_business_unit,
            blocked_codes={"BUSINESS_UNIT_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            business_unit = BusinessUnitManagementService.get_business_unit(
                current_user,
                business_unit_id,
            )
            return JsonResponse({"business_unit": business_unit})

        payload = parse_json_request(request)
        business_unit = BusinessUnitManagementService.update_business_unit(
            current_user,
            business_unit_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"business_unit": business_unit})


@require_http_methods(["GET", "POST"])
def clients_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            clients = ClientManagementService.list_clients(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"clients": clients})

        payload = parse_json_request(request)
        client = ClientManagementService.create_client(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"client": client}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def client_detail(request: HttpRequest, client_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="client",
            entity_id=client_id,
            delete_callable=ClientManagementService.delete_client,
            blocked_codes={"CLIENT_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            client = ClientManagementService.get_client(current_user, client_id)
            return JsonResponse({"client": client})

        payload = parse_json_request(request)
        client = ClientManagementService.update_client(current_user, client_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"client": client})


@require_http_methods(["GET", "POST"])
def internal_categories_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            categories = InternalCategoryManagementService.list_categories(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"internal_categories": categories})

        payload = parse_json_request(request)
        category = InternalCategoryManagementService.create_category(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"internal_category": category}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def internal_category_detail(request: HttpRequest, category_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="internal_category",
            entity_id=category_id,
            delete_callable=InternalCategoryManagementService.delete_category,
            blocked_codes={"INTERNAL_CATEGORY_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            category = InternalCategoryManagementService.get_category(current_user, category_id)
            return JsonResponse({"internal_category": category})

        payload = parse_json_request(request)
        category = InternalCategoryManagementService.update_category(
            current_user,
            category_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"internal_category": category})


@require_http_methods(["GET", "POST"])
def cost_centers_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            cost_centers = CostCenterManagementService.list_cost_centers(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"cost_centers": cost_centers})

        payload = parse_json_request(request)
        cost_center = CostCenterManagementService.create_cost_center(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"cost_center": cost_center}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def cost_center_detail(request: HttpRequest, cost_center_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="cost_center",
            entity_id=cost_center_id,
            delete_callable=CostCenterManagementService.delete_cost_center,
            blocked_codes={"COST_CENTER_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            cost_center = CostCenterManagementService.get_cost_center(current_user, cost_center_id)
            return JsonResponse({"cost_center": cost_center})

        payload = parse_json_request(request)
        cost_center = CostCenterManagementService.update_cost_center(
            current_user,
            cost_center_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"cost_center": cost_center})


@require_http_methods(["GET", "POST"])
def pricing_models_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            pricing_models = PricingModelManagementService.list_pricing_models(current_user)
            return JsonResponse({"pricing_models": pricing_models})

        payload = parse_json_request(request)
        pricing_model = PricingModelManagementService.create_pricing_model(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"pricing_model": pricing_model}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def pricing_model_detail(request: HttpRequest, pricing_model_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="pricing_model",
            entity_id=pricing_model_id,
            delete_callable=PricingModelManagementService.delete_pricing_model,
            blocked_codes={"PRICING_MODEL_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            pricing_model = PricingModelManagementService.get_pricing_model(
                current_user,
                pricing_model_id,
            )
            return JsonResponse({"pricing_model": pricing_model})

        payload = parse_json_request(request)
        pricing_model = PricingModelManagementService.update_pricing_model(
            current_user,
            pricing_model_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"pricing_model": pricing_model})


@require_http_methods(["GET", "POST"])
def general_charge_codes_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            general_charge_codes = GeneralChargeCodeManagementService.list_general_charge_codes(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"general_charge_codes": general_charge_codes})

        payload = parse_json_request(request)
        general_charge_code = GeneralChargeCodeManagementService.create_general_charge_code(
            current_user,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"general_charge_code": general_charge_code}, status=201)


@require_http_methods(["GET", "POST"])
def general_charge_code_approval_roles_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            approval_roles = GeneralChargeCodeApprovalRoleManagementService.list_approval_roles(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"general_charge_code_approval_roles": approval_roles})

        payload = parse_json_request(request)
        approval_role = GeneralChargeCodeApprovalRoleManagementService.create_approval_role(
            current_user,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"general_charge_code_approval_role": approval_role}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def general_charge_code_approval_role_detail(
    request: HttpRequest,
    approval_role_id: int,
) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="general_charge_code_approval_role",
            entity_id=approval_role_id,
            delete_callable=GeneralChargeCodeApprovalRoleManagementService.delete_approval_role,
            blocked_codes={"GENERAL_CHARGE_CODE_APPROVAL_ROLE_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            approval_role = GeneralChargeCodeApprovalRoleManagementService.get_approval_role(
                current_user,
                approval_role_id,
            )
            return JsonResponse({"general_charge_code_approval_role": approval_role})

        payload = parse_json_request(request)
        approval_role = GeneralChargeCodeApprovalRoleManagementService.update_approval_role(
            current_user,
            approval_role_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"general_charge_code_approval_role": approval_role})


@require_http_methods(["GET", "PATCH", "DELETE"])
def general_charge_code_detail(
    request: HttpRequest,
    general_charge_code_id: int,
) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="general_charge_code",
            entity_id=general_charge_code_id,
            delete_callable=GeneralChargeCodeManagementService.delete_general_charge_code,
            blocked_codes={"GENERAL_CHARGE_CODE_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            general_charge_code = GeneralChargeCodeManagementService.get_general_charge_code(
                current_user,
                general_charge_code_id,
            )
            return JsonResponse({"general_charge_code": general_charge_code})

        payload = parse_json_request(request)
        general_charge_code = GeneralChargeCodeManagementService.update_general_charge_code(
            current_user,
            general_charge_code_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"general_charge_code": general_charge_code})


@require_http_methods(["GET", "POST"])
def yearly_calendars_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            yearly_calendars = YearlyCalendarManagementService.list_yearly_calendars(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"yearly_calendars": yearly_calendars})

        payload = parse_json_request(request)
        yearly_calendar = YearlyCalendarManagementService.create_yearly_calendar(
            current_user,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"yearly_calendar": yearly_calendar}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def yearly_calendar_detail(request: HttpRequest, yearly_calendar_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="yearly_calendar",
            entity_id=yearly_calendar_id,
            delete_callable=YearlyCalendarManagementService.delete_yearly_calendar,
            blocked_codes={"YEARLY_CALENDAR_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            yearly_calendar = YearlyCalendarManagementService.get_yearly_calendar(
                current_user,
                yearly_calendar_id,
            )
            return JsonResponse({"yearly_calendar": yearly_calendar})

        payload = parse_json_request(request)
        yearly_calendar = YearlyCalendarManagementService.update_yearly_calendar(
            current_user,
            yearly_calendar_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"yearly_calendar": yearly_calendar})


@require_http_methods(["GET", "POST"])
def calendar_special_days_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            yearly_calendar_id = request.GET.get("yearly_calendar_id")
            special_days = CalendarSpecialDayManagementService.list_special_days(
                current_user,
                yearly_calendar_id=int(yearly_calendar_id)
                if yearly_calendar_id and yearly_calendar_id.isdigit()
                else None,
            )
            return JsonResponse({"calendar_special_days": special_days})

        payload = parse_json_request(request)
        special_day = CalendarSpecialDayManagementService.create_special_day(
            current_user,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"calendar_special_day": special_day}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def calendar_special_day_detail(request: HttpRequest, special_day_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="calendar_special_day",
            entity_id=special_day_id,
            delete_callable=CalendarSpecialDayManagementService.delete_special_day,
            blocked_codes={"CALENDAR_SPECIAL_DAY_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            special_day = CalendarSpecialDayManagementService.get_special_day(
                current_user,
                special_day_id,
            )
            return JsonResponse({"calendar_special_day": special_day})

        payload = parse_json_request(request)
        special_day = CalendarSpecialDayManagementService.update_special_day(
            current_user,
            special_day_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"calendar_special_day": special_day})


@require_http_methods(["GET", "POST"])
def employees_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            employees = EmployeeManagementService.list_employees(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"employees": employees})

        payload = parse_json_request(request)
        employee = EmployeeManagementService.create_employee(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"employee": employee}, status=201)


@require_http_methods(["GET", "POST"])
def projects_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            projects = ProjectManagementService.list_projects(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"projects": projects})

        payload = parse_json_request(request)
        project = ProjectManagementService.create_project(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"project": project}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def project_detail(request: HttpRequest, project_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="project",
            entity_id=project_id,
            delete_callable=ProjectManagementService.delete_project,
            blocked_codes={"PROJECT_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            project = ProjectManagementService.get_project(current_user, project_id)
            return JsonResponse({"project": project})

        payload = parse_json_request(request)
        project = ProjectManagementService.update_project(current_user, project_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"project": project})


@require_http_methods(["GET", "POST"])
def project_assignments_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            assignments = ProjectAssignmentManagementService.list_assignments(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"project_assignments": assignments})

        payload = parse_json_request(request)
        assignment = ProjectAssignmentManagementService.create_assignment(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"project_assignment": assignment}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def project_assignment_detail(request: HttpRequest, assignment_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="project_assignment",
            entity_id=assignment_id,
            delete_callable=ProjectAssignmentManagementService.delete_assignment,
            blocked_codes={"PROJECT_ASSIGNMENT_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            assignment = ProjectAssignmentManagementService.get_assignment(
                current_user,
                assignment_id,
            )
            return JsonResponse({"project_assignment": assignment})

        payload = parse_json_request(request)
        assignment = ProjectAssignmentManagementService.update_assignment(
            current_user,
            assignment_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"project_assignment": assignment})


@require_http_methods(["GET", "POST"])
def calendar_period_rules_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            period_rules = CalendarPeriodRuleManagementService.list_period_rules(
                current_user,
                status_code=request.GET.get("status"),
            )
            return JsonResponse({"calendar_period_rules": period_rules})

        payload = parse_json_request(request)
        period_rule = CalendarPeriodRuleManagementService.create_period_rule(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"calendar_period_rule": period_rule}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def calendar_period_rule_detail(request: HttpRequest, period_rule_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="calendar_period_rule",
            entity_id=period_rule_id,
            delete_callable=CalendarPeriodRuleManagementService.delete_period_rule,
            blocked_codes={"CALENDAR_PERIOD_RULE_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            period_rule = CalendarPeriodRuleManagementService.get_period_rule(
                current_user,
                period_rule_id,
            )
            return JsonResponse({"calendar_period_rule": period_rule})

        payload = parse_json_request(request)
        period_rule = CalendarPeriodRuleManagementService.update_period_rule(
            current_user,
            period_rule_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"calendar_period_rule": period_rule})


@require_http_methods(["GET", "PATCH", "DELETE"])
def employee_detail(request: HttpRequest, employee_id: int) -> JsonResponse:
    if request.method == "DELETE":
        return _handle_guarded_delete(
            request,
            entity_name="employee",
            entity_id=employee_id,
            delete_callable=EmployeeManagementService.delete_employee,
            blocked_codes={"EMPLOYEE_DELETE_BLOCKED"},
        )
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            employee = EmployeeManagementService.get_employee(current_user, employee_id)
            return JsonResponse({"employee": employee})

        payload = parse_json_request(request)
        employee = EmployeeManagementService.update_employee(current_user, employee_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"employee": employee})


@require_http_methods(["PUT"])
def replace_employee_roles(request: HttpRequest, employee_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        employee = EmployeeManagementService.replace_roles(current_user, employee_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"employee": employee})


@require_http_methods(["PUT"])
def replace_employee_business_units(request: HttpRequest, employee_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        employee = EmployeeManagementService.replace_business_units(
            current_user,
            employee_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"employee": employee})
