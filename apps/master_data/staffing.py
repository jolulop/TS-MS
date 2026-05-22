from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from django.db.models import Q

from apps.master_data.models import CrossOfficeProjectAssignment, Project, ProjectAssignment


@dataclass(frozen=True)
class ProjectStaffingWindow:
    project_id: int
    project_code: str
    project_name: str
    project_start_date: date
    project_end_date: date | None
    project_close_date: date | None
    employee_id: int
    employee_code: str
    employee_full_name: str
    employee_email: str
    employee_created_at: datetime
    employee_employment_end_date: date | None
    staffing_start_date: date
    staffing_end_date: date | None


def _active_staffing_date_overlap_filter(
    *,
    start_field: str,
    end_field: str,
    window_start: date,
    window_end: date,
) -> Q:
    return Q(**{f"{start_field}__lte": window_end}) & (
        Q(**{f"{end_field}__isnull": True}) | Q(**{f"{end_field}__gte": window_start})
    )


def employee_has_project_staffing_on_date(
    *,
    employee_id: int,
    project_id: int,
    work_date: date,
) -> bool:
    overlap_filter = _active_staffing_date_overlap_filter(
        start_field="assignment_start_date",
        end_field="assignment_end_date",
        window_start=work_date,
        window_end=work_date,
    )
    return (
        ProjectAssignment.objects.filter(
            employee_id=employee_id,
            project_id=project_id,
            status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
        )
        .filter(overlap_filter)
        .exists()
        or CrossOfficeProjectAssignment.objects.filter(
            employee_id=employee_id,
            project_id=project_id,
            status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
        )
        .filter(overlap_filter)
        .exists()
    )


def staffed_project_ids_for_employee_window(
    *,
    employee_id: int,
    week_start_date: date,
    week_end_date: date,
) -> list[int]:
    overlap_filter = _active_staffing_date_overlap_filter(
        start_field="assignment_start_date",
        end_field="assignment_end_date",
        window_start=week_start_date,
        window_end=week_end_date,
    )
    project_ids = {
        *ProjectAssignment.objects.filter(
            employee_id=employee_id,
            status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
        )
        .filter(overlap_filter)
        .values_list("project_id", flat=True),
        *CrossOfficeProjectAssignment.objects.filter(
            employee_id=employee_id,
            status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
            status__value_code="ACTIVE",
        )
        .filter(overlap_filter)
        .values_list("project_id", flat=True),
    }
    if not project_ids:
        return []

    return list(
        Project.objects.filter(
            id__in=project_ids,
            status__domain__domain_code="PROJECT_STATUS",
            status__value_code="ACTIVE",
            start_date__lte=week_end_date,
        )
        .filter(
            Q(end_date__isnull=True) | Q(end_date__gte=week_start_date),
            Q(close_date__isnull=True) | Q(close_date__gte=week_start_date),
        )
        .order_by("project_code")
        .values_list("id", flat=True)
    )


def project_staffing_windows(project_ids: Iterable[int]) -> list[ProjectStaffingWindow]:
    resolved_project_ids = tuple(dict.fromkeys(int(project_id) for project_id in project_ids))
    if not resolved_project_ids:
        return []

    normal_assignments = ProjectAssignment.objects.select_related("employee", "project").filter(
        project_id__in=resolved_project_ids,
        employee__status__value_code="ACTIVE",
        status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
        status__value_code="ACTIVE",
    )
    cross_office_assignments = CrossOfficeProjectAssignment.objects.select_related(
        "employee",
        "project",
    ).filter(
        project_id__in=resolved_project_ids,
        employee__status__value_code="ACTIVE",
        status__domain__domain_code="PROJECT_ASSIGNMENT_STATUS",
        status__value_code="ACTIVE",
    )

    windows = [
        ProjectStaffingWindow(
            project_id=assignment.project_id,
            project_code=assignment.project.project_code,
            project_name=assignment.project.name,
            project_start_date=assignment.project.start_date,
            project_end_date=assignment.project.end_date,
            project_close_date=assignment.project.close_date,
            employee_id=assignment.employee_id,
            employee_code=assignment.employee.employee_code,
            employee_full_name=assignment.employee.full_name,
            employee_email=assignment.employee.email,
            employee_created_at=assignment.employee.created_at,
            employee_employment_end_date=assignment.employee.employment_end_date,
            staffing_start_date=assignment.assignment_start_date,
            staffing_end_date=assignment.assignment_end_date,
        )
        for assignment in normal_assignments
    ]
    windows.extend(
        ProjectStaffingWindow(
            project_id=assignment.project_id,
            project_code=assignment.project.project_code,
            project_name=assignment.project.name,
            project_start_date=assignment.project.start_date,
            project_end_date=assignment.project.end_date,
            project_close_date=assignment.project.close_date,
            employee_id=assignment.employee_id,
            employee_code=assignment.employee.employee_code,
            employee_full_name=assignment.employee.full_name,
            employee_email=assignment.employee.email,
            employee_created_at=assignment.employee.created_at,
            employee_employment_end_date=assignment.employee.employment_end_date,
            staffing_start_date=assignment.assignment_start_date,
            staffing_end_date=assignment.assignment_end_date,
        )
        for assignment in cross_office_assignments
    )
    windows.sort(
        key=lambda window: (
            window.employee_full_name,
            window.staffing_start_date,
            window.project_code,
        )
    )
    return windows
