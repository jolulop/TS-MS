import unicodedata

import django.db.models.deletion
from django.db import migrations, models


def _country_code_from_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
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


def prepare_office_postgresql_artifacts(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    schema_editor.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.country_pkey') IS NOT NULL
               AND to_regclass('public.office_pkey') IS NULL THEN
                ALTER INDEX public.country_pkey RENAME TO office_pkey;
            END IF;
            IF to_regclass('public.country_country_name_key') IS NOT NULL
               AND to_regclass('public.office_office_name_key') IS NULL THEN
                ALTER INDEX public.country_country_name_key RENAME TO office_office_name_key;
            END IF;
            IF to_regclass('public.country_country_name_7fbf0aaa_like') IS NOT NULL
               AND to_regclass('public.office_office_name_like') IS NULL THEN
                ALTER INDEX public.country_country_name_7fbf0aaa_like
                RENAME TO office_office_name_like;
            END IF;
            IF to_regclass('public.country_status_id_2696fdeb') IS NOT NULL
               AND to_regclass('public.office_status_id_idx') IS NULL THEN
                ALTER INDEX public.country_status_id_2696fdeb RENAME TO office_status_id_idx;
            END IF;
            PERFORM setval(
                pg_get_serial_sequence('office', 'id'),
                COALESCE((SELECT MAX(id) FROM public.office), 1),
                true
            );
        END
        $$;
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0018_generalchargecodeapprovalrole_and_more"),
        ("reference_data", "0003_general_charge_code_approval_role_status"),
    ]

    operations = [
        migrations.RunPython(
            prepare_office_postgresql_artifacts,
            migrations.RunPython.noop,
        ),
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
