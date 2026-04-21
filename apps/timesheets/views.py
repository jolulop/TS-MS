from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from apps.auth.errors import AuthError
from apps.auth.services import CurrentUserService, error_response, parse_json_request
from apps.timesheets.services import TimesheetService


@require_http_methods(["GET", "POST"])
def timesheets_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if request.method == "GET":
            timesheets = TimesheetService.list_timesheets(current_user)
            return JsonResponse({"timesheets": timesheets})

        payload = parse_json_request(request)
        timesheet = TimesheetService.create_timesheet(current_user, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet}, status=201)


@require_http_methods(["GET"])
def timesheet_detail(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        timesheet = TimesheetService.get_timesheet(current_user, timesheet_id)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})


@require_http_methods(["PUT"])
def replace_timesheet_lines(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        timesheet = TimesheetService.replace_lines(current_user, timesheet_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})


@require_http_methods(["POST"])
def submit_timesheet(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        timesheet = TimesheetService.submit_timesheet(current_user, timesheet_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})


@require_http_methods(["POST"])
def withdraw_timesheet(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        timesheet = TimesheetService.withdraw_timesheet(current_user, timesheet_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})


@require_http_methods(["GET"])
def approvals_collection(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        approval_items = TimesheetService.list_approval_items(current_user)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"approval_items": approval_items})


@require_http_methods(["GET"])
def approval_detail(request: HttpRequest, approval_item_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        approval_item = TimesheetService.get_approval_item(current_user, approval_item_id)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"approval_item": approval_item})


@require_http_methods(["POST"])
def approve_approval_item(request: HttpRequest, approval_item_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        approval_item = TimesheetService.approve_approval_item(
            current_user,
            approval_item_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"approval_item": approval_item})


@require_http_methods(["POST"])
def reject_approval_item(request: HttpRequest, approval_item_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        approval_item = TimesheetService.reject_approval_item(
            current_user,
            approval_item_id,
            payload,
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"approval_item": approval_item})


@require_http_methods(["POST"])
def reopen_timesheet(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        timesheet = TimesheetService.reopen_timesheet(current_user, timesheet_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})


@require_http_methods(["POST"])
def archive_timesheet(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        timesheet = TimesheetService.archive_timesheet(current_user, timesheet_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})


@require_http_methods(["POST"])
def restore_timesheet(request: HttpRequest, timesheet_id: int) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        payload = parse_json_request(request)
        timesheet = TimesheetService.restore_timesheet(current_user, timesheet_id, payload)
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse({"timesheet": timesheet})
