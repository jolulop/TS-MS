from datetime import date

from django.core.management import call_command

from apps.master_data.models import (
    BusinessUnit,
    BusinessUnitConfiguration,
    CalendarPeriodRule,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    Project,
    ProjectAssignment,
    YearlyCalendar,
)
from apps.master_data.models import (
    Client as ClientRecord,
)
from apps.master_data.models import (
    CostCenter as CostCenterRecord,
)
from apps.master_data.models import (
    GeneralChargeCode as GeneralChargeCodeRecord,
)
from apps.master_data.models import (
    InternalCategory as InternalCategoryRecord,
)
from apps.reference_data.models import RefValue

SYSTEM_ACTOR = "system@test.local"


def seed_reference_data() -> None:
    call_command("seed_reference_data")


def ref_value(domain_code: str, value_code: str) -> RefValue:
    return RefValue.objects.get(domain__domain_code=domain_code, value_code=value_code)


def create_business_unit(*, bu_code: str, name: str) -> BusinessUnit:
    return BusinessUnit.objects.create(
        bu_code=bu_code,
        name=name,
        description="",
        status=ref_value("BUSINESS_UNIT_STATUS", "ACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_business_unit_configuration(
    *,
    business_unit: BusinessUnit,
    approval_mode_code: str = "PROJECT",
    allow_employee_withdraw_flag: bool = False,
    timesheet_cutoff_date: date | None = None,
) -> BusinessUnitConfiguration:
    return BusinessUnitConfiguration.objects.create(
        business_unit=business_unit,
        approval_mode=ref_value("APPROVAL_MODE", approval_mode_code),
        allow_employee_withdraw_flag=allow_employee_withdraw_flag,
        timesheet_cutoff_date=timesheet_cutoff_date,
        count_non_billable_in_daily_limit_flag=False,
        archive_after_years=5,
        enable_timer_flag=False,
        enable_leave_integration_flag=False,
        enable_copy_previous_week_flag=False,
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_employee(
    *,
    employee_code: str,
    full_name: str,
    email: str,
    primary_business_unit: BusinessUnit,
    active: bool = True,
) -> Employee:
    normalized_email = email.strip().lower()
    return Employee.objects.create(
        employee_code=employee_code,
        full_name=full_name,
        email=email,
        canonical_email=normalized_email,
        status=ref_value("EMPLOYEE_STATUS", "ACTIVE" if active else "INACTIVE"),
        primary_business_unit=primary_business_unit,
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def assign_employee_to_business_unit(
    *,
    employee: Employee,
    business_unit: BusinessUnit,
    is_primary_flag: bool = False,
) -> EmployeeBusinessUnit:
    return EmployeeBusinessUnit.objects.create(
        employee=employee,
        business_unit=business_unit,
        is_primary_flag=is_primary_flag,
        status=ref_value("EMPLOYEE_BU_STATUS", "ACTIVE"),
        valid_from=date.today(),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def assign_role(
    *,
    employee: Employee,
    role_code: str,
    business_unit: BusinessUnit | None = None,
) -> EmployeeRole:
    return EmployeeRole.objects.create(
        employee=employee,
        role=ref_value("ROLE_CODE", role_code),
        business_unit=business_unit,
        valid_from=date.today(),
        status=ref_value("ROLE_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_client(
    *,
    business_unit: BusinessUnit,
    client_code: str,
    name: str,
    parent_client: ClientRecord | None = None,
    active: bool = True,
) -> ClientRecord:
    return ClientRecord.objects.create(
        business_unit=business_unit,
        parent_client=parent_client,
        client_code=client_code,
        name=name,
        status=ref_value("CLIENT_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_internal_category(
    *,
    business_unit: BusinessUnit,
    category_code: str,
    name: str,
    description: str = "",
    active: bool = True,
) -> InternalCategoryRecord:
    return InternalCategoryRecord.objects.create(
        business_unit=business_unit,
        category_code=category_code,
        name=name,
        description=description,
        status=ref_value("INTERNAL_CATEGORY_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_cost_center(
    *,
    business_unit: BusinessUnit,
    cost_center_code: str,
    name: str,
    description: str = "",
    active: bool = True,
) -> CostCenterRecord:
    return CostCenterRecord.objects.create(
        business_unit=business_unit,
        cost_center_code=cost_center_code,
        name=name,
        description=description,
        status=ref_value("COST_CENTER_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_general_charge_code(
    *,
    business_unit: BusinessUnit,
    code: str,
    name: str,
    valid_from: date,
    valid_to: date | None = None,
    charge_type_code: str = "STANDARD",
    billable_flag: bool = False,
    common_code_flag: bool = False,
    requires_approval_flag: bool = False,
    description_required_flag: bool = False,
    active: bool = True,
) -> GeneralChargeCodeRecord:
    return GeneralChargeCodeRecord.objects.create(
        business_unit=business_unit,
        code=code,
        name=name,
        charge_type=ref_value("GENERAL_CHARGE_CODE_TYPE", charge_type_code),
        billable_flag=billable_flag,
        common_code_flag=common_code_flag,
        requires_approval_flag=requires_approval_flag,
        description_required_flag=description_required_flag,
        valid_from=valid_from,
        valid_to=valid_to,
        status=ref_value("GENERAL_CHARGE_CODE_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_yearly_calendar(
    *,
    business_unit: BusinessUnit,
    calendar_year: int,
    calendar_name: str,
) -> YearlyCalendar:
    return YearlyCalendar.objects.create(
        business_unit=business_unit,
        calendar_year=calendar_year,
        calendar_name=calendar_name,
        status=ref_value("CALENDAR_STATUS", "ACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_calendar_period_rule(
    *,
    yearly_calendar: YearlyCalendar,
    effective_from: date,
    effective_to: date,
    monday_max_hours: str = "8.00",
    tuesday_max_hours: str = "8.00",
    wednesday_max_hours: str = "8.00",
    thursday_max_hours: str = "8.00",
    friday_max_hours: str = "8.00",
) -> CalendarPeriodRule:
    return CalendarPeriodRule.objects.create(
        yearly_calendar=yearly_calendar,
        effective_from=effective_from,
        effective_to=effective_to,
        monday_max_hours=monday_max_hours,
        tuesday_max_hours=tuesday_max_hours,
        wednesday_max_hours=wednesday_max_hours,
        thursday_max_hours=thursday_max_hours,
        friday_max_hours=friday_max_hours,
        status=ref_value("CALENDAR_PERIOD_STATUS", "ACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def assign_calendar(*, employee: Employee, yearly_calendar: YearlyCalendar) -> None:
    employee.assigned_calendar = yearly_calendar
    employee.updated_by = SYSTEM_ACTOR
    employee.save(update_fields=["assigned_calendar", "updated_by", "updated_at"])


def create_project(
    *,
    business_unit: BusinessUnit,
    project_code: str,
    name: str,
    project_owner_employee: Employee,
    project_manager_employee: Employee,
    client: ClientRecord,
    internal_category: InternalCategoryRecord,
    cost_center: CostCenterRecord,
    start_date: date,
    end_date: date | None = None,
    close_date: date | None = None,
    billable_flag: bool = False,
    active: bool = True,
) -> Project:
    return Project.objects.create(
        business_unit=business_unit,
        project_code=project_code,
        name=name,
        description="",
        project_owner_employee=project_owner_employee,
        project_manager_employee=project_manager_employee,
        client=client,
        internal_category=internal_category,
        cost_center=cost_center,
        start_date=start_date,
        end_date=end_date,
        close_date=close_date,
        billable_flag=billable_flag,
        status=ref_value("PROJECT_STATUS", "ACTIVE" if active else "CLOSED"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def assign_project(
    *,
    project: Project,
    employee: Employee,
    assignment_start_date: date,
    assignment_end_date: date | None = None,
    active: bool = True,
) -> ProjectAssignment:
    return ProjectAssignment.objects.create(
        project=project,
        employee=employee,
        assignment_start_date=assignment_start_date,
        assignment_end_date=assignment_end_date,
        status=ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )
