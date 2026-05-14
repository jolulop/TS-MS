from dataclasses import dataclass

from apps.auth.policies import AuthorizationPolicyService
from apps.auth.context import CurrentUser


@dataclass(frozen=True)
class NavItem:
    label: str
    href: str
    summary: str
    active: bool


@dataclass(frozen=True)
class NavGroup:
    label: str
    items: tuple[NavItem, ...]


def _nav_item(*, label: str, href: str, summary: str, current_path: str) -> NavItem:
    return NavItem(
        label=label,
        href=href,
        summary=summary,
        active=current_path == href or (href != "/" and current_path.startswith(href)),
    )


def build_navigation(current_user: CurrentUser, *, current_path: str) -> tuple[NavGroup, ...]:
    work_items = [
        _nav_item(
            label="Dashboard",
            href="/",
            summary="Role-aware dashboard and quick actions.",
            current_path=current_path,
        ),
        _nav_item(
            label="My Timesheets",
            href="/ts/",
            summary="Create, edit, submit, and review your weekly timesheets.",
            current_path=current_path,
        ),
        _nav_item(
            label="My History",
            href="/ts/history/",
            summary="Read-only history of your submitted and completed weeks.",
            current_path=current_path,
        ),
        _nav_item(
            label="Reports",
            href="/reports/",
            summary="Role-aware report hub and scoped viewers.",
            current_path=current_path,
        ),
    ]
    if AuthorizationPolicyService.can_access_approval_worklist(current_user):
        work_items.append(
            _nav_item(
                label="Approval Worklist",
                href="/approvals/",
                summary="Pending approvals and approval actions.",
                current_path=current_path,
            )
        )
    if current_user.has_role("PROJECT_OWNER") or current_user.has_role("PROJECT_MANAGER"):
        work_items.append(
            _nav_item(
                label="Project Time Inquiry",
                href="/ts/inquiry/",
                summary="Project-scoped inquiry for owned or managed project time.",
                current_path=current_path,
            )
        )

    groups = [NavGroup(label="TS Management", items=tuple(work_items))]

    if (
        current_user.is_ts_admin
        or current_user.is_ts_admin_master
        or current_user.has_role("PROJECT_OWNER")
    ):
        system_items = [
            _nav_item(
                label="System Management",
                href="/system/",
                summary="Administration and project-management overview.",
                current_path=current_path,
            ),
        ]
        if current_user.is_ts_admin_master:
            system_items.extend(
                [
                    _nav_item(
                        label="Countries",
                        href="/system/countries/",
                        summary="Country lifecycle management for master administration.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Offices",
                        href="/system/offices/",
                        summary="Office lifecycle management for master administration.",
                        current_path=current_path,
                    ),
                ]
            )
        if current_user.is_ts_admin:
            system_items.extend(
                [
                    _nav_item(
                        label="Business Units",
                        href="/system/business-units/",
                        summary="Scoped Business Unit identity and configuration screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Employees",
                        href="/system/employees/",
                        summary="Employee identity, role, and BU administration.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Clients",
                        href="/system/clients/",
                        summary="Scoped client management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Internal Categories",
                        href="/system/internal-categories/",
                        summary="Scoped internal category management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Cost Centers",
                        href="/system/cost-centers/",
                        summary="Scoped cost center management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Pricing Models",
                        href="/system/pricing-models/",
                        summary="Office-level pricing model management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="GCC Approval Roles",
                        href="/system/general-charge-code-approval-roles/",
                        summary=(
                            "Office-scoped ad-hoc approval roles and member assignments "
                            "for General Charge Code routing."
                        ),
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="General Charge Codes",
                        href="/system/general-charge-codes/",
                        summary=(
                            "Scoped general charge code management with "
                            "Office Cost Center assignment."
                        ),
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Projects",
                        href="/system/projects/",
                        summary="Scoped project setup and lifecycle management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Project Assignments",
                        href="/system/project-assignments/",
                        summary="Scoped project staffing and lifecycle management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Calendars",
                        href="/system/calendars/",
                        summary="Office-level yearly calendar and special-day management screens.",
                        current_path=current_path,
                    ),
                    _nav_item(
                        label="Calendar Period Rules",
                        href="/system/calendar-period-rules/",
                        summary="Scoped daily-hour period-rule management screens.",
                        current_path=current_path,
                    ),
                ]
            )
        groups.append(NavGroup(label="System Management", items=tuple(system_items)))

    groups.append(
        NavGroup(
            label="Session",
            items=(
                _nav_item(
                    label="Profile",
                    href="/profile/",
                    summary="Employee identity, roles, and scope.",
                    current_path=current_path,
                ),
            ),
        )
    )
    return tuple(groups)
