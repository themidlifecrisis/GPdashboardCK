"""Configuration constants for the GP Dashboard."""

# Branch names
BRANCHES = [
    "CK Constantiaberg",
    "CK Tokai",
    "JCF",
    "CK Foreshore",
    "CK Tygerberg",
]

# Months in financial year (starting March)
MONTHS = [
    "March", "April", "May", "June",
    "July", "August", "September",
    "October", "November", "December",
    "January", "February",
]

QUARTERS = {
    "Q1": ["March", "April", "May"],
    "Q2": ["June", "July", "August"],
    "Q3": ["September", "October", "November"],
    "Q4": ["December", "January", "February"],
}

# GP calculation rates (target defaults)
RSB_PAINT_PCT = 0.04              # 4% of sales
CONSUMABLES_PCT = 0.03            # 3% of sales
COST_OF_SALES_OTHER_PCT = 0.07    # 7% of sales (default)

# Contribution split defaults (can be overridden in budget)
PAINT_LABOUR_PCT = 0.49    # 49%
PARTS_SALES_PCT = 0.51     # 51%

# Default parts markup
DEFAULT_PARTS_MARKUP = 25   # 25%

# Roles
ROLE_MANAGER = "manager"
ROLE_DIRECTOR = "director"
ROLE_ADMIN = "admin"
ROLE_ACCOUNTANT = "accountant"

# Google Sheets tab names
SHEET_USERS = "Users"
SHEET_BUDGET = "Budget"
SHEET_ACTUALS = "Actuals"
SHEET_AUDIT = "AuditLog"
SHEET_SETTINGS = "Settings"

# Spreadsheet name on Google Drive
SPREADSHEET_NAME = "GP_Dashboard_Data"
