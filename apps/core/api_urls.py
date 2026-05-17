from django.urls import path

from apps.core import api_views

urlpatterns = [
    path(
        "reports/missing-timesheets/exports/",
        api_views.create_missing_timesheets_export,
        name="report-missing-timesheets-export-create",
    ),
    path(
        "reports/missing-timesheets/export.csv",
        api_views.download_missing_timesheets_export,
        name="report-missing-timesheets-export-download",
    ),
]
