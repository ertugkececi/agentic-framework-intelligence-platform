from collections import defaultdict
from agentic_platform.domain.models import CodingContext
class DeterministicPythonCodingModel:
 def generate_service(self,service_name,context:CodingContext):
  groups=defaultdict(list)
  for x in context.imports: groups[x.module].append(x.symbol)
  imports='\n'.join(f"from {m} import {', '.join(sorted(set(s)))}" for m,s in sorted(groups.items()))
  deps=[d for d in context.dependencies if d.class_name]
  init='\n'.join(f'        self.{d.attribute} = {d.class_name}(__name__)' for d in deps)
  usable=next((d for d in deps if d.methods),None)
  call=f'self.{usable.attribute}.{usable.methods[0]}("Retrieving customer account")' if usable else 'pass'
  return f'''{imports}\n\n@{context.service_decorator}\nclass {service_name}({context.service_base_class}):\n    def __init__(self) -> None:\n{init}\n\n    def get_account(self, account_id: str) -> dict[str, str]:\n        {call}\n        return {{"account_id": account_id}}\n'''
