"""GP calculation engine — all business logic lives here.

Formulas sourced from CKmain GP dashboard V1.xlsx (March sheet).
"""

from config import RSB_PAINT_PCT, CONSUMABLES_PCT, COST_OF_SALES_OTHER_PCT


def calculate_gp_actuals(
    sales: float,
    parts_contribution: float,
    parts_gp_pct: float,
    paints: float,
    consumables_paintshop: float,
    consumables: float,
    cos_other_pct: float = COST_OF_SALES_OTHER_PCT,
) -> dict:
    """Calculate GP from actual manager inputs.

    Parts Costs         = parts_contribution × (1 - parts_gp%)
    Cost of Sales Other = sales × cos_other_pct
    RSB Paint           = paints (direct input)
    Consumables         = consumables_paintshop + consumables (direct input)
    GP                  = sales - parts_costs - cos_other - rsb_paint - consumables
    """
    VAT = 1.15
    parts_costs = parts_contribution * (1 - parts_gp_pct)
    cos_other = sales * cos_other_pct
    rsb_paint = paints / VAT
    consumables_combined = (consumables_paintshop + consumables) / VAT
    paint_labour_other = sales - parts_contribution

    gross_profit = sales - parts_costs - cos_other - rsb_paint - consumables_combined
    gp_pct = (gross_profit / sales * 100) if sales > 0 else 0.0

    return {
        "sales": sales,
        "parts_contribution": parts_contribution,
        "paint_labour_other": paint_labour_other,
        "parts_costs": parts_costs,
        "cos_other": cos_other,
        "rsb_paint": rsb_paint,
        "consumables_combined": consumables_combined,
        "gross_profit": gross_profit,
        "gp_pct": gp_pct,
    }


def calculate_targets(
    sales_target: float,
    paint_labour_pct: float,
    parts_sales_pct: float,
    parts_markup: float,
    cos_other_pct: float = COST_OF_SALES_OTHER_PCT,
    rsb_paint_pct: float = RSB_PAINT_PCT,
    consumables_pct: float = CONSUMABLES_PCT,
) -> dict:
    """Calculate target figures from budget parameters.

    paint_labour_pct and parts_sales_pct are decimals (e.g. 0.49, 0.51).
    parts_markup is a percentage number (e.g. 25 for 25%).
    cos_other_pct, rsb_paint_pct, consumables_pct are decimals (e.g. 0.07 for 7%).
    """
    paint_labour_target = sales_target * paint_labour_pct
    parts_sales_target = sales_target * parts_sales_pct

    # Parts Costs = Parts Sales Target / (1 + markup/100)
    if parts_markup > 0:
        parts_costs = parts_sales_target / (1 + parts_markup / 100)
    else:
        parts_costs = parts_sales_target

    cos_other = sales_target * cos_other_pct
    rsb_paint = sales_target * rsb_paint_pct
    consumables = sales_target * consumables_pct

    gross_profit = sales_target - parts_costs - cos_other - rsb_paint - consumables
    gp_pct = (gross_profit / sales_target * 100) if sales_target > 0 else 0.0

    return {
        "sales_target": sales_target,
        "paint_labour_target": paint_labour_target,
        "parts_sales_target": parts_sales_target,
        "parts_markup": parts_markup,
        "parts_costs": parts_costs,
        "cos_other": cos_other,
        "rsb_paint": rsb_paint,
        "consumables": consumables,
        "gross_profit": gross_profit,
        "gp_pct": gp_pct,
    }


def calculate_variance(actual: float, target: float) -> float:
    """Return actual - target. Negative means under target."""
    return actual - target


def calculate_quarterly_summary(monthly_data) -> dict:
    """Aggregate monthly actuals GP data into a quarterly summary."""
    if not monthly_data:
        return calculate_gp_actuals(0, 0, 0, 0, 0, 0)

    total_sales = sum(m.get("sales", 0) for m in monthly_data)
    total_parts_costs = sum(m.get("parts_costs", 0) for m in monthly_data)
    total_cos_other = sum(m.get("cos_other", 0) for m in monthly_data)
    total_rsb = sum(m.get("rsb_paint", 0) for m in monthly_data)
    total_cons = sum(m.get("consumables_combined", 0) for m in monthly_data)

    gross_profit = total_sales - total_parts_costs - total_cos_other - total_rsb - total_cons
    gp_pct = (gross_profit / total_sales * 100) if total_sales > 0 else 0.0

    return {
        "sales": total_sales,
        "parts_costs": total_parts_costs,
        "cos_other": total_cos_other,
        "rsb_paint": total_rsb,
        "consumables_combined": total_cons,
        "gross_profit": gross_profit,
        "gp_pct": gp_pct,
    }
