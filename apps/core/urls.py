from django.urls import path

from apps.core import approval_views, reports_views, system_views, ts_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("logout/", views.logout, name="ui-logout"),
    path("profile/", views.profile, name="profile"),
    path("system/", views.system_management, name="system-management"),
    path("system/countries/", system_views.countries_collection, name="system-countries"),
    path(
        "system/countries/<int:country_id>/",
        system_views.country_detail,
        name="system-country-detail",
    ),
    path("system/offices/", system_views.offices_collection, name="system-offices"),
    path("system/offices/new/", system_views.office_create, name="system-offices-new"),
    path(
        "system/offices/<int:office_id>/",
        system_views.office_detail,
        name="system-office-detail",
    ),
    path(
        "system/business-units/",
        system_views.business_units_collection,
        name="system-business-units",
    ),
    path(
        "system/business-units/new/",
        system_views.business_unit_create,
        name="system-business-unit-create",
    ),
    path(
        "system/business-units/<int:business_unit_id>/",
        system_views.business_unit_detail,
        name="system-business-unit-detail",
    ),
    path("system/employees/", system_views.employees_collection, name="system-employees"),
    path(
        "system/employees/new/",
        system_views.employee_create,
        name="system-employee-create",
    ),
    path(
        "system/employees/<int:employee_id>/",
        system_views.employee_detail,
        name="system-employee-detail",
    ),
    path("system/clients/", system_views.clients_collection, name="system-clients"),
    path(
        "system/clients/new/",
        system_views.client_create,
        name="system-client-create",
    ),
    path(
        "system/clients/<int:client_id>/",
        system_views.client_detail,
        name="system-client-detail",
    ),
    path(
        "system/internal-categories/",
        system_views.internal_categories_collection,
        name="system-internal-categories",
    ),
    path(
        "system/internal-categories/new/",
        system_views.internal_category_create,
        name="system-internal-category-create",
    ),
    path(
        "system/internal-categories/<int:category_id>/",
        system_views.internal_category_detail,
        name="system-internal-category-detail",
    ),
    path(
        "system/cost-centers/",
        system_views.cost_centers_collection,
        name="system-cost-centers",
    ),
    path(
        "system/cost-centers/new/",
        system_views.cost_center_create,
        name="system-cost-center-create",
    ),
    path(
        "system/cost-centers/<int:cost_center_id>/",
        system_views.cost_center_detail,
        name="system-cost-center-detail",
    ),
    path(
        "system/pricing-models/",
        system_views.pricing_models_collection,
        name="system-pricing-models",
    ),
    path(
        "system/pricing-models/new/",
        system_views.pricing_model_create,
        name="system-pricing-model-create",
    ),
    path(
        "system/pricing-models/<int:pricing_model_id>/",
        system_views.pricing_model_detail,
        name="system-pricing-model-detail",
    ),
    path(
        "system/general-charge-code-approval-roles/",
        system_views.general_charge_code_approval_roles_collection,
        name="system-general-charge-code-approval-roles",
    ),
    path(
        "system/general-charge-code-approval-roles/new/",
        system_views.general_charge_code_approval_role_create,
        name="system-general-charge-code-approval-role-create",
    ),
    path(
        "system/general-charge-code-approval-roles/<int:approval_role_id>/",
        system_views.general_charge_code_approval_role_detail,
        name="system-general-charge-code-approval-role-detail",
    ),
    path(
        "system/general-charge-codes/",
        system_views.general_charge_codes_collection,
        name="system-general-charge-codes",
    ),
    path(
        "system/general-charge-codes/new/",
        system_views.general_charge_code_create,
        name="system-general-charge-code-create",
    ),
    path(
        "system/general-charge-codes/<int:general_charge_code_id>/",
        system_views.general_charge_code_detail,
        name="system-general-charge-code-detail",
    ),
    path("system/projects/", system_views.projects_collection, name="system-projects"),
    path(
        "system/projects/new/",
        system_views.project_create,
        name="system-project-create",
    ),
    path(
        "system/projects/<int:project_id>/",
        system_views.project_detail,
        name="system-project-detail",
    ),
    path(
        "system/project-assignments/",
        system_views.project_assignments_collection,
        name="system-project-assignments",
    ),
    path(
        "system/project-assignments/new/",
        system_views.project_assignment_create,
        name="system-project-assignment-create",
    ),
    path(
        "system/project-assignments/<int:assignment_id>/",
        system_views.project_assignment_detail,
        name="system-project-assignment-detail",
    ),
    path("system/calendars/", system_views.yearly_calendars_collection, name="system-calendars"),
    path(
        "system/calendars/new/",
        system_views.yearly_calendar_create,
        name="system-calendar-create",
    ),
    path(
        "system/calendars/<int:yearly_calendar_id>/",
        system_views.yearly_calendar_detail,
        name="system-calendar-detail",
    ),
    path(
        "system/calendars/<int:yearly_calendar_id>/special-days/new/",
        system_views.calendar_special_day_create,
        name="system-calendar-special-day-create",
    ),
    path(
        "system/calendar-special-days/<int:special_day_id>/",
        system_views.calendar_special_day_detail,
        name="system-calendar-special-day-detail",
    ),
    path(
        "system/calendar-period-rules/",
        system_views.calendar_period_rules_collection,
        name="system-calendar-period-rules",
    ),
    path(
        "system/calendar-period-rules/new/",
        system_views.calendar_period_rule_create,
        name="system-calendar-period-rule-create",
    ),
    path(
        "system/calendar-period-rules/<int:period_rule_id>/",
        system_views.calendar_period_rule_detail,
        name="system-calendar-period-rule-detail",
    ),
    path("ts/", ts_views.my_timesheets, name="ts-management"),
    path("ts/history/", ts_views.my_history, name="ts-history"),
    path("ts/projects/", ts_views.project_management, name="ts-project-management"),
    path("ts/inquiry/", ts_views.project_time_inquiry, name="ts-project-inquiry"),
    path(
        "ts/timesheets/<int:timesheet_id>/",
        ts_views.timesheet_detail,
        name="ts-timesheet-detail",
    ),
    path("approvals/", approval_views.approval_worklist, name="approval-worklist"),
    path(
        "approvals/<int:approval_item_id>/",
        approval_views.approval_detail,
        name="approval-detail",
    ),
    path("reports/", reports_views.reports_hub, name="reports"),
    path(
        "reports/missing-timesheets/export/",
        reports_views.export_missing_timesheets_csv,
        name="report-missing-timesheets-export",
    ),
    path("reports/<slug:report_code>/", reports_views.report_viewer, name="report-viewer"),
]
