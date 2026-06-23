import pytest

from wp2aws.scanners.secrets_filter import (
    SAFE_CONSTANTS,
    assert_no_secrets_leaked,
    extract_safe_constants,
)

SAMPLE_WP_CONFIG = """
<?php
define('DB_NAME', 'wordpress_prod');
define('DB_USER', 'admin_user_dont_leak_me');
define('DB_PASSWORD', 'SuperSecretPassword123!');
define('DB_HOST', 'prod-db.internal');
define('AUTH_KEY',         'put your unique phrase here aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
define('SECURE_AUTH_KEY',  'put your unique phrase here bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
define('LOGGED_IN_KEY',    'put your unique phrase here cccccccccccccccccccccccccccccccc');
define('NONCE_KEY',        'put your unique phrase here dddddddddddddddddddddddddddddddd');
define('AUTH_SALT',        'some-salt-value');
define('WP_CACHE', true);
define('WP_DEBUG', false);
define('DISABLE_WP_CRON', true);
define('WP_MEMORY_LIMIT', '256M');
define('WP_MAX_MEMORY_LIMIT', '512M');
"""


def test_extracts_only_allowlisted_constants():
    result = extract_safe_constants(SAMPLE_WP_CONFIG)
    assert set(result.keys()) == {
        "WP_CACHE",
        "WP_DEBUG",
        "DISABLE_WP_CRON",
        "WP_MEMORY_LIMIT",
        "WP_MAX_MEMORY_LIMIT",
    }


def test_never_extracts_db_credentials():
    result = extract_safe_constants(SAMPLE_WP_CONFIG)
    assert "DB_PASSWORD" not in result
    assert "DB_USER" not in result
    assert "DB_HOST" not in result
    assert "DB_NAME" not in result


def test_never_extracts_auth_keys_or_salts():
    result = extract_safe_constants(SAMPLE_WP_CONFIG)
    for forbidden in ("AUTH_KEY", "SECURE_AUTH_KEY", "LOGGED_IN_KEY", "NONCE_KEY", "AUTH_SALT"):
        assert forbidden not in result


def test_no_secret_values_anywhere_in_extracted_dict():
    result = extract_safe_constants(SAMPLE_WP_CONFIG)
    serialized = str(result)
    assert "SuperSecretPassword123!" not in serialized
    assert "prod-db.internal" not in serialized
    assert "admin_user_dont_leak_me" not in serialized
    assert "put your unique phrase here" not in serialized


def test_extracted_values_normalized_correctly():
    result = extract_safe_constants(SAMPLE_WP_CONFIG)
    assert result["WP_CACHE"] == "true"
    assert result["WP_DEBUG"] == "false"
    assert result["WP_MEMORY_LIMIT"] == "256M"


def test_assert_no_secrets_leaked_passes_on_clean_input():
    clean = {"WP_CACHE": "true", "WP_MEMORY_LIMIT": "256M"}
    assert_no_secrets_leaked(clean)  # should not raise


def test_assert_no_secrets_leaked_catches_accidental_secret_name():
    # Simulates a future bug where the allowlist was wrongly expanded.
    contaminated = {"WP_CACHE": "true", "DB_PASSWORD": "leaked"}
    with pytest.raises(AssertionError):
        assert_no_secrets_leaked(contaminated)


def test_allowlist_contains_no_secret_shaped_names():
    # Defense in depth on the allowlist definition itself.
    for name in SAFE_CONSTANTS:
        assert "KEY" not in name
        assert "SALT" not in name
        assert "PASSWORD" not in name
        assert "SECRET" not in name


def test_handles_empty_input():
    assert extract_safe_constants("") == {}


def test_ignores_unknown_constants():
    php = "<?php\ndefine('SOME_RANDOM_PLUGIN_SETTING', 'foo');\n"
    assert extract_safe_constants(php) == {}
