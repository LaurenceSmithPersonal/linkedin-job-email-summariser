# linkedin-job-email-summariser
Workflow to read LinkedIn job emails, extract useful fields, and de-duplicate them into a local JSON file.

## Setup
1. Install the project dependencies with `uv sync`.
2. Place your Gmail OAuth client credentials in `credentials.json`.
3. Run the workflow once to complete the Gmail authorization flow.

## Run
```bash
uv run python main.py
```

To target a specific date range, call the workflow directly with inclusive bounds:

```python
from datetime import date
import main

jobs = main.run_workflow(
    output_path="jobs.json",
    limit=25,
    date_from=date(2026, 8, 1),
    date_to=date(2026, 8, 31),
)
```

The script will:
- authenticate with Gmail using OAuth2,
- fetch recent LinkedIn-related messages,
- extract job title, company, location, salary, and URL,
- store the normalized results in `jobs.json` while avoiding duplicates on future runs.

