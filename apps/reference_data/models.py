from django.db import models


class RefDomain(models.Model):
    domain_code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    active_flag = models.BooleanField(default=True)

    class Meta:
        db_table = "ref_domain"
        ordering = ["domain_code"]

    def __str__(self) -> str:
        return self.domain_code


class RefValue(models.Model):
    domain = models.ForeignKey(
        RefDomain,
        on_delete=models.PROTECT,
        related_name="values",
    )
    value_code = models.CharField(max_length=100)
    value_label = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    active_flag = models.BooleanField(default=True)
    system_flag = models.BooleanField(default=True)

    class Meta:
        db_table = "ref_value"
        ordering = ["domain__domain_code", "sort_order", "value_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "value_code"],
                name="ref_value_domain_value_code_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.domain.domain_code}:{self.value_code}"
