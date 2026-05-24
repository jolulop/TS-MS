from django.utils import timezone

from apps.audit.models import AuditLog
from apps.reference_data.models import RefValue


def write_audit_event(
    *,
    action_code: str,
    entity_name: str,
    entity_id: int | None = None,
    actor_employee=None,
    actor_email: str = "",
    business_unit=None,
    field_name: str = "",
    old_value: str = "",
    new_value: str = "",
    reason_text: str = "",
    correlation_id: str = "",
) -> None:
    action_type = RefValue.objects.get(
        domain__domain_code="AUDIT_ACTION_TYPE",
        value_code=action_code,
    )
    AuditLog.objects.create(
        event_timestamp=timezone.now(),
        actor_employee=actor_employee,
        actor_email=actor_email,
        entity_name=entity_name,
        entity_id=entity_id,
        action_type=action_type,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        reason_text=reason_text,
        correlation_id=correlation_id,
        business_unit=business_unit,
    )
