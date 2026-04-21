import pytest
from django.core.management import call_command

from apps.reference_data.models import RefDomain, RefValue
from apps.reference_data.seeds import REFERENCE_DATA


@pytest.mark.django_db
def test_seed_reference_data_creates_expected_values() -> None:
    call_command("seed_reference_data")

    assert RefDomain.objects.filter(domain_code="ROLE_CODE").exists()
    assert RefValue.objects.filter(domain__domain_code="ROLE_CODE", value_code="USER").exists()
    assert RefValue.objects.filter(
        domain__domain_code="TIMESHEET_STATUS",
        value_code="APPROVED",
    ).exists()
    assert RefDomain.objects.count() == len(REFERENCE_DATA)
    assert RefValue.objects.count() == sum(
        len(domain_data["values"]) for domain_data in REFERENCE_DATA.values()
    )


@pytest.mark.django_db
def test_seed_reference_data_is_idempotent() -> None:
    call_command("seed_reference_data")
    call_command("seed_reference_data")

    assert RefDomain.objects.count() == len(REFERENCE_DATA)
    assert RefValue.objects.count() == sum(
        len(domain_data["values"]) for domain_data in REFERENCE_DATA.values()
    )
