"""Choose support subjects, resources, and a simple weekly outline.

These functions use the official results already calculated in Python.
They do not ask the language model to decide who needs help.
"""

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def latest_results_by_subject(results: list[dict]) -> list[dict]:
    """Keep the most recent result for each subject.

    Two results on the same date are both kept out of this choice, because
    their order is unknown. The caller then sees no latest result for that subject.
    """
    grouped: dict[int, list[dict]] = {}
    for result in results:
        grouped.setdefault(result["subject_id"], []).append(result)

    chosen = []
    for subject_results in grouped.values():
        latest_date = max(item["held_on"] for item in subject_results)
        on_latest_date = [item for item in subject_results if item["held_on"] == latest_date]
        if len(on_latest_date) == 1:
            chosen.append(on_latest_date[0])
    chosen.sort(key=lambda item: item["subject_name"])
    return chosen


def needs_support(result: dict) -> bool:
    """A subject needs support when the latest result failed or is below 50%.

    A pass with the developing or strong label is not selected. A missing
    pass mark is selected only when the guidance label is needs_attention.
    """
    return result["official_status"] == "fail" or result["guidance_label"] == "needs_attention"


def subjects_needing_support(results: list[dict]) -> list[dict]:
    """Return the latest result for each subject that currently needs support."""
    return [result for result in latest_results_by_subject(results) if needs_support(result)]


def select_resources(resources: list[dict], results: list[dict]) -> list[dict]:
    """Return stored resources whose subject currently needs support."""
    subject_ids = {result["subject_id"] for result in subjects_needing_support(results)}
    selected = [resource for resource in resources if resource["subject_id"] in subject_ids]
    return sorted(selected, key=lambda resource: (resource["subject_name"], resource["title"]))


def _format_for_subject(subject_id: int, feedback: list[dict]) -> str:
    matches = [
        item["preferred_format"]
        for item in feedback
        if item.get("subject_id") == subject_id and item.get("preferred_format")
    ]
    if matches:
        return matches[-1]
    general = [
        item["preferred_format"]
        for item in feedback
        if item.get("subject_id") is None and item.get("preferred_format")
    ]
    if general:
        return general[-1]
    return "practice questions"


def _topic_for_subject(subject_id: int, feedback: list[dict]) -> str | None:
    topics = [
        item.get("topic")
        for item in feedback
        if item.get("subject_id") == subject_id and item.get("topic")
    ]
    if topics:
        return topics[-1]
    return None


def build_study_outline(results: list[dict], feedback: list[dict]) -> dict:
    """Build a weekday outline from calculated results and reported feedback.

    The text says what the student reported. It does not judge effort or ability.
    """
    focus = subjects_needing_support(results)
    if not focus:
        return {
            "source": "academic_rules",
            "items": [],
            "note": (
                "No latest result is an official fail or below 50%. "
                "This outline is not an official academic decision."
            ),
        }

    items = []
    for index, result in enumerate(focus):
        preferred = _format_for_subject(result["subject_id"], feedback)
        topic = _topic_for_subject(result["subject_id"], feedback)
        if topic:
            focus_text = f"The student reported difficulty with {topic}."
        else:
            focus_text = "No specific topic was reported."
        grade = result.get("grade")
        if grade:
            score_text = (
                f" Internal mark {result.get('internal_mark')} out of 50, "
                f"external mark {result.get('external_mark')} out of 50, "
                f"final mark {result.get('final_mark')} out of 100, grade {grade}."
            )
        else:
            score_text = ""
        items.append(
            {
                "day": DAYS[index % len(DAYS)],
                "subject_id": result["subject_id"],
                "subject_name": result["subject_name"],
                "official_status": result["official_status"],
                "guidance_label": result["guidance_label"],
                "percentage": str(result["percentage"]),
                "grade": grade,
                "activity": (
                    f"Review {result['subject_name']} with {preferred}. {focus_text} "
                    f"The latest official status is {result['official_status']} "
                    f"and the guidance label is {result['guidance_label']}.{score_text}"
                ),
            }
        )
    return {
        "source": "academic_rules",
        "items": items,
        "note": (
            "This outline comes from calculated results and student-reported feedback. "
            "It is editable guidance, not an official academic decision."
        ),
    }
