from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0004_country_foundation"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Country",
            new_name="Office",
        ),
        migrations.AlterModelTable(
            name="office",
            table="office",
        ),
        migrations.AlterModelOptions(
            name="office",
            options={"ordering": ["office_name"]},
        ),
        migrations.RenameField(
            model_name="office",
            old_name="country_name",
            new_name="office_name",
        ),
        migrations.RenameField(
            model_name="businessunit",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="yearlycalendar",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="employee",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="calendarperiodrule",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="client",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="internalcategory",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="costcenter",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="generalchargecode",
            old_name="country",
            new_name="office",
        ),
        migrations.RenameField(
            model_name="project",
            old_name="country",
            new_name="office",
        ),
    ]
