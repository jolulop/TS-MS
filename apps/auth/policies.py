from datetime import date

from django.db.models import Q

from apps.master_data.models import (
    GeneralChargeCodeApprovalRoleAssignment,
    GeneralChargeCodeApproverRole,
)

from apps.auth.context import CurrentUser


class AuthorizationPolicyService:
    REPORT_CODES = {
        "my-timesheet-history",
        "project-time",
        "pending-approvals",
        "missing-timesheets",
        "archived-timesheets",
        "audit-history",
        "integration-jobs",
    }

    @staticmethod
    def _active_general_charge_code_approval_role_ids(current_user: CurrentUser) -> set[int]:
        return set(
            GeneralChargeCodeApprovalRoleAssignment.objects.filter(
                employee_id=current_user.employee_id,
                status__domain__domain_code="ROLE_ASSIGNMENT_STATUS",
                status__value_code="ACTIVE",
                valid_from__lte=date.today(),
            )
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=date.today()))
            .values_list("approval_role_id", flat=True)
        )

    @staticmethod
    def has_general_charge_code_approval_access(current_user: CurrentUser) -> bool:
        if AuthorizationPolicyService._active_general_charge_code_approval_role_ids(current_user):
            return True
        if not current_user.role_codes:
            return False
        return GeneralChargeCodeApproverRole.objects.filter(
            general_charge_code__office_id=current_user.office_id,
            general_charge_code__status__value_code="ACTIVE",
            general_charge_code__requires_approval_flag=True,
            existing_role__value_code__in=current_user.role_codes,
        ).exists()

    @staticmethod
    def can_access_approval_worklist(current_user: CurrentUser) -> bool:
        return (
            current_user.has_role("PROJECT_MANAGER")
            or current_user.has_role("PROJECT_OWNER")
            or (
            AuthorizationPolicyService.has_general_charge_code_approval_access(current_user)
            )
        )

    @staticmethod
    def can_view_employee(current_user: CurrentUser, employee) -> bool:
        if current_user.employee_id == employee.id:
            return True

        if current_user.is_ts_admin:
            employee_scope_ids = {employee.primary_business_unit_id}
            employee_scope_ids.update(
                employee.business_unit_assignments.values_list("business_unit_id", flat=True)
            )
            return bool(employee_scope_ids.intersection(current_user.scoped_business_unit_ids))

        return False

    @staticmethod
    def can_manage_employee(current_user: CurrentUser, employee) -> bool:
        return AuthorizationPolicyService.can_view_employee(current_user, employee) and (
            current_user.is_ts_admin
        )

    @staticmethod
    def can_list_employees(current_user: CurrentUser) -> bool:
        return current_user.is_ts_admin

    @staticmethod
    def can_view_business_unit(current_user: CurrentUser, business_unit_id: int) -> bool:
        return business_unit_id in current_user.scoped_business_unit_ids

    @staticmethod
    def can_view_timesheet(current_user: CurrentUser, timesheet) -> bool:
        if current_user.employee_id == timesheet.employee_id:
            return True
        if current_user.is_ts_admin:
            return timesheet.business_unit_id in current_user.scoped_business_unit_ids
        return False

    @staticmethod
    def can_edit_timesheet(current_user: CurrentUser, timesheet) -> bool:
        editable_status_codes = {"CREATED", "REJECTED"}
        return (
            current_user.employee_id == timesheet.employee_id
            and timesheet.status.value_code in editable_status_codes
        )

    @staticmethod
    def can_submit_timesheet(current_user: CurrentUser, timesheet) -> bool:
        submittable_status_codes = {"CREATED", "REJECTED"}
        return (
            current_user.employee_id == timesheet.employee_id
            and timesheet.status.value_code in submittable_status_codes
        )

    @staticmethod
    def can_withdraw_timesheet(current_user: CurrentUser, timesheet) -> bool:
        return (
            current_user.employee_id == timesheet.employee_id
            and timesheet.status.value_code == "SUBMITTED"
        )

    @staticmethod
    def can_delete_timesheet(current_user: CurrentUser, timesheet) -> bool:
        return (
            current_user.employee_id == timesheet.employee_id
            and timesheet.status.value_code == "CREATED"
        )

    @staticmethod
    def can_reopen_timesheet(current_user: CurrentUser, timesheet) -> bool:
        return current_user.is_ts_admin and (
            timesheet.business_unit_id in current_user.scoped_business_unit_ids
            and timesheet.status.value_code == "APPROVED"
        )

    @staticmethod
    def can_admin_withdraw_timesheet(current_user: CurrentUser, timesheet) -> bool:
        return current_user.is_ts_admin and (
            timesheet.business_unit_id in current_user.scoped_business_unit_ids
            and timesheet.status.value_code == "APPROVED"
        )

    @staticmethod
    def can_override_period_lock(current_user: CurrentUser, timesheet) -> bool:
        return current_user.is_ts_admin and (
            timesheet.business_unit_id in current_user.scoped_business_unit_ids
        )

    @staticmethod
    def can_archive_timesheet(current_user: CurrentUser, timesheet) -> bool:
        return current_user.is_ts_admin and (
            timesheet.business_unit_id in current_user.scoped_business_unit_ids
            and timesheet.status.value_code == "APPROVED"
        )

    @staticmethod
    def can_restore_timesheet(current_user: CurrentUser, timesheet) -> bool:
        return current_user.is_ts_admin and (
            timesheet.business_unit_id in current_user.scoped_business_unit_ids
            and timesheet.status.value_code == "ARCHIVED"
        )

    @staticmethod
    def can_view_approval_item(current_user: CurrentUser, approval_item) -> bool:
        if approval_item.approver_employee_id == current_user.employee_id:
            return True
        if (
            approval_item.project_id is not None
            and approval_item.project.project_owner_employee_id == current_user.employee_id
        ):
            return True
        if approval_item.general_charge_code_id is None:
            return False
        active_ad_hoc_role_ids = AuthorizationPolicyService._active_general_charge_code_approval_role_ids(
            current_user
        )
        return approval_item.approver_roles.filter(
            Q(existing_role__value_code__in=current_user.role_codes)
            | Q(approval_role_id__in=active_ad_hoc_role_ids)
        ).exists()

    @staticmethod
    def can_approve_approval_item(current_user: CurrentUser, approval_item) -> bool:
        if approval_item.status.value_code != "PENDING":
            return False
        if approval_item.submission_cycle.weekly_timesheet.employee_id == current_user.employee_id:
            return False
        if approval_item.approver_employee_id == current_user.employee_id:
            return True
        if approval_item.general_charge_code_id is None:
            return False
        active_ad_hoc_role_ids = AuthorizationPolicyService._active_general_charge_code_approval_role_ids(
            current_user
        )
        return approval_item.approver_roles.filter(
            Q(existing_role__value_code__in=current_user.role_codes)
            | Q(approval_role_id__in=active_ad_hoc_role_ids)
        ).exists()

    @staticmethod
    def can_reject_approval_item(current_user: CurrentUser, approval_item) -> bool:
        return AuthorizationPolicyService.can_approve_approval_item(current_user, approval_item)

    @staticmethod
    def can_run_report(current_user: CurrentUser, report_code: str) -> bool:
        if report_code not in AuthorizationPolicyService.REPORT_CODES:
            return False
        if report_code == "my-timesheet-history":
            return True
        if report_code == "project-time":
            return (
                current_user.is_ts_admin
                or current_user.has_role("PROJECT_OWNER")
                or current_user.has_role("PROJECT_MANAGER")
            )
        if report_code == "pending-approvals":
            return current_user.is_ts_admin or AuthorizationPolicyService.can_access_approval_worklist(
                current_user
            )
        if report_code == "missing-timesheets":
            return (
                current_user.is_ts_admin
                or current_user.has_role("PROJECT_OWNER")
                or current_user.has_role("PROJECT_MANAGER")
            )
        if report_code in {"archived-timesheets", "audit-history", "integration-jobs"}:
            return current_user.is_ts_admin
        return False
