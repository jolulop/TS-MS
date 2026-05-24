from pathlib import Path

import pytest

from apps.common import approval_scope
from apps.common.reference_data import get_ref_value
from apps.common.urls import safe_local_path
from apps.timesheets import approval_scope as legacy_approval_scope
from tests.helpers import seed_reference_data


def test_auth_policy_module_does_not_import_timesheets_app() -> None:
    policy_source = Path("apps/auth/policies.py").read_text()
    assert "apps.timesheets" not in policy_source


def test_legacy_timesheet_approval_scope_reexports_common_policy_helpers() -> None:
    assert (
        legacy_approval_scope.can_ts_admin_view_approval_item
        is approval_scope.can_ts_admin_view_approval_item
    )
    assert (
        legacy_approval_scope.ts_admin_visible_approval_items_q
        is approval_scope.ts_admin_visible_approval_items_q
    )


def test_safe_local_path_allows_only_single_slash_local_paths() -> None:
    assert safe_local_path("/approvals/?page=1", default="/fallback/") == "/approvals/?page=1"
    assert safe_local_path("//example.test/approvals/", default="/fallback/") == "/fallback/"
    assert safe_local_path("https://example.test/approvals/", default="/fallback/") == "/fallback/"
    assert safe_local_path("", default="/fallback/") == "/fallback/"


@pytest.mark.django_db
def test_common_reference_value_lookup_matches_seeded_reference_data() -> None:
    seed_reference_data()

    status = get_ref_value("TIMESHEET_STATUS", "CREATED")

    assert status.value_code == "CREATED"
    assert status.domain.domain_code == "TIMESHEET_STATUS"
