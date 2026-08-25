"""Context-only deterministic source generation."""
from __future__ import annotations
from collections import defaultdict
from agentic_platform.domain.models import CodingContext
class DeterministicPythonCodingModel:
    def generate_service(self,service_name:str,context:CodingContext)->str:
        imports=defaultdict(list)
        for item in context.imports: imports[item.module].append(item.symbol)
        import_lines="\n".join(f"from {module} import {', '.join(sorted(set(symbols)))}" for module,symbols in sorted(imports.items()))
        concrete=[d for d in context.dependencies if d.class_name]
        init="\n".join(f"        self.{d.attribute} = {d.class_name}({', '.join(d.constructor_arguments)})" for d in concrete)
        usable=next((d for d in concrete if d.methods),None); call=f"self.{usable.attribute}.{usable.methods[0]}(\"Retrieving customer account\")" if usable else "pass"
        return f'''{import_lines}\n\n@{context.service_decorator}\nclass {service_name}({context.service_base_class}):\n    def __init__(self) -> None:\n{init}\n\n    def get_account(self, account_id: str) -> dict[str, str]:\n        {call}\n        return {{"account_id": account_id}}\n'''
