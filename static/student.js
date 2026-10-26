const pageMessage = document.querySelector("#page-message");

function show(text, ok) {
  pageMessage.textContent = text || "";
  pageMessage.className = ok ? "message ok" : "message";
}

function recorded(value) {
  return value === null || value === undefined || value === "" ? "Not recorded" : value;
}

function renderAcademicTables(report) {
  if (!report) return "<p>The Semester 1 report is not available.</p>";
  const internalRows = (report.internal_assessments || []).map((row) => `<tr>
      <td>${escapeHtml(row.subject_name)}</td>
      <td>${escapeHtml(recorded(row.cat_1))}</td>
      <td>${escapeHtml(recorded(row.assignment_1))}</td>
      <td>${escapeHtml(recorded(row.cat_2))}</td>
      <td>${escapeHtml(recorded(row.assignment_2))}</td>
      <td>${escapeHtml(recorded(row.cat_3))}</td>
      <td>${escapeHtml(recorded(row.assignment_3))}</td>
      <td>${escapeHtml(recorded(row.internal_mark))}</td>
      <td>${chip(row.assessment_status)}</td>
    </tr>`).join("");
  const externalRows = (report.external_examinations || []).map((row) => `<tr>
      <td>${escapeHtml(row.subject_name)}</td>
      <td>${escapeHtml(recorded(row.external_raw))}</td>
      <td>${escapeHtml(recorded(row.external_mark))}</td>
      <td>${chip(row.assessment_status)}</td>
    </tr>`).join("");
  const finalRows = (report.final_results || []).map((row) => `<tr>
      <td>${escapeHtml(row.subject_name)}</td>
      <td>${escapeHtml(recorded(row.internal_mark))}</td>
      <td>${escapeHtml(recorded(row.external_mark))}</td>
      <td>${escapeHtml(recorded(row.final_mark))}</td>
      <td>${escapeHtml(recorded(row.grade))}</td>
      <td>${chip(row.official_status)}</td>
    </tr>`).join("");
  return `
    <p class="hint">${escapeHtml(report.department)} · ${escapeHtml(report.semester)}</p>
    <section id="internal-assessment">
      <h3>Internal assessment</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Subject</th><th>CAT 1 /50</th><th>Assignment 1 /50</th><th>CAT 2 /50</th><th>Assignment 2 /50</th><th>CAT 3 /50</th><th>Assignment 3 /50</th><th>Internal mark /50</th><th>Assessment status</th></tr></thead>
        <tbody>${internalRows}</tbody>
      </table></div>
    </section>
    <section id="external-examination">
      <h3>External examination</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Subject</th><th>External raw mark /100</th><th>Converted external mark /50</th><th>Assessment status</th></tr></thead>
        <tbody>${externalRows}</tbody>
      </table></div>
    </section>
    <section id="final-subject-results">
      <h3>Final subject results</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Subject</th><th>Internal mark /50</th><th>External mark /50</th><th>Final mark /100</th><th>Grade</th><th>Pass/fail status</th></tr></thead>
        <tbody>${finalRows}</tbody>
      </table></div>
    </section>`;
}

function renderResults(payload) {
  document.querySelector("#results-table").innerHTML = renderAcademicTables(payload.academic_report);
}

function renderVideos(rows) {
  const target = document.querySelector("#video-list");
  if (!rows.length) {
    target.innerHTML = "<p>No stored videos match a subject you have studied or reported.</p>";
    return;
  }
  target.innerHTML = rows.map((row) => {
    const player = row.embed_url
      ? `<iframe class="video-frame" src="${escapeHtml(row.embed_url)}" title="${escapeHtml(row.title)}" sandbox="allow-scripts allow-presentation" referrerpolicy="strict-origin-when-cross-origin" allow="fullscreen"></iframe>`
      : "";
    return `<article class="card">
      <h3>${escapeHtml(row.title)} ${chip(row.verification_status)}</h3>
      <p>${escapeHtml(row.subject_name || "")} · ${escapeHtml(row.topic)} · ${escapeHtml(row.author || "Publisher not stored")}</p>
      <p>${escapeHtml(row.description)}</p>
      ${player}
      <p><a href="${escapeHtml(row.url)}" rel="noopener noreferrer" target="_blank">Open video</a></p>
    </article>`;
  }).join("");
}

function renderAttendance(report) {
  const summary = report.summary;
  const percent = summary.percentage === null ? "Not enough sessions" : `${summary.percentage}%`;
  document.querySelector("#attendance-summary").innerHTML =
    `<p>${summary.attended} attended out of ${summary.sessions} sessions. Attendance: ${escapeHtml(percent)}.</p>`;
  if (!report.records.length) {
    document.querySelector("#attendance-table").innerHTML = "<p>No attendance sessions have been recorded.</p>";
    return;
  }
  document.querySelector("#attendance-table").innerHTML = `<table><thead><tr><th>Date</th><th>Subject</th><th>Status</th></tr></thead><tbody>
    ${report.records.map((row) => `<tr><td>${escapeHtml(row.session_date)}</td><td>${escapeHtml(row.subject_name)}</td><td>${chip(row.status)}</td></tr>`).join("")}
  </tbody></table>`;
}

function renderConcerns(rows) {
  const target = document.querySelector("#concern-list");
  if (!rows.length) {
    target.innerHTML = "<p>You have not reported a difficulty yet.</p>";
    return;
  }
  target.innerHTML = rows.map((row) => `
    <article class="concern">
      <strong>${escapeHtml(row.subject_name)} · ${escapeHtml(row.topic)}</strong>
      ${chip(row.status)} ${chip(row.priority)}
      <p>${escapeHtml(row.description)}</p>
      <p class="hint">Concept: ${escapeHtml(row.concept)}</p>
      ${(row.updates || []).map((item) => `<p><strong>${escapeHtml(item.kind)}</strong> ${escapeHtml(item.message)}</p>`).join("")}
      ${(row.resources || []).map((item) => {
        const href = safeHref(item.url);
        const title = escapeHtml(item.title);
        const link = href ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${title}</a>` : title;
        return `<p>${link} ${chip(item.verification_status)}</p>`;
      }).join("")}
      <div class="button-row"><button type="button" class="secondary" data-panel="resources">See learning resources</button></div>
    </article>`).join("");
}

function renderResources(rows) {
  const target = document.querySelector("#resource-list");
  if (!rows.length) {
    target.innerHTML = "<p>No stored resources match a subject that currently needs support.</p>";
    return;
  }
  target.innerHTML = `<ul class="list">${rows.map((row) => {
    const href = safeHref(row.url);
    const title = escapeHtml(row.title);
    const link = href ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${title}</a>` : title;
    return `<li>${link}
    ${chip(row.resource_type)} ${chip(row.verification_status)}
    <div class="hint">${escapeHtml(row.subject_name)} · ${escapeHtml(row.description)}</div></li>`;
  }).join("")}</ul>`;
}

async function loadStudent() {
  const account = await requireRole("student");
  if (!account) return;
  document.querySelector("#student-name").textContent = account.student.full_name;
  const [results, attendance, concerns, resources, videos, plan, subjects] = await Promise.all([
    request("/me/results"),
    request("/me/attendance"),
    request("/me/concerns"),
    request("/me/resources"),
    request("/me/videos"),
    request("/me/study-plan"),
    request("/me/subjects"),
  ]);
  const programme = results.academic_report || {};
  const attendanceText = attendance.summary.percentage === null ? "No sessions" : `${attendance.summary.percentage}%`;
  const openConcerns = concerns.filter((row) => row.status !== "resolved");
  document.querySelector("#overview-stats").innerHTML = `
    <article><strong>${escapeHtml(programme.semester || "Semester 1")}</strong><span>${escapeHtml(programme.department || "Computer Science")}</span></article>
    <article><strong>${escapeHtml(attendanceText)}</strong><span>Attendance</span></article>
    <article><strong>${openConcerns.length}</strong><span>Open concerns</span></article>`;
  document.querySelector("#overview-concerns").innerHTML = openConcerns.length
    ? `<p class="card">${openConcerns.length} reported difficult${openConcerns.length === 1 ? "y is" : "ies are"} still open. <button type="button" data-panel="concerns">Open my concerns</button></p>`
    : "";
  renderResults(results);
  renderAttendance(attendance);
  renderConcerns(concerns);
  renderResources(resources);
  renderVideos(videos);
  renderLocalReport(results, attendance, concerns);
  showStoredPlan(plan);
  const select = document.querySelector("#concern-subject");
  select.innerHTML = subjects.map((row) => `<option value="${row.id}">${escapeHtml(row.code)} · ${escapeHtml(row.name)}</option>`).join("");
  const profile = account.student;
  document.querySelector("#profile-name").value = profile.full_name;
  document.querySelector("#profile-email").value = profile.email;
  document.querySelector("#profile-programme").textContent =
    `${profile.department || "Computer Science"} · ${profile.year_or_semester || "Semester 1"}`;
}

function showPanel(name, scrollTarget) {
  const panel = document.querySelector(`#${name}`);
  if (!panel) return;
  document.querySelectorAll(".panel").forEach((item) => item.classList.remove("active"));
  document.querySelectorAll("#student-nav button").forEach((item) => {
    item.classList.remove("active");
    item.removeAttribute("aria-current");
  });
  panel.classList.add("active");
  const navButton = document.querySelector(`#student-nav button[data-panel="${name}"]`);
  if (navButton) {
    navButton.classList.add("active");
    navButton.setAttribute("aria-current", "true");
  }
  if (scrollTarget) {
    document.querySelector(scrollTarget)?.scrollIntoView({ block: "start" });
  }
}

document.querySelector("#student-nav").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-panel]");
  if (!button) return;
  showPanel(button.dataset.panel);
});

document.querySelector("main").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-panel]");
  if (!button || button.closest("#student-nav")) return;
  showPanel(button.dataset.panel, button.dataset.scroll);
});

document.querySelector("#logout").addEventListener("click", () => logout("/login"));

document.querySelector("#concern-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  show("Saving the concern…");
  try {
    await request("/me/concerns", {
      method: "POST",
      body: JSON.stringify({
        subject_id: Number(document.querySelector("#concern-subject").value),
        topic: document.querySelector("#concern-topic").value,
        description: document.querySelector("#concern-description").value,
        concept: document.querySelector("#concern-concept").value,
        assistance_type: document.querySelector("#concern-help").value,
        preferred_format: document.querySelector("#concern-format").value,
        priority: document.querySelector("#concern-priority").value,
      }),
    });
    event.target.reset();
    await loadStudent();
    show("Concern submitted.", true);
  } catch (error) {
    show(error.message);
  }
});

document.querySelector("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await request("/me", {
      method: "PUT",
      body: JSON.stringify({
        full_name: document.querySelector("#profile-name").value,
        email: document.querySelector("#profile-email").value,
      }),
    });
    await loadStudent();
    show("Profile saved.", true);
  } catch (error) {
    show(error.message);
  }
});

function outlineToText(outline) {
  if (!outline) return "";
  if (outline.source === "student_edit") return outline.note || "";
  const lines = (outline.items || []).map((item) => `${item.day}: ${item.activity}`);
  return [outline.note || "", ...lines].filter((line) => line).join("\n\n");
}

let currentOutline = null;
let savedPlan = null;
let planTouched = false;
let replaceSuggestion = false;

function formatStoredTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function sourceDescription(stored) {
  const source = stored && stored.outline ? stored.outline.source : "";
  const when = formatStoredTime(stored && stored.created_at);
  if (source === "student_edit") {
    return when
      ? `This is a plan you saved. Last saved ${when}.`
      : "This is a plan you saved. The saved time is not available.";
  }
  if (source === "academic_rules") {
    return when
      ? `This is suggested guidance calculated from your results and reported difficulties. It was stored ${when}.`
      : "This is suggested guidance calculated from your results and reported difficulties. The stored time is not available.";
  }
  if (source === "demo_seed") {
    return when
      ? `This plan was stored with the demonstration records on ${when}. It is not a plan you wrote.`
      : "This plan was stored with the demonstration records. It is not a plan you wrote. The stored time is not available.";
  }
  if (source) {
    return when
      ? `A plan is stored. The recorded source is ${source}. Stored ${when}.`
      : `A plan is stored. The recorded source is ${source}. The stored time is not available.`;
  }
  return when
    ? `A plan is stored. Stored ${when}.`
    : "A plan is stored. Its source and stored time are not available.";
}

function showStoredPlan(plan) {
  currentOutline = plan.current_outline || null;
  const stored = plan.stored || null;
  const incoming = stored ? outlineToText(stored.outline) : "";
  const box = document.querySelector("#plan-text");
  const baseline = savedPlan ? savedPlan.text : "";
  const dirty = planTouched && box.value.trim() !== baseline.trim();
  savedPlan = stored ? { text: incoming, raw: stored } : null;
  if (!dirty) {
    box.value = incoming;
    planTouched = false;
  }
  updatePlanState();
}

function updatePlanState() {
  const box = document.querySelector("#plan-text");
  const trimmed = box.value.trim();
  const baseline = savedPlan ? savedPlan.text.trim() : "";
  const dirty = trimmed !== baseline;
  const meta = document.querySelector("#plan-meta");
  const dirtyEl = document.querySelector("#plan-dirty");
  document.querySelector("#plan-empty").hidden = Boolean(savedPlan) || Boolean(trimmed);
  if (savedPlan) meta.textContent = sourceDescription(savedPlan.raw);
  else if (trimmed) meta.textContent = "This text is a suggestion in the box. It is not saved yet.";
  else meta.textContent = "";
  if (!trimmed && !savedPlan) {
    dirtyEl.textContent = "";
    dirtyEl.className = "message";
  } else if (dirty) {
    dirtyEl.className = "message";
    dirtyEl.textContent = savedPlan
      ? "You have unsaved changes. The plan in the database stays as it is until you save."
      : "This suggestion is not saved yet.";
  } else {
    dirtyEl.className = "message ok";
    dirtyEl.textContent = "The text matches your saved plan.";
  }
}

function renderLocalReport(results, attendance, concerns) {
  const summary = attendance.summary || {};
  const concernItems = (concerns || []).length
    ? concerns.map((item) => `<li>${escapeHtml(item.subject_name)}: ${escapeHtml(item.topic)}. ${escapeHtml(item.description)} Status: ${escapeHtml(item.status)}.</li>`).join("")
    : "<li>No difficulty concerns are stored.</li>";
  const attendanceText = summary.percentage === null || summary.percentage === undefined
    ? "unavailable"
    : `${summary.percentage}%`;
  document.querySelector("#report-official").innerHTML = `
    <h3>Official records</h3>
    <p class="hint">The internal assessment, external examination, and final subject tables are shown once above. A missing assessment is incomplete, not zero.</p>
    <p>Attendance: ${escapeHtml(summary.attended ?? 0)} present of ${escapeHtml(summary.sessions ?? 0)} sessions (${escapeHtml(attendanceText)}).</p>
    <h3>Reported difficulty concerns</h3>
    <ul>${concernItems}</ul>`;
}

function inlineMarkup(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderParagraphs(text) {
  const blocks = String(text || "").trim().split(/\n{2,}/).filter((block) => block.trim());
  if (!blocks.length) return "<p>No text was returned.</p>";
  return blocks.map((block) => {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    const parts = [];
    let list = [];
    const flush = () => {
      if (!list.length) return;
      parts.push(`<ul>${list.map((line) => `<li>${inlineMarkup(line.replace(/^([-*]|\d+\.)\s+/, ""))}</li>`).join("")}</ul>`);
      list = [];
    };
    lines.forEach((line) => {
      if (/^([-*]|\d+\.)\s+/.test(line)) list.push(line);
      else {
        flush();
        parts.push(`<p>${inlineMarkup(line)}</p>`);
      }
    });
    flush();
    return parts.join("");
  }).join("");
}

function safeHref(url) {
  const value = String(url || "").trim();
  return /^https?:\/\//i.test(value) ? escapeHtml(value) : "";
}

function attentionResults(facts) {
  return (facts.results || []).filter((row) => row.official_status === "fail" || row.guidance_label === "needs_attention");
}

function renderSuggestions(facts, narrative) {
  const weak = attentionResults(facts);
  const priority = [...weak].sort((left, right) => Number(left.percentage) - Number(right.percentage))[0];
  const incomplete = (facts.results || []).filter((row) => row.official_status === "incomplete");
  const incompleteItems = incomplete.length
    ? incomplete.map((row) => `<li>${escapeHtml(row.subject)} is incomplete. A missing CAT, assignment, or external mark is not treated as zero, so no official grade is shown.</li>`).join("")
    : "";
  const priorityHtml = priority
    ? `<h3>Priority subject</h3><p>${escapeHtml(priority.subject)} — ${escapeHtml(priority.examination)}: final ${escapeHtml(priority.final_mark || priority.marks_obtained)} / ${escapeHtml(priority.maximum_marks)}. Grade ${escapeHtml(priority.grade || "not available")}. Official status ${escapeHtml(priority.official_status)}. Guidance ${escapeHtml(priority.guidance_label)}.</p>`
    : "<h3>Priority subject</h3><p>No stored result is an official fail or below the needs-attention guidance threshold.</p>";
  const concerns = facts.concerns || [];
  const feedback = facts.student_reported_feedback || [];
  const resources = facts.stored_resources || [];
  const subjectItems = weak.length
    ? weak.map((row) => `<li>${escapeHtml(row.subject)} — ${escapeHtml(row.examination)}: ${escapeHtml(row.marks_obtained)} / ${escapeHtml(row.maximum_marks)} (${escapeHtml(row.percentage)}), official status ${escapeHtml(row.official_status)}, guidance ${escapeHtml(row.guidance_label)}.</li>`).join("")
    : "<li>No stored result is an official fail or below the needs-attention guidance threshold.</li>";
  const topics = [];
  concerns.forEach((item) => {
    if (item.topic) topics.push(`${item.subject || "Concern"}: ${item.topic}`);
    if (item.concept) topics.push(`${item.subject || "Concern"}: ${item.concept}`);
  });
  feedback.forEach((item) => {
    if (item.reported_difficulty) topics.push(`${item.subject || "Feedback"}: ${item.reported_difficulty}`);
  });
  const topicItems = topics.length
    ? topics.map((topic) => `<li>${escapeHtml(topic)}</li>`).join("")
    : "<li>No revision topics are stored in concerns or feedback.</li>";
  const reasons = [
    ...weak.map((row) => `${row.subject} needs attention because the stored result is ${row.marks_obtained}/${row.maximum_marks} (${row.percentage}), official status ${row.official_status}.`),
    ...concerns.map((item) => `${item.subject || "A concern"}: the student reported “${item.topic || "a topic"}”. ${item.description || ""}`.trim()),
  ];
  const reasonItems = reasons.length
    ? reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")
    : "<li>No mark or concern gives a reason for extra revision.</li>";
  const resourceItems = resources.length
    ? resources.map((item) => {
      const href = safeHref(item.url);
      const title = escapeHtml(item.title);
      const link = href ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${title}</a>` : title;
      return `<li>${link} — ${escapeHtml(item.subject)} / ${escapeHtml(item.topic)} (${escapeHtml(item.verification_status)}).</li>`;
    }).join("")
    : "<li>No resources were selected for a failed or reported subject.</li>";
  return `
    ${priorityHtml}
    ${incompleteItems ? `<h3>Incomplete assessments</h3><ul>${incompleteItems}</ul>` : ""}
    <h3>Subjects requiring attention</h3>
    <ul>${subjectItems}</ul>
    <h3>Topics to revise</h3>
    <ul>${topicItems}</ul>
    <h3>Reasons from stored marks and concerns</h3>
    <ul>${reasonItems}</ul>
    <h3>Resources already in the database</h3>
    <ul>${resourceItems}</ul>
    <h3>Practical next steps</h3>
    <p class="hint">${escapeHtml(facts.notice || "Generated by the local model. This is not an official academic result.")}</p>
    ${renderParagraphs(narrative)}`;
}

function renderExplanation(answer) {
  return `
    <h3>Explanation</h3>
    <p class="hint">${escapeHtml(answer.notice || "Generated by the local model. This is not an official academic result.")}</p>
    ${renderParagraphs(answer.narrative)}`;
}

let assistantRequest = null;
let savePending = false;
const ASSISTANT_TIMEOUT_MS = 190000;

function setButtonBusy(button, busy, busyLabel) {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyLabel : button.dataset.label;
}

async function runAssistant(button, path, body, target, busyLabel, render) {
  if (assistantRequest) {
    target.innerHTML = "<p class=\"message\">An assistant request is already running. Wait for it to finish.</p>";
    return;
  }
  assistantRequest = path;
  setButtonBusy(button, true, busyLabel);
  target.innerHTML = `<p class="message">${escapeHtml(busyLabel)}</p>`;
  try {
    const answer = await request(path, {
      method: "POST",
      body: JSON.stringify(body || {}),
      timeoutMs: ASSISTANT_TIMEOUT_MS,
    });
    if (!answer || !String(answer.narrative || "").trim()) {
      target.innerHTML = "<p class=\"message\">The assistant returned an empty answer. Your records were not changed.</p>";
      return;
    }
    target.innerHTML = render(answer);
  } catch (error) {
    target.innerHTML = `<p class="message">${escapeHtml(error.message || "The assistant request failed.")}</p>`;
  } finally {
    assistantRequest = null;
    setButtonBusy(button, false, busyLabel);
  }
}

document.querySelector("#plan-text").addEventListener("input", () => {
  planTouched = true;
  replaceSuggestion = false;
  updatePlanState();
});

document.querySelector("#generate-plan").addEventListener("click", () => {
  const status = document.querySelector("#plan-status");
  const suggestion = outlineToText(currentOutline).trim();
  status.className = "message";
  if (!suggestion) {
    status.textContent = "There is not enough stored information to suggest a plan yet.";
    return;
  }
  const box = document.querySelector("#plan-text");
  const baseline = savedPlan ? savedPlan.text.trim() : "";
  if (box.value.trim() !== baseline && !replaceSuggestion) {
    replaceSuggestion = true;
    status.textContent = "The box has unsaved changes. Choose Generate a suggested study plan again to replace that text. Your saved plan stays stored until you save.";
    return;
  }
  replaceSuggestion = false;
  box.value = suggestion;
  planTouched = true;
  status.textContent = "A suggestion is in the box. It is labeled as guidance. Save it only if you want to keep this version.";
  updatePlanState();
});

document.querySelector("#save-plan").addEventListener("click", async () => {
  const button = document.querySelector("#save-plan");
  const status = document.querySelector("#plan-status");
  const text = document.querySelector("#plan-text").value.trim();
  if (savePending) return;
  status.className = "message";
  if (!text) {
    status.textContent = "Write a study plan before saving.";
    return;
  }
  savePending = true;
  setButtonBusy(button, true, "Saving…");
  status.textContent = "Saving the study plan…";
  try {
    await request("/me/study-plan", {
      method: "POST",
      body: JSON.stringify({ outline_text: text }),
    });
    const confirmed = await request("/me/study-plan");
    const stored = confirmed && confirmed.stored;
    if (!stored || !stored.outline || stored.outline.source !== "student_edit" || stored.outline.note !== text) {
      status.textContent = "The server did not confirm the saved plan. It was not marked as saved.";
      return;
    }
    savedPlan = { text: outlineToText(stored.outline), raw: stored };
    document.querySelector("#plan-text").value = savedPlan.text;
    planTouched = false;
    replaceSuggestion = false;
    updatePlanState();
    status.className = "message ok";
    status.textContent = "Study plan saved.";
  } catch (error) {
    status.className = "message";
    status.textContent = error.message || "The study plan could not be saved.";
  } finally {
    savePending = false;
    setButtonBusy(button, false, "Saving…");
  }
});

document.querySelector("#explain-plan").addEventListener("click", () => {
  const planText = document.querySelector("#plan-text").value.trim();
  const target = document.querySelector("#plan-explanation");
  if (!planText) {
    target.innerHTML = "<p class=\"message\">Generate or write a study plan before asking for an explanation.</p>";
    return;
  }
  runAssistant(
    document.querySelector("#explain-plan"),
    "/me/assistant/plan",
    { plan_text: planText },
    target,
    "Generating explanation…",
    renderExplanation,
  );
});
document.querySelector("#revision-suggestions").addEventListener("click", () => {
  runAssistant(
    document.querySelector("#revision-suggestions"),
    "/me/assistant/suggestions",
    {},
    document.querySelector("#revision-result"),
    "Generating revision suggestions…",
    (answer) => renderSuggestions({ ...answer.facts, notice: answer.notice }, answer.narrative),
  );
});
document.querySelector("#academic-report").addEventListener("click", () => {
  runAssistant(
    document.querySelector("#academic-report"),
    "/me/assistant/report",
    {},
    document.querySelector("#report-result"),
    "Generating academic report…",
    (answer) => `<h3>Explanation from the local model</h3>
      <p class="hint">${escapeHtml(answer.notice || "")} Model: ${escapeHtml(answer.model || "")}.</p>
      ${renderParagraphs(answer.narrative)}`,
  );
});

let lastExchange = null;

function questionForAssistant(text) {
  const trimmed = text.trim();
  if (!lastExchange) return trimmed;
  const followUp = `Follow-up.\nPrevious question: ${lastExchange.question}\nPrevious answer: ${lastExchange.answer.slice(0, 350)}\nNew question: ${trimmed}`;
  return followUp.length <= 1000 ? followUp : trimmed;
}

document.querySelector("#example-questions").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-question]");
  if (!button) return;
  const box = document.querySelector("#question");
  box.value = button.dataset.question;
  box.focus();
});

document.querySelector("#ask-button").addEventListener("click", async () => {
  const button = document.querySelector("#ask-button");
  const status = document.querySelector("#ask-status");
  const target = document.querySelector("#ask-result");
  const asked = document.querySelector("#question").value.trim();
  status.className = "message";
  if (!asked) {
    status.textContent = "Write a question before asking.";
    return;
  }
  if (assistantRequest) {
    status.textContent = "An assistant request is already running. Wait for it to finish.";
    return;
  }
  assistantRequest = "/me/assistant/ask";
  setButtonBusy(button, true, "Asking the local assistant…");
  status.textContent = "Asking the local assistant…";
  try {
    const answer = await request("/me/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ question: questionForAssistant(asked) }),
      timeoutMs: ASSISTANT_TIMEOUT_MS,
    });
    if (!answer || !String(answer.narrative || "").trim()) {
      status.textContent = "The assistant returned an empty answer. Your records were not changed.";
      return;
    }
    lastExchange = { question: asked, answer: answer.narrative };
    const block = document.createElement("article");
    block.className = "card exchange";
    block.innerHTML = `<h3>You asked</h3><p>${escapeHtml(asked)}</p>${renderExplanation(answer)}`;
    target.appendChild(block);
    document.querySelector("#question").value = "";
    document.querySelector("#question").placeholder = "Ask a follow-up question";
    status.className = "message ok";
    status.textContent = "Answer ready. You can ask a follow-up.";
    block.scrollIntoView({ block: "nearest" });
  } catch (error) {
    status.className = "message";
    status.textContent = error.message || "The assistant request failed.";
  } finally {
    assistantRequest = null;
    setButtonBusy(button, false, "Asking the local assistant…");
  }
});

loadStudent().catch((error) => show(error.message));
