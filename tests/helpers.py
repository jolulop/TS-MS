from datetime import date

from django.core.management import call_command

from apps.master_data.models import (
    BusinessUnit,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
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
