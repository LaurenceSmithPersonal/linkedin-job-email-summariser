import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
]


def get_gmail_service():
    creds = None
    token_path = BASE_DIR / "token.json"
    credentials_path = BASE_DIR / "credentials.json"

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        with token_path.open("w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def extract_message_text(payload: dict[str, Any]) -> str:
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


def get_linkedin_messages(service, limit: int = 10) -> list[dict[str, Any]]:
    query = "from:(linkedin.com) OR subject:(LinkedIn) OR subject:(job) OR linkedin"
    response = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    message_refs = response.get("messages", [])
    messages: list[dict[str, Any]] = []

    for message_ref in message_refs:
        message = service.users().messages().get(userId="me", id=message_ref["id"], format="full").execute()
        messages.append(message)

    return messages


def parse_email_content(content: str) -> dict[str, str]:
    normalized_content = content or ""
    lines = [line.strip() for line in normalized_content.splitlines() if line.strip()]

    subject_line = next((line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("subject:")), "")
    source_text = "\n".join(lines)

    title = ""
    company = ""

    for line in lines:
        match = re.match(r"(?i)\b(?:role|title|position|job)\s*[:\-]\s*(.+)", line)
        if match:
            title = match.group(1).strip(" .:-")
            break

    if not title:
        match = re.search(r"(?i)\b(?:subject|headline)\s*[:\-]\s*(.+)", source_text)
        if match:
            title = match.group(1).strip(" .:-")

    if not title and subject_line:
        title = subject_line.strip(" .:-")

    if not company and subject_line:
        if " at " in subject_line:
            parsed_title, parsed_company = [segment.strip() for segment in subject_line.split(" at ", 1)]
            if not title:
                title = parsed_title
            company = parsed_company
        elif " - " in subject_line:
            parsed_title, parsed_company = [segment.strip() for segment in subject_line.split(" - ", 1)]
            if not title:
                title = parsed_title
            company = parsed_company

    location = ""
    salary = ""
    url = ""

    for line in lines:
        if not location and re.match(r"(?i)location\s*[:\-]", line):
            location = re.split(r"(?i)location\s*[:\-]", line, maxsplit=1)[1].strip()
        if not salary and re.match(r"(?i)(?:salary|compensation|pay)\s*[:\-]", line):
            salary = re.split(r"(?i)(?:salary|compensation|pay)\s*[:\-]", line, maxsplit=1)[1].strip()

    url_match = re.search(r"https?://[^\s)\]>]+", source_text)
    if url_match:
        url = url_match.group(0)

    return {
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "url": url,
    }


def make_job_id(job: dict[str, str]) -> str:
    seed = job.get("url") or f"{job.get('title','')}|{job.get('company','')}|{job.get('location','')}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def merge_jobs(existing_jobs: list[dict[str, Any]], incoming_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for job in existing_jobs:
        job_copy = dict(job)
        job_copy.setdefault("id", make_job_id(job_copy))
        merged[job_copy["id"]] = job_copy

    for job in incoming_jobs:
        job_copy = dict(job)
        job_copy.setdefault("id", make_job_id(job_copy))
        if job_copy["id"] not in merged:
            merged[job_copy["id"]] = job_copy

    return list(merged.values())


def load_jobs(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        return data

    return []


def persist_jobs(path: str | os.PathLike[str], jobs: list[dict[str, Any]]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(jobs, handle, indent=2)
        handle.write("\n")


def run_workflow(output_path: str | os.PathLike[str] = BASE_DIR / "jobs.json", limit: int = 10) -> list[dict[str, Any]]:
    service = get_gmail_service()
    messages = get_linkedin_messages(service, limit=limit)
    parsed_jobs: list[dict[str, Any]] = []

    for message in messages:
        headers = {header["name"].lower(): header["value"] for header in message.get("payload", {}).get("headers", [])}
        subject = headers.get("subject", "")
        body = extract_message_text(message.get("payload", {}))
        full_content = f"Subject: {subject}\n{body}"

        if "linkedin" not in full_content.lower():
            continue

        parsed = parse_email_content(full_content)
        if parsed.get("title") or parsed.get("url"):
            parsed.setdefault("id", make_job_id(parsed))
            parsed.setdefault("source_message_id", message.get("id"))
            parsed_jobs.append(parsed)

    existing_jobs = load_jobs(output_path)
    merged_jobs = merge_jobs(existing_jobs, parsed_jobs)
    persist_jobs(output_path, merged_jobs)
    return merged_jobs


def main() -> None:
    jobs = run_workflow()
    print(f"Processed {len(jobs)} jobs and saved them to {BASE_DIR / 'jobs.json'}")


if __name__ == "__main__":
    main()
