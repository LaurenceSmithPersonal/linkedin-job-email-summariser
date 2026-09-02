# Front-End Requirements

## 1. Purpose

Build a local web front end for reviewing and managing the deduplicated job
records stored in `jobs.json`.

The interface should help a user quickly scan new opportunities, see the
available details and listing link for each job immediately, mark it as
reviewed, hide reviewed jobs when needed, and run the existing job-ingestion
workflow to find new records.

This document describes the required behavior and testing expectations. It does
not prescribe an implementation framework.

## 2. Data Contract

Each job is a JSON object. The front end should support these fields:

- `id`: Stable unique identifier used for rendering, updates, and deduplication.
- `title`: Job title.
- `company`: Hiring company.
- `location`: Job location.
- `salary`: Salary or compensation text, which may be empty.
- `url`: Link to the job listing, which may be empty or unavailable.
- `extra information`: Additional extracted job information, which may be empty.
- `source_message_id`: Gmail message identifier, which may be absent.
- `email_datetime`: Original email timestamp, which may be absent.
- `reviewed`: Review status. New jobs must default to `"no"`; existing values
  must be preserved.

The front end must treat `id` as the record identity. It must not create a
second copy of a job when the same job is returned by a refresh or update.

For backward compatibility, jobs that predate the `reviewed` field should be
treated as not reviewed in the interface. Adding the field to old records is a
backend/data-migration decision and is outside this front-end requirement.

## 3. Primary User Experience

### 3.1 Initial load

- Load the current job list from the application data source backed by
  `jobs.json`.
- Show a clear loading state while the list is being retrieved.
- Display jobs in a predictable order, with newest or most recently received
  jobs first when `email_datetime` is available.
- Show the total number of jobs and the number currently awaiting review.
- Preserve the selected filter and review state when refreshing data, where
  doing so does not hide newly added jobs unexpectedly.

### 3.2 Job list

Each job should be represented by a compact, scannable row or card containing:

- Job title as the primary label.
- Company and location.
- Salary when present.
- Received date when present.
- A visible reviewed/not-reviewed status.
- An accessible control for changing the review status.

The list must be deduplicated by `id`. Duplicate records must never be shown to
the user, even if the source data accidentally contains repeated entries.

The complete job information should be visible on the initial list screen. The
review control must be independently usable from the external listing link.

### 3.3 Job information and listing link

Each job row must show all available user-relevant fields directly, including:

- Title, company, location, salary, and extra information.
- Original email date and source message identifier when available.
- The canonical job URL.
- The current reviewed status and its toggle.

The job URL must be presented as an explicit "Open job listing" action. It must
open the external LinkedIn listing in a new browser tab with appropriate
security attributes. If no URL exists, show a clear unavailable state and do
not render a broken link. No popup or separate detail view is required.

### 3.4 Review status

- The control must provide exactly two understandable states: `Not reviewed`
  and `Reviewed`.
- New jobs must appear as `Not reviewed`.
- Changing the control must persist the new value to the data source; a visual
  change alone is insufficient.
- Existing job details and user-edited text must remain unchanged when the
  review status is updated.
- Show a pending state while the status update is being saved.
- If saving fails, restore the last confirmed state, explain that the update
  failed, and provide a retry path.
- The control must be keyboard accessible and expose its state to assistive
  technology. A native checkbox or switch pattern is preferred.

### 3.5 Hide reviewed jobs

Provide a prominent filter control with at least these modes:

- `All jobs`
- `Not reviewed`

The `Not reviewed` mode must hide jobs whose status is `Reviewed` and show jobs
whose status is `Not reviewed` or absent. The filter must update without a full
page reload.

The interface should show the active filter and the count of visible jobs. If
the active filter produces no results, show an informative empty state with an
action to return to `All jobs`.

### 3.6 Update jobs

Provide a clearly labelled `Update jobs` action that invokes the existing
workflow operation (`run_workflow` through the chosen application boundary).

While the update is running:

- Disable the update action or prevent duplicate submissions.
- Show progress or a clear in-progress state.
- Keep the existing list visible unless the application must replace it.

On success:

- Reload or merge the returned jobs into the list.
- Preserve existing review statuses and job text.
- Show how many new jobs were added, if that information is available.
- Apply the current filter to the refreshed list.

On failure:

- Keep the existing list and review states intact.
- Show a concise, actionable error message.
- Make it possible to retry without losing the current view.
- Surface authentication failures clearly, including when the user needs to
  complete Google re-authentication in the terminal or browser.

## 4. Persistence and API Boundary

The browser must not rely on directly editing a local JSON file unless the
application environment explicitly supports secure local-file access. A small
backend or local API should own reading and writing `jobs.json` and invoking
`run_workflow`.

The boundary should provide operations equivalent to:

- Read the deduplicated job list.
- Update one job's `reviewed` value by `id`.
- Run the job workflow and return the resulting list or an update summary.

Update operations must be atomic from the user's perspective. A failed write
must not leave a partially written `jobs.json` or make the interface report an
unconfirmed status.

Concurrent refreshes must not overwrite a user's confirmed review change with
stale job data. The implementation should use a server-side update, revision,
or equivalent conflict strategy.

## 5. Visual and Interaction Requirements

- Prioritize scanning: compact rows, strong title hierarchy, aligned metadata,
  and clear status treatment.
- Keep the list usable on desktop and mobile widths without horizontal
  scrolling.
- Use a distinct but restrained visual difference between reviewed and
  unreviewed jobs; do not communicate status by color alone.
- Use familiar controls: a switch or checkbox for review state, a filter control
  for visibility, and a labelled button for updating jobs.
- Ensure text wraps cleanly, especially long job titles, company names, URLs,
  and extra information.
- Provide visible focus indicators and a logical keyboard tab order.
- Do not make the whole job card appear interactive in a way that conflicts
  with the independent review control.
- Confirm destructive or surprising actions only if they are introduced later;
  marking a job reviewed should not require a confirmation dialog.

## 6. Accessibility Requirements

- Meet WCAG 2.1 AA expectations for keyboard operation, focus visibility,
  semantic structure, contrast, and status communication.
- Use a meaningful page heading and landmarks for the main list, filters, and
  update controls.
- Give every interactive control an accessible name.
- Announce update completion, save failures, and loading state changes through
  an appropriate live region or equivalent mechanism.
- Do not use color as the only indication of reviewed status.
- External links must clearly communicate that they open a new tab.

## 7. Error and Empty States

The front end must handle and test these states:

- Empty data set: explain that no jobs are available yet and offer `Update
  jobs`.
- No not-reviewed jobs: explain that all jobs have been reviewed and offer a
  way to show all jobs.
- Malformed or incomplete job record: render available fields without crashing;
  use sensible placeholders for missing values.
- Data-load failure: preserve a retry action and avoid displaying stale data as
  current without indicating that it is stale.
- Review-save failure: restore the confirmed value and allow retry.
- Workflow failure: retain the current list and report the failure.
- Authentication failure: explain the next action without exposing tokens or
  credential contents.

## 8. Testing Requirements

### 8.1 Unit tests

Test pure data and presentation logic for:

- Deduplication by stable `id`.
- Fallback identity handling for records without an `id`, if supported by the
  backend contract.
- Defaulting a missing `reviewed` value to `Not reviewed` in the UI.
- Preserving an existing `reviewed` value and all other existing job fields.
- Filtering `All jobs` versus `Not reviewed`.
- Sorting jobs by received date, including missing or invalid dates.
- Safe rendering of missing salary, URL, extra information, and email metadata.
- Counting total and visible jobs accurately.

### 8.2 Component or interaction tests

Test that:

- The loading, populated, empty, and error states render correctly.
- The initial list shows the available job details and listing link.
- Toggling a job sends an update for the correct `id` and displays the saved
  state.
- A failed review update restores the previous state and exposes retry.
- The reviewed filter hides reviewed jobs and can be cleared.
- Job rows show available fields and handle a missing URL.
- The external listing action uses the expected URL and new-tab behavior.
- The update action prevents duplicate requests while the workflow is running.
- A successful update adds new jobs without changing existing job text or
  review statuses.
- A failed update keeps the existing list visible and offers retry.

### 8.3 Accessibility tests

Automated accessibility checks should run against the list, filtered list, and
each major loading/error state. They should verify:

- Every control has an accessible name.
- Review state is exposed correctly.
- Keyboard navigation reaches every action in a logical order.
- Focus is visible and keyboard navigation is correct.
- Status and error messages are announced appropriately.
- No critical contrast or landmark violations are introduced.

Automated checks should be supplemented by a keyboard-only smoke test and a
screen-reader smoke test for the primary review workflow.

### 8.4 End-to-end tests

Using a temporary or test data store, cover the complete workflows:

1. Load jobs and see a deduplicated list with job information and listing links.
2. Mark a new job reviewed, reload the application, and confirm the state is
   retained.
3. Enable `Not reviewed`, confirm reviewed jobs are hidden, then restore all
   jobs.
4. Run `Update jobs`, confirm a new job appears with `reviewed` set to `no`,
   and confirm existing records are unchanged.
5. Simulate review-save, load, and workflow failures and verify recovery paths.
6. Verify that two records with the same `id` render once.

End-to-end tests must not use production `jobs.json`, real Gmail credentials,
or a real LinkedIn account. External workflow calls should be stubbed or run
against a controlled fixture.

## 9. Definition of Done

The front end is ready when:

- A user can scan a deduplicated job list from `jobs.json`.
- A user can inspect each job and open its listing URL when available.
- A user can toggle reviewed status and see the change persist.
- A user can hide reviewed jobs and understand the active filter and counts.
- A user can invoke the job update workflow and receive success or failure
  feedback.
- Existing job text and review values are preserved across updates.
- New jobs receive `reviewed: "no"`.
- Loading, empty, malformed-data, authentication, save, and workflow failure
  states are handled.
- Required unit, interaction, accessibility, and end-to-end tests pass.
- The primary workflows are usable by keyboard and meet the stated
  accessibility expectations.
