# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GP Dashboard — a Streamlit web app for tracking monthly Gross Profit calculations across 5 branches. Uses Google Sheets as the backend database, deployed on Streamlit Cloud.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# First-time setup: create Google Sheet with tabs and demo users
python setup_sheets.py

# Run locally
streamlit run app.py

# Deploy: push to GitHub, connect repo on share.streamlit.io
```

## Architecture

- **app.py** — Main Streamlit app. All 4 pages (Dashboard, Manager Input, Quarterly Summary, Budget Setup) in one file with sidebar navigation. Renders GP tables as raw HTML for styling control.
- **sheets.py** — Google Sheets data layer via gspread. All reads cached with `st.cache_data` (TTL-based). Handles CRUD for Users, Budget, Actuals, and AuditLog tabs.
- **calculations.py** — Pure business logic. GP formula: `Sales - Parts Costs - RSB Paint (4%) - Consumables (3%)`. No Streamlit or I/O dependencies.
- **auth.py** — Session-based auth using `st.session_state`. Passwords hashed with bcrypt. Two roles: `manager` (branch-restricted) and `director` (sees all branches).
- **config.py** — All constants: branch names, month lists, quarter definitions, GP rates, sheet tab names.
- **utils.py** — Currency formatting (South African Rand), percentage formatting, variance color helpers.
- **setup_sheets.py** — One-time CLI script to initialize Google Sheet structure and create demo users. Not part of the running app.

## Data Flow

1. Directors set budget targets per branch/month via Budget Setup page → writes to `Budget` sheet tab
2. Branch managers enter actuals via Manager Input form → writes to `Actuals` sheet tab
3. Dashboard page reads both, runs GP calculations, renders table + charts
4. All writes append to `AuditLog` sheet tab

## Auth & Access Control

- Managers can only view/edit their own branch
- Directors can view all branches and manage budgets
- `get_allowed_branches()` in auth.py enforces branch filtering
- Google Sheet credentials stored in `.streamlit/secrets.toml` (never committed)

## GP Calculation

```
RSB Paint    = Sales × 4%
Consumables  = Sales × 3%
Gross Profit = Sales - Parts Costs - RSB Paint - Consumables
GP %         = Gross Profit / Sales × 100
```

Rates defined in `config.py` as `RSB_PAINT_PCT` and `CONSUMABLES_PCT`.

## Google Sheets Structure

Four tabs in the spreadsheet `GP_Dashboard_Data`:
- **Users**: email, password_hash, role, branch, name
- **Budget**: branch, month, sales_target, paint_labour_pct, parts_sales_pct, parts_markup, diagnostics_target, additionals_target, csi_target
- **Actuals**: branch, month, sales, parts_contribution, parts_gp_pct, paints, consumables_paintshop, consumables, diagnostics, additionals, csi
- **AuditLog**: timestamp, user_email, action, branch, month, old_data, new_data
