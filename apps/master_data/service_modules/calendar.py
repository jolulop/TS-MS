from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError

from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    CalendarSpecialDay,
    YearlyCalendar,
)
from apps.master_data.models import CalendarSpecialDay as CalendarSpecialDayRecord
from apps.master_data.models import GeneralChargeCode as GeneralChargeCodeRecord


def _master_services():
    from apps.master_data import services

    return services


def _actor_employee(current_user):
    return _master_services()._actor_employee(current_user)


def _apply_status_filter(queryset, status_code):
    return _master_services()._apply_status_filter(queryset, status_code)


def _build_special_day_name(day_type, special_date: date) -> str:
    return _master_services()._build_special_day_name(day_type, special_date)


def _ensure_business_units_in_scope(
    current_user: CurrentUser,
    business_unit_ids: set[int],
) -> None:
    return _master_services()._ensure_business_units_in_scope(
        current_user,
        business_unit_ids,
    )


def _ensure_current_office_active_for_write(current_user: CurrentUser):
    return _master_services()._ensure_current_office_active_for_write(current_user)


def _ensure_office_in_scope(current_user: CurrentUser, office_id: int, *, message: str) -> None:
    return _master_services()._ensure_office_in_scope(
        current_user,
        office_id,
        message=message,
    )


def _ensure_scoped_active_office_for_write(
    current_user: CurrentUser,
    office,
    *,
    out_of_scope_message: str,
) -> None:
    return _master_services()._ensure_scoped_active_office_for_write(
        current_user,
        office,
        out_of_scope_message=out_of_scope_message,
    )


def _ensure_ts_admin(current_user: CurrentUser) -> None:
    return _master_services()._ensure_ts_admin(current_user)


def _get_current_office(current_user: CurrentUser):
    return _master_services()._get_current_office(current_user)


def _get_scoped_business_unit(current_user: CurrentUser, business_unit_id: int):
    return _master_services()._get_scoped_business_unit(current_user, business_unit_id)


def _parse_bool(value: object) -> bool:
    return _master_services()._parse_bool(value)


def _parse_decimal(value: object, *, code: str, message: str):
    return _master_services()._parse_decimal(value, code=code, message=message)


def _parse_iso_date(value: object, *, code: str, message: str) -> date:
    return _master_services()._parse_iso_date(value, code=code, message=message)


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    return _master_services()._parse_required_int(value, code=code, message=message)


def _parse_status_filter(status_code, *, domain_code: str):
    return _master_services()._parse_status_filter(status_code, domain_code=domain_code)


def _ref_value(domain_code: str, value_code: str):
    return _master_services()._ref_value(domain_code, value_code)


def _serialize_calendar_period_rule(rule: CalendarPeriodRule) -> dict:
    return _master_services()._serialize_calendar_period_rule(rule)


def _serialize_calendar_special_day(special_day: CalendarSpecialDayRecord) -> dict:
    return _master_services()._serialize_calendar_special_day(special_day)


def _serialize_yearly_calendar(yearly_calendar: YearlyCalendar) -> dict:
    return _master_services()._serialize_yearly_calendar(yearly_calendar)


def _validate_optional_office_payload(payload: dict, **kwargs) -> None:
    return _master_services()._validate_optional_office_payload(payload, **kwargs)


def _validate_weekend_hours(period_rule, payload: dict):
    return _master_services()._validate_weekend_hours(period_rule, payload)


class GeneralChargeCodeManagementService:
    @staticmethod
    def _get_scoped_general_charge_code(
        current_user: CurrentUser,
        general_charge_code_id: int,
    ) -> GeneralChargeCodeRecord:
        service = _master_services().GeneralChargeCodeManagementService
        return service._get_scoped_general_charge_code(current_user, general_charge_code_id)


class YearlyCalendarManagementService:
    @staticmethod
    def list_yearly_calendars(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        calendars = _apply_status_filter(
            YearlyCalendar.objects.select_related("office", "status")
            .filter(office_id=current_user.office_id)
            .order_by("calendar_year", "calendar_name"),
            _parse_status_filter(status_code, domain_code="CALENDAR_STATUS"),
        )
        return [_serialize_yearly_calendar(calendar) for calendar in calendars]

    @staticmethod
    def get_yearly_calendar(current_user: CurrentUser, yearly_calendar_id: int) -> dict:
        _ensure_ts_admin(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
        return YearlyCalendarManagementService._serialize_yearly_calendar_detail(yearly_calendar)

    @staticmethod
    @transaction.atomic
    def create_yearly_calendar(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        office = _get_current_office(current_user)
        _ensure_scoped_active_office_for_write(
            current_user,
            office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        calendar_year = _parse_required_int(
            payload.get("calendar_year"),
            code="YEARLY_CALENDAR_YEAR_REQUIRED",
            message="calendar_year is required.",
        )
        calendar_name = str(payload.get("calendar_name", "")).strip()
        if not calendar_name:
            raise AuthError(
                "YEARLY_CALENDAR_NAME_REQUIRED",
                "Calendar name is required.",
                400,
            )
        _validate_optional_office_payload(
            payload,
            code_prefix="YEARLY_CALENDAR",
            expected_office_id=office.id,
            mismatch_message="Yearly calendar office must match the active office.",
        )

        try:
            yearly_calendar = YearlyCalendar.objects.create(
                office=office,
                calendar_year=calendar_year,
                calendar_name=calendar_name,
                status=_ref_value(
                    "CALENDAR_STATUS",
                    str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "YEARLY_CALENDAR_NOT_UNIQUE",
                "Only one yearly calendar can exist for the same year within the Office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="yearly_calendar",
            entity_id=yearly_calendar.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Yearly calendar created by Timesheet Administrator.",
        )
        return _serialize_yearly_calendar(
            YearlyCalendarManagementService._refresh_yearly_calendar(yearly_calendar.id)
        )

    @staticmethod
    @transaction.atomic
    def update_yearly_calendar(
        current_user: CurrentUser,
        yearly_calendar_id: int,
        payload: dict,
    ) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="YEARLY_CALENDAR",
            expected_office_id=yearly_calendar.office_id,
            immutable_office_id=yearly_calendar.office_id,
            mismatch_message="Yearly calendar office must match the existing office.",
            immutable_message="Yearly calendar office cannot be changed.",
        )

        changed_fields: list[tuple[str, str, str]] = []

        if "calendar_year" in payload:
            new_calendar_year = _parse_required_int(
                payload.get("calendar_year"),
                code="YEARLY_CALENDAR_YEAR_REQUIRED",
                message="calendar_year is required.",
            )
            if new_calendar_year != yearly_calendar.calendar_year:
                changed_fields.append(
                    ("calendar_year", str(yearly_calendar.calendar_year), str(new_calendar_year))
                )
                yearly_calendar.calendar_year = new_calendar_year

        if "calendar_name" in payload:
            new_calendar_name = str(payload.get("calendar_name", "")).strip()
            if not new_calendar_name:
                raise AuthError(
                    "YEARLY_CALENDAR_NAME_REQUIRED",
                    "Calendar name is required.",
                    400,
                )
            if new_calendar_name != yearly_calendar.calendar_name:
                changed_fields.append(
                    ("calendar_name", yearly_calendar.calendar_name, new_calendar_name)
                )
                yearly_calendar.calendar_name = new_calendar_name

        if "status_code" in payload:
            new_status = _ref_value("CALENDAR_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != yearly_calendar.status_id:
                changed_fields.append(
                    ("status", yearly_calendar.status.value_code, new_status.value_code)
                )
                yearly_calendar.status = new_status

        if changed_fields:
            try:
                yearly_calendar.updated_by = current_user.email
                yearly_calendar.save()
            except IntegrityError as exc:
                raise AuthError(
                    "YEARLY_CALENDAR_NOT_UNIQUE",
                    "Only one yearly calendar can exist for the same year within the Office.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="yearly_calendar",
                entity_id=yearly_calendar.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Yearly calendar updated by Timesheet Administrator.",
            )
        return _serialize_yearly_calendar(
            YearlyCalendarManagementService._refresh_yearly_calendar(yearly_calendar.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_yearly_calendar(current_user: CurrentUser, yearly_calendar_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )

        try:
            calendar_label = f"{yearly_calendar.calendar_year} - {yearly_calendar.calendar_name}"
            calendar_id = yearly_calendar.id
            yearly_calendar.delete()
        except ProtectedError as exc:
            raise AuthError(
                "YEARLY_CALENDAR_DELETE_BLOCKED",
                "Yearly calendar cannot be deleted because it is still referenced by "
                "employees, period rules, special days, or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="yearly_calendar",
            entity_id=calendar_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=calendar_label,
            reason_text="Yearly calendar deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _serialize_yearly_calendar_detail(yearly_calendar: YearlyCalendar) -> dict:
        special_days = list(
            CalendarSpecialDayRecord.objects.select_related(
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "day_type",
                "default_general_charge_code",
                "status",
            )
            .filter(yearly_calendar_id=yearly_calendar.id)
            .order_by("special_date")
        )
        active_special_days = [
            special_day for special_day in special_days if special_day.status.value_code == "ACTIVE"
        ]
        active_holiday_codes = {"NATIONAL_HOLIDAY", "LOCAL_HOLIDAY"}
        weekday_count = 0
        week_starts: set[date] = set()
        first_day = date(yearly_calendar.calendar_year, 1, 1)
        last_day = date(yearly_calendar.calendar_year, 12, 31)
        current_day = first_day
        while current_day <= last_day:
            if current_day.weekday() < 5:
                weekday_count += 1
                week_starts.add(current_day - timedelta(days=current_day.weekday()))
            current_day += timedelta(days=1)

        active_weekday_special_days = sum(
            1 for special_day in active_special_days if special_day.special_date.weekday() < 5
        )

        return {
            **_serialize_yearly_calendar(yearly_calendar),
            "special_days": [
                _serialize_calendar_special_day(special_day) for special_day in special_days
            ],
            "summary": {
                "week_count": len(week_starts),
                "weekday_count": weekday_count,
                "active_holiday_count": sum(
                    1
                    for special_day in active_special_days
                    if special_day.day_type.value_code in active_holiday_codes
                ),
                "active_timia_other_count": sum(
                    1
                    for special_day in active_special_days
                    if special_day.day_type.value_code not in active_holiday_codes
                ),
                "net_working_day_count": weekday_count - active_weekday_special_days,
            },
            "period_rule_count": yearly_calendar.period_rules.count(),
        }

    @staticmethod
    def _get_scoped_yearly_calendar(
        current_user: CurrentUser, yearly_calendar_id: int
    ) -> YearlyCalendar:
        try:
            yearly_calendar = YearlyCalendar.objects.select_related(
                "office",
                "office__status",
                "status",
            ).get(id=yearly_calendar_id)
        except YearlyCalendar.DoesNotExist as exc:
            raise AuthError("YEARLY_CALENDAR_NOT_FOUND", "Yearly calendar not found.", 404) from exc
        _ensure_office_in_scope(
            current_user,
            yearly_calendar.office_id,
            message="Yearly calendar is outside your active office.",
        )
        return yearly_calendar

    @staticmethod
    def _refresh_yearly_calendar(yearly_calendar_id: int) -> YearlyCalendar:
        return YearlyCalendar.objects.select_related("office", "status").get(id=yearly_calendar_id)


class CalendarSpecialDayManagementService:
    @staticmethod
    def list_special_days(
        current_user: CurrentUser,
        *,
        yearly_calendar_id: int | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        special_days = CalendarSpecialDayRecord.objects.select_related(
            "yearly_calendar",
            "yearly_calendar__office",
            "yearly_calendar__status",
            "day_type",
            "default_general_charge_code",
            "status",
        ).filter(yearly_calendar__office_id=current_user.office_id)
        if yearly_calendar_id is not None:
            special_days = special_days.filter(yearly_calendar_id=yearly_calendar_id)
        special_days = special_days.order_by("yearly_calendar__calendar_year", "special_date")
        return [_serialize_calendar_special_day(special_day) for special_day in special_days]

    @staticmethod
    def get_special_day(current_user: CurrentUser, special_day_id: int) -> dict:
        _ensure_ts_admin(current_user)
        special_day = CalendarSpecialDayManagementService._get_scoped_special_day(
            current_user,
            special_day_id,
        )
        return _serialize_calendar_special_day(special_day)

    @staticmethod
    @transaction.atomic
    def create_special_day(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_SPECIAL_DAY_CALENDAR_REQUIRED",
                message="yearly_calendar_id is required.",
            ),
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        special_date = _parse_iso_date(
            payload.get("special_date"),
            code="CALENDAR_SPECIAL_DAY_DATE_REQUIRED",
            message="special_date must be a valid ISO date.",
        )
        CalendarSpecialDayManagementService._validate_calendar_year(
            yearly_calendar.calendar_year,
            special_date=special_date,
        )
        day_type = _ref_value(
            "SPECIAL_DAY_TYPE",
            str(payload.get("day_type_code", "")).strip(),
        )
        default_general_charge_code = (
            CalendarSpecialDayManagementService._resolve_default_general_charge_code(
                current_user,
                yearly_calendar=yearly_calendar,
                default_general_charge_code_id=payload.get("default_general_charge_code_id"),
            )
        )
        try:
            special_day = CalendarSpecialDay.objects.create(
                yearly_calendar=yearly_calendar,
                special_date=special_date,
                day_type=day_type,
                name=_build_special_day_name(day_type, special_date),
                default_general_charge_code=default_general_charge_code,
                status=_ref_value(
                    "SPECIAL_DAY_STATUS",
                    str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
                ),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_NOT_UNIQUE",
                "A special day already exists for that date in the selected calendar.",
                400,
            ) from exc
        write_audit_event(
            action_code="CREATE",
            entity_name="calendar_special_day",
            entity_id=special_day.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Calendar special day created by Timesheet Administrator.",
        )
        return _serialize_calendar_special_day(
            CalendarSpecialDayManagementService._refresh_special_day(special_day.id)
        )

    @staticmethod
    @transaction.atomic
    def update_special_day(current_user: CurrentUser, special_day_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        special_day = CalendarSpecialDayManagementService._get_scoped_special_day(
            current_user,
            special_day_id,
        )
        yearly_calendar = special_day.yearly_calendar
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Calendar special day is outside your active office.",
        )
        if (
            "yearly_calendar_id" in payload
            and _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_SPECIAL_DAY_CALENDAR_REQUIRED",
                message="yearly_calendar_id must be a valid calendar identifier.",
            )
            != special_day.yearly_calendar_id
        ):
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_CALENDAR_IMMUTABLE",
                "Calendar special day calendar cannot be changed.",
                400,
            )

        changed_fields: list[tuple[str, str, str]] = []
        updated_day_type = special_day.day_type
        updated_special_date = special_day.special_date

        if "special_date" in payload:
            updated_special_date = _parse_iso_date(
                payload.get("special_date"),
                code="CALENDAR_SPECIAL_DAY_DATE_REQUIRED",
                message="special_date must be a valid ISO date.",
            )
            CalendarSpecialDayManagementService._validate_calendar_year(
                yearly_calendar.calendar_year,
                special_date=updated_special_date,
            )
            if updated_special_date != special_day.special_date:
                changed_fields.append(
                    (
                        "special_date",
                        special_day.special_date.isoformat(),
                        updated_special_date.isoformat(),
                    )
                )
                special_day.special_date = updated_special_date

        if "day_type_code" in payload:
            updated_day_type = _ref_value(
                "SPECIAL_DAY_TYPE",
                str(payload.get("day_type_code", "")).strip(),
            )
            if updated_day_type.id != special_day.day_type_id:
                changed_fields.append(
                    (
                        "day_type",
                        special_day.day_type.value_code,
                        updated_day_type.value_code,
                    )
                )
                special_day.day_type = updated_day_type

        if "status_code" in payload:
            new_status = _ref_value(
                "SPECIAL_DAY_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != special_day.status_id:
                changed_fields.append(
                    ("status", special_day.status.value_code, new_status.value_code)
                )
                special_day.status = new_status

        if "default_general_charge_code_id" in payload:
            new_default_general_charge_code = (
                CalendarSpecialDayManagementService._resolve_default_general_charge_code(
                    current_user,
                    yearly_calendar=yearly_calendar,
                    default_general_charge_code_id=payload.get("default_general_charge_code_id"),
                )
            )
            old_code = (
                special_day.default_general_charge_code.code
                if special_day.default_general_charge_code_id is not None
                else ""
            )
            new_code = (
                new_default_general_charge_code.code
                if new_default_general_charge_code is not None
                else ""
            )
            if special_day.default_general_charge_code_id != (
                new_default_general_charge_code.id if new_default_general_charge_code else None
            ):
                changed_fields.append(("default_general_charge_code", old_code, new_code))
                special_day.default_general_charge_code = new_default_general_charge_code

        updated_name = _build_special_day_name(updated_day_type, updated_special_date)
        if updated_name != special_day.name:
            changed_fields.append(("name", special_day.name, updated_name))
            special_day.name = updated_name

        if changed_fields:
            try:
                special_day.updated_by = current_user.email
                special_day.save()
            except IntegrityError as exc:
                raise AuthError(
                    "CALENDAR_SPECIAL_DAY_NOT_UNIQUE",
                    "A special day already exists for that date in the selected calendar.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="calendar_special_day",
                entity_id=special_day.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Calendar special day updated by Timesheet Administrator.",
            )
        return _serialize_calendar_special_day(
            CalendarSpecialDayManagementService._refresh_special_day(special_day.id)
        )

    @staticmethod
    @transaction.atomic
    def delete_special_day(current_user: CurrentUser, special_day_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        special_day = CalendarSpecialDayManagementService._get_scoped_special_day(
            current_user,
            special_day_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            special_day.yearly_calendar.office,
            out_of_scope_message="Calendar special day is outside your active office.",
        )
        try:
            special_day_label = (
                f"{special_day.special_date.isoformat()} {special_day.day_type.value_code}"
            )
            special_day_record_id = special_day.id
            special_day.delete()
        except ProtectedError as exc:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_DELETE_BLOCKED",
                "Calendar special day cannot be deleted because it is still referenced by "
                "other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="calendar_special_day",
            entity_id=special_day_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=special_day_label,
            reason_text="Calendar special day deleted by Timesheet Administrator.",
        )

    @staticmethod
    def _validate_calendar_year(calendar_year: int, *, special_date: date) -> None:
        if special_date.year != calendar_year:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_YEAR_MISMATCH",
                "Special day date must belong to the selected calendar year.",
                400,
            )

    @staticmethod
    def _resolve_default_general_charge_code(
        current_user: CurrentUser,
        *,
        yearly_calendar: YearlyCalendar,
        default_general_charge_code_id: object,
    ) -> GeneralChargeCodeRecord | None:
        if default_general_charge_code_id in (None, ""):
            return None
        general_charge_code = GeneralChargeCodeManagementService._get_scoped_general_charge_code(
            current_user,
            _parse_required_int(
                default_general_charge_code_id,
                code="CALENDAR_SPECIAL_DAY_GENERAL_CHARGE_CODE_INVALID",
                message=(
                    "default_general_charge_code_id must be a valid general charge code identifier."
                ),
            ),
        )
        if general_charge_code.office_id != yearly_calendar.office_id:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_GENERAL_CHARGE_CODE_OFFICE_MISMATCH",
                "Default general charge code must belong to the same Office.",
                400,
            )
        return general_charge_code

    @staticmethod
    def _get_scoped_special_day(
        current_user: CurrentUser,
        special_day_id: int,
    ) -> CalendarSpecialDayRecord:
        try:
            special_day = CalendarSpecialDayRecord.objects.select_related(
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "day_type",
                "default_general_charge_code",
                "status",
            ).get(id=special_day_id)
        except CalendarSpecialDayRecord.DoesNotExist as exc:
            raise AuthError(
                "CALENDAR_SPECIAL_DAY_NOT_FOUND",
                "Calendar special day not found.",
                404,
            ) from exc
        _ensure_office_in_scope(
            current_user,
            special_day.yearly_calendar.office_id,
            message="Calendar special day is outside your active office.",
        )
        return special_day

    @staticmethod
    def _refresh_special_day(special_day_id: int) -> CalendarSpecialDayRecord:
        return CalendarSpecialDayRecord.objects.select_related(
            "yearly_calendar",
            "yearly_calendar__office",
            "yearly_calendar__status",
            "day_type",
            "default_general_charge_code",
            "status",
        ).get(id=special_day_id)


class CalendarPeriodRuleManagementService:
    @staticmethod
    def list_period_rules(
        current_user: CurrentUser,
        *,
        status_code: str | None = None,
    ) -> list[dict]:
        _ensure_ts_admin(current_user)
        period_rules = _apply_status_filter(
            CalendarPeriodRule.objects.select_related(
                "business_unit",
                "office",
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "status",
            )
            .filter(office_id=current_user.office_id)
            .filter(
                Q(business_unit_id__in=current_user.scoped_business_unit_ids)
                | Q(business_unit_id__isnull=True)
            )
            .order_by(
                "yearly_calendar__calendar_year",
                "yearly_calendar__calendar_name",
                "business_unit__bu_code",
                "effective_from",
            ),
            _parse_status_filter(status_code, domain_code="CALENDAR_PERIOD_STATUS"),
        )
        return [_serialize_calendar_period_rule(period_rule) for period_rule in period_rules]

    @staticmethod
    def list_yearly_calendars(current_user: CurrentUser) -> list[dict]:
        return YearlyCalendarManagementService.list_yearly_calendars(current_user)

    @staticmethod
    def get_period_rule(current_user: CurrentUser, period_rule_id: int) -> dict:
        _ensure_ts_admin(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        return _serialize_calendar_period_rule(period_rule)

    @staticmethod
    @transaction.atomic
    def delete_period_rule(current_user: CurrentUser, period_rule_id: int) -> None:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            period_rule.office,
            out_of_scope_message="Calendar Period Rule is outside your active office.",
        )

        try:
            period_rule_label = (
                f"{period_rule.yearly_calendar.calendar_name} "
                f"{period_rule.effective_from.isoformat()} - {period_rule.effective_to.isoformat()}"
            )
            period_rule_record_id = period_rule.id
            period_rule.delete()
        except ProtectedError as exc:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_DELETE_BLOCKED",
                "Calendar Period Rule cannot be deleted because it is still referenced by "
                "other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="calendar_period_rule",
            entity_id=period_rule_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=period_rule_label,
            reason_text="Calendar period rule deleted by Timesheet Administrator.",
        )

    @staticmethod
    @transaction.atomic
    def create_period_rule(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        yearly_calendar = CalendarPeriodRuleManagementService._get_scoped_yearly_calendar(
            current_user,
            _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED",
                message="yearly_calendar_id is required.",
            ),
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            yearly_calendar.office,
            out_of_scope_message="Yearly calendar is outside your active office.",
        )
        business_unit = _get_scoped_business_unit(
            current_user,
            _parse_required_int(
                payload.get("business_unit_id"),
                code="CALENDAR_PERIOD_RULE_BUSINESS_UNIT_REQUIRED",
                message="business_unit_id is required.",
            ),
        )
        if business_unit.office_id != yearly_calendar.office_id:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_BUSINESS_UNIT_OFFICE_MISMATCH",
                "Business Unit must belong to the same Office as the selected yearly calendar.",
                400,
            )
        effective_from = _parse_iso_date(
            payload.get("effective_from"),
            code="CALENDAR_PERIOD_RULE_EFFECTIVE_FROM_REQUIRED",
            message="effective_from must be a valid ISO date.",
        )
        effective_to = _parse_iso_date(
            payload.get("effective_to"),
            code="CALENDAR_PERIOD_RULE_EFFECTIVE_TO_REQUIRED",
            message="effective_to must be a valid ISO date.",
        )
        CalendarPeriodRuleManagementService._validate_date_range(effective_from, effective_to)
        CalendarPeriodRuleManagementService._lock_period_rule_overlap_scope(
            yearly_calendar_id=yearly_calendar.id,
            business_unit_ids={business_unit.id},
        )
        CalendarPeriodRuleManagementService._ensure_no_overlap(
            yearly_calendar.id,
            business_unit.id,
            effective_from=effective_from,
            effective_to=effective_to,
        )
        saturday_max_hours, sunday_max_hours = _validate_weekend_hours(None, payload)
        _validate_optional_office_payload(
            payload,
            code_prefix="CALENDAR_PERIOD_RULE",
            expected_office_id=yearly_calendar.office_id,
            mismatch_message=(
                "Calendar Period Rule office must match the selected yearly calendar office."
            ),
        )
        period_rule = CalendarPeriodRule.objects.create(
            yearly_calendar=yearly_calendar,
            business_unit=business_unit,
            office=yearly_calendar.office,
            effective_from=effective_from,
            effective_to=effective_to,
            monday_max_hours=_parse_decimal(
                payload.get("monday_max_hours"),
                code="CALENDAR_PERIOD_RULE_MONDAY_REQUIRED",
                message="monday_max_hours is required.",
            ),
            tuesday_max_hours=_parse_decimal(
                payload.get("tuesday_max_hours"),
                code="CALENDAR_PERIOD_RULE_TUESDAY_REQUIRED",
                message="tuesday_max_hours is required.",
            ),
            wednesday_max_hours=_parse_decimal(
                payload.get("wednesday_max_hours"),
                code="CALENDAR_PERIOD_RULE_WEDNESDAY_REQUIRED",
                message="wednesday_max_hours is required.",
            ),
            thursday_max_hours=_parse_decimal(
                payload.get("thursday_max_hours"),
                code="CALENDAR_PERIOD_RULE_THURSDAY_REQUIRED",
                message="thursday_max_hours is required.",
            ),
            friday_max_hours=_parse_decimal(
                payload.get("friday_max_hours"),
                code="CALENDAR_PERIOD_RULE_FRIDAY_REQUIRED",
                message="friday_max_hours is required.",
            ),
            working_on_saturdays_flag=_parse_bool(payload.get("working_on_saturdays_flag")),
            working_on_sundays_flag=_parse_bool(payload.get("working_on_sundays_flag")),
            saturday_max_hours=saturday_max_hours,
            sunday_max_hours=sunday_max_hours,
            status=_ref_value(
                "CALENDAR_PERIOD_STATUS",
                str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE",
            ),
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        write_audit_event(
            action_code="CREATE",
            entity_name="calendar_period_rule",
            entity_id=period_rule.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Calendar period rule created by Timesheet Administrator.",
        )
        return _serialize_calendar_period_rule(
            CalendarPeriodRuleManagementService._refresh_period_rule(period_rule.id)
        )

    @staticmethod
    @transaction.atomic
    def update_period_rule(current_user: CurrentUser, period_rule_id: int, payload: dict) -> dict:
        _ensure_ts_admin(current_user)
        _ensure_current_office_active_for_write(current_user)
        actor_employee = _actor_employee(current_user)
        period_rule = CalendarPeriodRuleManagementService._get_scoped_period_rule(
            current_user,
            period_rule_id,
        )
        _ensure_scoped_active_office_for_write(
            current_user,
            period_rule.office,
            out_of_scope_message="Calendar Period Rule is outside your active office.",
        )
        _validate_optional_office_payload(
            payload,
            code_prefix="CALENDAR_PERIOD_RULE",
            expected_office_id=period_rule.office_id,
            immutable_office_id=period_rule.office_id,
            mismatch_message="Calendar Period Rule office must match the existing office.",
            immutable_message="Calendar Period Rule office cannot be changed.",
        )
        if (
            "yearly_calendar_id" in payload
            and _parse_required_int(
                payload.get("yearly_calendar_id"),
                code="CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED",
                message="yearly_calendar_id must be a valid calendar identifier.",
            )
            != period_rule.yearly_calendar_id
        ):
            raise AuthError(
                "CALENDAR_PERIOD_RULE_CALENDAR_IMMUTABLE",
                "Calendar Period Rule calendar cannot be changed.",
                400,
            )
        proposed_business_unit = period_rule.business_unit
        if "business_unit_id" in payload:
            proposed_business_unit = _get_scoped_business_unit(
                current_user,
                _parse_required_int(
                    payload.get("business_unit_id"),
                    code="CALENDAR_PERIOD_RULE_BUSINESS_UNIT_REQUIRED",
                    message="business_unit_id must be a valid Business Unit identifier.",
                ),
            )
        if proposed_business_unit is None:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_BUSINESS_UNIT_REQUIRED",
                "business_unit_id is required.",
                400,
            )
        if proposed_business_unit.office_id != period_rule.office_id:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_BUSINESS_UNIT_OFFICE_MISMATCH",
                "Business Unit must belong to the same Office as the selected yearly calendar.",
                400,
            )
        proposed_effective_from = period_rule.effective_from
        proposed_effective_to = period_rule.effective_to
        if "effective_from" in payload:
            proposed_effective_from = _parse_iso_date(
                payload.get("effective_from"),
                code="CALENDAR_PERIOD_RULE_EFFECTIVE_FROM_REQUIRED",
                message="effective_from must be a valid ISO date.",
            )
        if "effective_to" in payload:
            proposed_effective_to = _parse_iso_date(
                payload.get("effective_to"),
                code="CALENDAR_PERIOD_RULE_EFFECTIVE_TO_REQUIRED",
                message="effective_to must be a valid ISO date.",
            )
        CalendarPeriodRuleManagementService._validate_date_range(
            proposed_effective_from,
            proposed_effective_to,
        )
        CalendarPeriodRuleManagementService._lock_period_rule_overlap_scope(
            yearly_calendar_id=period_rule.yearly_calendar_id,
            business_unit_ids={
                business_unit_id
                for business_unit_id in (
                    period_rule.business_unit_id,
                    proposed_business_unit.id,
                )
                if business_unit_id is not None
            },
        )
        CalendarPeriodRuleManagementService._ensure_no_overlap(
            period_rule.yearly_calendar_id,
            proposed_business_unit.id,
            effective_from=proposed_effective_from,
            effective_to=proposed_effective_to,
            exclude_rule_id=period_rule.id,
        )
        saturday_max_hours, sunday_max_hours = _validate_weekend_hours(period_rule, payload)
        changed_fields: list[tuple[str, str, str]] = []
        if period_rule.business_unit_id != proposed_business_unit.id:
            changed_fields.append(
                (
                    "business_unit",
                    period_rule.business_unit.bu_code if period_rule.business_unit_id else "",
                    proposed_business_unit.bu_code,
                )
            )
            period_rule.business_unit = proposed_business_unit
        for field_name, code, message in (
            (
                "monday_max_hours",
                "CALENDAR_PERIOD_RULE_MONDAY_REQUIRED",
                "monday_max_hours is required.",
            ),
            (
                "tuesday_max_hours",
                "CALENDAR_PERIOD_RULE_TUESDAY_REQUIRED",
                "tuesday_max_hours is required.",
            ),
            (
                "wednesday_max_hours",
                "CALENDAR_PERIOD_RULE_WEDNESDAY_REQUIRED",
                "wednesday_max_hours is required.",
            ),
            (
                "thursday_max_hours",
                "CALENDAR_PERIOD_RULE_THURSDAY_REQUIRED",
                "thursday_max_hours is required.",
            ),
            (
                "friday_max_hours",
                "CALENDAR_PERIOD_RULE_FRIDAY_REQUIRED",
                "friday_max_hours is required.",
            ),
        ):
            if field_name in payload:
                new_value = _parse_decimal(payload.get(field_name), code=code, message=message)
                if getattr(period_rule, field_name) != new_value:
                    changed_fields.append(
                        (field_name, str(getattr(period_rule, field_name)), str(new_value))
                    )
                    setattr(period_rule, field_name, new_value)
        if proposed_effective_from != period_rule.effective_from:
            changed_fields.append(
                (
                    "effective_from",
                    period_rule.effective_from.isoformat(),
                    proposed_effective_from.isoformat(),
                )
            )
            period_rule.effective_from = proposed_effective_from
        if proposed_effective_to != period_rule.effective_to:
            changed_fields.append(
                (
                    "effective_to",
                    period_rule.effective_to.isoformat(),
                    proposed_effective_to.isoformat(),
                )
            )
            period_rule.effective_to = proposed_effective_to
        for flag_name in ("working_on_saturdays_flag", "working_on_sundays_flag"):
            if flag_name in payload:
                new_flag_value = _parse_bool(payload.get(flag_name))
                if getattr(period_rule, flag_name) != new_flag_value:
                    changed_fields.append(
                        (
                            flag_name,
                            str(getattr(period_rule, flag_name)),
                            str(new_flag_value),
                        )
                    )
                    setattr(period_rule, flag_name, new_flag_value)
        for field_name, new_value in (
            ("saturday_max_hours", saturday_max_hours),
            ("sunday_max_hours", sunday_max_hours),
        ):
            if getattr(period_rule, field_name) != new_value:
                changed_fields.append(
                    (field_name, str(getattr(period_rule, field_name)), str(new_value))
                )
                setattr(period_rule, field_name, new_value)
        if "status_code" in payload:
            new_status = _ref_value(
                "CALENDAR_PERIOD_STATUS",
                str(payload.get("status_code", "")).strip(),
            )
            if new_status.id != period_rule.status_id:
                changed_fields.append(
                    ("status", period_rule.status.value_code, new_status.value_code)
                )
                period_rule.status = new_status
        if changed_fields:
            period_rule.updated_by = current_user.email
            period_rule.save()
        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="calendar_period_rule",
                entity_id=period_rule.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Calendar period rule updated by Timesheet Administrator.",
            )
        return _serialize_calendar_period_rule(
            CalendarPeriodRuleManagementService._refresh_period_rule(period_rule.id)
        )

    @staticmethod
    def _validate_date_range(effective_from: date, effective_to: date) -> None:
        if effective_to < effective_from:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_DATE_RANGE_INVALID",
                "effective_to must be on or after effective_from.",
                400,
            )

    @staticmethod
    def _ensure_no_overlap(
        yearly_calendar_id: int,
        business_unit_id: int | None,
        *,
        effective_from: date,
        effective_to: date,
        exclude_rule_id: int | None = None,
    ) -> None:
        overlaps = CalendarPeriodRule.objects.filter(
            yearly_calendar_id=yearly_calendar_id,
            effective_from__lte=effective_to,
            effective_to__gte=effective_from,
        )
        if business_unit_id is None:
            overlaps = overlaps.filter(business_unit_id__isnull=True)
        else:
            overlaps = overlaps.filter(business_unit_id=business_unit_id)
        if exclude_rule_id is not None:
            overlaps = overlaps.exclude(id=exclude_rule_id)
        if overlaps.exists():
            raise AuthError(
                "CALENDAR_PERIOD_RULE_OVERLAP",
                (
                    "Calendar Period Rules cannot overlap within the same "
                    "Business Unit and yearly calendar."
                ),
                400,
            )

    @staticmethod
    def _lock_period_rule_overlap_scope(
        *,
        yearly_calendar_id: int,
        business_unit_ids: set[int],
    ) -> None:
        if business_unit_ids:
            list(
                BusinessUnit.objects.select_for_update(of=("self",))
                .filter(id__in=sorted(business_unit_ids))
                .order_by("id")
            )
            return
        YearlyCalendar.objects.select_for_update(of=("self",)).get(id=yearly_calendar_id)

    @staticmethod
    def _get_scoped_yearly_calendar(
        current_user: CurrentUser, yearly_calendar_id: int
    ) -> YearlyCalendar:
        return YearlyCalendarManagementService._get_scoped_yearly_calendar(
            current_user,
            yearly_calendar_id,
        )

    @staticmethod
    def _get_scoped_period_rule(
        current_user: CurrentUser, period_rule_id: int
    ) -> CalendarPeriodRule:
        try:
            period_rule = CalendarPeriodRule.objects.select_related(
                "business_unit",
                "office",
                "yearly_calendar",
                "yearly_calendar__office",
                "yearly_calendar__status",
                "status",
            ).get(id=period_rule_id)
        except CalendarPeriodRule.DoesNotExist as exc:
            raise AuthError(
                "CALENDAR_PERIOD_RULE_NOT_FOUND", "Calendar Period Rule not found.", 404
            ) from exc
        _ensure_office_in_scope(
            current_user,
            period_rule.office_id,
            message="Calendar Period Rule is outside your active office.",
        )
        if period_rule.business_unit_id is not None:
            _ensure_business_units_in_scope(current_user, {period_rule.business_unit_id})
        return period_rule

    @staticmethod
    def _refresh_period_rule(period_rule_id: int) -> CalendarPeriodRule:
        return CalendarPeriodRule.objects.select_related(
            "business_unit",
            "office",
            "yearly_calendar",
            "yearly_calendar__office",
            "yearly_calendar__status",
            "status",
        ).get(id=period_rule_id)
