"""Small checks used before a row is saved.

Pydantic calls these functions, so a bad request becomes HTTP 422 before
PostgreSQL sees it. The database constraints remain as a second guard.
"""

import re

from app.models import (
    ASSISTANCE_TYPES,
    ATTENDANCE_STATUSES,
    CONCERN_PRIORITIES,
    CONCERN_STATUSES,
    ACTIVE_EXAM_TYPES,
    PREFERRED_FORMATS,
    RESOURCE_RATINGS,
    RESOURCE_TYPES,
    VERIFICATION_STATUSES,
)

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def clean_text(value: str | None, field_name: str, limit: int, required: bool = False) -> str | None:
    """Trim text and reject values that are empty when required, or too long."""
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required.")
        return None
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ValueError(f"{field_name} is required.")
        return None
    if len(cleaned) > limit:
        raise ValueError(f"{field_name} must be {limit} characters or fewer.")
    return cleaned


def clean_email(value: str) -> str:
    """Accept a simple mailbox address and store it in lowercase."""
    email = (value or "").strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError("email must look like name@example.com.")
    return email


def clean_choice(value: str | None, choices: tuple[str, ...], field_name: str, required: bool) -> str | None:
    """Accept only one of the known choices."""
    if value is None or not str(value).strip():
        if required:
            raise ValueError(f"{field_name} is required.")
        return None
    cleaned = str(value).strip().lower()
    if cleaned not in choices:
        allowed = ", ".join(choices)
        raise ValueError(f"{field_name} must be one of: {allowed}.")
    return cleaned


def clean_exam_type(value: str) -> str:
    """Return one of the three current examination types."""
    return clean_choice(value, ACTIVE_EXAM_TYPES, "exam_type", required=True)


def clean_preferred_format(value: str) -> str:
    """Return videos, books, examples, or exercises."""
    return clean_choice(value, PREFERRED_FORMATS, "preferred_format", required=True)


def clean_resource_rating(value: str | None) -> str | None:
    """Return useful, unhelpful, or None when the student did not rate a resource."""
    return clean_choice(value, RESOURCE_RATINGS, "resource_rating", required=False)


def clean_password(value: str) -> str:
    """Accept a password that bcrypt can store. The value is not trimmed."""
    password = value or ""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or fewer.")
    return password


def clean_attendance_status(value: str) -> str:
    """Return present or absent."""
    return clean_choice(value, ATTENDANCE_STATUSES, "status", required=True)


def clean_concern_status(value: str) -> str:
    """Return one workflow status."""
    return clean_choice(value, CONCERN_STATUSES, "status", required=True)


def clean_priority(value: str) -> str:
    """Return low, normal, or high."""
    return clean_choice(value, CONCERN_PRIORITIES, "priority", required=True)


def clean_assistance_type(value: str) -> str:
    """Return the kind of help the student asked for."""
    return clean_choice(value, ASSISTANCE_TYPES, "assistance_type", required=True)


def clean_resource_type(value: str) -> str:
    """Return book, website, course, or video."""
    return clean_choice(value, RESOURCE_TYPES, "resource_type", required=True)


def clean_whole_number(value, field_name: str, maximum: int):
    """Accept a missing score or a whole number from 0 through maximum.

    A blank value stays missing. A decimal, a negative number, or a score
    above the maximum is rejected. Zero is kept when it was entered.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        if not value.strip().isdigit():
            raise ValueError(f"{field_name} must be a whole number from 0 through {maximum}.")
        value = int(value.strip())
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a whole number from 0 through {maximum}.")
    if value < 0 or value > maximum:
        raise ValueError(f"{field_name} must be a whole number from 0 through {maximum}.")
    return value


def clean_verification_status(value: str) -> str:
    """Return verified or unverified."""
    return clean_choice(value, VERIFICATION_STATUSES, "verification_status", required=True)


_MARKDOWN_LINK = re.compile(
    r"^\[[^\]]*\]\(\s*(https?://[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)$",
    re.IGNORECASE,
)
_ANGLE_LINK = re.compile(r"^<(https?://[^>\s]+)>$", re.IGNORECASE)


def clean_https_url(value: str) -> str:
    """Accept an http or https URL and reject anything else.

    A Markdown link or angle-bracket link is reduced to the URL inside it.
    A URL that is already plain is left unchanged, including parentheses.
    """
    if value is None or not str(value).strip():
        raise ValueError("url is required.")
    url = str(value).strip()
    markdown = _MARKDOWN_LINK.match(url)
    if markdown:
        url = markdown.group(1)
    else:
        angle = _ANGLE_LINK.match(url)
        if angle:
            url = angle.group(1)
    if len(url) > 300:
        raise ValueError("url must be 300 characters or fewer.")
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("url must start with http:// or https://.")
    return url
