# Clinical Patient Visit Dashboard

A local Streamlit dashboard for longitudinal analysis of deidentified clinical data stored across separate Excel visit sheets.

The supplied workbook is bundled in `data/R_Deidentified_R01_.xlsx`, so the dashboard opens with the study data immediately. A different `.xlsx` or `.xlsm` workbook can also be uploaded from the sidebar.

## Verified profile of the bundled workbook

- Visit sheets detected: `Visit_1`, `Visit_2`, `Visit_3`, `visit_4`
- Reference sheet detected: `Base_File`
- Patient identifier: `Record ID`, standardized internally as `Patient ID`
- Visit records loaded: **797**
- Unique patients: **256**
- Duplicate patient–visit rows: **0**
- Normalized visit stages: `V1/V1A`, `V2`, `V3`, `V4`
- Visit dates are recovered from the appropriate date fields in `Base_File` and joined using patient ID plus visit stage.

The source Excel workbook is never edited by the application.

## Run the dashboard

### 1. Create a virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Start Streamlit

```bash
streamlit run app.py
```

You can also use `run_dashboard.bat` on Windows or `./run_dashboard.sh` on macOS/Linux after installing the dependencies.

## Dashboard pages

### Overview

- Total patients and patient-visits
- Visit completion rate
- Missingness across selected clinical variables
- Visit counts
- Mean, median, standard deviation, and sample size grouped by visit
- Workbook, sheet, duplicate, date-coverage, and column-normalization audit

### Trends

- Population mean with a 95% confidence band
- Population median with an interquartile band
- Individual-patient longitudinal trends
- Interactive line or area chart

### Comparisons

- Paired patient comparison between any two visits
- Baseline and follow-up mean or median
- Absolute and relative change indicators
- Paired scatter plot
- Distribution of patient-level change
- Box plots and histograms by visit

### Raw Data

- Searchable and filterable longitudinal table
- User-selected columns
- Excel and CSV export
- Excel export includes summary statistics and a data-quality sheet

## Workbook auto-detection

The loader recognizes visit-sheet labels such as:

- `V1`, `v1`, `Visit_1`
- `V1A`, `visit 1a`
- `Visit 1 & 1a`
- `V2`, `Visit_2`, and the common typo `V@`
- `V3`, `v4`, and later numbered visits

Where available, the row-level `Event Name` value takes priority over the sheet name. This allows a single sheet to contain a combined `Visit 1 & 1a` stage while still receiving the correct normalized label.

## Column-name configuration

Common clinical names are standardized in `data_utils.py` through:

- `CANONICAL_COLUMN_PATTERNS`
- `canonical_column_name()`
- `DEFAULT_METRIC_PRIORITY`

The current workbook is already mapped for:

- `Record ID` → `Patient ID`
- `Age at Visit`, `AGE`, `Age` → `Age`
- baseline and follow-up HbA1c labels → `HbA1c`
- height, weight, BMI, waist, hip, SBP, DBP, and finger-stick glucose aliases

To support a future field with a new label, add a regex/canonical-name pair to `CANONICAL_COLUMN_PATTERNS`, or add a small condition inside `canonical_column_name()`.

## Data-quality behavior

- Empty strings and common missing-value tokens are treated as missing.
- Patient IDs are converted to trimmed strings.
- Dates and numeric fields are inferred conservatively.
- Duplicate patient–visit rows are flagged and shown in the audit.
- Dashboard calculations can keep all duplicate rows, retain the most complete row, or combine first non-missing values.
- Columns that normalize to the same label are coalesced only when values agree.
- Conflicting duplicate fields are preserved as numbered columns instead of being overwritten.
- The original source sheet and row number remain available for traceability.

## Privacy

The application is designed for deidentified study data. It processes the workbook in memory and does not write changes back to the uploaded source file. When deploying beyond a local computer, use an approved secure environment and follow the study’s data-governance requirements.
