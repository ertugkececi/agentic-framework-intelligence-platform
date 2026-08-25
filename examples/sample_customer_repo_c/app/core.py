def component(cls): return cls
class BusinessUnit: pass
class AuditSink:
 def __init__(self,name): self.name=name
 def record(self,message): pass
class SharedCache: pass
