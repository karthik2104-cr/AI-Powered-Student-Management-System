const pageMessage = document.querySelector("#page-message");
const state = { students: [], subjects: [], allSubjects: [], exams: [], resources: [] };
const EXAM_NAMES = {
  fat: "FAT",
  assignment: "Assignment",
  end_semester: "End Semester Examination",
};
const EXAM_NOTES = {
  fat: "FAT is the formative assessment. The three CAT scores stay in the internal assessment.",
  assignment: "Assignment scores stay in the internal assessment, paired with each CAT.",
  end_semester: "End Semester Examination is the external raw mark out of 100.",
};
const registrationState = { page: 1, pageSize: 8, total: 0 };

function show(text, ok) {
  pageMessage.textContent = text || "";
  pageMessage.className = ok ? "message ok" : "message";
}

function options(rows, label) {
  return rows.map((row) => `<option value="${row.id}">${escapeHtml(label(row))}</option>`).join("");
}

function fillSelects() {
  const studentOptions = options(state.students, (row) => `${row.admission_number} · ${row.full_name}${row.is_demo ? " (demo)" : ""}`);
  const subjectOptions = options(state.subjects, (row) => `${row.code} · ${row.name}`);
  const examOptions = options(state.exams, (row) => row.held_on ? `${row.name} · ${row.held_on}` : row.name);
  ["mark-student", "assessment-student", "attendance-student"].forEach((id) => { document.querySelector(`#${id}`).innerHTML = studentOptions; });
  ["mark-subject", "assessment-subject", "attendance-subject", "resource-subject"].forEach((id) => { document.querySelector(`#${id}`).innerHTML = subjectOptions; });
  document.querySelector("#mark-exam").innerHTML = examOptions;
}

function renderStudents() {
  const list = document.querySelector("#student-list");
  if (!state.students.length) {
    list.innerHTML = "<li>No students are stored yet.</li>";
    return;
  }
  list.innerHTML = state.students.map((row) => `
    <li>
      <button type="button" data-id="${row.id}">${escapeHtml(row.full_name)}</button>
      <div class="hint">${escapeHtml(row.admission_number)} · ${escapeHtml(row.email)} ${row.is_demo ? chip("demo") : ""} ${row.is_active ? "" : chip("inactive")}</div>
    </li>`).join("");
}

async function loadReference() {
  const [summary, students, subjects, allSubjects, exams, resources] = await Promise.all([
    request("/summary"),
    request("/students?q=" + encodeURIComponent(document.querySelector("#student-search").value || "")),
    request("/subjects"),
    request("/subjects?include_inactive=true"),
    request("/examinations"),
    request("/resources"),
  ]);
  state.students = students;
  state.subjects = subjects;
  state.allSubjects = allSubjects;
  state.exams = exams;
  state.resources = resources;
  const performance = summary.performance || {};
  document.querySelector("#stats").innerHTML = `
    <article><strong>${summary.students}</strong><span>Students</span></article>
    <article><strong>${summary.active_students}</strong><span>Active students</span></article>
    <article><strong>${summary.demo_students}</strong><span>Demo students</span></article>
    <article><strong>${summary.subjects}</strong><span>Subjects</span></article>
    <article><strong>${summary.examinations}</strong><span>Exams</span></article>
    <article><strong>${summary.marks}</strong><span>Marks</span></article>
    <article><strong>${summary.attendance_present}/${summary.attendance_sessions}</strong><span>Attendance present</span></article>
    <article><strong>${performance.pass || 0}</strong><span>Pass results</span></article>
    <article><strong>${performance.fail || 0}</strong><span>Fail results</span></article>
    <article><strong>${summary.open_concerns}</strong><span>Open concerns</span></article>
    <article><strong>${summary.resolved_concerns}</strong><span>Resolved concerns</span></article>
    <article><strong>${summary.subjects_needing_support}</strong><span>Subjects needing support</span></article>`;
  document.querySelector("#demo-indicator").textContent =
    `${summary.demo_students} demo student records are labeled separately from other registrations. Counts come from PostgreSQL.`;
  const recent = summary.recent_registrations || [];
  document.querySelector("#recent-registrations").innerHTML = recent.length
    ? `<ul class="list">${recent.map((row) => `<li>${escapeHtml(row.full_name || "Student")} · ${escapeHtml(row.email)} ${row.is_demo ? chip("demo") : ""}<div class="hint">${escapeHtml(row.registered_at)}</div></li>`).join("")}</ul>`
    : "<p>No student logins have been created yet.</p>";
  const difficult = summary.difficult_subjects || [];
  document.querySelector("#difficult-subjects").innerHTML = difficult.length
    ? `<ul class="list">${difficult.map((row) => `<li>${escapeHtml(row.subject)} · ${row.concerns} concern${row.concerns === 1 ? "" : "s"}</li>`).join("")}</ul>`
    : "<p>No concerns have been stored yet.</p>";
  fillSelects();
  renderStudents();
  document.querySelector("#academic-lists").innerHTML = `
    <h3>Subjects</h3>
    <ul class="list">${allSubjects.map((row) => `<li>
      <button type="button" data-edit-subject="${row.id}">${escapeHtml(row.code)} · ${escapeHtml(row.name)}</button>
      ${row.is_active ? chip("active") : chip("inactive")}
      <button type="button" class="secondary" data-toggle-subject="${row.id}">${row.is_active ? "Deactivate" : "Activate"}</button>
      <button type="button" class="secondary" data-remove-subject="${row.id}">Remove</button>
    </li>`).join("") || "<li>No subjects yet.</li>"}</ul>
    <h3>Exams</h3>
    <p class="hint">Only FAT, Assignment, and End Semester Examination are examination types. A subject name is not an examination type.</p>
    <ul class="list">${exams.map((row) => `<li><button type="button" data-edit-exam="${row.id}">${escapeHtml(row.name)}</button> <span class="hint">${escapeHtml(row.held_on || "Date not set")}</span></li>`).join("") || "<li>No examination types yet.</li>"}</ul>`;
  const subjectFilter = document.querySelector("#filter-subject");
  const selectedSubject = subjectFilter.value;
  subjectFilter.innerHTML = `<option value="">Any</option>` + subjects.map((row) => `<option value="${row.id}">${escapeHtml(row.code)}</option>`).join("");
  subjectFilter.value = selectedSubject;
  document.querySelector("#resource-admin-list").innerHTML = resources.length
    ? `<ul class="list">${resources.map((row) => `<li>${escapeHtml(row.title)} ${chip(row.resource_type)} ${chip(row.verification_status)}<div class="hint">${escapeHtml(row.author || "Publisher not stored")} · ${escapeHtml(row.url)}</div></li>`).join("")}</ul>`
    : "<p>No resources are stored yet.</p>";
}

async function loadConcerns() {
  const status = document.querySelector("#filter-status").value;
  const priority = document.querySelector("#filter-priority").value;
  const subject = document.querySelector("#filter-subject").value;
  const dateFrom = document.querySelector("#filter-from").value;
  const dateTo = document.querySelector("#filter-to").value;
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (priority) params.set("priority", priority);
  if (subject) params.set("subject_id", subject);
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const rows = await request("/concerns?" + params.toString());
  const target = document.querySelector("#concern-admin-list");
  if (!rows.length) {
    target.innerHTML = "<p>No concerns match this filter.</p>";
    return;
  }
  target.innerHTML = rows.map((row) => `
    <article class="concern" data-concern="${row.id}">
      <strong>${escapeHtml(row.student_name)} · ${escapeHtml(row.subject_name)} · ${escapeHtml(row.topic)}</strong>
      ${chip(row.status)} ${chip(row.priority)}
      <p>${escapeHtml(row.description)}</p>
      <p class="hint">Concept: ${escapeHtml(row.concept)}. Requested: ${escapeHtml(row.assistance_type)}.</p>
      <label>Reply</label>
      <textarea data-reply></textarea>
      <label>New status</label>
      <select data-status>
        <option value="">Keep current</option>
        <option>under_review</option>
        <option>resources_recommended</option>
        <option>in_progress</option>
        <option>resolved</option>
        <option>closed</option>
      </select>
      <label>Recommend a stored resource</label>
      <select data-resource><option value="">None</option>${state.resources.filter((item) => item.subject_id === row.subject_id).map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("")}</select>
      <div class="button-row">
        <button type="button" data-save-concern="${row.id}">Save response</button>
        <button type="button" class="secondary" data-draft="${row.id}">Draft with assistant</button>
      </div>
      <p data-draft-output></p>
    </article>`).join("");
}

async function loadAudit() {
  const rows = await request("/audit-logs");
  document.querySelector("#audit-list").innerHTML = rows.length
    ? `<ul class="list">${rows.map((row) => `<li><strong>${escapeHtml(row.action)}</strong> ${escapeHtml(row.detail)}<div class="hint">${escapeHtml(row.created_at)}</div></li>`).join("")}</ul>`
    : "<p>No administrative changes have been recorded.</p>";
}

function showPanel(name) {
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
  document.querySelectorAll("#admin-nav button").forEach((item) => item.classList.remove("active"));
  document.querySelector(`#${name}`).classList.add("active");
  const button = document.querySelector(`#admin-nav button[data-panel="${name}"]`);
  if (button) button.classList.add("active");
}

async function loadNotices() {
  const [rows, count] = await Promise.all([
    request("/notifications"),
    request("/notifications/unread-count"),
  ]);
  document.querySelector("#notice-count").textContent = String(count.unread);
  const target = document.querySelector("#notice-list");
  if (!rows.length) {
    target.innerHTML = "<p>No registration notices yet.</p>";
    return;
  }
  target.innerHTML = rows.map((row) => `
    <article class="concern">
      <strong>${escapeHtml(row.full_name)}</strong>
      ${row.is_read ? chip("read") : chip("submitted")}
      <p>${escapeHtml(row.email)} · ${escapeHtml(row.admission_number)} · ${escapeHtml(row.department || "No department")}</p>
      <p class="hint">${escapeHtml(row.year_or_semester || "")} · Registered ${escapeHtml(row.registered_at)}</p>
      <div class="button-row">
        <button type="button" data-open-student="${row.student_id}">Open student</button>
        ${row.is_read ? "" : `<button type="button" class="secondary" data-read-notice="${row.id}">Mark read</button>`}
      </div>
    </article>`).join("");
}

async function loadRegistrations() {
  const params = new URLSearchParams();
  params.set("page", String(registrationState.page));
  params.set("page_size", String(registrationState.pageSize));
  const query = document.querySelector("#registration-search").value;
  const department = document.querySelector("#registration-department").value;
  const active = document.querySelector("#registration-active").value;
  if (query) params.set("q", query);
  if (department) params.set("department", department);
  if (active) params.set("active", active);
  const body = await request("/registrations?" + params.toString());
  registrationState.total = body.total;
  const pages = Math.max(1, Math.ceil(body.total / body.page_size));
  document.querySelector("#registration-page").textContent = `Page ${body.page} of ${pages} · ${body.total} students`;
  const rows = document.querySelector("#registration-rows");
  rows.innerHTML = body.items.length
    ? body.items.map((row) => `
      <tr>
        <td>${escapeHtml(row.full_name)}</td>
        <td>${escapeHtml(row.email)}</td>
        <td>${escapeHtml(row.admission_number)}</td>
        <td>${escapeHtml(row.department || "")}${row.year_or_semester ? " · " + escapeHtml(row.year_or_semester) : ""}</td>
        <td>${escapeHtml(row.registered_at || "No login account")}</td>
        <td>${escapeHtml(row.account_status)}</td>
        <td><button type="button" data-open-student="${row.id}">Open</button></td>
      </tr>`).join("")
    : `<tr><td colspan="7">No students match this search.</td></tr>`;
}

async function openRegistrationStudent(id) {
  const [student, results, attendance, concerns] = await Promise.all([
    request(`/students/${id}`),
    request(`/students/${id}/results`),
    request(`/students/${id}/attendance`),
    request(`/students/${id}/concerns`),
  ]);
  const summary = attendance.summary || {};
  document.querySelector("#registration-detail").innerHTML = `
    <p><strong>${escapeHtml(student.full_name)}</strong> · ${escapeHtml(student.admission_number)}</p>
    <p>${escapeHtml(student.email)} · ${escapeHtml(student.department || "No department")} · ${escapeHtml(student.year_or_semester || "No year")}</p>
    <p>Status: ${student.is_active ? "active" : "inactive"}. ${escapeHtml(student.department || "Computer Science")} · ${escapeHtml(student.year_or_semester || "Semester 1")}.</p>
    <p>Attendance: ${summary.percentage == null ? "not available" : escapeHtml(summary.percentage)} (${summary.attended || 0}/${summary.sessions || 0}). Concerns: ${concerns.length}.</p>`;
  showPanel("registrations");
  await loadRegistrations();
}

document.querySelector("#admin-nav").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-panel]");
  if (!button) return;
  showPanel(button.dataset.panel);
  if (button.dataset.panel === "concerns") loadConcerns().catch((error) => show(error.message));
  if (button.dataset.panel === "marks") {
    loadMarkList().catch((error) => show(error.message));
    loadAssessment(document.querySelector("#assessment-student").value).catch((error) => show(error.message));
  }
  if (button.dataset.panel === "attendance" && document.querySelector("#attendance-student").value) {
    request(`/students/${document.querySelector("#attendance-student").value}/attendance`).then(renderAttendance).catch((error) => show(error.message));
  }
  if (button.dataset.panel === "audit") loadAudit().catch((error) => show(error.message));
  if (button.dataset.panel === "notices") loadNotices().catch((error) => show(error.message));
  if (button.dataset.panel === "registrations") loadRegistrations().catch((error) => show(error.message));
});

document.querySelector("main").addEventListener("click", async (event) => {
  const open = event.target.closest("[data-open-student]");
  if (open) {
    try {
      await openRegistrationStudent(open.dataset.openStudent);
    } catch (error) {
      show(error.message);
    }
    return;
  }
  const read = event.target.closest("[data-read-notice]");
  if (!read) return;
  try {
    await request(`/notifications/${read.dataset.readNotice}/read`, { method: "POST", body: "{}" });
    await loadNotices();
    show("Notification marked read.", true);
  } catch (error) {
    show(error.message);
  }
});

document.querySelector("#logout").addEventListener("click", () => logout("/admin/login"));
document.querySelector("#student-search").addEventListener("input", () => loadReference().catch((error) => show(error.message)));

document.querySelector("#student-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  const student = state.students.find((row) => String(row.id) === button.dataset.id);
  document.querySelector("#student-id").value = student.id;
  document.querySelector("#admission-number").value = student.admission_number;
  document.querySelector("#full-name").value = student.full_name;
  document.querySelector("#email").value = student.email;
  document.querySelector("#department").value = student.department || "";
  document.querySelector("#year").value = student.year_or_semester || "";
  document.querySelector("#is-active").checked = student.is_active;
  const results = await request(`/students/${student.id}/results`);
  document.querySelector("#selected-results").innerHTML = renderAcademicTables(results.academic_report);
});

function recorded(value) {
  return value === null || value === undefined || value === "" ? "Not recorded" : value;
}

function renderAcademicTables(report) {
  if (!report) return "<p>The Semester 1 report is not available.</p>";
  const finalRows = (report.final_results || []).map((row) => `<tr>
      <td>${escapeHtml(row.subject_name)}</td>
      <td>${escapeHtml(recorded(row.internal_mark))}</td>
      <td>${escapeHtml(recorded(row.external_mark))}</td>
      <td>${escapeHtml(recorded(row.final_mark))}</td>
      <td>${escapeHtml(recorded(row.grade))}</td>
      <td>${chip(row.official_status)}</td>
    </tr>`).join("");
  const internalRows = (report.internal_assessments || []).map((row) => `<p>${escapeHtml(row.subject_name)}: CAT ${escapeHtml(recorded(row.cat_1))}, ${escapeHtml(recorded(row.cat_2))}, ${escapeHtml(recorded(row.cat_3))}; assignments ${escapeHtml(recorded(row.assignment_1))}, ${escapeHtml(recorded(row.assignment_2))}, ${escapeHtml(recorded(row.assignment_3))}. Internal ${escapeHtml(recorded(row.internal_mark))} /50. ${escapeHtml(row.assessment_status)}.</p>`).join("");
  return `
    <p class="hint">${escapeHtml(report.department)} · ${escapeHtml(report.semester)}</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Subject</th><th>Internal /50</th><th>External /50</th><th>Final /100</th><th>Grade</th><th>Pass/fail</th></tr></thead>
      <tbody>${finalRows}</tbody>
    </table></div>
    ${internalRows}`;
}

function wholeOrNull(id, maximum) {
  const raw = document.querySelector(id).value.trim();
  if (raw === "") return null;
  if (!/^\d+$/.test(raw) || Number(raw) > maximum) {
    throw new Error(`Enter a whole number from 0 through ${maximum}, or leave the box blank.`);
  }
  return Number(raw);
}

function studentPayload() {
  return {
    admission_number: document.querySelector("#admission-number").value,
    full_name: document.querySelector("#full-name").value,
    email: document.querySelector("#email").value,
    department: "Computer Science",
    year_or_semester: "Semester 1",
    is_active: document.querySelector("#is-active").checked,
  };
}

document.querySelector("#student-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.querySelector("#student-id").value;
  try {
    await request(id ? `/students/${id}` : "/students", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(studentPayload()),
    });
    event.target.reset();
    document.querySelector("#student-id").value = "";
    document.querySelector("#is-active").checked = true;
    await loadReference();
    show("Student saved.", true);
  } catch (error) {
    show(error.message);
  }
});

document.querySelector("#reset-access").addEventListener("click", async () => {
  const id = document.querySelector("#student-id").value;
  if (!id) return show("Select a student first.");
  const password = window.prompt("New password for this student (at least 8 characters). It will not be shown again.");
  if (!password) return;
  try {
    await request(`/students/${id}/access`, { method: "POST", body: JSON.stringify({ password }) });
    show("Student access saved.", true);
  } catch (error) {
    show(error.message);
  }
});

document.querySelector("#deactivate-student").addEventListener("click", async () => {
  const id = document.querySelector("#student-id").value;
  if (!id) return show("Select a student first.");
  try {
    await request(`/students/${id}/deactivate`, { method: "POST", body: "{}" });
    await loadReference();
    show("Student deactivated. Academic rows were kept.", true);
  } catch (error) {
    show(error.message);
  }
});

document.querySelector("#subject-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.querySelector("#subject-id").value;
  try {
    await request(id ? `/subjects/${id}` : "/subjects", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify({
        code: document.querySelector("#subject-code").value,
        name: document.querySelector("#subject-name").value,
        is_active: document.querySelector("#subject-active").checked,
      }),
    });
    event.target.reset();
    document.querySelector("#subject-id").value = "";
    document.querySelector("#subject-active").checked = true;
    await loadReference();
    show("Subject saved.", true);
  } catch (error) { show(error.message); }
});

function selectedExamType() {
  return document.querySelector("#exam-type").value;
}

function showExamNote() {
  const type = selectedExamType();
  document.querySelector("#exam-label").textContent = EXAM_NOTES[type] || "";
}

document.querySelector("#exam-type").addEventListener("change", showExamNote);

document.querySelector("#exam-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const type = selectedExamType();
  const existing = state.exams.find((row) => row.exam_type === type);
  const id = document.querySelector("#exam-id").value || (existing ? String(existing.id) : "");
  try {
    await request(id ? `/examinations/${id}` : "/examinations", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify({
        name: EXAM_NAMES[type],
        exam_type: type,
        held_on: document.querySelector("#exam-date").value || null,
      }),
    });
    event.target.reset();
    document.querySelector("#exam-id").value = "";
    showExamNote();
    await loadReference();
    show("Examination type saved.", true);
  } catch (error) { show(error.message); }
});

document.querySelector("#academic-lists").addEventListener("click", (event) => {
  const subjectButton = event.target.closest("[data-edit-subject]");
  if (subjectButton) {
    const subject = state.allSubjects.find((row) => String(row.id) === subjectButton.dataset.editSubject);
    document.querySelector("#subject-id").value = subject.id;
    document.querySelector("#subject-code").value = subject.code;
    document.querySelector("#subject-name").value = subject.name;
    document.querySelector("#subject-active").checked = Boolean(subject.is_active);
    showPanel("academics");
  }
  const toggleButton = event.target.closest("[data-toggle-subject]");
  if (toggleButton) {
    const subject = state.allSubjects.find((row) => String(row.id) === toggleButton.dataset.toggleSubject);
    request(`/subjects/${subject.id}`, {
      method: "PUT",
      body: JSON.stringify({ code: subject.code, name: subject.name, is_active: !subject.is_active }),
    }).then(() => loadReference()).then(() => show(subject.is_active ? "Subject deactivated." : "Subject activated.", true)).catch((error) => show(error.message));
  }
  const removeButton = event.target.closest("[data-remove-subject]");
  if (removeButton) {
    request(`/subjects/${removeButton.dataset.removeSubject}`, { method: "DELETE" })
      .then(() => loadReference())
      .then(() => show("Subject removed.", true))
      .catch((error) => show(error.message));
  }
  const examButton = event.target.closest("[data-edit-exam]");
  if (examButton) {
    const exam = state.exams.find((row) => String(row.id) === examButton.dataset.editExam);
    document.querySelector("#exam-id").value = exam.id;
    document.querySelector("#exam-type").value = exam.exam_type;
    document.querySelector("#exam-date").value = exam.held_on || "";
    showExamNote();
    showPanel("academics");
  }
});

function fillAssessment(report, subjectId) {
  const internal = (report.internal_assessments || []).find((row) => String(row.subject_id) === String(subjectId));
  const external = (report.external_examinations || []).find((row) => String(row.subject_id) === String(subjectId));
  const fields = [
    ["#cat-1", internal && internal.cat_1],
    ["#assignment-1", internal && internal.assignment_1],
    ["#cat-2", internal && internal.cat_2],
    ["#assignment-2", internal && internal.assignment_2],
    ["#cat-3", internal && internal.cat_3],
    ["#assignment-3", internal && internal.assignment_3],
    ["#external-raw", external && external.external_raw],
  ];
  fields.forEach(([selector, value]) => {
    document.querySelector(selector).value = value === null || value === undefined ? "" : value;
  });
}

async function loadAssessment(studentId) {
  const target = document.querySelector("#assessment-tables");
  if (!studentId) {
    target.innerHTML = "<p>Choose a student to load the Semester 1 report.</p>";
    return;
  }
  const results = await request(`/students/${studentId}/results`);
  target.innerHTML = renderAcademicTables(results.academic_report);
  fillAssessment(results.academic_report, document.querySelector("#assessment-subject").value);
  return results;
}

async function loadMarkList() {
  const studentId = document.querySelector("#mark-student").value;
  const target = document.querySelector("#mark-list");
  if (!studentId) {
    target.innerHTML = "<p>Choose a student to load marks from PostgreSQL.</p>";
    return;
  }
  const results = await request(`/students/${studentId}/results`);
  if (!results.results.length) {
    target.innerHTML = "<p>No earlier examination records are stored for this student.</p>";
    return;
  }
  target.innerHTML = results.results.map((row) => `<p><button type="button" data-edit-mark="${row.mark_id}" data-subject="${row.subject_id}" data-exam="${row.examination_id}" data-obtained="${escapeHtml(row.marks_obtained)}" data-maximum="${escapeHtml(row.maximum_marks)}" data-pass="${row.pass_marks ?? ""}">${escapeHtml(row.subject_name)} · ${escapeHtml(row.examination_name)} · ${escapeHtml(row.marks_obtained)}/${escapeHtml(row.maximum_marks)}</button> ${chip(row.official_status)}</p>`).join("");
}

function renderAttendance(report) {
  const summary = report.summary || {};
  const percent = summary.percentage == null ? "not available" : `${summary.percentage}%`;
  const rows = report.records || [];
  document.querySelector("#attendance-view").innerHTML = `<p>${summary.attended || 0} of ${summary.sessions || 0} sessions attended (${escapeHtml(percent)}).</p>` +
    (rows.length ? rows.map((row) => `<p>${escapeHtml(row.session_date)} · ${escapeHtml(row.subject_name)} ${chip(row.status)} <button type="button" class="secondary" data-attendance-status="${row.id}" data-next="${row.status === "present" ? "absent" : "present"}">Change to ${row.status === "present" ? "absent" : "present"}</button></p>`).join("") : "<p>No sessions are stored for this student.</p>");
}

document.querySelector("#assessment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const studentId = document.querySelector("#assessment-student").value;
  try {
    const body = {
      subject_id: Number(document.querySelector("#assessment-subject").value),
      cat_1: wholeOrNull("#cat-1", 50),
      assignment_1: wholeOrNull("#assignment-1", 50),
      cat_2: wholeOrNull("#cat-2", 50),
      assignment_2: wholeOrNull("#assignment-2", 50),
      cat_3: wholeOrNull("#cat-3", 50),
      assignment_3: wholeOrNull("#assignment-3", 50),
    };
    const external = {
      subject_id: body.subject_id,
      raw_mark: wholeOrNull("#external-raw", 100),
    };
    await request(`/students/${studentId}/internal-assessment`, { method: "PUT", body: JSON.stringify(body) });
    const report = await request(`/students/${studentId}/external-examination`, { method: "PUT", body: JSON.stringify(external) });
    document.querySelector("#assessment-tables").innerHTML = renderAcademicTables(report);
    show("Assessment saved.", true);
  } catch (error) {
    show(error.message);
  }
});
document.querySelector("#assessment-student").addEventListener("change", () => {
  loadAssessment(document.querySelector("#assessment-student").value).catch((error) => show(error.message));
});
document.querySelector("#assessment-subject").addEventListener("change", () => {
  loadAssessment(document.querySelector("#assessment-student").value).catch((error) => show(error.message));
});
document.querySelector("#mark-student").addEventListener("change", () => loadMarkList().catch((error) => show(error.message)));
document.querySelector("#mark-clear").addEventListener("click", () => {
  document.querySelector("#mark-id").value = "";
  document.querySelector("#mark-form").reset();
});
document.querySelector("#mark-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-edit-mark]");
  if (!button) return;
  document.querySelector("#mark-id").value = button.dataset.editMark;
  document.querySelector("#mark-subject").value = button.dataset.subject;
  document.querySelector("#mark-exam").value = button.dataset.exam;
  document.querySelector("#marks-obtained").value = button.dataset.obtained;
  document.querySelector("#maximum-marks").value = button.dataset.maximum;
  document.querySelector("#pass-marks").value = button.dataset.pass;
});

document.querySelector("#mark-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const obtained = Number(document.querySelector("#marks-obtained").value);
  const maximum = Number(document.querySelector("#maximum-marks").value);
  if (Number.isNaN(obtained) || Number.isNaN(maximum) || obtained > maximum) {
    show("Marks obtained cannot be greater than the maximum.");
    return;
  }
  const pass = document.querySelector("#pass-marks").value;
  const id = document.querySelector("#mark-id").value;
  const payload = {
    student_id: Number(document.querySelector("#mark-student").value),
    subject_id: Number(document.querySelector("#mark-subject").value),
    examination_id: Number(document.querySelector("#mark-exam").value),
    marks_obtained: document.querySelector("#marks-obtained").value,
    maximum_marks: document.querySelector("#maximum-marks").value,
    pass_marks: pass === "" ? null : pass,
  };
  try {
    await request(id ? `/marks/${id}` : "/marks", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) });
    document.querySelector("#mark-id").value = "";
    await loadMarkList();
    await loadReference();
    show("Mark saved.", true);
  } catch (error) { show(error.message); }
});

document.querySelector("#attendance-student").addEventListener("change", async () => {
  const studentId = document.querySelector("#attendance-student").value;
  if (!studentId) return;
  try {
    renderAttendance(await request(`/students/${studentId}/attendance`));
  } catch (error) { show(error.message); }
});

document.querySelector("#attendance-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const studentId = document.querySelector("#attendance-student").value;
  try {
    const report = await request("/attendance", { method: "POST", body: JSON.stringify({
      student_id: Number(studentId),
      subject_id: Number(document.querySelector("#attendance-subject").value),
      session_date: document.querySelector("#attendance-date").value,
      status: document.querySelector("#attendance-status").value,
    }) });
    renderAttendance(report);
    await loadReference();
    show("Attendance saved.", true);
  } catch (error) { show(error.message); }
});

document.querySelector("#attendance-view").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-attendance-status]");
  if (!button) return;
  try {
    const report = await request(`/attendance/${button.dataset.attendanceStatus}`, {
      method: "PUT",
      body: JSON.stringify({ status: button.dataset.next }),
    });
    renderAttendance(report);
    await loadReference();
    show("Attendance updated.", true);
  } catch (error) { show(error.message); }
});

document.querySelector("#refresh-concerns").addEventListener("click", () => loadConcerns().catch((error) => show(error.message)));

document.querySelector("#concern-admin-list").addEventListener("click", async (event) => {
  const save = event.target.closest("[data-save-concern]");
  const draft = event.target.closest("[data-draft]");
  const article = event.target.closest("article");
  if (save) {
    const resource = article.querySelector("[data-resource]").value;
    try {
      await request(`/concerns/${save.dataset.saveConcern}/response`, { method: "POST", body: JSON.stringify({
        message: article.querySelector("[data-reply]").value,
        status: article.querySelector("[data-status]").value || null,
        resource_ids: resource ? [Number(resource)] : [],
      }) });
      await loadConcerns();
      show("Response saved.", true);
    } catch (error) { show(error.message); }
  }
  if (draft) {
    const output = article.querySelector("[data-draft-output]");
    output.textContent = "Drafting…";
    try {
      const answer = await request(`/concerns/${draft.dataset.draft}/assistant/draft`, { method: "POST", body: "{}" });
      output.textContent = `${answer.notice} ${answer.narrative}`;
    } catch (error) { output.textContent = error.message; }
  }
});

document.querySelector("#resource-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const verification = document.querySelector("#resource-verification").value;
    const checked = document.querySelector("#resource-checked").value;
    if (verification === "verified" && !checked) {
      show("A verified resource needs the date the link was checked.");
      return;
    }
    const url = document.querySelector("#resource-url").value.trim();
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      show("The URL must start with http:// or https://.");
      return;
    }
    await request("/resources", { method: "POST", body: JSON.stringify({
      title: document.querySelector("#resource-title").value,
      resource_type: document.querySelector("#resource-type").value,
      author: document.querySelector("#resource-author").value || null,
      subject_id: Number(document.querySelector("#resource-subject").value),
      topic: document.querySelector("#resource-topic").value,
      url,
      description: document.querySelector("#resource-description").value,
      verification_status: verification,
      last_checked: checked || null,
    }) });
    event.target.reset();
    document.querySelector("#resource-verification").value = "unverified";
    await loadReference();
    show(verification === "verified" ? "Verified resource saved." : "Unverified resource saved.", true);
  } catch (error) { show(error.message); }
});

document.querySelector("#load-demo").addEventListener("click", async () => {
  try {
    const result = await request("/demo-data", { method: "POST", body: "{}" });
    await loadReference();
    show(`${result.detail} New students: ${result.students_created}. New logins: ${result.accounts_created}. Repeated rows were skipped.`, true);
  } catch (error) { show(error.message); }
});

document.querySelector("#registration-filter").addEventListener("submit", (event) => {
  event.preventDefault();
  registrationState.page = 1;
  loadRegistrations().catch((error) => show(error.message));
});

document.querySelector("#registration-prev").addEventListener("click", () => {
  if (registrationState.page <= 1) return;
  registrationState.page -= 1;
  loadRegistrations().catch((error) => show(error.message));
});

document.querySelector("#registration-next").addEventListener("click", () => {
  const pages = Math.max(1, Math.ceil(registrationState.total / registrationState.pageSize));
  if (registrationState.page >= pages) return;
  registrationState.page += 1;
  loadRegistrations().catch((error) => show(error.message));
});

document.querySelector("#save-study-plan").addEventListener("click", async () => {
  const id = document.querySelector("#student-id").value;
  if (!id) return show("Select a student first.");
  try {
    const plan = await request(`/students/${id}/study-plan`, { method: "POST", body: "{}" });
    const outline = plan.outline || {};
    document.querySelector("#study-plan-view").textContent = outline.note || "Study outline saved.";
    show("Study outline saved from the academic rules.", true);
  } catch (error) { show(error.message); }
});

const passwordDialog = document.querySelector("#password-dialog");
const accountMenu = document.querySelector("#account-menu");
document.querySelector("#account-menu-button").addEventListener("click", () => {
  const open = accountMenu.hidden;
  accountMenu.hidden = !open;
  document.querySelector("#account-menu-button").setAttribute("aria-expanded", String(open));
});
document.querySelector("#open-password").addEventListener("click", () => {
  accountMenu.hidden = true;
  document.querySelector("#password-required-note").hidden = true;
  document.querySelector("#close-password").hidden = false;
  passwordDialog.showModal();
});
document.querySelector("#close-password").addEventListener("click", () => passwordDialog.close());

document.querySelector("#password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.querySelector("#password-message");
  const next = document.querySelector("#new-password").value;
  if (next !== document.querySelector("#confirm-password").value) {
    message.textContent = "Password confirmation does not match.";
    return;
  }
  message.textContent = "Updating the password…";
  try {
    const result = await request("/auth/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: document.querySelector("#current-password").value,
        new_password: next,
        new_password_confirmation: document.querySelector("#confirm-password").value,
      }),
    });
    event.target.reset();
    message.textContent = "";
    passwordDialog.close();
    show(result.detail, true);
  } catch (error) {
    message.textContent = error.message;
  }
});

requireRole("admin").then((account) => {
  if (!account) return;
  document.querySelector("#account-label").textContent = account.email;
  if (account.must_change_password) {
    document.querySelector("#password-required-note").hidden = false;
    document.querySelector("#close-password").hidden = true;
    passwordDialog.showModal();
  }
  return Promise.all([loadReference(), loadNotices()]);
}).catch((error) => show(error.message));
