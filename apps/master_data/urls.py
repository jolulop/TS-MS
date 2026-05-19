from django.urls import path

from apps.master_data import views

urlpatterns = [
    path("admin/countries/", views.countries_collection, name="admin-country-collection"),
    path(
        "admin/countries/<int:country_id>/",
        views.country_detail,
        name="admin-country-detail",
    ),
    path("admin/offices/", views.offices_collection, name="admin-office-collection"),
    path(
        "admin/offices/<int:office_id>/",
        views.office_detail,
        name="admin-office-detail",
    ),
    path(
        "admin/business-units/",
        views.business_units_collection,
        name="admin-business-unit-collection",
    ),
    path(
        "admin/business-units/<int:business_unit_id>/",
        views.business_unit_detail,
        name="admin-business-unit-detail",
    ),
    path("admin/clients/", views.clients_collection, name="admin-client-collection"),
    path("admin/clients/<int:client_id>/", views.client_detail, name="admin-client-detail"),
    path(
        "admin/internal-categories/",
        views.internal_categories_collection,
        name="admin-internal-category-collection",
    ),
    path(
        "admin/internal-categories/<int:category_id>/",
        views.internal_category_detail,
        name="admin-internal-category-detail",
    ),
    path(
        "admin/cost-centers/",
        views.cost_centers_collection,
        name="admin-cost-center-collection",
    ),
    path(
        "admin/cost-centers/<int:cost_center_id>/",
        views.cost_center_detail,
        name="admin-cost-center-detail",
    ),
    path(
        "admin/pricing-models/",
        views.pricing_models_collection,
        name="admin-pricing-model-collection",
    ),
    path(
        "admin/pricing-models/<int:pricing_model_id>/",
        views.pricing_model_detail,
        name="admin-pricing-model-detail",
    ),
    path(
        "admin/yearly-calendars/",
        views.yearly_calendars_collection,
        name="admin-yearly-calendar-collection",
    ),
    path(
        "admin/yearly-calendars/<int:yearly_calendar_id>/",
        views.yearly_calendar_detail,
        name="admin-yearly-calendar-detail",
    ),
    path(
        "admin/calendar-special-days/",
        views.calendar_special_days_collection,
        name="admin-calendar-special-day-collection",
    ),
    path(
        "admin/calendar-special-days/<int:special_day_id>/",
        views.calendar_special_day_detail,
        name="admin-calendar-special-day-detail",
    ),
    path(
        "admin/general-charge-codes/",
        views.general_charge_codes_collection,
        name="admin-general-charge-code-collection",
    ),
    path(
        "admin/general-charge-code-approval-roles/",
        views.general_charge_code_approval_roles_collection,
        name="admin-general-charge-code-approval-role-collection",
    ),
    path(
        "admin/general-charge-code-approval-roles/<int:approval_role_id>/",
        views.general_charge_code_approval_role_detail,
        name="admin-general-charge-code-approval-role-detail",
    ),
    path(
        "admin/general-charge-codes/<int:general_charge_code_id>/",
        views.general_charge_code_detail,
        name="admin-general-charge-code-detail",
    ),
    path("admin/projects/", views.projects_collection, name="admin-project-collection"),
    path("admin/projects/<int:project_id>/", views.project_detail, name="admin-project-detail"),
    path(
        "admin/project-assignments/",
        views.project_assignments_collection,
        name="admin-project-assignment-collection",
    ),
    path(
        "admin/project-assignments/<int:assignment_id>/",
        views.project_assignment_detail,
        name="admin-project-assignment-detail",
    ),
    path(
        "admin/calendar-period-rules/",
        views.calendar_period_rules_collection,
        name="admin-calendar-period-rule-collection",
    ),
    path(
        "admin/calendar-period-rules/<int:period_rule_id>/",
        views.calendar_period_rule_detail,
        name="admin-calendar-period-rule-detail",
    ),
    path("admin/employees/", views.create_employee, name="admin-employee-create"),
    path("admin/employees/<int:employee_id>/", views.update_employee, name="admin-employee-update"),
    path(
        "admin/employees/<int:employee_id>/roles/",
        views.replace_employee_roles,
        name="admin-employee-roles",
    ),
    path(
        "admin/employees/<int:employee_id>/business-units/",
        views.replace_employee_business_units,
        name="admin-employee-business-units",
    ),
]
