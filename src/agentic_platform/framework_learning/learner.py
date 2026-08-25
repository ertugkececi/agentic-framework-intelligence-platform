"""Generic AST learning of repeated service structures."""
from __future__ import annotations
import ast
from collections import defaultdict
from pathlib import Path
from agentic_platform.domain.models import Evidence, FrameworkRule, RuleStatus
class FrameworkLearner:
    def __init__(self, minimum_evidence:int=3, active_threshold:float=.8)->None:
        self.minimum_evidence=minimum_evidence; self.active_threshold=active_threshold
    def learn(self, repository:Path)->list[FrameworkRule]:
        observations=defaultdict(lambda:defaultdict(list)); services=0
        for path in repository.rglob("*.py"):
            if "tests" in path.parts: continue
            source=path.read_text(); tree=ast.parse(source); imports=self._imports(tree); relative=path.relative_to(repository).as_posix()
            for service in self._services(tree):
                services+=1; self._observe(observations,service,imports,relative)
        return self._rules(observations,services)
    def _services(self,tree): return [n for n in tree.body if isinstance(n,ast.ClassDef) and n.name.endswith("Service") and (n.bases or n.decorator_list)]
    def _observe(self,obs,service,imports,path):
        for kind,nodes in (("service.base_class",service.bases),("service.required_decorator",service.decorator_list)):
            for node in nodes:
                name=self._name(node)
                if name: obs[kind][name,imports.get(name,"")].append(Evidence(path,service.name,name))
        for attribute,(name,args) in self._dependencies(service).items():
            methods=sorted(self._calls(service,attribute)); obs["dependency.constructor"][attribute].append((Evidence(path,service.name,attribute),name,imports.get(name,""),args,methods))
    def _rules(self,obs,services):
        rules=[]
        for kind,values in obs.items():
            for key,entries in values.items():
                if kind=="dependency.constructor":
                    evidence=tuple(x[0] for x in entries); types=sorted({x[1] for x in entries}); modules=sorted({x[2] for x in entries if x[2]}); args=sorted({x[3] for x in entries}); methods=sorted({m for x in entries for m in x[4]}); metadata={"concrete_types":types,"import_modules":modules,"constructor_arguments":args[0] if len(args)==1 else (),"usage_methods":methods,"type_pattern":self._suffix(types)}; expected=key
                else: evidence=tuple(entries); expected,module=key; metadata={"import_module":module} if module else {}
                support=len(evidence); confidence=support/services if services else 0; status=RuleStatus.ACTIVE if support>=self.minimum_evidence and confidence>=self.active_threshold else RuleStatus.CANDIDATE
                rules.append(FrameworkRule(kind,expected,confidence,support,services-support,evidence,metadata,status=status))
        return rules
    def _dependencies(self,service):
        result={}; init=next((n for n in service.body if isinstance(n,ast.FunctionDef) and n.name=="__init__"),None)
        for node in ast.walk(init) if init else ():
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name):
                args=tuple("__name__" if isinstance(a,ast.Name) and a.id=="__name__" else repr(a.value) if isinstance(a,ast.Constant) else "unsupported" for a in node.value.args)
                for target in node.targets:
                    if isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=="self": result[target.attr]=(node.value.func.id,args)
        return result
    def _calls(self,service,attribute):
        return {n.func.attr for n in ast.walk(service) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Attribute) and isinstance(n.func.value.value,ast.Name) and n.func.value.value.id=="self" and n.func.value.attr==attribute}
    def _imports(self,tree): return {a.asname or a.name:n.module for n in tree.body if isinstance(n,ast.ImportFrom) and n.module for a in n.names}
    def _suffix(self,types):
        if len(types)<2:return None
        suffix=types[0]
        for value in types[1:]:
            while suffix and not value.endswith(suffix): suffix=suffix[1:]
        return "*"+suffix if len(suffix)>=4 and suffix[0].isupper() else None
    def _name(self,node): return node.id if isinstance(node,ast.Name) else node.attr if isinstance(node,ast.Attribute) else ""
