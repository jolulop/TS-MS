from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.auth.errors import AuthError
from apps.auth.services import CurrentUserService, error_response, parse_json_request
from apps.master_data.services import (
    ClientManagementService,
    CostCenterManagementService,
    EmployeeManagementService,
    GeneralChargeCodeManagementService,
    InternalCategoryManagementService,
)


@require_http_methods(["GET", "POST"])
def clients_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            clients = ClientManagementService.list_clients(current_user)
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
            categories = InternalCategoryManagementService.list_categories(current_user)
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
            cost_centers = CostCenterManagementService.list_cost_centers(current_user)
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
                current_user
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
