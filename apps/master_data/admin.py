from django.contrib import admin

from apps.master_data.models import (
    BusinessUnit,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
    Office,
    OfficeConfiguration,
    PricingModel,
)


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ("office_name", "status")
    search_fields = ("office_name",)
    ordering = ("office_name",)


@admin.register(OfficeConfiguration)
class OfficeConfigurationAdmin(admin.ModelAdmin):
    list_display = ("office", "approval_mode", "archive_after_years", "timesheet_cutoff_date")
    list_filter = ("approval_mode",)
    search_fields = ("office__office_name",)
    ordering = ("office__office_name",)


@admin.register(BusinessUnit)
class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("bu_code", "name", "office", "status")
    search_fields = ("bu_code", "name", "office__office_name")
    list_filter = ("office", "status")
    ordering = ("bu_code",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_code",
        "full_name",
        "email",
        "office",
        "primary_business_unit",
        "status",
    )
    list_filter = ("office", "primary_business_unit", "status")
    search_fields = ("employee_code", "full_name", "email", "canonical_email")
    ordering = ("employee_code",)


@admin.register(EmployeeBusinessUnit)
class EmployeeBusinessUnitAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "business_unit",
        "is_primary_flag",
        "status",
        "valid_from",
        "valid_to",
    )
    list_filter = ("business_unit", "is_primary_flag", "status")
    search_fields = ("employee__employee_code", "business_unit__bu_code")
    ordering = ("employee__employee_code", "business_unit__bu_code", "valid_from")


@admin.register(EmployeeRole)
class EmployeeRoleAdmin(admin.ModelAdmin):
    list_display = ("employee", "role", "business_unit", "status", "valid_from", "valid_to")
    list_filter = ("role", "business_unit", "status")
    search_fields = ("employee__employee_code", "role__value_code", "business_unit__bu_code")
    ordering = ("employee__employee_code", "role__value_code", "valid_from")


@admin.register(PricingModel)
class PricingModelAdmin(admin.ModelAdmin):
    list_display = ("name", "office")
    list_filter = ("office",)
    search_fields = ("name", "office__office_name")
    ordering = ("office__office_name", "name")
