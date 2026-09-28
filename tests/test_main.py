import base64
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import main
from google.auth.exceptions import RefreshError


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

    def test_parse_email_content_ignores_subject_metadata_before_job_block(self):
        """Do not turn a reminder email subject into a job record."""
        content = "\n".join(
            [
                "Subject: New jobs similar to Senior Lead - Reporting, Analytics and AI at RES",
                "Jobs similar to Senior Lead - Reporting, Analytics and AI at RES",
                "View job: https://www.linkedin.com/comm/jobs/view/4461543492",
                "---------------------------------------------------------",
                "Senior Lead - Reporting, Analytics and AI",
                "RES",
                "Cambridge",
                "View job: https://www.linkedin.com/comm/jobs/view/4462414313",
            ]
        )

        parsed_jobs = main.parse_email_content(content)

        self.assertEqual(len(parsed_jobs), 1)
        self.assertEqual(parsed_jobs[0]["title"], "Senior Lead - Reporting, Analytics and AI")
        self.assertEqual(parsed_jobs[0]["company"], "RES")

    def test_parse_email_content_ignores_jobs_similar_metadata_from_downloaded_email(self):
        """Parse genuine jobs after the leading reminder metadata line."""
        fixture_path = Path(__file__).resolve().parent / "inputs" / "risk_finance_leader_reminder_2026-09-07.json"
        with fixture_path.open("r", encoding="utf-8") as handle:
            sample = json.load(handle)

        parsed_jobs = main.parse_email_content("\n".join(sample["lines"]))

        self.assertEqual(parsed_jobs[0]["title"], "Head of Credit Risk")
        self.assertEqual(parsed_jobs[0]["company"], "Abound")
        self.assertNotIn("Jobs similar to", parsed_jobs[0]["title"])

    def test_parse_email_content_skips_no_results_similar_jobs_banner(self):
        """Extract listings only after a similar-jobs no-results banner."""
        content = "\n".join(
            [
                "Subject: Jobs similar to your alert",
                "Jobs similar to your alert",
                "There were no results for your alert, but these similar jobs "
                "may be a fit. Manage alert:",
                "https://www.linkedin.com/comm/jobs/alerts/?alert=123",
                "Director, Credit Risk",
                "Airwallex",
                "London",
                "View job: https://www.linkedin.com/comm/jobs/view/4458429721",
                "---------------------------------------------------------",
                "Head of Risk Operations",
                "Airwallex",
                "London",
                "View job: https://www.linkedin.com/comm/jobs/view/4448786713",
                "See all jobs on LinkedIn",
            ]
        )

        parsed_jobs = main.parse_email_content(content)

        self.assertEqual(
            [job["title"] for job in parsed_jobs],
            ["Director, Credit Risk", "Head of Risk Operations"],
        )
        self.assertTrue(all(job["company"] == "Airwallex" for job in parsed_jobs))

    def test_parse_email_content_skips_your_job_alert_header(self):
        """Do not parse a job-alert header or intro as a listing."""
        content = "\n".join(
            [
                "Subject: Senior Credit Analyst at Lendable",
                "Your job alert for Senior Credit Risk Manager in London",
                "A new job matches your preferences.",
                "Senior Credit Analyst",
                "Lendable",
                "London",
                "View job: https://www.linkedin.com/comm/jobs/view/4431908771",
                "---------------------------------------------------------",
                "Head of Decision Science",
                "Secure Trust Bank",
                "Kidderminster",
                "View job: https://www.linkedin.com/comm/jobs/view/4471634220",
                "See all jobs on LinkedIn",
            ]
        )

        parsed_jobs = main.parse_email_content(content)

        self.assertEqual(
            [job["title"] for job in parsed_jobs],
            ["Senior Credit Analyst", "Head of Decision Science"],
        )
        self.assertEqual(parsed_jobs[0]["company"], "Lendable")

    def test_run_workflow_excludes_saved_job_reminder_email(self):
        """Do not add jobs from the supplied saved-job reminder message."""
        body_text = "Your saved job at Monzo is still available.\nLinkedIn"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()
        message = {
            "id": "1a0822706bd12c79",
            "internalDate": "1788889983000",
            "payload": {
                "headers": [
                    {
                        "name": "Subject",
                        "value": "LinkedIn job reminder",
                    }
                ],
                "mimeType": "text/plain",
                "body": {
                    "data": encoded_body,
                },
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir, \
                patch.object(main, "get_gmail_service", return_value="service"), \
                patch.object(main, "get_linkedin_messages", return_value=[message]), \
                patch.object(
                    main,
                    "get_gmail_label_ids",
                    return_value={
                        main.GMAIL_LABELS_TO_REVIEW[0]: "label-review",
                        main.GMAIL_LABEL_ONCE_REVIEWED: "label-reviewed",
                    },
                ), \
                patch.object(main, "mark_message_reviewed") as mark_reviewed:
            jobs = main.run_workflow(Path(tmpdir) / "jobs.json")

        self.assertEqual(jobs, [])
        mark_reviewed.assert_called_once_with(
            "service",
            "1a0822706bd12c79",
            ["label-review"],
            "label-reviewed",
        )

    def test_run_workflow_excludes_companies_on_ignore_list(self):
        """Do not add newly parsed jobs from ignored companies."""
        body_text = "LinkedIn job alert"
        message = {
            "id": "ignored-company-message",
            "internalDate": "1788889983000",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "New job alert"},
                ],
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(body_text.encode()).decode(),
                },
            },
        }
        parsed_job = {
            "title": "Senior Lead - Reporting, Analytics and AI",
            "company": "res",
            "location": "London",
            "url": "https://www.linkedin.com/jobs/view/123",
        }

        with tempfile.TemporaryDirectory() as tmpdir, \
                patch.object(main, "get_gmail_service", return_value="service"), \
                patch.object(main, "get_linkedin_messages", return_value=[message]), \
                patch.object(main, "parse_email_content", return_value=[parsed_job]), \
                patch.object(
                    main,
                    "get_gmail_label_ids",
                    return_value={
                        main.GMAIL_LABELS_TO_REVIEW[0]: "label-review",
                        main.GMAIL_LABEL_ONCE_REVIEWED: "label-reviewed",
                    },
                ), \
                patch.object(main, "mark_message_reviewed") as mark_reviewed:
            jobs = main.run_workflow(Path(tmpdir) / "jobs.json")

        self.assertEqual(jobs, [])
        mark_reviewed.assert_called_once()

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
        self.assertEqual(
            [job["id"] for job in merged],
            [main.make_job_id(existing[0]), main.make_job_id(incoming[0])],
        )

    def test_merge_jobs_deduplicates_same_job_at_different_urls(self):
        """Use title, company, and location rather than URL for job identity."""
        existing = [
            {
                "id": "old-id",
                "title": "Data Analyst",
                "company": "Acme",
                "location": "London",
                "url": "https://www.linkedin.com/jobs/view/1",
            }
        ]
        incoming = [
            {
                "title": "Data Analyst",
                "company": "Acme",
                "location": "London",
                "url": "https://www.linkedin.com/jobs/view/2",
            }
        ]

        merged = main.merge_jobs(existing, incoming)

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            merged[0]["id"],
            main.make_job_id(incoming[0]),
        )
        self.assertEqual(merged[0]["url"], existing[0]["url"])

    def test_merge_jobs_sets_reviewed_flag_for_new_jobs_only(self):
        """New jobs should default to not reviewed without altering existing values."""
        existing = [{"id": "job-1", "title": "Existing Role", "reviewed": "yes"}]
        incoming = [{"id": "job-2", "title": "New Role"}]

        merged = main.merge_jobs(existing, incoming)

        by_id = {job["id"]: job for job in merged}
        self.assertEqual(by_id[main.make_job_id(existing[0])]["reviewed"], "yes")
        self.assertEqual(by_id[main.make_job_id(incoming[0])]["reviewed"], "not reviewed")

    def test_merge_jobs_keeps_existing_job_text_unchanged(self):
        """Existing entries should be left alone; only brand-new jobs receive review defaults."""
        existing = [{"id": "job-1", "title": "Existing Role"}]
        incoming = [{"id": "job-2", "title": "New Role"}]

        merged = main.merge_jobs(existing, incoming)

        by_id = {job["id"]: job for job in merged}
        self.assertNotIn("reviewed", by_id[main.make_job_id(existing[0])])
        self.assertEqual(by_id[main.make_job_id(incoming[0])]["reviewed"], "not reviewed")

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

    def test_get_linkedin_messages_handles_no_matching_messages(self):
        """Treat Gmail's null messages response as an empty result."""
        class FakeMessages:
            def list(self, **kwargs):
                return self

            def execute(self):
                return {"messages": None}

        class FakeUsers:
            def messages(self):
                return FakeMessages()

        class FakeService:
            def users(self):
                return FakeUsers()

        messages = main.get_linkedin_messages(FakeService())

        self.assertEqual(messages, [])

    def test_get_linkedin_messages_requires_review_label(self):
        """Only request LinkedIn messages carrying a review label."""
        class FakeMessages:
            query = None

            def list(self, **kwargs):
                self.query = kwargs["q"]
                return self

            def execute(self):
                return {"messages": None}

        class FakeUsers:
            def __init__(self):
                self.message_resource = FakeMessages()

            def messages(self):
                return self.message_resource

        class FakeService:
            def __init__(self):
                self.user_resource = FakeUsers()

            def users(self):
                return self.user_resource

        service = FakeService()
        main.get_linkedin_messages(service)

        self.assertIn('label:"Linkedin to review"', service.user_resource.message_resource.query)

    def test_get_gmail_label_ids_creates_missing_labels(self):
        """Create configured labels when Gmail does not have them yet."""
        service = MagicMock()
        service.users().labels().list().execute.return_value = {"labels": []}
        service.users().labels().create.side_effect = [
            MagicMock(execute=MagicMock(return_value={"id": "label-review"})),
            MagicMock(execute=MagicMock(return_value={"id": "label-reviewed"})),
        ]

        label_ids = main.get_gmail_label_ids(
            service,
            ["Linkedin to review", "Linkedin reviewed"],
        )

        self.assertEqual(
            label_ids,
            {
                "Linkedin to review": "label-review",
                "Linkedin reviewed": "label-reviewed",
            },
        )
        self.assertEqual(service.users().labels().create.call_count, 2)

    def test_get_gmail_label_ids_matches_labels_case_insensitively(self):
        """Reuse existing labels when Gmail capitalizes their names differently."""
        service = MagicMock()
        service.users().labels().list().execute.return_value = {
            "labels": [
                {"name": "LinkedIn to review", "id": "label-review"},
                {"name": "LinkedIn reviewed", "id": "label-reviewed"},
            ]
        }

        label_ids = main.get_gmail_label_ids(
            service,
            ["Linkedin to review", "Linkedin reviewed"],
        )

        self.assertEqual(
            label_ids,
            {
                "Linkedin to review": "label-review",
                "Linkedin reviewed": "label-reviewed",
            },
        )
        service.users().labels().create.assert_not_called()

    def test_get_gmail_service_reauthenticates_after_refresh_error(self):
        """Ensure stale refresh tokens trigger a fresh OAuth flow automatically."""
        class FakeCredentials:
            expired = True
            valid = False
            refresh_token = "stale_refresh_token"

            def refresh(self, request):
                raise RefreshError("invalid_grant")

            def to_json(self):
                return '{"token": "fresh"}'

        fake_creds = FakeCredentials()

        temp_dir = Path(tempfile.mkdtemp())
        token_path = temp_dir / "token.json"
        token_path.write_text("{\"stale\": true}", encoding="utf-8")

        with patch.object(main, "BASE_DIR", temp_dir), \
             patch.object(main, "SCOPES", ["scope"]), \
             patch.object(main.Credentials, "from_authorized_user_file", return_value=fake_creds), \
             patch.object(main.InstalledAppFlow, "from_client_secrets_file") as flow_factory, \
             patch.object(main, "build", return_value="service") as build_mock:
            flow = type("Flow", (), {"run_local_server": lambda self, port=0: fake_creds})()
            flow_factory.return_value = flow
            service = main.get_gmail_service()

        self.assertEqual(service, "service")
        build_mock.assert_called_once_with("gmail", "v1", credentials=fake_creds)
        self.assertTrue(token_path.exists())


if __name__ == "__main__":
    unittest.main()
