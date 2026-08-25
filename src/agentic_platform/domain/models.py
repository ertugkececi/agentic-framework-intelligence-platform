from dataclasses import dataclass, field
from typing import Mapping
@dataclass(frozen=True)
class Evidence: source_path:str; symbol:str; observation:str; polarity:str='support'
@dataclass(frozen=True)
class FrameworkRule:
 kind:str; expected_value:str; confidence:float; support_count:int; conflict_count:int; evidence:tuple[Evidence,...]; metadata:Mapping[str,object]=field(default_factory=dict); origin:str='deterministic_inferred'; status:str='active'; framework_version:str='1.0'; discovered_at:object=field(default_factory=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc))
@dataclass(frozen=True)
class ImportSpec: module:str; symbol:str
@dataclass(frozen=True)
class CodeExample: source_path:str; symbol:str; snippet:str
@dataclass(frozen=True)
class DependencyContext:
 attribute:str; class_name:str|None; import_module:str|None; methods:tuple[str,...]; type_pattern:str|None=None
@dataclass(frozen=True)
class CodingContext:
 service_base_class:str; service_decorator:str; imports:tuple[ImportSpec,...]; dependencies:tuple[DependencyContext,...]; examples:tuple[CodeExample,...]
@dataclass(frozen=True)
class CommandResult: passed:bool; command:tuple[str,...]; output:str
@dataclass(frozen=True)
class ValidationFinding: rule_kind:str; message:str; severity:str='error'
@dataclass(frozen=True)
class ValidationReport: passed:bool; findings:tuple[ValidationFinding,...]=()
