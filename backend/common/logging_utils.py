import re

from django.utils.log import ServerFormatter


_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(x-agent-token\s*[:=]\s*)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(ticket=)[^&\s]+"), r"\1[REDACTED]"),
    (
        re.compile(r"(?i)((?:password|passwd|secret|refresh|token)\s*[:=]\s*)[^\s,;]+"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "[REDACTED-JWT]",
    ),
)


def redact_secrets(value):
    text = str(value)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(ServerFormatter):
    def format(self, record):
        return redact_secrets(super().format(record))
