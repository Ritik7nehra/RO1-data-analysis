# Clinical Patient Visit Dashboard

A Streamlit dashboard for longitudinal analysis of deidentified clinical data stored across separate Excel visit sheets.

The dashboard can load `.xlsx` or `.xlsm` workbooks from the sidebar. The current repository does not require the source workbook to be committed; this keeps the deidentified study file separate from the application code.

## Verified validation

The included validation report records a successful workbook validation:

- Visit records: **797**
- Unique patients: **256**
- Unique patient-visits: **797**
- Duplicate patient-visit rows: **0**
- Normalized visit stages: `V1/V1A`, `V2`, `V3`, `V4`
- Visit-date coverage: **91.719%**
- Default metrics: HbA1c, Calculated BMI, Mean Weight, Mean SBP, Mean DBP, and Finger Stick Blood Glucose
- Excel export test: **PASS**

See `validation_report.json` for the recorded validation results.

## Run locally

### 1. Create a virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Start the dashboard

```bash
streamlit run app.py
```

Then upload the clinical workbook from the sidebar.

## Dashboard

### Overview
- Patient and patient-visit counts
- Visit completion rate
- Missingness across selected clinical variables
- Visit counts
- Mean, median, standard deviation, and sample size by visit
- Workbook and data-quality audit

### Trends
- Population mean with a 95% confidence band
- Population median with an interquartile band
- Individual-patient longitudinal trends
- Line or area chart

### Comparisons
- Paired patient comparison between visits
- Baseline/follow-up mean or median
- Absolute and relative change
- Paired scatter plot
- Patient-level change distribution
- Box plots and histograms

### Raw Data
- Searchable filtered table
- User-selected columns
- Excel and CSV export
- Excel export with summary statistics and data-quality information

## Workbook auto-detection

The loader recognizes visit-sheet labels such as:

- `V1`, `v1`, `Visit_1`
- `V1A`, `visit 1a`
- `Visit 1 & 1a`
- `V2`, `Visit_2`, and the common typo `V@`
- `V3`, `v4`, and later numbered visits

When available, row-level `Event Name` values are used to determine the normalized visit stage. The original source sheet and source row are retained for traceability.

## Data-quality behavior

- Empty strings and common missing-value tokens are treated as missing.
- Patient IDs are normalized to strings.
- Dates and numeric fields are inferred conservatively.
- Duplicate patient-visit rows are flagged.
- Dashboard calculations can keep all duplicate rows, retain the most complete row, or combine first non-missing values.
- Duplicate columns are coalesced only when their values agree.
- Conflicting duplicate fields are preserved rather than overwritten.
- The uploaded source workbook is never modified.

## Privacy

The application is designed for deidentified study data. It processes the workbook in memory and does not write changes back to the uploaded source file. Use an approved secure environment and follow the study's data-governance requirements when handling research data.