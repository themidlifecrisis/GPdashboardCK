"""Formatting and display utilities for the dashboard."""


def fmt_currency(value: float) -> str:
    """Format as South African Rand, e.g. R 1,234,567."""
    if value < 0:
        return f"(R{abs(value):,.0f})"
    return f"R{value:,.0f}"


def fmt_pct(value: float) -> str:
    """Format as percentage, e.g. 45.0%."""
    return f"{value:.1f}%"


def variance_color(variance: float) -> str:
    """Return CSS color based on variance direction."""
    if variance > 0:
        return "#4CAF50"  # green
    elif variance < 0:
        return "#FF5252"  # red
    return "#FAFAFA"  # neutral


def variance_delta_color(variance: float) -> str:
    """Return 'normal' or 'inverse' for st.metric delta_color."""
    return "normal"  # positive = green, negative = red (default)


def fmt_variance(value: float) -> str:
    """Format variance with brackets for negative."""
    if value < 0:
        return f"(R{abs(value):,.0f})"
    elif value > 0:
        return f"R{value:,.0f}"
    return "-"
