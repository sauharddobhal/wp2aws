"""Allowlist-only reader for wp-config.php constants.

This is deliberately an allowlist, not a denylist-plus-redaction. A denylist has to be
remembered and updated every time a new secret-shaped constant becomes relevant; an
allowlist fails safe by construction, anything not explicitly named here is never
extracted, regardless of what it's called or what it looks like.

DB_PASSWORD, DB_USER, DB_HOST, AUTH_KEY, SECURE_AUTH_KEY, LOGGED_IN_KEY, NONCE_KEY, and
all *_SALT variants are intentionally absent from the allowlist and will never appear in
any wp2aws output.
"""

from __future__ import annotations

import re

# Only these constants are ever extracted from wp-config.php. Values are booleans or
# short config strings, never credentials.
SAFE_CONSTANTS = {
    "WP_CACHE",
    "WP_DEBUG",
    "DISABLE_WP_CRON",
    "WP_MEMORY_LIMIT",
    "WP_MAX_MEMORY_LIMIT",
}

_DEFINE_PATTERN = re.compile(
    r"""define\s*\(\s*['"](?P<name>[A-Z_]+)['"]\s*,\s*(?P<value>true|false|'[^']*'|"[^"]*"|\d+)\s*\)""",
    re.IGNORECASE,
)


def extract_safe_constants(php_source: str) -> dict[str, str]:
    """Returns only the SAFE_CONSTANTS found in the given wp-config.php text.

    Any constant name not in SAFE_CONSTANTS is silently skipped, it is never included
    in the returned dict, never logged, and never passed through to any report.
    """
    results: dict[str, str] = {}
    for match in _DEFINE_PATTERN.finditer(php_source):
        name = match.group("name").upper()
        if name not in SAFE_CONSTANTS:
            continue
        raw_value = match.group("value")
        results[name] = _normalize_value(raw_value)
    return results


def _normalize_value(raw_value: str) -> str:
    if raw_value.lower() == "true":
        return "true"
    if raw_value.lower() == "false":
        return "false"
    return raw_value.strip("'\"")


def assert_no_secrets_leaked(extracted: dict[str, str]) -> None:
    """Defense-in-depth check: raises if anything resembling a secret somehow ended up
    in an extracted-constants dict. This should never trigger given extract_safe_constants
    only returns allowlisted names, it exists so a future change to the allowlist that
    accidentally includes a sensitive name fails loudly in tests rather than shipping.
    """
    forbidden_substrings = ("KEY", "SALT", "PASSWORD", "SECRET", "DB_USER", "DB_HOST")
    for name in extracted:
        for forbidden in forbidden_substrings:
            if forbidden in name:
                raise AssertionError(
                    f"Refusing to proceed: extracted constant '{name}' contains "
                    f"'{forbidden}', which suggests a secret-shaped value almost made "
                    f"it into output. This should be unreachable; check SAFE_CONSTANTS."
                )
