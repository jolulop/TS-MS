from django.db import models

from apps.common.models import CreatedAuditModel


class IntegrationJob(CreatedAuditModel):
    business_unit = models.ForeignKey(
        "master_data.BusinessUnit",
        on_delete=models.PROTECT,
        related_name="integration_jobs",
    )
    interface_code = models.CharField(max_length=100)
    direction = models.CharField(max_length=20)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    requested_by_employee = models.ForeignKey(
        "master_data.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="requested_integration_jobs",
    )
    total_records = models.PositiveIntegerField(default=0)
    success_records = models.PositiveIntegerField(default=0)
    error_records = models.PositiveIntegerField(default=0)
    payload_reference = models.CharField(max_length=255, blank=True)
    summary_message = models.TextField(blank=True)

    class Meta:
        db_table = "integration_job"
        ordering = ["-created_at", "interface_code"]


class IntegrationJobError(models.Model):
    integration_job = models.ForeignKey(
        IntegrationJob,
        on_delete=models.PROTECT,
        related_name="errors",
    )
    row_no = models.PositiveIntegerField(null=True, blank=True)
    entity_name = models.CharField(max_length=100)
    external_key = models.CharField(max_length=100, blank=True)
    error_code = models.CharField(max_length=100)
    error_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "integration_job_error"
        ordering = ["integration_job", "id"]
