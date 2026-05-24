from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.common.approval_scope import (
    approval_item_effective_business_unit,
    ts_admin_visible_approval_items_q,
)
from apps.common.logging import log_workflow_conflict
from apps.common.parsing import parse_iso_date as _parse_iso_date
from apps.common.reference_data import get_ref_value as _ref_value
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    CalendarSpecialDay,
    Employee,
    GeneralChargeCode,
    GeneralChargeCodeApprovalRoleAssignment,
    OfficeConfiguration,
    Project,
)
from apps.master_data.staffing import (
    employee_has_project_staffing_on_date,
    staffed_project_ids_for_employee_window,
)
from apps.timesheets.models import (
    ApprovalAction,
    ApprovalItem,
    ApprovalItemApproverRole,
    TimesheetLine,
    TimesheetLineAttributeValue,
    TimesheetSubmissionCycle,
    WeeklyTimesheet,
)


def _parse_decimal_hours(value: object) -> Decimal:
    try:
        hours = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AuthError(
            "TIMESHEET_INVALID_HOURS",
            "hours must be a valid decimal value.",
            400,
        ) from exc
    if hours <= 0:
        raise AuthError(
            "TIMESHEET_INVALID_HOURS",
            "hours must be greater than zero.",
            400,
        )
    return hours


def _employee_for_current_user(current_user: CurrentUser) -> Employee:
    try:
        return Employee.objects.select_related(
            "primary_business_unit",
            "assigned_calendar",
        ).get(id=current_user.employee_id)
    except Employee.DoesNotExist as exc:
        raise AuthError("EMPLOYEE_NOT_FOUND", "Employee not found.", 404) from exc


def _active_general_charge_code_approval_role_ids_for_employee(employee_id: int) -> set[int]:
    today = date.today()
    return set(
        GeneralChargeCodeApprovalRoleAssignment.objects.filter(
            employee_id=employee_id,
            status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
            valid_from__lte=today,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today))
        .values_list("approval_role_id", flat=True)
    )


def _eligible_general_charge_code_approver_employee_ids(
    general_charge_code: GeneralChargeCode,
    *,
    exclude_employee_id: int | None = None,
) -> set[int]:
    today = date.today()
    approver_mappings = list(
        general_charge_code.approver_roles.select_related(
            "existing_role",
            "approval_role",
            "approval_role__status",
        )
    )
    existing_role_codes = [
        mapping.existing_role.value_code
        for mapping in approver_mappings
        if mapping.existing_role_id is not None
    ]
    ad_hoc_role_ids = [
        mapping.approval_role_id
        for mapping in approver_mappings
        if mapping.approval_role_id is not None
        and mapping.approval_role.status.value_code == "ACTIVE"
    ]

    employee_ids: set[int] = set()
    if existing_role_codes:
        employee_ids.update(
            Employee.objects.filter(
                office_id=general_charge_code.office_id,
                status__domain__domain_code="EMPLOYEE_STATUS",
                status__value_code="ACTIVE",
                role_assignments__role__domain__domain_code="ROLE_CODE",
                role_assignments__role__value_code__in=existing_role_codes,
                role_assignments__status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                role_assignments__status__value_code="ACTIVE",
                role_assignments__valid_from__lte=today,
                role_assignments__valid_to__isnull=True,
            ).values_list("id", flat=True)
        )
    if ad_hoc_role_ids:
        employee_ids.update(
            Employee.objects.filter(
                office_id=general_charge_code.office_id,
                status__domain__domain_code="EMPLOYEE_STATUS",
                status__value_code="ACTIVE",
                general_charge_code_approval_role_assignments__approval_role_id__in=ad_hoc_role_ids,
                general_charge_code_approval_role_assignments__status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                general_charge_code_approval_role_assignments__status__value_code="ACTIVE",
                general_charge_code_approval_role_assignments__valid_from__lte=today,
            )
            .filter(
                Q(general_charge_code_approval_role_assignments__valid_to__isnull=True)
                | Q(general_charge_code_approval_role_assignments__valid_to__gte=today)
            )
            .values_list("id", flat=True)
        )
    if exclude_employee_id is not None:
        employee_ids.discard(exclude_employee_id)
    return employee_ids


def _approval_item_line_ids(approval_item: ApprovalItem) -> list[int]:
    timesheet = approval_item.submission_cycle.weekly_timesheet
    line_filters = Q()
    if approval_item.project_id is not None:
        line_filters = Q(project_id=approval_item.project_id)
    elif approval_item.general_charge_code_id is not None:
        line_filters = Q(general_charge_code_id=approval_item.general_charge_code_id)
    return list(timesheet.lines.filter(line_filters).values_list("id", flat=True))


def _serialize_line(line: TimesheetLine) -> dict:
    return {
        "id": line.id,
        "work_date": line.work_date.isoformat(),
        "hours": str(line.hours),
        "comment_text": line.comment_text,
        "billable_flag": line.billable_flag,
        "approval_state": line.approval_state.value_code if line.approval_state_id else None,
        "project": (
            {
                "id": line.project_id,
                "project_code": line.project.project_code,
                "name": line.project.name,
            }
            if line.project_id is not None
            else None
        ),
        "general_charge_code": (
            {
                "id": line.general_charge_code_id,
                "code": line.general_charge_code.code,
                "name": line.general_charge_code.name,
            }
            if line.general_charge_code_id is not None
            else None
        ),
    }


def _serialize_timesheet(timesheet: WeeklyTimesheet) -> dict:
    return {
        "id": timesheet.id,
        "employee_id": timesheet.employee_id,
        "week_start_date": timesheet.week_start_date.isoformat(),
        "week_end_date": timesheet.week_end_date.isoformat(),
        "status": timesheet.status.value_code,
        "current_submission_no": timesheet.current_submission_no,
        "submission_datetime": (
            timesheet.submission_datetime.isoformat() if timesheet.submission_datetime else None
        ),
        "final_approval_datetime": (
            timesheet.final_approval_datetime.isoformat()
            if timesheet.final_approval_datetime
            else None
        ),
        "archive_eligible_date": (
            timesheet.archive_eligible_date.isoformat() if timesheet.archive_eligible_date else None
        ),
        "period_lock_override_flag": timesheet.period_lock_override_flag,
        "comment_text": timesheet.comment_text,
        "lines": [
            _serialize_line(line) for line in timesheet.lines.all().order_by("work_date", "id")
        ],
    }


def _serialize_timesheet_summary(timesheet: WeeklyTimesheet) -> dict:
    return {
        "id": timesheet.id,
        "week_start_date": timesheet.week_start_date.isoformat(),
        "week_end_date": timesheet.week_end_date.isoformat(),
        "status": timesheet.status.value_code,
        "current_submission_no": timesheet.current_submission_no,
        "submission_datetime": (
            timesheet.submission_datetime.isoformat() if timesheet.submission_datetime else None
        ),
        "final_approval_datetime": (
            timesheet.final_approval_datetime.isoformat()
            if timesheet.final_approval_datetime
            else None
        ),
        "line_count": timesheet.lines.count(),
    }


def _current_monday() -> date:
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


def _first_monday_on_or_after(start_date: date) -> date:
    return start_date + timedelta(days=(7 - start_date.weekday()) % 7)


def _missing_timesheet_summaries(employee: Employee, existing_week_starts: set[date]) -> list[dict]:
    first_week_start = _first_monday_on_or_after(employee.created_at.date())
    current_week_start = _current_monday()
    if first_week_start > current_week_start:
        return []

    missing_summaries: list[dict] = []
    week_start = first_week_start
    while week_start <= current_week_start:
        if week_start not in existing_week_starts:
            missing_summaries.append(
                {
                    "id": None,
                    "week_start_date": week_start.isoformat(),
                    "week_end_date": (week_start + timedelta(days=6)).isoformat(),
                    "status": "Missing",
                    "current_submission_no": 0,
                    "submission_datetime": None,
                    "final_approval_datetime": None,
                    "line_count": 0,
                    "is_missing": True,
                }
            )
        week_start += timedelta(days=7)
    return missing_summaries


def _get_timesheet_for_view(current_user: CurrentUser, timesheet_id: int) -> WeeklyTimesheet:
    try:
        timesheet = (
            WeeklyTimesheet.objects.select_related("employee", "business_unit", "status")
            .prefetch_related("lines__project", "lines__general_charge_code")
            .get(id=timesheet_id)
        )
    except WeeklyTimesheet.DoesNotExist as exc:
        raise AuthError("TIMESHEET_NOT_FOUND", "Timesheet not found.", 404) from exc

    if not AuthorizationPolicyService.can_view_timesheet(current_user, timesheet):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to view this timesheet.",
            403,
        )
    return timesheet


def _timesheet_detail_queryset():
    return WeeklyTimesheet.objects.select_related(
        "employee",
        "business_unit",
        "status",
    ).prefetch_related("lines__project", "lines__general_charge_code")


def _get_timesheet_for_update(current_user: CurrentUser, timesheet_id: int) -> WeeklyTimesheet:
    try:
        timesheet = _timesheet_detail_queryset().select_for_update(of=("self",)).get(
            id=timesheet_id
        )
    except WeeklyTimesheet.DoesNotExist as exc:
        raise AuthError("TIMESHEET_NOT_FOUND", "Timesheet not found.", 404) from exc

    if not AuthorizationPolicyService.can_view_timesheet(current_user, timesheet):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to view this timesheet.",
            403,
        )
    return timesheet


def _validate_week_start_date(week_start_date: date) -> tuple[date, date]:
    if week_start_date.weekday() != 0:
        raise AuthError(
            "TIMESHEET_WEEK_START_INVALID",
            "week_start_date must be a Monday.",
            400,
        )
    return week_start_date, week_start_date + timedelta(days=6)


def _get_project_for_line(employee: Employee, work_date: date, project_id: int) -> Project:
    try:
        project = Project.objects.select_related("status").get(id=project_id)
    except Project.DoesNotExist as exc:
        raise AuthError("PROJECT_NOT_FOUND", "Project not found.", 404) from exc

    if project.status.value_code != "ACTIVE":
        raise AuthError("TIMESHEET_PROJECT_INVALID", "Project is not active.", 400)
    if work_date < project.start_date:
        raise AuthError(
            "TIMESHEET_PROJECT_INVALID", "Project is not active for the work date.", 400
        )
    if project.end_date is not None and work_date > project.end_date:
        raise AuthError(
            "TIMESHEET_PROJECT_INVALID", "Project is not active for the work date.", 400
        )
    if project.close_date is not None and work_date > project.close_date:
        raise AuthError("TIMESHEET_PROJECT_CLOSED", "Closed projects cannot receive new time.", 400)

    if not employee_has_project_staffing_on_date(
        employee_id=employee.id,
        project_id=project.id,
        work_date=work_date,
    ):
        raise AuthError(
            "TIMESHEET_PROJECT_NOT_ASSIGNED",
            "Employee is not assigned to this project for the work date.",
            400,
        )
    return project


def _get_general_charge_code_for_line(
    work_date: date,
    general_charge_code_id: int,
    business_unit_id: int,
) -> GeneralChargeCode:
    try:
        general_charge_code = GeneralChargeCode.objects.select_related("status").get(
            id=general_charge_code_id
        )
    except GeneralChargeCode.DoesNotExist as exc:
        raise AuthError(
            "GENERAL_CHARGE_CODE_NOT_FOUND",
            "General charge code not found.",
            404,
        ) from exc

    if general_charge_code.business_unit_id != business_unit_id:
        raise AuthError(
            "TIMESHEET_GENERAL_CHARGE_CODE_INVALID",
            "General charge code is not available for this timesheet Business Unit.",
            400,
        )
    if general_charge_code.status.value_code != "ACTIVE":
        raise AuthError(
            "TIMESHEET_GENERAL_CHARGE_CODE_INVALID",
            "General charge code is not active.",
            400,
        )
    if work_date < general_charge_code.valid_from:
        raise AuthError(
            "TIMESHEET_GENERAL_CHARGE_CODE_INVALID",
            "General charge code is not valid for the work date.",
            400,
        )
    if general_charge_code.valid_to is not None and work_date > general_charge_code.valid_to:
        raise AuthError(
            "TIMESHEET_GENERAL_CHARGE_CODE_INVALID",
            "General charge code is not valid for the work date.",
            400,
        )
    return general_charge_code


def _period_rule_for_date(
    employee: Employee,
    business_unit_id: int,
    work_date: date,
) -> CalendarPeriodRule:
    if employee.assigned_calendar_id is None:
        raise AuthError(
            "TIMESHEET_CALENDAR_REQUIRED",
            "Employee must have an assigned calendar before saving timesheet lines.",
            400,
        )

    rules = list(
        CalendarPeriodRule.objects.filter(
            yearly_calendar_id=employee.assigned_calendar_id,
            business_unit_id=business_unit_id,
            effective_from__lte=work_date,
            effective_to__gte=work_date,
            status__domain__domain_code="CALENDAR_PERIOD_STATUS",
            status__value_code="ACTIVE",
        ).order_by("effective_from", "id")
    )
    if not rules:
        rules = list(
            CalendarPeriodRule.objects.filter(
                yearly_calendar_id=employee.assigned_calendar_id,
                business_unit_id__isnull=True,
                effective_from__lte=work_date,
                effective_to__gte=work_date,
                status__domain__domain_code="CALENDAR_PERIOD_STATUS",
                status__value_code="ACTIVE",
            ).order_by("effective_from", "id")
        )
    if not rules:
        raise AuthError(
            "TIMESHEET_DAY_LIMIT_NOT_FOUND",
            "No active calendar period rule found for the work date.",
            400,
        )
    if len(rules) > 1:
        raise AuthError(
            "TIMESHEET_DAY_LIMIT_CONFLICT",
            "Multiple calendar period rules match the work date.",
            400,
        )

    return rules[0]


def _is_active_special_day(employee: Employee, work_date: date) -> bool:
    if employee.assigned_calendar_id is None:
        return False
    return CalendarSpecialDay.objects.filter(
        yearly_calendar_id=employee.assigned_calendar_id,
        special_date=work_date,
        status__domain__domain_code="SPECIAL_DAY_STATUS",
        status__value_code="ACTIVE",
    ).exists()


def _is_chargeable_work_date(employee: Employee, business_unit_id: int, work_date: date) -> bool:
    if _is_active_special_day(employee, work_date):
        return False
    if work_date.weekday() < 5:
        return True
    try:
        rule = _period_rule_for_date(employee, business_unit_id, work_date)
    except AuthError as error:
        if error.code == "TIMESHEET_DAY_LIMIT_NOT_FOUND":
            return False
        raise
    if work_date.weekday() == 5:
        return rule.working_on_saturdays_flag
    if work_date.weekday() == 6:
        return rule.working_on_sundays_flag
    return False


def _available_work_dates_for_week(
    employee: Employee,
    business_unit_id: int,
    week_start_date: date,
) -> list[date]:
    return [
        current_day
        for current_day in (week_start_date + timedelta(days=offset) for offset in range(7))
        if _is_chargeable_work_date(employee, business_unit_id, current_day)
    ]


def _daily_limit_for_date(employee: Employee, business_unit_id: int, work_date: date) -> Decimal:
    rule = _period_rule_for_date(employee, business_unit_id, work_date)
    weekday_fields = {
        0: rule.monday_max_hours,
        1: rule.tuesday_max_hours,
        2: rule.wednesday_max_hours,
        3: rule.thursday_max_hours,
        4: rule.friday_max_hours,
        5: rule.saturday_max_hours,
        6: rule.sunday_max_hours,
    }
    return Decimal(weekday_fields[work_date.weekday()])


def _timesheet_line_summary(lines) -> str:
    line_count = 0
    total_hours = Decimal("0.00")
    for line in lines:
        line_count += 1
        total_hours += line["hours"] if isinstance(line, dict) else line.hours
    return f"lines={line_count}; hours={total_hours.quantize(Decimal('0.00'))}"


def _office_configuration_for_business_unit(
    business_unit_id: int,
) -> OfficeConfiguration | None:
    try:
        business_unit = BusinessUnit.objects.select_related(
            "office__configuration__approval_mode"
        ).get(id=business_unit_id)
    except BusinessUnit.DoesNotExist:
        return None
    return getattr(business_unit.office, "configuration", None)


def _copy_previous_week_enabled(business_unit_id: int) -> bool:
    configuration = _office_configuration_for_business_unit(business_unit_id)
    if configuration is None:
        return False
    return bool(configuration.enable_copy_previous_week_flag)


def _approval_mode_code(business_unit_id: int) -> str:
    configuration = _office_configuration_for_business_unit(business_unit_id)
    if configuration is None:
        return "PROJECT"
    return configuration.approval_mode.value_code


def _archive_after_years(business_unit_id: int) -> int:
    configuration = _office_configuration_for_business_unit(business_unit_id)
    if configuration is None:
        return 5
    return configuration.archive_after_years or 5


def _timesheet_cutoff_date(business_unit_id: int) -> date | None:
    configuration = _office_configuration_for_business_unit(business_unit_id)
    if configuration is None:
        return None
    return configuration.timesheet_cutoff_date


def _latest_approved_timesheet_for_copy(
    employee: Employee,
    *,
    before_week_start_date: date,
) -> WeeklyTimesheet | None:
    return (
        WeeklyTimesheet.objects.select_related("status")
        .prefetch_related("lines")
        .filter(
            employee=employee,
            status__value_code="APPROVED",
            week_start_date__lt=before_week_start_date,
        )
        .order_by("-week_start_date", "-id")
        .first()
    )


def _add_years(base_date: date, years: int) -> date:
    try:
        return base_date.replace(year=base_date.year + years)
    except ValueError:
        return base_date.replace(month=2, day=28, year=base_date.year + years)


def _archive_eligible_date_for_timesheet(timesheet: WeeklyTimesheet) -> date:
    if timesheet.archive_eligible_date is not None:
        return timesheet.archive_eligible_date
    return _add_years(timesheet.created_at.date(), _archive_after_years(timesheet.business_unit_id))


def _is_period_locked(timesheet: WeeklyTimesheet) -> bool:
    cutoff_date = _timesheet_cutoff_date(timesheet.business_unit_id)
    if cutoff_date is None:
        return False
    if timesheet.period_lock_override_flag:
        return False
    return timesheet.week_end_date < cutoff_date


def _ensure_period_unlocked(timesheet: WeeklyTimesheet) -> None:
    if _is_period_locked(timesheet):
        raise AuthError(
            "TIMESHEET_PERIOD_LOCKED",
            "This timesheet is in a locked period and requires an administrative override.",
            400,
        )


def _approval_pending_age_days(approval_item: ApprovalItem) -> int:
    reference_datetime = (
        approval_item.submission_cycle.weekly_timesheet.submission_datetime
        or approval_item.created_at
    )
    return max((timezone.now().date() - reference_datetime.date()).days, 0)


def _serialize_approval_item(approval_item: ApprovalItem, *, include_lines: bool = False) -> dict:
    submission_cycle = approval_item.submission_cycle
    timesheet = submission_cycle.weekly_timesheet
    pending_age_days = _approval_pending_age_days(approval_item)
    payload = {
        "id": approval_item.id,
        "submission_cycle_id": submission_cycle.id,
        "submission_no": submission_cycle.submission_no,
        "timesheet_id": timesheet.id,
        "timesheet": {
            "id": timesheet.id,
            "status": timesheet.status.value_code,
            "week_start_date": timesheet.week_start_date.isoformat(),
            "week_end_date": timesheet.week_end_date.isoformat(),
            "submission_datetime": (
                timesheet.submission_datetime.isoformat()
                if timesheet.submission_datetime is not None
                else None
            ),
            "final_approval_datetime": (
                timesheet.final_approval_datetime.isoformat()
                if timesheet.final_approval_datetime is not None
                else None
            ),
        },
        "timesheet_employee": {
            "id": timesheet.employee_id,
            "employee_code": timesheet.employee.employee_code,
            "full_name": timesheet.employee.full_name,
        },
        "business_unit": approval_item_effective_business_unit(approval_item),
        "scope_type": approval_item.scope_type.value_code,
        "status": approval_item.status.value_code,
        "rejection_reason": approval_item.rejection_reason,
        "approver_employee": (
            {
                "id": approval_item.approver_employee_id,
                "employee_code": approval_item.approver_employee.employee_code,
                "full_name": approval_item.approver_employee.full_name,
            }
            if approval_item.approver_employee_id is not None
            else None
        ),
        "pending_age_days": pending_age_days,
        "stalled_flag": approval_item.status.value_code == "PENDING" and pending_age_days >= 7,
        "project": (
            {
                "id": approval_item.project_id,
                "project_code": approval_item.project.project_code,
                "name": approval_item.project.name,
            }
            if approval_item.project_id is not None
            else None
        ),
        "general_charge_code": (
            {
                "id": approval_item.general_charge_code_id,
                "code": approval_item.general_charge_code.code,
                "name": approval_item.general_charge_code.name,
            }
            if approval_item.general_charge_code_id is not None
            else None
        ),
        "approver_roles": [
            (
                {
                    "kind": "EXISTING_ROLE",
                    "code": approver_role.existing_role.value_code,
                    "name": approver_role.existing_role.value_label,
                }
                if approver_role.existing_role_id is not None
                else {
                    "kind": "AD_HOC_ROLE",
                    "code": approver_role.approval_role.role_code,
                    "name": approver_role.approval_role.name,
                }
            )
            for approver_role in approval_item.approver_roles.all()
        ],
    }
    if include_lines:
        lines = timesheet.lines.all().order_by("work_date", "id")
        if approval_item.project_id is not None:
            lines = lines.filter(project_id=approval_item.project_id)
        elif approval_item.general_charge_code_id is not None:
            lines = lines.filter(general_charge_code_id=approval_item.general_charge_code_id)
        payload["lines"] = [_serialize_line(line) for line in lines]
    return payload


def _set_line_approval_state(*, line_ids: list[int], approval_state_code: str | None) -> None:
    if not line_ids:
        return
    approval_state = (
        _ref_value("APPROVAL_STATUS", approval_state_code)
        if approval_state_code is not None
        else None
    )
    TimesheetLine.objects.filter(id__in=line_ids).update(approval_state=approval_state)


def _finalize_approved_timesheet(
    *,
    timesheet: WeeklyTimesheet,
    submission_cycle: TimesheetSubmissionCycle,
    acted_at,
    actor_email: str,
) -> None:
    submission_cycle.cycle_status = _ref_value("SUBMISSION_CYCLE_STATUS", "COMPLETED")
    submission_cycle.outcome_status = _ref_value("APPROVAL_STATUS", "APPROVED")
    submission_cycle.completed_at = acted_at
    submission_cycle.updated_by = actor_email
    submission_cycle.save(
        update_fields=[
            "cycle_status",
            "outcome_status",
            "completed_at",
            "updated_by",
            "updated_at",
        ]
    )

    timesheet.status = _ref_value("TIMESHEET_STATUS", "APPROVED")
    timesheet.final_approval_datetime = acted_at
    timesheet.archive_eligible_date = _archive_eligible_date_for_timesheet(timesheet)
    timesheet.updated_by = actor_email
    timesheet.save(
        update_fields=[
            "status",
            "final_approval_datetime",
            "archive_eligible_date",
            "updated_by",
            "updated_at",
        ]
    )


def _get_approval_item_for_view(current_user: CurrentUser, approval_item_id: int) -> ApprovalItem:
    try:
        approval_item = _approval_item_detail_queryset().get(id=approval_item_id)
    except ApprovalItem.DoesNotExist as exc:
        raise AuthError("APPROVAL_ITEM_NOT_FOUND", "Approval item not found.", 404) from exc

    if not AuthorizationPolicyService.can_view_approval_item(current_user, approval_item):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to view this approval item.",
            403,
        )
    return approval_item


def _approval_item_detail_queryset():
    return ApprovalItem.objects.select_related(
        "scope_type",
        "status",
        "approver_employee",
        "project",
        "project__business_unit",
        "project__office",
        "general_charge_code",
        "submission_cycle",
        "submission_cycle__weekly_timesheet",
        "submission_cycle__weekly_timesheet__employee",
        "submission_cycle__weekly_timesheet__business_unit",
    ).prefetch_related(
        "approver_roles__existing_role",
        "approver_roles__approval_role",
        "submission_cycle__weekly_timesheet__lines__project",
        "submission_cycle__weekly_timesheet__lines__general_charge_code",
    )


def _get_approval_item_for_update(
    current_user: CurrentUser,
    approval_item_id: int,
) -> ApprovalItem:
    try:
        unlocked_item = ApprovalItem.objects.select_related("submission_cycle").get(
            id=approval_item_id
        )
    except ApprovalItem.DoesNotExist as exc:
        raise AuthError("APPROVAL_ITEM_NOT_FOUND", "Approval item not found.", 404) from exc

    WeeklyTimesheet.objects.select_for_update(of=("self",)).get(
        id=unlocked_item.submission_cycle.weekly_timesheet_id
    )
    TimesheetSubmissionCycle.objects.select_for_update(of=("self",)).get(
        id=unlocked_item.submission_cycle_id
    )

    try:
        approval_item = (
            _approval_item_detail_queryset()
            .select_for_update(of=("self",))
            .get(id=approval_item_id)
        )
    except ApprovalItem.DoesNotExist as exc:
        raise AuthError("APPROVAL_ITEM_NOT_FOUND", "Approval item not found.", 404) from exc

    if not AuthorizationPolicyService.can_view_approval_item(current_user, approval_item):
        raise AuthError(
            "AUTH_ACCESS_DENIED",
            "You are not authorized to view this approval item.",
            403,
        )
    return approval_item


def _available_projects_for_week(timesheet: WeeklyTimesheet) -> list[dict]:
    staffed_project_ids = staffed_project_ids_for_employee_window(
        employee_id=timesheet.employee_id,
        week_start_date=timesheet.week_start_date,
        week_end_date=timesheet.week_end_date,
    )
    if not staffed_project_ids:
        return []

    projects = (
        Project.objects.filter(
            id__in=staffed_project_ids,
        )
        .order_by("project_code")
    )
    return [
        {
            "id": project.id,
            "project_code": project.project_code,
            "name": project.name,
        }
        for project in projects
    ]


def _available_general_charge_codes_for_week(timesheet: WeeklyTimesheet) -> list[dict]:
    open_codes = (
        GeneralChargeCode.objects.select_related("charge_type")
        .filter(
            business_unit_id=timesheet.business_unit_id,
            status__domain__domain_code="GENERAL_CHARGE_CODE_STATUS",
            status__value_code="ACTIVE",
            valid_from__lte=timesheet.week_end_date,
            valid_to__isnull=True,
        )
        .order_by("code")
    )
    bounded_codes = (
        GeneralChargeCode.objects.select_related("charge_type")
        .filter(
            business_unit_id=timesheet.business_unit_id,
            status__domain__domain_code="GENERAL_CHARGE_CODE_STATUS",
            status__value_code="ACTIVE",
            valid_from__lte=timesheet.week_end_date,
            valid_to__gte=timesheet.week_start_date,
        )
        .exclude(id__in=open_codes.values_list("id", flat=True))
        .order_by("code")
    )
    return [
        {
            "id": general_charge_code.id,
            "code": general_charge_code.code,
            "name": general_charge_code.name,
            "charge_type": general_charge_code.charge_type.value_code,
        }
        for general_charge_code in list(open_codes) + list(bounded_codes)
    ]


def _submission_blockers(timesheet: WeeklyTimesheet) -> list[str]:
    blockers: list[str] = []
    if not timesheet.lines.exists():
        blockers.append("A timesheet must contain at least one line before submission.")
        return blockers

    if _approval_mode_code(timesheet.business_unit_id) != "PROJECT":
        blockers.append(
            "Only project-scoped approval mode is supported in the current implementation."
        )
        return blockers

    unroutable_general_codes = sorted(
        {
            line.general_charge_code.code
            for line in timesheet.lines.select_related(
                "project",
                "general_charge_code",
            )
            .prefetch_related("general_charge_code__approver_roles__existing_role")
            .all()
            if line.general_charge_code_id is not None
            and line.general_charge_code.requires_approval_flag
            and not _eligible_general_charge_code_approver_employee_ids(
                line.general_charge_code,
                exclude_employee_id=timesheet.employee_id,
            )
        }
    )
    if unroutable_general_codes:
        blockers.append(
            "General charge code approval routing does not currently resolve to any "
            "eligible approver other than the timesheet owner. Update the approver "
            "roles or remove lines charged to: " + ", ".join(unroutable_general_codes) + "."
        )

    for line in timesheet.lines.select_related("project", "general_charge_code").all():
        if (
            line.project_id is not None
            and line.project.project_manager_employee_id == timesheet.employee_id
        ):
            blockers.append(
                "A timesheet cannot be submitted when project approval would route to the "
                "timesheet owner."
            )
            break

    return blockers


def _matching_capacity_period_rule(
    business_unit_rules: list[CalendarPeriodRule],
    fallback_rules: list[CalendarPeriodRule],
    work_date: date,
) -> CalendarPeriodRule | None:
    matching_rules = [
        rule
        for rule in business_unit_rules
        if rule.effective_from <= work_date <= rule.effective_to
    ]
    if not matching_rules:
        matching_rules = [
            rule for rule in fallback_rules if rule.effective_from <= work_date <= rule.effective_to
        ]
    if len(matching_rules) != 1:
        return None
    return matching_rules[0]


def _capacity_hours_for_rule_day(rule: CalendarPeriodRule, work_date: date) -> Decimal:
    weekday = work_date.weekday()
    if weekday == 0:
        return Decimal(rule.monday_max_hours)
    if weekday == 1:
        return Decimal(rule.tuesday_max_hours)
    if weekday == 2:
        return Decimal(rule.wednesday_max_hours)
    if weekday == 3:
        return Decimal(rule.thursday_max_hours)
    if weekday == 4:
        return Decimal(rule.friday_max_hours)
    if weekday == 5 and rule.working_on_saturdays_flag:
        return Decimal(rule.saturday_max_hours)
    if weekday == 6 and rule.working_on_sundays_flag:
        return Decimal(rule.sunday_max_hours)
    return Decimal("0.00")


class TimesheetService:
    @staticmethod
    def expected_capacity_hours(
        employee: Employee,
        business_unit_id: int,
        start_date: date,
        end_date: date,
    ) -> Decimal:
        return TimesheetService.expected_capacity_hours_by_employee(
            [employee],
            start_date,
            end_date,
            business_unit_id_by_employee={employee.id: business_unit_id},
        ).get(employee.id, Decimal("0.00"))

    @staticmethod
    def expected_capacity_hours_by_employee(
        employees: list[Employee],
        start_date: date,
        end_date: date,
        *,
        business_unit_id_by_employee: dict[int, int] | None = None,
    ) -> dict[int, Decimal]:
        totals = {employee.id: Decimal("0.00") for employee in employees}
        if end_date < start_date or not employees:
            return totals

        business_unit_ids_by_employee = business_unit_id_by_employee or {
            employee.id: employee.primary_business_unit_id for employee in employees
        }
        calendar_ids = {
            employee.assigned_calendar_id
            for employee in employees
            if employee.assigned_calendar_id is not None
        }
        business_unit_ids = {
            business_unit_id
            for business_unit_id in business_unit_ids_by_employee.values()
            if business_unit_id is not None
        }
        if not calendar_ids or not business_unit_ids:
            return totals

        active_special_days = set(
            CalendarSpecialDay.objects.filter(
                yearly_calendar_id__in=calendar_ids,
                special_date__gte=start_date,
                special_date__lte=end_date,
                status__domain__domain_code="SPECIAL_DAY_STATUS",
                status__value_code="ACTIVE",
            ).values_list("yearly_calendar_id", "special_date")
        )
        period_rules = CalendarPeriodRule.objects.filter(
            yearly_calendar_id__in=calendar_ids,
            effective_from__lte=end_date,
            effective_to__gte=start_date,
            status__domain__domain_code="CALENDAR_PERIOD_STATUS",
            status__value_code="ACTIVE",
        ).filter(Q(business_unit_id__in=business_unit_ids) | Q(business_unit_id__isnull=True))
        rules_by_calendar_and_bu: dict[tuple[int, int], list[CalendarPeriodRule]] = defaultdict(
            list
        )
        fallback_rules_by_calendar: dict[int, list[CalendarPeriodRule]] = defaultdict(list)
        for rule in period_rules.order_by("effective_from", "id"):
            if rule.business_unit_id is None:
                fallback_rules_by_calendar[rule.yearly_calendar_id].append(rule)
            else:
                rules_by_calendar_and_bu[(rule.yearly_calendar_id, rule.business_unit_id)].append(
                    rule
                )

        for employee in employees:
            if employee.assigned_calendar_id is None:
                continue
            business_unit_id = business_unit_ids_by_employee.get(employee.id)
            if business_unit_id is None:
                continue
            current_day = start_date
            if employee.employment_start_date and employee.employment_start_date > current_day:
                current_day = employee.employment_start_date
            last_day = end_date
            if employee.employment_end_date and employee.employment_end_date < last_day:
                last_day = employee.employment_end_date
            while current_day <= last_day:
                if (employee.assigned_calendar_id, current_day) not in active_special_days:
                    rule = _matching_capacity_period_rule(
                        rules_by_calendar_and_bu.get(
                            (employee.assigned_calendar_id, business_unit_id),
                            [],
                        ),
                        fallback_rules_by_calendar.get(employee.assigned_calendar_id, []),
                        current_day,
                    )
                    if rule is not None:
                        totals[employee.id] += _capacity_hours_for_rule_day(rule, current_day)
                current_day += timedelta(days=1)
        return totals

    @staticmethod
    def can_copy_previous_week(current_user: CurrentUser) -> bool:
        employee = _employee_for_current_user(current_user)
        return _copy_previous_week_enabled(employee.primary_business_unit_id)

    @staticmethod
    def list_timesheets(current_user: CurrentUser) -> list[dict]:
        employee = _employee_for_current_user(current_user)
        timesheets = (
            WeeklyTimesheet.objects.select_related("status")
            .prefetch_related("lines")
            .filter(employee_id=current_user.employee_id)
            .order_by("-week_start_date", "id")
        )
        summaries = [_serialize_timesheet_summary(timesheet) for timesheet in timesheets]
        existing_week_starts = {timesheet.week_start_date for timesheet in timesheets}
        summaries.extend(_missing_timesheet_summaries(employee, existing_week_starts))
        summaries.sort(key=lambda item: item["week_start_date"], reverse=True)
        return summaries

    @staticmethod
    def get_timesheet_editor_context(current_user: CurrentUser, timesheet_id: int) -> dict:
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
        employee = _employee_for_current_user(current_user)
        submit_blockers = _submission_blockers(timesheet)
        return {
            "timesheet": _serialize_timesheet(timesheet),
            "employee": {
                "id": employee.id,
                "employee_code": employee.employee_code,
                "full_name": employee.full_name,
                "assigned_calendar": (
                    employee.assigned_calendar.calendar_name if employee.assigned_calendar else ""
                ),
            },
            "available_projects": _available_projects_for_week(timesheet),
            "available_general_charge_codes": _available_general_charge_codes_for_week(timesheet),
            "available_work_dates": [
                work_date.isoformat()
                for work_date in _available_work_dates_for_week(
                    employee,
                    timesheet.business_unit_id,
                    timesheet.week_start_date,
                )
            ],
            "can_edit": AuthorizationPolicyService.can_edit_timesheet(current_user, timesheet),
            "can_submit": AuthorizationPolicyService.can_submit_timesheet(current_user, timesheet)
            and not submit_blockers,
            "can_withdraw": AuthorizationPolicyService.can_withdraw_timesheet(
                current_user, timesheet
            ),
            "can_delete": AuthorizationPolicyService.can_delete_timesheet(current_user, timesheet),
            "can_reopen": AuthorizationPolicyService.can_reopen_timesheet(current_user, timesheet),
            "can_admin_withdraw": AuthorizationPolicyService.can_admin_withdraw_timesheet(
                current_user, timesheet
            ),
            "can_archive": AuthorizationPolicyService.can_archive_timesheet(
                current_user, timesheet
            ),
            "can_restore": AuthorizationPolicyService.can_restore_timesheet(
                current_user, timesheet
            ),
            "submit_blockers": submit_blockers,
        }

    @staticmethod
    @transaction.atomic
    def create_timesheet(current_user: CurrentUser, payload: dict) -> dict:
        employee = _employee_for_current_user(current_user)
        copy_previous_week_raw = payload.get("copy_previous_week")
        copy_previous_week_flag = copy_previous_week_raw in (
            True,
            "true",
            "True",
            "1",
            1,
            "on",
        )
        week_start_date = _parse_iso_date(
            payload.get("week_start_date"),
            code="TIMESHEET_WEEK_START_REQUIRED",
            message="week_start_date must be a valid ISO date.",
        )
        week_start_date, week_end_date = _validate_week_start_date(week_start_date)

        source_timesheet = None
        if copy_previous_week_flag:
            if not _copy_previous_week_enabled(employee.primary_business_unit_id):
                raise AuthError(
                    "TIMESHEET_COPY_PREVIOUS_WEEK_DISABLED",
                    "Copy previous week is not enabled for your Office.",
                    400,
                )
            source_timesheet = _latest_approved_timesheet_for_copy(
                employee,
                before_week_start_date=week_start_date,
            )
            if source_timesheet is None:
                raise AuthError(
                    "TIMESHEET_COPY_PREVIOUS_WEEK_SOURCE_NOT_FOUND",
                    "No approved previous timesheet is available to copy.",
                    400,
                )

        try:
            timesheet = WeeklyTimesheet.objects.create(
                employee=employee,
                business_unit=employee.primary_business_unit,
                week_start_date=week_start_date,
                week_end_date=week_end_date,
                status=_ref_value("TIMESHEET_STATUS", "CREATED"),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "TIMESHEET_ALREADY_EXISTS",
                "A weekly timesheet already exists for that week.",
                400,
            ) from exc

        if source_timesheet is not None:
            day_offset = (week_start_date - source_timesheet.week_start_date).days
            copied_lines_payload = [
                {
                    "work_date": (line.work_date + timedelta(days=day_offset)).isoformat(),
                    "project_id": line.project_id,
                    "general_charge_code_id": line.general_charge_code_id,
                    "hours": str(line.hours),
                    "comment_text": line.comment_text,
                }
                for line in source_timesheet.lines.all().order_by("work_date", "id")
            ]
            TimesheetService.replace_lines(
                current_user,
                timesheet.id,
                {"lines": copied_lines_payload},
            )

        return _serialize_timesheet(
            WeeklyTimesheet.objects.select_related("status")
            .prefetch_related("lines")
            .get(id=timesheet.id)
        )

    @staticmethod
    def get_timesheet(current_user: CurrentUser, timesheet_id: int) -> dict:
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
        return _serialize_timesheet(timesheet)

    @staticmethod
    @transaction.atomic
    def replace_lines(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_edit_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_NOT_EDITABLE",
                "This timesheet is not editable.",
                400,
            )
        _ensure_period_unlocked(timesheet)

        employee = _employee_for_current_user(current_user)
        raw_lines = payload.get("lines", [])
        if not isinstance(raw_lines, list):
            raise AuthError("TIMESHEET_LINES_INVALID", "lines must be a JSON array.", 400)

        normalized_lines: list[dict] = []
        hours_by_date: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))

        for raw_line in raw_lines:
            if not isinstance(raw_line, dict):
                raise AuthError(
                    "TIMESHEET_LINES_INVALID",
                    "Each timesheet line must be a JSON object.",
                    400,
                )

            work_date = _parse_iso_date(
                raw_line.get("work_date"),
                code="TIMESHEET_WORK_DATE_REQUIRED",
                message="work_date must be a valid ISO date.",
            )
            if (
                work_date < timesheet.week_start_date
                or work_date > timesheet.week_start_date + timedelta(days=6)
            ):
                raise AuthError(
                    "TIMESHEET_WORK_DATE_OUT_OF_RANGE",
                    "work_date must be inside the weekly timesheet window.",
                    400,
                )
            if _is_active_special_day(employee, work_date):
                raise AuthError(
                    "TIMESHEET_NON_WORKING_DAY",
                    (
                        "Special Day entries are non-working and cannot receive "
                        "standard timesheet time."
                    ),
                    400,
                )
            if not _is_chargeable_work_date(employee, timesheet.business_unit_id, work_date):
                raise AuthError(
                    "TIMESHEET_WEEKEND_NOT_ALLOWED",
                    (
                        "Weekend entry is not allowed unless the active Calendar "
                        "Period Rule marks that day as working."
                    ),
                    400,
                )

            project_id = raw_line.get("project_id")
            general_charge_code_id = raw_line.get("general_charge_code_id")
            if bool(project_id) == bool(general_charge_code_id):
                raise AuthError(
                    "TIMESHEET_CHARGE_TARGET_INVALID",
                    "Each line must target exactly one project or one general charge code.",
                    400,
                )

            project = None
            general_charge_code = None
            billable_flag = False
            if project_id:
                project = _get_project_for_line(
                    employee,
                    work_date,
                    int(project_id),
                )
                billable_flag = project.billable_flag
            else:
                general_charge_code = _get_general_charge_code_for_line(
                    work_date,
                    int(general_charge_code_id),
                    timesheet.business_unit_id,
                )
                billable_flag = general_charge_code.billable_flag

            hours = _parse_decimal_hours(raw_line.get("hours"))
            hours_by_date[work_date] += hours
            normalized_lines.append(
                {
                    "work_date": work_date,
                    "project": project,
                    "general_charge_code": general_charge_code,
                    "hours": hours,
                    "comment_text": str(raw_line.get("comment_text", "")).strip(),
                    "billable_flag": billable_flag,
                }
            )

        for work_date, hours in hours_by_date.items():
            max_hours = _daily_limit_for_date(employee, timesheet.business_unit_id, work_date)
            if hours > max_hours:
                raise AuthError(
                    "TIMESHEET_DAILY_LIMIT_EXCEEDED",
                    f"Daily hours exceed the calendar limit for {work_date.isoformat()}.",
                    400,
                )

        existing_line_summary = _timesheet_line_summary(timesheet.lines.all())
        timesheet.lines.all().delete()
        for normalized_line in normalized_lines:
            TimesheetLine.objects.create(
                weekly_timesheet=timesheet,
                work_date=normalized_line["work_date"],
                project=normalized_line["project"],
                general_charge_code=normalized_line["general_charge_code"],
                hours=normalized_line["hours"],
                comment_text=normalized_line["comment_text"],
                billable_flag=normalized_line["billable_flag"],
                created_by=current_user.email,
                updated_by=current_user.email,
            )

        replacement_line_summary = _timesheet_line_summary(normalized_lines)
        write_audit_event(
            action_code="UPDATE",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=timesheet.employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            field_name="lines",
            old_value=existing_line_summary,
            new_value=replacement_line_summary,
            reason_text="Timesheet lines replaced.",
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def submit_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_submit_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_SUBMIT_NOT_ALLOWED",
                "This timesheet cannot be submitted in its current state.",
                400,
            )
        _ensure_period_unlocked(timesheet)
        if not timesheet.lines.exists():
            raise AuthError(
                "TIMESHEET_SUBMIT_EMPTY",
                "A timesheet must contain at least one line before submission.",
                400,
            )

        submitted_at = timezone.now()
        next_submission_no = timesheet.current_submission_no + 1
        comment_text = str(payload.get("comment_text", "")).strip()

        timesheet.status = _ref_value("TIMESHEET_STATUS", "SUBMITTED")
        timesheet.current_submission_no = next_submission_no
        timesheet.submission_datetime = submitted_at
        if comment_text:
            timesheet.comment_text = comment_text
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "current_submission_no",
                "submission_datetime",
                "comment_text",
                "updated_by",
                "updated_at",
            ]
        )

        submission_cycle = TimesheetSubmissionCycle.objects.create(
            weekly_timesheet=timesheet,
            submission_no=next_submission_no,
            submitted_by_employee_id=current_user.employee_id,
            submitted_at=submitted_at,
            cycle_status=_ref_value("SUBMISSION_CYCLE_STATUS", "OPEN"),
            outcome_status=_ref_value("APPROVAL_STATUS", "PENDING"),
            created_by=current_user.email,
            updated_by=current_user.email,
        )

        approval_mode_code = _approval_mode_code(timesheet.business_unit_id)
        if approval_mode_code != "PROJECT":
            raise AuthError(
                "TIMESHEET_APPROVAL_MODE_NOT_SUPPORTED",
                "Only project-scoped approval mode is supported in the current implementation.",
                400,
            )

        project_line_ids_by_project_id: dict[int, list[int]] = defaultdict(list)
        general_charge_code_line_ids_by_code_id: dict[int, list[int]] = defaultdict(list)
        auto_approved_line_ids: list[int] = []
        project_map: dict[int, Project] = {}
        general_charge_code_map: dict[int, GeneralChargeCode] = {}

        for line in timesheet.lines.select_related("project", "general_charge_code").all():
            if line.project_id is not None:
                if line.project.project_manager_employee_id == timesheet.employee_id:
                    raise AuthError(
                        "TIMESHEET_SELF_APPROVAL_NOT_ALLOWED",
                        (
                            "A timesheet cannot be submitted when project approval "
                            "would route to the timesheet owner."
                        ),
                        400,
                    )
                project_line_ids_by_project_id[line.project_id].append(line.id)
                project_map[line.project_id] = line.project
                continue

            if line.general_charge_code.requires_approval_flag:
                general_charge_code_line_ids_by_code_id[line.general_charge_code_id].append(line.id)
                general_charge_code_map[line.general_charge_code_id] = line.general_charge_code
                continue
            auto_approved_line_ids.append(line.id)

        unroutable_general_codes = sorted(
            general_charge_code.code
            for general_charge_code in general_charge_code_map.values()
            if not _eligible_general_charge_code_approver_employee_ids(
                general_charge_code,
                exclude_employee_id=timesheet.employee_id,
            )
        )
        if unroutable_general_codes:
            raise AuthError(
                "TIMESHEET_GENERAL_CODE_APPROVER_NOT_AVAILABLE",
                (
                    "General charge code approval routing does not currently resolve "
                    "to any eligible approver other than the timesheet owner for: "
                    + ", ".join(unroutable_general_codes)
                    + "."
                ),
                400,
            )

        _set_line_approval_state(
            line_ids=[
                line_id
                for project_line_ids in project_line_ids_by_project_id.values()
                for line_id in project_line_ids
            ],
            approval_state_code="PENDING",
        )
        _set_line_approval_state(
            line_ids=[
                line_id
                for general_charge_code_line_ids in general_charge_code_line_ids_by_code_id.values()
                for line_id in general_charge_code_line_ids
            ],
            approval_state_code="PENDING",
        )
        _set_line_approval_state(line_ids=auto_approved_line_ids, approval_state_code="APPROVED")

        for project_id in project_line_ids_by_project_id:
            project = project_map[project_id]
            ApprovalItem.objects.create(
                submission_cycle=submission_cycle,
                scope_type=_ref_value("APPROVAL_SCOPE_TYPE", "PROJECT"),
                approver_employee=project.project_manager_employee,
                project=project,
                status=_ref_value("APPROVAL_STATUS", "PENDING"),
                created_by=current_user.email,
                updated_by=current_user.email,
            )

        for general_charge_code_id in sorted(general_charge_code_line_ids_by_code_id):
            general_charge_code = general_charge_code_map[general_charge_code_id]
            approval_item = ApprovalItem.objects.create(
                submission_cycle=submission_cycle,
                scope_type=_ref_value("APPROVAL_SCOPE_TYPE", "GENERAL_CODE"),
                approver_employee=None,
                general_charge_code=general_charge_code,
                status=_ref_value("APPROVAL_STATUS", "PENDING"),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
            for mapping in general_charge_code.approver_roles.select_related(
                "existing_role",
                "approval_role",
            ):
                ApprovalItemApproverRole.objects.create(
                    approval_item=approval_item,
                    existing_role=mapping.existing_role,
                    approval_role=mapping.approval_role,
                    created_by=current_user.email,
                    updated_by=current_user.email,
                )
            write_audit_event(
                action_code="CREATE",
                entity_name="approval_item",
                entity_id=approval_item.id,
                actor_employee=timesheet.employee,
                actor_email=current_user.email,
                business_unit=timesheet.business_unit,
                reason_text=(
                    "General Charge Code approval item created during timesheet submission."
                ),
            )

        write_audit_event(
            action_code="SUBMIT",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=timesheet.employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Timesheet submitted by employee.",
        )

        if not project_line_ids_by_project_id and not general_charge_code_line_ids_by_code_id:
            _finalize_approved_timesheet(
                timesheet=timesheet,
                submission_cycle=submission_cycle,
                acted_at=submitted_at,
                actor_email=current_user.email,
            )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def withdraw_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_withdraw_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_WITHDRAW_NOT_ALLOWED",
                "This timesheet cannot be withdrawn in its current state.",
                400,
            )

        try:
            submission_cycle = timesheet.submission_cycles.select_for_update().select_related(
                "cycle_status",
                "outcome_status",
            ).get(submission_no=timesheet.current_submission_no)
        except TimesheetSubmissionCycle.DoesNotExist as exc:
            raise AuthError(
                "TIMESHEET_SUBMISSION_CYCLE_NOT_FOUND",
                "Active submission cycle not found for this timesheet.",
                400,
            ) from exc

        withdrawn_at = timezone.now()
        comment_text = str(payload.get("comment_text", "")).strip()

        submission_cycle.approval_items.filter(status__value_code="PENDING").update(
            status=_ref_value("APPROVAL_STATUS", "CANCELLED"),
            updated_by=current_user.email,
        )
        _set_line_approval_state(
            line_ids=list(timesheet.lines.values_list("id", flat=True)),
            approval_state_code=None,
        )

        submission_cycle.cycle_status = _ref_value("SUBMISSION_CYCLE_STATUS", "COMPLETED")
        submission_cycle.outcome_status = _ref_value("APPROVAL_STATUS", "CANCELLED")
        submission_cycle.completed_at = withdrawn_at
        submission_cycle.updated_by = current_user.email
        submission_cycle.save(
            update_fields=[
                "cycle_status",
                "outcome_status",
                "completed_at",
                "updated_by",
                "updated_at",
            ]
        )

        timesheet.status = _ref_value("TIMESHEET_STATUS", "CREATED")
        timesheet.submission_datetime = None
        if comment_text:
            timesheet.comment_text = comment_text
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "submission_datetime",
                "comment_text",
                "updated_by",
                "updated_at",
            ]
        )

        write_audit_event(
            action_code="WITHDRAW",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=timesheet.employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Timesheet withdrawn by employee.",
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def delete_timesheet(current_user: CurrentUser, timesheet_id: int) -> None:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_delete_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_DELETE_NOT_ALLOWED",
                "This timesheet cannot be deleted in its current state.",
                400,
            )
        if timesheet.submission_cycles.exists():
            raise AuthError(
                "TIMESHEET_DELETE_BLOCKED",
                "This timesheet cannot be deleted because it already has submission history.",
                400,
            )

        timesheet_id_value = timesheet.id
        timesheet_label = (
            f"{timesheet.employee.employee_code} week {timesheet.week_start_date.isoformat()}"
        )
        TimesheetLineAttributeValue.objects.filter(
            timesheet_line__weekly_timesheet=timesheet
        ).delete()
        timesheet.lines.all().delete()

        try:
            timesheet.delete()
        except ProtectedError as exc:
            raise AuthError(
                "TIMESHEET_DELETE_BLOCKED",
                (
                    "This timesheet cannot be deleted because other protected "
                    "records still reference it."
                ),
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="weekly_timesheet",
            entity_id=timesheet_id_value,
            actor_employee=timesheet.employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            old_value=timesheet_label,
            reason_text="Draft timesheet deleted by employee.",
        )

    @staticmethod
    def list_approval_items(current_user: CurrentUser) -> list[dict]:
        if not AuthorizationPolicyService.can_access_approval_worklist(current_user):
            raise AuthError(
                "AUTH_ACCESS_DENIED",
                "You are not authorized to view approval items.",
                403,
            )

        approval_items = ApprovalItem.objects.select_related(
            "scope_type",
            "status",
            "project",
            "project__business_unit",
            "project__office",
            "approver_employee",
            "general_charge_code",
            "submission_cycle",
            "submission_cycle__weekly_timesheet",
            "submission_cycle__weekly_timesheet__employee",
            "submission_cycle__weekly_timesheet__business_unit",
        ).prefetch_related(
            "approver_roles__existing_role",
            "approver_roles__approval_role",
        )
        if current_user.is_ts_admin:
            approval_items = approval_items.filter(ts_admin_visible_approval_items_q(current_user))
        else:
            active_ad_hoc_role_ids = _active_general_charge_code_approval_role_ids_for_employee(
                current_user.employee_id
            )
            approval_items = approval_items.filter(
                Q(approver_employee_id=current_user.employee_id)
                | Q(project__project_owner_employee_id=current_user.employee_id)
                | Q(
                    general_charge_code_id__isnull=False,
                    approver_roles__existing_role__value_code__in=current_user.role_codes,
                )
                | Q(
                    general_charge_code_id__isnull=False,
                    approver_roles__approval_role_id__in=active_ad_hoc_role_ids,
                )
            )
        approval_items = approval_items.distinct().order_by(
            "status__sort_order",
            "submission_cycle__weekly_timesheet__week_start_date",
            "id",
        )
        return [_serialize_approval_item(item) for item in approval_items]

    @staticmethod
    def get_approval_item(current_user: CurrentUser, approval_item_id: int) -> dict:
        approval_item = _get_approval_item_for_view(current_user, approval_item_id)
        return _serialize_approval_item(approval_item, include_lines=True)

    @staticmethod
    @transaction.atomic
    def approve_approval_item(
        current_user: CurrentUser,
        approval_item_id: int,
        payload: dict,
    ) -> dict:
        approval_item = _get_approval_item_for_update(current_user, approval_item_id)
        if not AuthorizationPolicyService.can_approve_approval_item(current_user, approval_item):
            log_workflow_conflict(
                code="APPROVAL_ACTION_NOT_ALLOWED",
                message="This approval item cannot be approved by the current user.",
                actor_email=current_user.email,
                entity_name="approval_item",
                entity_id=approval_item.id,
            )
            raise AuthError(
                "APPROVAL_ACTION_NOT_ALLOWED",
                "This approval item cannot be approved by the current user.",
                400,
            )

        acted_at = timezone.now()
        comment_text = str(payload.get("comment_text", "")).strip()
        submission_cycle = approval_item.submission_cycle
        timesheet = submission_cycle.weekly_timesheet
        actor_employee = _employee_for_current_user(current_user)

        approval_item.status = _ref_value("APPROVAL_STATUS", "APPROVED")
        approval_item.rejection_reason = ""
        approval_item.updated_by = current_user.email
        approval_item.save(update_fields=["status", "rejection_reason", "updated_by", "updated_at"])

        ApprovalAction.objects.create(
            approval_item=approval_item,
            action_type=_ref_value("APPROVAL_ACTION_TYPE", "APPROVE"),
            acted_by_employee_id=current_user.employee_id,
            action_timestamp=acted_at,
            comment_text=comment_text,
            created_by=current_user.email,
        )

        _set_line_approval_state(
            line_ids=_approval_item_line_ids(approval_item),
            approval_state_code="APPROVED",
        )

        write_audit_event(
            action_code="APPROVE",
            entity_name="approval_item",
            entity_id=approval_item.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Approval completed.",
        )

        if not submission_cycle.approval_items.exclude(status__value_code="APPROVED").exists():
            _finalize_approved_timesheet(
                timesheet=timesheet,
                submission_cycle=submission_cycle,
                acted_at=acted_at,
                actor_email=current_user.email,
            )
            write_audit_event(
                action_code="APPROVE",
                entity_name="weekly_timesheet",
                entity_id=timesheet.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                business_unit=timesheet.business_unit,
                reason_text="All required approvals completed.",
            )

        return TimesheetService.get_approval_item(current_user, approval_item.id)

    @staticmethod
    @transaction.atomic
    def reject_approval_item(
        current_user: CurrentUser,
        approval_item_id: int,
        payload: dict,
    ) -> dict:
        approval_item = _get_approval_item_for_update(current_user, approval_item_id)
        if not AuthorizationPolicyService.can_reject_approval_item(current_user, approval_item):
            log_workflow_conflict(
                code="APPROVAL_ACTION_NOT_ALLOWED",
                message="This approval item cannot be rejected by the current user.",
                actor_email=current_user.email,
                entity_name="approval_item",
                entity_id=approval_item.id,
            )
            raise AuthError(
                "APPROVAL_ACTION_NOT_ALLOWED",
                "This approval item cannot be rejected by the current user.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        if not reason_text:
            log_workflow_conflict(
                code="APPROVAL_REJECTION_REASON_REQUIRED",
                message="A rejection reason is required.",
                actor_email=current_user.email,
                entity_name="approval_item",
                entity_id=approval_item.id,
            )
            raise AuthError(
                "APPROVAL_REJECTION_REASON_REQUIRED",
                "A rejection reason is required.",
                400,
            )

        acted_at = timezone.now()
        submission_cycle = approval_item.submission_cycle
        timesheet = submission_cycle.weekly_timesheet
        actor_employee = _employee_for_current_user(current_user)

        approval_item.status = _ref_value("APPROVAL_STATUS", "REJECTED")
        approval_item.rejection_reason = reason_text
        approval_item.updated_by = current_user.email
        approval_item.save(update_fields=["status", "rejection_reason", "updated_by", "updated_at"])

        ApprovalAction.objects.create(
            approval_item=approval_item,
            action_type=_ref_value("APPROVAL_ACTION_TYPE", "REJECT"),
            acted_by_employee_id=current_user.employee_id,
            action_timestamp=acted_at,
            comment_text=reason_text,
            created_by=current_user.email,
        )

        submission_cycle.approval_items.filter(status__value_code="PENDING").exclude(
            id=approval_item.id
        ).update(
            status=_ref_value("APPROVAL_STATUS", "CANCELLED"),
            updated_by=current_user.email,
        )

        _set_line_approval_state(
            line_ids=_approval_item_line_ids(approval_item),
            approval_state_code="REJECTED",
        )

        submission_cycle.cycle_status = _ref_value("SUBMISSION_CYCLE_STATUS", "COMPLETED")
        submission_cycle.outcome_status = _ref_value("APPROVAL_STATUS", "REJECTED")
        submission_cycle.completed_at = acted_at
        submission_cycle.updated_by = current_user.email
        submission_cycle.save(
            update_fields=[
                "cycle_status",
                "outcome_status",
                "completed_at",
                "updated_by",
                "updated_at",
            ]
        )

        timesheet.status = _ref_value("TIMESHEET_STATUS", "REJECTED")
        timesheet.final_approval_datetime = None
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "final_approval_datetime",
                "updated_by",
                "updated_at",
            ]
        )

        write_audit_event(
            action_code="REJECT",
            entity_name="approval_item",
            entity_id=approval_item.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text=reason_text,
        )
        write_audit_event(
            action_code="REJECT",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Timesheet rejected after approval action.",
        )

        return TimesheetService.get_approval_item(current_user, approval_item.id)

    @staticmethod
    @transaction.atomic
    def reopen_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_reopen_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_REOPEN_NOT_ALLOWED",
                "This timesheet cannot be reopened by the current user.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        if not reason_text:
            raise AuthError(
                "TIMESHEET_REOPEN_REASON_REQUIRED",
                "A reopen reason is required.",
                400,
            )

        actor_employee = _employee_for_current_user(current_user)

        timesheet.status = _ref_value("TIMESHEET_STATUS", "CREATED")
        timesheet.submission_datetime = None
        timesheet.final_approval_datetime = None
        timesheet.archive_eligible_date = None
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "submission_datetime",
                "final_approval_datetime",
                "archive_eligible_date",
                "updated_by",
                "updated_at",
            ]
        )

        _set_line_approval_state(
            line_ids=list(timesheet.lines.values_list("id", flat=True)),
            approval_state_code=None,
        )

        write_audit_event(
            action_code="REOPEN",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text=reason_text,
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def admin_withdraw_timesheet(
        current_user: CurrentUser,
        timesheet_id: int,
        payload: dict,
    ) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_admin_withdraw_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_ADMIN_WITHDRAW_NOT_ALLOWED",
                "This timesheet cannot be withdrawn by the current user.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        if not reason_text:
            raise AuthError(
                "TIMESHEET_WITHDRAW_REASON_REQUIRED",
                "A withdrawal reason is required.",
                400,
            )

        actor_employee = _employee_for_current_user(current_user)

        timesheet.status = _ref_value("TIMESHEET_STATUS", "SUBMITTED")
        timesheet.final_approval_datetime = None
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "final_approval_datetime",
                "updated_by",
                "updated_at",
            ]
        )

        write_audit_event(
            action_code="WITHDRAW",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text=reason_text,
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def override_period_lock(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_override_period_lock(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_PERIOD_OVERRIDE_NOT_ALLOWED",
                "This timesheet period lock cannot be overridden by the current user.",
                400,
            )
        if not _timesheet_cutoff_date(timesheet.business_unit_id):
            raise AuthError(
                "TIMESHEET_PERIOD_LOCK_NOT_CONFIGURED",
                "No Business Unit cutoff date is configured for this timesheet.",
                400,
            )
        if not _is_period_locked(timesheet):
            raise AuthError(
                "TIMESHEET_PERIOD_NOT_LOCKED",
                "This timesheet is not currently in a locked period.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        if not reason_text:
            raise AuthError(
                "TIMESHEET_PERIOD_OVERRIDE_REASON_REQUIRED",
                "A period lock override reason is required.",
                400,
            )

        actor_employee = _employee_for_current_user(current_user)
        timesheet.period_lock_override_flag = True
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "period_lock_override_flag",
                "updated_by",
                "updated_at",
            ]
        )

        write_audit_event(
            action_code="UPDATE",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            field_name="period_lock_override_flag",
            old_value="false",
            new_value="true",
            reason_text=reason_text,
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def archive_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_archive_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_ARCHIVE_NOT_ALLOWED",
                "This timesheet cannot be archived by the current user.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        archive_eligible_date = _archive_eligible_date_for_timesheet(timesheet)
        if archive_eligible_date > timezone.localdate():
            raise AuthError(
                "TIMESHEET_NOT_ARCHIVE_ELIGIBLE",
                "This timesheet is not yet archive eligible.",
                400,
            )

        actor_employee = _employee_for_current_user(current_user)

        timesheet.status = _ref_value("TIMESHEET_STATUS", "ARCHIVED")
        timesheet.archive_eligible_date = archive_eligible_date
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "archive_eligible_date",
                "updated_by",
                "updated_at",
            ]
        )

        write_audit_event(
            action_code="ARCHIVE",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text=reason_text,
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def restore_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_update(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_restore_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_RESTORE_NOT_ALLOWED",
                "This timesheet cannot be restored by the current user.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        actor_employee = _employee_for_current_user(current_user)

        timesheet.status = _ref_value("TIMESHEET_STATUS", "APPROVED")
        timesheet.updated_by = current_user.email
        timesheet.save(
            update_fields=[
                "status",
                "updated_by",
                "updated_at",
            ]
        )

        write_audit_event(
            action_code="RESTORE",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text=reason_text,
        )

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)
