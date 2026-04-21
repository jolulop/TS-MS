REFERENCE_DATA = {
    "ROLE_CODE": {
        "name": "Role Code",
        "description": "Internal TS authorization roles.",
        "values": [
            {"code": "USER", "label": "User", "sort_order": 10},
            {"code": "TS_ADMIN", "label": "Timesheet Administrator", "sort_order": 20},
            {"code": "PROJECT_OWNER", "label": "Project Owner", "sort_order": 30},
            {"code": "PROJECT_MANAGER", "label": "Project Manager", "sort_order": 40},
        ],
    },
    "EMPLOYEE_STATUS": {
        "name": "Employee Status",
        "description": "Employee lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "BUSINESS_UNIT_STATUS": {
        "name": "Business Unit Status",
        "description": "Business unit lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "EMPLOYEE_BU_STATUS": {
        "name": "Employee Business Unit Status",
        "description": "Employee-to-business-unit assignment status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "ROLE_ASSIGNMENT_STATUS": {
        "name": "Role Assignment Status",
        "description": "Employee role assignment status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "CALENDAR_STATUS": {
        "name": "Calendar Status",
        "description": "Yearly calendar lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "CALENDAR_PERIOD_STATUS": {
        "name": "Calendar Period Status",
        "description": "Calendar period rule lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "SPECIAL_DAY_STATUS": {
        "name": "Special Day Status",
        "description": "Special day lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "SPECIAL_DAY_TYPE": {
        "name": "Special Day Type",
        "description": "Special day classifications from the ERD.",
        "values": [
            {"code": "HOLIDAY", "label": "Holiday", "sort_order": 10},
            {"code": "COMPANY_DAY", "label": "Company Day", "sort_order": 20},
        ],
    },
    "CLIENT_STATUS": {
        "name": "Client Status",
        "description": "Client lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "INTERNAL_CATEGORY_STATUS": {
        "name": "Internal Category Status",
        "description": "Internal category lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "COST_CENTER_STATUS": {
        "name": "Cost Center Status",
        "description": "Cost center lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "GENERAL_CHARGE_CODE_TYPE": {
        "name": "General Charge Code Type",
        "description": "General charge code classifications.",
        "values": [
            {"code": "STANDARD", "label": "Standard", "sort_order": 10},
        ],
    },
    "GENERAL_CHARGE_CODE_STATUS": {
        "name": "General Charge Code Status",
        "description": "General charge code lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "PROJECT_STATUS": {
        "name": "Project Status",
        "description": "Project lifecycle status values.",
        "values": [
            {"code": "DRAFT", "label": "Draft", "sort_order": 10},
            {"code": "ACTIVE", "label": "Active", "sort_order": 20},
            {"code": "CLOSED", "label": "Closed", "sort_order": 30},
        ],
    },
    "PROJECT_ASSIGNMENT_STATUS": {
        "name": "Project Assignment Status",
        "description": "Project assignment lifecycle status values.",
        "values": [
            {"code": "ACTIVE", "label": "Active", "sort_order": 10},
            {"code": "INACTIVE", "label": "Inactive", "sort_order": 20},
        ],
    },
    "TIMESHEET_STATUS": {
        "name": "Timesheet Status",
        "description": "Weekly timesheet lifecycle status values.",
        "values": [
            {"code": "CREATED", "label": "Created", "sort_order": 10},
            {"code": "SUBMITTED", "label": "Submitted", "sort_order": 20},
            {"code": "APPROVED", "label": "Approved", "sort_order": 30},
            {"code": "REJECTED", "label": "Rejected", "sort_order": 40},
            {"code": "ARCHIVED", "label": "Archived", "sort_order": 50},
        ],
    },
    "APPROVAL_STATUS": {
        "name": "Approval Status",
        "description": "Approval state values.",
        "values": [
            {"code": "PENDING", "label": "Pending", "sort_order": 10},
            {"code": "APPROVED", "label": "Approved", "sort_order": 20},
            {"code": "REJECTED", "label": "Rejected", "sort_order": 30},
            {"code": "CANCELLED", "label": "Cancelled", "sort_order": 40},
        ],
    },
    "SUBMISSION_CYCLE_STATUS": {
        "name": "Submission Cycle Status",
        "description": "Submission cycle lifecycle values.",
        "values": [
            {"code": "OPEN", "label": "Open", "sort_order": 10},
            {"code": "COMPLETED", "label": "Completed", "sort_order": 20},
        ],
    },
    "APPROVAL_SCOPE_TYPE": {
        "name": "Approval Scope Type",
        "description": "Approval aggregation scope values.",
        "values": [
            {"code": "LINE", "label": "Line", "sort_order": 10},
            {"code": "PROJECT", "label": "Project", "sort_order": 20},
            {"code": "GENERAL_CODE", "label": "General Code", "sort_order": 30},
        ],
    },
    "APPROVAL_ACTION_TYPE": {
        "name": "Approval Action Type",
        "description": "Immutable approval action history types.",
        "values": [
            {"code": "APPROVE", "label": "Approve", "sort_order": 10},
            {"code": "REJECT", "label": "Reject", "sort_order": 20},
            {"code": "REOPEN", "label": "Reopen", "sort_order": 30},
            {"code": "WITHDRAW", "label": "Withdraw", "sort_order": 40},
            {"code": "AUTO_APPROVE", "label": "Auto Approve", "sort_order": 50},
        ],
    },
    "APPROVAL_MODE": {
        "name": "Approval Mode",
        "description": "Business unit approval routing mode values.",
        "values": [
            {"code": "LINE", "label": "Line", "sort_order": 10},
            {"code": "PROJECT", "label": "Project", "sort_order": 20},
            {"code": "MIXED", "label": "Mixed", "sort_order": 30},
        ],
    },
    "REMINDER_TYPE": {
        "name": "Reminder Type",
        "description": "Reminder rule trigger categories.",
        "values": [
            {"code": "SUBMISSION", "label": "Submission", "sort_order": 10},
            {"code": "APPROVAL", "label": "Approval", "sort_order": 20},
        ],
    },
    "CUSTOM_ATTRIBUTE_DATA_TYPE": {
        "name": "Custom Attribute Data Type",
        "description": "Supported custom attribute data types.",
        "values": [
            {"code": "TEXT", "label": "Text", "sort_order": 10},
            {"code": "NUMBER", "label": "Number", "sort_order": 20},
            {"code": "DATE", "label": "Date", "sort_order": 30},
            {"code": "BOOLEAN", "label": "Boolean", "sort_order": 40},
            {"code": "REFERENCE", "label": "Reference", "sort_order": 50},
        ],
    },
    "INTEGRATION_JOB_STATUS": {
        "name": "Integration Job Status",
        "description": "Integration job lifecycle status values.",
        "values": [
            {"code": "QUEUED", "label": "Queued", "sort_order": 10},
            {"code": "RUNNING", "label": "Running", "sort_order": 20},
            {"code": "COMPLETED", "label": "Completed", "sort_order": 30},
            {"code": "FAILED", "label": "Failed", "sort_order": 40},
        ],
    },
    "AUDIT_ACTION_TYPE": {
        "name": "Audit Action Type",
        "description": "Audit event action classifications.",
        "values": [
            {"code": "CREATE", "label": "Create", "sort_order": 10},
            {"code": "UPDATE", "label": "Update", "sort_order": 20},
            {"code": "DELETE", "label": "Delete", "sort_order": 30},
            {"code": "SUBMIT", "label": "Submit", "sort_order": 40},
            {"code": "APPROVE", "label": "Approve", "sort_order": 50},
            {"code": "REJECT", "label": "Reject", "sort_order": 60},
            {"code": "REOPEN", "label": "Reopen", "sort_order": 70},
            {"code": "WITHDRAW", "label": "Withdraw", "sort_order": 80},
            {"code": "ARCHIVE", "label": "Archive", "sort_order": 90},
            {"code": "RESTORE", "label": "Restore", "sort_order": 100},
            {"code": "IMPORT", "label": "Import", "sort_order": 110},
            {"code": "EXPORT", "label": "Export", "sort_order": 120},
            {"code": "DENY", "label": "Deny", "sort_order": 130},
        ],
    },
}
