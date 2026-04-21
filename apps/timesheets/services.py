from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.policies import AuthorizationPolicyService
from apps.master_data.models import (
    BusinessUnitConfiguration,
    CalendarPeriodRule,
    Employee,
    GeneralChargeCode,
    Project,
    ProjectAssignment,
)
from apps.reference_data.models import RefValue
from apps.timesheets.models import (
    ApprovalAction,
    ApprovalItem,
    TimesheetLine,
    TimesheetSubmissionCycle,
    WeeklyTimesheet,
)


def _ref_value(domain_code: str, value_code: str) -> RefValue:
    try:
        return RefValue.objects.get(domain__domain_code=domain_code, value_code=value_code)
    except RefValue.DoesNotExist as exc:
        raise AuthError(
            "REFERENCE_VALUE_NOT_FOUND",
            f"Unknown reference value {domain_code}:{value_code}.",
            400,
        ) from exc


def _parse_iso_date(value: object, *, code: str, message: str) -> date:
    if value in (None, ""):
        raise AuthError(code, message, 400)
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AuthError(code, message, 400) from exc


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


def _validate_week_start_date(week_start_date: date) -> tuple[date, date]:
    if week_start_date.weekday() != 0:
        raise AuthError(
            "TIMESHEET_WEEK_START_INVALID",
            "week_start_date must be a Monday.",
            400,
        )
    return week_start_date, week_start_date + timedelta(days=4)


def _get_project_for_line(
    employee: Employee, work_date: date, project_id: int, business_unit_id: int
) -> Project:
    try:
        project = Project.objects.select_related("status").get(id=project_id)
    except Project.DoesNotExist as exc:
        raise AuthError("PROJECT_NOT_FOUND", "Project not found.", 404) from exc

    if project.business_unit_id != business_unit_id:
        raise AuthError(
            "TIMESHEET_PROJECT_INVALID",
            "Project is not available for this timesheet Business Unit.",
            400,
        )
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

    assignment_exists = (
        ProjectAssignment.objects.filter(
            employee=employee,
            project=project,
            status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
            assignment_start_date__lte=work_date,
        )
        .filter(assignment_end_date__isnull=True)
        .exists()
        or ProjectAssignment.objects.filter(
            employee=employee,
            project=project,
            status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
            assignment_start_date__lte=work_date,
            assignment_end_date__gte=work_date,
        ).exists()
    )
    if not assignment_exists:
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


def _daily_limit_for_date(employee: Employee, work_date: date) -> Decimal:
    if employee.assigned_calendar_id is None:
        raise AuthError(
            "TIMESHEET_CALENDAR_REQUIRED",
            "Employee must have an assigned calendar before saving timesheet lines.",
            400,
        )

    rules = list(
        CalendarPeriodRule.objects.filter(
            yearly_calendar_id=employee.assigned_calendar_id,
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

    rule = rules[0]
    weekday_fields = {
        0: rule.monday_max_hours,
        1: rule.tuesday_max_hours,
        2: rule.wednesday_max_hours,
        3: rule.thursday_max_hours,
        4: rule.friday_max_hours,
    }
    return Decimal(weekday_fields[work_date.weekday()])


def _approval_mode_code(business_unit_id: int) -> str:
    try:
        configuration = BusinessUnitConfiguration.objects.select_related("approval_mode").get(
            business_unit_id=business_unit_id
        )
    except BusinessUnitConfiguration.DoesNotExist:
        return "PROJECT"
    return configuration.approval_mode.value_code


def _archive_after_years(business_unit_id: int) -> int:
    try:
        configuration = BusinessUnitConfiguration.objects.get(business_unit_id=business_unit_id)
    except BusinessUnitConfiguration.DoesNotExist:
        return 5
    return configuration.archive_after_years or 5


def _timesheet_cutoff_date(business_unit_id: int) -> date | None:
    try:
        configuration = BusinessUnitConfiguration.objects.get(business_unit_id=business_unit_id)
    except BusinessUnitConfiguration.DoesNotExist:
        return None
    return configuration.timesheet_cutoff_date


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


def _serialize_approval_item(approval_item: ApprovalItem, *, include_lines: bool = False) -> dict:
    submission_cycle = approval_item.submission_cycle
    timesheet = submission_cycle.weekly_timesheet
    payload = {
        "id": approval_item.id,
        "submission_cycle_id": submission_cycle.id,
        "submission_no": submission_cycle.submission_no,
        "timesheet_id": timesheet.id,
        "timesheet_employee": {
            "id": timesheet.employee_id,
            "employee_code": timesheet.employee.employee_code,
            "full_name": timesheet.employee.full_name,
        },
        "scope_type": approval_item.scope_type.value_code,
        "status": approval_item.status.value_code,
        "rejection_reason": approval_item.rejection_reason,
        "project": (
            {
                "id": approval_item.project_id,
                "project_code": approval_item.project.project_code,
                "name": approval_item.project.name,
            }
            if approval_item.project_id is not None
            else None
        ),
    }
    if include_lines:
        lines = timesheet.lines.all().order_by("work_date", "id")
        if approval_item.project_id is not None:
            lines = lines.filter(project_id=approval_item.project_id)
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
        approval_item = (
            ApprovalItem.objects.select_related(
                "scope_type",
                "status",
                "approver_employee",
                "project",
                "submission_cycle",
                "submission_cycle__weekly_timesheet",
                "submission_cycle__weekly_timesheet__employee",
                "submission_cycle__weekly_timesheet__business_unit",
            )
            .prefetch_related("submission_cycle__weekly_timesheet__lines__project")
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


class TimesheetService:
    @staticmethod
    def list_timesheets(current_user: CurrentUser) -> list[dict]:
        timesheets = (
            WeeklyTimesheet.objects.select_related("status")
            .filter(employee_id=current_user.employee_id)
            .order_by("-week_start_date", "id")
        )
        return [
            {
                "id": timesheet.id,
                "week_start_date": timesheet.week_start_date.isoformat(),
                "week_end_date": timesheet.week_end_date.isoformat(),
                "status": timesheet.status.value_code,
                "current_submission_no": timesheet.current_submission_no,
            }
            for timesheet in timesheets
        ]

    @staticmethod
    @transaction.atomic
    def create_timesheet(current_user: CurrentUser, payload: dict) -> dict:
        employee = _employee_for_current_user(current_user)
        week_start_date = _parse_iso_date(
            payload.get("week_start_date"),
            code="TIMESHEET_WEEK_START_REQUIRED",
            message="week_start_date must be a valid ISO date.",
        )
        week_start_date, week_end_date = _validate_week_start_date(week_start_date)

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
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
            if work_date < timesheet.week_start_date or work_date > timesheet.week_end_date:
                raise AuthError(
                    "TIMESHEET_WORK_DATE_OUT_OF_RANGE",
                    "work_date must be inside the Monday-Friday timesheet week.",
                    400,
                )
            if work_date.weekday() > 4:
                raise AuthError(
                    "TIMESHEET_WEEKEND_NOT_ALLOWED",
                    "Weekend entry is not allowed in the standard timesheet.",
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
                    timesheet.business_unit_id,
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
            max_hours = _daily_limit_for_date(employee, work_date)
            if hours > max_hours:
                raise AuthError(
                    "TIMESHEET_DAILY_LIMIT_EXCEEDED",
                    f"Daily hours exceed the calendar limit for {work_date.isoformat()}.",
                    400,
                )

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

        refreshed = _get_timesheet_for_view(current_user, timesheet.id)
        return _serialize_timesheet(refreshed)

    @staticmethod
    @transaction.atomic
    def submit_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
        auto_approved_line_ids: list[int] = []
        project_map: dict[int, Project] = {}

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
                raise AuthError(
                    "TIMESHEET_GENERAL_CODE_APPROVAL_NOT_CONFIGURED",
                    (
                        "General charge code approval routing is not configured in "
                        "the current implementation."
                    ),
                    400,
                )
            auto_approved_line_ids.append(line.id)

        _set_line_approval_state(
            line_ids=[
                line_id
                for project_line_ids in project_line_ids_by_project_id.values()
                for line_id in project_line_ids
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

        write_audit_event(
            action_code="SUBMIT",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=timesheet.employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Timesheet submitted by employee.",
        )

        if not project_line_ids_by_project_id:
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
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
        if not AuthorizationPolicyService.can_withdraw_timesheet(current_user, timesheet):
            raise AuthError(
                "TIMESHEET_WITHDRAW_NOT_ALLOWED",
                "This timesheet cannot be withdrawn in its current state.",
                400,
            )

        try:
            submission_cycle = timesheet.submission_cycles.select_related(
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
    def list_approval_items(current_user: CurrentUser) -> list[dict]:
        if not current_user.has_role("PROJECT_MANAGER"):
            raise AuthError(
                "AUTH_ACCESS_DENIED",
                "You are not authorized to view approval items.",
                403,
            )

        approval_items = (
            ApprovalItem.objects.select_related(
                "scope_type",
                "status",
                "project",
                "submission_cycle",
                "submission_cycle__weekly_timesheet",
                "submission_cycle__weekly_timesheet__employee",
            )
            .filter(approver_employee_id=current_user.employee_id)
            .order_by(
                "status__sort_order",
                "submission_cycle__weekly_timesheet__week_start_date",
                "id",
            )
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
        approval_item = _get_approval_item_for_view(current_user, approval_item_id)
        if not AuthorizationPolicyService.can_approve_approval_item(current_user, approval_item):
            raise AuthError(
                "APPROVAL_ACTION_NOT_ALLOWED",
                "This approval item cannot be approved by the current user.",
                400,
            )

        acted_at = timezone.now()
        comment_text = str(payload.get("comment_text", "")).strip()
        submission_cycle = approval_item.submission_cycle
        timesheet = submission_cycle.weekly_timesheet

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
            line_ids=list(
                timesheet.lines.filter(project_id=approval_item.project_id).values_list(
                    "id",
                    flat=True,
                )
            ),
            approval_state_code="APPROVED",
        )

        write_audit_event(
            action_code="APPROVE",
            entity_name="approval_item",
            entity_id=approval_item.id,
            actor_employee=approval_item.approver_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Project approval completed.",
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
                actor_employee=approval_item.approver_employee,
                actor_email=current_user.email,
                business_unit=timesheet.business_unit,
                reason_text="All required project approvals completed.",
            )

        return TimesheetService.get_approval_item(current_user, approval_item.id)

    @staticmethod
    @transaction.atomic
    def reject_approval_item(
        current_user: CurrentUser,
        approval_item_id: int,
        payload: dict,
    ) -> dict:
        approval_item = _get_approval_item_for_view(current_user, approval_item_id)
        if not AuthorizationPolicyService.can_reject_approval_item(current_user, approval_item):
            raise AuthError(
                "APPROVAL_ACTION_NOT_ALLOWED",
                "This approval item cannot be rejected by the current user.",
                400,
            )

        reason_text = str(payload.get("reason_text") or payload.get("comment_text") or "").strip()
        if not reason_text:
            raise AuthError(
                "APPROVAL_REJECTION_REASON_REQUIRED",
                "A rejection reason is required.",
                400,
            )

        acted_at = timezone.now()
        submission_cycle = approval_item.submission_cycle
        timesheet = submission_cycle.weekly_timesheet

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
            line_ids=list(
                timesheet.lines.filter(project_id=approval_item.project_id).values_list(
                    "id",
                    flat=True,
                )
            ),
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
            actor_employee=approval_item.approver_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text=reason_text,
        )
        write_audit_event(
            action_code="REJECT",
            entity_name="weekly_timesheet",
            entity_id=timesheet.id,
            actor_employee=approval_item.approver_employee,
            actor_email=current_user.email,
            business_unit=timesheet.business_unit,
            reason_text="Timesheet rejected after project approval action.",
        )

        return TimesheetService.get_approval_item(current_user, approval_item.id)

    @staticmethod
    @transaction.atomic
    def reopen_timesheet(current_user: CurrentUser, timesheet_id: int, payload: dict) -> dict:
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
        timesheet = _get_timesheet_for_view(current_user, timesheet_id)
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
