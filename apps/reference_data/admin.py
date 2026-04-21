from django.contrib import admin

from apps.reference_data.models import RefDomain, RefValue


@admin.register(RefDomain)
class RefDomainAdmin(admin.ModelAdmin):
    list_display = ("domain_code", "name", "active_flag")
    search_fields = ("domain_code", "name")
    ordering = ("domain_code",)


@admin.register(RefValue)
class RefValueAdmin(admin.ModelAdmin):
    list_display = ("domain", "value_code", "value_label", "active_flag", "system_flag")
    list_filter = ("domain__domain_code", "active_flag", "system_flag")
    search_fields = ("value_code", "value_label", "domain__domain_code")
    ordering = ("domain__domain_code", "sort_order", "value_code")
