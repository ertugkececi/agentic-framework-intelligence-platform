import ast
from collections import defaultdict
from pathlib import Path
from agentic_platform.domain.models import Evidence, FrameworkRule
class FrameworkLearner:
 def __init__(self,minimum_evidence=3): self.minimum_evidence=minimum_evidence
 def learn(self,repository:Path):
  obs=defaultdict(lambda:defaultdict(list)); count=0
  for path in repository.rglob('*.py'):
   if 'tests' in path.parts: continue
   src=path.read_text(); tree=ast.parse(src); imports={a.asname or a.name:n.module for n in tree.body if isinstance(n,ast.ImportFrom) and n.module for a in n.names}
   for cls in [n for n in tree.body if isinstance(n,ast.ClassDef) and n.name.endswith('Service') and (n.bases or n.decorator_list)]:
    count+=1; rel=path.relative_to(repository).as_posix()
    for kind,nodes in [('service.base_class',cls.bases),('service.required_decorator',cls.decorator_list)]:
     for n in nodes:
      v=n.id if isinstance(n,ast.Name) else ''; obs[kind][v,imports.get(v,'')].append(Evidence(rel,cls.name,v))
    deps={}
    init=next((n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__'),None)
    for n in ast.walk(init) if init else []:
     if isinstance(n,ast.Assign) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name):
      for t in n.targets:
       if isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name) and t.value.id=='self': deps[t.attr]=n.value.func.id
    for attr,typ in deps.items():
     methods=sorted({n.func.attr for n in ast.walk(cls) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Attribute) and isinstance(n.func.value.value,ast.Name) and n.func.value.value.id=='self' and n.func.value.attr==attr})
     obs['dependency.constructor'][attr].append((Evidence(rel,cls.name,attr),typ,imports.get(typ,''),methods))
  rules=[]
  for kind,items in obs.items():
   for key,vals in items.items():
    if kind=='dependency.constructor':
     ev=[x[0] for x in vals]; types=sorted({x[1] for x in vals}); mods=sorted({x[2] for x in vals if x[2]}); methods=sorted({m for x in vals for m in x[3]}); meta={'concrete_types':types,'import_modules':mods,'usage_methods':methods,'type_pattern':('*'+types[0].split(types[0].rstrip('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'))[-1] if False else ('*'+next((t[t.rfind('Repository'):] for t in types if t.endswith('Repository')), next((t[t.rfind('Mapper'):] for t in types if t.endswith('Mapper')), ''))))}; value=key
     if not meta['type_pattern']: meta.pop('type_pattern')
    else: ev=vals; value=key[0]; meta={'import_module':key[1]} if key[1] else {}
    support=len(ev); rules.append(FrameworkRule(kind,value,support/count,support,count-support,tuple(ev),meta))
  return rules
