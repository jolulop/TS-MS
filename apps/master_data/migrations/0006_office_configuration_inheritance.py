import django.db.models.deletion
from django.db import migrations, models

CONFIG_FIELDS = (
    "approval_mode_id",
    "allow_employee_withdraw_flag",
    "timesheet_cutoff_date",
    "count_non_billable_in_daily_limit_flag",
    "archive_after_years",
    "enable_timer_flag",
    "enable_leave_integration_flag",
    "enable_copy_previous_week_flag",
)


def _configuration_signature(values):
    return tuple(values[field_name] for field_name in CONFIG_FIELDS)


def _copy_business_unit_configuration_to_office(apps, schema_editor):
    Office = apps.get_model("master_data", "Office")
    BusinessUnitConfiguration = apps.get_model("master_data", "BusinessUnitConfiguration")
    OfficeConfiguration = apps.get_model("master_data", "OfficeConfiguration")

    for office in Office.objects.all().order_by("id"):
        configurations = list(
            BusinessUnitConfiguration.objects.filter(business_unit__office_id=office.id)
            .order_by("business_unit_id")
            .values(*CONFIG_FIELDS, "created_by", "updated_by")
        )

        if not configurations:
            continue

        signatures = {_configuration_signature(values) for values in configurations}
        if len(signatures) > 1:
            raise RuntimeError(
                "Cannot migrate Office configuration because Business Units under "
                f"office {office.id} ({office.office_name}) have conflicting configuration values."
            )

        source = configurations[0]
        payload = {field_name: source[field_name] for field_name in CONFIG_FIELDS}
        OfficeConfiguration.objects.create(
            office_id=office.id,
            **payload,
            created_by=source["created_by"],
            updated_by=source["updated_by"],
        )


def _restore_business_unit_configuration_from_office(apps, schema_editor):
    BusinessUnit = apps.get_model("master_data", "BusinessUnit")
    BusinessUnitConfiguration = apps.get_model("master_data", "BusinessUnitConfiguration")
    OfficeConfiguration = apps.get_model("master_data", "OfficeConfiguration")
    office_configurations = {
        configuration.office_id: configuration
        for configuration in OfficeConfiguration.objects.all().order_by("office_id")
    }

    for business_unit in BusinessUnit.objects.select_related("office").all().order_by("id"):
        office_configuration = office_configurations.get(business_unit.office_id)
        if office_configuration is None:
            continue

        BusinessUnitConfiguration.objects.create(
            business_unit_id=business_unit.id,
            approval_mode_id=office_configuration.approval_mode_id,
            allow_employee_withdraw_flag=office_configuration.allow_employee_withdraw_flag,
            timesheet_cutoff_date=office_configuration.timesheet_cutoff_date,
            count_non_billable_in_daily_limit_flag=(
                office_configuration.count_non_billable_in_daily_limit_flag
            ),
            archive_after_years=office_configuration.archive_after_years,
            enable_timer_flag=office_configuration.enable_timer_flag,
            enable_leave_integration_flag=office_configuration.enable_leave_integration_flag,
            enable_copy_previous_week_flag=office_configuration.enable_copy_previous_week_flag,
            created_by=office_configuration.created_by,
            updated_by=office_configuration.updated_by,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0005_rename_country_to_office"),
        ("reference_data", "0002_refdomain_refvalue_delete_referencevalue_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfficeConfiguration",
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
                ("allow_employee_withdraw_flag", models.BooleanField(default=False)),
                ("timesheet_cutoff_date", models.DateField(blank=True, null=True)),
                ("count_non_billable_in_daily_limit_flag", models.BooleanField(default=False)),
                ("archive_after_years", models.PositiveSmallIntegerField(default=0)),
                ("enable_timer_flag", models.BooleanField(default=False)),
                ("enable_leave_integration_flag", models.BooleanField(default=False)),
                ("enable_copy_previous_week_flag", models.BooleanField(default=False)),
                (
                    "approval_mode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="reference_data.refvalue",
                    ),
                ),
                (
                    "office",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="configuration",
                        to="master_data.office",
                    ),
                ),
            ],
            options={
                "db_table": "office_configuration",
            },
        ),
        migrations.RunPython(
            _copy_business_unit_configuration_to_office,
            _restore_business_unit_configuration_from_office,
        ),
        migrations.DeleteModel(
            name="BusinessUnitConfiguration",
        ),
    ]
