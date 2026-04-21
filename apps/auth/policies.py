from apps.auth.context import CurrentUser


class AuthorizationPolicyService:
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
