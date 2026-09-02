import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import main


class LinkedInEmailWorkflowTests(unittest.TestCase):
    """Exercise the LinkedIn email parsing workflow and its data-handling helpers."""

    def test_extract_email_lines_strips_blank_lines(self):
        """Ensure blank lines are removed while preserving meaningful email content.

        Returns:
            None. The test asserts on the cleaned line list.
        """
        content = "\n\nSubject: Developer at Acme\n  Role: Senior Engineer\n\n"

        self.assertEqual(main.extract_email_lines(content), ["Subject: Developer at Acme", "Role: Senior Engineer"])

    def test_parse_email_content_extracts_multiple_jobs_from_fixture(self):
        """Parse a real sample email fixture into multiple job records.

        Returns:
            None. The test validates the parsed title, company, location, and URL.
        """
        fixture_path = Path(__file__).resolve().parent / "inputs" / "recent_linkedin_email_lines.json"
        with fixture_path.open("r", encoding="utf-8") as handle:
            samples = json.load(handle)

        parsed_jobs = main.parse_email_content("\n".join(samples[0]["lines"]))

        self.assertGreaterEqual(len(parsed_jobs), 2)
        self.assertEqual(parsed_jobs[0]["title"], "Senior Director Credit Risk Manager")
        self.assertEqual(parsed_jobs[0]["company"], "Morgan McKinley")
        self.assertEqual(parsed_jobs[0]["location"], "London Area, United Kingdom")
        self.assertIn("https://www.linkedin.com", parsed_jobs[0]["url"])
        self.assertIn("extra information", parsed_jobs[0])

    def test_parse_email_content_handles_all_recent_fixtures(self):
        """Ensure each recorded fixture parses into at least one valid job record.

        Returns:
            None. The test asserts that every fixture yields valid job fields.
        """
        fixture_path = Path(__file__).resolve().parent / "inputs" / "recent_linkedin_email_lines.json"
        with fixture_path.open("r", encoding="utf-8") as handle:
            samples = json.load(handle)

        self.assertEqual(len(samples), 5)

        for sample in samples:
            parsed_jobs = main.parse_email_content("\n".join(sample["lines"]))
            self.assertTrue(parsed_jobs, f"Expected at least one parsed job for {sample['subject']}")
            for parsed_job in parsed_jobs:
                self.assertTrue(parsed_job.get("title"))
                self.assertTrue(parsed_job.get("company"))
                self.assertTrue(parsed_job.get("location"))
                self.assertTrue(parsed_job.get("url"))

    def test_merge_jobs_appends_only_new_entries(self):
        """Ensure merge_jobs only adds new IDs while preserving existing records.

        Returns:
            None. The test validates deduplicated merge behavior.
        """
        existing = [{"id": "job-1", "title": "Existing Role"}]
        incoming = [
            {"id": "job-2", "title": "New Role"},
            {"id": "job-1", "title": "Existing Role"},
        ]

        merged = main.merge_jobs(existing, incoming)

        self.assertEqual(len(merged), 2)
        self.assertEqual([job["id"] for job in merged], ["job-1", "job-2"])

    def test_persist_jobs_writes_json_file(self):
        """Write job records to disk as JSON and preserve their content.

        Returns:
            None. The test verifies the saved JSON matches the input jobs.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "jobs.json")
            jobs = [{"id": "job-1", "title": "Engineeer"}]

            main.persist_jobs(path, jobs)

            with open(path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)

            self.assertEqual(saved, jobs)

    def test_is_message_in_date_range_uses_inclusive_bounds(self):
        """Check inclusive date-range filtering for Gmail message age.

        Returns:
            None. The test asserts the date boundary behavior.
        """
        message = {"internalDate": "1718832000000"}

        self.assertTrue(main.is_message_in_date_range(message, date_from=date(2024, 6, 1), date_to=date(2024, 6, 30)))
        self.assertFalse(main.is_message_in_date_range(message, date_from=date(2024, 6, 30), date_to=date(2024, 6, 30)))
        self.assertFalse(main.is_message_in_date_range(message, date_from=date(2024, 6, 1), date_to=date(2024, 6, 2)))


if __name__ == "__main__":
    unittest.main()
