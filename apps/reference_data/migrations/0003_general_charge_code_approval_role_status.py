from django.db import migrations


def seed_general_charge_code_approval_role_status(apps, schema_editor):
    RefDomain = apps.get_model("reference_data", "RefDomain")
    RefValue = apps.get_model("reference_data", "RefValue")

    domain, _ = RefDomain.objects.update_or_create(
        domain_code="GENERAL_CHARGE_CODE_APPROVAL_ROLE_STATUS",
        defaults={
            "name": "General Charge Code Approval Role Status",
            "description": "Ad-hoc General Charge Code approval role lifecycle status values.",
            "active_flag": True,
        },
    )

    desired_values = [
        ("ACTIVE", "Active", 10),
        ("INACTIVE", "Inactive", 20),
    ]
    for code, label, sort_order in desired_values:
        RefValue.objects.update_or_create(
            domain=domain,
            value_code=code,
            defaults={
                "value_label": label,
                "description": "",
                "sort_order": sort_order,
                "active_flag": True,
                "system_flag": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("reference_data", "0002_refdomain_refvalue_delete_referencevalue_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_general_charge_code_approval_role_status,
            migrations.RunPython.noop,
        ),
    ]
