import django.db.models.deletion
from django.db import migrations, models


def backfill_project_pricing_models(apps, schema_editor):
    Office = apps.get_model("master_data", "Office")
    PricingModel = apps.get_model("master_data", "PricingModel")
    Project = apps.get_model("master_data", "Project")

    for office in Office.objects.all():
        office_projects = Project.objects.filter(
            office_id=office.id,
            pricing_model_id__isnull=True,
        )
        if not office_projects.exists():
            continue

        pricing_model, _ = PricingModel.objects.get_or_create(
            office_id=office.id,
            name="Default Pricing Model",
            defaults={
                "description": "Backfilled default pricing model for existing projects.",
                "created_by": "migration-0009",
                "updated_by": "migration-0009",
            },
        )
        office_projects.update(
            pricing_model_id=pricing_model.id,
            updated_by="migration-0009",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0008_cost_centers_office_level"),
    ]

    operations = [
        migrations.CreateModel(
            name="PricingModel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.CharField(max_length=320)),
                ("updated_by", models.CharField(max_length=320)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                (
                    "office",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pricing_models",
                        to="master_data.office",
                    ),
                ),
            ],
            options={
                "db_table": "pricing_model",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="project",
            name="pricing_model",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="projects",
                to="master_data.pricingmodel",
            ),
        ),
        migrations.RunPython(backfill_project_pricing_models, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="project",
            name="pricing_model",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="projects",
                to="master_data.pricingmodel",
            ),
        ),
    ]
