"""Plotly chart builders for the clinical visit dashboard.

Charts deliberately avoid silently changing the underlying observations. Longitudinal
axes use the normalized visit order supplied by ``data_utils``.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from data_utils import ordered_visits

ACCENT = "#2F6F78"
ACCENT_DARK = "#245761"
ACCENT_LIGHT = "#AFC9CC"
NEUTRAL = "#D8DEE2"
TEXT = "#24313A"
GRID = "#E9EEF1"
VISIT_PALETTE = ["#245761", "#3F7780", "#5E9299", "#7BA9AE", "#A0C2C5", "#C4DADB"]


def style_figure(fig: go.Figure, height: int = 420, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=35, r=25, t=60, b=45),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, Arial, sans-serif", color=TEXT, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title_text=""),
        showlegend=legend,
        hoverlabel=dict(bgcolor="#FFFFFF", font_size=12),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=TEXT), automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=TEXT), automargin=True)
    return fig


def _safe_range(values: pd.Series, pad: float = 0.12) -> tuple[float, float] | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    lo, hi = float(numeric.min()), float(numeric.max())
    if lo == hi:
        delta = max(abs(lo) * 0.1, 1.0)
        return lo - delta, hi + delta
    span = hi - lo
    return lo - span * pad, hi + span * pad


def visit_counts_figure(visit_counts: pd.DataFrame) -> go.Figure:
    frame = visit_counts.copy()
    frame["Rows"] = pd.to_numeric(frame["Rows"], errors="coerce").fillna(0)
    fig = go.Figure(go.Bar(x=frame["Visit"].astype(str), y=frame["Rows"], marker_color=ACCENT,
                           text=frame["Rows"].map(lambda x: f"{x:,.0f}"), textposition="outside",
                           hovertemplate="%{x}<br>Records: %{y:,}<extra></extra>"))
    fig.update_layout(title="Records by visit stage")
    fig.update_yaxes(title="Records", rangemode="tozero")
    return style_figure(fig, height=360, legend=False)


def missingness_figure(missingness: pd.DataFrame, top_n: int = 12) -> go.Figure:
    frame = missingness.copy().sort_values("Missing %", ascending=False).head(top_n).sort_values("Missing %")
    fig = go.Figure(go.Bar(x=frame["Missing %"], y=frame["Column"].astype(str), orientation="h",
                           marker_color=ACCENT_LIGHT,
                           text=frame["Missing %"].map(lambda v: f"{v:.1f}%"), textposition="outside",
                           hovertemplate="%{y}<br>Missing: %{x:.1f}%<extra></extra>"))
    fig.update_layout(title="Missingness in selected clinical variables")
    fig.update_xaxes(title="Missing values (%)", range=[0, 100])
    return style_figure(fig, height=max(360, 34 * max(len(frame), 1) + 120), legend=False)


def trend_figure(data: pd.DataFrame, metric: str, mode: str, patient_id: str | None = None,
                 chart_type: str = "Line") -> go.Figure:
    frame = data[["Patient ID", "Visit", metric]].copy()
    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.dropna(subset=["Visit", metric])
    visits = ordered_visits(frame["Visit"])
    fill_mode = "tozeroy" if chart_type == "Area" else None

    if mode == "Individual patient":
        frame = frame[frame["Patient ID"].astype("string") == str(patient_id)]
        trend = frame.groupby("Visit", as_index=False)[metric].mean()
        trend["Visit"] = pd.Categorical(trend["Visit"], categories=visits, ordered=True)
        trend = trend.sort_values("Visit")
        fig = go.Figure(go.Scatter(x=trend["Visit"].astype(str), y=trend[metric], mode="lines+markers",
                                   line=dict(color=ACCENT, width=3), marker=dict(size=9, color=ACCENT_DARK),
                                   fill=fill_mode, fillcolor="rgba(47,111,120,0.16)",
                                   hovertemplate=f"Visit: %{{x}}<br>{metric}: %{{y:.3g}}<extra></extra>"))
        fig.update_layout(title=f"{metric} trend — {patient_id}")
    else:
        rows: list[dict[str, Any]] = []
        for visit in visits:
            values = frame.loc[frame["Visit"] == visit, metric].dropna()
            if values.empty:
                continue
            if mode == "Population median":
                center = float(values.median())
                lower = float(values.quantile(0.25))
                upper = float(values.quantile(0.75))
                band_name = "Interquartile range"
            else:
                center = float(values.mean())
                sem = float(values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
                margin = 1.96 * sem
                lower, upper = center - margin, center + margin
                band_name = "95% confidence interval"
            rows.append({"Visit": visit, "Center": center, "Lower": lower, "Upper": upper, "N": int(len(values))})
        trend = pd.DataFrame(rows)
        fig = go.Figure()
        if not trend.empty:
            fig.add_trace(go.Scatter(x=trend["Visit"], y=trend["Upper"], mode="lines", line=dict(width=0),
                                     hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=trend["Visit"], y=trend["Lower"], mode="lines", line=dict(width=0),
                                     fill="tonexty", fillcolor="rgba(47,111,120,0.15)", name=band_name, hoverinfo="skip"))
            label = "Mean" if mode == "Population mean" else "Median"
            fig.add_trace(go.Scatter(x=trend["Visit"], y=trend["Center"], customdata=trend[["N"]],
                                     mode="lines+markers", line=dict(color=ACCENT, width=3), marker=dict(size=9, color=ACCENT_DARK),
                                     fill=fill_mode, fillcolor="rgba(47,111,120,0.10)", name=label,
                                     hovertemplate=f"Visit: %{{x}}<br>{metric}: %{{y:.3g}}<br>N: %{{customdata[0]}}<extra></extra>"))
        fig.update_layout(title=f"{metric} across visits — {mode.lower()}")

    fig.update_xaxes(title="Visit stage", categoryorder="array", categoryarray=visits)
    fig.update_yaxes(title=metric)
    return style_figure(fig, height=470, legend=mode != "Individual patient")


def comparison_bar_figure(baseline_label: str, followup_label: str, baseline_value: float,
                          followup_value: float, metric: str) -> go.Figure:
    frame = pd.DataFrame({"Visit": [baseline_label, followup_label], metric: [baseline_value, followup_value]})
    fig = go.Figure(go.Bar(x=frame["Visit"], y=frame[metric], marker_color=[ACCENT_LIGHT, ACCENT],
                           text=[f"{v:.3g}" if pd.notna(v) else "NA" for v in frame[metric]], textposition="outside",
                           hovertemplate=f"%{{x}}<br>{metric}: %{{y:.3g}}<extra></extra>"))
    fig.update_layout(title=f"Paired {metric}: {baseline_label} vs {followup_label}")
    fig.update_yaxes(title=metric)
    return style_figure(fig, height=390, legend=False)


def paired_scatter_figure(paired: pd.DataFrame, baseline_label: str, followup_label: str, metric: str) -> go.Figure:
    fig = go.Figure()
    if paired.empty:
        fig.update_layout(title="Patient-level paired comparison")
        return style_figure(fig, height=390, legend=False)
    minimum = float(np.nanmin([paired[baseline_label].min(), paired[followup_label].min()]))
    maximum = float(np.nanmax([paired[baseline_label].max(), paired[followup_label].max()]))
    if minimum == maximum:
        maximum = minimum + 1.0
    fig.add_trace(go.Scatter(x=paired[baseline_label], y=paired[followup_label], mode="markers",
                             marker=dict(color=ACCENT, size=8, opacity=0.72), customdata=paired.index.astype(str),
                             hovertemplate=("Patient: %{customdata}<br>" + f"{baseline_label}: %{{x:.3g}}<br>" +
                                            f"{followup_label}: %{{y:.3g}}<extra></extra>")))
    fig.add_trace(go.Scatter(x=[minimum, maximum], y=[minimum, maximum], mode="lines",
                             line=dict(color=NEUTRAL, dash="dash"), hoverinfo="skip", showlegend=False))
    fig.update_layout(title="Patient-level paired comparison")
    fig.update_xaxes(title=f"{baseline_label} {metric}")
    fig.update_yaxes(title=f"{followup_label} {metric}")
    return style_figure(fig, height=390, legend=False)


def delta_distribution_figure(deltas: pd.Series, metric: str) -> go.Figure:
    clean = pd.to_numeric(deltas, errors="coerce").dropna()
    bins = min(30, max(8, int(np.sqrt(max(len(clean), 1)) * 2)))
    fig = px.histogram(x=clean, nbins=bins, labels={"x": f"Change in {metric}", "y": "Patients"},
                       color_discrete_sequence=[ACCENT])
    fig.add_vline(x=0, line_dash="dash", line_color=NEUTRAL)
    fig.update_layout(title="Distribution of patient-level change")
    return style_figure(fig, height=390, legend=False)


def distribution_figure(data: pd.DataFrame, metric: str, chart_type: str) -> go.Figure:
    frame = data[["Visit", metric]].copy()
    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.dropna(subset=["Visit", metric])
    visits = ordered_visits(frame["Visit"])
    color_map = {visit: VISIT_PALETTE[idx % len(VISIT_PALETTE)] for idx, visit in enumerate(visits)}
    if chart_type == "Histogram":
        fig = px.histogram(frame, x=metric, color="Visit", barmode="overlay", opacity=0.58, marginal="rug",
                           category_orders={"Visit": visits}, color_discrete_map=color_map)
        fig.update_layout(title=f"Distribution of {metric} by visit")
    else:
        fig = px.box(frame, x="Visit", y=metric, color="Visit", points="outliers",
                     category_orders={"Visit": visits}, color_discrete_map=color_map)
        fig.update_layout(title=f"{metric} by visit")
        fig.update_traces(marker=dict(size=5, opacity=0.55))
    return style_figure(fig, height=430, legend=chart_type == "Histogram")
