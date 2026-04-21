from django.contrib import admin
from django.urls import include, path

from apps.core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("api/v1/", include("apps.auth.urls")),
    path("api/v1/", include("apps.master_data.urls")),
    path("", views.home, name="home"),
]
