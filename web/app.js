const state = {
  jobs: [],
  filter: "all",
  pendingIds: new Set(),
};

const listElement = document.querySelector("#job-list");
const statusElement = document.querySelector("#status-message");
const filterElement = document.querySelector("#job-filter");
const updateButton = document.querySelector("#update-button");
const dateFromElement = document.querySelector("#date-from");
const dateToElement = document.querySelector("#date-to");

const jobStatuses = [
  "not reviewed",
  "reviewed",
  "want to apply",
  "applied",
  "rejected",
  "success",
];

function jobStatus(job) {
  if (job.reviewed === "yes") return "reviewed";
  if (job.reviewed === "no" || !job.reviewed) return "not reviewed";
  return job.reviewed;
}

function isReviewed(job) {
  return jobStatus(job) !== "not reviewed";
}

function populateFilterOptions() {
  filterElement.replaceChildren();
  const allJobsOption = document.createElement("option");
  allJobsOption.value = "all";
  allJobsOption.textContent = "All jobs";
  filterElement.append(allJobsOption);

  jobStatuses.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    filterElement.append(option);
  });
}

function displayValue(value, fallback = "Not provided") {
  return value === undefined || value === null || value === "" ? fallback : value;
}

function deduplicateJobs(jobs) {
  const uniqueJobs = new Map();
  jobs.forEach((job) => {
    if (job && job.id && !uniqueJobs.has(job.id)) {
      uniqueJobs.set(job.id, job);
    }
  });
  return [...uniqueJobs.values()];
}

function sortJobs(jobs) {
  return [...jobs].sort((first, second) => {
    const firstDate = Date.parse(first.email_datetime || "") || 0;
    const secondDate = Date.parse(second.email_datetime || "") || 0;
    return secondDate - firstDate;
  });
}

function dateInputValue(value) {
  const match = String(value || "").match(/^(\d{4}-\d{2}-\d{2})/);
  if (match && !Number.isNaN(Date.parse(`${match[1]}T00:00:00Z`))) {
    return match[1];
  }
  return "";
}

function setDefaultDateInputs() {
  const dates = state.jobs
    .map((job) => dateInputValue(job.email_datetime))
    .filter(Boolean)
    .sort();
  dateFromElement.value = dates[dates.length - 1] || "";
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  dateToElement.value = `${today.getFullYear()}-${month}-${day}`;
}

function visibleJobs() {
  const jobs = state.filter === "all"
    ? state.jobs
    : state.jobs.filter((job) => jobStatus(job) === state.filter);
  return sortJobs(jobs);
}

function setStatus(message, kind = "") {
  statusElement.textContent = message;
  statusElement.className = `status-message ${kind}`;
}

function updateCounts() {
  const visibleCount = visibleJobs().length;
  const awaitingCount = state.jobs.filter((job) => !isReviewed(job)).length;
  document.querySelector("#visible-count").textContent =
    `${visibleCount} ${visibleCount === 1 ? "job" : "jobs"}`;
  document.querySelector("#review-count").textContent =
    `${awaitingCount} awaiting review`;
}

function createTextElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function createReviewControl(job) {
  const wrapper = document.createElement("label");
  wrapper.className = "review-control";
  wrapper.addEventListener("click", (event) => event.stopPropagation());

  const select = document.createElement("select");
  select.className = "status-select";
  select.disabled = state.pendingIds.has(job.id);
  select.setAttribute("aria-label", `Set status for ${displayValue(job.title, "job")}`);
  jobStatuses.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    option.selected = status === jobStatus(job);
    select.append(option);
  });
  select.addEventListener("change", () => saveReviewStatus(job, select.value));

  wrapper.append(select);
  return wrapper;
}

function createJobCard(job) {
  const card = document.createElement("article");
  card.className = `job-card ${isReviewed(job) ? "is-reviewed" : ""}`;

  const header = document.createElement("div");
  header.className = "job-header";
  const heading = createTextElement("h2", "job-title", displayValue(job.title, "Untitled role"));
  header.append(heading, createTextElement("time", "received-date", formatDate(job.email_datetime)));
  const company = createTextElement("p", "job-company", displayValue(job.company, "Company not provided"));
  const metadata = document.createElement("div");
  metadata.className = "job-metadata";
  metadata.append(
    createTextElement("span", "metadata-item", displayValue(job.location, "Location not provided")),
    createTextElement("span", "metadata-item", displayValue(job.salary, "Salary not listed")),
  );
  const extraInformation = createTextElement(
    "p",
    "extra-information",
    displayValue(job["extra information"], "No extra information"),
  );
  const footer = document.createElement("div");
  footer.className = "job-footer";
  footer.append(createReviewControl(job));
  if (job.url) {
    const link = document.createElement("a");
    link.className = "job-link";
    link.href = job.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open job listing (new tab)";
    footer.append(link);
  } else {
    footer.append(createTextElement("span", "unavailable-link", "Job listing URL unavailable"));
  }
  card.append(header, company, metadata, extraInformation, footer);
  return card;
}

function formatDate(value) {
  if (!value) return "Date not provided";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Date not provided";
  return `Received ${new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" }).format(parsed)}`;
}

function renderJobs() {
  const jobs = visibleJobs();
  listElement.replaceChildren();
  listElement.setAttribute("aria-busy", "false");
  updateCounts();

  if (!jobs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const isUnreviewedFilter = state.filter === "not reviewed";
    empty.append(
      createTextElement("h2", "empty-title", isUnreviewedFilter ? "All caught up." : "No jobs yet."),
      createTextElement("p", "empty-copy", isUnreviewedFilter ? "Every saved job has been reviewed." : "No jobs match this status."),
    );
    if (state.filter !== "all") {
      const showAll = document.createElement("button");
      showAll.className = "button button-secondary";
      showAll.type = "button";
      showAll.textContent = "Show all jobs";
      showAll.addEventListener("click", () => {
        state.filter = "all";
        filterElement.value = "all";
        renderJobs();
      });
      empty.append(showAll);
    }
    listElement.append(empty);
    return;
  }
  jobs.forEach((job) => listElement.append(createJobCard(job)));
}

async function loadJobs() {
  listElement.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/jobs");
    if (!response.ok) throw new Error("Could not load jobs.");
    const payload = await response.json();
    state.jobs = deduplicateJobs(payload.jobs || []);
    setDefaultDateInputs();
    renderJobs();
    setStatus("");
  } catch (error) {
    listElement.setAttribute("aria-busy", "false");
    listElement.replaceChildren(createTextElement("div", "error-state", "Jobs could not be loaded. Refresh to try again."));
    setStatus(error.message, "error");
  }
}

async function saveReviewStatus(job, reviewed) {
  const previousValue = job.reviewed;
  state.pendingIds.add(job.id);
  job.reviewed = reviewed;
  renderJobs();
  setStatus("Saving review status...");
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(job.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed }),
    });
    if (!response.ok) throw new Error("Review status could not be saved.");
    const payload = await response.json();
    Object.assign(job, payload.job);
    setStatus("Review status saved.", "success");
  } catch (error) {
    job.reviewed = previousValue;
    setStatus("Review status could not be saved. Try again.", "error");
  } finally {
    state.pendingIds.delete(job.id);
    renderJobs();
  }
}

populateFilterOptions();

filterElement.addEventListener("change", () => {
  state.filter = filterElement.value;
  renderJobs();
});

updateButton.addEventListener("click", async () => {
  updateButton.disabled = true;
  updateButton.innerHTML = "<span aria-hidden=\"true\">&#8987;</span> Updating...";
  setStatus("Updating jobs. This may take a moment...");
  try {
    const response = await fetch("/api/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date_from: dateFromElement.value,
        date_to: dateToElement.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Job update failed.");
    state.jobs = deduplicateJobs(payload.jobs || []);
    renderJobs();
    setStatus(`${payload.new_count || 0} new ${payload.new_count === 1 ? "job" : "jobs"} added.`, "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    updateButton.disabled = false;
    updateButton.innerHTML = "<span aria-hidden=\"true\">&#8635;</span> Update jobs";
  }
});

loadJobs();
