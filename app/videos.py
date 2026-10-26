"""Turn a checked YouTube watch link into a safe embed address.

Only an 11-character video id from youtube.com or youtu.be is accepted.
Any other URL stays a normal link and is never placed in an iframe.
"""

from urllib.parse import parse_qs, urlparse

_VIDEO_ID = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")


def youtube_embed_url(url: str) -> str | None:
    """Return a youtube-nocookie embed URL, or None when the link is not a YouTube video."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        elif parsed.path.startswith("/embed/"):
            parts = [part for part in parsed.path.split("/") if part and part != "embed"]
            video_id = parts[0] if parts else ""
    if len(video_id) != 11 or any(character not in _VIDEO_ID for character in video_id):
        return None
    return "https://www.youtube-nocookie.com/embed/" + video_id
