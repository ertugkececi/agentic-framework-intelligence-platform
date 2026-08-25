"""Provider-neutral model boundary. Provider adapters live outside the domain."""
from __future__ import annotations

from typing import Protocol


class CodingModel(Protocol):
    def generate_service(self, service_name: str, context: str) -> str: ...


class DeterministicPythonCodingModel:
    """Executable local PoC model: produces a rule-constrained source artifact.

    It is deliberately not an LLM mock. Production adapters implement the same port.
    """

    def generate_service(self, service_name: str, context: str) -> str:
        return f'''from app.framework import BaseService, CompanyLogger, business_service


@business_service
class {service_name}(BaseService):
    """Generated from retrieved framework rules and local examples."""

    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def get_account(self, account_id: str) -> dict[str, str]:
        self.logger.info("Retrieving customer account")
        return {{"account_id": account_id}}
'''
