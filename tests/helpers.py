from datetime import date

from django.core.management import call_command
from django.test import Client

from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    CalendarSpecialDay,
    Country,
    CrossOfficeProjectAssignment,
    Employee,
    EmployeeBusinessUnit,
    GeneralChargeCodeApprovalRole,
    GeneralChargeCodeApprovalRoleAssignment,
    GeneralChargeCodeApproverRole,
    EmployeeRole,
    Office,
    OfficeConfiguration,
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
from apps.master_data.models import (
    PricingModel as PricingModelRecord,
)
from apps.reference_data.models import RefValue

SYSTEM_ACTOR = "system@test.local"


def seed_reference_data() -> None:
    call_command("seed_reference_data")


def initialize_ui_session(client: Client, validated_email: str) -> None:
    response = client.post("/", data={"validated_email": validated_email}, follow=False)
    assert response.status_code == 302


def ref_value(domain_code: str, value_code: str) -> RefValue:
    return RefValue.objects.get(domain__domain_code=domain_code, value_code=value_code)


def get_office(office_name: str = "Holding") -> Office:
    return Office.objects.get(office_name=office_name)


def create_country(
    *,
    country_code: str,
    country_name: str,
    active: bool = True,
) -> Country:
    return Country.objects.create(
        country_code=country_code,
        country_name=country_name,
        status=ref_value("COUNTRY_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_office(
    *,
    office_name: str,
    active: bool = True,
    country: Country | None = None,
) -> Office:
    resolved_country = country
    if resolved_country is None:
        resolved_country = Country.objects.filter(country_name="Holding").first()
        if resolved_country is None:
            resolved_country = create_country(
                country_code="HOLDING",
                country_name="Holding",
                active=True,
            )
    office = Office.objects.create(
        country=resolved_country,
        office_name=office_name,
        status=ref_value("COUNTRY_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )
    create_office_configuration(office=office)
    return office


def create_office_configuration(
    *,
    office: Office,
    approval_mode_code: str = "PROJECT",
    allow_employee_withdraw_flag: bool = False,
    timesheet_cutoff_date: date | None = None,
) -> OfficeConfiguration:
    return OfficeConfiguration.objects.update_or_create(
        office=office,
        defaults={
            "approval_mode": ref_value("APPROVAL_MODE", approval_mode_code),
            "allow_employee_withdraw_flag": allow_employee_withdraw_flag,
            "timesheet_cutoff_date": timesheet_cutoff_date,
            "count_non_billable_in_daily_limit_flag": False,
            "archive_after_years": 5,
            "enable_timer_flag": False,
            "enable_leave_integration_flag": False,
            "enable_copy_previous_week_flag": False,
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )[0]


def create_business_unit(
    *,
    bu_code: str,
    name: str,
    office: Office | None = None,
) -> BusinessUnit:
    return BusinessUnit.objects.create(
        bu_code=bu_code,
        name=name,
        description="",
        office=office or get_office(),
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
) -> OfficeConfiguration:
    return create_office_configuration(
        office=business_unit.office,
        approval_mode_code=approval_mode_code,
        allow_employee_withdraw_flag=allow_employee_withdraw_flag,
        timesheet_cutoff_date=timesheet_cutoff_date,
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
        office=primary_business_unit.office,
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


def create_general_charge_code_approval_role(
    *,
    office: Office | None = None,
    role_code: str,
    name: str,
    description: str = "",
    active: bool = True,
) -> GeneralChargeCodeApprovalRole:
    resolved_office = office or get_office()
    return GeneralChargeCodeApprovalRole.objects.create(
        office=resolved_office,
        role_code=role_code,
        name=name,
        description=description,
        status=ref_value(
            "GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
            "ACTIVE" if active else "INACTIVE",
        ),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def assign_general_charge_code_approval_role(
    *,
    employee: Employee,
    approval_role: GeneralChargeCodeApprovalRole,
) -> GeneralChargeCodeApprovalRoleAssignment:
    return GeneralChargeCodeApprovalRoleAssignment.objects.create(
        approval_role=approval_role,
        employee=employee,
        valid_from=date.today(),
        status=ref_value("ROLE_ASSIGNMENT_STATUS", "ACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_client(
    *,
    business_unit: BusinessUnit | None = None,
    office: Office | None = None,
    client_code: str,
    name: str,
    parent_client: ClientRecord | None = None,
    active: bool = True,
) -> ClientRecord:
    client_office = office or (business_unit.office if business_unit is not None else get_office())
    return ClientRecord.objects.create(
        office=client_office,
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
        office=business_unit.office,
        category_code=category_code,
        name=name,
        description=description,
        status=ref_value("INTERNAL_CATEGORY_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_cost_center(
    *,
    business_unit: BusinessUnit | None = None,
    office: Office | None = None,
    cost_center_code: str,
    name: str,
    description: str = "",
    active: bool = True,
) -> CostCenterRecord:
    cost_center_office = office or (
        business_unit.office if business_unit is not None else get_office()
    )
    return CostCenterRecord.objects.create(
        office=cost_center_office,
        cost_center_code=cost_center_code,
        name=name,
        description=description,
        status=ref_value("COST_CENTER_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_pricing_model(
    *,
    business_unit: BusinessUnit | None = None,
    office: Office | None = None,
    name: str,
    description: str = "",
) -> PricingModelRecord:
    pricing_model_office = office or (
        business_unit.office if business_unit is not None else get_office()
    )
    return PricingModelRecord.objects.create(
        office=pricing_model_office,
        name=name,
        description=description,
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )


def create_general_charge_code(
    *,
    business_unit: BusinessUnit,
    code: str,
    name: str,
    cost_center: CostCenterRecord | None = None,
    valid_from: date,
    valid_to: date | None = None,
    charge_type_code: str = "STANDARD",
    billable_flag: bool = False,
    requires_approval_flag: bool = False,
    description_required_flag: bool = False,
    active: bool = True,
    approver_role_codes: list[str] | None = None,
    ad_hoc_approval_roles: list[GeneralChargeCodeApprovalRole] | None = None,
) -> GeneralChargeCodeRecord:
    resolved_cost_center = cost_center or CostCenterRecord.objects.filter(
        office=business_unit.office
    ).order_by("cost_center_code", "id").first()
    if resolved_cost_center is None:
        resolved_cost_center = create_cost_center(
            business_unit=business_unit,
            cost_center_code=f"CC-{business_unit.bu_code}",
            name=f"{business_unit.name} Cost Center",
            description="Auto-generated test cost center for General Charge Code helpers.",
        )
    general_charge_code = GeneralChargeCodeRecord.objects.create(
        business_unit=business_unit,
        office=business_unit.office,
        code=code,
        name=name,
        charge_type=ref_value("GENERAL_CHARGE_CODE_TYPE", charge_type_code),
        cost_center=resolved_cost_center,
        billable_flag=billable_flag,
        requires_approval_flag=requires_approval_flag,
        description_required_flag=description_required_flag,
        valid_from=valid_from,
        valid_to=valid_to,
        status=ref_value("GENERAL_CHARGE_CODE_STATUS", "ACTIVE" if active else "INACTIVE"),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )
    for role_code in approver_role_codes or []:
        GeneralChargeCodeApproverRole.objects.create(
            general_charge_code=general_charge_code,
            existing_role=ref_value("ROLE_CODE", role_code),
            created_by=SYSTEM_ACTOR,
            updated_by=SYSTEM_ACTOR,
        )
    for approval_role in ad_hoc_approval_roles or []:
        GeneralChargeCodeApproverRole.objects.create(
            general_charge_code=general_charge_code,
            approval_role=approval_role,
            created_by=SYSTEM_ACTOR,
            updated_by=SYSTEM_ACTOR,
        )
    return general_charge_code


def create_yearly_calendar(
    *,
    business_unit: BusinessUnit | None = None,
    office: Office | None = None,
    calendar_year: int,
    calendar_name: str,
) -> YearlyCalendar:
    calendar_office = (
        office or (business_unit.office if business_unit is not None else get_office())
    )
    calendar = YearlyCalendar.objects.update_or_create(
        office=calendar_office,
        calendar_year=calendar_year,
        defaults={
            "calendar_name": calendar_name,
            "status": ref_value("CALENDAR_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )[0]
    if business_unit is not None:
        calendar._default_business_unit_id = business_unit.id
    return calendar


def create_calendar_period_rule(
    *,
    yearly_calendar: YearlyCalendar,
    business_unit: BusinessUnit | None = None,
    effective_from: date,
    effective_to: date,
    monday_max_hours: str = "8.00",
    tuesday_max_hours: str = "8.00",
    wednesday_max_hours: str = "8.00",
    thursday_max_hours: str = "8.00",
    friday_max_hours: str = "8.00",
    working_on_saturdays_flag: bool = False,
    working_on_sundays_flag: bool = False,
    saturday_max_hours: str = "0.00",
    sunday_max_hours: str = "0.00",
) -> CalendarPeriodRule:
    if business_unit is None:
        default_business_unit_id = getattr(yearly_calendar, "_default_business_unit_id", None)
        if default_business_unit_id is not None:
            business_unit = BusinessUnit.objects.get(id=default_business_unit_id)
        else:
            business_unit = yearly_calendar.office.business_units.order_by("id").first()
    if business_unit is None:
        raise ValueError("Calendar Period Rule helper requires an Office Business Unit.")
    return CalendarPeriodRule.objects.update_or_create(
        yearly_calendar=yearly_calendar,
        business_unit=business_unit,
        effective_from=effective_from,
        effective_to=effective_to,
        defaults={
            "business_unit": business_unit,
            "office": yearly_calendar.office,
            "monday_max_hours": monday_max_hours,
            "tuesday_max_hours": tuesday_max_hours,
            "wednesday_max_hours": wednesday_max_hours,
            "thursday_max_hours": thursday_max_hours,
            "friday_max_hours": friday_max_hours,
            "working_on_saturdays_flag": working_on_saturdays_flag,
            "working_on_sundays_flag": working_on_sundays_flag,
            "saturday_max_hours": saturday_max_hours,
            "sunday_max_hours": sunday_max_hours,
            "status": ref_value("CALENDAR_PERIOD_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )[0]


def create_calendar_special_day(
    *,
    yearly_calendar: YearlyCalendar,
    special_date: date,
    day_type_code: str = "NATIONAL_HOLIDAY",
    active: bool = True,
) -> CalendarSpecialDay:
    return CalendarSpecialDay.objects.create(
        yearly_calendar=yearly_calendar,
        special_date=special_date,
        day_type=ref_value("SPECIAL_DAY_TYPE", day_type_code),
        name=f"{day_type_code} {special_date.isoformat()}",
        status=ref_value("SPECIAL_DAY_STATUS", "ACTIVE" if active else "INACTIVE"),
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
    pricing_model: PricingModelRecord | None = None,
    start_date: date,
    end_date: date | None = None,
    close_date: date | None = None,
    billable_flag: bool = False,
    active: bool = True,
) -> Project:
    resolved_pricing_model = pricing_model or create_pricing_model(
        business_unit=business_unit,
        name=f"Pricing Model {project_code}",
        description="Default pricing model for test project helpers.",
    )
    return Project.objects.create(
        business_unit=business_unit,
        office=business_unit.office,
        project_code=project_code,
        name=name,
        description="",
        project_owner_employee=project_owner_employee,
        project_manager_employee=project_manager_employee,
        client=client,
        internal_category=internal_category,
        cost_center=cost_center,
        pricing_model=resolved_pricing_model,
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


def assign_cross_office_project(
    *,
    project: Project,
    employee: Employee,
    assignment_start_date: date,
    assignment_end_date: date | None = None,
    justification_text: str = "",
    active: bool = True,
) -> CrossOfficeProjectAssignment:
    return CrossOfficeProjectAssignment.objects.create(
        project=project,
        employee=employee,
        origin_office=employee.office,
        origin_business_unit=employee.primary_business_unit,
        assignment_start_date=assignment_start_date,
        assignment_end_date=assignment_end_date,
        justification_text=justification_text,
        status=ref_value(
            "PROJECT_ASSIGNMENT_STATUS",
            "ACTIVE" if active else "INACTIVE",
        ),
        created_by=SYSTEM_ACTOR,
        updated_by=SYSTEM_ACTOR,
    )
