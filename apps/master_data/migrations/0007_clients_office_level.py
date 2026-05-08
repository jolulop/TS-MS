from django.db import migrations, models
from django.db.models import Count


def validate_unique_client_codes_per_office(apps, schema_editor):
    Client = apps.get_model("master_data", "Client")
    duplicates = list(
        Client.objects.values("office_id", "client_code")
        .annotate(client_count=Count("id"))
        .filter(client_count__gt=1)
        .order_by("office_id", "client_code")
    )
    if duplicates:
        duplicate_summary = ", ".join(
            f"office_id={row['office_id']} client_code={row['client_code']}"
            for row in duplicates[:10]
        )
        raise RuntimeError(
            "Cannot migrate Clients to Office-level uniqueness because duplicate "
            f"client codes exist within the same Office: {duplicate_summary}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0006_office_configuration_inheritance"),
    ]

    operations = [
        migrations.RunPython(
            validate_unique_client_codes_per_office,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="client",
            name="client_bu_client_code_uniq",
        ),
        migrations.AlterModelOptions(
            name="client",
            options={"ordering": ["client_code"]},
        ),
        migrations.AddConstraint(
            model_name="client",
            constraint=models.UniqueConstraint(
                fields=("office", "client_code"),
                name="client_office_client_code_uniq",
            ),
        ),
        migrations.RemoveField(
            model_name="client",
            name="business_unit",
        ),
    ]
