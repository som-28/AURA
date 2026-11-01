"""Small helpers for preventing placeholder addresses from becoming recipients."""
from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PLACEHOLDER_LOCALS = {"user", "recipient", "test", "example", "your-email"}
_PLACEHOLDER_DOMAINS = {"example.com", "example.net", "example.org", "invalid", "localhost"}


def usable_recipient(value: object) -> str | None:
    """Return a plausible supplied email address, excluding obvious examples."""
    if not isinstance(value, str):
        return None
    address = value.strip()
    if not _EMAIL_RE.fullmatch(address):
        return None
    local, domain = address.rsplit("@", 1)
    if local.casefold() in _PLACEHOLDER_LOCALS:
        return None
    domain = domain.casefold().rstrip(".")
    if domain in _PLACEHOLDER_DOMAINS or domain.endswith(".invalid"):
        return None
    return address
