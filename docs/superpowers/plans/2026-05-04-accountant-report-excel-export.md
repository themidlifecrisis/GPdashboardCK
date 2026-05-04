# Accountant Report & Excel Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sidebar page **📑 Accountant Report** visible only to accountant/director/admin. The page shows a cross-branch GP summary for the selected month and lets the user download a multi-sheet Excel workbook (Summary + one sheet per branch).

**Architecture:** New `reports.py` module holds pure logic — assembling the report dict and serializing it to xlsx bytes via `openpyxl`. Page block lives in `app.py`. Existing helpers `targets_from_budget` and `actuals_from_row` move from `app.py` into `calculations.py` with `cos_other_pct` made an explicit argument so `reports.py` stays free of Streamlit imports. New auth helper `can_view_accountant_report()` gates the page in two places — sidebar nav and page block.

**Tech Stack:** Python 3, Streamlit, gspread, pandas, openpyxl (new).

**Spec:** `docs/superpowers/specs/2026-05-04-accountant-report-excel-export-design.md`

**Note on testing:** The spec explicitly defers a test suite ("adding one is out of scope for this change"). This plan uses Python REPL verification snippets and manual app-level checks instead of pytest. If a future plan adds pytest, the pure functions in `reports.py` and the lifted helpers in `calculations.py` will be straightforward to retrofit with unit tests.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `requirements.txt` | modify | Pin `openpyxl>=3.1.0`. |
| `auth.py` | modify | Add `can_view_accountant_report()`. |
| `calculations.py` | modify | Receive `targets_from_budget` and `actuals_from_row` (lifted from `app.py`), with `cos_other_pct` as explicit arg. |
| `reports.py` | **create** | `build_month_report(month, cos_other_pct)` and `build_excel_workbook(report)`. No Streamlit, no Sheets imports — calls into `calculations.py` and accepts dependencies as arguments. |
| `app.py` | modify | Update call sites of moved helpers; add conditional sidebar entry; add new page block. |
| `CLAUDE.md` | modify | Document new module and page. |

---

## Task 1: Add openpyxl dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add openpyxl to requirements.txt**

Open `requirements.txt`. The current contents are:

```
streamlit>=1.41.0
gspread>=6.1.0
google-auth>=2.38.0
bcrypt>=4.2.0
pandas>=2.2.0
plotly>=5.24.0
```

Add a new line at the bottom:

```
openpyxl>=3.1.0
```

Final file:

```
streamlit>=1.41.0
gspread>=6.1.0
google-auth>=2.38.0
bcrypt>=4.2.0
pandas>=2.2.0
plotly>=5.24.0
openpyxl>=3.1.0
```

- [ ] **Step 2: Install locally**

Run from the project root:

```bash
pip install openpyxl>=3.1.0
```

Expected: success message ending with `Successfully installed openpyxl-3.x.x` (or "already satisfied" — pandas usually pulls it in transitively).

- [ ] **Step 3: Verify import works**

Run:

```bash
python -c "import openpyxl; print(openpyxl.__version__)"
```

Expected: a version string `3.x.x` printed, no traceback.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "Pin openpyxl for Excel export support"
```

---

## Task 2: Add `can_view_accountant_report` auth helper

**Files:**
- Modify: `auth.py`

- [ ] **Step 1: Add the helper to auth.py**

Open `auth.py`. Find the existing `is_director()` function (around line 95). Add a new function immediately after `get_allowed_branches` at the end of the file:

```python
def can_view_accountant_report() -> bool:
    """Visibility for the Accountant Report page.

    Same role set as is_director() today, but kept as its own helper so a
    future change (e.g. restricting to accountant only) is a one-line edit.
    """
    return st.session_state.get("user_role") in (ROLE_ACCOUNTANT, ROLE_DIRECTOR, ROLE_ADMIN)
```

The imports at the top of `auth.py` already include `ROLE_ACCOUNTANT, ROLE_ADMIN, ROLE_DIRECTOR, ROLE_MANAGER` from `config`, so no import changes needed.

- [ ] **Step 2: Verify the function loads**

Run from project root:

```bash
python -c "from auth import can_view_accountant_report; print(can_view_accountant_report)"
```

Expected: prints something like `<function can_view_accountant_report at 0x...>`. No traceback.

- [ ] **Step 3: Commit**

```bash
git add auth.py
git commit -m "Add can_view_accountant_report auth helper"
```

---

## Task 3: Lift helpers into `calculations.py`

The helpers `targets_from_budget` and `actuals_from_row` currently live inside `app.py` (lines 185–211). They wrap `calculate_targets` and `calculate_gp_actuals` with budget-row dict parsing. Both call `get_cos_other_pct()` from `app.py`, which reads from Streamlit secrets/Sheets — that's the impurity we need to remove.

This task moves both helpers into `calculations.py` and makes `cos_other_pct` an explicit argument. App.py call sites are updated to pass `get_cos_other_pct()` as that argument.

**Files:**
- Modify: `calculations.py`
- Modify: `app.py:162-211, 528, 757, 762, and any other call sites of the two helpers`

- [ ] **Step 1: Add `targets_from_budget` and `actuals_from_row` to `calculations.py`**

Open `calculations.py`. At the bottom of the file (after `calculate_quarterly_summary`), append:

```python
def _budget_pct(budget: dict, key: str, default_decimal: float) -> float:
    """Extract a percentage stored as a whole number (e.g. 7) from a budget row,
    return as a decimal (0.07). Falls back to default_decimal if missing."""
    val = budget.get(key, "")
    if val not in ("", 0, None):
        try:
            return float(val) / 100
        except (ValueError, TypeError):
            pass
    return default_decimal


def targets_from_budget(budget: dict, cos_other_default: float) -> dict:
    """Build a calculate_targets call from a budget sheet row dict.

    cos_other_default is the fallback (as a decimal, e.g. 0.07) used when the
    budget row does not specify cos_other_pct. The caller is responsible for
    sourcing this value (e.g. from app settings).
    """
    return calculate_targets(
        float(budget.get("sales_target", 0)),
        float(budget.get("paint_labour_pct", 49)) / 100,
        float(budget.get("parts_sales_pct", 51)) / 100,
        float(budget.get("parts_markup", 25)),
        cos_other_pct=_budget_pct(budget, "cos_other_pct", cos_other_default),
        rsb_paint_pct=_budget_pct(budget, "rsb_paint_pct", RSB_PAINT_PCT),
        consumables_pct=_budget_pct(budget, "consumables_pct", CONSUMABLES_PCT),
    )


def actuals_from_row(act: dict, cos_other_pct: float) -> dict:
    """Build a calculate_gp_actuals call from an actuals sheet row dict.

    cos_other_pct is the configured rate (decimal, e.g. 0.07). The caller
    is responsible for sourcing this value.
    """
    raw_pct = float(act.get("parts_gp_pct", 0))
    pct_decimal = raw_pct / 100 if raw_pct > 1 else raw_pct
    return calculate_gp_actuals(
        sales=float(act.get("sales", 0)),
        parts_contribution=float(act.get("parts_contribution", 0)),
        parts_gp_pct=pct_decimal,
        paints=float(act.get("paints", 0)),
        consumables_paintshop=float(act.get("consumables_paintshop", 0)),
        consumables=float(act.get("consumables", 0)),
        cos_other_pct=cos_other_pct,
    )
```

`calculations.py` already imports `RSB_PAINT_PCT, CONSUMABLES_PCT, COST_OF_SALES_OTHER_PCT` from `config` at the top — those imports stay.

- [ ] **Step 2: Verify the new helpers work standalone**

Run:

```bash
python -c "
from calculations import targets_from_budget, actuals_from_row
b = {'sales_target': 5000000, 'paint_labour_pct': 49, 'parts_sales_pct': 51, 'parts_markup': 25}
t = targets_from_budget(b, cos_other_default=0.07)
print('targets gp_pct:', round(t['gp_pct'], 2))
a = {'sales': 5000000, 'parts_contribution': 2550000, 'parts_gp_pct': 25, 'paints': 200000, 'consumables_paintshop': 50000, 'consumables': 100000}
ag = actuals_from_row(a, cos_other_pct=0.07)
print('actuals gp_pct:', round(ag['gp_pct'], 2))
"
```

Expected: two lines printed, both with reasonable percentages (around 25–35%). No tracebacks.

- [ ] **Step 3: Remove the old definitions from `app.py`**

Open `app.py`. Delete lines 174–211 (the `_budget_pct`, `targets_from_budget`, and `actuals_from_row` definitions). The `get_cos_other_pct` function on lines 162–171 STAYS in `app.py` — it's Streamlit-aware (calls `get_setting`).

After deletion, the `# --- HELPERS ---` block in `app.py` should contain only `get_cos_other_pct`.

- [ ] **Step 4: Import the lifted helpers in `app.py`**

Open `app.py`. Find the existing import block:

```python
from calculations import calculate_gp_actuals, calculate_quarterly_summary, calculate_targets, calculate_variance
```

Replace with:

```python
from calculations import (
    actuals_from_row,
    calculate_gp_actuals,
    calculate_quarterly_summary,
    calculate_targets,
    calculate_variance,
    targets_from_budget,
)
```

- [ ] **Step 5: Update call sites in `app.py` to pass `cos_other_pct`**

Search `app.py` for every call to `targets_from_budget(` and `actuals_from_row(`. As of this writing they appear at:

- Dashboard page: `targets = targets_from_budget(budget)` (around line 522)
- Dashboard page: `actuals_gp = actuals_from_row(actuals_raw)` (around line 528)
- Quarterly Summary: `monthly_actuals.append(actuals_from_row(act))` (around line 757)
- Quarterly Summary: `monthly_targets.append(targets_from_budget(bud))` (around line 762)
- Quarterly Summary branch comparison: `monthly_gps.append(actuals_from_row(act))` (around line 880)

Update each call to pass the cos_other rate. Pattern:

| Old | New |
|---|---|
| `targets_from_budget(bud)` | `targets_from_budget(bud, get_cos_other_pct())` |
| `actuals_from_row(act)` | `actuals_from_row(act, get_cos_other_pct())` |

To avoid repeated calls in tight loops, optionally cache it in a local variable at the top of the page block, e.g. `cos_pct = get_cos_other_pct()`, and pass `cos_pct`. Either approach is fine.

Concrete edit for the Dashboard page (around lines 521–528):

```python
    # Calculate targets
    if budget:
        targets = targets_from_budget(budget, get_cos_other_pct())
    else:
        targets = None

    # Calculate actuals GP
    if actuals_raw:
        actuals_gp = actuals_from_row(actuals_raw, get_cos_other_pct())
        ...
```

Concrete edit for the Quarterly Summary loop (around lines 752–765):

```python
            cos_pct = get_cos_other_pct()
            for m in q_months:
                act = get_actuals_for_branch_month(selected_branch, m)
                bud = get_budget_for_branch_month(selected_branch, m)

                if act:
                    monthly_actuals.append(actuals_from_row(act, cos_pct))
                else:
                    monthly_actuals.append(calculate_gp_actuals(0, 0, 0, 0, 0, 0))

                if bud:
                    monthly_targets.append(targets_from_budget(bud, cos_pct))
                else:
                    monthly_targets.append(None)
                ...
```

Concrete edit for the branch-comparison loop in Quarterly Summary (around line 877):

```python
        cos_pct = get_cos_other_pct()
        for branch in BRANCHES:
            ...
            for m in q_months:
                act = get_actuals_for_branch_month(branch, m)
                if act:
                    monthly_gps.append(actuals_from_row(act, cos_pct))
            ...
```

- [ ] **Step 6: Verify there are no remaining stale call sites**

Run:

```bash
grep -nE "targets_from_budget\(|actuals_from_row\(" app.py
```

Expected: every match has TWO arguments (a variable + `cos_pct` or `get_cos_other_pct()`). If any line shows a single-arg call like `targets_from_budget(bud)`, fix it.

- [ ] **Step 7: Smoke-test the imports load cleanly**

Run:

```bash
python -c "import app" 2>&1 | head -30
```

Expected: either silent success or a Streamlit-related warning (Streamlit's runtime is not active outside `streamlit run`). What you must NOT see: `ImportError`, `NameError`, `TypeError`. If Streamlit complains about missing context — that's fine, it means the imports themselves resolved.

- [ ] **Step 8: Visual smoke test — Dashboard page**

Run:

```bash
streamlit run app.py
```

Sign in (any role). Open the Dashboard page. Pick a branch + month that has data. Confirm: GP table renders, KPI cards show numbers, no tracebacks in the terminal. Stop the server (Ctrl-C).

- [ ] **Step 9: Commit**

```bash
git add app.py calculations.py
git commit -m "Lift targets_from_budget and actuals_from_row into calculations.py

Make cos_other_pct an explicit argument so reports.py can call these
helpers without depending on Streamlit. App page call sites updated to
pass get_cos_other_pct() in."
```

---

## Task 4: Create `reports.py` with `build_month_report`

This task creates the new module and the report-data builder. Excel serialization comes in Task 5.

**Files:**
- Create: `reports.py`

- [ ] **Step 1: Create `reports.py` with `build_month_report`**

Create a new file `reports.py` at the project root with these contents:

```python
"""Accountant report builder — pure logic, no Streamlit or I/O.

Two public functions:
- build_month_report(month, cos_other_pct, budget_df, actuals_df)
    Returns a structured report dict.
- build_excel_workbook(report)
    Returns xlsx bytes for download. Defined in this module (added in
    a later task).
"""

from datetime import datetime

from calculations import (
    actuals_from_row,
    calculate_gp_actuals,
    targets_from_budget,
)
from config import BRANCHES


def _empty_targets() -> dict:
    """Zero-valued target dict, same shape as calculate_targets output."""
    return {
        "sales_target": 0,
        "paint_labour_target": 0,
        "parts_sales_target": 0,
        "parts_markup": 0,
        "parts_costs": 0,
        "cos_other": 0,
        "rsb_paint": 0,
        "consumables": 0,
        "gross_profit": 0,
        "gp_pct": 0.0,
    }


def _row_for_branch(branch: str, targets: dict, actuals: dict, extras: dict) -> dict:
    """Flatten one branch's data into the Summary-row schema."""
    return {
        "branch": branch,
        "sales_target": targets["sales_target"],
        "sales_actual": actuals["sales"],
        "sales_var": actuals["sales"] - targets["sales_target"],
        "parts_costs_target": targets["parts_costs"],
        "parts_costs_actual": actuals["parts_costs"],
        "parts_costs_var": actuals["parts_costs"] - targets["parts_costs"],
        "cos_other_target": targets["cos_other"],
        "cos_other_actual": actuals["cos_other"],
        "cos_other_var": actuals["cos_other"] - targets["cos_other"],
        "rsb_paint_target": targets["rsb_paint"],
        "rsb_paint_actual": actuals["rsb_paint"],
        "rsb_paint_var": actuals["rsb_paint"] - targets["rsb_paint"],
        "consumables_target": targets["consumables"],
        "consumables_actual": actuals["consumables_combined"],
        "consumables_var": actuals["consumables_combined"] - targets["consumables"],
        "gp_target": targets["gross_profit"],
        "gp_actual": actuals["gross_profit"],
        "gp_var": actuals["gross_profit"] - targets["gross_profit"],
        "gp_pct_target": targets["gp_pct"] / 100,  # store as decimal for Excel %
        "gp_pct_actual": actuals["gp_pct"] / 100,
        "diagnostics_target": extras.get("diagnostics_target", 0),
        "diagnostics_actual": extras.get("diagnostics", 0),
        "additionals_target": extras.get("additionals_target", 0),
        "additionals_actual": extras.get("additionals", 0),
        "csi_target": extras.get("csi_target", 0) / 100,  # decimal for Excel %
        "csi_actual": extras.get("csi", 0) / 100,
    }


def _total_row(rows: list[dict]) -> dict:
    """Build the TOTAL aggregation row for the Summary table.

    Sums for currency columns. Weighted GP% = ΣGP / ΣSales.
    Weighted CSI = Σ(CSI × Sales) / ΣSales (uses actual sales as weight).
    """
    sum_keys = [
        "sales_target", "sales_actual", "sales_var",
        "parts_costs_target", "parts_costs_actual", "parts_costs_var",
        "cos_other_target", "cos_other_actual", "cos_other_var",
        "rsb_paint_target", "rsb_paint_actual", "rsb_paint_var",
        "consumables_target", "consumables_actual", "consumables_var",
        "gp_target", "gp_actual", "gp_var",
        "diagnostics_target", "diagnostics_actual",
        "additionals_target", "additionals_actual",
    ]
    totals = {"branch": "TOTAL"}
    for k in sum_keys:
        totals[k] = sum(r[k] for r in rows)

    sales_t = totals["sales_target"]
    sales_a = totals["sales_actual"]
    totals["gp_pct_target"] = (totals["gp_target"] / sales_t) if sales_t > 0 else 0.0
    totals["gp_pct_actual"] = (totals["gp_actual"] / sales_a) if sales_a > 0 else 0.0

    weighted_csi_t = sum(r["csi_target"] * r["sales_target"] for r in rows)
    weighted_csi_a = sum(r["csi_actual"] * r["sales_actual"] for r in rows)
    totals["csi_target"] = (weighted_csi_t / sales_t) if sales_t > 0 else 0.0
    totals["csi_actual"] = (weighted_csi_a / sales_a) if sales_a > 0 else 0.0

    return totals


def build_month_report(
    month: str,
    cos_other_pct: float,
    budget_df,
    actuals_df,
) -> dict:
    """Assemble the cross-branch report for one month.

    Args:
        month: e.g. "March".
        cos_other_pct: configured Cost of Sales Other rate as a decimal (e.g. 0.07).
        budget_df: pandas.DataFrame returned by sheets.get_budget_data().
        actuals_df: pandas.DataFrame returned by sheets.get_actuals_data().

    Returns:
        {
            "month": str,
            "generated_at": ISO timestamp str,
            "summary_rows": [<branch row>, ..., <TOTAL row>],
            "branch_details": {
                "<branch>": {
                    "targets": dict,       # always populated (zero-filled if no budget)
                    "actuals": dict,       # always populated (zero-filled if no actuals)
                    "extras": dict,        # diagnostics/additionals/csi (target & actual)
                    "has_budget": bool,
                    "has_actuals": bool,
                },
                ...
            },
            "branches_with_budget": int,
            "branches_with_actuals": int,
        }
    """
    branch_details = {}
    summary_rows = []
    branches_with_budget = 0
    branches_with_actuals = 0

    for branch in BRANCHES:
        budget_row = None
        if budget_df is not None and not budget_df.empty:
            match = budget_df[
                (budget_df["branch"] == branch) & (budget_df["month"] == month)
            ]
            if not match.empty:
                budget_row = match.iloc[0].to_dict()

        actuals_row = None
        if actuals_df is not None and not actuals_df.empty:
            match = actuals_df[
                (actuals_df["branch"] == branch) & (actuals_df["month"] == month)
            ]
            if not match.empty:
                actuals_row = match.iloc[0].to_dict()

        if budget_row:
            targets = targets_from_budget(budget_row, cos_other_pct)
            branches_with_budget += 1
        else:
            targets = _empty_targets()

        if actuals_row:
            actuals = actuals_from_row(actuals_row, cos_other_pct)
            branches_with_actuals += 1
        else:
            actuals = calculate_gp_actuals(0, 0, 0, 0, 0, 0, cos_other_pct=cos_other_pct)

        extras = {
            "diagnostics": float(actuals_row.get("diagnostics", 0)) if actuals_row else 0.0,
            "additionals": float(actuals_row.get("additionals", 0)) if actuals_row else 0.0,
            "csi": float(actuals_row.get("csi", 0)) if actuals_row else 0.0,
            "diagnostics_target": float(budget_row.get("diagnostics_target", 0)) if budget_row else 0.0,
            "additionals_target": float(budget_row.get("additionals_target", 0)) if budget_row else 0.0,
            "csi_target": float(budget_row.get("csi_target", 0)) if budget_row else 0.0,
        }

        branch_details[branch] = {
            "targets": targets,
            "actuals": actuals,
            "extras": extras,
            "has_budget": budget_row is not None,
            "has_actuals": actuals_row is not None,
        }

        summary_rows.append(_row_for_branch(branch, targets, actuals, extras))

    summary_rows.append(_total_row(summary_rows))

    return {
        "month": month,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary_rows": summary_rows,
        "branch_details": branch_details,
        "branches_with_budget": branches_with_budget,
        "branches_with_actuals": branches_with_actuals,
    }
```

Note: `build_excel_workbook` is added in Task 5. It's referenced in the docstring at the top so the file's intent is clear.

- [ ] **Step 2: Verify the report builder works with synthetic data**

Run this verification snippet from the project root:

```bash
python -c "
import pandas as pd
from reports import build_month_report

budget_df = pd.DataFrame([
    {'branch': 'CK Constantiaberg', 'month': 'March', 'sales_target': 5000000, 'paint_labour_pct': 49, 'parts_sales_pct': 51, 'parts_markup': 25, 'cos_other_pct': 7, 'rsb_paint_pct': 4, 'consumables_pct': 3, 'diagnostics_target': 50000, 'additionals_target': 30000, 'csi_target': 90},
])
actuals_df = pd.DataFrame([
    {'branch': 'CK Constantiaberg', 'month': 'March', 'sales': 5200000, 'parts_contribution': 2700000, 'parts_gp_pct': 26, 'paints': 220000, 'consumables_paintshop': 60000, 'consumables': 110000, 'diagnostics': 55000, 'additionals': 28000, 'csi': 92},
])
r = build_month_report('March', 0.07, budget_df, actuals_df)
print('month:', r['month'])
print('summary rows:', len(r['summary_rows']))  # 5 branches + TOTAL = 6
print('branches with budget:', r['branches_with_budget'])  # 1
print('branches with actuals:', r['branches_with_actuals'])  # 1
print('first row branch:', r['summary_rows'][0]['branch'])
print('first row sales actual:', r['summary_rows'][0]['sales_actual'])
print('TOTAL row:', r['summary_rows'][-1]['branch'])
print('TOTAL sales actual:', r['summary_rows'][-1]['sales_actual'])  # same as first row (only one branch has data)
print('TOTAL gp_pct_actual:', round(r['summary_rows'][-1]['gp_pct_actual'] * 100, 2))
"
```

Expected output (numbers may vary slightly):

```
month: March
summary rows: 6
branches with budget: 1
branches with actuals: 1
first row branch: CK Constantiaberg
first row sales actual: 5200000.0
TOTAL row: TOTAL
TOTAL sales actual: 5200000.0
TOTAL gp_pct_actual: <some percentage>
```

If anything raises a traceback or the row count is wrong, fix before continuing.

- [ ] **Step 3: Verify a branch with no data shows zeros, not None**

```bash
python -c "
import pandas as pd
from reports import build_month_report
r = build_month_report('March', 0.07, pd.DataFrame(), pd.DataFrame())
print('rows:', len(r['summary_rows']))  # 5 + 1 = 6
print('first row sales target:', r['summary_rows'][0]['sales_target'])  # 0
print('first row sales actual:', r['summary_rows'][0]['sales_actual'])  # 0
print('first row variance:', r['summary_rows'][0]['sales_var'])  # 0
print('first row gp_pct actual:', r['summary_rows'][0]['gp_pct_actual'])  # 0.0
print('branches with budget:', r['branches_with_budget'])  # 0
"
```

Expected: all zeros, no tracebacks.

- [ ] **Step 4: Commit**

```bash
git add reports.py
git commit -m "Add reports.build_month_report

Pure function that assembles the cross-branch GP summary for one month
from budget and actuals DataFrames. Branches with no data appear as
zero-filled rows so missing data is visible in the report rather than
silently dropped. The TOTAL row uses weighted means for GP% and CSI.

Excel serialization comes in a follow-up commit."
```

---

## Task 5: Add `build_excel_workbook` (Summary sheet)

This task adds the Excel writer with the Summary sheet only. The per-branch detail sheets come in Task 6.

**Files:**
- Modify: `reports.py`

- [ ] **Step 1: Add openpyxl imports and constants**

Open `reports.py`. Add new imports below the existing imports:

```python
from io import BytesIO

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
```

Add these module-level constants below the imports (above `_empty_targets`):

```python
# Visual constants
HEADER_FILL = PatternFill(start_color="1E88E5", end_color="1E88E5", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TOTAL_FONT = Font(bold=True)
SECTION_FILL = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid")
SECTION_FONT = Font(bold=True, color="1E88E5")

GREEN_FILL = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
RED_FILL = PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid")

CURRENCY_FMT = "#,##0;(#,##0);-"
PCT_FMT = "0.0%"
```

`CURRENCY_FMT` shows negatives in parentheses and zero as `-`. No "R" prefix — column header carries the unit.

- [ ] **Step 2: Add the Summary-sheet writer**

Append to `reports.py`:

```python
# Schema for Summary sheet — (header_label, key_in_row_dict, format_kind, is_cost)
# format_kind ∈ {"currency", "percent", "text"}
# is_cost: True means lower-is-better (variance colours invert)
_SUMMARY_COLUMNS = [
    ("Branch",                "branch",              "text",     False),
    ("Sales Target",          "sales_target",        "currency", False),
    ("Sales Actual",          "sales_actual",        "currency", False),
    ("Sales Var",             "sales_var",           "currency", False),
    ("Parts Costs Target",    "parts_costs_target",  "currency", True),
    ("Parts Costs Actual",    "parts_costs_actual",  "currency", True),
    ("Parts Costs Var",       "parts_costs_var",     "currency", True),
    ("COS Other Target",      "cos_other_target",    "currency", True),
    ("COS Other Actual",      "cos_other_actual",    "currency", True),
    ("COS Other Var",         "cos_other_var",       "currency", True),
    ("RSB Paint Target",      "rsb_paint_target",    "currency", True),
    ("RSB Paint Actual",      "rsb_paint_actual",    "currency", True),
    ("RSB Paint Var",         "rsb_paint_var",       "currency", True),
    ("Consumables Target",    "consumables_target",  "currency", True),
    ("Consumables Actual",    "consumables_actual",  "currency", True),
    ("Consumables Var",       "consumables_var",     "currency", True),
    ("GP Target",             "gp_target",           "currency", False),
    ("GP Actual",             "gp_actual",           "currency", False),
    ("GP Var",                "gp_var",              "currency", False),
    ("GP% Target",            "gp_pct_target",       "percent",  False),
    ("GP% Actual",            "gp_pct_actual",       "percent",  False),
    ("Diagnostics Target",    "diagnostics_target",  "currency", False),
    ("Diagnostics Actual",    "diagnostics_actual",  "currency", False),
    ("Additionals Target",    "additionals_target",  "currency", False),
    ("Additionals Actual",    "additionals_actual",  "currency", False),
    ("CSI Target",            "csi_target",          "percent",  False),
    ("CSI Actual",            "csi_actual",          "percent",  False),
]


def _apply_variance_colour(ws, col_letter: str, first_row: int, last_row: int, is_cost: bool):
    """Add conditional formatting: green for 'good' variance, red for 'bad'.

    For revenue columns: positive var = green, negative = red.
    For cost columns (is_cost=True): negative var = green, positive = red.
    """
    rng = f"{col_letter}{first_row}:{col_letter}{last_row}"
    if is_cost:
        good = CellIsRule(operator="lessThan", formula=["0"], fill=GREEN_FILL)
        bad = CellIsRule(operator="greaterThan", formula=["0"], fill=RED_FILL)
    else:
        good = CellIsRule(operator="greaterThan", formula=["0"], fill=GREEN_FILL)
        bad = CellIsRule(operator="lessThan", formula=["0"], fill=RED_FILL)
    ws.conditional_formatting.add(rng, good)
    ws.conditional_formatting.add(rng, bad)


def _write_summary_sheet(wb: Workbook, report: dict):
    """Populate the 'Summary' sheet with one row per branch + TOTAL."""
    ws = wb.active
    ws.title = "Summary"

    # Title row
    ws.cell(row=1, column=1, value=f"Cross-Branch Summary — {report['month']}").font = Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=f"Generated {report['generated_at']}").font = Font(italic=True, color="666666")

    header_row = 4
    first_data_row = 5

    # Headers
    for col_idx, (label, _key, _fmt, _is_cost) in enumerate(_SUMMARY_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Data rows
    rows = report["summary_rows"]
    for row_offset, row in enumerate(rows):
        r = first_data_row + row_offset
        is_total = (row.get("branch") == "TOTAL")
        for col_idx, (_label, key, fmt, _is_cost) in enumerate(_SUMMARY_COLUMNS, start=1):
            cell = ws.cell(row=r, column=col_idx, value=row.get(key, 0))
            if fmt == "currency":
                cell.number_format = CURRENCY_FMT
            elif fmt == "percent":
                cell.number_format = PCT_FMT
            if is_total:
                cell.font = TOTAL_FONT
                cell.fill = SECTION_FILL

    # Conditional formatting on variance columns (data rows only — not TOTAL,
    # since totals already convey the aggregate)
    last_branch_row = first_data_row + len(rows) - 2  # exclude TOTAL row from CF
    for col_idx, (_label, key, _fmt, is_cost) in enumerate(_SUMMARY_COLUMNS, start=1):
        if not key.endswith("_var"):
            continue
        col_letter = get_column_letter(col_idx)
        _apply_variance_colour(ws, col_letter, first_data_row, last_branch_row, is_cost)

    # Column widths
    ws.column_dimensions["A"].width = 24
    for col_idx in range(2, len(_SUMMARY_COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16

    # Freeze panes: top header rows + first column
    ws.freeze_panes = "B5"


def build_excel_workbook(report: dict) -> bytes:
    """Serialize a report dict (from build_month_report) to xlsx bytes."""
    wb = Workbook()
    _write_summary_sheet(wb, report)
    # Per-branch sheets come in a follow-up task.

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 3: Verify the workbook builds and is valid xlsx**

Run:

```bash
python -c "
import pandas as pd
from reports import build_month_report, build_excel_workbook
budget_df = pd.DataFrame([
    {'branch': 'CK Constantiaberg', 'month': 'March', 'sales_target': 5000000, 'paint_labour_pct': 49, 'parts_sales_pct': 51, 'parts_markup': 25, 'cos_other_pct': 7, 'rsb_paint_pct': 4, 'consumables_pct': 3, 'diagnostics_target': 50000, 'additionals_target': 30000, 'csi_target': 90},
    {'branch': 'CK Tokai', 'month': 'March', 'sales_target': 4500000, 'paint_labour_pct': 49, 'parts_sales_pct': 51, 'parts_markup': 25, 'cos_other_pct': 7, 'rsb_paint_pct': 4, 'consumables_pct': 3, 'diagnostics_target': 45000, 'additionals_target': 25000, 'csi_target': 88},
])
actuals_df = pd.DataFrame([
    {'branch': 'CK Constantiaberg', 'month': 'March', 'sales': 5200000, 'parts_contribution': 2700000, 'parts_gp_pct': 26, 'paints': 220000, 'consumables_paintshop': 60000, 'consumables': 110000, 'diagnostics': 55000, 'additionals': 28000, 'csi': 92},
])
r = build_month_report('March', 0.07, budget_df, actuals_df)
xlsx = build_excel_workbook(r)
print('xlsx bytes:', len(xlsx))
with open('/tmp/test_report.xlsx', 'wb') as f:
    f.write(xlsx)
print('written to /tmp/test_report.xlsx')
"
```

Expected: `xlsx bytes: <some number around 7000-12000>`, file written.

Now verify the file is readable as a workbook:

```bash
python -c "
from openpyxl import load_workbook
wb = load_workbook('/tmp/test_report.xlsx')
print('sheets:', wb.sheetnames)
ws = wb['Summary']
print('A1:', ws['A1'].value)
print('A4:', ws['A4'].value)  # 'Branch' header
print('A5:', ws['A5'].value)  # First branch
print('B5 (sales target):', ws['B5'].value)
print('last row branch:', ws.cell(row=ws.max_row, column=1).value)  # 'TOTAL'
"
```

Expected: `sheets: ['Summary']`, `A1: Cross-Branch Summary — March`, `A4: Branch`, `A5: CK Constantiaberg`, `B5: 5000000` (or `5000000.0`), last row branch: `TOTAL`.

- [ ] **Step 4: Open the file manually**

Open `/tmp/test_report.xlsx` in Excel / Numbers / LibreOffice. Visual checks:
- Headers are blue with white text.
- Currency cells show formatted numbers like `5,000,000`.
- Percentage cells show e.g. `35.0%`.
- TOTAL row at the bottom is bold with light-blue fill.
- Variance columns: positive values in revenue cols are green-tinted, negatives red-tinted; cost-column variances flip.
- Top rows and first column stay frozen when scrolling.

- [ ] **Step 5: Commit**

```bash
git add reports.py
git commit -m "Add Summary sheet to Excel workbook

build_excel_workbook now emits a 'Summary' sheet with one row per branch
plus a weighted TOTAL row. Currency columns use CURRENCY_FMT; percentage
columns use PCT_FMT (stored as decimals). Variance cells get conditional
formatting — green for good, red for bad — and cost-column rules invert
so under-budget shows green. Per-branch detail sheets come next."
```

---

## Task 6: Add per-branch detail sheets to `build_excel_workbook`

**Files:**
- Modify: `reports.py`

- [ ] **Step 1: Add the per-branch sheet writer**

Append to `reports.py` (above `build_excel_workbook`):

```python
def _write_branch_sheet(wb: Workbook, branch: str, detail: dict, month: str, generated_at: str):
    """Write one sheet for a single branch — mirrors the dashboard GP table layout."""
    ws = wb.create_sheet(title=branch[:31])  # Excel sheet-name limit
    targets = detail["targets"]
    actuals = detail["actuals"]
    extras = detail["extras"]

    # Caption
    ws.cell(row=1, column=1, value=f"{branch} — {month} — Generated {generated_at}").font = Font(italic=True, color="666666")

    # Compute Act % values (as decimals for PCT_FMT)
    a_sales = actuals["sales"]
    def pct_of_sales(actual_value: float) -> float:
        return (actual_value / a_sales) if a_sales > 0 else 0.0

    t_sales = targets["sales_target"]
    def t_pct_of_sales(target_value: float) -> float:
        return (target_value / t_sales) if t_sales > 0 else 0.0

    # Section: Targets
    ws.cell(row=3, column=1, value="Targets").font = SECTION_FONT
    ws.cell(row=3, column=1).fill = SECTION_FILL

    ws.cell(row=4, column=1, value="Sales Target")
    ws.cell(row=4, column=2, value=targets["sales_target"]).number_format = CURRENCY_FMT

    ws.cell(row=5, column=1, value="Paint Labour Other Target")
    ws.cell(row=5, column=2, value=targets["paint_labour_target"]).number_format = CURRENCY_FMT

    ws.cell(row=6, column=1, value="Parts Sales Target")
    ws.cell(row=6, column=2, value=targets["parts_sales_target"]).number_format = CURRENCY_FMT

    ws.cell(row=7, column=1, value="Parts Markup")
    ws.cell(row=7, column=2, value=targets["parts_markup"] / 100).number_format = PCT_FMT

    # Section: GP Calculations
    ws.cell(row=9, column=1, value="GP Calculations").font = SECTION_FONT
    ws.cell(row=9, column=1).fill = SECTION_FILL

    headers = ["Item", "Target", "Actual", "Variance", "Act %", "Target %"]
    for col_idx, label in enumerate(headers, start=1):
        c = ws.cell(row=10, column=col_idx, value=label)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")

    # Rows: (label, target, actual, is_cost)
    gp_rows = [
        ("Sales",                targets["sales_target"], actuals["sales"], False),
        ("Parts Costs",          targets["parts_costs"],  actuals["parts_costs"], True),
        ("Cost of Sales Other",  targets["cos_other"],    actuals["cos_other"], True),
        ("RSB Paint",            targets["rsb_paint"],    actuals["rsb_paint"], True),
        ("Consumables Combined", targets["consumables"],  actuals["consumables_combined"], True),
    ]
    var_first_row = 11
    for offset, (label, t_val, a_val, is_cost) in enumerate(gp_rows):
        r = var_first_row + offset
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=t_val).number_format = CURRENCY_FMT
        ws.cell(row=r, column=3, value=a_val).number_format = CURRENCY_FMT
        ws.cell(row=r, column=4, value=a_val - t_val).number_format = CURRENCY_FMT
        ws.cell(row=r, column=5, value=pct_of_sales(a_val)).number_format = PCT_FMT
        ws.cell(row=r, column=6, value=t_pct_of_sales(t_val)).number_format = PCT_FMT
        # Per-row variance colouring via conditional formatting
        col_letter = get_column_letter(4)
        _apply_variance_colour(ws, col_letter, r, r, is_cost)

    var_last_row = var_first_row + len(gp_rows) - 1
    gp_row = var_last_row + 1
    pct_row = var_last_row + 2

    ws.cell(row=gp_row, column=1, value="Gross Profit").font = TOTAL_FONT
    ws.cell(row=gp_row, column=2, value=targets["gross_profit"]).number_format = CURRENCY_FMT
    ws.cell(row=gp_row, column=3, value=actuals["gross_profit"]).number_format = CURRENCY_FMT
    ws.cell(row=gp_row, column=4, value=actuals["gross_profit"] - targets["gross_profit"]).number_format = CURRENCY_FMT
    for c in range(1, 5):
        ws.cell(row=gp_row, column=c).font = TOTAL_FONT
    _apply_variance_colour(ws, "D", gp_row, gp_row, False)

    ws.cell(row=pct_row, column=1, value="GP %").font = TOTAL_FONT
    ws.cell(row=pct_row, column=2, value=targets["gp_pct"] / 100).number_format = PCT_FMT
    ws.cell(row=pct_row, column=3, value=actuals["gp_pct"] / 100).number_format = PCT_FMT
    ws.cell(row=pct_row, column=4, value=(actuals["gp_pct"] - targets["gp_pct"]) / 100).number_format = PCT_FMT
    for c in range(1, 5):
        ws.cell(row=pct_row, column=c).font = TOTAL_FONT

    # Section: Additional KPIs
    kpi_section_row = pct_row + 2
    ws.cell(row=kpi_section_row, column=1, value="Additional KPIs").font = SECTION_FONT
    ws.cell(row=kpi_section_row, column=1).fill = SECTION_FILL

    kpi_rows = [
        ("Diagnostics", extras.get("diagnostics_target", 0), extras.get("diagnostics", 0), "currency"),
        ("Additionals", extras.get("additionals_target", 0), extras.get("additionals", 0), "currency"),
        ("CSI",         extras.get("csi_target", 0) / 100,   extras.get("csi", 0) / 100,   "percent"),
    ]
    for offset, (label, t_val, a_val, fmt) in enumerate(kpi_rows):
        r = kpi_section_row + 1 + offset
        ws.cell(row=r, column=1, value=label)
        cell_t = ws.cell(row=r, column=2, value=t_val)
        cell_a = ws.cell(row=r, column=3, value=a_val)
        if fmt == "currency":
            cell_t.number_format = CURRENCY_FMT
            cell_a.number_format = CURRENCY_FMT
            ws.cell(row=r, column=4, value=a_val - t_val).number_format = CURRENCY_FMT
        else:
            cell_t.number_format = PCT_FMT
            cell_a.number_format = PCT_FMT
            # No variance cell for CSI (matches dashboard behaviour)

    # Column widths
    ws.column_dimensions["A"].width = 28
    for col in ["B", "C", "D", "E", "F"]:
        ws.column_dimensions[col].width = 16

    # Freeze top 2 rows
    ws.freeze_panes = "A3"
```

- [ ] **Step 2: Wire it into `build_excel_workbook`**

In `reports.py`, find the existing `build_excel_workbook` function and update it:

```python
def build_excel_workbook(report: dict) -> bytes:
    """Serialize a report dict (from build_month_report) to xlsx bytes."""
    wb = Workbook()
    _write_summary_sheet(wb, report)
    for branch, detail in report["branch_details"].items():
        _write_branch_sheet(wb, branch, detail, report["month"], report["generated_at"])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 3: Re-verify the workbook structure**

Run:

```bash
python -c "
import pandas as pd
from reports import build_month_report, build_excel_workbook
from openpyxl import load_workbook
budget_df = pd.DataFrame([
    {'branch': 'CK Constantiaberg', 'month': 'March', 'sales_target': 5000000, 'paint_labour_pct': 49, 'parts_sales_pct': 51, 'parts_markup': 25, 'cos_other_pct': 7, 'rsb_paint_pct': 4, 'consumables_pct': 3, 'diagnostics_target': 50000, 'additionals_target': 30000, 'csi_target': 90},
])
actuals_df = pd.DataFrame([
    {'branch': 'CK Constantiaberg', 'month': 'March', 'sales': 5200000, 'parts_contribution': 2700000, 'parts_gp_pct': 26, 'paints': 220000, 'consumables_paintshop': 60000, 'consumables': 110000, 'diagnostics': 55000, 'additionals': 28000, 'csi': 92},
])
r = build_month_report('March', 0.07, budget_df, actuals_df)
xlsx = build_excel_workbook(r)
with open('/tmp/test_report.xlsx', 'wb') as f:
    f.write(xlsx)
wb = load_workbook('/tmp/test_report.xlsx')
print('sheets:', wb.sheetnames)
print('expected: Summary + 5 branch sheets =', 6, 'sheets')
"
```

Expected:

```
sheets: ['Summary', 'CK Constantiaberg', 'CK Tokai', 'JCF', 'CK Foreshore', 'CK Tygerberg']
expected: Summary + 5 branch sheets = 6 sheets
```

- [ ] **Step 4: Open the file in Excel/Numbers/LibreOffice**

Visual verification:
- Six tabs along the bottom: Summary + 5 branches.
- The branch sheet for the branch that has data (CK Constantiaberg) shows actual numbers.
- The other four branch sheets show all zeros.
- "Targets", "GP Calculations", "Additional KPIs" appear as section headers in light blue.
- Gross Profit and GP % rows are bold.
- Variance cells in the Variance column colour based on direction (green = good).

- [ ] **Step 5: Commit**

```bash
git add reports.py
git commit -m "Add per-branch detail sheets to Excel workbook

Each branch gets its own sheet mirroring the Dashboard GP table layout:
sections for Targets, GP Calculations, and Additional KPIs. Variance
column gets the same green/red conditional formatting (inverted on cost
rows) used on the Summary sheet."
```

---

## Task 7: Add the Accountant Report page in `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Import the new helpers and module**

Open `app.py`. Find the existing `from auth import (...)` block (around line 9). Add `can_view_accountant_report` to the imports:

```python
from auth import (
    can_edit_actuals,
    can_edit_budgets,
    can_view_accountant_report,
    get_allowed_branches,
    get_user_branch,
    is_director,
    is_manager,
    login_form,
    logout,
)
```

Find the existing `from sheets import (...)` block (around line 21). Add `get_actuals_data` and `get_budget_data` if not already imported (check the current state — they may already be imported). Final block should include them:

```python
from sheets import (
    get_actuals_data,
    get_actuals_for_branch_month,
    get_budget_data,
    get_budget_for_branch_month,
    get_setting,
    get_users,
    save_actuals,
    save_budget,
    save_setting,
)
```

Add a new import line just below the `from sheets import` block:

```python
from reports import build_excel_workbook, build_month_report
```

- [ ] **Step 2: Make the sidebar nav include the new page (conditional on role)**

Find the existing sidebar navigation `st.radio` call (around line 134):

```python
    page = st.radio(
        "Navigation",
        ["📊 Dashboard", "📝 Manager Input", "📈 Quarterly Summary", "🎯 Budget Setup", "⚙️ Settings"],
        label_visibility="collapsed",
    )
```

Replace with:

```python
    nav_options = ["📊 Dashboard", "📝 Manager Input", "📈 Quarterly Summary", "🎯 Budget Setup"]
    if can_view_accountant_report():
        nav_options.append("📑 Accountant Report")
    nav_options.append("⚙️ Settings")
    page = st.radio(
        "Navigation",
        nav_options,
        label_visibility="collapsed",
    )
```

Only the new Accountant Report entry is role-conditional. Existing nav behaviour for the other pages is unchanged — they remain visible to everyone and stop at the page-body level when a user lacks permission. This minimizes behaviour change for existing roles.

- [ ] **Step 3: Add the page block**

Open `app.py`. Find the Settings page block (`elif page == "⚙️ Settings":`). Add a new `elif` block immediately ABOVE it (so the new page appears in the file in the same order as in the nav):

```python
# =====================================================
# PAGE: ACCOUNTANT REPORT (Accountants, Directors, Admins)
# =====================================================
elif page == "📑 Accountant Report":
    if not can_view_accountant_report():
        st.warning("This report is only available to accountants and directors.")
        st.stop()

    st.markdown(f"## 📑 Accountant Report — {selected_month}")
    st.caption("Cross-branch GP summary for the selected month. Use the sidebar to change the month.")

    # Cache key by month so re-clicks don't re-fetch
    cache_key = f"accountant_report::{selected_month}"

    if st.button("🔄 Generate Report", type="primary"):
        try:
            budget_df = get_budget_data()
            actuals_df = get_actuals_data()
            report = build_month_report(
                month=selected_month,
                cos_other_pct=get_cos_other_pct(),
                budget_df=budget_df,
                actuals_df=actuals_df,
            )
            st.session_state[cache_key] = report
        except Exception as e:
            st.error(f"Failed to generate report: {e}")
            st.stop()

    report = st.session_state.get(cache_key)
    if report is None:
        st.info("Click **Generate Report** to load data for this month.")
    else:
        # Coverage caption
        st.caption(
            f"{report['branches_with_budget']} of {len(BRANCHES)} branches have budgets set · "
            f"{report['branches_with_actuals']} of {len(BRANCHES)} branches have actuals captured · "
            f"Generated {report['generated_at']}"
        )

        # On-screen table
        df = pd.DataFrame(report["summary_rows"])
        # Reorder columns to match the Excel summary order
        column_order = [
            "branch",
            "sales_target", "sales_actual", "sales_var",
            "parts_costs_target", "parts_costs_actual", "parts_costs_var",
            "cos_other_target", "cos_other_actual", "cos_other_var",
            "rsb_paint_target", "rsb_paint_actual", "rsb_paint_var",
            "consumables_target", "consumables_actual", "consumables_var",
            "gp_target", "gp_actual", "gp_var",
            "gp_pct_target", "gp_pct_actual",
            "diagnostics_target", "diagnostics_actual",
            "additionals_target", "additionals_actual",
            "csi_target", "csi_actual",
        ]
        df = df[column_order]
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Excel download
        try:
            xlsx_bytes = build_excel_workbook(report)
            from datetime import date
            filename = f"GP_Report_{selected_month}_{date.today().isoformat()}.xlsx"
            st.download_button(
                "⬇️ Download Excel",
                data=xlsx_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption("Workbook contains a Summary sheet and one detail sheet per branch.")
        except Exception as e:
            st.error(f"Failed to build Excel workbook: {e}")

```

The block uses `pd` (pandas) which is already imported in `app.py` at the top. The block uses `BRANCHES` which is already imported from `config`. Both `selected_month` and `get_cos_other_pct` are available in the surrounding scope.

- [ ] **Step 4: Verify imports load and the app starts**

Run:

```bash
python -c "import app" 2>&1 | grep -E "(Error|Traceback)" | head
```

Expected: empty output (no errors). Streamlit runtime warnings are OK and won't appear in this filtered grep.

- [ ] **Step 5: Visual smoke test — page appears for the right roles**

Run the app:

```bash
streamlit run app.py
```

Sign in with each role and verify:

| Role | Expect "📑 Accountant Report" in sidebar? |
|---|---|
| manager | NO |
| accountant | YES |
| director | YES |
| admin | YES |

If you don't have a user for each role, check the Users tab in the Google Sheet, or temporarily change a user's role to test.

- [ ] **Step 6: Visual smoke test — the page works**

Signed in as accountant or director:
1. Open "📑 Accountant Report".
2. Pick a month from the sidebar where you know there is data.
3. Click "🔄 Generate Report".
4. Confirm the on-screen table renders with one row per branch + a TOTAL row.
5. Confirm the coverage caption shows correct counts.
6. Click "⬇️ Download Excel".
7. Open the downloaded file. Verify Summary tab + 5 branch tabs all render correctly.

Stop the server.

- [ ] **Step 7: Defence-in-depth check**

Manually navigate the app as a manager. The page should NOT appear in the sidebar. (We can't easily simulate "deep linking to a hidden page" in Streamlit, but the page-block guard `if not can_view_accountant_report(): st.stop()` is the second line of defence if Streamlit's API ever exposes such routing.)

- [ ] **Step 8: Commit**

```bash
git add app.py
git commit -m "Add Accountant Report page

New '📑 Accountant Report' sidebar entry visible to accountant, director,
and admin (managers cannot see or open it). The page shows a cross-branch
GP summary for the sidebar-selected month and offers a multi-sheet Excel
download. Page is built lazily — Generate Report fetches data and caches
the result in session_state keyed by month."
```

---

## Task 8: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document the new module and page**

Open `CLAUDE.md`. Find the **Architecture** section. Add a new bullet for `reports.py`. The current list ends with `setup_sheets.py`. Insert this bullet alphabetically (between `calculations.py` and `setup_sheets.py`):

```
- **reports.py** — Pure logic for the Accountant Report. `build_month_report` aggregates budget + actuals across all branches for one month; `build_excel_workbook` serializes that report to an xlsx file using openpyxl. No Streamlit imports — accepts dependencies as arguments.
```

In the **Project Overview** section, the line "All 4 pages (Dashboard, Manager Input, Quarterly Summary, Budget Setup) in one file" is now stale. Update the **Architecture** entry for `app.py` from:

```
- **app.py** — Main Streamlit app. All 4 pages (Dashboard, Manager Input, Quarterly Summary, Budget Setup) in one file with sidebar navigation. Renders GP tables as raw HTML for styling control.
```

to:

```
- **app.py** — Main Streamlit app. Pages (Dashboard, Manager Input, Quarterly Summary, Budget Setup, Accountant Report, Settings) live in one file with sidebar navigation. The Accountant Report sidebar entry is hidden for users without the right role. Renders GP tables as raw HTML for styling control.
```

In the **Auth & Access Control** section, after the existing bullets, add:

```
- The Accountant Report page is gated by `can_view_accountant_report()` — visible to accountant, director, admin
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document accountant report module and page in CLAUDE.md"
```

---

## Task 9: Final end-to-end verification

This is the spec's eight-point verification list, run as a single checkpoint.

- [ ] **Step 1: Run the app**

```bash
streamlit run app.py
```

- [ ] **Step 2: Verify role visibility**

For each role available in your Users sheet:

| Role | "📑 Accountant Report" in sidebar? |
|---|---|
| manager | NO |
| accountant | YES |
| director | YES |
| admin | YES |

- [ ] **Step 3: Verify the page works for accountant, director, admin**

Log in as each privileged role, open the page, click Generate Report. Verify the on-screen table renders.

- [ ] **Step 4: Verify the download works**

Signed in as accountant: click "⬇️ Download Excel". Open the resulting file. Confirm:
- Filename matches `GP_Report_<Month>_YYYY-MM-DD.xlsx`.
- 6 sheets: Summary + 5 branches.
- Summary numbers match the on-screen table.
- Each branch sheet matches what you see if you open the Dashboard for that branch + month.

- [ ] **Step 5: Verify "no budget" handling**

Pick a month where no branch has a budget yet (or temporarily clear the Budget tab in the spreadsheet for that month). Click Generate Report. Confirm:
- Table renders with all-zero target columns.
- Coverage caption says "0 of 5 branches have budgets set".
- Download still produces a valid file (open it; cells just contain zeros).

- [ ] **Step 6: Verify "partial actuals" handling**

Pick a month with actuals from only some branches. Confirm:
- Branches without actuals show Actual = 0, Variance = -Target.
- Coverage caption shows the correct partial count.

- [ ] **Step 7: Verify the workbook is editable**

Open the downloaded file in Excel/Numbers/LibreOffice. Edit a cell. Add a new column with a SUM formula. Save. Re-open. The file behaves like a normal `.xlsx` (no protected cells, no embedded formulas to break).

- [ ] **Step 8: Verify other pages still work**

Click through Dashboard, Manager Input, Quarterly Summary, Budget Setup, Settings. Confirm none have regressed (because Task 3 changed call sites of `targets_from_budget` / `actuals_from_row`, this is the catch-net for any missed call site).

- [ ] **Step 9: If all pass — final tag commit**

```bash
git log --oneline -10
```

Expected: a clean chain of ~7 commits from Tasks 1-8. No squashing required — the per-task commits are the audit trail.

---

## Self-review

Spec coverage check:

| Spec section | Implementing task |
|---|---|
| File layout (reports.py, auth.py, requirements.txt) | Tasks 1, 2, 4–6 |
| Public interface of reports.py | Tasks 4–6 |
| UI / sidebar nav / page block | Task 7 |
| Page-level access guard | Task 7 step 3 |
| Excel Summary sheet | Task 5 |
| Excel per-branch sheets | Task 6 |
| Filename format | Task 7 step 3 |
| `can_view_accountant_report` helper | Task 2 |
| Two enforcement points | Task 7 (sidebar) + Task 7 (page guard) |
| Error handling (no budget, no actuals, sheets fail, openpyxl missing) | Task 7 try/except + Task 4 zero-fill |
| Manual testing (8 steps) | Task 9 |
| Helper lift to `calculations.py` with explicit `cos_other_pct` arg | Task 3 |
| `CLAUDE.md` update | Task 8 |

No gaps. No `TBD`/`TODO` markers. Type and function-name consistency: `build_month_report` and `build_excel_workbook` defined in Task 4–6, used identically in Task 7 imports. `can_view_accountant_report` defined in Task 2, used in Task 7. `targets_from_budget` / `actuals_from_row` signature change in Task 3 propagates consistently to call-site updates in the same task.
