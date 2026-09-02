"""Tests for the local job-review web server data boundary."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import web_server


class WebServerTests(unittest.TestCase):
    """Verify job API data operations without starting a network server."""

    def test_deduplicate_jobs_keeps_first_record(self):
        """Keep one record per ID and preserve the first duplicate."""
        jobs = [
            {"id": "job-1", "title": "First"},
            {"id": "job-1", "title": "Duplicate"},
            {"id": "job-2", "title": "Second"},
        ]

        result = web_server.deduplicate_jobs(jobs)

        self.assertEqual(result, [jobs[0], jobs[2]])

    def test_update_review_status_persists_only_requested_status(self):
        """Persist a review change while retaining the job's other fields."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            jobs_path = Path(temporary_directory) / "jobs.json"
            original_job = {"id": "job-1", "title": "Role", "reviewed": "no"}
            jobs_path.write_text(json.dumps([original_job]), encoding="utf-8")

            with patch.object(web_server, "JOBS_PATH", jobs_path):
                updated_job = web_server.update_review_status("job-1", "yes")

            saved_jobs = json.loads(jobs_path.read_text(encoding="utf-8"))

        self.assertEqual(updated_job["reviewed"], "yes")
        self.assertEqual(saved_jobs, [{"id": "job-1", "title": "Role", "reviewed": "yes"}])

    def test_update_review_status_returns_none_for_unknown_id(self):
        """Report a missing job without writing a new record."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            jobs_path = Path(temporary_directory) / "jobs.json"
            jobs_path.write_text("[]", encoding="utf-8")

            with patch.object(web_server, "JOBS_PATH", jobs_path):
                result = web_server.update_review_status("missing", "yes")

            self.assertIsNone(result)
            self.assertEqual(jobs_path.read_text(encoding="utf-8"), "[]")


if __name__ == "__main__":
    unittest.main()
