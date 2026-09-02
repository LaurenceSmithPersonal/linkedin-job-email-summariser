"""Serve the local job-review web application and JSON API."""

import json
import os
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import main

WEB_DIR = Path(__file__).resolve().parent / "web"
JOBS_PATH = main.BASE_DIR / "jobs.json"
HOST = "127.0.0.1"
PORT = 8000


def deduplicate_jobs(jobs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return the first record for each stable job ID."""
    unique_jobs: dict[str, dict[str, object]] = {}
    for job in jobs:
        job_copy = dict(job)
        job_id = str(job_copy.get("id") or main.make_job_id(job_copy))
        job_copy["id"] = job_id
        unique_jobs.setdefault(job_id, job_copy)
    return list(unique_jobs.values())


def read_jobs() -> list[dict[str, object]]:
    """Load and deduplicate jobs from the configured JSON file."""
    return deduplicate_jobs(main.load_jobs(JOBS_PATH))


def write_jobs(jobs: list[dict[str, object]]) -> None:
    """Atomically replace the jobs JSON file with the supplied records."""
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=JOBS_PATH.parent,
            delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(jobs, handle, indent=2)
            handle.write("\n")
        os.replace(temporary_path, JOBS_PATH)
        temporary_path = None
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)


def update_review_status(job_id: str, reviewed: str) -> dict[str, object] | None:
    """Set one job's review status and return the updated record."""
    jobs = read_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["reviewed"] = reviewed
            write_jobs(jobs)
            return job
    return None


class JobRequestHandler(BaseHTTPRequestHandler):
    """Handle static files and the local job-management API."""

    def do_GET(self) -> None:
        """Serve the job list API or the frontend entry point."""
        request_path = urlparse(self.path).path
        if request_path == "/api/jobs":
            self._send_json({"jobs": read_jobs()})
            return
        if request_path == "/" or request_path == "/index.html":
            self._send_static("index.html", "text/html; charset=utf-8")
            return
        if request_path.startswith("/static/"):
            relative_path = unquote(request_path.removeprefix("/static/"))
            if relative_path in {"app.js", "styles.css"}:
                content_type = (
                    "application/javascript; charset=utf-8"
                    if relative_path == "app.js"
                    else "text/css; charset=utf-8"
                )
                self._send_static(relative_path, content_type)
                return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PATCH(self) -> None:
        """Update a job's review status through the JSON API."""
        request_path = urlparse(self.path).path
        if not request_path.startswith("/api/jobs/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        payload = self._read_json()
        reviewed = payload.get("reviewed") if payload else None
        if reviewed not in {"yes", "no"}:
            self._send_json(
                {"error": "reviewed must be 'yes' or 'no'"},
                HTTPStatus.BAD_REQUEST,
            )
            return

        job_id = unquote(request_path.removeprefix("/api/jobs/"))
        job = update_review_status(job_id, reviewed)
        if job is None:
            self._send_json({"error": "Job not found"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json({"job": job})

    def do_POST(self) -> None:
        """Run the existing Gmail workflow and return refreshed jobs."""
        if urlparse(self.path).path != "/api/update":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            before_ids = {job["id"] for job in read_jobs()}
            jobs = main.run_workflow(output_path=JOBS_PATH)
            jobs = deduplicate_jobs(jobs)
            new_count = sum(job["id"] not in before_ids for job in jobs)
            self._send_json({"jobs": jobs, "new_count": new_count})
        except Exception as error:
            self._send_json(
                {"error": f"Job update failed: {error}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format_string: str, *args: object) -> None:
        """Keep request logging concise for the local development server."""
        print(f"{self.command} {self.path}")

    def _read_json(self) -> dict[str, object] | None:
        """Read a JSON request body, returning None for invalid input."""
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            payload = json.loads(body)
            return payload if isinstance(payload, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def _send_json(
        self,
        payload: dict[str, object],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        """Send a JSON response with the supplied HTTP status."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, relative_path: str, content_type: str) -> None:
        """Send a known frontend asset."""
        file_path = WEB_DIR / relative_path
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve() -> None:
    """Start the local web server until interrupted."""
    server = ThreadingHTTPServer((HOST, PORT), JobRequestHandler)
    print(f"Job review app running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping job review app.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
