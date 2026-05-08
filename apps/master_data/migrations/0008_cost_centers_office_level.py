from django.db import migrations, models
from django.db.models import Count


def validate_unique_cost_center_codes_per_office(apps, schema_editor):
    CostCenter = apps.get_model("master_data", "CostCenter")
    duplicates = list(
        CostCenter.objects.values("office_id", "cost_center_code")
        .annotate(cost_center_count=Count("id"))
        .filter(cost_center_count__gt=1)
        .order_by("office_id", "cost_center_code")
    )
    if duplicates:
        duplicate_summary = ", ".join(
            f"office_id={row['office_id']} cost_center_code={row['cost_center_code']}"
            for row in duplicates[:10]
        )
        raise RuntimeError(
            "Cannot migrate Cost Centers to Office-level uniqueness because duplicate "
            f"cost center codes exist within the same Office: {duplicate_summary}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0007_clients_office_level"),
    ]

    operations = [
        migrations.RunPython(
            validate_unique_cost_center_codes_per_office,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="costcenter",
            name="cost_center_bu_code_uniq",
        ),
        migrations.AlterModelOptions(
            name="costcenter",
            options={"ordering": ["cost_center_code"]},
        ),
        migrations.AddConstraint(
            model_name="costcenter",
            constraint=models.UniqueConstraint(
                fields=("office", "cost_center_code"),
                name="cost_center_office_code_uniq",
            ),
        ),
        migrations.RemoveField(
            model_name="costcenter",
            name="business_unit",
        ),
    ]
