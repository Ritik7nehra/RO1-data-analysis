"""Streamlit dashboard for longitudinal clinical visit analysis."""
from __future__ import annotations
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import streamlit as st
from charts import comparison_bar_figure, delta_distribution_figure, distribution_figure, missingness_figure, paired_scatter_figure, trend_figure, visit_counts_figure
from data_utils import completion_rate, dataframe_to_excel_bytes, deduplicate_patient_visits, filter_clinical_data, load_clinical_workbook, missingness_table, numeric_metric_columns, ordered_visits, patient_visit_level, suggested_metrics
APP_DIR=Path(__file__).resolve().parent
PLOTLY_CONFIG={"displaylogo":False,"responsive":True,"modeBarButtonsToRemove":["lasso2d","select2d"]}
st.set_page_config(page_title="Clinical Visit Analytics",page_icon="🩺",layout="wide",initial_sidebar_state="expanded")
st.markdown("""<style>:root{--bg:#F5F7F8;--border:#E1E7EA;--text:#24313A;--muted:#6C7A83}#MainMenu,footer{visibility:hidden}[data-testid="stAppViewContainer"]{background:var(--bg)}[data-testid="stSidebar"]{background:#F0F4F5;border-right:1px solid var(--border)}.block-container{max-width:1580px;padding-top:1.2rem;padding-bottom:2.5rem}h1,h2,h3{color:var(--text);letter-spacing:-.02em}[data-testid="stMetric"]{background:#FFF;border:1px solid var(--border);border-radius:14px;padding:1rem}.dashboard-hero{background:linear-gradient(115deg,#FFF 0%,#F3F8F8 100%);border:1px solid var(--border);border-radius:16px;padding:1.25rem 1.4rem;margin-bottom:1rem}.dashboard-hero p{color:var(--muted);margin:.25rem 0 0}.small-muted{color:var(--muted);font-size:.88rem}</style>""",unsafe_allow_html=True)
@st.cache_data(show_spinner=False)
def load_data_cached(file_bytes:bytes,file_name:str)->dict:return load_clinical_workbook(file_bytes,file_name)
def natural_sort(values):
 import re
 return sorted(values,key=lambda x:[int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)",x)])
def fmt(value,digits=2):return "—" if value is None or pd.isna(value) else f"{value:,.{digits}f}"
def render_quality(bundle,data,metrics):
 q=bundle["quality"]
 with st.expander("Data quality and workbook audit",expanded=False):
  a,b,c,d=st.columns(4);a.metric("Rows",f"{q['Rows']:,}");b.metric("Unique patients",f"{q['Unique Patients']:,}");c.metric("Duplicate patient-visits",f"{q['Duplicate Patient-Visit Rows']:,}");d.metric("Visit-date coverage",f"{q['Visit Date Coverage %']:.1f}%")
  if q.get("Column Conflicts During Coalescing",0):st.warning(f"{q['Column Conflicts During Coalescing']:,} conflicting duplicate-column cells were preserved instead of overwritten.")
  st.dataframe(bundle["sheet_summary"],width="stretch",hide_index=True)
  if not bundle["excluded_sheets"].empty:st.dataframe(bundle["excluded_sheets"],width="stretch",hide_index=True)
  for warning in bundle["warnings"]:st.warning(warning)
  if metrics:st.dataframe(missingness_table(data,metrics).style.format({"Missing %":"{:.1f}%"}),width="stretch",hide_index=True)
  if not bundle["column_mappings"].empty:st.dataframe(bundle["column_mappings"].head(300),width="stretch",hide_index=True,height=300)
def render_overview(bundle,data,visits,metrics):
 analysis=patient_visit_level(data,metrics);patients=analysis["Patient ID"].nunique() if "Patient ID" in analysis else 0;pv=analysis[["Patient ID","Visit"]].drop_duplicates().shape[0];completion=completion_rate(data,visits);miss=missingness_table(analysis,metrics);missing_pct=float(miss["Missing"].sum()/miss["Total"].sum()*100) if not miss.empty and miss["Total"].sum() else 0
 k1,k2,k3,k4=st.columns(4);k1.metric("Patients",f"{patients:,}");k2.metric("Patient-visits",f"{pv:,}");k3.metric("Visit completion",f"{completion:.1f}%");k4.metric("Missing selected data",f"{missing_pct:.1f}%")
 left,right=st.columns(2);counts=analysis.groupby("Visit",as_index=False).size().rename(columns={"size":"Rows"});counts["Visit"]=pd.Categorical(counts["Visit"],categories=ordered_visits(counts["Visit"]),ordered=True);counts=counts.sort_values("Visit")
 with left:st.plotly_chart(visit_counts_figure(counts),width="stretch",config=PLOTLY_CONFIG)
 with right:
  if miss.empty:st.info("No selected numeric variables have usable values.")
  else:st.plotly_chart(missingness_figure(miss),width="stretch",config=PLOTLY_CONFIG)
 stats=[]
 for m in metrics:
  for v in ordered_visits(analysis["Visit"]):
   x=pd.to_numeric(analysis.loc[analysis["Visit"]==v,m],errors="coerce").dropna()
   if len(x):stats.append({"Metric":m,"Visit":v,"N":len(x),"Mean":x.mean(),"Median":x.median(),"SD":x.std(ddof=1) if len(x)>1 else np.nan})
 st.markdown("### Summary statistics by visit")
 st.dataframe(pd.DataFrame(stats).style.format({"Mean":"{:.3f}","Median":"{:.3f}","SD":"{:.3f}"},na_rep="—"),width="stretch",hide_index=True) if stats else st.info("Choose at least one numeric clinical variable.")
 render_quality(bundle,data,metrics)
def render_trends(data,metrics,prefix):
 if not metrics:st.info("No numeric clinical variables are available.");return
 a,b,c=st.columns([1.4,1,.8]);metric=a.selectbox("Clinical metric",metrics,key=f"{prefix}_metric");mode=b.selectbox("Trend view",["Population mean","Population median","Individual patient"],key=f"{prefix}_mode");chart=c.radio("Chart",["Line","Area"],horizontal=True,key=f"{prefix}_chart");patient=None
 if mode=="Individual patient":
  patients=natural_sort(data.loc[data[metric].notna(),"Patient ID"].dropna().astype(str).unique().tolist())
  if not patients:st.info("No patients have a value for this metric.");return
  patient=st.selectbox("Patient ID",patients,key=f"{prefix}_patient")
 st.plotly_chart(trend_figure(data,metric,mode,patient,chart),width="stretch",config=PLOTLY_CONFIG)
def render_comparisons(data,metrics,prefix):
 visits=ordered_visits(data["Visit"])
 if len(visits)<2:st.info("Select at least two visit stages.");return
 if not metrics:st.info("No numeric clinical variables are available.");return
 a,b,c,d=st.columns([1.35,1,1,.8]);metric=a.selectbox("Clinical metric",metrics,key=f"{prefix}_metric");baseline=b.selectbox("Baseline visit",visits,index=0,key=f"{prefix}_baseline");candidates=[v for v in visits if v!=baseline];follow=c.selectbox("Comparison visit",candidates,index=len(candidates)-1,key=f"{prefix}_follow");statistic=d.radio("Statistic",["Mean","Median"],horizontal=True,key=f"{prefix}_stat")
 frame=data[["Patient ID","Visit",metric]].copy();frame[metric]=pd.to_numeric(frame[metric],errors="coerce");frame=frame.dropna(subset=["Patient ID","Visit",metric]);pivot=frame.groupby(["Patient ID","Visit"])[metric].mean().unstack("Visit")
 if baseline not in pivot or follow not in pivot:st.info("The selected visits do not have comparable values.");return
 paired=pivot[[baseline,follow]].dropna()
 if paired.empty:st.info("No patients have non-missing values at both visits.");return
 reducer="mean" if statistic=="Mean" else "median";bval=float(getattr(paired[baseline],reducer)());fval=float(getattr(paired[follow],reducer)());deltas=paired[follow]-paired[baseline];dval=float(getattr(deltas,reducer)());pct=dval/bval*100 if bval!=0 else np.nan
 m1,m2,m3,m4=st.columns(4);m1.metric(f"{baseline} {statistic.lower()}",fmt(bval,3));m2.metric(f"{follow} {statistic.lower()}",fmt(fval,3),delta=f"{dval:+.3f} vs {baseline}");m3.metric("Relative change","—" if pd.isna(pct) else f"{pct:.2f}%");m4.metric("Paired patients",f"{len(paired):,}")
 x,y=st.columns(2)
 with x:st.plotly_chart(comparison_bar_figure(baseline,follow,bval,fval,metric),width="stretch",config=PLOTLY_CONFIG)
 with y:st.plotly_chart(paired_scatter_figure(paired,baseline,follow,metric),width="stretch",config=PLOTLY_CONFIG)
 st.plotly_chart(delta_distribution_figure(deltas,metric),width="stretch",config=PLOTLY_CONFIG);st.caption("Only patients with values at both visits are included. Duplicate source rows are averaged within patient/visit before pairing.")
def render_distributions(data,metrics,prefix):
 if not metrics:st.info("No numeric clinical variables are available.");return
 a,b=st.columns([1.4,1]);metric=a.selectbox("Clinical metric",metrics,key=f"{prefix}_metric");chart=b.radio("Distribution",["Box plot","Histogram"],horizontal=True,key=f"{prefix}_type");st.plotly_chart(distribution_figure(data,metric,"Histogram" if chart=="Histogram" else "Box plot"),width="stretch",config=PLOTLY_CONFIG)
def render_raw(data,prefix):
 cols=[c for c in data.columns if c!="Duplicate Patient-Visit"];selected=st.multiselect("Columns",cols,default=cols[:min(14,len(cols))],key=f"{prefix}_columns");view=data[selected].copy() if selected else data.copy();search=st.text_input("Search patient ID",key=f"{prefix}_search")
 if search and "Patient ID" in view:view=view[view["Patient ID"].astype("string").str.contains(search,case=False,regex=False,na=False)]
 st.dataframe(view,width="stretch",hide_index=True,height=520);st.download_button("Download CSV",view.to_csv(index=False).encode(),file_name="clinical_filtered.csv",mime="text/csv",key=f"{prefix}_csv");st.download_button("Download Excel",dataframe_to_excel_bytes(view),file_name="clinical_filtered.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key=f"{prefix}_xlsx")
st.sidebar.header("Data source");uploaded=st.sidebar.file_uploader("Upload clinical workbook",type=["xlsx","xlsm"],help="Processed in memory; source workbook is not modified.")
if not uploaded:
 st.markdown('<div class="dashboard-hero"><h1>Clinical Visit Analytics</h1><p>Upload the deidentified Excel workbook to begin.</p></div>',unsafe_allow_html=True);st.info("No workbook uploaded yet.");st.stop()
file_bytes=uploaded.getvalue();file_hash=hashlib.sha256(file_bytes).hexdigest()
try:bundle=load_data_cached(file_bytes,uploaded.name)
except Exception as exc:st.error(f"Workbook could not be loaded: {exc}");st.stop()
raw=bundle["data"];all_visits=ordered_visits(raw["Visit"]);numeric=numeric_metric_columns(raw);defaults=suggested_metrics(raw,6)
st.sidebar.caption(f"Loaded {len(raw):,} rows • {raw['Patient ID'].nunique(dropna=True):,} patients • {len(all_visits)} visit stages")
selected_visits=st.sidebar.multiselect("Visit stages",all_visits,default=all_visits,key="selected_visits");patient_search=st.sidebar.text_input("Patient ID contains",key="patient_search");sex_options=sorted(raw["Sex"].dropna().astype(str).unique().tolist()) if "Sex" in raw else [];sex_filter=st.sidebar.multiselect("Sex",sex_options,key="sex_filter") if sex_options else [];metrics=st.sidebar.multiselect("Clinical variables",numeric,default=[m for m in defaults if m in numeric],key="metrics");strategy=st.sidebar.selectbox("Duplicate patient-visit handling",["Most complete","Average numeric duplicates","Keep all"],help="Most complete is the safest default for patient-level summaries.")
filtered=filter_clinical_data(raw,selected_visits,patient_search,sex_filter);analysis=deduplicate_patient_visits(filtered,strategy)
st.markdown('<div class="dashboard-hero"><h1>Clinical Visit Analytics</h1><p>Longitudinal patient-level analysis with explicit visit ordering, duplicate handling, missingness auditing, and exportable filtered data.</p></div>',unsafe_allow_html=True);st.caption(f"Source: {uploaded.name} • File fingerprint: {file_hash[:12]} • Filtered rows: {len(filtered):,} • Analysis rows: {len(analysis):,}")
tabs=st.tabs(["Overview","Trends","Comparisons","Distributions","Raw Data"])
with tabs[0]:render_overview(bundle,analysis,selected_visits,metrics)
with tabs[1]:render_trends(analysis,metrics,"trend")
with tabs[2]:render_comparisons(analysis,metrics,"comparison")
with tabs[3]:render_distributions(analysis,metrics,"distribution")
with tabs[4]:render_raw(filtered,"raw")
