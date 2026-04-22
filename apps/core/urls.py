from django.urls import path

from apps.core import system_views, ts_views, views

urlpatterns = [
    path("", views.home, name="home"),
    path("logout/", views.logout, name="ui-logout"),
    path("profile/", views.profile, name="profile"),
    path("system/", views.system_management, name="system-management"),
    path("system/employees/", system_views.employees_collection, name="system-employees"),
    path(
        "system/employees/<int:employee_id>/",
        system_views.employee_detail,
        name="system-employee-detail",
    ),
    path("system/clients/", system_views.clients_collection, name="system-clients"),
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
        "system/cost-centers/<int:cost_center_id>/",
        system_views.cost_center_detail,
        name="system-cost-center-detail",
    ),
    path(
        "system/general-charge-codes/",
        system_views.general_charge_codes_collection,
        name="system-general-charge-codes",
    ),
    path(
        "system/general-charge-codes/<int:general_charge_code_id>/",
        system_views.general_charge_code_detail,
        name="system-general-charge-code-detail",
    ),
    path("ts/", ts_views.my_timesheets, name="ts-management"),
    path("ts/history/", ts_views.my_history, name="ts-history"),
    path("ts/inquiry/", ts_views.project_time_inquiry_placeholder, name="ts-project-inquiry"),
    path(
        "ts/timesheets/<int:timesheet_id>/",
        ts_views.timesheet_detail,
        name="ts-timesheet-detail",
    ),
    path("approvals/", views.approval_worklist, name="approval-worklist"),
    path("reports/", views.reports, name="reports"),
]
