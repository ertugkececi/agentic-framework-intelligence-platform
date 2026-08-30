from __future__ import annotations

import pytest

from agentic_platform.security.secrets import SecretRedactor, SecretReference


def test_secret_reference_is_identifier_only_and_validated() -> None:
    reference = SecretReference(provider="vault", path="tenants/acme/model", key="api-key", version="7")

    assert reference.provider == "vault"
    assert reference.path == "tenants/acme/model"
    assert reference.key == "api-key"
    assert reference.version == "7"
    assert "secret-value" not in repr(reference)

    with pytest.raises(ValueError, match="provider"):
        SecretReference(provider="VAULT!", path="safe/path", key="token")
    for invalid_path in ("../escape", "safe//token", "safe/token value"):
        with pytest.raises(ValueError, match="path"):
            SecretReference(provider="vault", path=invalid_path, key="token")


def test_redactor_masks_registered_values_and_structured_credentials() -> None:
    redactor = SecretRedactor(("resolved-super-secret",))
    text = (
        "value=resolved-super-secret API_TOKEN=token-value "
        "Bearer abc.def.ghi https://alice:pw@example.test "
        '{"password": "json-value"}'
    )

    redacted = redactor.redact(text)

    for secret in ("resolved-super-secret", "token-value", "abc.def.ghi", "alice", "pw", "json-value"):
        assert secret not in redacted
    assert redacted.count("[REDACTED]") >= 5


def test_redactor_rejects_short_registered_values_to_avoid_broad_replacement() -> None:
    with pytest.raises(ValueError, match="at least 4"):
        SecretRedactor(("abc",))
