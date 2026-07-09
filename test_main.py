import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone

import main


class LinkedInEmailWorkflowTests(unittest.TestCase):
    def test_parse_email_content_extracts_key_fields(self):
        sample_email = """
        Subject: Software Engineer at Acme Corp
        Hello,
        We thought you'd be interested in this opportunity:
        Role: Senior Backend Engineer
        Location: Remote, US
        Salary: $180k-$220k
        Apply here: https://www.linkedin.com/jobs/view/123456789
        """

        parsed = main.parse_email_content(sample_email)

        self.assertEqual(parsed["title"], "Senior Backend Engineer")
        self.assertEqual(parsed["company"], "Acme Corp")
        self.assertEqual(parsed["location"], "Remote, US")
        self.assertEqual(parsed["salary"], "$180k-$220k")
        self.assertEqual(parsed["url"], "https://www.linkedin.com/jobs/view/123456789")

    def test_merge_jobs_appends_only_new_entries(self):
        existing = [{"id": "job-1", "title": "Existing Role"}]
        incoming = [
            {"id": "job-2", "title": "New Role"},
            {"id": "job-1", "title": "Existing Role"},
        ]

        merged = main.merge_jobs(existing, incoming)

        self.assertEqual(len(merged), 2)
        self.assertEqual([job["id"] for job in merged], ["job-1", "job-2"])

    def test_persist_jobs_writes_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "jobs.json")
            jobs = [{"id": "job-1", "title": "Engineeer"}]

            main.persist_jobs(path, jobs)

            with open(path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)

            self.assertEqual(saved, jobs)

    def test_is_message_recent_enough_uses_cutoff_date(self):
        message = {"internalDate": "1718832000000"}

        self.assertTrue(main.is_message_recent_enough(message, date(2024, 6, 1)))
        self.assertFalse(main.is_message_recent_enough(message, date(2024, 7, 1)))


if __name__ == "__main__":
    unittest.main()
