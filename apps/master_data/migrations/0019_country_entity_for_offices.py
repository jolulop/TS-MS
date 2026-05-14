import unicodedata
from django.db import migrations, models
import django.db.models.deletion


def _country_code_from_name(name: str) -> str:
    normalized = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    cleaned = "".join(char if char.isalnum() else "_" for char in normalized.upper()).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or "COUNTRY"


def backfill_countries_for_offices(apps, schema_editor):
    Country = apps.get_model("master_data", "Country")
    Office = apps.get_model("master_data", "Office")

    used_codes: set[str] = set(Country.objects.values_list("country_code", flat=True))
    for office in Office.objects.filter(country_id__isnull=True).order_by("id"):
        base_code = _country_code_from_name(office.office_name)
        candidate_code = base_code
        suffix = 2
        while candidate_code in used_codes:
            candidate_code = f"{base_code}_{suffix}"
            suffix += 1
        country = Country.objects.create(
            country_code=candidate_code,
            country_name=office.office_name,
            status_id=office.status_id,
            created_by="migration",
            updated_by="migration",
        )
        used_codes.add(candidate_code)
        office.country_id = country.id
        office.save(update_fields=["country"])


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0018_generalchargecodeapprovalrole_and_more"),
        ("reference_data", "0003_general_charge_code_approval_role_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="Country",
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
                ("country_code", models.CharField(max_length=50, unique=True)),
                ("country_name", models.CharField(max_length=200, unique=True)),
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
                "db_table": "country",
                "ordering": ["country_name"],
            },
        ),
        migrations.AddField(
            model_name="office",
            name="country",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="offices",
                to="master_data.country",
            ),
        ),
        migrations.RunPython(backfill_countries_for_offices, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="office",
            name="country",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="offices",
                to="master_data.country",
            ),
        ),
    ]
