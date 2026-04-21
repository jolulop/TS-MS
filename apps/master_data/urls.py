from django.urls import path

from apps.master_data import views

urlpatterns = [
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
