from django.db import migrations


def refresh_special_day_types(apps, schema_editor):
    RefDomain = apps.get_model("reference_data", "RefDomain")
    RefValue = apps.get_model("reference_data", "RefValue")
    CalendarSpecialDay = apps.get_model("master_data", "CalendarSpecialDay")

    domain = RefDomain.objects.filter(domain_code="SPECIAL_DAY_TYPE").first()
    if domain is None:
        return

    desired_values = [
        ("NATIONAL_HOLIDAY", "National Holiday", 10, True),
        ("LOCAL_HOLIDAY", "Local Holiday", 20, True),
        ("TIMIA_DAY", "Timia Day", 30, True),
        ("OTHER", "Other", 40, True),
        ("HOLIDAY", "Holiday", 90, False),
        ("COMPANY_DAY", "Company Day", 100, False),
    ]

    value_by_code = {}
    for code, label, sort_order, active_flag in desired_values:
        value_by_code[code], _ = RefValue.objects.update_or_create(
            domain=domain,
            value_code=code,
            defaults={
                "value_label": label,
                "description": "",
                "sort_order": sort_order,
                "active_flag": active_flag,
                "system_flag": True,
            },
        )

    old_to_new = {
        "HOLIDAY": "NATIONAL_HOLIDAY",
        "COMPANY_DAY": "TIMIA_DAY",
    }
    for old_code, new_code in old_to_new.items():
        try:
            old_value = RefValue.objects.get(domain=domain, value_code=old_code)
        except RefValue.DoesNotExist:
            continue
        CalendarSpecialDay.objects.filter(day_type_id=old_value.id).update(
            day_type_id=value_by_code[new_code].id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("reference_data", "0002_refdomain_refvalue_delete_referencevalue_and_more"),
        ("master_data", "0009_pricing_models"),
    ]

    operations = [
        migrations.RunPython(refresh_special_day_types, migrations.RunPython.noop),
    ]
