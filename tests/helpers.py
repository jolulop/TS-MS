from datetime import date

from django.core.management import call_command

from apps.master_data.models import (
    BusinessUnit,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
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
