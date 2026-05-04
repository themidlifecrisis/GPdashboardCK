# Accountant Report & Excel Export — Design

**Date:** 2026-05-04
**Status:** Approved (pending user spec review)

## Summary

Add a new sidebar page **📑 Accountant Report** to the GP Dashboard. The page shows a cross-branch GP summary for the selected month and offers a one-click Excel download. Visible only to roles `accountant`, `director`, and `admin`. Managers cannot see or reach it.

## Goals

- Give the accountant a single screen that shows GP performance across all branches for a chosen month.
- Produce an Excel workbook the accountant can manipulate offline (sort, pivot, add formulas).
- Keep role gating consistent with the existing auth helpers.
- Don't disturb the existing Dashboard, Manager Input, Quarterly Summary, Budget Setup, or Settings pages.

## Non-Goals

- No YTD or quarterly export in this iteration (the page can grow into that later).
- No CSV export — Excel only, since the accountant explicitly wants Excel.
- No formulas inside the workbook. Static values only.
- No charts inside the Excel file. The on-screen plotly charts on the Dashboard are unaffected; this report focuses on tabular data.
- No new auth role. The existing `accountant` role is reused.

## Architecture

### File layout

| File | Change | Purpose |
|---|---|---|
| `reports.py` | **new** | Pure logic: build the report data structure and serialize to xlsx bytes. No Streamlit imports. |
| `app.py` | modified | Add the new page block. Conditionally include it in the sidebar nav. |
| `auth.py` | modified | Add `can_view_accountant_report()` helper. |
| `requirements.txt` | modified | Add `openpyxl>=3.1.0`. |

Splitting `reports.py` out follows the existing project pattern (`calculations.py` is also pure logic, no Streamlit). Keeps `app.py` from growing further and makes report logic testable in isolation.

### Public interface of `reports.py`

```python
def build_month_report(month: str) -> dict:
    """Pull all branches' budget + actuals for a month, run them through
    calculate_targets and calculate_gp_actuals, return a structured dict.

    Returns:
        {
            "month": "<month>",
            "generated_at": "<ISO timestamp>",
            "summary_rows": [  # one per branch + a TOTAL row
                {"branch": "...", "sales_target": ..., "sales_actual": ...,
                 "sales_var": ..., "parts_costs_target": ..., ...},
                ...
                {"branch": "TOTAL", ...},
            ],
            "branch_details": {
                "<branch>": {
                    "targets": <calculate_targets output>,
                    "actuals": <calculate_gp_actuals output>,  # zeros if no data
                    "extras": {"diagnostics": ..., "additionals": ..., "csi": ...,
                               "diagnostics_target": ..., "additionals_target": ...,
                               "csi_target": ...},
                    "has_actuals": bool,
                },
                ...
            },
        }
    """

def build_excel_workbook(report: dict) -> bytes:
    """Serialize a report dict to an xlsx file. Returns raw bytes
    suitable for st.download_button."""
```

`build_month_report` reuses the existing helpers `targets_from_budget` and `actuals_from_row` currently defined inside `app.py`. They will be lifted into `calculations.py` — they're already pure functions on top of pure logic. To preserve `calculations.py`'s purity (no Streamlit, no Sheets I/O), they will accept `cos_other_pct` as an explicit argument rather than calling `get_cos_other_pct()` themselves. `get_cos_other_pct` stays in `app.py` (Streamlit-aware), and `build_month_report` accepts `cos_other_pct: float` as a parameter that the page computes and passes in.

Updated signatures:

```python
# in calculations.py (lifted from app.py, made arg-explicit)
def targets_from_budget(budget: dict, cos_other_default: float) -> dict: ...
def actuals_from_row(act: dict, cos_other_pct: float) -> dict: ...

# in reports.py
def build_month_report(month: str, cos_other_pct: float) -> dict: ...
def build_excel_workbook(report: dict) -> bytes: ...
```

This means `app.py`'s existing call sites for `targets_from_budget` and `actuals_from_row` need to be updated to pass `get_cos_other_pct()` as an argument.

## UI

### Sidebar nav

The nav list is built dynamically based on role:

```python
nav_options = ["📊 Dashboard", "📝 Manager Input", "📈 Quarterly Summary"]
if can_edit_budgets():
    nav_options.append("🎯 Budget Setup")
if can_view_accountant_report():
    nav_options.append("📑 Accountant Report")
if can_edit_budgets():
    nav_options.append("⚙️ Settings")
```

Managers see exactly what they see today. Accountants/directors/admins see the new entry between Budget Setup and Settings.

### Page contents

```
## 📑 Accountant Report — <Selected Month>

[ Generate Report ]

(After click — cached in session_state until month changes:)

### Cross-Branch Summary — <Month>
<st.dataframe with sortable columns; one row per branch + TOTAL row>

[ ⬇️ Download Excel ]
Workbook contains a Summary sheet and one detail sheet per branch.
```

Behaviour rules:
- Month is taken from the existing sidebar month selector. No separate selector on this page.
- A "Generate Report" click reads all branches' data; result is stored in `st.session_state["accountant_report"]` keyed by month so re-clicks don't re-hit Sheets needlessly.
- Branches with no actuals appear with Actual = 0 and Variance = -Target, so missing data is visible rather than silently dropped.
- The on-screen table uses `st.dataframe` (sortable, copyable) — not the Dashboard's inline-styled HTML, since this is for analysis, not presentation.

### Page-level access guard (defence-in-depth)

```python
elif page == "📑 Accountant Report":
    if not can_view_accountant_report():
        st.warning("This report is only available to accountants and directors.")
        st.stop()
    ...
```

Hiding the nav option isn't enough — the page block must also re-check the role. This protects against a hypothetical future where the page string is reachable via URL params or session manipulation.

## Excel workbook structure

Filename: `GP_Report_<Month>_<YYYY-MM-DD>.xlsx`.

### Sheet 1: `Summary`

One row per branch + a `TOTAL` row at the bottom. Columns:

| Branch | Sales Target | Sales Actual | Sales Var | Parts Costs Target | Parts Costs Actual | Parts Costs Var | COS Other Target | COS Other Actual | COS Other Var | RSB Paint Target | RSB Paint Actual | RSB Paint Var | Consumables Target | Consumables Actual | Consumables Var | GP Target | GP Actual | GP Var | GP% Target | GP% Actual | Diagnostics Target | Diagnostics Actual | Additionals Target | Additionals Actual | CSI Target | CSI Actual |

Formatting:
- Currency cells: `#,##0`. No `R` prefix in cells (the column header carries the unit; keeps Excel sums working).
- Percentage cells (`GP%`, `CSI`): `0.0%`, stored as decimals.
- Variance cells: same currency format, plus conditional formatting — green positive, red negative. Inverted on cost rows (Parts Costs, COS Other, RSB Paint, Consumables) so under-budget shows green.
- Header row: bold, white text, fill `#1E88E5` (matches dashboard blue).
- Frozen top row + frozen first column.
- TOTAL row: sums for currency columns; weighted `GP% = ΣGP / ΣSales`; weighted `CSI = ΣCSI×Sales / ΣSales`.

### Sheets 2–N: One per branch

Sheet name = exact branch string from `config.BRANCHES`. (All five current branch names fit Excel's 31-char limit and contain no forbidden characters.)

Layout mirrors the Dashboard's GP table — line items as rows, columns Target / Actual / Variance / Act% / Target%:

```
Row 1: Branch — Month — Generated YYYY-MM-DD HH:MM   (italic caption)
Row 2: blank
Row 3: section header "Targets" (bold, blue fill)
Row 4: Sales Target            <Target>
Row 5: Paint Labour Other      <Target>
Row 6: Parts Sales Target      <Target>
Row 7: Parts Markup            <%>
Row 8: blank
Row 9: section header "GP Calculations" (bold, blue fill)
Row 10: header — Item | Target | Actual | Variance | Act % | Target %
Row 11: Sales                  T  A  V    Act%
Row 12: Parts Costs            T  A  V    Act%   T%
Row 13: Cost of Sales Other    T  A  V    Act%   T%
Row 14: RSB Paint              T  A  V    Act%   T%
Row 15: Consumables Combined   T  A  V    Act%   T%
Row 16: blank with top border
Row 17: Gross Profit (bold)    T  A  V
Row 18: GP %             (bold) T  A  V
Row 19: blank
Row 20: section header "Additional KPIs" (bold, blue fill)
Row 21: Diagnostics            T  A  V
Row 22: Additionals            T  A  V
Row 23: CSI                    T  A
```

Same number formatting and conditional-formatting rules as Summary. Frozen top 2 rows so the caption and section headers stay in view.

## Data flow

```
User picks month in sidebar → clicks "Generate Report" on Accountant Report page
  ↓
build_month_report(month) reads:
  - get_budget_data()   (cached, 120s TTL)
  - get_actuals_data()  (cached, 60s TTL)
  - get_cos_other_pct() (cached settings)
  ↓
For each branch in config.BRANCHES:
  - targets   = calculate_targets(...)  if budget exists, else all-zero target dict
  - actuals   = calculate_gp_actuals(...) if actuals row exists, else all-zero actuals dict
  - extras    = diagnostics/additionals/csi (actual + target, zero if missing)
  ↓
Build summary_rows (per-branch + TOTAL) and branch_details
  ↓
Cache result in st.session_state["accountant_report"][month]
  ↓
Render st.dataframe; show "Download Excel" button
  ↓
On download click: build_excel_workbook(report) → bytes
  ↓
st.download_button serves the file
```

No new Sheets reads beyond what's already cached. The full report is 5 branches × (1 budget row + 1 actuals row) = 10 lookups, all in-memory after the cached `get_budget_data()` / `get_actuals_data()` calls.

## Access control

### `auth.py` addition

```python
def can_view_accountant_report() -> bool:
    """Accountant-facing month report. Visible to accountant, director, admin."""
    return st.session_state.get("user_role") in (ROLE_ACCOUNTANT, ROLE_DIRECTOR, ROLE_ADMIN)
```

Same role set as `is_director()` today, but a separately named helper so future role changes are a one-line edit. No change to `is_director`, `can_edit_budgets`, or `can_edit_actuals` — the existing helpers stay as they are.

### Two enforcement points

1. **Sidebar nav** — the page entry is only added to the radio list when `can_view_accountant_report()` is True.
2. **Page block** — the page implementation also re-checks the role and `st.stop()`s if not allowed. Defence-in-depth.

## Error handling

- **No budget for a branch in the selected month**: row appears with Target = 0, Variance = Actual; flagged to the user with a small note in the on-screen table caption ("3 of 5 branches have budgets set for May").
- **No actuals for a branch**: row appears with Actual = 0, Variance = -Target. Same caption shows a count ("2 of 5 branches have actuals captured for May").
- **Sheets read fails**: caught at the page level and rendered with `st.error(...)`. The page never crashes the app.
- **Excel build fails**: caught around `build_excel_workbook` and surfaced via `st.error(...)` on the page. The on-screen table still renders.
- **`openpyxl` not installed** (e.g. on a stale Streamlit Cloud deploy): caught at import time at the top of `reports.py`, surfaced as a deployment-time error rather than a per-request crash.

## Testing

Manual verification before merge:

1. Sign in as **manager** → confirm "📑 Accountant Report" does **not** appear in the sidebar.
2. Sign in as **accountant** → page appears; "Generate Report" populates the table; "Download Excel" produces a file that opens cleanly in Excel/Numbers/LibreOffice.
3. Sign in as **director** → same as accountant.
4. Sign in as **admin** → same.
5. Pick a month with no budget rows → table renders with all-zero targets and a caption note, download still works.
6. Pick a month with partial actuals → missing branches show Actual = 0, Variance = -Target.
7. Open the downloaded workbook → verify Summary sheet sums match the on-screen table; verify each branch sheet matches the corresponding Dashboard view; verify conditional-formatting colours.
8. Edit a value in the downloaded workbook → confirm the file behaves as a normal `.xlsx` (no protected cells, no embedded formulas to break).

The pure functions in `reports.py` (`build_month_report`, `build_excel_workbook`) are amenable to unit tests later, but no test suite exists in the repo today and adding one is out of scope for this change.

## Open questions

None. Everything above is approved.

## Implementation sketch (rough order)

1. Add `openpyxl` to `requirements.txt`.
2. Add `can_view_accountant_report()` to `auth.py`.
3. Lift `targets_from_budget` and `actuals_from_row` from `app.py` into `calculations.py`, making `cos_other_pct` (or `cos_other_default`) an explicit parameter. Update `app.py`'s existing call sites to pass `get_cos_other_pct()` in. `get_cos_other_pct` stays in `app.py`.
4. Create `reports.py` with `build_month_report` and `build_excel_workbook`.
5. Add the new page block + conditional sidebar entry in `app.py`.
6. Manual test the eight verification steps above.
7. Update `CLAUDE.md` to mention the new page and `reports.py` module.
