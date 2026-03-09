"""Google Sheets data layer — all reads and writes go through here."""

import datetime

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from config import (
    SHEET_ACTUALS,
    SHEET_AUDIT,
    SHEET_BUDGET,
    SHEET_SETTINGS,
    SHEET_USERS,
    SPREADSHEET_NAME,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource(ttl=300)
def _get_client():
    """Create and cache authenticated gspread client."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def _get_spreadsheet():
    """Open the main spreadsheet by name."""
    client = _get_client()
    return client.open(SPREADSHEET_NAME)


# --- Users ---

@st.cache_data(ttl=120)
def get_users():
    """Read all users from the Users sheet."""
    ws = _get_spreadsheet().worksheet(SHEET_USERS)
    return ws.get_all_records()


# --- Budget ---

@st.cache_data(ttl=120)
def get_budget_data() -> pd.DataFrame:
    """Read all budget rows into a DataFrame."""
    ws = _get_spreadsheet().worksheet(SHEET_BUDGET)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def get_budget_for_branch_month(branch: str, month: str):
    """Get budget row for a specific branch and month."""
    df = get_budget_data()
    if df.empty:
        return None
    match = df[(df["branch"] == branch) & (df["month"] == month)]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


# --- Actuals ---

@st.cache_data(ttl=60)
def get_actuals_data() -> pd.DataFrame:
    """Read all actuals rows into a DataFrame."""
    ws = _get_spreadsheet().worksheet(SHEET_ACTUALS)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    # Ensure numeric columns
    numeric_cols = [
        "sales", "parts_contribution", "parts_gp_pct",
        "paints", "consumables_paintshop", "consumables",
        "diagnostics", "additionals", "csi",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def get_actuals_for_branch_month(branch: str, month: str):
    """Get actuals row for a specific branch and month."""
    df = get_actuals_data()
    if df.empty:
        return None
    match = df[(df["branch"] == branch) & (df["month"] == month)]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def save_actuals(branch: str, month: str, data: dict, user_email: str):
    """Write or update actuals for a branch/month. Appends audit log."""
    ws = _get_spreadsheet().worksheet(SHEET_ACTUALS)
    all_records = ws.get_all_records()
    now = datetime.datetime.now().isoformat()

    row_data = {
        "branch": branch,
        "month": month,
        "sales": data.get("sales", 0),
        "parts_contribution": data.get("parts_contribution", 0),
        "parts_gp_pct": data.get("parts_gp_pct", 0),
        "paints": data.get("paints", 0),
        "consumables_paintshop": data.get("consumables_paintshop", 0),
        "consumables": data.get("consumables", 0),
        "diagnostics": data.get("diagnostics", 0),
        "additionals": data.get("additionals", 0),
        "csi": data.get("csi", 0),
        "submitted_by": user_email,
        "submitted_at": now,
    }

    # Find existing row or append
    row_idx = None
    for i, rec in enumerate(all_records):
        if rec.get("branch") == branch and rec.get("month") == month:
            row_idx = i + 2  # +1 for header, +1 for 1-indexed
            old_data = rec
            break

    headers = ws.row_values(1)
    row_values = [row_data.get(h, "") for h in headers]

    if row_idx:
        ws.update(f"A{row_idx}:{chr(64 + len(headers))}{row_idx}", [row_values])
        _log_audit(user_email, "update", branch, month, old_data, row_data)
    else:
        ws.append_row(row_values)
        _log_audit(user_email, "create", branch, month, {}, row_data)

    # Clear cache so fresh data loads
    get_actuals_data.clear()


def _log_audit(user: str, action: str, branch: str, month: str, old: dict, new: dict):
    """Append an entry to the AuditLog sheet."""
    try:
        ws = _get_spreadsheet().worksheet(SHEET_AUDIT)
        now = datetime.datetime.now().isoformat()
        ws.append_row([now, user, action, branch, month, str(old), str(new)])
    except Exception:
        pass  # Audit logging should never break the app


# --- Budget write (for directors) ---

def save_budget(branch: str, month: str, data: dict, user_email: str):
    """Write or update budget for a branch/month."""
    ws = _get_spreadsheet().worksheet(SHEET_BUDGET)
    all_records = ws.get_all_records()
    now = datetime.datetime.now().isoformat()

    row_data = {
        "branch": branch,
        "month": month,
        "sales_target": data.get("sales_target", 0),
        "paint_labour_pct": data.get("paint_labour_pct", 49),
        "parts_sales_pct": data.get("parts_sales_pct", 51),
        "parts_markup": data.get("parts_markup", 25),
        "cos_other_pct": data.get("cos_other_pct", 7),
        "rsb_paint_pct": data.get("rsb_paint_pct", 4),
        "consumables_pct": data.get("consumables_pct", 3),
        "diagnostics_target": data.get("diagnostics_target", 0),
        "additionals_target": data.get("additionals_target", 0),
        "csi_target": data.get("csi_target", 0),
        "updated_by": user_email,
        "updated_at": now,
    }

    row_idx = None
    for i, rec in enumerate(all_records):
        if rec.get("branch") == branch and rec.get("month") == month:
            row_idx = i + 2
            break

    headers = ws.row_values(1)
    row_values = [row_data.get(h, "") for h in headers]

    if row_idx:
        ws.update(f"A{row_idx}:{chr(64 + len(headers))}{row_idx}", [row_values])
    else:
        ws.append_row(row_values)

    get_budget_data.clear()


# --- Settings ---

@st.cache_data(ttl=120)
def get_settings():
    """Read all settings as a dict of key -> value."""
    try:
        ws = _get_spreadsheet().worksheet(SHEET_SETTINGS)
        records = ws.get_all_records()
        return {r["key"]: r["value"] for r in records}
    except Exception:
        return {}


def get_setting(key: str, default=None):
    """Get a single setting value."""
    settings = get_settings()
    return settings.get(key, default)


def save_setting(key: str, value, user_email: str):
    """Write or update a setting."""
    try:
        ws = _get_spreadsheet().worksheet(SHEET_SETTINGS)
    except Exception:
        # Create the sheet if it doesn't exist
        ss = _get_spreadsheet()
        ws = ss.add_worksheet(title=SHEET_SETTINGS, rows=50, cols=4)
        ws.append_row(["key", "value", "updated_by", "updated_at"])

    all_records = ws.get_all_records()
    now = datetime.datetime.now().isoformat()

    row_idx = None
    for i, rec in enumerate(all_records):
        if rec.get("key") == key:
            row_idx = i + 2
            break

    row_values = [key, value, user_email, now]

    if row_idx:
        ws.update(f"A{row_idx}:D{row_idx}", [row_values])
    else:
        ws.append_row(row_values)

    get_settings.clear()
