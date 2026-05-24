from django.db import models
from django.db.models import Q

from apps.common.models import AuditFieldsModel, CreatedAuditModel


class WeeklyTimesheet(AuditFieldsModel):
    employee = models.ForeignKey(
        "master_data.Employee",
        on_delete=models.PROTECT,
        related_name="weekly_timesheets",
    )
    business_unit = models.ForeignKey(
        "master_data.BusinessUnit",
        on_delete=models.PROTECT,
        related_name="weekly_timesheets",
    )
    week_start_date = models.DateField()
    week_end_date = models.DateField()
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    current_submission_no = models.PositiveIntegerField(default=0)
    submission_datetime = models.DateTimeField(null=True, blank=True)
    final_approval_datetime = models.DateTimeField(null=True, blank=True)
    comment_text = models.TextField(blank=True)
    archive_eligible_date = models.DateField(null=True, blank=True)
    period_lock_override_flag = models.BooleanField(default=False)

    class Meta:
        db_table = "weekly_timesheet"
        ordering = ["-week_start_date", "employee__employee_code"]
        indexes = [
            models.Index(
                fields=["business_unit", "week_start_date"],
                name="weekly_ts_bu_week_idx",
            ),
            models.Index(
                fields=["status", "week_start_date"],
                name="weekly_ts_status_week_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "week_start_date"],
                name="weekly_timesheet_employee_week_start_uniq",
            ),
            models.CheckConstraint(
                condition=Q(week_end_date__gte=models.F("week_start_date")),
                name="weekly_timesheet_week_date_order_chk",
            ),
        ]


class TimesheetLine(AuditFieldsModel):
    weekly_timesheet = models.ForeignKey(
        WeeklyTimesheet,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    work_date = models.DateField()
    project = models.ForeignKey(
        "master_data.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="timesheet_lines",
    )
    general_charge_code = models.ForeignKey(
        "master_data.GeneralChargeCode",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="timesheet_lines",
    )
    activity_code = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    comment_text = models.TextField(blank=True)
    billable_flag = models.BooleanField(default=False)
    approval_state = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "timesheet_line"
        ordering = ["weekly_timesheet", "work_date", "id"]
        indexes = [
            models.Index(
                fields=["weekly_timesheet", "work_date"],
                name="ts_line_sheet_date_idx",
            ),
            models.Index(
                fields=["project", "work_date"],
                name="ts_line_project_date_idx",
            ),
            models.Index(
                fields=["general_charge_code", "work_date"],
                name="ts_line_gcc_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(project__isnull=False) & Q(general_charge_code__isnull=True))
                    | (Q(project__isnull=True) & Q(general_charge_code__isnull=False))
                ),
                name="timesheet_line_charge_target_xor_chk",
            )
        ]


class TimesheetSubmissionCycle(AuditFieldsModel):
    weekly_timesheet = models.ForeignKey(
        WeeklyTimesheet,
        on_delete=models.PROTECT,
        related_name="submission_cycles",
    )
    submission_no = models.PositiveIntegerField()
    submitted_by_employee = models.ForeignKey(
        "master_data.Employee",
        on_delete=models.PROTECT,
        related_name="submitted_timesheet_cycles",
    )
    submitted_at = models.DateTimeField()
    cycle_status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    outcome_status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "timesheet_submission_cycle"
        ordering = ["weekly_timesheet", "submission_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["weekly_timesheet", "submission_no"],
                name="timesheet_submission_cycle_sheet_submission_no_uniq",
            )
        ]


class ApprovalItem(AuditFieldsModel):
    submission_cycle = models.ForeignKey(
        TimesheetSubmissionCycle,
        on_delete=models.PROTECT,
        related_name="approval_items",
    )
    scope_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    approver_employee = models.ForeignKey(
        "master_data.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_items",
    )
    project = models.ForeignKey(
        "master_data.Project",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_items",
    )
    timesheet_line = models.ForeignKey(
        TimesheetLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_items",
    )
    general_charge_code = models.ForeignKey(
        "master_data.GeneralChargeCode",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_items",
    )
    status = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    rejection_reason = models.TextField(blank=True)

    class Meta:
        db_table = "approval_item"
        ordering = ["submission_cycle", "id"]
        indexes = [
            models.Index(
                fields=["status", "approver_employee"],
                name="approval_item_status_appr_idx",
            ),
            models.Index(
                fields=["status", "project"],
                name="approval_item_status_prj_idx",
            ),
        ]


class ApprovalItemApproverRole(AuditFieldsModel):
    approval_item = models.ForeignKey(
        ApprovalItem,
        on_delete=models.PROTECT,
        related_name="approver_roles",
    )
    existing_role = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    approval_role = models.ForeignKey(
        "master_data.GeneralChargeCodeApprovalRole",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_item_assignments",
    )

    class Meta:
        db_table = "approval_item_approver_role"
        ordering = ["approval_item", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(existing_role__isnull=False, approval_role__isnull=True)
                    | Q(existing_role__isnull=True, approval_role__isnull=False)
                ),
                name="approval_item_approver_role_target_xor_chk",
            ),
            models.UniqueConstraint(
                fields=["approval_item", "existing_role"],
                condition=Q(existing_role__isnull=False),
                name="approval_item_approver_existing_uniq",
            ),
            models.UniqueConstraint(
                fields=["approval_item", "approval_role"],
                condition=Q(approval_role__isnull=False),
                name="approval_item_approver_ad_hoc_uniq",
            ),
        ]


class ApprovalAction(CreatedAuditModel):
    approval_item = models.ForeignKey(
        ApprovalItem,
        on_delete=models.PROTECT,
        related_name="actions",
    )
    action_type = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        related_name="+",
    )
    acted_by_employee = models.ForeignKey(
        "master_data.Employee",
        on_delete=models.PROTECT,
        related_name="approval_actions",
    )
    action_timestamp = models.DateTimeField()
    comment_text = models.TextField(blank=True)

    class Meta:
        db_table = "approval_action"
        ordering = ["approval_item", "action_timestamp", "id"]


class TimesheetLineAttributeValue(AuditFieldsModel):
    timesheet_line = models.ForeignKey(
        TimesheetLine,
        on_delete=models.PROTECT,
        related_name="attribute_values",
    )
    custom_attribute_definition = models.ForeignKey(
        "master_data.CustomAttributeDefinition",
        on_delete=models.PROTECT,
        related_name="line_values",
    )
    value_text = models.TextField(blank=True)
    value_number = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    value_date = models.DateField(null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    ref_value = models.ForeignKey(
        "reference_data.RefValue",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "timesheet_line_attribute_value"
        ordering = ["timesheet_line", "custom_attribute_definition"]
        constraints = [
            models.UniqueConstraint(
                fields=["timesheet_line", "custom_attribute_definition"],
                name="timesheet_line_attribute_value_line_definition_uniq",
            )
        ]
