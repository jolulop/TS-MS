from django.contrib import admin

from apps.master_data.models import (
    BusinessUnit,
    Country,
    Employee,
    EmployeeBusinessUnit,
    EmployeeRole,
)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("country_name", "status")
    search_fields = ("country_name",)
    ordering = ("country_name",)


@admin.register(BusinessUnit)
class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("bu_code", "name", "country", "status")
    search_fields = ("bu_code", "name", "country__country_name")
    list_filter = ("country", "status")
    ordering = ("bu_code",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_code",
        "full_name",
        "email",
        "country",
        "primary_business_unit",
        "status",
    )
    list_filter = ("country", "primary_business_unit", "status")
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
