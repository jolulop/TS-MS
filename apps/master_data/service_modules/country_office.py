from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError

from apps.audit.models import AuditLog
from apps.audit.services import write_audit_event
from apps.auth.context import CurrentUser
from apps.auth.errors import AuthError
from apps.auth.services import canonicalize_email
from apps.master_data.models import (
    BusinessUnit,
    Country,
    Employee,
    Office,
    OfficeConfiguration,
)


def _master_services():
    from apps.master_data import services

    return services


def _actor_employee(current_user):
    return _master_services()._actor_employee(current_user)


def _apply_status_filter(queryset, status_code):
    return _master_services()._apply_status_filter(queryset, status_code)


def _default_office_configuration_data():
    return _master_services()._default_office_configuration_data()


def _ensure_business_unit_code_available(**kwargs) -> None:
    return _master_services()._ensure_business_unit_code_available(**kwargs)


def _ensure_employee_calendar_setup(employee: Employee, *, actor_email: str) -> None:
    return _master_services()._ensure_employee_calendar_setup(
        employee,
        actor_email=actor_email,
    )


def _ensure_ts_admin_master(current_user: CurrentUser) -> None:
    return _master_services()._ensure_ts_admin_master(current_user)


def _parse_bool(value: object) -> bool:
    return _master_services()._parse_bool(value)


def _parse_optional_iso_date(value: object, *, code: str, message: str):
    return _master_services()._parse_optional_iso_date(value, code=code, message=message)


def _parse_required_int(value: object, *, code: str, message: str) -> int:
    return _master_services()._parse_required_int(value, code=code, message=message)


def _ref_value(domain_code: str, value_code: str):
    return _master_services()._ref_value(domain_code, value_code)


def _serialize_country(country: Country) -> dict:
    return _master_services()._serialize_country(country)


def _serialize_office(office: Office) -> dict:
    return _master_services()._serialize_office(office)


OFFICE_CONFIG_FIELD_NAMES = {
    "approval_mode_code",
    "allow_employee_withdraw_flag",
    "timesheet_cutoff_date",
    "count_non_billable_in_daily_limit_flag",
    "archive_after_years",
    "enable_timer_flag",
    "enable_leave_integration_flag",
    "enable_copy_previous_week_flag",
}


class CountryManagementService:
    @staticmethod
    def list_countries(current_user: CurrentUser, *, status_code: str | None = None) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        countries = _apply_status_filter(
            Country.objects.select_related("status")
            .annotate(office_count=Count("offices"))
            .order_by("country_name"),
            status_code,
        )
        return [_serialize_country(country) for country in countries]

    @staticmethod
    def get_country(current_user: CurrentUser, country_id: int) -> dict:
        _ensure_ts_admin_master(current_user)
        return _serialize_country(CountryManagementService._refresh_country(country_id))

    @staticmethod
    @transaction.atomic
    def create_country(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country_code = str(payload.get("country_code", "")).strip()
        country_name = str(payload.get("country_name", "")).strip()
        if not country_code:
            raise AuthError("COUNTRY_CODE_REQUIRED", "Country code is required.", 400)
        if not country_name:
            raise AuthError("COUNTRY_NAME_REQUIRED", "Country name is required.", 400)
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        try:
            country = Country.objects.create(
                country_code=country_code,
                country_name=country_name,
                status=_ref_value("COUNTRY_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "COUNTRY_NOT_UNIQUE",
                "Country code and country name must be unique.",
                400,
            ) from exc
        write_audit_event(
            action_code="CREATE",
            entity_name="country",
            entity_id=country.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Country created by Timesheet Master Administrator.",
        )
        return _serialize_country(CountryManagementService._refresh_country(country.id))

    @staticmethod
    @transaction.atomic
    def update_country(current_user: CurrentUser, country_id: int, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country = CountryManagementService._refresh_country(country_id)
        changed_fields: list[tuple[str, str, str]] = []

        if "country_code" in payload:
            new_country_code = str(payload.get("country_code", "")).strip()
            if not new_country_code:
                raise AuthError("COUNTRY_CODE_REQUIRED", "Country code is required.", 400)
            if new_country_code != country.country_code:
                changed_fields.append(("country_code", country.country_code, new_country_code))
                country.country_code = new_country_code

        if "country_name" in payload:
            new_country_name = str(payload.get("country_name", "")).strip()
            if not new_country_name:
                raise AuthError("COUNTRY_NAME_REQUIRED", "Country name is required.", 400)
            if new_country_name != country.country_name:
                changed_fields.append(("country_name", country.country_name, new_country_name))
                country.country_name = new_country_name

        if "status_code" in payload:
            new_status = _ref_value("COUNTRY_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != country.status_id:
                changed_fields.append(("status", country.status.value_code, new_status.value_code))
                country.status = new_status

        if changed_fields:
            try:
                country.updated_by = current_user.email
                country.save()
            except IntegrityError as exc:
                raise AuthError(
                    "COUNTRY_NOT_UNIQUE",
                    "Country code and country name must be unique.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="country",
                entity_id=country.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Country updated by Timesheet Master Administrator.",
            )

        return _serialize_country(CountryManagementService._refresh_country(country.id))

    @staticmethod
    @transaction.atomic
    def delete_country(current_user: CurrentUser, country_id: int) -> None:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country = CountryManagementService._refresh_country(country_id)
        try:
            country_name = country.country_name
            country_record_id = country.id
            country.delete()
        except ProtectedError as exc:
            raise AuthError(
                "COUNTRY_DELETE_BLOCKED",
                "Country cannot be deleted because it is still referenced by Offices "
                "or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="country",
            entity_id=country_record_id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            old_value=country_name,
            reason_text="Country deleted by Timesheet Master Administrator.",
        )

    @staticmethod
    def _refresh_country(country_id: int) -> Country:
        try:
            return (
                Country.objects.select_related("status")
                .annotate(office_count=Count("offices"))
                .get(id=country_id)
            )
        except Country.DoesNotExist as exc:
            raise AuthError("COUNTRY_NOT_FOUND", "Country not found.", 404) from exc


class OfficeManagementService:
    CONFIG_FIELD_NAMES = OFFICE_CONFIG_FIELD_NAMES

    @staticmethod
    def list_offices(current_user: CurrentUser, *, status_code: str | None = None) -> list[dict]:
        _ensure_ts_admin_master(current_user)
        offices = _apply_status_filter(
            Office.objects.select_related(
                "country",
                "country__status",
                "status",
                "configuration",
                "configuration__approval_mode",
            )
            .annotate(
                active_employee_count=Count(
                    "employees",
                    filter=Q(employees__status__value_code="ACTIVE"),
                    distinct=True,
                )
            )
            .order_by("office_name"),
            status_code,
        )
        return [_serialize_office(office) for office in offices]

    @staticmethod
    def get_office(current_user: CurrentUser, office_id: int) -> dict:
        _ensure_ts_admin_master(current_user)
        return _serialize_office(OfficeManagementService._refresh_office(office_id))

    @staticmethod
    @transaction.atomic
    def create_office(current_user: CurrentUser, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        country_id = _parse_required_int(
            payload.get("country_id"),
            code="COUNTRY_REQUIRED",
            message="country_id is required.",
        )
        country = CountryManagementService._refresh_country(country_id)
        office_name = str(payload.get("office_name", "")).strip()
        if not office_name:
            raise AuthError("COUNTRY_NAME_REQUIRED", "Office name is required.", 400)
        status_code = str(payload.get("status_code", "ACTIVE")).strip() or "ACTIVE"
        bootstrap_business_unit_code = str(payload.get("bootstrap_bu_code", "")).strip()
        bootstrap_business_unit_name = str(payload.get("bootstrap_bu_name", "")).strip()
        bootstrap_business_unit_description = str(
            payload.get("bootstrap_bu_description", "")
        ).strip()
        bootstrap_admin_employee_code = str(
            payload.get("bootstrap_admin_employee_code", "")
        ).strip()
        bootstrap_admin_full_name = str(payload.get("bootstrap_admin_full_name", "")).strip()
        bootstrap_admin_email = str(payload.get("bootstrap_admin_email", "")).strip()
        if not bootstrap_business_unit_code:
            raise AuthError(
                "BUSINESS_UNIT_CODE_REQUIRED",
                "Initial Business Unit code is required.",
                400,
            )
        if not bootstrap_business_unit_name:
            raise AuthError(
                "BUSINESS_UNIT_NAME_REQUIRED",
                "Initial Business Unit name is required.",
                400,
            )
        if not bootstrap_admin_employee_code:
            raise AuthError(
                "EMPLOYEE_CODE_REQUIRED",
                "Initial admin employee code is required.",
                400,
            )
        if not bootstrap_admin_full_name:
            raise AuthError(
                "EMPLOYEE_NAME_REQUIRED",
                "Initial admin full name is required.",
                400,
            )
        if not bootstrap_admin_email:
            raise AuthError(
                "EMPLOYEE_EMAIL_REQUIRED",
                "Initial admin email is required.",
                400,
            )
        try:
            office = Office.objects.create(
                country=country,
                office_name=office_name,
                status=_ref_value("COUNTRY_STATUS", status_code),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "COUNTRY_NAME_NOT_UNIQUE",
                "Office name must be unique.",
                400,
            ) from exc

        OfficeManagementService._upsert_configuration(
            current_user,
            office,
            payload,
            actor_employee=actor_employee,
            create_if_missing=True,
        )
        bootstrap_business_unit = OfficeManagementService._create_bootstrap_business_unit(
            current_user,
            office,
            bu_code=bootstrap_business_unit_code,
            name=bootstrap_business_unit_name,
            description=bootstrap_business_unit_description,
            actor_employee=actor_employee,
        )
        OfficeManagementService._create_bootstrap_admin_employee(
            current_user,
            office,
            business_unit=bootstrap_business_unit,
            employee_code=bootstrap_admin_employee_code,
            full_name=bootstrap_admin_full_name,
            email=bootstrap_admin_email,
            actor_employee=actor_employee,
        )
        write_audit_event(
            action_code="CREATE",
            entity_name="office",
            entity_id=office.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            reason_text="Office created by Timesheet Master Administrator.",
        )
        return _serialize_office(OfficeManagementService._refresh_office(office.id))

    @staticmethod
    @transaction.atomic
    def update_office(current_user: CurrentUser, office_id: int, payload: dict) -> dict:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        office = OfficeManagementService._refresh_office(office_id)
        changed_fields: list[tuple[str, str, str]] = []

        if "country_id" in payload:
            new_country_id = _parse_required_int(
                payload.get("country_id"),
                code="COUNTRY_REQUIRED",
                message="country_id is required.",
            )
            if new_country_id != office.country_id:
                new_country = CountryManagementService._refresh_country(new_country_id)
                changed_fields.append(
                    ("country", office.country.country_code, new_country.country_code)
                )
                office.country = new_country

        if "office_name" in payload:
            new_office_name = str(payload.get("office_name", "")).strip()
            if not new_office_name:
                raise AuthError("COUNTRY_NAME_REQUIRED", "Office name is required.", 400)
            if new_office_name != office.office_name:
                changed_fields.append(("office_name", office.office_name, new_office_name))
                office.office_name = new_office_name

        if "status_code" in payload:
            new_status = _ref_value("COUNTRY_STATUS", str(payload.get("status_code", "")).strip())
            if new_status.id != office.status_id:
                changed_fields.append(("status", office.status.value_code, new_status.value_code))
                office.status = new_status

        if changed_fields:
            try:
                office.updated_by = current_user.email
                office.save()
            except IntegrityError as exc:
                raise AuthError(
                    "COUNTRY_NAME_NOT_UNIQUE",
                    "Office name must be unique.",
                    400,
                ) from exc

        for field_name, old_value, new_value in changed_fields:
            write_audit_event(
                action_code="UPDATE",
                entity_name="office",
                entity_id=office.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name=field_name,
                old_value=old_value,
                new_value=new_value,
                reason_text="Office updated by Timesheet Master Administrator.",
            )

        if changed_fields or OfficeManagementService.CONFIG_FIELD_NAMES.intersection(payload):
            OfficeManagementService._upsert_configuration(
                current_user,
                office,
                payload,
                actor_employee=actor_employee,
                create_if_missing=True,
            )

        return _serialize_office(OfficeManagementService._refresh_office(office.id))

    @staticmethod
    @transaction.atomic
    def delete_office(current_user: CurrentUser, office_id: int) -> None:
        _ensure_ts_admin_master(current_user)
        actor_employee = _actor_employee(current_user)
        office = OfficeManagementService._refresh_office(office_id)
        setup_teardown = OfficeManagementService._get_setup_only_teardown_records(office)
        audit_actor = OfficeManagementService._audit_actor_for_teardown(
            actor_employee,
            setup_teardown,
        )
        configuration = OfficeConfiguration.objects.filter(office=office).first()

        if setup_teardown is not None:
            OfficeManagementService._delete_setup_only_records(
                current_user,
                business_units=setup_teardown[0],
                employees=setup_teardown[1],
                actor_employee=audit_actor,
            )

        if configuration is not None:
            write_audit_event(
                action_code="DELETE",
                entity_name="office_configuration",
                entity_id=configuration.id,
                actor_employee=audit_actor,
                actor_email=current_user.email,
                reason_text="Office configuration deleted with Office deletion.",
            )
            configuration.delete()

        try:
            office_name = office.office_name
            office_record_id = office.id
            office.delete()
        except ProtectedError as exc:
            raise AuthError(
                "COUNTRY_DELETE_BLOCKED",
                "Office cannot be deleted because it is still referenced by "
                "Business Units or other records.",
                400,
            ) from exc

        write_audit_event(
            action_code="DELETE",
            entity_name="office",
            entity_id=office_record_id,
            actor_employee=audit_actor,
            actor_email=current_user.email,
            old_value=office_name,
            reason_text="Office deleted by Timesheet Master Administrator.",
        )

    @staticmethod
    def _get_setup_only_teardown_records(
        office: Office,
    ) -> tuple[list[BusinessUnit], list[Employee]] | None:
        business_units = list(BusinessUnit.objects.filter(office=office).order_by("id"))
        employees = list(Employee.objects.filter(office=office).order_by("id"))
        if not business_units and not employees:
            return None
        if len(business_units) != 1 or len(employees) != 1:
            return None

        business_unit = business_units[0]
        employee = employees[0]
        if employee.primary_business_unit_id != business_unit.id:
            return None
        role_codes = set(
            employee.role_assignments.values_list("role__value_code", flat=True)
        )
        if "TS_ADMIN" not in role_codes:
            return None
        if role_codes - {"USER", "TS_ADMIN", "TS_ADMIN_MASTER"}:
            return None
        if not employee.role_assignments.filter(
            role__domain__domain_code="ROLE_CODE",
            role__value_code="TS_ADMIN",
            status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
            valid_to__isnull=True,
        ).exists():
            return None

        scoped_business_unit_ids = set(
            employee.business_unit_assignments.values_list("business_unit_id", flat=True)
        )
        if scoped_business_unit_ids - {business_unit.id}:
            return None

        role_business_unit_ids = set(
            employee.role_assignments.exclude(business_unit__isnull=True).values_list(
                "business_unit_id",
                flat=True,
            )
        )
        if role_business_unit_ids - {business_unit.id}:
            return None

        return business_units, employees

    @staticmethod
    def _delete_setup_only_records(
        current_user: CurrentUser,
        *,
        business_units: list[BusinessUnit],
        employees: list[Employee],
        actor_employee: Employee | None,
    ) -> None:
        employee_ids = [employee.id for employee in employees]
        business_unit_ids = [business_unit.id for business_unit in business_units]
        audit_actor = actor_employee
        if actor_employee is not None and actor_employee.id in employee_ids:
            audit_actor = None

        for employee in employees:
            OfficeManagementService._delete_setup_employee_assignments(
                current_user,
                employee,
                actor_employee=audit_actor,
            )

        AuditLog.objects.filter(actor_employee_id__in=employee_ids).update(
            actor_employee=None
        )
        AuditLog.objects.filter(business_unit_id__in=business_unit_ids).update(
            business_unit=None
        )

        try:
            for employee in employees:
                employee_name = employee.full_name
                employee_record_id = employee.id
                employee.delete()
                write_audit_event(
                    action_code="DELETE",
                    entity_name="employee",
                    entity_id=employee_record_id,
                    actor_employee=audit_actor,
                    actor_email=current_user.email,
                    old_value=employee_name,
                    reason_text="Setup-only Office administrator deleted with Office deletion.",
                )

            for business_unit in business_units:
                business_unit_code = business_unit.bu_code
                business_unit_record_id = business_unit.id
                business_unit.delete()
                write_audit_event(
                    action_code="DELETE",
                    entity_name="business_unit",
                    entity_id=business_unit_record_id,
                    actor_employee=audit_actor,
                    actor_email=current_user.email,
                    old_value=business_unit_code,
                    reason_text="Setup-only Business Unit deleted with Office deletion.",
                )
        except ProtectedError as exc:
            raise AuthError(
                "COUNTRY_DELETE_BLOCKED",
                "Office cannot be deleted because it is still referenced by "
                "Business Units, employees, or other records.",
                400,
            ) from exc

    @staticmethod
    def _delete_setup_employee_assignments(
        current_user: CurrentUser,
        employee: Employee,
        *,
        actor_employee: Employee | None,
    ) -> None:
        role_assignments = list(employee.role_assignments.select_related("role"))
        for assignment in role_assignments:
            write_audit_event(
                action_code="DELETE",
                entity_name="employee_role",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                old_value=assignment.role.value_code,
                reason_text="Employee role deleted with setup-only Office deletion.",
            )
            assignment.delete()

        business_unit_assignments = list(
            employee.business_unit_assignments.select_related("business_unit")
        )
        for assignment in business_unit_assignments:
            write_audit_event(
                action_code="DELETE",
                entity_name="employee_business_unit",
                entity_id=assignment.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                old_value=assignment.business_unit.bu_code,
                reason_text="Employee Business Unit scope deleted with setup-only Office deletion.",
            )
            assignment.delete()

    @staticmethod
    def _audit_actor_for_teardown(
        actor_employee: Employee | None,
        setup_teardown: tuple[list[BusinessUnit], list[Employee]] | None,
    ) -> Employee | None:
        if actor_employee is None or setup_teardown is None:
            return actor_employee
        teardown_employee_ids = {employee.id for employee in setup_teardown[1]}
        if actor_employee.id in teardown_employee_ids:
            return None
        return actor_employee

    @staticmethod
    def _refresh_office(office_id: int) -> Office:
        try:
            office = (
                Office.objects.select_related(
                    "country",
                    "country__status",
                    "status",
                    "configuration",
                    "configuration__approval_mode",
                )
                .annotate(
                    active_employee_count=Count(
                        "employees",
                        filter=Q(employees__status__value_code="ACTIVE"),
                        distinct=True,
                    )
                )
                .get(id=office_id)
            )
        except Office.DoesNotExist as exc:
            raise AuthError("COUNTRY_NOT_FOUND", "Office not found.", 404) from exc
        office._administrators_cache = list(
            Employee.objects.select_related("primary_business_unit", "status")
            .filter(
                office_id=office.id,
                role_assignments__role__domain__domain_code="ROLE_CODE",
                role_assignments__role__value_code="TS_ADMIN",
                role_assignments__status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                role_assignments__status__value_code="ACTIVE",
                role_assignments__valid_to__isnull=True,
            )
            .order_by("employee_code")
            .distinct()
        )
        return office

    @staticmethod
    def _upsert_configuration(
        current_user: CurrentUser,
        office: Office,
        payload: dict,
        *,
        actor_employee: Employee | None,
        create_if_missing: bool,
    ) -> None:
        configuration = OfficeConfiguration.objects.select_related("approval_mode").filter(
            office=office
        ).first()
        defaults = _default_office_configuration_data()

        approval_mode_code = str(
            payload.get(
                "approval_mode_code",
                configuration.approval_mode.value_code
                if configuration
                else defaults["approval_mode"],
            )
        ).strip()
        if not approval_mode_code:
            raise AuthError(
                "OFFICE_APPROVAL_MODE_REQUIRED",
                "approval_mode_code is required.",
                400,
            )

        archive_after_years = _parse_required_int(
            payload.get(
                "archive_after_years",
                configuration.archive_after_years
                if configuration
                else defaults["archive_after_years"],
            ),
            code="OFFICE_ARCHIVE_YEARS_REQUIRED",
            message="archive_after_years is required.",
        )
        if archive_after_years <= 0:
            raise AuthError(
                "OFFICE_ARCHIVE_YEARS_INVALID",
                "archive_after_years must be greater than 0.",
                400,
            )

        timesheet_cutoff_date = _parse_optional_iso_date(
            payload.get(
                "timesheet_cutoff_date",
                configuration.timesheet_cutoff_date if configuration else None,
            ),
            code="OFFICE_CUTOFF_DATE_INVALID",
            message="timesheet_cutoff_date must be a valid ISO date.",
        )

        allow_employee_withdraw_flag = _parse_bool(
            payload.get(
                "allow_employee_withdraw_flag",
                configuration.allow_employee_withdraw_flag
                if configuration
                else defaults["allow_employee_withdraw_flag"],
            )
        )
        count_non_billable_in_daily_limit_flag = _parse_bool(
            payload.get(
                "count_non_billable_in_daily_limit_flag",
                configuration.count_non_billable_in_daily_limit_flag
                if configuration
                else defaults["count_non_billable_in_daily_limit_flag"],
            )
        )
        enable_timer_flag = _parse_bool(
            payload.get(
                "enable_timer_flag",
                configuration.enable_timer_flag if configuration else defaults["enable_timer_flag"],
            )
        )
        enable_leave_integration_flag = _parse_bool(
            payload.get(
                "enable_leave_integration_flag",
                configuration.enable_leave_integration_flag
                if configuration
                else defaults["enable_leave_integration_flag"],
            )
        )
        enable_copy_previous_week_flag = _parse_bool(
            payload.get(
                "enable_copy_previous_week_flag",
                configuration.enable_copy_previous_week_flag
                if configuration
                else defaults["enable_copy_previous_week_flag"],
            )
        )

        approval_mode = _ref_value("APPROVAL_MODE", approval_mode_code)

        if configuration is None:
            if not create_if_missing:
                return
            configuration = OfficeConfiguration.objects.create(
                office=office,
                approval_mode=approval_mode,
                allow_employee_withdraw_flag=allow_employee_withdraw_flag,
                timesheet_cutoff_date=timesheet_cutoff_date,
                count_non_billable_in_daily_limit_flag=count_non_billable_in_daily_limit_flag,
                archive_after_years=archive_after_years,
                enable_timer_flag=enable_timer_flag,
                enable_leave_integration_flag=enable_leave_integration_flag,
                enable_copy_previous_week_flag=enable_copy_previous_week_flag,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
            write_audit_event(
                action_code="CREATE",
                entity_name="office_configuration",
                entity_id=configuration.id,
                actor_employee=actor_employee,
                actor_email=current_user.email,
                field_name="office_configuration",
                new_value="created",
                reason_text="Office configuration created by Timesheet Master Administrator.",
            )
            return

        changed_fields: list[tuple[str, str, str]] = []
        if approval_mode.id != configuration.approval_mode_id:
            changed_fields.append(
                ("approval_mode", configuration.approval_mode.value_code, approval_mode.value_code)
            )
            configuration.approval_mode = approval_mode
        if allow_employee_withdraw_flag != configuration.allow_employee_withdraw_flag:
            changed_fields.append(
                (
                    "allow_employee_withdraw_flag",
                    str(configuration.allow_employee_withdraw_flag),
                    str(allow_employee_withdraw_flag),
                )
            )
            configuration.allow_employee_withdraw_flag = allow_employee_withdraw_flag
        old_cutoff_date = (
            configuration.timesheet_cutoff_date.isoformat()
            if configuration.timesheet_cutoff_date
            else ""
        )
        new_cutoff_date = timesheet_cutoff_date.isoformat() if timesheet_cutoff_date else ""
        if old_cutoff_date != new_cutoff_date:
            changed_fields.append(("timesheet_cutoff_date", old_cutoff_date, new_cutoff_date))
            configuration.timesheet_cutoff_date = timesheet_cutoff_date
        if (
            count_non_billable_in_daily_limit_flag
            != configuration.count_non_billable_in_daily_limit_flag
        ):
            changed_fields.append(
                (
                    "count_non_billable_in_daily_limit_flag",
                    str(configuration.count_non_billable_in_daily_limit_flag),
                    str(count_non_billable_in_daily_limit_flag),
                )
            )
            configuration.count_non_billable_in_daily_limit_flag = (
                count_non_billable_in_daily_limit_flag
            )
        if archive_after_years != configuration.archive_after_years:
            changed_fields.append(
                (
                    "archive_after_years",
                    str(configuration.archive_after_years),
                    str(archive_after_years),
                )
            )
            configuration.archive_after_years = archive_after_years
        if enable_timer_flag != configuration.enable_timer_flag:
            changed_fields.append(
                ("enable_timer_flag", str(configuration.enable_timer_flag), str(enable_timer_flag))
            )
            configuration.enable_timer_flag = enable_timer_flag
        if enable_leave_integration_flag != configuration.enable_leave_integration_flag:
            changed_fields.append(
                (
                    "enable_leave_integration_flag",
                    str(configuration.enable_leave_integration_flag),
                    str(enable_leave_integration_flag),
                )
            )
            configuration.enable_leave_integration_flag = enable_leave_integration_flag
        if enable_copy_previous_week_flag != configuration.enable_copy_previous_week_flag:
            changed_fields.append(
                (
                    "enable_copy_previous_week_flag",
                    str(configuration.enable_copy_previous_week_flag),
                    str(enable_copy_previous_week_flag),
                )
            )
            configuration.enable_copy_previous_week_flag = enable_copy_previous_week_flag

        if changed_fields:
            configuration.updated_by = current_user.email
            configuration.save()
            for field_name, old_value, new_value in changed_fields:
                write_audit_event(
                    action_code="UPDATE",
                    entity_name="office_configuration",
                    entity_id=configuration.id,
                    actor_employee=actor_employee,
                    actor_email=current_user.email,
                    field_name=field_name,
                    old_value=old_value,
                    new_value=new_value,
                    reason_text="Office configuration updated by Timesheet Master Administrator.",
                )

    @staticmethod
    def _create_bootstrap_business_unit(
        current_user: CurrentUser,
        office: Office,
        *,
        bu_code: str,
        name: str,
        description: str,
        actor_employee: Employee | None,
    ) -> BusinessUnit:
        _ensure_business_unit_code_available(
            office_id=office.id,
            bu_code=bu_code,
            message="Initial Business Unit code must be unique within the Office.",
        )
        try:
            business_unit = BusinessUnit.objects.create(
                bu_code=bu_code,
                name=name,
                description=description,
                office=office,
                status=_ref_value("BUSINESS_UNIT_STATUS", "ACTIVE"),
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "BUSINESS_UNIT_CODE_NOT_UNIQUE",
                "Initial Business Unit code must be unique within the Office.",
                400,
            ) from exc

        write_audit_event(
            action_code="CREATE",
            entity_name="business_unit",
            entity_id=business_unit.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            reason_text="Initial Business Unit created with Office creation.",
        )
        return business_unit

    @staticmethod
    def _create_bootstrap_admin_employee(
        current_user: CurrentUser,
        office: Office,
        *,
        business_unit: BusinessUnit,
        employee_code: str,
        full_name: str,
        email: str,
        actor_employee: Employee | None,
    ) -> Employee:
        try:
            employee = Employee.objects.create(
                employee_code=employee_code,
                full_name=full_name,
                email=email,
                canonical_email=canonicalize_email(email),
                office=office,
                status=_ref_value("EMPLOYEE_STATUS", "ACTIVE"),
                primary_business_unit=business_unit,
                created_by=current_user.email,
                updated_by=current_user.email,
            )
        except IntegrityError as exc:
            raise AuthError(
                "EMPLOYEE_EMAIL_NOT_UNIQUE",
                "Initial admin employee email must be unique.",
                400,
            ) from exc

        _master_services().EmployeeManagementService._replace_business_unit_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            primary_business_unit_id=business_unit.id,
            business_unit_ids={business_unit.id},
            reason="Initial Office administrator created with initial BU assignments.",
            enforce_current_office_scope=False,
        )
        _master_services().EmployeeManagementService._replace_role_assignments(
            current_user,
            employee,
            actor_employee=actor_employee,
            role_codes=["TS_ADMIN", "USER"],
            reason="Initial Office administrator created with initial role assignments.",
        )
        _ensure_employee_calendar_setup(employee, actor_email=current_user.email)

        write_audit_event(
            action_code="CREATE",
            entity_name="employee",
            entity_id=employee.id,
            actor_employee=actor_employee,
            actor_email=current_user.email,
            business_unit=business_unit,
            reason_text="Initial Office administrator created with Office creation.",
        )
        return employee
