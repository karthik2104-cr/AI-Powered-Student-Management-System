"""Official academic calculations.

These functions use the stored marks. They do not ask a language model to
decide a pass, a fail, a percentage, or a change between examinations.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

# Guidance uses the percentage only. It is not the official result.
# strong: 75% and above
# developing: 50% up to, but not including, 75%
# needs_attention: below 50%
STRONG_PERCENTAGE = Decimal("75.00")
DEVELOPING_PERCENTAGE = Decimal("50.00")
TWO_PLACES = Decimal("0.01")

PASS = "pass"
FAIL = "fail"
NOT_ASSESSED = "not_assessed"

STRONG = "strong"
DEVELOPING = "developing"
NEEDS_ATTENTION = "needs_attention"

IMPROVED = "improved"
DECLINED = "declined"
UNCHANGED = "unchanged"


@dataclass(frozen=True)
class ScoreInput:
    """One stored mark, plus the names needed to explain it."""

    student_id: int
    subject_id: int
    subject_code: str
    subject_name: str
    examination_id: int
    examination_name: str
    exam_type: str
    held_on: date
    marks_obtained: Decimal | int | str
    maximum_marks: Decimal | int | str
    pass_marks: Decimal | int | str | None
    mark_id: int = 0


def quantize_score(value: Decimal) -> Decimal:
    """Round a mark or percentage to two decimal places, half up."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_score(value: Decimal) -> str:
    """Show a quantized score with two decimal places, such as 38.00."""
    return format(quantize_score(value), "f")


def validate_mark_values(
    marks_obtained: Decimal | int | str,
    maximum_marks: Decimal | int | str,
    pass_marks: Decimal | int | str | None,
) -> tuple[Decimal, Decimal, Decimal | None]:
    """Check a mark and return the three scores rounded to two places.

    A missing pass mark is valid. It means the result is not assessed.
    """
    obtained = quantize_score(Decimal(str(marks_obtained)))
    maximum = quantize_score(Decimal(str(maximum_marks)))
    if obtained < 0:
        raise ValueError("marks_obtained cannot be negative.")
    if maximum <= 0:
        raise ValueError("maximum_marks must be greater than zero.")
    if obtained > maximum:
        raise ValueError("marks_obtained cannot be greater than maximum_marks.")

    if pass_marks is None:
        return obtained, maximum, None

    passing = quantize_score(Decimal(str(pass_marks)))
    if passing < 0:
        raise ValueError("pass_marks cannot be negative.")
    if passing > maximum:
        raise ValueError("pass_marks cannot be greater than maximum_marks.")
    return obtained, maximum, passing


def percentage(marks_obtained: Decimal, maximum_marks: Decimal) -> Decimal:
    """Return marks_obtained / maximum_marks as a percentage."""
    return quantize_score(marks_obtained / maximum_marks * Decimal("100"))


AGGREGATE_METHOD = (
    "Overall percentage is the sum of marks obtained divided by the sum of "
    "maximum marks across every stored assessment. A missing assessment is "
    "left out. It is not treated as zero."
)


def aggregate_percentage(results: list[dict]) -> dict:
    """Calculate one overall percentage from stored assessments.

    The denominator is the sum of those assessments' maximum marks. When no
    assessment is stored, the percentage is missing rather than zero.
    """
    if not results:
        return {
            "marks_counted": 0,
            "marks_obtained": None,
            "maximum_marks": None,
            "percentage": None,
            "method": AGGREGATE_METHOD,
        }

    obtained = sum((Decimal(str(item["marks_obtained"])) for item in results), Decimal("0"))
    maximum = sum((Decimal(str(item["maximum_marks"])) for item in results), Decimal("0"))
    obtained = quantize_score(obtained)
    maximum = quantize_score(maximum)
    overall = None
    if maximum > 0:
        overall = percentage(obtained, maximum)
    return {
        "marks_counted": len(results),
        "marks_obtained": obtained,
        "maximum_marks": maximum,
        "percentage": overall,
        "method": AGGREGATE_METHOD,
    }


def attendance_percentage(attended: int, total: int) -> Decimal | None:
    """Return attended / total as a percentage.

    Zero sessions means the percentage is unavailable. It is not zero and it
    is not a failure.
    """
    if attended < 0 or total < 0:
        raise ValueError("Attendance counts cannot be negative.")
    if attended > total:
        raise ValueError("Attended sessions cannot be greater than total sessions.")
    if total == 0:
        return None
    return percentage(Decimal(attended), Decimal(total))


def official_status(marks_obtained: Decimal, pass_marks: Decimal | None) -> str:
    """Return pass, fail, or not_assessed.

    fail is returned only when a pass mark is present and the score is below it.
    A score equal to the pass mark is a pass.
    """
    if pass_marks is None:
        return NOT_ASSESSED
    if marks_obtained < pass_marks:
        return FAIL
    return PASS


def guidance_label(percentage_value: Decimal) -> str:
    """Label the percentage for study guidance. This is not pass or fail."""
    if percentage_value >= STRONG_PERCENTAGE:
        return STRONG
    if percentage_value >= DEVELOPING_PERCENTAGE:
        return DEVELOPING
    return NEEDS_ATTENTION


def explain_result(
    marks_obtained: Decimal,
    maximum_marks: Decimal,
    pass_marks: Decimal | None,
    percentage_value: Decimal,
    status: str,
    label: str,
) -> str:
    """Explain the official status and the separate guidance label."""
    obtained_text = format_score(marks_obtained)
    maximum_text = format_score(maximum_marks)
    percentage_text = format_score(percentage_value)

    if status == NOT_ASSESSED:
        official = (
            f"No pass mark is recorded, so {obtained_text} out of {maximum_text} "
            "is not assessed as pass or fail."
        )
    elif status == FAIL:
        official = (
            f"{obtained_text} out of {maximum_text} is below the pass mark of "
            f"{format_score(pass_marks)}, so the official result is fail."
        )
    else:
        official = (
            f"{obtained_text} out of {maximum_text} meets the pass mark of "
            f"{format_score(pass_marks)}, so the official result is pass."
        )

    if label == STRONG:
        band = "at least 75%"
    elif label == DEVELOPING:
        band = "from 50% up to but not including 75%"
    else:
        band = "below 50%"

    guidance = (
        f"The percentage {percentage_text}% is {band}, so the guidance label is {label}. "
        "The guidance label is not an official result."
    )
    return official + " " + guidance


def history_note(
    current_percentage: Decimal,
    previous: dict | None,
    ambiguous: bool,
) -> str:
    """Describe the change from the most recent earlier result, when one exists."""
    if ambiguous:
        return (
            "More than one earlier result for this subject has the same most recent date, "
            "so no historical comparison was made."
        )
    if previous is None:
        return "No earlier result for this subject was found, so no historical comparison was made."

    change = previous["percentage_change"]
    if previous["direction"] == IMPROVED:
        movement = f"increased by {format_score(change)} points"
    elif previous["direction"] == DECLINED:
        movement = f"decreased by {format_score(abs(change))} points"
    else:
        movement = "did not change"

    return (
        f"Compared with {previous['examination_name']} on {previous['held_on'].isoformat()}, "
        f"the percentage moved from {format_score(previous['percentage'])}% to "
        f"{format_score(current_percentage)}% and {movement}. "
        "This comparison uses percentages only."
    )


def build_results(scores: list[ScoreInput]) -> list[dict]:
    """Calculate every result, then attach one earlier comparison when it is clear.

    An earlier result counts only when it is the same subject and its date is
    strictly earlier. When two earlier results share that latest date, no
    comparison is made, because the order of those two results is unknown.
    """
    prepared: list[dict] = []
    for score in scores:
        obtained, maximum, passing = validate_mark_values(
            score.marks_obtained,
            score.maximum_marks,
            score.pass_marks,
        )
        percentage_value = percentage(obtained, maximum)
        status = official_status(obtained, passing)
        label = guidance_label(percentage_value)
        prepared.append(
            {
                "mark_id": score.mark_id,
                "student_id": score.student_id,
                "subject_id": score.subject_id,
                "subject_code": score.subject_code,
                "subject_name": score.subject_name,
                "examination_id": score.examination_id,
                "examination_name": score.examination_name,
                "exam_type": score.exam_type,
                "held_on": score.held_on,
                "marks_obtained": obtained,
                "maximum_marks": maximum,
                "pass_marks": passing,
                "percentage": percentage_value,
                "official_status": status,
                "guidance_label": label,
                "explanation": explain_result(
                    obtained,
                    maximum,
                    passing,
                    percentage_value,
                    status,
                    label,
                ),
            }
        )

    for item in prepared:
        earlier = [
            other
            for other in prepared
            if other["subject_id"] == item["subject_id"]
            and other["student_id"] == item["student_id"]
            and other["held_on"] < item["held_on"]
        ]
        previous = None
        ambiguous = False
        if earlier:
            latest_date = max(other["held_on"] for other in earlier)
            candidates = [other for other in earlier if other["held_on"] == latest_date]
            if len(candidates) == 1:
                source = candidates[0]
                change = quantize_score(item["percentage"] - source["percentage"])
                if change > 0:
                    direction = IMPROVED
                elif change < 0:
                    direction = DECLINED
                else:
                    direction = UNCHANGED
                previous = {
                    "examination_id": source["examination_id"],
                    "examination_name": source["examination_name"],
                    "exam_type": source["exam_type"],
                    "held_on": source["held_on"],
                    "percentage": source["percentage"],
                    "official_status": source["official_status"],
                    "percentage_change": change,
                    "direction": direction,
                }
            else:
                ambiguous = True

        item["previous_result"] = previous
        item["history_note"] = history_note(item["percentage"], previous, ambiguous)

    prepared.sort(
        key=lambda row: (row["held_on"], row["subject_name"], row["examination_id"])
    )
    return prepared
