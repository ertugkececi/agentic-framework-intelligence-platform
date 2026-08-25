"""Provider-neutral model boundary. Provider adapters live outside the domain."""
from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from agentic_platform.domain.models import CodingContext


class CodingModel(Protocol):
    def generate_service(self, service_name: str, context: CodingContext) -> str: ...


class DeterministicPythonCodingModel:
    """Produces source exclusively from a runtime-assembled coding context."""

    def generate_service(self, service_name: str, context: CodingContext) -> str:
        symbols_by_module: dict[str, list[str]] = defaultdict(list)
        for import_spec in context.imports:
            symbols_by_module[import_spec.module].append(import_spec.symbol)
        imports = "\n".join(
            f"from {module} import {', '.join(sorted(set(symbols)))}"
            for module, symbols in sorted(symbols_by_module.items())
        )
        return f'''{imports}


@{context.service_decorator}
class {service_name}({context.service_base_class}):
    """Generated from runtime-retrieved framework rules."""

    def __init__(self) -> None:
        self.{context.logger_attribute} = {context.logger_class}(__name__)

    def get_account(self, account_id: str) -> dict[str, str]:
        self.{context.logger_attribute}.{context.logger_method}("Retrieving customer account")
        return {{"account_id": account_id}}
'''
