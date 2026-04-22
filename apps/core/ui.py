from dataclasses import dataclass

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
            summary="Reporting hub placeholder for later milestones.",
            current_path=current_path,
        ),
    ]
    if current_user.has_role("PROJECT_MANAGER"):
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
                summary="Project-scoped inquiry placeholder for later work.",
                current_path=current_path,
            )
        )

    groups = [NavGroup(label="TS Management", items=tuple(work_items))]

    if current_user.is_ts_admin or current_user.has_role("PROJECT_OWNER"):
        system_items = [
            _nav_item(
                label="System Management",
                href="/system/",
                summary="Administration and project-management overview.",
                current_path=current_path,
            ),
        ]
        if current_user.is_ts_admin:
            system_items.extend(
                [
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
                        label="General Charge Codes",
                        href="/system/general-charge-codes/",
                        summary="Scoped general charge code management screens.",
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
