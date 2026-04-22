import pytest
from django.core.management import call_command

from apps.master_data.models import (
    BusinessUnit,
    Client,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    GeneralChargeCode,
    InternalCategory,
    Project,
    ProjectAssignment,
)


@pytest.mark.django_db
def test_seed_dev_data_creates_expected_sample_records() -> None:
    call_command("seed_dev_data")

    admin_employee = Employee.objects.get(canonical_email="jose.luis.lopez@timia.ai")

    assert BusinessUnit.objects.filter(bu_code="CONSULTING").exists()
    assert BusinessUnit.objects.filter(bu_code="DELIVERY").exists()
    assert admin_employee.full_name == "Jose Luis Lopez"
    assert EmployeeRole.objects.filter(
        employee=admin_employee,
        role__value_code="TS_ADMIN",
        valid_to__isnull=True,
    ).exists()
    assert EmployeeBusinessUnit.objects.filter(
        employee=admin_employee,
        business_unit__bu_code="DELIVERY",
        valid_to__isnull=True,
    ).exists()
    assert Client.objects.filter(client_code="CLI-BLUE").exists()
    assert InternalCategory.objects.filter(category_code="IC-DELIVERY").exists()
    assert GeneralChargeCode.objects.filter(code="GCC-ADMIN").exists()
    assert Project.objects.filter(project_code="PRJ-ALPHA").exists()
    assert ProjectAssignment.objects.filter(project__project_code="PRJ-ALPHA").count() == 2


@pytest.mark.django_db
def test_seed_dev_data_is_idempotent() -> None:
    call_command("seed_dev_data")
    call_command("seed_dev_data")

    assert BusinessUnit.objects.filter(bu_code__in=["CONSULTING", "DELIVERY"]).count() == 2
    assert (
        Employee.objects.filter(
            employee_code__in=[
                "EMP-ADMIN-001",
                "EMP-PO-001",
                "EMP-PM-001",
                "EMP-USER-001",
            ]
        ).count()
        == 4
    )
    assert Client.objects.filter(client_code__in=["CLI-BLUE", "CLI-GREEN"]).count() == 2
    assert (
        GeneralChargeCode.objects.filter(
            code__in=["GCC-ADMIN", "GCC-TRAIN", "GCC-DELIVERY"]
        ).count()
        == 3
    )
    assert Project.objects.filter(project_code="PRJ-ALPHA").count() == 1
