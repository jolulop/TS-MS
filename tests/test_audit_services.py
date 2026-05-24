import pytest

from apps.audit.models import AuditLog
from apps.audit.services import write_audit_event
from tests.helpers import seed_reference_data


@pytest.mark.django_db
def test_write_audit_event_persists_optional_correlation_id() -> None:
    seed_reference_data()

    write_audit_event(
        action_code="UPDATE",
        entity_name="audit_test_entity",
        entity_id=42,
        actor_email="auditor@example.com",
        field_name="example_field",
        old_value="before",
        new_value="after",
        reason_text="Audit service correlation test.",
        correlation_id="phase-6-correlation",
    )

    audit_event = AuditLog.objects.get(entity_name="audit_test_entity")
    assert audit_event.correlation_id == "phase-6-correlation"
