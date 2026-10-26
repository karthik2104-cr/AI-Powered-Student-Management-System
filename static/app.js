const state = { selectedId: null, subjects: [], examinations: [] };

const healthStatus = document.querySelector("#health-status");
const stats = document.querySelector("#stats");
const studentList = document.querySelector("#student-list");
const studentForm = document.querySelector("#student-form");
const studentMessage = document.querySelector("#student-message");
const detailTitle = document.querySelector("#detail-title");
const resultsTable = document.querySelector("#results-table");
const feedbackList = document.querySelector("#feedback-list");
const resourceList = document.querySelector("#resource-list");
const studyPlan = document.querySelector("#study-plan");
const aiOutput = document.querySelector("#ai-output");

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : response.statusText;
    const message = typeof detail === "string" ? detail : "The request was not accepted.";
    throw new Error(message);
  }
  return body;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
}

function chip(value) {
  const safe = escapeHtml(value);
  return `<span class="chip ${safe}">${safe.replaceAll("_", " ")}</span>`;
}

function showMessage(text) {
  studentMessage.textContent = text || "";
}

async function loadHealth() {
  const health = await request("/health").catch((error) => ({ status: "unhealthy", detail: error.message }));
  const assistant = await request("/assistant/status").catch(() => ({ reachable: false, detail: "Assistant status unavailable." }));
  const databaseText = health.status === "healthy" ? "Database connected" : "Database unavailable";
  const modelText = assistant.installed ? assistant.model + " ready" : assistant.model + " not installed";
  healthStatus.textContent = databaseText + " · " + (assistant.reachable ? modelText : "Ollama unavailable");
}

async function loadSummary() {
  try {
    const summary = await request("/summary");
    const cards = [
      ["Students", summary.students],
      ["Subjects", summary.subjects],
      ["Examinations", summary.examinations],
      ["Feedback", summary.feedback_entries],
      ["Resources", summary.resources],
      ["Needs support", summary.subjects_needing_support],
    ];
    stats.innerHTML = cards.map(([label, value]) => `<article class="stat"><span>${label}</span><strong>${value}</strong></article>`).join("");
  } catch (error) {
    stats.innerHTML = `<article class="stat">${error.message}</article>`;
  }
}

function fillSelect(select, rows, labelKey, includeBlank) {
  const blank = includeBlank ? '<option value="">No subject</option>' : "";
  select.innerHTML = blank + rows.map((row) => `<option value="${row.id}">${row[labelKey]}</option>`).join("");
}

async function loadReferenceData() {
  state.subjects = await request("/subjects");
  state.examinations = await request("/examinations");
  fillSelect(document.querySelector("#mark-subject"), state.subjects, "name", false);
  fillSelect(document.querySelector("#mark-examination"), state.examinations, "name", false);
  fillSelect(document.querySelector("#feedback-subject"), state.subjects, "name", true);
}

async function loadStudents() {
  const query = document.querySelector("#student-search").value.trim();
  const path = query ? `/students?q=${encodeURIComponent(query)}` : "/students";
  const students = await request(path);
  studentList.innerHTML = students.map((student) => `
    <li><button type="button" data-id="${student.id}" class="${student.id === state.selectedId ? "active" : ""}">
      <strong>${escapeHtml(student.full_name)}</strong><br>${escapeHtml(student.admission_number)}<br>${escapeHtml(student.email)}
    </button></li>
  `).join("");
  studentList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => selectStudent(Number(button.dataset.id)));
  });
}

function resetStudentForm() {
  state.selectedId = null;
  studentForm.reset();
  document.querySelector("#student-id").value = "";
  document.querySelector("#student-form-title").textContent = "Add student";
  document.querySelector("#cancel-edit").hidden = true;
  document.querySelector("#delete-student").hidden = true;
  detailTitle.textContent = "Select a student";
  resultsTable.innerHTML = "";
  feedbackList.innerHTML = "";
  resourceList.innerHTML = "";
  studyPlan.value = "";
  aiOutput.textContent = "";
}

async function selectStudent(studentId) {
  const student = await request(`/students/${studentId}`);
  state.selectedId = student.id;
  document.querySelector("#student-id").value = student.id;
  document.querySelector("#admission-number").value = student.admission_number;
  document.querySelector("#full-name").value = student.full_name;
  document.querySelector("#email").value = student.email;
  document.querySelector("#student-form-title").textContent = "Edit student";
  document.querySelector("#cancel-edit").hidden = false;
  document.querySelector("#delete-student").hidden = false;
  detailTitle.textContent = `${student.full_name} (${student.admission_number})`;
  await loadStudents();
  await loadStudentDetails();
}

async function loadStudentDetails() {
  if (!state.selectedId) {
    return;
  }
  const results = await request(`/students/${state.selectedId}/results`);
  resultsTable.innerHTML = renderResults(results.results);
  resultsTable.querySelectorAll("[data-delete-mark]").forEach((button) => {
    button.addEventListener("click", async () => {
      await request(`/marks/${button.dataset.deleteMark}`, { method: "DELETE" });
      await loadStudentDetails();
      await loadSummary();
    });
  });
  const feedback = await request(`/students/${state.selectedId}/feedback`);
  feedbackList.innerHTML = feedback.map((item) => `
    <li><strong>${escapeHtml(item.subject_name || "General")}: ${escapeHtml(item.topic || "No topic")}</strong><br>
    ${escapeHtml(item.difficult_topics || "")} ${escapeHtml(item.explanation_request || "")} ${escapeHtml(item.practice_request || "")}<br>
    Preferred format: ${item.preferred_format}. Student-reported, not an official result.</li>
  `).join("") || "<li>No feedback yet.</li>";
  const resources = await request(`/students/${state.selectedId}/resources`);
  resourceList.innerHTML = resources.map((resource) => `
    <li><a href="${escapeHtml(resource.url)}" target="_blank" rel="noopener">${escapeHtml(resource.title)}</a>
    ${chip(resource.verification_status)}<br>
    ${escapeHtml(resource.subject_name)} · ${escapeHtml(resource.topic)} · ${escapeHtml(resource.resource_type)}
    ${resource.author ? " · " + escapeHtml(resource.author) : ""}<br>${escapeHtml(resource.description)}</li>
  `).join("") || "<li>No stored resource matches a subject that currently needs support.</li>";
  const outline = await request(`/students/${state.selectedId}/study-outline`);
  studyPlan.value = outline.note + "\n\n" + outline.items.map((item) => `${item.day}: ${item.activity}`).join("\n");
}

function renderResults() {
  return "<p>Official Semester 1 results are the internal assessment, external examination, and final subject tables in the student and admin portals. This page does not show a separate percentage result.</p>";
}

studentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    admission_number: document.querySelector("#admission-number").value,
    full_name: document.querySelector("#full-name").value,
    email: document.querySelector("#email").value,
  };
  try {
    const id = document.querySelector("#student-id").value;
    const saved = id
      ? await request(`/students/${id}`, { method: "PUT", body: JSON.stringify(payload) })
      : await request("/students", { method: "POST", body: JSON.stringify(payload) });
    showMessage("Student saved.");
    await loadSummary();
    await selectStudent(saved.id);
  } catch (error) {
    showMessage(error.message);
  }
});

document.querySelector("#cancel-edit").addEventListener("click", async () => {
  resetStudentForm();
  await loadStudents();
});

document.querySelector("#delete-student").addEventListener("click", async () => {
  if (!state.selectedId || !confirm("Delete this student, including marks and feedback?")) {
    return;
  }
  try {
    await request(`/students/${state.selectedId}`, { method: "DELETE" });
    resetStudentForm();
    await loadStudents();
    await loadSummary();
    showMessage("Student deleted.");
  } catch (error) {
    showMessage(error.message);
  }
});

document.querySelector("#student-search").addEventListener("input", () => {
  loadStudents().catch((error) => showMessage(error.message));
});

document.querySelector("#mark-form").addEventListener("submit", (event) => {
  event.preventDefault();
  showMessage("This page cannot save marks. Use the administrator portal for CAT, assignment, and external scores.");
});

document.querySelector("#feedback-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.selectedId) {
    showMessage("Select a student before adding feedback.");
    return;
  }
  const subjectValue = document.querySelector("#feedback-subject").value;
  const rating = document.querySelector("#resource-rating").value;
  const payload = {
    subject_id: subjectValue ? Number(subjectValue) : null,
    topic: document.querySelector("#feedback-topic").value,
    difficult_topics: document.querySelector("#difficult-topics").value,
    explanation_request: document.querySelector("#explanation-request").value,
    practice_request: document.querySelector("#practice-request").value,
    preferred_format: document.querySelector("#preferred-format").value,
    resource_note: document.querySelector("#resource-note").value,
    resource_rating: rating || null,
  };
  try {
    await request(`/students/${state.selectedId}/feedback`, { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    await loadStudentDetails();
    showMessage("Feedback saved as a student report.");
  } catch (error) {
    showMessage(error.message);
  }
});

async function askAssistant(path, extra) {
  if (!state.selectedId) {
    aiOutput.textContent = "Select a student first.";
    return;
  }
  aiOutput.textContent = "Asking the local model…";
  try {
    const answer = await request(`/students/${state.selectedId}${path}`, {
      method: "POST",
      body: JSON.stringify(extra || {}),
    });
    aiOutput.textContent = answer.notice + "\nModel: " + answer.model + "\n\n" + answer.narrative;
  } catch (error) {
    aiOutput.textContent = error.message;
  }
}

document.querySelector("#ai-report").addEventListener("click", () => askAssistant("/assistant/report"));
document.querySelector("#ai-suggestions").addEventListener("click", () => askAssistant("/assistant/suggestions"));
document.querySelector("#ai-plan").addEventListener("click", () => askAssistant("/assistant/plan"));
document.querySelector("#ai-ask").addEventListener("click", () => {
  askAssistant("/assistant/ask", { question: document.querySelector("#question-input").value });
});

async function start() {
  await loadHealth();
  try {
    await loadSummary();
    await loadReferenceData();
    await loadStudents();
  } catch (error) {
    showMessage(error.message);
  }
}

start();
