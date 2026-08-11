import unittest
from io import BytesIO

import pandas as pd

from data_utils import (
    completion_rate,
    load_clinical_workbook,
    normalize_visit_label,
    patient_visit_level,
)


class DataUtilsTests(unittest.TestCase):
    def test_visit_normalization(self):
        self.assertEqual(normalize_visit_label("Visit 1"), "V1")
        self.assertEqual(normalize_visit_label("Visit 1 & 1A"), "V1/V1A")
        self.assertEqual(normalize_visit_label("V@"), "V2")
        self.assertEqual(normalize_visit_label("visit 4"), "V4")

    def test_completion_rate_counts_unique_patient_visits(self):
        data = pd.DataFrame({
            "Patient ID": ["1", "1", "1", "2"],
            "Visit": ["V1", "V1", "V2", "V1"],
            "HbA1c": [7.0, 7.1, 6.8, 8.0],
        })
        self.assertAlmostEqual(completion_rate(data, ["V1", "V2"]), 75.0)

    def test_patient_visit_level_prevents_duplicate_weighting(self):
        data = pd.DataFrame({
            "Patient ID": ["1", "1", "2"],
            "Visit": ["V1", "V1", "V1"],
            "HbA1c": [6.0, 8.0, 7.0],
        })
        result = patient_visit_level(data, ["HbA1c"])
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(float(result.loc[result["Patient ID"] == "1", "HbA1c"].iloc[0]), 7.0)

    def test_workbook_loader_uses_sheet_visit_when_event_is_missing(self):
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame({"Patient ID": ["1", "2"], "HbA1c": [7.0, 8.0]}).to_excel(writer, index=False, sheet_name="V1")
            pd.DataFrame({"Patient ID": ["1"], "HbA1c": [6.5]}).to_excel(writer, index=False, sheet_name="V2")
        bundle = load_clinical_workbook(output.getvalue(), "test.xlsx")
        self.assertEqual(set(bundle["data"]["Visit"]), {"V1", "V2"})
        self.assertEqual(bundle["quality"]["Unique Patients"], 2)


if __name__ == "__main__":
    unittest.main()
