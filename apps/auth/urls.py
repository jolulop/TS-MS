from django.urls import path

from apps.auth import views

urlpatterns = [
    path("auth/session/initialize", views.initialize_session, name="auth-session-initialize"),
    path("auth/session", views.get_session, name="auth-session"),
    path("auth/logout", views.logout, name="auth-logout"),
    path("employees/", views.list_employees, name="employee-list"),
    path("employees/<int:employee_id>/", views.employee_detail, name="employee-detail"),
    path("business-units/", views.list_business_units, name="business-unit-list"),
]
