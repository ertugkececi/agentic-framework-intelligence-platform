"""Agent-facing adapters with bounded, typed context."""
from __future__ import annotations

from pathlib import Path

from agentic_platform.models.gateway import CodingModel
from agentic_platform.security.policy import Capability, CapabilityGrant


def implement_service(
    repository: Path,
    service_name: str,
    rules_context: str,
    model: CodingModel,
    grant: CapabilityGrant,
) -> list[str]:
    grant.require(Capability.WRITE_REPOSITORY)
    app = repository / "app"
    tests = repository / "tests"
    app.mkdir(exist_ok=True)
    tests.mkdir(exist_ok=True)
    service_file = app / "customer_account_service.py"
    service_file.write_text(model.generate_service(service_name, rules_context), encoding="utf-8")
    (tests / "test_customer_account_service.py").write_text(
        "from app.customer_account_service import CustomerAccountService\n\n"
        "def test_get_account_returns_requested_identifier():\n"
        "    assert CustomerAccountService().get_account('A-42') == {'account_id': 'A-42'}\n",
        encoding="utf-8",
    )
    return ["app/customer_account_service.py"]
