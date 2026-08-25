"""Deterministic grammar for the initial development-request PoC."""
import re
from agentic_platform.tasks.types import DevelopmentTask,OperationSpec,ParameterSpec
class TaskParseError(ValueError): pass
_PATTERN=re.compile(r"^Create (?P<artifact>[A-Z][A-Za-z0-9]*Service)(?: with method (?P<method>[a-z][A-Za-z0-9_]*)\((?P<parameters>[^)]*)\))?$")
def parse_development_task(request:str)->DevelopmentTask:
 match=_PATTERN.fullmatch(request.strip())
 if not match: raise TaskParseError("Expected: Create <Name>Service [with method name(parameters)]")
 params=tuple(ParameterSpec(item.strip()) for item in match.group("parameters").split(",") if item.strip()) if match.group("method") else ()
 operations=(OperationSpec(match.group("method"),params),) if match.group("method") else ()
 return DevelopmentTask("service",match.group("artifact"),operations)
