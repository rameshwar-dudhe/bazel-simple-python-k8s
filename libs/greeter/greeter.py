"""Shared business logic.

This library is deliberately boring: its job in this repo is to be the *shared
node in the build graph*. Both //services/api and //services/worker depend on
it, so touching this file rebuilds and retests both services, while touching a
single service rebuilds only that one.
"""

from libs.version.version import VERSION

DEFAULT_NAME = "world"


def greet(name: str | None = None) -> str:
    """Return the greeting shown by every service."""
    cleaned = (name or "").strip() or DEFAULT_NAME
    return f"hello, {cleaned}!"


def build_info(service: str, environment: str = "local") -> dict:
    """Metadata every service exposes on /version.

    Having one implementation means the release pipeline can assert the same
    JSON shape for every image during smoke validation.
    """
    return {
        "service": service,
        "version": VERSION,
        "environment": environment,
    }
