from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditFieldsModel(TimestampedModel):
    created_by = models.CharField(max_length=320)
    updated_by = models.CharField(max_length=320)

    class Meta:
        abstract = True


class CreatedAuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=320)

    class Meta:
        abstract = True
