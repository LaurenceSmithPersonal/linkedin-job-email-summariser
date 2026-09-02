import base64
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
]


LINKEDIN_EMAIL_ADDRESSES = [
    "jobs-noreply@linkedin.com",
    "jobalerts-noreply@linkedin.com",
]


def get_gmail_service():
    """Create an authenticated Gmail API client for the current user.

    Returns:
        googleapiclient.discovery.Resource: A configured Gmail API resource that can
        be used to list and fetch messages in the authenticated account.
    """
    creds = None
    token_path = BASE_DIR / "token.json"
    credentials_path = BASE_DIR / "credentials.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Google can revoke or invalidate a saved refresh token. When that
            # happens, discard the stale token and start a fresh OAuth flow so the
            # user is prompted automatically for re-authentication.
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
                if token_path.exists():
                    token_path.unlink()
        if not creds or not creds.valid:
            # Otherwise, complete the OAuth flow and persist the resulting token
            # so future runs do not require re-authentication.
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with token_path.open("w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def extract_message_text(payload: dict[str, Any]) -> str:
    """Extract the readable plain text content from a Gmail message payload.

    Args:
        payload: A Gmail message payload dictionary, possibly containing nested
            multipart message parts.

    Returns:
        A string containing the text content decoded from the message body.
    """
    text_parts: list[str] = []

    if payload.get("mimeType", "").startswith("text/"):
        body_data = payload.get("body", {}).get("data")
        if body_data:
            decoded = base64.urlsafe_b64decode(body_data.encode("ascii")).decode("utf-8", errors="ignore")
            return decoded

    for part in payload.get("parts", []):
        part_text = extract_message_text(part)
        if part_text:
            text_parts.append(part_text)

    return "\n".join(text_parts).strip()


def is_message_in_date_range(
    message: dict[str, Any],
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
) -> bool:
    """Check whether a Gmail message falls within an inclusive date range.

    Args:
        message: A Gmail message dictionary returned by the API.
        date_from: The earliest accepted date. When omitted, there is no lower
            bound.
        date_to: The latest accepted date. When omitted, there is no upper bound.

    Returns:
        True if the message's internal date falls within the inclusive range,
        otherwise False.
    """
    internal_date = message.get("internalDate")
    if not internal_date:
        return False

    message_date = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc).date()

    if date_from is not None:
        date_from_value = date_from.date() if isinstance(date_from, datetime) else date_from
        if message_date < date_from_value:
            return False

    if date_to is not None:
        date_to_value = date_to.date() if isinstance(date_to, datetime) else date_to
        if message_date > date_to_value:
            return False

    return True


def get_linkedin_messages(
    service,
    limit: int = 10,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
) -> list[dict[str, Any]]:
    """Fetch LinkedIn job-alert messages from Gmail within an inclusive date range.

    Args:
        service: An authenticated Gmail API service object.
        limit: Maximum number of messages to return after filtering and sorting.
        date_from: Earliest date to include. Messages before this date are
            excluded.
        date_to: Latest date to include. Messages after this date are excluded.

    Returns:
        A list of Gmail message dictionaries for LinkedIn job alerts, sorted from
        newest to oldest and limited to ``limit`` entries.
    """
    sender_filter = " OR ".join(f"from:({address})" for address in LINKEDIN_EMAIL_ADDRESSES)
    query = f"({sender_filter})"
    response = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    message_refs = response.get("messages", [])
    messages: list[dict[str, Any]] = []

    for message_ref in message_refs:
        # Fetch each message in full so we can evaluate the message date and
        # apply the explicit date-range filter before returning results.
        message = service.users().messages().get(userId="me", id=message_ref["id"], format="full").execute()
        if is_message_in_date_range(message, date_from=date_from, date_to=date_to):
            messages.append(message)

    messages.sort(key=lambda item: int(item.get("internalDate", "0")), reverse=True)
    return messages[:limit]


def extract_email_lines(content: str) -> list[str]:
    """Return the non-empty lines from an email body with surrounding whitespace removed.

    Args:
        content: Raw email text as a single string.

    Returns:
        A list of stripped, non-blank lines in their original order.
    """
    normalized_content = content or ""
    return [line.strip() for line in normalized_content.splitlines() if line.strip()]


def parse_email_content(content: str) -> list[dict[str, str]]:
    """Parse a LinkedIn job alert into one or more structured job records.

    Args:
        content: The full text of a LinkedIn alert email, including subject and
            body content.

    Returns:
        A list of job dictionaries with keys such as title, company, location,
        salary, url, and extra information. Empty lists are returned when no job
        records can be parsed.
    """
    lines = extract_email_lines(content)

    if not lines:
        return []

    def is_generic_text(value: str) -> bool:
        """Return True when a line is LinkedIn boilerplate rather than a job entry.

        Args:
            value: Candidate text from a parsed email line.

        Returns:
            True if the text matches common LinkedIn alert footer or navigation
            copy, otherwise False.
        """
        lowered = value.lower()
        generic_phrases = {
            "new jobs match your preferences.",
            "expand your search",
            "recommendations based on your activity.",
            "this email was intended for",
            "learn why we included this",
            "you are receiving job alert emails.",
            "manage your job alerts",
            "unsubscribe:",
            "view all jobs:",
            "this company is actively hiring",
            "apply with resume & profile",
            "see all jobs on linkedin",
            "your job alert for",
        }
        return lowered in generic_phrases or any(
            phrase in lowered for phrase in ("learn why", "manage your job alerts", "unsubscribe", "view all jobs", "this email was intended")
        )

    def parse_simple_content(source_lines: list[str]) -> list[dict[str, str]]:
        """Parse a small email body without separator markers.

        Args:
            source_lines: A list of cleaned email lines to interpret as a job.

        Returns:
            A list containing one or more parsed job dictionaries when a simple
            pattern is detected; otherwise an empty list.
        """
        subject_line = next((line.split(":", 1)[1].strip() for line in source_lines if line.lower().startswith("subject:")), "")
        source_text = "\n".join(source_lines)

    # LinkedIn job alerts usually prepend a generic intro and append a footer,
    # so trim those sections to isolate the actual job listings.
    start_index = None
    end_index = None

    for index, line in enumerate(lines):
        if line.lower() == "new jobs match your preferences.":
            start_index = index + 1
        elif line.lower().startswith("see all jobs on linkedin"):
            end_index = index
            break

    if start_index is None:
        start_index = 0
    if end_index is None:
        end_index = len(lines)

    relevant_lines = [line.strip() for line in lines[start_index:end_index] if line.strip()]

    if not any(line.startswith("-----") for line in relevant_lines):
        return parse_simple_content(relevant_lines or lines)

    job_blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in relevant_lines:
        if line.startswith("-----"):
            if current_block:
                job_blocks.append(current_block)
                current_block = []
            continue
        current_block.append(line)

    if current_block:
        job_blocks.append(current_block)

    parsed_jobs: list[dict[str, str]] = []

    for block in job_blocks:
        if not block:
            continue

        normalized_block = [line for line in block if line]
        if len(normalized_block) < 3:
            continue

        title = normalized_block[0]
        company = normalized_block[1] if len(normalized_block) > 1 else ""
        location = normalized_block[2] if len(normalized_block) > 2 else ""

        if is_generic_text(title) or is_generic_text(company) or is_generic_text(location):
            continue

        url = ""
        extra_information_parts: list[str] = []

        for line in normalized_block[3:]:
            url_match = re.search(r"https?://[^\s)\]>]+", line)
            if url_match:
                url = url_match.group(0)
            else:
                extra_information_parts.append(line)

        if not url and normalized_block:
            last_line = normalized_block[-1]
            last_url_match = re.search(r"https?://[^\s)\]>]+", last_line)
            if last_url_match:
                url = last_url_match.group(0)
                extra_information_parts = [line for line in normalized_block[3:-1] if line]

        parsed_jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "salary": "",
                "url": url,
                "extra information": "\n".join(extra_information_parts).strip(),
            }
        )

    if parsed_jobs:
        return parsed_jobs

    return parse_simple_content(relevant_lines or lines)


def make_job_id(job: dict[str, str]) -> str:
    """Create a short stable identifier for a job record.

    Args:
        job: A job dictionary, typically containing title, company, location, and
            optional URL data.

    Returns:
        A 12-character SHA-1 hash derived from the job URL or descriptive fields.
    """
    seed = job.get("url") or f"{job.get('title','')}|{job.get('company','')}|{job.get('location','')}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def merge_jobs(existing_jobs: list[dict[str, Any]], incoming_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge existing and newly parsed jobs without duplicating records.

    Args:
        existing_jobs: Jobs already saved to disk.
        incoming_jobs: Newly parsed jobs from the latest email batch.

    Returns:
        A deduplicated list of jobs, preserving the first-seen copy for each
        unique job ID.
    """
    merged: dict[str, dict[str, Any]] = {}

    for job in existing_jobs:
        job_copy = dict(job)
        job_copy.setdefault("id", make_job_id(job_copy))
        merged[job_copy["id"]] = job_copy

    for job in incoming_jobs:
        job_copy = dict(job)
        job_copy.setdefault("id", make_job_id(job_copy))
        job_copy.setdefault("reviewed", "no")
        if job_copy["id"] not in merged:
            merged[job_copy["id"]] = job_copy

    return list(merged.values())


def load_jobs(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Load saved jobs from a JSON file.

    Args:
        path: Path to the JSON file containing the stored jobs.

    Returns:
        A list of job dictionaries loaded from disk. Returns an empty list if the
        file does not exist or does not contain a list payload.
    """
    file_path = Path(path)
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        return data

    return []


def persist_jobs(path: str | os.PathLike[str], jobs: list[dict[str, Any]]) -> None:
    """Save a list of job records to a JSON file.

    Args:
        path: Destination path for the JSON output.
        jobs: Job dictionaries to write to disk.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(jobs, handle, indent=2)
        handle.write("\n")


def export_recent_email_lines(
    output_path: str | os.PathLike[str] = BASE_DIR / "recent_linkedin_email_lines.json",
    limit: int = 5,
    days: int = 3,
) -> list[dict[str, Any]]:
    """Export recent LinkedIn email content to a JSON snapshot for inspection.

    Args:
        output_path: Where to write the exported email samples.
        limit: Maximum number of messages to include in the export.
        days: Number of recent days to scan when selecting messages.

    Returns:
        A list of exported message dictionaries containing the message ID, subject,
        timestamp, and extracted email lines.
    """
    date_from = date.today() - timedelta(days=days)
    date_to = date.today()
    service = get_gmail_service()
    # Fetch more messages than the final sample count so filters can remove
    # stale or non-LinkedIn items without dropping too many valid results.
    messages = get_linkedin_messages(
        service,
        limit=max(limit * 4, 20),
        date_from=date_from,
        date_to=date_to,
    )

    samples: list[dict[str, Any]] = []
    for message in messages[:limit]:
        headers = {header["name"].lower(): header["value"] for header in message.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        body = extract_message_text(message.get("payload", {}))
        full_content = f"Subject: {subject}\n{body}"

        if "linkedin" not in full_content.lower():
            continue

        samples.append(
            {
                "message_id": message.get("id"),
                "subject": subject,
                "email_datetime": datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, tz=timezone.utc).isoformat(),
                "lines": extract_email_lines(full_content),
            }
        )

    with Path(output_path).open("w", encoding="utf-8") as handle:
        json.dump(samples, handle, indent=2)
        handle.write("\n")

    return samples


def run_workflow(
    output_path: str | os.PathLike[str] = BASE_DIR / "jobs.json",
    limit: int = 10,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
) -> list[dict[str, Any]]:
    """Fetch LinkedIn job alerts, parse job records, and save the consolidated output.

    Args:
        output_path: File path where the merged job list should be stored.
        limit: Maximum number of Gmail messages to inspect for this run.
        date_from: Earliest date to include in the lookup. Inclusive.
        date_to: Latest date to include in the lookup. Inclusive.

    Returns:
        A merged list of job dictionaries saved to the output file.
    """
    service = get_gmail_service()
    messages = get_linkedin_messages(service, limit=limit, date_from=date_from, date_to=date_to)
    parsed_jobs: list[dict[str, Any]] = []

    for message in messages:
        headers = {header["name"].lower(): header["value"] for header in message.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        body = extract_message_text(message.get("payload", {}))
        full_content = f"Subject: {subject}\n{body}"

        if "linkedin" not in full_content.lower():
            continue

        parsed_jobs_for_message = parse_email_content(full_content)
        for parsed in parsed_jobs_for_message:
            if parsed.get("title") or parsed.get("url"):
                parsed.setdefault("id", make_job_id(parsed))
                parsed.setdefault("source_message_id", message.get("id"))
                parsed.setdefault("email_datetime", datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, tz=timezone.utc).isoformat())
                parsed_jobs.append(parsed)

    existing_jobs = load_jobs(output_path)
    # Merge on a stable job ID so repeated runs keep the canonical record without
    # accumulating duplicate entries from the same alert.
    merged_jobs = merge_jobs(existing_jobs, parsed_jobs)
    persist_jobs(output_path, merged_jobs)
    return merged_jobs


def main() -> None:
    """Run the daily LinkedIn job workflow for the current date.

    Returns:
        None. The function processes the latest jobs and writes them to the default
        jobs.json file.
    """
    today = date.today()
    jobs = run_workflow(date_from=today, date_to=today)
    print(f"Processed {len(jobs)} jobs and saved them to {BASE_DIR / 'jobs.json'}")


if __name__ == "__main__":
    main()
