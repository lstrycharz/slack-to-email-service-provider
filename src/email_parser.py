"""Email extraction: bounded regex, lowercasing, dedup."""

import re

# Character-class based (linear-time, no backtracking blowup); bounded lengths
# per RFC limits; requires a dotted domain — deliberately stricter than
# email.utils.parseaddr, which accepts strings like "foo@bar".
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}")


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from free-form message text.

    Args:
        text: Raw Slack message text.

    Returns:
        Lowercased, deduplicated addresses in first-seen order. Empty list
        if the text contains no valid address.
    """
    seen: dict[str, None] = {}
    for match in _EMAIL_RE.finditer(text):
        seen.setdefault(match.group().lower())
    return list(seen)
