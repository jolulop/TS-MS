from django.db import models


class AuditLog(models.Model):
    event_timestamp = models.DateTimeField()
    actor_employee = models.ForeignKey(
        "master_data.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_email = models.EmailField(max_length=320, blank=True)
    entity_name = models.CharField(max_length=100)
    entity_id = models.BigIntegerField(null=True, blank=True)
    action_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    field_name = models.CharField(max_length=100, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    reason_text = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=100, blank=True)
    business_unit = models.ForeignKey(
        "master_data.BusinessUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-event_timestamp", "-id"]
        indexes = [
            models.Index(fields=["entity_name", "entity_id"], name="audit_log_entity_idx"),
            models.Index(fields=["actor_employee"], name="audit_log_actor_idx"),
        ]
