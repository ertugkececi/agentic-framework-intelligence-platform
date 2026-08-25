"""Rule selection and deterministic coding-context assembly."""
from __future__ import annotations
import ast
from collections import defaultdict
from pathlib import Path
from agentic_platform.domain.models import CodeExample,CodingContext,DependencyContext,ImportSpec,FrameworkRule
class AmbiguousFrameworkRuleError(ValueError): pass
def select_rule(rules:list[FrameworkRule],kind:str)->FrameworkRule:
    candidates=[r for r in rules if r.kind==kind]
    if not candidates: raise ValueError(f"Missing active rule: {kind}")
    ranked=sorted(candidates,key=lambda r:(r.confidence,r.support_count,-r.conflict_count),reverse=True)
    if len(ranked)>1 and (ranked[0].confidence,ranked[0].support_count,ranked[0].conflict_count)==(ranked[1].confidence,ranked[1].support_count,ranked[1].conflict_count): raise AmbiguousFrameworkRuleError(kind)
    return ranked[0]
def retrieve_service_context(store,repository:Path):
    rules=store.active_rules_for("service")+store.active_rules_for("dependency")
    base=select_rule(rules,"service.base_class"); decorator=select_rule(rules,"service.required_decorator")
    imports=[ImportSpec(base.metadata["import_module"],base.expected_value),ImportSpec(decorator.metadata["import_module"],decorator.expected_value)]
    dependencies=[]
    for rule in [r for r in rules if r.kind=="dependency.constructor"]:
        types=rule.metadata["concrete_types"]; modules=rule.metadata["import_modules"]; concrete=types[0] if len(types)==1 else None; module=modules[0] if len(modules)==1 else None
        dependencies.append(DependencyContext(rule.expected_value,concrete,module,tuple(rule.metadata["usage_methods"]),tuple(rule.metadata["constructor_arguments"]),rule.metadata.get("type_pattern")))
        if concrete and module: imports.append(ImportSpec(module,concrete))
    examples=[]
    for relative in sorted({r.evidence[0].source_path for r in rules if r.evidence})[:3]:
        source=(repository/relative).read_text(); tree=ast.parse(source); service=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name.endswith("Service")); examples.append(CodeExample(relative,service.name,ast.get_source_segment(source,service) or ""))
    return rules,CodingContext(base.expected_value,decorator.expected_value,tuple(imports),tuple(dependencies),tuple(examples))
