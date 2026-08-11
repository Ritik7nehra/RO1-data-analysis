"""Robust workbook loading, cleaning, validation, and patient-visit analysis."""
from __future__ import annotations
from io import BytesIO
import re
import unicodedata
from typing import Any, Iterable
import numpy as np
import pandas as pd

MISSING_TOKENS = {"", "na", "n/a", "nan", "none", "null", "missing", "not available", "not applicable", "unknown", "-", "--"}
META_COLUMNS = {"Patient ID", "Event Name", "Visit", "Visit Date", "Source Sheet", "Source Row", "Duplicate Patient-Visit"}
BASE_SHEET_HINTS = ("base", "master", "raw", "all data", "alldata", "full data", "source")
DEFAULT_METRIC_PRIORITY = ["HbA1c", "Calculated BMI", "Mean Weight (kg)", "Mean SBP", "Mean DBP", "Finger Stick Blood Glucose (mg/dL)", "Age", "Mean Waist (cm)", "Mean Hip (cm)", "Waist Hip Ratio", "Average HbA1c"]

def _plain_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)): return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value)).replace("\n", " ").replace("\r", " ").strip())

def _header_signature(value: Any) -> str:
    s = _plain_text(value).replace("&", " and ")
    s = re.sub(r"\.\d+$", "", s); s = re.sub(r"[_\-/]+", " ", s); s = re.sub(r"[():,;?]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()

def canonical_column_name(value: Any) -> str:
    raw = _plain_text(value)
    if not raw or raw.lower().startswith("unnamed:"): return ""
    s = _header_signature(raw)
    if re.fullmatch(r"(record|study|patient|subject)\s*(id|identifier)", s): return "Patient ID"
    if re.fullmatch(r"(event|visit)\s*(name|label|stage)?", s): return "Event Name"
    if re.fullmatch(r"(date\s*of\s*birth|dob)\d*", s): return "Date of Birth"
    if s in {"age", "age at visit"}: return "Age"
    if s in {"bmi", "calculated bmi"}: return "Calculated BMI"
    if s in {"mean sbp", "systolic blood pressure", "systolic bp"}: return "Mean SBP"
    if s in {"mean dbp", "diastolic blood pressure", "diastolic bp"}: return "Mean DBP"
    if s in {"mean hr", "mean heart rate", "heart rate"}: return "Mean HR"
    if s == "waist hip ratio": return "Waist Hip Ratio"
    if s == "use of cgm": return "Use of CGM"
    if s == "pump": return "Pump"
    if "date" in s and "visit" in s and not any(x in s for x in ("birth", "diagnos", "collection", "start", "stop")): return "Visit Date"
    if ("hba1c" in s or "a1c" in s) and "control" not in s:
        if "avg" in s or "average" in s: return "Average HbA1c"
        if "reading" in s and "year" in s: return "Readings per year before Visit1"
        if s in {"hba1c", "a1c", "hba1c value", "a1c value"}: return "HbA1c"
    if "finger" in s and "glucose" in s: return "Finger Stick Blood Glucose (mg/dL)"
    if "mean" in s and "height" in s: return "Mean Height (cm)"
    if "weight" in s and "pregnan" not in s and ("mean" in s or s in {"weight", "weight kg"}): return "Mean Weight (kg)"
    if "mean" in s and "waist" in s and "ratio" not in s: return "Mean Waist (cm)"
    if "mean" in s and "hip" in s and "ratio" not in s: return "Mean Hip (cm)"
    return re.sub(r"\s*:\s*$", "", re.sub(r"\s+", " ", raw)).strip()

def normalize_visit_label(value: Any, fallback: Any = None) -> str | None:
    raw = _plain_text(value) or _plain_text(fallback)
    if not raw: return None
    text = re.sub(r"[_-]+", " ", raw.lower().replace("@", "2")).replace("baseline", "visit 1")
    compact = re.sub(r"[^a-z0-9]+", "", text)
    if re.search(r"(?:visit|v)?1\s*(?:&|and|\+|/)\s*(?:visit|v)?1a", text) or compact in {"visit1and1a", "visit11a", "v1and1a", "v11a"}: return "V1/V1A"
    if re.search(r"(?:visit|v)\s*1a\b", text) or compact in {"1a", "v1a", "visit1a"}: return "V1A"
    m = re.search(r"(?:visit|v)\s*0*([1-9]\d*)\b", text)
    if not m and compact.isdigit(): m = re.match(r"0*([1-9]\d*)", compact)
    return f"V{int(m.group(1))}" if m else None

def visit_sort_key(label: Any) -> tuple[float, str]:
    v = _plain_text(label).upper()
    if v == "V1/V1A": return (1.0, v)
    if v == "V1A": return (1.1, v)
    m = re.fullmatch(r"V(\d+)", v)
    return (float(m.group(1)), v) if m else (999.0, v)

def ordered_visits(values: Iterable[Any]) -> list[str]: return sorted({_plain_text(v) for v in values if _plain_text(v)}, key=visit_sort_key)

def normalize_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == "object": out[c] = out[c].map(lambda v: pd.NA if v is None or (isinstance(v, str) and _plain_text(v).lower() in MISSING_TOKENS) else (_plain_text(v) if isinstance(v, str) else v))
    return out

def _normalise_patient_id(value: Any) -> Any:
    if value is None or pd.isna(value): return pd.NA
    if isinstance(value, (int, np.integer)): return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer(): return str(int(value))
    text = _plain_text(value); return text if text else pd.NA

def coalesce_and_canonicalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    groups = {}
    for i, col in enumerate(df.columns): groups.setdefault(canonical_column_name(col) or f"Unnamed column {i+1}", []).append(i)
    out = {}; mappings = []; conflict_total = 0
    for canonical, indices in groups.items():
        block = df.iloc[:, indices]; conflicts = 0
        if len(indices) > 1: conflicts = int(block.apply(lambda r: len({_plain_text(v) for v in r if not pd.isna(v)}) > 1, axis=1).sum())
        conflict_total += conflicts
        if len(indices) == 1: names = [canonical]; out[canonical] = block.iloc[:, 0]; coal = False
        elif conflicts == 0: out[canonical] = block.bfill(axis=1).iloc[:, 0]; names = [canonical] * len(indices); coal = True
        else:
            names = []
            for pos, idx in enumerate(indices, 1):
                name = canonical if pos == 1 else f"{canonical} [{pos}]"; names.append(name); out[name] = df.iloc[:, idx]
            coal = False
        for pos, idx in enumerate(indices): mappings.append({"Original Column": _plain_text(df.columns[idx]), "Canonical Column": names[pos], "Changed": _plain_text(df.columns[idx]) != names[pos], "Coalesced": coal, "Conflicting Rows": conflicts})
    return pd.DataFrame(out), pd.DataFrame(mappings), conflict_total

def convert_inferred_types(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c == "Patient ID": out[c] = out[c].map(_normalise_patient_id); continue
        if pd.api.types.is_numeric_dtype(out[c]) or pd.api.types.is_datetime64_any_dtype(out[c]): continue
        non_null = out[c].dropna()
        if non_null.empty: continue
        sig = _header_signature(c)
        if "date" in sig:
            parsed = pd.to_datetime(out[c], errors="coerce")
            if parsed.notna().sum() / len(non_null) >= .8: out[c] = parsed; continue
        cleaned = out[c].astype("string").str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.replace(r"^\s*[<>]\s*", "", regex=True)
        numeric = pd.to_numeric(cleaned, errors="coerce")
        if numeric.notna().sum() / len(non_null) >= .85: out[c] = numeric
    return out

def _is_base_sheet(name: str) -> bool:
    s = _plain_text(name).lower().replace("_", " "); return any(h in s for h in BASE_SHEET_HINTS)

def load_clinical_workbook(file_bytes: bytes, file_name: str | None = None) -> dict[str, Any]:
    xls = pd.ExcelFile(BytesIO(file_bytes), engine="openpyxl"); sheets = xls.sheet_names
    visit_sheet_names = [s for s in sheets if normalize_visit_label(s)]
    frames = []; sheet_rows = []; excluded = []; warnings = []; maps = []; conflict_total = 0
    for sheet in sheets:
        try: raw = pd.read_excel(xls, sheet_name=sheet)
        except Exception as exc: warnings.append(f"Could not read sheet '{sheet}': {exc}"); continue
        raw = raw.dropna(how="all")
        if raw.empty: excluded.append({"Sheet": sheet, "Reason": "Empty sheet"}); continue
        cleaned, mapping, conflicts = coalesce_and_canonicalize_columns(raw); maps.append(mapping); conflict_total += conflicts
        cleaned = normalize_missing_values(cleaned); sheet_visit = normalize_visit_label(sheet)
        if _is_base_sheet(sheet) and visit_sheet_names: excluded.append({"Sheet": sheet, "Reason": "Base sheet skipped because visit sheets were detected"}); continue
        if "Patient ID" not in cleaned.columns or ("Event Name" not in cleaned.columns and "Visit" not in cleaned.columns and not sheet_visit): excluded.append({"Sheet": sheet, "Reason": "No Patient ID and visit/event information"}); continue
        cleaned["Source Sheet"] = sheet; cleaned["Source Row"] = np.arange(2, len(cleaned) + 2)
        if "Event Name" not in cleaned.columns: cleaned["Event Name"] = pd.NA
        if "Visit" in cleaned.columns: cleaned["Visit"] = cleaned["Visit"].map(lambda x: normalize_visit_label(x, sheet_visit))
        else: cleaned["Visit"] = cleaned["Event Name"].map(lambda x: normalize_visit_label(x, sheet_visit))
        if sheet_visit: cleaned["Visit"] = cleaned["Visit"].fillna(sheet_visit)
        if "Visit Date" in cleaned.columns: cleaned["Visit Date"] = pd.to_datetime(cleaned["Visit Date"], errors="coerce")
        cleaned = convert_inferred_types(cleaned); cleaned["Patient ID"] = cleaned["Patient ID"].map(_normalise_patient_id)
        frames.append(cleaned); sheet_rows.append({"Sheet": sheet, "Rows loaded": len(cleaned), "Visit labels": ", ".join(ordered_visits(cleaned["Visit"])) or "Unrecognized"})
    if not frames: raise ValueError("No usable worksheet was found. A sheet must contain Patient ID plus a visit/event label.")
    data = pd.concat(frames, ignore_index=True, sort=False); data = data[data["Visit"].notna()].reset_index(drop=True)
    if data.empty: raise ValueError("No rows have a recognizable visit label.")
    key = data["Patient ID"].notna(); data["Duplicate Patient-Visit"] = False; data.loc[key, "Duplicate Patient-Visit"] = data.loc[key].duplicated(["Patient ID", "Visit"], keep=False)
    mapping_df = pd.concat(maps, ignore_index=True) if maps else pd.DataFrame()
    quality = {"Rows": int(len(data)), "Unique Patients": int(data["Patient ID"].nunique(dropna=True)), "Unique Patient-Visits": int(data.loc[key, ["Patient ID", "Visit"]].drop_duplicates().shape[0]), "Missing Patient IDs": int(data["Patient ID"].isna().sum()), "Duplicate Patient-Visit Rows": int(data.loc[key].duplicated(["Patient ID", "Visit"], keep=False).sum()), "Visit Date Coverage %": float(data["Visit Date"].notna().mean() * 100) if "Visit Date" in data else 0.0, "Column Conflicts During Coalescing": int(conflict_total)}
    return {"data": data, "sheet_summary": pd.DataFrame(sheet_rows), "excluded_sheets": pd.DataFrame(excluded), "warnings": warnings, "column_mappings": mapping_df, "quality": quality, "file_name": file_name or "uploaded workbook"}

def numeric_metric_columns(data: pd.DataFrame) -> list[str]:
    cols = [c for c in data.columns if c not in META_COLUMNS and pd.api.types.is_numeric_dtype(data[c])]
    return sorted(cols, key=lambda c: (DEFAULT_METRIC_PRIORITY.index(c) if c in DEFAULT_METRIC_PRIORITY else 999, c.lower()))

def suggested_metrics(data: pd.DataFrame, limit: int = 6) -> list[str]: return numeric_metric_columns(data)[:limit]

def patient_visit_level(data: pd.DataFrame, metrics: Iterable[str] | None = None) -> pd.DataFrame:
    if not {"Patient ID", "Visit"}.issubset(data.columns): return data.copy()
    frame = data.dropna(subset=["Patient ID", "Visit"]).copy(); metrics = [m for m in (metrics or numeric_metric_columns(frame)) if m in frame.columns]
    if not metrics: return frame.drop_duplicates(["Patient ID", "Visit"])
    agg = {m: "mean" for m in metrics};
    if "Visit Date" in frame: agg["Visit Date"] = "min"
    return frame.groupby(["Patient ID", "Visit"], as_index=False).agg(agg)

def deduplicate_patient_visits(data: pd.DataFrame, strategy: str = "Most complete") -> pd.DataFrame:
    if not {"Patient ID", "Visit"}.issubset(data.columns) or strategy == "Keep all": return data.copy()
    if strategy == "Average numeric duplicates": return patient_visit_level(data)
    frame = data.copy(); numeric = numeric_metric_columns(frame); frame["_completeness"] = frame[numeric].notna().sum(axis=1) if numeric else 0
    sort_cols = ["Patient ID", "Visit", "_completeness"] + (["Source Row"] if "Source Row" in frame else [])
    frame = frame.sort_values(sort_cols, ascending=[True, True, False] + ([True] if "Source Row" in frame else []), na_position="last")
    keyed = frame.drop_duplicates(["Patient ID", "Visit"], keep="first").drop(columns="_completeness"); missing = data[data["Patient ID"].isna()].copy()
    return pd.concat([keyed, missing], ignore_index=True, sort=False)

def filter_clinical_data(data: pd.DataFrame, selected_visits: list[str] | None = None, patient_search: str = "", sex_filter: list[str] | None = None) -> pd.DataFrame:
    out = data.copy()
    if selected_visits: out = out[out["Visit"].isin(selected_visits)]
    if patient_search.strip(): out = out[out["Patient ID"].astype("string").str.contains(patient_search.strip(), case=False, regex=False, na=False)]
    if sex_filter and "Sex" in out: out = out[out["Sex"].astype("string").isin(sex_filter)]
    return out

def completion_rate(data: pd.DataFrame, selected_visits: list[str]) -> float:
    if not selected_visits or not {"Patient ID", "Visit"}.issubset(data.columns): return 0.0
    patients = data["Patient ID"].dropna().unique(); expected = len(patients) * len(selected_visits)
    if expected == 0: return 0.0
    observed = data.dropna(subset=["Patient ID"]).loc[data["Visit"].isin(selected_visits)].drop_duplicates(["Patient ID", "Visit"]).shape[0]
    return observed / expected * 100

def missingness_table(data: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    rows = []
    for c in columns:
        if c not in data: continue
        total = len(data); missing = int(data[c].isna().sum()); rows.append({"Column": c, "Missing": missing, "Total": total, "Missing %": missing / total * 100 if total else 0.0})
    return pd.DataFrame(rows).sort_values("Missing %", ascending=False).reset_index(drop=True) if rows else pd.DataFrame(columns=["Column", "Missing", "Total", "Missing %"])

def summary_statistics(data: pd.DataFrame, metrics: Iterable[str]) -> pd.DataFrame:
    rows = []
    for metric in metrics:
        if metric not in data: continue
        for visit in ordered_visits(data["Visit"]):
            values = pd.to_numeric(data.loc[data["Visit"] == visit, metric], errors="coerce").dropna()
            if values.empty: continue
            rows.append({"Metric": metric, "Visit": visit, "N": int(len(values)), "Mean": float(values.mean()), "Median": float(values.median()), "SD": float(values.std(ddof=1)) if len(values) > 1 else np.nan})
    return pd.DataFrame(rows)

def dataframe_to_excel_bytes(data: pd.DataFrame, sheet_name: str = "Data") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer: data.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return output.getvalue()
