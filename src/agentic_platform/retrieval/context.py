from collections import defaultdict
from agentic_platform.domain.models import CodingContext,DependencyContext,ImportSpec,CodeExample
def retrieve_service_context(store,repository):
 rules=store.active_rules_for('service')+store.active_rules_for('dependency'); grouped=defaultdict(list)
 for r in rules: grouped[r.kind].append(r)
 base=grouped['service.base_class'][0]; dec=grouped['service.required_decorator'][0]
 imports=[ImportSpec(base.metadata['import_module'],base.expected_value),ImportSpec(dec.metadata['import_module'],dec.expected_value)]
 deps=[]
 for r in grouped['dependency.constructor']:
  if r.confidence<.8: continue
  types=r.metadata['concrete_types']; mods=r.metadata['import_modules']; concrete=types[0] if len(types)==1 else None; mod=mods[0] if len(mods)==1 else None
  deps.append(DependencyContext(r.expected_value,concrete,mod,tuple(r.metadata['usage_methods']),r.metadata.get('type_pattern')))
  if concrete and mod: imports.append(ImportSpec(mod,concrete))
 return rules,CodingContext(base.expected_value,dec.expected_value,tuple(imports),tuple(deps),())
