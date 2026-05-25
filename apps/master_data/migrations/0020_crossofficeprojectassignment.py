import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reference_data", "0001_initial"),
        ("master_data", "0019_country_entity_for_offices"),
    ]

    operations = [
        migrations.CreateModel(
            name="CrossOfficeProjectAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.CharField(max_length=320)),
                ("updated_by", models.CharField(max_length=320)),
                ("assignment_start_date", models.DateField()),
                ("assignment_end_date", models.DateField(blank=True, null=True)),
                ("justification_text", models.TextField(blank=True)),
                (
                    "employee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cross_office_project_assignments",
                        to="master_data.employee",
                    ),
                ),
                (
                    "origin_business_unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="originating_cross_office_assignments",
                        to="master_data.businessunit",
                    ),
                ),
                (
                    "origin_office",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="originating_cross_office_assignments",
                        to="master_data.office",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cross_office_assignments",
                        to="master_data.project",
                    ),
                ),
                (
                    "status",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="reference_data.refvalue",
                    ),
                ),
            ],
            options={
                "db_table": "cross_office_project_assignment",
                "ordering": [
                    "project__project_code",
                    "employee__employee_code",
                    "assignment_start_date",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="crossofficeprojectassignment",
            constraint=models.UniqueConstraint(
                fields=("project", "employee", "assignment_start_date"),
                name="cross_office_project_assignment_window_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="crossofficeprojectassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("assignment_end_date__isnull", True),
                    ("assignment_end_date__gte", models.F("assignment_start_date")),
                    _connector="OR",
                ),
                name="cross_office_project_assignment_date_order_chk",
            ),
        ),
    ]
