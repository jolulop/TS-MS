import csv

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.auth.services import CurrentUserService, error_response, parse_json_request
from apps.core.reports_views import (
    REPORT_BUILDERS,
    REPORT_DEFINITIONS,
    _audit_missing_timesheets_report,
    _project_missing_timesheet_rows,
    _resolved_project_selection,
    _selected_project_values,
    build_missing_timesheets_export_query,
)


def _missing_timesheets_export_uri(project_ids: list[int]) -> str:
    query = build_missing_timesheets_export_query(project_ids)
    return (
        f"/api/v1/reports/missing-timesheets/export.csv?{query}"
        if query
        else "/api/v1/reports/missing-timesheets/export.csv"
    )


@require_POST
def create_missing_timesheets_export(request: HttpRequest) -> JsonResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if not AuthorizationPolicyService.can_run_report(current_user, "missing-timesheets"):
            raise AuthError(
                "AUTH_ACCESS_DENIED",
                "You do not have permission to create this report export.",
                403,
            )
        payload = parse_json_request(request)
        raw_project_ids = payload.get("project_ids", [])
        if raw_project_ids in (None, ""):
            raw_project_id_values: list[str] = []
        elif not isinstance(raw_project_ids, list):
            raise AuthError(
                "REPORT_INVALID_REQUEST",
                "project_ids must be a JSON array when provided.",
                400,
            )
        else:
            raw_project_id_values = [
                str(project_id).strip() for project_id in raw_project_ids if str(project_id).strip()
            ]

        effective_project_ids, _, _ = _resolved_project_selection(
            current_user,
            raw_project_id_values,
        )
        if raw_project_id_values and not effective_project_ids:
            raise AuthError(
                "REPORT_INVALID_SCOPE",
                "None of the selected projects are available in your report scope.",
                400,
            )
        rows, _, _ = _project_missing_timesheet_rows(current_user, raw_project_id_values)
        selected_project_ids = effective_project_ids if raw_project_id_values else []
        _audit_missing_timesheets_report(
            current_user,
            action_code="CREATE",
            selected_project_ids=selected_project_ids,
            row_count=len(rows),
            reason_prefix="Created project missing timesheets export URI",
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    return JsonResponse(
        {
            "report": {
                "code": REPORT_DEFINITIONS["missing-timesheets"].code,
                "title": REPORT_DEFINITIONS["missing-timesheets"].title,
                "row_count": len(rows),
            },
            "export_uri": _missing_timesheets_export_uri(effective_project_ids),
        },
        status=201,
    )


@require_GET
def download_missing_timesheets_export(request: HttpRequest) -> HttpResponse:
    try:
        current_user = CurrentUserService.get_from_request(request)
        if not AuthorizationPolicyService.can_run_report(current_user, "missing-timesheets"):
            raise AuthError(
                "AUTH_ACCESS_DENIED",
                "You do not have permission to export this report.",
                403,
            )
        report_payload = REPORT_BUILDERS["missing-timesheets"](current_user, request)
        effective_project_ids, _, _ = _resolved_project_selection(
            current_user,
            _selected_project_values(request),
        )
        selected_project_ids = effective_project_ids if _selected_project_values(request) else []
        _audit_missing_timesheets_report(
            current_user,
            action_code="EXPORT",
            selected_project_ids=selected_project_ids,
            row_count=len(report_payload["rows"]),
            reason_prefix="Exported project missing timesheets CSV via API",
        )
    except AuthError as exc:
        return error_response(exc.code, exc.message, exc.status)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="missing-timesheets-api-export.csv"'
    writer = csv.writer(response)
    writer.writerow(report_payload["headers"])
    writer.writerows(report_payload["rows"])
    return response
