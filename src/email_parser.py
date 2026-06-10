"""Email extraction: Slack link flattening, bounded regex, lowercasing, dedup."""

import re

# Character-class based (linear-time, no backtracking blowup); bounded lengths
# per RFC limits; requires a dotted domain — deliberately stricter than
# email.utils.parseaddr, which accepts strings like "foo@bar".
# The lookbehind stops matches starting mid-token: without it, a 70-char
# local part would match as its 64-char SUFFIX — a different address.
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}"
)

# Slack wraps addresses as <mailto:href|label>. Editing a draft around an
# auto-linked email can leave a STALE href under a correct visible label —
# so extraction must trust the label (what the human saw), never the href.
_LABELED_LINK_RE = re.compile(r"<[^<>|]*\|([^<>]*)>")
_BARE_MAILTO_RE = re.compile(r"<mailto:([^<>|]+)>")


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from free-form Slack message text.

    Args:
        text: Raw Slack message text (may contain <mailto:...|...> links).

    Returns:
        Lowercased, deduplicated addresses in first-seen order. Empty list
        if the text contains no valid address.
    """
    flattened = _BARE_MAILTO_RE.sub(r"\1", _LABELED_LINK_RE.sub(r"\1", text))
    seen: dict[str, None] = {}
    for match in _EMAIL_RE.finditer(flattened):
        seen.setdefault(match.group().lower())
    return list(seen)
