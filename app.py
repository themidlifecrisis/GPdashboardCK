"""GP Dashboard — Gross Profit Calculations & Analysis."""

from datetime import date

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

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
from calculations import (
    actuals_from_row,
    calculate_gp_actuals,
    calculate_quarterly_summary,
    calculate_targets,
    calculate_variance,
    targets_from_budget,
)
from config import BRANCHES, MONTHS, QUARTERS, RSB_PAINT_PCT, CONSUMABLES_PCT
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
from reports import SUMMARY_COLUMN_KEYS, build_excel_workbook, build_month_report
from utils import fmt_currency, fmt_pct, fmt_variance, variance_color

# --- Page config ---
st.set_page_config(
    page_title="GP Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #FFFFFF 0%, #F5F7FA 100%);
        border: 1px solid #E0E4EA;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    div[data-testid="stMetric"] label {
        color: #1E88E5 !important;
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        color: #1A1A2E !important;
    }

    /* Tables */
    .stDataFrame {
        border-radius: 8px;
        overflow: hidden;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #F5F7FA;
        border-right: 1px solid #E0E4EA;
    }

    /* Headers */
    h1, h2, h3 {
        font-weight: 700 !important;
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 20px;
        font-weight: 600;
    }

    /* Unused — table uses inline styles via components.html */
</style>
""", unsafe_allow_html=True)


# =====================================================
# LOGIN
# =====================================================
try:
    users = get_users()
except Exception as e:
    users = None
    _conn_error = str(e)

if users is None:
    st.error("Could not connect to Google Sheets. Check your credentials in `.streamlit/secrets.toml`.")
    st.info("Run `python setup_sheets.py` to initialize the spreadsheet first.")
    st.code(_conn_error)
    st.stop()

if not login_form(users):
    st.stop()


# =====================================================
# SIDEBAR
# =====================================================
with st.sidebar:
    st.image("assets/logo.png", width=100)
    st.markdown(f"### 👤 {st.session_state.get('user_name', 'User')}")
    role_map = {
        "director": "🔑 Director",
        "admin": "🛡️ Admin",
        "accountant": "📑 Accountant",
        "manager": "📋 Manager",
    }
    role_badge = role_map.get(st.session_state.get("user_role", ""), "📋 User")
    st.caption(f"{role_badge} · {get_user_branch()}")
    st.divider()

    # Navigation
    nav_options = ["📊 Dashboard", "📝 Manager Input", "📈 Quarterly Summary", "🎯 Budget Setup"]
    if can_view_accountant_report():
        nav_options.append("📑 Accountant Report")
    nav_options.append("⚙️ Settings")
    page = st.radio(
        "Navigation",
        nav_options,
        label_visibility="collapsed",
    )

    st.divider()

    # Branch selector
    allowed = get_allowed_branches(BRANCHES)
    if len(allowed) > 1:
        selected_branch = st.selectbox("Branch", allowed)
    else:
        selected_branch = allowed[0]
        st.markdown(f"**Branch:** {selected_branch}")

    # Month selector
    selected_month = st.selectbox("Month", MONTHS, index=0)

    st.divider()
    if st.button("🚪 Sign Out", use_container_width=True):
        logout()


# =====================================================
# HELPERS
# =====================================================

def get_cos_other_pct():
    """Load Cost of Sales Other % from settings, default to config value."""
    from config import COST_OF_SALES_OTHER_PCT
    val = get_setting("cos_other_pct", None)
    if val is not None:
        try:
            return float(val) / 100  # stored as whole number (e.g. 7), return as decimal
        except (ValueError, TypeError):
            pass
    return COST_OF_SALES_OTHER_PCT


def build_gp_table_html(targets, actuals_gp, extras) -> str:
    """Build the styled GP calculation table as HTML."""
    def val(d, key, default=0):
        return d.get(key, default) if d else default

    t_sales = val(targets, "sales_target")
    t_pl = val(targets, "paint_labour_target")
    t_ps = val(targets, "parts_sales_target")
    t_markup = val(targets, "parts_markup")
    t_parts_costs = val(targets, "parts_costs")
    t_cos_other = val(targets, "cos_other")
    t_rsb = val(targets, "rsb_paint")
    t_cons = val(targets, "consumables")
    t_gp = val(targets, "gross_profit")
    t_gp_pct = val(targets, "gp_pct")

    a_sales = val(actuals_gp, "sales")
    a_parts_contribution = val(actuals_gp, "parts_contribution")
    a_paint_labour = val(actuals_gp, "paint_labour_other")
    a_parts = val(actuals_gp, "parts_costs")
    a_cos_other = val(actuals_gp, "cos_other")
    a_rsb = val(actuals_gp, "rsb_paint")
    a_cons = val(actuals_gp, "consumables_combined")
    a_gp = val(actuals_gp, "gross_profit")
    a_gp_pct = val(actuals_gp, "gp_pct")

    diag = val(extras, "diagnostics")
    addit = val(extras, "additionals")
    csi_val = val(extras, "csi")
    t_diag = val(extras, "diagnostics_target")
    t_addit = val(extras, "additionals_target")
    t_csi = val(extras, "csi_target")

    def var_style(diff, invert=False):
        if diff == 0:
            return "color:#999;"
        if invert:
            return "color:#43A047;" if diff < 0 else "color:#E53935;"
        return "color:#E53935;" if diff < 0 else "color:#43A047;"

    def var_fmt(actual, target, is_pct=False):
        diff = actual - target
        style = var_style(diff)
        if is_pct:
            return f'<span style="{style}">{fmt_pct(diff)}</span>'
        return f'<span style="{style}">{fmt_variance(diff)}</span>'

    # For costs, under target is GOOD (green)
    def var_cost(actual, target):
        diff = actual - target
        style = var_style(diff, invert=True)
        return f'<span style="{style}">{fmt_variance(diff)}</span>'

    paint_labour_pct = int(val(targets, "paint_labour_target", 0) / t_sales * 100) if t_sales > 0 else 49
    parts_sales_pct = 100 - paint_labour_pct

    # Inline styles for Streamlit HTML rendering (light mode)
    S_TABLE = "width:100%;border-collapse:collapse;font-size:0.95rem;"
    S_TH = "background:#F5F7FA;color:#1E88E5;padding:10px 15px;text-align:right;border-bottom:2px solid #E0E4EA;font-weight:600;text-transform:uppercase;font-size:0.8rem;letter-spacing:0.5px;"
    S_TH_L = S_TH + "text-align:left;"
    S_TD = "padding:8px 15px;text-align:right;border-bottom:1px solid #E8ECF0;"
    S_TD_L = S_TD + "text-align:left;font-weight:600;color:#444;"
    S_SEC = "font-weight:700;color:#1E88E5;padding:18px 15px 8px;border-bottom:2px solid #1E88E5;font-size:0.9rem;"
    S_TOT = S_TD + "font-weight:700;font-size:1.05rem;border-top:2px solid #1E88E5;padding-top:12px;color:#1A1A2E;"
    S_TOT_L = S_TOT + "text-align:left;"
    S_NEG = "color:#E53935;"
    S_POS = "color:#43A047;"
    S_NEU = "color:#999;"

    def sc(cls):
        return {True: S_NEG, False: S_NEU}.get(cls == "negative", S_POS if cls == "positive" else S_NEU)

    # Actual percentages of sales
    a_cos_other_pct = (a_cos_other / a_sales * 100) if a_sales > 0 else 0
    a_rsb_pct = (a_rsb / a_sales * 100) if a_sales > 0 else 0
    a_cons_pct = (a_cons / a_sales * 100) if a_sales > 0 else 0
    a_parts_costs_pct = (a_parts / a_sales * 100) if a_sales > 0 else 0

    # Target percentages
    t_cos_pct = fmt_pct(t_cos_other / t_sales * 100) if t_sales > 0 else '7.0%'
    t_rsb_pct_label = fmt_pct(t_rsb / t_sales * 100) if t_sales > 0 else '4.0%'
    t_cons_pct_label = fmt_pct(t_cons / t_sales * 100) if t_sales > 0 else '3.0%'

    NC = 6  # number of columns

    html = f"""
    <table style="{S_TABLE}">
        <tr>
            <th style="{S_TH_L}width:30%;"></th>
            <th style="{S_TH}width:9%;">Contrib %</th>
            <th style="{S_TH}width:16%;">Target</th>
            <th style="{S_TH}width:16%;">Actual</th>
            <th style="{S_TH}width:9%;">Act %</th>
            <th style="{S_TH}width:16%;">Variance</th>
        </tr>

        <tr><td colspan="{NC}" style="{S_SEC}">Targets</td></tr>
        <tr>
            <td style="{S_TD_L}">Sales Target</td>
            <td style="{S_TD}">100</td>
            <td style="{S_TD}">{fmt_currency(t_sales)}</td>
            <td style="{S_TD}">{fmt_currency(a_sales) if a_sales else '-'}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{var_fmt(a_sales, t_sales)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Paint Labour Other Target</td>
            <td style="{S_TD}">{paint_labour_pct}</td>
            <td style="{S_TD}">{fmt_currency(t_pl)}</td>
            <td style="{S_TD}">{fmt_currency(a_paint_labour) if a_paint_labour else '-'}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{var_fmt(a_paint_labour, t_pl)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Parts Sales Target</td>
            <td style="{S_TD}">{parts_sales_pct}</td>
            <td style="{S_TD}">{fmt_currency(t_ps)}</td>
            <td style="{S_TD}">{fmt_currency(a_parts_contribution) if a_parts_contribution else '-'}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{var_fmt(a_parts_contribution, t_ps)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Parts Markup</td>
            <td style="{S_TD}">{t_markup}%</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{fmt_pct((a_parts_contribution / a_parts - 1) * 100) if a_parts > 0 else '0%'}</td>
            <td style="{S_TD}"></td>
        </tr>

        <tr><td colspan="{NC}" style="{S_SEC}">GP Calculations</td></tr>
        <tr>
            <td style="{S_TD_L}">Sales</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{fmt_currency(t_sales)}</td>
            <td style="{S_TD}">{fmt_currency(a_sales) if a_sales else '-'}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{var_fmt(a_sales, t_sales)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Parts Costs</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{fmt_currency(t_parts_costs)}</td>
            <td style="{S_TD}">{fmt_currency(a_parts) if a_parts else '-'}</td>
            <td style="{S_TD}">{fmt_pct(a_parts_costs_pct) if a_sales > 0 else ''}</td>
            <td style="{S_TD}">{var_cost(a_parts, t_parts_costs)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Cost of Sales Other</td>
            <td style="{S_TD}">{t_cos_pct}</td>
            <td style="{S_TD}">{fmt_currency(t_cos_other)}</td>
            <td style="{S_TD}">{fmt_currency(a_cos_other) if a_cos_other else '-'}</td>
            <td style="{S_TD}">{fmt_pct(a_cos_other_pct) if a_sales > 0 else ''}</td>
            <td style="{S_TD}">{var_cost(a_cos_other, t_cos_other)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">RSB Paint</td>
            <td style="{S_TD}">{t_rsb_pct_label}</td>
            <td style="{S_TD}">{fmt_currency(t_rsb)}</td>
            <td style="{S_TD}">{fmt_currency(a_rsb) if a_rsb else '-'}</td>
            <td style="{S_TD}">{fmt_pct(a_rsb_pct) if a_sales > 0 else ''}</td>
            <td style="{S_TD}">{var_cost(a_rsb, t_rsb)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Consumables Combined</td>
            <td style="{S_TD}">{t_cons_pct_label}</td>
            <td style="{S_TD}">{fmt_currency(t_cons)}</td>
            <td style="{S_TD}">{fmt_currency(a_cons) if a_cons else '-'}</td>
            <td style="{S_TD}">{fmt_pct(a_cons_pct) if a_sales > 0 else ''}</td>
            <td style="{S_TD}">{var_cost(a_cons, t_cons)}</td>
        </tr>

        <tr>
            <td style="{S_TOT_L}">Gross Profit</td>
            <td style="{S_TOT}"></td>
            <td style="{S_TOT}">{fmt_currency(t_gp)}</td>
            <td style="{S_TOT}">{fmt_currency(a_gp) if a_gp else '-'}</td>
            <td style="{S_TOT}"></td>
            <td style="{S_TOT}">{var_fmt(a_gp, t_gp)}</td>
        </tr>
        <tr>
            <td style="{S_TOT_L}">GP %</td>
            <td style="{S_TOT}"></td>
            <td style="{S_TOT}">{fmt_pct(t_gp_pct)}</td>
            <td style="{S_TOT}">{fmt_pct(a_gp_pct) if a_gp_pct else '-'}</td>
            <td style="{S_TOT}"></td>
            <td style="{S_TOT}">{var_fmt(a_gp_pct, t_gp_pct, is_pct=True)}</td>
        </tr>

        <tr><td colspan="{NC}" style="{S_SEC}">Additional KPIs</td></tr>
        <tr>
            <td style="{S_TD_L}">Diagnostics</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{fmt_currency(t_diag)}</td>
            <td style="{S_TD}">{fmt_currency(diag)}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{var_fmt(diag, t_diag)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">Additionals</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{fmt_currency(t_addit)}</td>
            <td style="{S_TD}">{fmt_currency(addit)}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{var_fmt(addit, t_addit)}</td>
        </tr>
        <tr>
            <td style="{S_TD_L}">CSI</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}">{fmt_pct(t_csi)}</td>
            <td style="{S_TD}">{fmt_pct(csi_val)}</td>
            <td style="{S_TD}"></td>
            <td style="{S_TD}"></td>
        </tr>
    </table>
    """
    return html


def make_gauge(value: float, title: str, max_val: float = 100) -> go.Figure:
    """Create a GP% gauge chart."""
    color = "#43A047" if value >= 45 else ("#FFA726" if value >= 35 else "#E53935")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={"text": title, "font": {"size": 16, "color": "#666"}},
        number={"suffix": "%", "font": {"size": 32, "color": "#1A1A2E"}},
        gauge={
            "axis": {"range": [0, max_val], "tickcolor": "#999", "tickwidth": 1},
            "bar": {"color": color, "thickness": 0.7},
            "bgcolor": "#F5F7FA",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 35], "color": "rgba(229,57,53,0.1)"},
                {"range": [35, 45], "color": "rgba(255,167,38,0.1)"},
                {"range": [45, max_val], "color": "rgba(67,160,71,0.1)"},
            ],
            "threshold": {
                "line": {"color": "#1E88E5", "width": 3},
                "thickness": 0.8,
                "value": 45,
            },
        },
    ))
    fig.update_layout(
        height=220,
        margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#1A1A2E"},
    )
    return fig


def make_waterfall(gp_data: dict, title: str) -> go.Figure:
    """Create a waterfall chart showing GP breakdown."""
    fig = go.Figure(go.Waterfall(
        name=title,
        orientation="v",
        measure=["absolute", "relative", "relative", "relative", "relative", "total"],
        x=["Sales", "Parts Costs", "COS Other", "RSB Paint", "Consumables", "Gross Profit"],
        y=[
            gp_data.get("sales", gp_data.get("sales_target", 0)),
            -gp_data.get("parts_costs", 0),
            -gp_data.get("cos_other", 0),
            -gp_data.get("rsb_paint", 0),
            -gp_data.get("consumables_combined", gp_data.get("consumables", 0)),
            0,
        ],
        connector={"line": {"color": "#CCC"}},
        increasing={"marker": {"color": "#43A047"}},
        decreasing={"marker": {"color": "#E53935"}},
        totals={"marker": {"color": "#1E88E5"}},
        textposition="outside",
        text=[
            fmt_currency(gp_data.get("sales", gp_data.get("sales_target", 0))),
            fmt_currency(gp_data.get("parts_costs", 0)),
            fmt_currency(gp_data.get("cos_other", 0)),
            fmt_currency(gp_data.get("rsb_paint", 0)),
            fmt_currency(gp_data.get("consumables_combined", gp_data.get("consumables", 0))),
            fmt_currency(gp_data.get("gross_profit", 0)),
        ],
    ))
    fig.update_layout(
        title={"text": title, "font": {"size": 16, "color": "#666"}},
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#444"},
        yaxis={"gridcolor": "#E8ECF0", "title": ""},
        xaxis={"title": ""},
        showlegend=False,
    )
    return fig


# =====================================================
# PAGE: DASHBOARD
# =====================================================
if page == "📊 Dashboard":
    st.markdown(f"## 📊 {selected_branch} — {selected_month}")

    # Load data
    budget = get_budget_for_branch_month(selected_branch, selected_month)
    actuals_raw = get_actuals_for_branch_month(selected_branch, selected_month)

    # Calculate targets
    if budget:
        targets = targets_from_budget(budget, get_cos_other_pct())
    else:
        targets = None

    # Calculate actuals GP
    if actuals_raw:
        actuals_gp = actuals_from_row(actuals_raw, get_cos_other_pct())
        extras = {
            "diagnostics": float(actuals_raw.get("diagnostics", 0)),
            "additionals": float(actuals_raw.get("additionals", 0)),
            "csi": float(actuals_raw.get("csi", 0)),
            "diagnostics_target": float(budget.get("diagnostics_target", 0)) if budget else 0,
            "additionals_target": float(budget.get("additionals_target", 0)) if budget else 0,
            "csi_target": float(budget.get("csi_target", 0)) if budget else 0,
        }
    else:
        actuals_gp = None
        extras = {
            "diagnostics": 0, "additionals": 0, "csi": 0,
            "diagnostics_target": float(budget.get("diagnostics_target", 0)) if budget else 0,
            "additionals_target": float(budget.get("additionals_target", 0)) if budget else 0,
            "csi_target": float(budget.get("csi_target", 0)) if budget else 0,
        }

    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        actual_sales = actuals_gp["sales"] if actuals_gp else 0
        target_sales = targets["sales_target"] if targets else 0
        delta_sales = actual_sales - target_sales if targets else None
        st.metric("Sales", fmt_currency(actual_sales), delta=fmt_currency(delta_sales) if delta_sales is not None else None)
    with col2:
        actual_gp = actuals_gp["gross_profit"] if actuals_gp else 0
        target_gp = targets["gross_profit"] if targets else 0
        delta_gp = actual_gp - target_gp if targets else None
        st.metric("Gross Profit", fmt_currency(actual_gp), delta=fmt_currency(delta_gp) if delta_gp is not None else None)
    with col3:
        actual_pct = actuals_gp["gp_pct"] if actuals_gp else 0
        target_pct = targets["gp_pct"] if targets else 0
        delta_pct = actual_pct - target_pct if targets else None
        st.metric("GP %", fmt_pct(actual_pct), delta=fmt_pct(delta_pct) if delta_pct is not None else None)
    with col4:
        parts_cost = actuals_gp["parts_costs"] if actuals_gp else 0
        st.metric("Parts Costs", fmt_currency(parts_cost))

    st.markdown("---")

    # Main GP table + gauge
    left, right = st.columns([3, 1])
    with left:
        table_html = build_gp_table_html(targets, actuals_gp, extras)
        components.html(
            f'<div style="background:#FFFFFF;color:#1A1A2E;font-family:sans-serif;padding:10px;">{table_html}</div>',
            height=600,
            scrolling=True,
        )
    with right:
        st.plotly_chart(
            make_gauge(actual_pct, "GP %"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
        if targets:
            st.plotly_chart(
                make_gauge(target_pct, "Target GP %"),
                use_container_width=True,
                config={"displayModeBar": False},
            )

    # Waterfall chart
    st.markdown("---")
    if actuals_gp and actuals_gp["sales"] > 0:
        st.plotly_chart(
            make_waterfall(actuals_gp, f"GP Breakdown — {selected_branch} {selected_month}"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    elif targets:
        st.plotly_chart(
            make_waterfall(targets, f"Target GP Breakdown — {selected_branch} {selected_month}"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    else:
        st.info("No data available. Upload budget or actuals to see the waterfall chart.")


# =====================================================
# PAGE: MANAGER INPUT
# =====================================================
elif page == "📝 Manager Input":
    st.markdown(f"## 📝 Manager Input — {selected_branch}")
    st.caption("Enter actual figures for the selected month. Calculations are automatic.")

    # Managers can edit their own branch; accountants can edit any; admin view-only
    can_edit = can_edit_actuals() and (is_director() or get_user_branch() == selected_branch)
    if not can_edit:
        st.warning("You can only enter data for your own branch.")
        st.stop()

    # Load existing data
    existing = get_actuals_for_branch_month(selected_branch, selected_month)

    with st.form("manager_input", clear_on_submit=False):
        st.markdown(f"### {selected_month}")

        col1, col2 = st.columns(2)
        with col1:
            sales = st.number_input(
                "Sales (R)",
                value=float(existing.get("sales", 0)) if existing else 0.0,
                step=10000.0,
                format="%.0f",
            )
            parts_contribution = st.number_input(
                "Parts Contribution to Sales (R)",
                value=float(existing.get("parts_contribution", 0)) if existing else 0.0,
                step=10000.0,
                format="%.0f",
            )
            parts_gp_pct = st.number_input(
                "Parts GP %",
                value=float(existing.get("parts_gp_pct", 0)) if existing else 0.0,
                min_value=0.0,
                max_value=100.0,
                step=0.5,
            )

        with col2:
            paints = st.number_input(
                "Paints (R)",
                value=float(existing.get("paints", 0)) if existing else 0.0,
                step=1000.0,
                format="%.0f",
            )
            consumables_paintshop = st.number_input(
                "Consumables Paintshop (R)",
                value=float(existing.get("consumables_paintshop", 0)) if existing else 0.0,
                step=1000.0,
                format="%.0f",
            )
            consumables = st.number_input(
                "Consumables (R)",
                value=float(existing.get("consumables", 0)) if existing else 0.0,
                step=1000.0,
                format="%.0f",
            )

        st.divider()
        col3, col4, col5 = st.columns(3)
        with col3:
            diagnostics = st.number_input(
                "Diagnostics (R)",
                value=float(existing.get("diagnostics", 0)) if existing else 0.0,
                step=1000.0,
                format="%.0f",
            )
        with col4:
            additionals = st.number_input(
                "Additionals (R)",
                value=float(existing.get("additionals", 0)) if existing else 0.0,
                step=1000.0,
                format="%.0f",
            )
        with col5:
            csi = st.number_input(
                "CSI %",
                value=float(existing.get("csi", 0)) if existing else 0.0,
                min_value=0.0,
                max_value=100.0,
                step=0.1,
            )

        submitted = st.form_submit_button("💾 Save Data", use_container_width=True, type="primary")

    if submitted:
        data = {
            "sales": sales,
            "parts_contribution": parts_contribution,
            "parts_gp_pct": parts_gp_pct,
            "paints": paints,
            "consumables_paintshop": consumables_paintshop,
            "consumables": consumables,
            "diagnostics": diagnostics,
            "additionals": additionals,
            "csi": csi,
        }
        try:
            save_actuals(selected_branch, selected_month, data, st.session_state["user_email"])
            st.success(f"Data saved for {selected_branch} — {selected_month}!")
        except Exception as e:
            st.error(f"Error saving data: {e}")

    # Live preview of calculations
    if sales > 0:
        st.markdown("---")
        st.markdown("### Live GP Preview")
        preview = calculate_gp_actuals(sales, parts_contribution, parts_gp_pct / 100, paints, consumables_paintshop, consumables)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sales", fmt_currency(preview["sales"]))
        c2.metric("Gross Profit", fmt_currency(preview["gross_profit"]))
        c3.metric("GP %", fmt_pct(preview["gp_pct"]))
        c4.metric("Total Costs", fmt_currency(preview["parts_costs"] + preview["rsb_paint"] + preview["consumables_combined"]))


# =====================================================
# PAGE: QUARTERLY SUMMARY
# =====================================================
elif page == "📈 Quarterly Summary":
    st.markdown(f"## 📈 Quarterly Summary — {selected_branch}")

    # Determine which quarter the selected month is in
    current_quarter = None
    for q, months in QUARTERS.items():
        if selected_month in months:
            current_quarter = q
            break
    if not current_quarter:
        current_quarter = "Q1"

    quarter_tab_names = list(QUARTERS.keys())
    tabs = st.tabs(quarter_tab_names)

    for tab, (q_name, q_months) in zip(tabs, QUARTERS.items()):
        with tab:
            # Collect monthly data
            monthly_actuals = []
            monthly_targets = []
            month_labels = []
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

                month_labels.append(m)

            # Quarter totals
            q_actual = calculate_quarterly_summary(monthly_actuals)
            q_target_data = [t for t in monthly_targets if t]
            if q_target_data:
                q_target_sales = sum(t["sales_target"] for t in q_target_data)
                q_target_parts = sum(t["parts_costs"] for t in q_target_data)
                q_target_cos = sum(t["cos_other"] for t in q_target_data)
                q_target_rsb = sum(t["rsb_paint"] for t in q_target_data)
                q_target_cons = sum(t["consumables"] for t in q_target_data)
                q_target_gp_val = q_target_sales - q_target_parts - q_target_cos - q_target_rsb - q_target_cons
                q_target_gp_pct = (q_target_gp_val / q_target_sales * 100) if q_target_sales > 0 else 0
                q_target_gp = {"sales": q_target_sales, "gross_profit": q_target_gp_val, "gp_pct": q_target_gp_pct}
            else:
                q_target_gp = None

            # Summary metrics
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric(
                    f"{q_name} Sales",
                    fmt_currency(q_actual["sales"]),
                    delta=fmt_currency(q_actual["sales"] - q_target_gp["sales"]) if q_target_gp else None,
                )
            with c2:
                st.metric(
                    f"{q_name} Gross Profit",
                    fmt_currency(q_actual["gross_profit"]),
                    delta=fmt_currency(q_actual["gross_profit"] - q_target_gp["gross_profit"]) if q_target_gp else None,
                )
            with c3:
                st.metric(f"{q_name} GP %", fmt_pct(q_actual["gp_pct"]))
            with c4:
                if q_target_gp:
                    st.metric(f"{q_name} Target GP %", fmt_pct(q_target_gp["gp_pct"]))

            # Monthly comparison chart
            if any(a["sales"] > 0 for a in monthly_actuals):
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name="Actual Sales",
                    x=month_labels,
                    y=[a["sales"] for a in monthly_actuals],
                    marker_color="#1E88E5",
                    text=[fmt_currency(a["sales"]) for a in monthly_actuals],
                    textposition="outside",
                ))
                if q_target_data:
                    fig.add_trace(go.Bar(
                        name="Target Sales",
                        x=month_labels,
                        y=[t["sales_target"] if t else 0 for t in monthly_targets],
                        marker_color="rgba(30,136,229,0.25)",
                        text=[fmt_currency(t["sales_target"]) if t else "" for t in monthly_targets],
                        textposition="outside",
                    ))
                fig.update_layout(
                    barmode="group",
                    height=350,
                    margin=dict(l=20, r=20, t=30, b=20),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font={"color": "#444"},
                    yaxis={"gridcolor": "#E8ECF0"},
                    legend={"orientation": "h", "y": 1.15},
                )
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            # Monthly GP% trend
            gp_pcts = [a["gp_pct"] for a in monthly_actuals]
            target_pcts = [t["gp_pct"] if t else 0 for t in monthly_targets]

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=month_labels, y=gp_pcts,
                mode="lines+markers+text",
                name="Actual GP %",
                line={"color": "#43A047", "width": 3},
                marker={"size": 10},
                text=[fmt_pct(p) for p in gp_pcts],
                textposition="top center",
            ))
            if any(t > 0 for t in target_pcts):
                fig2.add_trace(go.Scatter(
                    x=month_labels, y=target_pcts,
                    mode="lines+markers",
                    name="Target GP %",
                    line={"color": "#1E88E5", "width": 2, "dash": "dash"},
                    marker={"size": 8},
                ))
            fig2.update_layout(
                height=300,
                margin=dict(l=20, r=20, t=30, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"color": "#444"},
                yaxis={"gridcolor": "#E8ECF0", "title": "GP %"},
                legend={"orientation": "h", "y": 1.15},
            )
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # Multi-branch comparison (directors only)
    if is_director():
        st.markdown("---")
        st.markdown("### Branch Comparison")

        branch_data = []
        cos_pct = get_cos_other_pct()
        for branch in BRANCHES:
            q_months = QUARTERS.get(current_quarter, QUARTERS["Q1"])
            monthly_gps = []
            for m in q_months:
                act = get_actuals_for_branch_month(branch, m)
                if act:
                    monthly_gps.append(actuals_from_row(act, cos_pct))
            gp = calculate_quarterly_summary(monthly_gps) if monthly_gps else calculate_gp_actuals(0, 0, 0, 0, 0, 0)
            branch_data.append({"Branch": branch, **gp})

        if any(d["sales"] > 0 for d in branch_data):
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=[d["Branch"] for d in branch_data],
                y=[d["gross_profit"] for d in branch_data],
                marker_color=["#43A047" if d["gp_pct"] >= 45 else ("#FFA726" if d["gp_pct"] >= 35 else "#E53935") for d in branch_data],
                text=[f"{fmt_currency(d['gross_profit'])}<br>{fmt_pct(d['gp_pct'])}" for d in branch_data],
                textposition="outside",
            ))
            fig.update_layout(
                title=f"{current_quarter} Gross Profit by Branch",
                height=400,
                margin=dict(l=20, r=20, t=50, b=20),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font={"color": "#444"},
                yaxis={"gridcolor": "#E8ECF0", "title": "Gross Profit (R)"},
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# =====================================================
# PAGE: BUDGET SETUP (Directors & Accountants)
# =====================================================
elif page == "🎯 Budget Setup":
    if not can_edit_budgets():
        st.warning("Only directors and accountants can manage budget targets.")
        st.stop()

    st.markdown("## 🎯 Budget Setup")
    st.caption("Set monthly targets for each branch.")

    budget_branch = st.selectbox("Branch", BRANCHES, key="budget_branch")
    budget_month = st.selectbox("Month", MONTHS, key="budget_month")

    existing_budget = get_budget_for_branch_month(budget_branch, budget_month)

    with st.form("budget_form"):
        col1, col2 = st.columns(2)
        with col1:
            sales_target = st.number_input(
                "Sales Target (R)",
                value=float(existing_budget.get("sales_target", 0)) if existing_budget else 0.0,
                step=50000.0,
                format="%.0f",
            )
            paint_labour_pct = st.number_input(
                "Paint/Labour/Other %",
                value=float(existing_budget.get("paint_labour_pct", 49)) if existing_budget else 49.0,
                min_value=0.0,
                max_value=100.0,
                step=1.0,
            )
            parts_sales_pct = st.number_input(
                "Parts Sales %",
                value=float(existing_budget.get("parts_sales_pct", 51)) if existing_budget else 51.0,
                min_value=0.0,
                max_value=100.0,
                step=1.0,
            )
        with col2:
            parts_markup = st.number_input(
                "Parts Markup %",
                value=float(existing_budget.get("parts_markup", 25)) if existing_budget else 25.0,
                min_value=0.0,
                max_value=100.0,
                step=1.0,
            )
            cos_other_pct_input = st.number_input(
                "Cost of Sales Other %",
                value=float(existing_budget.get("cos_other_pct", 7)) if existing_budget else 7.0,
                min_value=0.0,
                max_value=50.0,
                step=0.5,
                help="Additional cost of sales as % of total sales.",
            )
            rsb_paint_pct_input = st.number_input(
                "RSB Paint %",
                value=float(existing_budget.get("rsb_paint_pct", 4)) if existing_budget else 4.0,
                min_value=0.0,
                max_value=50.0,
                step=0.5,
                help="RSB Paint target as % of total sales.",
            )
            consumables_pct_input = st.number_input(
                "Consumables Combined %",
                value=float(existing_budget.get("consumables_pct", 3)) if existing_budget else 3.0,
                min_value=0.0,
                max_value=50.0,
                step=0.5,
                help="Consumables Combined target as % of total sales.",
            )
            diagnostics_target = st.number_input(
                "Diagnostics Target (R)",
                value=float(existing_budget.get("diagnostics_target", 0)) if existing_budget else 0.0,
                step=5000.0,
                format="%.0f",
            )
            additionals_target = st.number_input(
                "Additionals Target (R)",
                value=float(existing_budget.get("additionals_target", 0)) if existing_budget else 0.0,
                step=5000.0,
                format="%.0f",
            )
            csi_target = st.number_input(
                "CSI Target %",
                value=float(existing_budget.get("csi_target", 0)) if existing_budget else 0.0,
                min_value=0.0,
                max_value=100.0,
                step=0.5,
            )

        submitted = st.form_submit_button("💾 Save Budget", use_container_width=True, type="primary")

    if submitted:
        if abs(paint_labour_pct + parts_sales_pct - 100) > 0.1:
            st.warning(f"Paint/Labour % + Parts Sales % = {paint_labour_pct + parts_sales_pct}%. Should sum to 100%.")
        data = {
            "sales_target": sales_target,
            "paint_labour_pct": paint_labour_pct,
            "parts_sales_pct": parts_sales_pct,
            "parts_markup": parts_markup,
            "cos_other_pct": cos_other_pct_input,
            "rsb_paint_pct": rsb_paint_pct_input,
            "consumables_pct": consumables_pct_input,
            "diagnostics_target": diagnostics_target,
            "additionals_target": additionals_target,
            "csi_target": csi_target,
        }
        try:
            save_budget(budget_branch, budget_month, data, st.session_state["user_email"])
            st.success(f"Budget saved for {budget_branch} — {budget_month}!")
        except Exception as e:
            st.error(f"Error saving budget: {e}")

    # Preview
    if sales_target > 0:
        st.markdown("---")
        st.markdown("### Target Preview")
        preview = calculate_targets(
            sales_target, paint_labour_pct / 100, parts_sales_pct / 100, parts_markup,
            cos_other_pct=cos_other_pct_input / 100,
            rsb_paint_pct=rsb_paint_pct_input / 100,
            consumables_pct=consumables_pct_input / 100,
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Target GP", fmt_currency(preview["gross_profit"]))
        c2.metric("Target GP %", fmt_pct(preview["gp_pct"]))
        c3.metric("Parts Costs (derived)", fmt_currency(preview["parts_costs"]))


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
        # Reorder columns to match the Excel summary order (single source of truth in reports.py)
        df = df[SUMMARY_COLUMN_KEYS]
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Excel download
        try:
            xlsx_bytes = build_excel_workbook(report)
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


# =====================================================
# PAGE: SETTINGS (Directors & Accountants)
# =====================================================
elif page == "⚙️ Settings":
    if not can_edit_budgets():
        st.warning("Only directors and accountants can manage settings.")
        st.stop()

    st.markdown("## ⚙️ Settings")
    st.caption("Configure global calculation parameters.")

    st.markdown("### GP Calculation Rates")

    current_cos = get_cos_other_pct() * 100  # display as whole number

    with st.form("settings_form"):
        cos_other_input = st.number_input(
            "Cost of Sales Other %",
            value=current_cos,
            min_value=0.0,
            max_value=50.0,
            step=0.5,
            help="Applied as a percentage of total sales. This covers additional cost of sales not captured in parts, paint, or consumables.",
        )

        st.markdown("---")
        st.markdown("**Fixed rates (edit in config.py if needed):**")
        st.markdown(f"- RSB Paint: **{RSB_PAINT_PCT * 100:.0f}%** of sales (target)")
        st.markdown(f"- Consumables Combined: **{CONSUMABLES_PCT * 100:.0f}%** of sales (target)")

        submitted = st.form_submit_button("💾 Save Settings", use_container_width=True, type="primary")

    if submitted:
        try:
            save_setting("cos_other_pct", cos_other_input, st.session_state["user_email"])
            st.success(f"Cost of Sales Other updated to {cos_other_input}%")
        except Exception as e:
            st.error(f"Error saving setting: {e}")

    # Show impact preview
    st.markdown("---")
    st.markdown("### Impact Preview")
    st.caption("How the current rate affects a R5,500,000 sales target:")
    sample = calculate_targets(5500000, 0.49, 0.51, 25, cos_other_pct=cos_other_input / 100)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("COS Other", fmt_currency(sample["cos_other"]))
    c2.metric("Gross Profit", fmt_currency(sample["gross_profit"]))
    c3.metric("GP %", fmt_pct(sample["gp_pct"]))
    c4.metric("Total Deductions", fmt_currency(
        sample["parts_costs"] + sample["cos_other"] + sample["rsb_paint"] + sample["consumables"]
    ))
