from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.master_data.models import (
    BusinessUnit,
    CalendarPeriodRule,
    Client,
    CostCenter,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    GeneralChargeCode,
    InternalCategory,
    Office,
    OfficeConfiguration,
    PricingModel,
    Project,
    ProjectAssignment,
    YearlyCalendar,
)
from apps.reference_data.models import RefValue

SYSTEM_ACTOR = "seed-dev@local"
SEED_VALID_FROM = date(2026, 1, 1)
CURRENT_YEAR = 2026


def _ref_value(domain_code: str, value_code: str) -> RefValue:
    return RefValue.objects.get(domain__domain_code=domain_code, value_code=value_code)


def _upsert_country(*, office_id: int, office_name: str, active: bool) -> Office:
    office, _ = Office.objects.update_or_create(
        id=office_id,
        defaults={
            "office_name": office_name,
            "status": _ref_value("COUNTRY_STATUS", "ACTIVE" if active else "INACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return office


def _upsert_business_unit(
    *,
    office: Office,
    bu_code: str,
    name: str,
    description: str,
) -> BusinessUnit:
    business_unit, _ = BusinessUnit.objects.update_or_create(
        bu_code=bu_code,
        defaults={
            "name": name,
            "description": description,
            "office": office,
            "status": _ref_value("BUSINESS_UNIT_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return business_unit


def _upsert_office_configuration(office: Office) -> None:
    OfficeConfiguration.objects.update_or_create(
        office=office,
        defaults={
            "approval_mode": _ref_value("APPROVAL_MODE", "PROJECT"),
            "allow_employee_withdraw_flag": False,
            "timesheet_cutoff_date": None,
            "count_non_billable_in_daily_limit_flag": False,
            "archive_after_years": 5,
            "enable_timer_flag": False,
            "enable_leave_integration_flag": False,
            "enable_copy_previous_week_flag": False,
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )


def _upsert_calendar(business_unit: BusinessUnit, *, calendar_name: str) -> YearlyCalendar:
    calendar, _ = YearlyCalendar.objects.update_or_create(
        business_unit=business_unit,
        calendar_year=CURRENT_YEAR,
        calendar_name=calendar_name,
        defaults={
            "office": business_unit.office,
            "status": _ref_value("CALENDAR_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    CalendarPeriodRule.objects.update_or_create(
        yearly_calendar=calendar,
        effective_from=date(CURRENT_YEAR, 1, 1),
        effective_to=date(CURRENT_YEAR, 12, 31),
        defaults={
            "office": business_unit.office,
            "monday_max_hours": "8.00",
            "tuesday_max_hours": "8.00",
            "wednesday_max_hours": "8.00",
            "thursday_max_hours": "8.00",
            "friday_max_hours": "8.00",
            "status": _ref_value("CALENDAR_PERIOD_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return calendar


def _upsert_employee(
    *,
    employee_code: str,
    full_name: str,
    email: str,
    primary_business_unit: BusinessUnit,
    assigned_calendar: YearlyCalendar,
    manager_employee: Employee | None = None,
) -> Employee:
    employee, _ = Employee.objects.update_or_create(
        employee_code=employee_code,
        defaults={
            "full_name": full_name,
            "email": email,
            "canonical_email": email.strip().lower(),
            "office": primary_business_unit.office,
            "status": _ref_value("EMPLOYEE_STATUS", "ACTIVE"),
            "primary_business_unit": primary_business_unit,
            "manager_employee": manager_employee,
            "assigned_calendar": assigned_calendar,
            "employment_start_date": SEED_VALID_FROM,
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return employee


def _upsert_employee_business_unit(
    *,
    employee: Employee,
    business_unit: BusinessUnit,
    is_primary_flag: bool,
) -> None:
    EmployeeBusinessUnit.objects.update_or_create(
        employee=employee,
        business_unit=business_unit,
        valid_from=SEED_VALID_FROM,
        defaults={
            "is_primary_flag": is_primary_flag,
            "status": _ref_value("EMPLOYEE_BU_STATUS", "ACTIVE"),
            "valid_to": None,
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )


def _upsert_employee_role(*, employee: Employee, role_code: str) -> None:
    EmployeeRole.objects.update_or_create(
        employee=employee,
        role=_ref_value("ROLE_CODE", role_code),
        business_unit=None,
        valid_from=SEED_VALID_FROM,
        defaults={
            "valid_to": None,
            "status": _ref_value("ROLE_ASSIGNMENT_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )


def _upsert_client(*, business_unit: BusinessUnit, client_code: str, name: str) -> Client:
    client, _ = Client.objects.update_or_create(
        office=business_unit.office,
        client_code=client_code,
        defaults={
            "name": name,
            "parent_client": None,
            "status": _ref_value("CLIENT_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return client


def _upsert_internal_category(
    *,
    business_unit: BusinessUnit,
    category_code: str,
    name: str,
    description: str,
) -> InternalCategory:
    category, _ = InternalCategory.objects.update_or_create(
        business_unit=business_unit,
        category_code=category_code,
        defaults={
            "office": business_unit.office,
            "name": name,
            "description": description,
            "status": _ref_value("INTERNAL_CATEGORY_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return category


def _upsert_cost_center(
    *,
    business_unit: BusinessUnit,
    cost_center_code: str,
    name: str,
    description: str,
) -> CostCenter:
    cost_center, _ = CostCenter.objects.update_or_create(
        office=business_unit.office,
        cost_center_code=cost_center_code,
        defaults={
            "name": name,
            "description": description,
            "status": _ref_value("COST_CENTER_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return cost_center


def _upsert_pricing_model(
    *,
    office: Office,
    name: str,
    description: str,
) -> PricingModel:
    pricing_model, _ = PricingModel.objects.update_or_create(
        office=office,
        name=name,
        defaults={
            "description": description,
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return pricing_model


def _upsert_general_charge_code(
    *,
    business_unit: BusinessUnit,
    code: str,
    name: str,
    billable_flag: bool,
    common_code_flag: bool,
    requires_approval_flag: bool,
    description_required_flag: bool,
) -> GeneralChargeCode:
    general_charge_code, _ = GeneralChargeCode.objects.update_or_create(
        business_unit=business_unit,
        code=code,
        defaults={
            "office": business_unit.office,
            "name": name,
            "charge_type": _ref_value("GENERAL_CHARGE_CODE_TYPE", "STANDARD"),
            "billable_flag": billable_flag,
            "common_code_flag": common_code_flag,
            "requires_approval_flag": requires_approval_flag,
            "description_required_flag": description_required_flag,
            "valid_from": SEED_VALID_FROM,
            "valid_to": None,
            "status": _ref_value("GENERAL_CHARGE_CODE_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return general_charge_code


def _upsert_project(
    *,
    business_unit: BusinessUnit,
    project_code: str,
    name: str,
    project_owner_employee: Employee,
    project_manager_employee: Employee,
    client: Client,
    internal_category: InternalCategory,
    cost_center: CostCenter,
    pricing_model: PricingModel,
) -> Project:
    project, _ = Project.objects.update_or_create(
        business_unit=business_unit,
        project_code=project_code,
        defaults={
            "office": business_unit.office,
            "name": name,
            "description": "Development sample project for local UI exploration.",
            "project_owner_employee": project_owner_employee,
            "project_manager_employee": project_manager_employee,
            "client": client,
            "internal_category": internal_category,
            "cost_center": cost_center,
            "pricing_model": pricing_model,
            "start_date": SEED_VALID_FROM,
            "end_date": None,
            "close_date": None,
            "billable_flag": True,
            "status": _ref_value("PROJECT_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )
    return project


def _upsert_project_assignment(*, project: Project, employee: Employee) -> None:
    ProjectAssignment.objects.update_or_create(
        project=project,
        employee=employee,
        assignment_start_date=SEED_VALID_FROM,
        defaults={
            "assignment_end_date": None,
            "status": _ref_value("PROJECT_ASSIGNMENT_STATUS", "ACTIVE"),
            "created_by": SYSTEM_ACTOR,
            "updated_by": SYSTEM_ACTOR,
        },
    )


class Command(BaseCommand):
    help = "Load local developer sample data for browsing the TS UI."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        call_command("seed_reference_data")

        holding_country = _upsert_country(office_id=1, office_name="Holding", active=True)
        _upsert_country(office_id=2, office_name="España", active=True)
        _upsert_country(office_id=3, office_name="Colombia", active=True)
        _upsert_country(office_id=4, office_name="Perú", active=True)
        _upsert_country(office_id=5, office_name="Argentina", active=True)
        _upsert_country(office_id=6, office_name="México", active=False)
        for office in Office.objects.all():
            _upsert_office_configuration(office)

        consulting_bu = _upsert_business_unit(
            office=holding_country,
            bu_code="CONSULTING",
            name="Consulting",
            description="Primary local sample Business Unit.",
        )
        delivery_bu = _upsert_business_unit(
            office=holding_country,
            bu_code="DELIVERY",
            name="Delivery",
            description="Secondary local sample Business Unit.",
        )

        consulting_calendar = _upsert_calendar(
            consulting_bu,
            calendar_name="Consulting Standard 2026",
        )
        _upsert_calendar(
            delivery_bu,
            calendar_name="Delivery Standard 2026",
        )

        ts_admin = _upsert_employee(
            employee_code="EMP-ADMIN-001",
            full_name="Jose Luis Lopez",
            email="jose.luis.lopez@timia.ai",
            primary_business_unit=consulting_bu,
            assigned_calendar=consulting_calendar,
        )
        ts_admin_master = _upsert_employee(
            employee_code="EMP-MASTER-001",
            full_name="Office Master Admin",
            email="office.master@timia.ai",
            primary_business_unit=consulting_bu,
            assigned_calendar=consulting_calendar,
            manager_employee=ts_admin,
        )
        project_owner = _upsert_employee(
            employee_code="EMP-PO-001",
            full_name="Paula Owner",
            email="paula.owner@timia.ai",
            primary_business_unit=consulting_bu,
            assigned_calendar=consulting_calendar,
            manager_employee=ts_admin,
        )
        project_manager = _upsert_employee(
            employee_code="EMP-PM-001",
            full_name="Miguel Manager",
            email="miguel.manager@timia.ai",
            primary_business_unit=consulting_bu,
            assigned_calendar=consulting_calendar,
            manager_employee=project_owner,
        )
        standard_user = _upsert_employee(
            employee_code="EMP-USER-001",
            full_name="Ana Consultant",
            email="ana.consultant@timia.ai",
            primary_business_unit=consulting_bu,
            assigned_calendar=consulting_calendar,
            manager_employee=project_manager,
        )

        _upsert_employee_business_unit(
            employee=ts_admin,
            business_unit=consulting_bu,
            is_primary_flag=True,
        )
        _upsert_employee_business_unit(
            employee=ts_admin,
            business_unit=delivery_bu,
            is_primary_flag=False,
        )
        _upsert_employee_business_unit(
            employee=ts_admin_master,
            business_unit=consulting_bu,
            is_primary_flag=True,
        )
        for employee in (project_owner, project_manager, standard_user):
            _upsert_employee_business_unit(
                employee=employee,
                business_unit=consulting_bu,
                is_primary_flag=True,
            )

        for role_code in ("USER", "TS_ADMIN"):
            _upsert_employee_role(employee=ts_admin, role_code=role_code)
        _upsert_employee_role(employee=ts_admin_master, role_code="TS_ADMIN_MASTER")
        for role_code in ("USER", "PROJECT_OWNER"):
            _upsert_employee_role(employee=project_owner, role_code=role_code)
        for role_code in ("USER", "PROJECT_MANAGER"):
            _upsert_employee_role(employee=project_manager, role_code=role_code)
        _upsert_employee_role(employee=standard_user, role_code="USER")

        client_blue = _upsert_client(
            business_unit=consulting_bu,
            client_code="CLI-BLUE",
            name="Blue Ocean Holdings",
        )
        _upsert_client(
            business_unit=delivery_bu,
            client_code="CLI-GREEN",
            name="Green Valley Logistics",
        )

        category_delivery = _upsert_internal_category(
            business_unit=consulting_bu,
            category_code="IC-DELIVERY",
            name="Delivery Work",
            description="Billable delivery category for local demo data.",
        )
        _upsert_internal_category(
            business_unit=delivery_bu,
            category_code="IC-SUPPORT",
            name="Support Work",
            description="Support category for secondary BU sample data.",
        )

        cost_center_consulting = _upsert_cost_center(
            business_unit=consulting_bu,
            cost_center_code="CC-1000",
            name="Consulting Revenue",
            description="Primary consulting cost center.",
        )
        _upsert_cost_center(
            business_unit=delivery_bu,
            cost_center_code="CC-2000",
            name="Delivery Operations",
            description="Secondary BU cost center.",
        )
        pricing_model_standard = _upsert_pricing_model(
            office=holding_country,
            name="Time and Materials",
            description="Default sample pricing model for seeded projects.",
        )

        _upsert_general_charge_code(
            business_unit=consulting_bu,
            code="GCC-ADMIN",
            name="Administrative Time",
            billable_flag=False,
            common_code_flag=True,
            requires_approval_flag=False,
            description_required_flag=False,
        )
        _upsert_general_charge_code(
            business_unit=consulting_bu,
            code="GCC-TRAIN",
            name="Training Time",
            billable_flag=False,
            common_code_flag=False,
            requires_approval_flag=False,
            description_required_flag=True,
        )
        _upsert_general_charge_code(
            business_unit=delivery_bu,
            code="GCC-DELIVERY",
            name="Delivery Overhead",
            billable_flag=False,
            common_code_flag=True,
            requires_approval_flag=False,
            description_required_flag=False,
        )

        project = _upsert_project(
            business_unit=consulting_bu,
            project_code="PRJ-ALPHA",
            name="Project Alpha",
            project_owner_employee=project_owner,
            project_manager_employee=project_manager,
            client=client_blue,
            internal_category=category_delivery,
            cost_center=cost_center_consulting,
            pricing_model=pricing_model_standard,
        )
        _upsert_project_assignment(project=project, employee=standard_user)
        _upsert_project_assignment(project=project, employee=project_manager)

        self.stdout.write(
            self.style.SUCCESS(
                "Developer sample data loaded. TS Admin login email: jose.luis.lopez@timia.ai"
            )
        )
