from datetime import date

from django.db import migrations


def assign_full_office_scope_to_ts_admins(apps, schema_editor):
    BusinessUnit = apps.get_model("master_data", "BusinessUnit")
    Employee = apps.get_model("master_data", "Employee")
    EmployeeBusinessUnit = apps.get_model("master_data", "EmployeeBusinessUnit")
    RefValue = apps.get_model("reference_data", "RefValue")

    ts_admin_role = RefValue.objects.filter(
        domain__domain_code="ROLE_CODE",
        value_code="TS_ADMIN",
    ).first()
    active_role_status = RefValue.objects.filter(
        domain__domain_code="ROLE_ASSIGNMENT_STATUS",
        value_code="ACTIVE",
    ).first()
    active_bu_status = RefValue.objects.filter(
        domain__domain_code="EMPLOYEE_BU_STATUS",
        value_code="ACTIVE",
    ).first()
    inactive_bu_status = RefValue.objects.filter(
        domain__domain_code="EMPLOYEE_BU_STATUS",
        value_code="INACTIVE",
    ).first()
    if any(
        value is None
        for value in (ts_admin_role, active_role_status, active_bu_status, inactive_bu_status)
    ):
        return

    system_actor = "migration@system.local"
    today = date.today()
    office_business_units: dict[int, list] = {}
    office_admins = (
        Employee.objects.filter(
            role_assignments__role=ts_admin_role,
            role_assignments__status=active_role_status,
            role_assignments__valid_to__isnull=True,
        )
        .order_by("id")
        .distinct()
    )

    for employee in office_admins.iterator():
        desired_business_units = office_business_units.get(employee.office_id)
        if desired_business_units is None:
            desired_business_units = list(
                BusinessUnit.objects.filter(office_id=employee.office_id).order_by("bu_code")
            )
            office_business_units[employee.office_id] = desired_business_units
        desired_ids = {business_unit.id for business_unit in desired_business_units}

        active_assignments = {
            assignment.business_unit_id: assignment
            for assignment in EmployeeBusinessUnit.objects.filter(
                employee_id=employee.id,
                status=active_bu_status,
                valid_to__isnull=True,
            )
        }

        for assignment in active_assignments.values():
            if assignment.is_primary_flag:
                assignment.is_primary_flag = False
                assignment.updated_by = system_actor
                assignment.save(update_fields=["is_primary_flag", "updated_by", "updated_at"])

        for business_unit_id, assignment in active_assignments.items():
            if business_unit_id not in desired_ids:
                assignment.status = inactive_bu_status
                assignment.valid_to = today
                assignment.updated_by = system_actor
                assignment.save(update_fields=["status", "valid_to", "updated_by", "updated_at"])

        for business_unit in desired_business_units:
            is_primary = business_unit.id == employee.primary_business_unit_id
            assignment = active_assignments.get(business_unit.id)
            if assignment is None:
                existing_inactive = (
                    EmployeeBusinessUnit.objects.filter(
                        employee_id=employee.id,
                        business_unit_id=business_unit.id,
                        status=inactive_bu_status,
                        valid_to=today,
                    )
                    .order_by("-id")
                    .first()
                )
                if existing_inactive is not None:
                    existing_inactive.is_primary_flag = is_primary
                    existing_inactive.status = active_bu_status
                    existing_inactive.valid_to = None
                    existing_inactive.updated_by = system_actor
                    existing_inactive.save(
                        update_fields=[
                            "is_primary_flag",
                            "status",
                            "valid_to",
                            "updated_by",
                            "updated_at",
                        ]
                    )
                else:
                    EmployeeBusinessUnit.objects.create(
                        employee_id=employee.id,
                        business_unit_id=business_unit.id,
                        is_primary_flag=is_primary,
                        status=active_bu_status,
                        valid_from=today,
                        created_by=system_actor,
                        updated_by=system_actor,
                    )
            else:
                assignment.is_primary_flag = is_primary
                assignment.updated_by = system_actor
                assignment.save(update_fields=["is_primary_flag", "updated_by", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("reference_data", "0002_refdomain_refvalue_delete_referencevalue_and_more"),
        ("master_data", "0014_calendarperiodrule_saturday_max_hours_and_more"),
    ]

    operations = [
        migrations.RunPython(assign_full_office_scope_to_ts_admins, migrations.RunPython.noop),
    ]
