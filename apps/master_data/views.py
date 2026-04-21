from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.auth.errors import AuthError
from apps.auth.services import CurrentUserService, error_response, parse_json_request
from apps.master_data.services import EmployeeManagementService


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
