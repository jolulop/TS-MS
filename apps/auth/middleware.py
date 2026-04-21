from django.utils.deprecation import MiddlewareMixin

from apps.auth.constants import SESSION_EMAIL_KEY, SESSION_EMPLOYEE_ID_KEY
from apps.auth.errors import AuthError
from apps.auth.services import CurrentUserService
from apps.master_data.models import Employee


class InternalSessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.ts_user = None
        employee_id = request.session.get(SESSION_EMPLOYEE_ID_KEY)
        if employee_id is None:
            return None

        try:
            employee = Employee.objects.select_related(
                "status",
                "status__domain",
                "primary_business_unit",
            ).get(id=employee_id)
            request.ts_user = CurrentUserService.build_for_employee(employee)
        except (Employee.DoesNotExist, AuthError):
            request.session.pop(SESSION_EMPLOYEE_ID_KEY, None)
            request.session.pop(SESSION_EMAIL_KEY, None)
        return None
