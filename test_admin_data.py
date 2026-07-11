from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import admin_data
import clean_workbook
import server


class AdminDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sample_data.xlsx"
        self.output = self.root / "cleaned_data.xlsx"
        self.temp_output = self.root / "cleaned_data.tmp.xlsx"
        shutil.copyfile(admin_data.SOURCE, self.source)
        self.original_admin_source = admin_data.SOURCE
        self.original_clean_source = clean_workbook.SOURCE
        self.original_clean_output = clean_workbook.OUTPUT
        self.original_clean_temp = clean_workbook.TEMP_OUTPUT
        admin_data.SOURCE = self.source
        clean_workbook.SOURCE = self.source
        clean_workbook.OUTPUT = self.output
        clean_workbook.TEMP_OUTPUT = self.temp_output

    def tearDown(self) -> None:
        admin_data.SOURCE = self.original_admin_source
        clean_workbook.SOURCE = self.original_clean_source
        clean_workbook.OUTPUT = self.original_clean_output
        clean_workbook.TEMP_OUTPUT = self.original_clean_temp
        self.tempdir.cleanup()

    def test_add_record_updates_sample_and_cleaned_workbook(self) -> None:
        admin_data.apply_record_action(
            "Departments",
            "add",
            {
                "Department ID": "D999",
                "Department Name": "Admin Test Department",
                "Division": "Test",
                "Location": "Jeddah HQ",
                "Cost Center": "Admin Test",
                "Director": "Sanaa Waheeb",
                "Headcount": "1",
                "Annual Budget SAR": "1000",
            },
        )
        tables = server.parse_workbook(self.output)["tables"]
        created = next(row for row in tables["Departments"] if row["Department ID"] == "D999")
        self.assertEqual(created["Department Name"], "Admin Test Department")
        self.assertEqual(created["Headcount"], 1)

    def test_employee_id_is_generated_when_adding_employee(self) -> None:
        result = admin_data.apply_record_action(
            "Employees",
            "add",
            {
                "Employee ID": "",
                "Employee Name": "Generated Employee",
                "Email": "generated.employee@example.com",
                "Department ID": "D002",
                "Department": "Information Technology",
                "Job Title": "Software Engineer",
                "Level": "Specialist",
                "Manager": "Sanaa Waheeb",
                "Location": "Jeddah HQ",
                "Hire Date": "2026-07-08",
                "Employment Status": "Active",
            },
        )
        self.assertRegex(result["keyValue"], r"^E\d{4}$")
        tables = server.parse_workbook(self.output)["tables"]
        created = next(row for row in tables["Employees"] if row["Email"] == "generated.employee@example.com")
        self.assertEqual(created["Employee ID"], result["keyValue"])

    def test_required_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(admin_data.AdminDataError, "Please fill the required fields"):
            admin_data.apply_record_action(
                "Employees",
                "add",
                {
                    "Employee ID": "",
                    "Employee Name": "",
                    "Email": "",
                    "Department ID": "",
                    "Department": "",
                    "Job Title": "",
                    "Level": "",
                    "Manager": "",
                    "Location": "",
                    "Hire Date": "",
                    "Employment Status": "",
                },
            )


if __name__ == "__main__":
    unittest.main()
