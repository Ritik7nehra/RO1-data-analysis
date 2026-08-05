"""Plotly chart builders for the clinical visit dashboard."""

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
        margin=dict(l=20, r=20, t=55, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, Arial, sans-serif", color=TEXT, size=12),
        title=dict(font=dict(size=17, color=TEXT), x=0.01, xanchor="left"),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            title_text="",
        ),
        showlegend=legend,
        hoverlabel=dict(bgcolor="#FFFFFF", font_size=12),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID, tickfont=dict(color=TEXT))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=TEXT))
    return fig


def visit_counts_figure(visit_counts: pd.DataFrame) -> go.Figure:
    frame = visit_counts.copy()
    fig = go.Figure(
        go.Bar(
            x=frame["Visit"],
            y=frame["Rows"],
            marker_color=ACCENT,
            text=frame["Rows"],
            textposition="outside",
            hovertemplate="%{x}<br>Records: %{y:,}<extra></extra>",
        )
    )
    fig.update_layout(title="Records by visit stage")
    fig.update_yaxes(title="Records", rangemode="tozero")
    fig.update_xaxes(title="")
    return style_figure(fig, height=360, legend=False)


def missingness_figure(missingness: pd.DataFrame, top_n: int = 12) -> go.Figure:
    frame = missingness.head(top_n).sort_values("Missing %", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=frame["Missing %"],
            y=frame["Column"],
            orientation="h",
            marker_color=ACCENT_LIGHT,
            text=frame["Missing %"].map(lambda value: f"{value:.1f}%"),
            textposition="outside",
            hovertemplate="%{y}<br>Missing: %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(title="Missingness in selected clinical variables")
    fig.update_xaxes(title="Missing values (%)", range=[0, max(100, frame["Missing %"].max() * 1.15 if not frame.empty else 100)])
    fig.update_yaxes(title="")
    return style_figure(fig, height=360, legend=False)


def trend_figure(
    data: pd.DataFrame,
    metric: str,
    mode: str,
    patient_id: str | None = None,
    chart_type: str = "Line",
) -> go.Figure:
    frame = data[["Patient ID", "Visit", metric]].copy()
    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.dropna(subset=["Visit", metric])
    visits = ordered_visits(frame["Visit"])
    fill_mode = "tozeroy" if chart_type == "Area" else None

    if mode == "Individual patient":
        frame = frame[frame["Patient ID"] == patient_id]
        trend = frame.groupby("Visit", as_index=False)[metric].mean()
        trend["Visit"] = pd.Categorical(trend["Visit"], categories=visits, ordered=True)
        trend = trend.sort_values("Visit")
        fig = go.Figure(
            go.Scatter(
                x=trend["Visit"].astype(str),
                y=trend[metric],
                mode="lines+markers",
                line=dict(color=ACCENT, width=3),
                marker=dict(size=9, color=ACCENT_DARK),
                fill=fill_mode,
                fillcolor="rgba(47,111,120,0.16)",
                hovertemplate=f"Visit: %{{x}}<br>{metric}: %{{y:.3g}}<extra></extra>",
            )
        )
        fig.update_layout(title=f"{metric} trend — {patient_id}")
    else:
        rows: list[dict[str, Any]] = []
        for visit in visits:
            values = frame.loc[frame["Visit"] == visit, metric].dropna()
            if values.empty:
                continue
            if mode == "Population median":
                center = values.median()
                lower = values.quantile(0.25)
                upper = values.quantile(0.75)
                band_name = "Interquartile range"
            else:
                center = values.mean()
                sem = values.std(ddof=1) / np.sqrt(len(values)) if len(values) > 1 else 0.0
                lower = center - 1.96 * sem
                upper = center + 1.96 * sem
                band_name = "95% confidence interval"
            rows.append(
                {
                    "Visit": visit,
                    "Center": center,
                    "Lower": lower,
                    "Upper": upper,
                    "N": len(values),
                }
            )
        trend = pd.DataFrame(rows)
        fig = go.Figure()
        if not trend.empty:
            fig.add_trace(
                go.Scatter(
                    x=trend["Visit"],
                    y=trend["Upper"],
                    mode="lines",
                    line=dict(width=0),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=trend["Visit"],
                    y=trend["Lower"],
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(47,111,120,0.15)",
                    name=band_name,
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=trend["Visit"],
                    y=trend["Center"],
                    customdata=trend[["N"]],
                    mode="lines+markers",
                    line=dict(color=ACCENT, width=3),
                    marker=dict(size=9, color=ACCENT_DARK),
                    fill=fill_mode,
                    fillcolor="rgba(47,111,120,0.10)",
                    name="Mean" if mode == "Population mean" else "Median",
                    hovertemplate=(
                        f"Visit: %{{x}}<br>{metric}: %{{y:.3g}}"
                        "<br>N: %{customdata[0]}<extra></extra>"
                    ),
                )
            )
        fig.update_layout(title=f"{metric} across visits — {mode.lower()}")

    fig.update_xaxes(title="Visit stage", categoryorder="array", categoryarray=visits)
    fig.update_yaxes(title=metric)
    return style_figure(fig, height=470, legend=mode != "Individual patient")


def comparison_bar_figure(
    baseline_label: str,
    followup_label: str,
    baseline_value: float,
    followup_value: float,
    metric: str,
) -> go.Figure:
    frame = pd.DataFrame(
        {"Visit": [baseline_label, followup_label], metric: [baseline_value, followup_value]}
    )
    fig = go.Figure(
        go.Bar(
            x=frame["Visit"],
            y=frame[metric],
            marker_color=[ACCENT_LIGHT, ACCENT],
            text=[f"{value:.3g}" if pd.notna(value) else "NA" for value in frame[metric]],
            textposition="outside",
            hovertemplate=f"%{{x}}<br>{metric}: %{{y:.3g}}<extra></extra>",
        )
    )
    fig.update_layout(title=f"Paired {metric}: {baseline_label} vs {followup_label}")
    fig.update_xaxes(title="")
    fig.update_yaxes(title=metric, rangemode="tozero")
    return style_figure(fig, height=390, legend=False)


def paired_scatter_figure(
    paired: pd.DataFrame,
    baseline_label: str,
    followup_label: str,
    metric: str,
) -> go.Figure:
    fig = go.Figure()
    if paired.empty:
        return style_figure(fig, height=390, legend=False)

    minimum = float(np.nanmin([paired[baseline_label].min(), paired[followup_label].min()]))
    maximum = float(np.nanmax([paired[baseline_label].max(), paired[followup_label].max()]))
    fig.add_trace(
        go.Scatter(
            x=paired[baseline_label],
            y=paired[followup_label],
            mode="markers",
            marker=dict(color=ACCENT, size=8, opacity=0.72),
            customdata=paired.index.astype(str),
            hovertemplate=(
                "Patient: %{customdata}<br>"
                f"{baseline_label}: %{{x:.3g}}<br>{followup_label}: %{{y:.3g}}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[minimum, maximum],
            y=[minimum, maximum],
            mode="lines",
            line=dict(color=NEUTRAL, dash="dash"),
            hoverinfo="skip",
        )
    )
    fig.update_layout(title="Patient-level paired comparison")
    fig.update_xaxes(title=f"{baseline_label} {metric}")
    fig.update_yaxes(title=f"{followup_label} {metric}")
    return style_figure(fig, height=390, legend=False)


def delta_distribution_figure(deltas: pd.Series, metric: str) -> go.Figure:
    clean = pd.to_numeric(deltas, errors="coerce").dropna()
    fig = px.histogram(
        x=clean,
        nbins=min(30, max(8, int(np.sqrt(max(len(clean), 1))) * 2)),
        labels={"x": f"Change in {metric}", "y": "Patients"},
        color_discrete_sequence=[ACCENT],
    )
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
        fig = px.histogram(
            frame,
            x=metric,
            color="Visit",
            barmode="overlay",
            opacity=0.58,
            marginal="rug",
            category_orders={"Visit": visits},
            color_discrete_map=color_map,
        )
        fig.update_layout(title=f"Distribution of {metric} by visit")
    else:
        fig = px.box(
            frame,
            x="Visit",
            y=metric,
            color="Visit",
            points="outliers",
            category_orders={"Visit": visits},
            color_discrete_map=color_map,
        )
        fig.update_layout(title=f"{metric} by visit")
        fig.update_traces(marker=dict(size=5, opacity=0.55))

    return style_figure(fig, height=430, legend=chart_type == "Histogram")
