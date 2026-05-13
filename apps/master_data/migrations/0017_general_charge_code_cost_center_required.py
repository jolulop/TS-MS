import django.db.models.deletion
from django.db import migrations, models


def backfill_general_charge_code_cost_centers(apps, schema_editor):
    CostCenter = apps.get_model("master_data", "CostCenter")
    GeneralChargeCode = apps.get_model("master_data", "GeneralChargeCode")

    office_cost_centers: dict[int, int] = {}
    for cost_center in CostCenter.objects.order_by("office_id", "cost_center_code", "id"):
        office_cost_centers.setdefault(cost_center.office_id, cost_center.id)

    missing_offices = sorted(
        {
            office_id
            for office_id in GeneralChargeCode.objects.filter(cost_center_id__isnull=True)
            .values_list("office_id", flat=True)
            if office_id not in office_cost_centers
        }
    )
    if missing_offices:
        missing_list = ", ".join(str(office_id) for office_id in missing_offices)
        raise RuntimeError(
            "Cannot backfill general charge code cost centers because these offices do not "
            f"have any Cost Center records: {missing_list}"
        )

    for general_charge_code in GeneralChargeCode.objects.filter(cost_center_id__isnull=True):
        general_charge_code.cost_center_id = office_cost_centers[general_charge_code.office_id]
        general_charge_code.save(update_fields=["cost_center"])


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0016_businessunit_office_bu_code_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="generalchargecode",
            name="cost_center",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="general_charge_codes",
                to="master_data.costcenter",
            ),
        ),
        migrations.RunPython(
            backfill_general_charge_code_cost_centers,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="generalchargecode",
            name="cost_center",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="general_charge_codes",
                to="master_data.costcenter",
            ),
        ),
        migrations.RemoveField(
            model_name="generalchargecode",
            name="common_code_flag",
        ),
    ]
