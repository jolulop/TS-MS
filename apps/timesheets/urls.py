from django.urls import path

from apps.timesheets import views

urlpatterns = [
    path("timesheets/", views.timesheets_collection, name="timesheet-collection"),
    path("timesheets/<int:timesheet_id>/", views.timesheet_detail, name="timesheet-detail"),
    path(
        "timesheets/<int:timesheet_id>/lines/",
        views.replace_timesheet_lines,
        name="timesheet-lines-replace",
    ),
    path(
        "timesheets/<int:timesheet_id>/submit/",
        views.submit_timesheet,
        name="timesheet-submit",
    ),
    path(
        "timesheets/<int:timesheet_id>/withdraw/",
        views.withdraw_timesheet,
        name="timesheet-withdraw",
    ),
    path("approvals/", views.approvals_collection, name="approval-collection"),
    path("approvals/<int:approval_item_id>/", views.approval_detail, name="approval-detail"),
    path(
        "approvals/<int:approval_item_id>/approve/",
        views.approve_approval_item,
        name="approval-approve",
    ),
    path(
        "approvals/<int:approval_item_id>/reject/",
        views.reject_approval_item,
        name="approval-reject",
    ),
]
