"""One-time setup script to initialize the Google Sheet with required tabs and headers.

Usage:
    1. Set up .streamlit/secrets.toml with your GCP service account credentials
    2. Run: python setup_sheets.py
    3. This creates the spreadsheet and all tabs with proper headers
    4. Optionally creates a demo director + manager user
"""

import sys
import os

# Add parent dir so we can import config
sys.path.insert(0, os.path.dirname(__file__))

import gspread
from google.oauth2.service_account import Credentials

from auth import hash_password
from config import (
    BRANCHES,
    SHEET_ACTUALS,
    SHEET_AUDIT,
    SHEET_BUDGET,
    SHEET_USERS,
    SPREADSHEET_NAME,
)

# Load secrets from .streamlit/secrets.toml
try:
    import tomllib
except ModuleNotFoundError:
    import pip._vendor.tomli as tomllib

SECRETS_PATH = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")


def load_secrets():
    with open(SECRETS_PATH, "r") as f:
        content = f.read()
    return tomllib.loads(content)


def main():
    print("Loading credentials...")
    secrets = load_secrets()
    creds_info = secrets["gcp_service_account"]

    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    client = gspread.authorize(creds)

    # Create or open spreadsheet
    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
        print(f"Opened existing spreadsheet: {SPREADSHEET_NAME}")
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SPREADSHEET_NAME)
        print(f"Created new spreadsheet: {SPREADSHEET_NAME}")
        print(f"  URL: {spreadsheet.url}")
        print(f"  ⚠️  Share this spreadsheet with yourself to access it in Google Drive!")

    existing_tabs = [ws.title for ws in spreadsheet.worksheets()]

    # --- Users tab ---
    if SHEET_USERS not in existing_tabs:
        ws = spreadsheet.add_worksheet(title=SHEET_USERS, rows=50, cols=10)
        ws.append_row(["username", "password_hash", "role", "branch", "name"])
        print(f"  Created '{SHEET_USERS}' tab")
    else:
        ws = spreadsheet.worksheet(SHEET_USERS)
        print(f"  '{SHEET_USERS}' tab already exists")

    # --- Budget tab ---
    budget_headers = [
        "branch", "month", "sales_target", "paint_labour_pct", "parts_sales_pct",
        "parts_markup", "cos_other_pct", "rsb_paint_pct", "consumables_pct",
        "diagnostics_target", "additionals_target", "csi_target",
        "updated_by", "updated_at",
    ]
    if SHEET_BUDGET not in existing_tabs:
        ws = spreadsheet.add_worksheet(title=SHEET_BUDGET, rows=200, cols=len(budget_headers))
        ws.append_row(budget_headers)
        print(f"  Created '{SHEET_BUDGET}' tab")
    else:
        print(f"  '{SHEET_BUDGET}' tab already exists")

    # --- Actuals tab ---
    actuals_headers = [
        "branch", "month", "sales", "parts_contribution", "parts_gp_pct",
        "paints", "consumables_paintshop", "consumables",
        "diagnostics", "additionals", "csi",
        "submitted_by", "submitted_at",
    ]
    if SHEET_ACTUALS not in existing_tabs:
        ws = spreadsheet.add_worksheet(title=SHEET_ACTUALS, rows=200, cols=len(actuals_headers))
        ws.append_row(actuals_headers)
        print(f"  Created '{SHEET_ACTUALS}' tab")
    else:
        print(f"  '{SHEET_ACTUALS}' tab already exists")

    # --- AuditLog tab ---
    audit_headers = ["timestamp", "user_email", "action", "branch", "month", "old_data", "new_data"]
    if SHEET_AUDIT not in existing_tabs:
        ws = spreadsheet.add_worksheet(title=SHEET_AUDIT, rows=1000, cols=len(audit_headers))
        ws.append_row(audit_headers)
        print(f"  Created '{SHEET_AUDIT}' tab")
    else:
        print(f"  '{SHEET_AUDIT}' tab already exists")

    # Remove default Sheet1 if it exists and we created other sheets
    if "Sheet1" in existing_tabs and len(existing_tabs) > 1:
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
            print("  Removed default 'Sheet1'")
        except Exception:
            pass

    # --- Create demo users ---
    print("\n--- Demo User Setup ---")
    create_demo = input("Create demo users? (y/n): ").strip().lower()
    if create_demo == "y":
        users_ws = spreadsheet.worksheet(SHEET_USERS)
        existing_users = users_ws.get_all_records()
        existing_usernames = {u.get("username", "") for u in existing_users}

        demo_users = [
            {"username": "director", "password": "director123", "role": "director", "branch": "All", "name": "Director"},
            {"username": "admin", "password": "admin123", "role": "admin", "branch": "All", "name": "Admin"},
            {"username": "accountant", "password": "acc123", "role": "accountant", "branch": "All", "name": "Accountant"},
        ]
        # Add a manager for each branch
        manager_creds = [
            ("constantiaberg", "berg@CK9"),
            ("tokai", "Tok!blue7"),
            ("jcf", "Jcf#rain4"),
            ("foreshore", "Shore&sun8"),
            ("tygerberg", "Tyg3r!mt6"),
        ]
        for (shortname, pwd), branch in zip(manager_creds, BRANCHES):
            demo_users.append({
                "username": shortname,
                "password": pwd,
                "role": "manager",
                "branch": branch,
                "name": f"{branch} Manager",
            })

        for user in demo_users:
            if user["username"] not in existing_usernames:
                users_ws.append_row([
                    user["username"],
                    hash_password(user["password"]),
                    user["role"],
                    user["branch"],
                    user["name"],
                ])
                print(f"  Added: {user['username']} ({user['role']}) — password: {user['password']}")
            else:
                print(f"  Skipped (exists): {user['username']}")

    print("\n✅ Setup complete!")
    print(f"Run the dashboard with: streamlit run app.py")


if __name__ == "__main__":
    main()
