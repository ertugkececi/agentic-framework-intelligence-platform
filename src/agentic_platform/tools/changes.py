"""Capability-enforced generated-change validation and application."""
from pathlib import Path
from agentic_platform.security.policy import Capability,CapabilityGrant
from agentic_platform.tasks.types import GeneratedChange
class ChangeValidationError(ValueError): pass
def validate_change(change:GeneratedChange,repository:Path)->None:
 for file in change.files:
  target=(repository/file.path).resolve()
  if Path(file.path).is_absolute() or repository.resolve() not in target.parents or not file.content: raise ChangeValidationError(file.path)
def apply_change(change:GeneratedChange,repository:Path,grant:CapabilityGrant)->list[str]:
 grant.require(Capability.WRITE_REPOSITORY); validate_change(change,repository)
 for file in change.files:
  target=repository/file.path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(file.content,encoding="utf-8")
 return [file.path for file in change.files]
