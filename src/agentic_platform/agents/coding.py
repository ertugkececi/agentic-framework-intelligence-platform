"""Agent-facing implementation adapter."""
from __future__ import annotations
from pathlib import Path
from agentic_platform.security.policy import Capability, CapabilityGrant

def implement_service(repository: Path, service_name: str, context: object, model: object, grant: CapabilityGrant) -> list[str]:
    """Write generated service and its executable smoke test."""
    grant.require(Capability.WRITE_REPOSITORY)
    app_directory = repository / "app"
    tests_directory = repository / "tests"
    app_directory.mkdir(exist_ok=True)
    tests_directory.mkdir(exist_ok=True)
    source = model.generate_service(service_name, context)
    service_path = app_directory / "customer_account_service.py"
    service_path.write_text(source, encoding="utf-8")
    test_path = tests_directory / "test_customer_account_service.py"
    test_path.write_text(
        "from app.customer_account_service import CustomerAccountService\n\n"
        "def test_generated_service_returns_account_identifier():\n"
        "    assert CustomerAccountService().get_account('A')['account_id'] == 'A'\n",
        encoding="utf-8",
    )
    return ["app/customer_account_service.py"]
