# linkedin-job-email-summariser
Agentic workflow to read LinkedIn job emails, extract useful fields, and de-duplicate them into a local JSON file.

## Setup
1. Install the project dependencies with `uv sync`.
2. Place your Gmail OAuth client credentials in `credentials.json`.
3. Run the workflow once to complete the Gmail authorization flow.

## Run
```bash
uv run python main.py
```

The script will:
- authenticate with Gmail using OAuth2,
- fetch recent LinkedIn-related messages,
- extract job title, company, location, salary, and URL,
- store the normalized results in `jobs.json` while avoiding duplicates on future runs.

