from django.contrib import admin
from django.urls import path

from apps.core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("", views.home, name="home"),
]
