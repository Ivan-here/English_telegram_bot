"""Render feedback with Telegram HTML while keeping learner text escaped."""

import re
from html import escape


def feedback_html(text: str) -> str:
    lines = []
    for line in text.splitlines():
        # Tolerate Markdown decoration from a model without displaying its stars.
        plain = line.strip()
        label = re.match(
            r"^(?:\*\*|__)?(Original|Correction|Explanation|Pattern|Rule|Example|Hint|Answer|Why it matters|Your focus|Progress|Next step|Practice|Overview)(?:\*\*|__)?\s*:(?:\*\*|__)?\s*(.*)$",
            plain, re.IGNORECASE,
        )
        heading = re.fullmatch(
            r"(?:\*\*|__)?((?:\d+[.)]\s+.+)|(?:Practice(?: exercise)?|Feedback|Your feedback|Overview|Your strengths|Your focus|Progress|Next step|Lesson|Sentence patterns):?)(?:\*\*|__)?",
            plain, re.IGNORECASE,
        )
        if label:
            lines.append(f"<b>{label[1].capitalize()}:</b> {escape(label[2])}")
        elif heading:
            title = heading[1].removesuffix("**").removesuffix("__")
            if lines and lines[-1]:
                lines.append("")
            lines.append(f"<b>{escape(title)}</b>")
        else:
            lines.append(escape(line))
    return "\n".join(lines)


def text_chunks(text, limit=3500):
    """Prefer paragraph/line boundaries so long lessons remain readable."""
    while len(text) > limit:
        end = text.rfind("\n\n", 0, limit + 1)
        if end < limit // 2:
            end = text.rfind("\n", 0, limit + 1)
        if end < limit // 2:
            end = text.rfind(" ", 0, limit + 1)
        if end <= 0:
            end = limit
        yield text[:end]
        text = text[end:].lstrip()
    if text:
        yield text
