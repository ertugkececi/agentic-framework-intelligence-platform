from app.core import BusinessUnit, component, AuditSink, SharedCache
from app.support import ProfileStorage, ProfileConverter
@component
class ProfileService(BusinessUnit):
 def __init__(self): self.audit=AuditSink(__name__); self.cache=SharedCache(); self.storage=ProfileStorage(); self.converter=ProfileConverter()
 def work(self): self.audit.record('x'); self.storage.save(self.converter.convert({}))
