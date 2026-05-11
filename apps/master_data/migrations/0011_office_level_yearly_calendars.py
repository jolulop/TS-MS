from django.db import migrations, models


def consolidate_yearly_calendars(apps, schema_editor):
    YearlyCalendar = apps.get_model("master_data", "YearlyCalendar")
    CalendarPeriodRule = apps.get_model("master_data", "CalendarPeriodRule")
    CalendarSpecialDay = apps.get_model("master_data", "CalendarSpecialDay")
    Employee = apps.get_model("master_data", "Employee")

    grouped_calendars: dict[tuple[int, int], list] = {}
    for calendar in YearlyCalendar.objects.select_related("status").order_by("office_id", "id"):
        grouped_calendars.setdefault(
            (calendar.office_id, calendar.calendar_year),
            [],
        ).append(calendar)

    for (office_id, calendar_year), calendars in grouped_calendars.items():
        if len(calendars) <= 1:
            continue

        calendars = sorted(
            calendars,
            key=lambda calendar: (
                calendar.status.value_code != "ACTIVE",
                calendar.id,
            ),
        )
        canonical_calendar = calendars[0]

        for duplicate_calendar in calendars[1:]:
            Employee.objects.filter(assigned_calendar_id=duplicate_calendar.id).update(
                assigned_calendar_id=canonical_calendar.id
            )

            for special_day in CalendarSpecialDay.objects.filter(
                yearly_calendar_id=duplicate_calendar.id
            ).order_by("special_date", "id"):
                existing_special_day = CalendarSpecialDay.objects.filter(
                    yearly_calendar_id=canonical_calendar.id,
                    special_date=special_day.special_date,
                ).first()
                if existing_special_day is None:
                    special_day.yearly_calendar_id = canonical_calendar.id
                    special_day.save(update_fields=["yearly_calendar"])
                    continue
                if (
                    existing_special_day.day_type_id == special_day.day_type_id
                    and existing_special_day.default_general_charge_code_id
                    == special_day.default_general_charge_code_id
                    and existing_special_day.status_id == special_day.status_id
                ):
                    special_day.delete()
                    continue
                raise RuntimeError(
                    "Cannot merge yearly calendars for office "
                    f"{office_id} and year {calendar_year}: conflicting special days exist for "
                    f"{special_day.special_date.isoformat()}."
                )

            for period_rule in CalendarPeriodRule.objects.filter(
                yearly_calendar_id=duplicate_calendar.id
            ).order_by("effective_from", "effective_to", "id"):
                overlapping_rules = CalendarPeriodRule.objects.filter(
                    yearly_calendar_id=canonical_calendar.id,
                    effective_from__lte=period_rule.effective_to,
                    effective_to__gte=period_rule.effective_from,
                )
                exact_match = overlapping_rules.filter(
                    effective_from=period_rule.effective_from,
                    effective_to=period_rule.effective_to,
                    monday_max_hours=period_rule.monday_max_hours,
                    tuesday_max_hours=period_rule.tuesday_max_hours,
                    wednesday_max_hours=period_rule.wednesday_max_hours,
                    thursday_max_hours=period_rule.thursday_max_hours,
                    friday_max_hours=period_rule.friday_max_hours,
                    status_id=period_rule.status_id,
                ).first()
                if exact_match is not None:
                    period_rule.delete()
                    continue
                if overlapping_rules.exists():
                    raise RuntimeError(
                        "Cannot merge yearly calendars for office "
                        f"{office_id} and year {calendar_year}: conflicting period rules overlap "
                        f"{period_rule.effective_from.isoformat()} to "
                        f"{period_rule.effective_to.isoformat()}."
                    )
                period_rule.yearly_calendar_id = canonical_calendar.id
                period_rule.save(update_fields=["yearly_calendar"])

            duplicate_calendar.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('master_data', '0010_special_day_type_refresh'),
        ('reference_data', '0002_refdomain_refvalue_delete_referencevalue_and_more'),
    ]

    operations = [
        migrations.RunPython(
            consolidate_yearly_calendars,
            migrations.RunPython.noop,
        ),
        migrations.AlterModelOptions(
            name='yearlycalendar',
            options={'ordering': ['office__office_name', 'calendar_year', 'calendar_name']},
        ),
        migrations.RemoveConstraint(
            model_name='yearlycalendar',
            name='yearly_calendar_bu_year_name_uniq',
        ),
        migrations.RemoveField(
            model_name='yearlycalendar',
            name='business_unit',
        ),
        migrations.AddConstraint(
            model_name='yearlycalendar',
            constraint=models.UniqueConstraint(
                fields=('office', 'calendar_year'),
                name='yearly_calendar_office_year_uniq',
            ),
        ),
    ]
