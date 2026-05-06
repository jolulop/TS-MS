from django.db import models
from django.db.models import Q

from apps.common.models import AuditFieldsModel


class Country(AuditFieldsModel):
    country_name = models.CharField(max_length=200, unique=True)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "country"
        ordering = ["country_name"]

    def __str__(self) -> str:
        return self.country_name


class BusinessUnit(AuditFieldsModel):
    bu_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="business_units",
    )
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "business_unit"
        ordering = ["bu_code"]

    def __str__(self) -> str:
        return self.bu_code


class YearlyCalendar(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="yearly_calendars",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="yearly_calendars",
    )
    calendar_year = models.PositiveIntegerField()
    calendar_name = models.CharField(max_length=200)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "yearly_calendar"
        ordering = ["business_unit__bu_code", "calendar_year", "calendar_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "calendar_year", "calendar_name"],
                name="yearly_calendar_bu_year_name_uniq",
            )
        ]

    def __str__(self) -> str:
        return f"{self.business_unit.bu_code}:{self.calendar_year}:{self.calendar_name}"


class Employee(AuditFieldsModel):
    employee_code = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(max_length=320)
    canonical_email = models.CharField(max_length=320, unique=True)
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="employees",
    )
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    primary_business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="primary_employees",
    )
    manager_employee = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="direct_reports",
    )
    assigned_calendar = models.ForeignKey(
        YearlyCalendar,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_employees",
    )
    employment_start_date = models.DateField(null=True, blank=True)
    employment_end_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "employee"
        ordering = ["employee_code"]

    def __str__(self) -> str:
        return self.employee_code


class EmployeeBusinessUnit(AuditFieldsModel):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="business_unit_assignments",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="employee_assignments",
    )
    is_primary_flag = models.BooleanField(default=False)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "employee_business_unit"
        ordering = ["employee__employee_code", "business_unit__bu_code", "valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "business_unit", "valid_from"],
                name="employee_business_unit_window_uniq",
            ),
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(is_primary_flag=True, valid_to__isnull=True),
                name="employee_business_unit_active_primary_uniq",
            ),
        ]


class EmployeeRole(AuditFieldsModel):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "employee_role"
        ordering = ["employee__employee_code", "role__value_code", "valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "role", "business_unit", "valid_from"],
                name="employee_role_window_uniq",
            )
        ]


class CalendarPeriodRule(AuditFieldsModel):
    yearly_calendar = models.ForeignKey(
        YearlyCalendar,
        on_delete=models.PROTECT,
        related_name="period_rules",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="calendar_period_rules",
    )
    effective_from = models.DateField()
    effective_to = models.DateField()
    monday_max_hours = models.DecimalField(max_digits=5, decimal_places=2)
    tuesday_max_hours = models.DecimalField(max_digits=5, decimal_places=2)
    wednesday_max_hours = models.DecimalField(max_digits=5, decimal_places=2)
    thursday_max_hours = models.DecimalField(max_digits=5, decimal_places=2)
    friday_max_hours = models.DecimalField(max_digits=5, decimal_places=2)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "calendar_period_rule"
        ordering = ["yearly_calendar", "effective_from"]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__gte=models.F("effective_from")),
                name="calendar_period_rule_date_order_chk",
            )
        ]


class Client(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="clients",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="clients",
    )
    parent_client = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_clients",
    )
    client_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "client"
        ordering = ["business_unit__bu_code", "client_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "client_code"],
                name="client_bu_client_code_uniq",
            )
        ]


class InternalCategory(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="internal_categories",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="internal_categories",
    )
    category_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "internal_category"
        ordering = ["business_unit__bu_code", "category_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "category_code"],
                name="internal_category_bu_category_code_uniq",
            )
        ]


class CostCenter(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="cost_centers",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="cost_centers",
    )
    cost_center_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "cost_center"
        ordering = ["business_unit__bu_code", "cost_center_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "cost_center_code"],
                name="cost_center_bu_code_uniq",
            )
        ]


class GeneralChargeCode(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="general_charge_codes",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="general_charge_codes",
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    charge_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    billable_flag = models.BooleanField(default=False)
    common_code_flag = models.BooleanField(default=False)
    requires_approval_flag = models.BooleanField(default=False)
    description_required_flag = models.BooleanField(default=False)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "general_charge_code"
        ordering = ["business_unit__bu_code", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "code"],
                name="general_charge_code_bu_code_uniq",
            )
        ]


class CalendarSpecialDay(AuditFieldsModel):
    yearly_calendar = models.ForeignKey(
        YearlyCalendar,
        on_delete=models.PROTECT,
        related_name="special_days",
    )
    special_date = models.DateField()
    day_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    name = models.CharField(max_length=200)
    default_general_charge_code = models.ForeignKey(
        GeneralChargeCode,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="default_for_special_days",
    )
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "calendar_special_day"
        ordering = ["yearly_calendar", "special_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["yearly_calendar", "special_date"],
                name="calendar_special_day_calendar_date_uniq",
            )
        ]


class Project(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    project_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    project_owner_employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="owned_projects",
    )
    project_manager_employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="managed_projects",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    internal_category = models.ForeignKey(
        InternalCategory,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="projects",
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    close_date = models.DateField(null=True, blank=True)
    billable_flag = models.BooleanField(default=False)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "project"
        ordering = ["business_unit__bu_code", "project_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "project_code"],
                name="project_bu_project_code_uniq",
            )
        ]


class ProjectAssignment(AuditFieldsModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="project_assignments",
    )
    assignment_start_date = models.DateField()
    assignment_end_date = models.DateField(null=True, blank=True)
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "project_assignment"
        ordering = ["project__project_code", "employee__employee_code", "assignment_start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "employee", "assignment_start_date"],
                name="project_assignment_window_uniq",
            )
        ]


class BusinessUnitConfiguration(AuditFieldsModel):
    business_unit = models.OneToOneField(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="configuration",
    )
    approval_mode = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    allow_employee_withdraw_flag = models.BooleanField(default=False)
    timesheet_cutoff_date = models.DateField(null=True, blank=True)
    count_non_billable_in_daily_limit_flag = models.BooleanField(default=False)
    archive_after_years = models.PositiveSmallIntegerField(default=0)
    enable_timer_flag = models.BooleanField(default=False)
    enable_leave_integration_flag = models.BooleanField(default=False)
    enable_copy_previous_week_flag = models.BooleanField(default=False)

    class Meta:
        db_table = "business_unit_configuration"


class ReminderRule(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="reminder_rules",
    )
    reminder_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    rule_name = models.CharField(max_length=200)
    active_flag = models.BooleanField(default=True)
    schedule_expression = models.CharField(max_length=255)
    recipient_scope = models.CharField(max_length=100)
    template_code = models.CharField(max_length=100)

    class Meta:
        db_table = "reminder_rule"
        ordering = ["business_unit__bu_code", "rule_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "rule_name"],
                name="reminder_rule_bu_name_uniq",
            )
        ]


class CustomAttributeDefinition(AuditFieldsModel):
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="custom_attribute_definitions",
    )
    attribute_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    data_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    active_flag = models.BooleanField(default=True)

    class Meta:
        db_table = "custom_attribute_definition"
        ordering = ["business_unit__bu_code", "attribute_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["business_unit", "attribute_code"],
                name="custom_attribute_definition_bu_code_uniq",
            )
        ]


class CustomAttributeRule(AuditFieldsModel):
    custom_attribute_definition = models.ForeignKey(
        CustomAttributeDefinition,
        on_delete=models.PROTECT,
        related_name="rules",
    )
    business_unit = models.ForeignKey(
        BusinessUnit,
        on_delete=models.PROTECT,
        related_name="custom_attribute_rules",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="custom_attribute_rules",
    )
    general_charge_code = models.ForeignKey(
        GeneralChargeCode,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="custom_attribute_rules",
    )
    mandatory_flag = models.BooleanField(default=False)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    active_flag = models.BooleanField(default=True)

    class Meta:
        db_table = "custom_attribute_rule"
        ordering = ["custom_attribute_definition", "valid_from"]
