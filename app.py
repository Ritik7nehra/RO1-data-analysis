"""Streamlit dashboard for longitudinal clinical visit analysis.

Run locally with:
    streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path
import hashlib

import pandas as pd
import streamlit as st

from charts import (
    comparison_bar_figure,
    delta_distribution_figure,
    distribution_figure,
    missingness_figure,
    paired_scatter_figure,
    trend_figure,
    visit_counts_figure,
)
from data_utils import (
    META_COLUMNS,
    completion_rate,
    dataframe_to_excel_bytes,
    deduplicate_patient_visits,
    filter_clinical_data,
    load_clinical_workbook,
    missingness_table,
    numeric_metric_columns,
    ordered_visits,
    suggested_metrics,
    summary_statistics,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = APP_DIR / "data" / "R_Deidentified_R01_.xlsx"
PLOTLY_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}


st.set_page_config(
    page_title="Clinical Visit Analytics",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        :root {
            --accent: #2F6F78;
            --accent-dark: #245761;
            --surface: #FFFFFF;
            --background: #F5F7F8;
            --border: #E1E7EA;
            --text: #24313A;
            --muted: #6C7A83;
        }
        #MainMenu, footer {visibility: hidden;}
        [data-testid="stHeader"] {background: rgba(245, 247, 248, 0.88);}
        [data-testid="stAppViewContainer"] {background: var(--background);}
        [data-testid="stSidebar"] {
            background: #F0F4F5;
            border-right: 1px solid var(--border);
        }
        [data-testid="stSidebar"] .block-container {padding-top: 1.2rem;}
        .block-container {
            max-width: 1580px;
            padding-top: 1.35rem;
            padding-bottom: 2.5rem;
        }
        h1, h2, h3 {color: var(--text); letter-spacing: -0.02em;}
        h1 {font-size: 2.05rem !important; margin-bottom: 0.25rem !important;}
        h2 {font-size: 1.35rem !important;}
        h3 {font-size: 1.08rem !important;}
        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 1rem 1.05rem;
            box-shadow: 0 1px 2px rgba(22, 34, 42, 0.03);
        }
        [data-testid="stMetricLabel"] {color: var(--muted);}
        [data-testid="stMetricValue"] {color: var(--text);}
        [data-testid="stTabs"] button {font-weight: 600;}
        [data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 10px;
            overflow: hidden;
        }
        .dashboard-hero {
            background: linear-gradient(115deg, #FFFFFF 0%, #F3F8F8 100%);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.25rem 1.4rem;
            margin-bottom: 1rem;
        }
        .dashboard-hero p {color: var(--muted); margin: 0.25rem 0 0 0;}
        .soft-note {
            background: #F8FBFB;
            border-left: 4px solid var(--accent);
            padding: 0.75rem 0.9rem;
            border-radius: 8px;
            color: var(--text);
            margin: 0.5rem 0 1rem 0;
        }
        .small-muted {color: var(--muted); font-size: 0.88rem;}
        div[data-baseweb="select"] > div {border-color: var(--border);}
        .stDownloadButton button, .stButton button {
            border-radius: 9px;
            border-color: #CBD6DA;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_data_cached(file_bytes: bytes, file_name: str) -> dict:
    return load_clinical_workbook(file_bytes, file_name)


def natural_sort(values: list[str]) -> list[str]:
    def key(value: str):
        import re

        return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]

    return sorted(values, key=key)


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{digits}f}"


def show_quality_panel(bundle: dict, filtered_data: pd.DataFrame, key_metrics: list[str]) -> None:
    quality = bundle["quality"]
    with st.expander("Data quality and workbook audit", expanded=False):
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Missing patient IDs", f"{quality['Missing Patient IDs']:,}")
        q2.metric("Duplicate patient-visits", f"{quality['Duplicate Patient-Visit Rows']:,}")
        q3.metric("Visit-date coverage", f"{quality['Visit Date Coverage %']:.1f}%")
        q4.metric(
            "Conflicting duplicate fields",
            f"{quality['Column Conflicts During Coalescing']:,}",
            help="Conflicting fields were preserved as separately numbered columns; no values were overwritten.",
        )

        st.markdown("#### Sheets loaded")
        st.dataframe(bundle["sheet_summary"], width="stretch", hide_index=True)

        if not bundle["excluded_sheets"].empty:
            st.markdown("#### Reference or excluded sheets")
            st.dataframe(bundle["excluded_sheets"], width="stretch", hide_index=True)

        if bundle["warnings"]:
            for warning in bundle["warnings"]:
                st.warning(warning)

        changed = bundle["column_mappings"]
        if not changed.empty:
            st.markdown("#### Normalized or preserved duplicate column labels")
            st.caption(
                "Only labels needed for consistent cross-visit analysis are standardized. "
                "Conflicting duplicate fields remain separate to protect source information."
            )
            st.dataframe(changed.head(300), width="stretch", hide_index=True, height=320)

        if key_metrics:
            st.markdown("#### Missingness for selected variables")
            metric_missingness = missingness_table(filtered_data, key_metrics)
            st.dataframe(
                metric_missingness.style.format({"Missing %": "{:.1f}%"}),
                width="stretch",
                hide_index=True,
            )


def render_overview(
    bundle: dict,
    filtered: pd.DataFrame,
    selected_visits: list[str],
    key_metrics: list[str],
) -> None:
    unique_patients = filtered["Patient ID"].nunique(dropna=True)
    patient_visits = (
        filtered.dropna(subset=["Patient ID", "Visit"])
        .drop_duplicates(["Patient ID", "Visit"])
        .shape[0]
    )
    completion = completion_rate(filtered, selected_visits)

    missing_columns = key_metrics or [
        column
        for column in numeric_metric_columns(filtered)
        if column not in META_COLUMNS
    ][:10]
    if missing_columns:
        missing_pct = filtered[missing_columns].isna().sum().sum() / max(
            filtered[missing_columns].size, 1
        ) * 100
    else:
        missing_pct = 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Patients", f"{unique_patients:,}")
    k2.metric("Patient-visits", f"{patient_visits:,}")
    k3.metric(
        "Visit completion rate",
        f"{completion:.1f}%",
        help="Observed patient-visit combinations divided by all selected visits expected for the filtered patients.",
    )
    k4.metric(
        "Missing clinical data",
        f"{missing_pct:.1f}%",
        help="Missingness across the clinical variables selected in the sidebar.",
    )

    chart_left, chart_right = st.columns([1, 1])
    visit_counts = (
        filtered.groupby("Visit", dropna=False)
        .size()
        .rename("Rows")
        .reset_index()
    )
    visit_counts["Visit"] = visit_counts["Visit"].fillna("Unrecognized")
    order = ordered_visits(visit_counts["Visit"])
    visit_counts["Visit"] = pd.Categorical(visit_counts["Visit"], categories=order, ordered=True)
    visit_counts = visit_counts.sort_values("Visit")

    with chart_left:
        st.plotly_chart(
            visit_counts_figure(visit_counts),
            width="stretch",
            config=PLOTLY_CONFIG,
        )
    with chart_right:
        miss = missingness_table(filtered, missing_columns)
        if miss.empty:
            st.info("Select at least one numeric clinical variable to display missingness.")
        else:
            st.plotly_chart(
                missingness_figure(miss),
                width="stretch",
                config=PLOTLY_CONFIG,
            )

    st.markdown("### Summary statistics by visit")
    stats = summary_statistics(filtered, key_metrics)
    if stats.empty:
        st.info("Choose one or more numeric clinical variables in the sidebar.")
    else:
        st.dataframe(
            stats.style.format(
                {
                    "Mean": "{:.3f}",
                    "Median": "{:.3f}",
                    "SD": "{:.3f}",
                },
                na_rep="—",
            ),
            width="stretch",
            hide_index=True,
            height=min(520, 86 + len(stats) * 35),
        )

    show_quality_panel(bundle, filtered, key_metrics)


def render_trends(filtered: pd.DataFrame, metric_options: list[str], widget_prefix: str) -> None:
    if not metric_options:
        st.info("No numeric clinical variables are available after filtering.")
        return

    control_1, control_2, control_3 = st.columns([1.4, 1, 0.8])
    metric = control_1.selectbox(
        "Clinical metric",
        metric_options,
        key=f"{widget_prefix}_trend_metric",
    )
    mode = control_2.selectbox(
        "Trend view",
        ["Population mean", "Population median", "Individual patient"],
        key=f"{widget_prefix}_trend_mode",
    )
    chart_type = control_3.radio(
        "Chart",
        ["Line", "Area"],
        horizontal=True,
        key=f"{widget_prefix}_trend_chart",
    )

    patient_id = None
    if mode == "Individual patient":
        patients = natural_sort(
            filtered.loc[filtered[metric].notna(), "Patient ID"].dropna().astype(str).unique().tolist()
        )
        if not patients:
            st.info(f"No patients have non-missing {metric} values in the current filters.")
            return
        patient_id = st.selectbox(
            "Patient ID",
            patients,
            key=f"{widget_prefix}_trend_patient",
        )

    st.plotly_chart(
        trend_figure(filtered, metric, mode, patient_id, chart_type),
        width="stretch",
        config=PLOTLY_CONFIG,
    )

    trend_stats = summary_statistics(filtered, [metric])
    if not trend_stats.empty:
        st.markdown("#### Visit-level values used in the chart")
        st.dataframe(
            trend_stats.style.format(
                {"Mean": "{:.3f}", "Median": "{:.3f}", "SD": "{:.3f}"},
                na_rep="—",
            ),
            width="stretch",
            hide_index=True,
        )


def render_comparisons(filtered: pd.DataFrame, metric_options: list[str], widget_prefix: str) -> None:
    visits = ordered_visits(filtered["Visit"])
    if len(visits) < 2:
        st.info("Select at least two visit stages to use the comparison view.")
        return
    if not metric_options:
        st.info("No numeric clinical variables are available after filtering.")
        return

    c1, c2, c3, c4 = st.columns([1.35, 1, 1, 0.8])
    metric = c1.selectbox(
        "Clinical metric",
        metric_options,
        key=f"{widget_prefix}_comparison_metric",
    )
    baseline = c2.selectbox(
        "Baseline visit",
        visits,
        index=0,
        key=f"{widget_prefix}_baseline_visit",
    )
    followup_candidates = [visit for visit in visits if visit != baseline]
    followup = c3.selectbox(
        "Comparison visit",
        followup_candidates,
        index=len(followup_candidates) - 1,
        key=f"{widget_prefix}_followup_visit",
    )
    aggregation = c4.radio(
        "Statistic",
        ["Mean", "Median"],
        horizontal=True,
        key=f"{widget_prefix}_comparison_stat",
    )

    comparison = filtered[["Patient ID", "Visit", metric]].copy()
    comparison[metric] = pd.to_numeric(comparison[metric], errors="coerce")
    comparison = comparison.dropna(subset=["Patient ID", "Visit", metric])
    pivot = comparison.pivot_table(
        index="Patient ID",
        columns="Visit",
        values=metric,
        aggfunc="mean",
    )

    if baseline not in pivot.columns or followup not in pivot.columns:
        st.info("The selected visits do not contain comparable values for this metric.")
        return
    paired = pivot[[baseline, followup]].dropna()
    if paired.empty:
        st.info("No patients have non-missing values at both selected visits.")
        return

    reducer = "mean" if aggregation == "Mean" else "median"
    baseline_value = getattr(paired[baseline], reducer)()
    followup_value = getattr(paired[followup], reducer)()
    deltas = paired[followup] - paired[baseline]
    delta_value = getattr(deltas, reducer)()
    percent_change = (
        delta_value / baseline_value * 100
        if pd.notna(baseline_value) and baseline_value != 0
        else float("nan")
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{baseline} {aggregation.lower()}", format_number(baseline_value, 3))
    m2.metric(
        f"{followup} {aggregation.lower()}",
        format_number(followup_value, 3),
        delta=f"{delta_value:+.3f} vs {baseline}",
    )
    percent_text = "—" if pd.isna(percent_change) else f"{percent_change:,.2f}%"
    m3.metric("Relative change", percent_text)
    m4.metric("Paired patients", f"{len(paired):,}")

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.plotly_chart(
            comparison_bar_figure(
                baseline,
                followup,
                baseline_value,
                followup_value,
                metric,
            ),
            width="stretch",
            config=PLOTLY_CONFIG,
        )
    with chart_right:
        st.plotly_chart(
            paired_scatter_figure(paired, baseline, followup, metric),
            width="stretch",
            config=PLOTLY_CONFIG,
        )

    st.plotly_chart(
        delta_distribution_figure(deltas, metric),
        width="stretch",
        config=PLOTLY_CONFIG,
    )

    st.markdown("### Distribution analysis")
    distribution_controls = st.columns([1, 4])
    distribution_type = distribution_controls[0].radio(
        "Plot type",
        ["Box plot", "Histogram"],
        key=f"{widget_prefix}_distribution_type",
    )
    st.plotly_chart(
        distribution_figure(
            filtered,
            metric,
            "Histogram" if distribution_type == "Histogram" else "Box plot",
        ),
        width="stretch",
        config=PLOTLY_CONFIG,
    )


def render_raw_data(
    filtered: pd.DataFrame,
    key_metrics: list[str],
    quality: dict,
    widget_prefix: str,
) -> None:
    default_columns = [
        column
        for column in [
            "Patient ID",
            "Visit",
            "Visit Date",
            "Event Name",
            *key_metrics,
            "Source Sheet",
            "Source Row",
        ]
        if column in filtered.columns
    ]

    controls = st.columns([1.1, 2.4])
    search = controls[0].text_input(
        "Search visible data",
        placeholder="Patient ID or any displayed value",
        key=f"{widget_prefix}_raw_search",
    )
    display_columns = controls[1].multiselect(
        "Columns to display and export",
        options=list(filtered.columns),
        default=default_columns,
        key=f"{widget_prefix}_raw_columns",
    )
    if not display_columns:
        display_columns = default_columns or list(filtered.columns[:10])

    table = filtered[display_columns].copy()
    if search.strip():
        needle = search.strip().lower()
        matches = table.astype("string").apply(
            lambda column: column.str.lower().str.contains(needle, na=False)
        )
        table = table[matches.any(axis=1)]

    st.caption(f"Showing {len(table):,} of {len(filtered):,} filtered rows.")
    st.dataframe(table, width="stretch", hide_index=True, height=560)

    stats = summary_statistics(filtered, key_metrics)
    excel_bytes = dataframe_to_excel_bytes(table, stats=stats, quality=quality)
    csv_bytes = table.to_csv(index=False).encode("utf-8-sig")

    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button(
        "Download Excel",
        data=excel_bytes,
        file_name="clinical_dashboard_filtered_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    d2.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name="clinical_dashboard_filtered_data.csv",
        mime="text/csv",
        width="stretch",
    )


# -----------------------------------------------------------------------------
# Sidebar: source file and analysis controls
# -----------------------------------------------------------------------------
st.sidebar.markdown("## Clinical Visit Analytics")
st.sidebar.caption("Longitudinal, deidentified patient-level review")

uploaded_file = st.sidebar.file_uploader(
    "Excel workbook",
    type=["xlsx", "xlsm"],
    help="Upload a workbook containing visit sheets such as V1, Visit_2, V3, or v4.",
)

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    file_name = uploaded_file.name
    source_label = "Uploaded workbook"
elif DEFAULT_DATA_PATH.exists():
    file_bytes = DEFAULT_DATA_PATH.read_bytes()
    file_name = DEFAULT_DATA_PATH.name
    source_label = "Bundled deidentified workbook"
else:
    st.info("Upload an Excel workbook from the sidebar to begin.")
    st.stop()

file_key = hashlib.sha1(file_bytes).hexdigest()[:10]

try:
    with st.spinner("Loading and validating visit sheets…"):
        bundle = load_data_cached(file_bytes, file_name)
except Exception as exc:
    st.error(f"The workbook could not be loaded: {exc}")
    st.stop()

st.sidebar.success(
    f"{source_label}\n\n{bundle['quality']['Rows Loaded']:,} visit rows · "
    f"{bundle['quality']['Unique Patients']:,} patients"
)

with st.sidebar.expander("Data handling", expanded=False):
    duplicate_policy = st.selectbox(
        "Duplicate patient-visit policy",
        ["Keep most complete row", "Combine duplicate rows", "Keep all rows"],
        help="This affects dashboard calculations only. The source Excel file is never changed.",
        key=f"{file_key}_duplicate_policy",
    )
    st.caption(
        "Column aliases can be extended in `CANONICAL_COLUMN_PATTERNS` inside "
        "`data_utils.py` when future files use new clinical labels."
    )

analysis_data = deduplicate_patient_visits(bundle["data"], duplicate_policy)
all_visits = ordered_visits(analysis_data["Visit"])
all_patients = natural_sort(
    analysis_data["Patient ID"].dropna().astype(str).unique().tolist()
)
all_metrics = numeric_metric_columns(analysis_data)
default_metrics = suggested_metrics(analysis_data)

st.sidebar.markdown("### Filters")
selected_patients = st.sidebar.multiselect(
    "Patient ID",
    options=all_patients,
    default=[],
    placeholder="All patients",
    key=f"{file_key}_patients",
)
selected_visits = st.sidebar.multiselect(
    "Visit stage",
    options=all_visits,
    default=all_visits,
    key=f"{file_key}_visits",
)

apply_date_filter = False
date_range = None
visit_dates = pd.to_datetime(analysis_data.get("Visit Date"), errors="coerce").dropna()
if not visit_dates.empty:
    apply_date_filter = st.sidebar.checkbox(
        "Apply visit-date filter",
        value=False,
        key=f"{file_key}_apply_date",
    )
    if apply_date_filter:
        date_selection = st.sidebar.date_input(
            "Visit date range",
            value=(visit_dates.min().date(), visit_dates.max().date()),
            min_value=visit_dates.min().date(),
            max_value=visit_dates.max().date(),
            key=f"{file_key}_date_range",
        )
        if isinstance(date_selection, (tuple, list)) and len(date_selection) == 2:
            date_range = (date_selection[0], date_selection[1])
else:
    st.sidebar.caption("No usable visit-date field was detected.")

key_metrics = st.sidebar.multiselect(
    "Key clinical variables",
    options=all_metrics,
    default=default_metrics,
    help="These variables drive KPI missingness, summaries, trends, and exports.",
    key=f"{file_key}_key_metrics",
)

numeric_ranges: dict[str, tuple[float, float]] = {}
with st.sidebar.expander("Clinical value filters", expanded=False):
    range_metrics = st.multiselect(
        "Filter up to three variables",
        options=key_metrics or all_metrics,
        max_selections=3,
        key=f"{file_key}_range_metrics",
    )
    for metric in range_metrics:
        values = pd.to_numeric(analysis_data[metric], errors="coerce").dropna()
        if values.empty:
            continue
        lower, upper = float(values.min()), float(values.max())
        if lower == upper:
            st.caption(f"{metric}: all non-missing values are {lower:g}.")
            continue
        step = max((upper - lower) / 200, 0.001)
        selected_range = st.slider(
            metric,
            min_value=lower,
            max_value=upper,
            value=(lower, upper),
            step=step,
            key=f"{file_key}_range_{metric}",
        )
        numeric_ranges[metric] = selected_range

filtered = filter_clinical_data(
    analysis_data,
    patient_ids=selected_patients,
    visits=selected_visits,
    date_range=date_range,
    numeric_ranges=numeric_ranges,
)

if filtered.empty:
    st.warning("The current filters return no rows. Adjust the sidebar selections.")
    st.stop()

# -----------------------------------------------------------------------------
# Main dashboard
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="dashboard-hero">
        <h1>Clinical Patient Visit Dashboard</h1>
        <p><strong>{file_name}</strong> · Visits normalized across workbook sheets · Source data remains unchanged</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="soft-note">
        Visit sheets are combined into a longitudinal table using the detected patient ID. 
        Sheet labels and event values are normalized to consistent visit stages, while the original source sheet and row remain traceable.
    </div>
    """,
    unsafe_allow_html=True,
)

overview_tab, trends_tab, comparison_tab, raw_tab = st.tabs(
    ["Overview", "Trends", "Comparisons", "Raw Data"]
)

with overview_tab:
    render_overview(bundle, filtered, selected_visits, key_metrics)

with trends_tab:
    render_trends(filtered, key_metrics or all_metrics, file_key)

with comparison_tab:
    render_comparisons(filtered, key_metrics or all_metrics, file_key)

with raw_tab:
    render_raw_data(filtered, key_metrics, bundle["quality"], file_key)

st.markdown(
    "<p class='small-muted'>All processing occurs in memory. The uploaded workbook is not modified by the dashboard.</p>",
    unsafe_allow_html=True,
)
