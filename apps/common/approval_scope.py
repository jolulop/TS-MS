from __future__ import annotations

from django.db.models import Q

from apps.auth.context import CurrentUser


def ts_admin_visible_approval_items_q(current_user: CurrentUser) -> Q:
    return Q(
        project_id__isnull=False,
        project__office_id=current_user.office_id,
        project__business_unit_id__in=current_user.scoped_business_unit_ids,
    ) | Q(
        project_id__isnull=True,
        submission_cycle__weekly_timesheet__business_unit_id__in=(
            current_user.scoped_business_unit_ids
        ),
    )


def ts_admin_approval_business_unit_filter_q(
    current_user: CurrentUser,
    business_unit_id: int,
) -> Q:
    return Q(
        project_id__isnull=False,
        project__office_id=current_user.office_id,
        project__business_unit_id=business_unit_id,
    ) | Q(
        project_id__isnull=True,
        submission_cycle__weekly_timesheet__business_unit_id=business_unit_id,
    )


def approval_item_effective_business_unit(approval_item) -> dict[str, object]:
    if approval_item.project_id is not None:
        return {
            "id": approval_item.project.business_unit_id,
            "bu_code": approval_item.project.business_unit.bu_code,
            "name": approval_item.project.business_unit.name,
        }
    return {
        "id": approval_item.submission_cycle.weekly_timesheet.business_unit_id,
        "bu_code": approval_item.submission_cycle.weekly_timesheet.business_unit.bu_code,
        "name": approval_item.submission_cycle.weekly_timesheet.business_unit.name,
    }


def can_ts_admin_view_approval_item(current_user: CurrentUser, approval_item) -> bool:
    if approval_item.project_id is not None:
        return (
            approval_item.project.office_id == current_user.office_id
            and approval_item.project.business_unit_id in current_user.scoped_business_unit_ids
        )
    return approval_item.submission_cycle.weekly_timesheet.business_unit_id in (
        current_user.scoped_business_unit_ids
    )
