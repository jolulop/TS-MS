from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.auth.errors import AuthError
from apps.auth.services import CurrentUserService, error_response, parse_json_request
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


@require_http_methods(["GET", "PATCH"])
def client_detail(request: HttpRequest, client_id: int) -> JsonResponse:
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


@require_http_methods(["GET", "PATCH"])
def internal_category_detail(request: HttpRequest, category_id: int) -> JsonResponse:
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


@require_http_methods(["GET", "PATCH"])
def cost_center_detail(request: HttpRequest, cost_center_id: int) -> JsonResponse:
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


@require_http_methods(["GET", "PATCH"])
def general_charge_code_detail(
    request: HttpRequest,
    general_charge_code_id: int,
) -> JsonResponse:
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


@require_http_methods(["POST"])
def create_employee(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
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


@require_http_methods(["GET", "PATCH"])
def project_detail(request: HttpRequest, project_id: int) -> JsonResponse:
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


@require_http_methods(["GET", "PATCH"])
def project_assignment_detail(request: HttpRequest, assignment_id: int) -> JsonResponse:
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


@require_http_methods(["GET", "PATCH"])
def calendar_period_rule_detail(request: HttpRequest, period_rule_id: int) -> JsonResponse:
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


@require_http_methods(["PATCH"])
def update_employee(request: HttpRequest, employee_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
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
