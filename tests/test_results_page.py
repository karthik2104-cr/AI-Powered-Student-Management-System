"""The student My Results page renders each official table once."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDENT_JS = (ROOT / "static" / "student.js").read_text(encoding="utf-8")
STUDENT_HTML = (ROOT / "static" / "student.html").read_text(encoding="utf-8")
LEGACY_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    next_function = source.find("\nfunction ", start + len(marker))
    return source[start:next_function if next_function != -1 else None]


def test_my_results_has_one_mount_for_the_three_tables():
    assert STUDENT_HTML.count('id="results-table"') == 1
    assert STUDENT_HTML.count('id="academic-report-section"') == 1
    tables = _function_body(STUDENT_JS, "renderAcademicTables")
    for section_id in ("internal-assessment", "external-examination", "final-subject-results"):
        assert tables.count(f'id="{section_id}"') == 1
    rendered = _function_body(STUDENT_JS, "renderResults")
    assert 'querySelector("#results-table").innerHTML' in rendered
    assert "append" not in rendered
    report = _function_body(STUDENT_JS, "renderLocalReport")
    assert "renderAcademicTables" not in report
    assert "innerHTML" in report


def test_legacy_page_does_not_render_a_percentage_result_table():
    rendered = _function_body(LEGACY_JS, "renderResults").split("\n\n", 1)[0]
    assert "result.percentage" not in rendered
    assert "<table" not in rendered
    assert "Official Semester 1 results" in rendered
    mark_handler = LEGACY_JS.split('"#mark-form"', 1)[1].split('"#feedback-form"', 1)[0]
    assert '"/marks"' not in mark_handler
    assert "cannot save marks" in mark_handler
    legacy_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "<fieldset disabled>" in legacy_html
    assert "This page cannot save marks." in legacy_html
