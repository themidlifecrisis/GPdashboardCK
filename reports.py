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
