from datetime import date

from django.db import migrations

SYSTEM_ACTOR = "migration:0021_backfill_employee_calendar_setup"


def _preferred_calendar(yearly_calendar_model, *, office_id: int):
    current_year = date.today().year
    calendars = list(
        yearly_calendar_model.objects.select_related("status")
        .filter(office_id=office_id)
        .order_by("-calendar_year", "id")
    )
    if not calendars:
        return None
    calendars.sort(
        key=lambda calendar: (
            calendar.status.value_code != "ACTIVE",
            calendar.calendar_year != current_year,
            abs(calendar.calendar_year - current_year),
            -calendar.calendar_year,
            calendar.id,
        )
    )
    return calendars[0]


def _clone_default_rules(
    calendar_period_rule_model, *, yearly_calendar, business_unit_id: int
) -> None:
    if calendar_period_rule_model.objects.filter(
        yearly_calendar_id=yearly_calendar.id,
        business_unit_id=business_unit_id,
    ).exists():
        return
    if calendar_period_rule_model.objects.filter(
        yearly_calendar_id=yearly_calendar.id,
        business_unit_id__isnull=True,
    ).exists():
        return

    donor_rules = list(
        calendar_period_rule_model.objects.filter(
            yearly_calendar_id=yearly_calendar.id,
            business_unit_id__isnull=False,
        ).order_by("business_unit_id", "effective_from", "id")
    )
    donor_business_unit_ids = sorted({rule.business_unit_id for rule in donor_rules})
    if len(donor_business_unit_ids) != 1:
        return

    for donor_rule in donor_rules:
        if calendar_period_rule_model.objects.filter(
            yearly_calendar_id=yearly_calendar.id,
            business_unit_id=business_unit_id,
            effective_from=donor_rule.effective_from,
            effective_to=donor_rule.effective_to,
        ).exists():
            continue
        calendar_period_rule_model.objects.create(
            yearly_calendar_id=yearly_calendar.id,
            business_unit_id=business_unit_id,
            office_id=yearly_calendar.office_id,
            effective_from=donor_rule.effective_from,
            effective_to=donor_rule.effective_to,
            monday_max_hours=donor_rule.monday_max_hours,
            tuesday_max_hours=donor_rule.tuesday_max_hours,
            wednesday_max_hours=donor_rule.wednesday_max_hours,
            thursday_max_hours=donor_rule.thursday_max_hours,
            friday_max_hours=donor_rule.friday_max_hours,
            working_on_saturdays_flag=donor_rule.working_on_saturdays_flag,
            working_on_sundays_flag=donor_rule.working_on_sundays_flag,
            saturday_max_hours=donor_rule.saturday_max_hours,
            sunday_max_hours=donor_rule.sunday_max_hours,
            status_id=donor_rule.status_id,
            created_by=SYSTEM_ACTOR,
            updated_by=SYSTEM_ACTOR,
        )


def backfill_employee_calendar_setup(apps, schema_editor):
    Employee = apps.get_model("master_data", "Employee")
    YearlyCalendar = apps.get_model("master_data", "YearlyCalendar")
    CalendarPeriodRule = apps.get_model("master_data", "CalendarPeriodRule")

    for employee in Employee.objects.filter(assigned_calendar_id__isnull=True).order_by("id"):
        preferred_calendar = _preferred_calendar(YearlyCalendar, office_id=employee.office_id)
        if preferred_calendar is None:
            continue
        employee.assigned_calendar_id = preferred_calendar.id
        employee.updated_by = SYSTEM_ACTOR
        employee.save(update_fields=["assigned_calendar", "updated_by", "updated_at"])

    for employee in Employee.objects.filter(assigned_calendar_id__isnull=False).order_by("id"):
        yearly_calendar = YearlyCalendar.objects.filter(id=employee.assigned_calendar_id).first()
        if yearly_calendar is None:
            continue
        _clone_default_rules(
            CalendarPeriodRule,
            yearly_calendar=yearly_calendar,
            business_unit_id=employee.primary_business_unit_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0020_crossofficeprojectassignment"),
    ]

    operations = [
        migrations.RunPython(
            backfill_employee_calendar_setup,
            migrations.RunPython.noop,
        ),
    ]
